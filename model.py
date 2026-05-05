from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil


MANUFACTURING_ACTIVITY = 1
REACTION_ACTIVITY = 11
PRODUCTION_ACTIVITIES = (MANUFACTURING_ACTIVITY, REACTION_ACTIVITY)
SHOPPING_LIST_GROUPS = {
    "minerals": {18},
    "gas": {711},
}

# --- models for the db tables ---
@dataclass(frozen=True)
class TypeInfo:
    type_id: int
    name: str
    volume: float
    icon_id: int | None
    group_id: int | None
    market_group_id: int | None


@dataclass(frozen=True)
class BlueprintProduct:
    type_id: int
    activity: int
    product_typeid: int
    quantity: float


@dataclass(frozen=True)
class MaterialRow:
    type_id: int
    activity: int
    material_typeid: int
    quantity: float


@dataclass(frozen=True)
class BlueprintActivityTime:
    type_id: int
    activity: int
    time: float


# --- models for business logic ---
# model that holds all info for a plan
@dataclass
class PlanConfig:
    # remove the | None 
    plan_id: str | None = None
    top_level_blueprints: dict[int, BlueprintSettings] | None = field(default_factory=dict)
    blueprint_settings: dict[int, BlueprintSettings] | None = field(default_factory=dict)
    buy_components: set[str] | None = field(default_factory=set)

    # remove this
    def __post_init__(self) -> None:
        self.top_level_blueprints = _copy_settings_by_id(self.top_level_blueprints)
        self.blueprint_settings = _copy_settings_by_id(self.blueprint_settings)
        self.buy_components = set(self.buy_components or set())

    def settings_for(self, blueprint_type_id: int, blueprint_name: str) -> BlueprintSettings:
        return self.blueprint_settings.get(
            blueprint_type_id,
            BlueprintSettings(blueprint_name, blueprint_type_id=blueprint_type_id),
        )

    def add_top_level_blueprint(self, settings: BlueprintSettings) -> None:
        if settings.blueprint_type_id is None:
            raise ValueError(f"Blueprint type id is required for {settings.name}.")
        if settings.blueprint_type_id in self.top_level_blueprints:
            raise ValueError(f"{settings.name} is already selected.")
        self.top_level_blueprints[settings.blueprint_type_id] = settings

    def remove_top_level_blueprints(self, blueprint_type_ids: list[int]) -> None:
        missing_ids = set(blueprint_type_ids) - set(self.top_level_blueprints)
        if missing_ids:
            raise KeyError(f"Top-level blueprints are not selected: {', '.join(str(type_id) for type_id in sorted(missing_ids))}")

        for blueprint_type_id in blueprint_type_ids:
            del self.top_level_blueprints[blueprint_type_id]

    def set_buy_component(self, component_name: str, should_buy: bool) -> None:
        if should_buy:
            self.buy_components.add(component_name)
        else:
            self.buy_components.discard(component_name)

    def update_top_level_blueprints(self, updates_by_id: dict[int, dict]) -> None:
        missing_ids = set(updates_by_id) - set(self.top_level_blueprints)
        if missing_ids:
            raise KeyError(f"Top-level blueprints are not selected: {', '.join(str(type_id) for type_id in sorted(missing_ids))}")

        for blueprint_type_id, update in updates_by_id.items():
            self.top_level_blueprints[blueprint_type_id] = _apply_settings_update(
                self.top_level_blueprints[blueprint_type_id],
                update,
                allow_runs=True,
            )

    def update_blueprint_overrides(self, updates_by_id: dict[int, dict]) -> None:
        for blueprint_type_id, update in updates_by_id.items():
            current = self.blueprint_settings.get(
                blueprint_type_id,
                BlueprintSettings(str(blueprint_type_id), blueprint_type_id=blueprint_type_id),
            )
            self.blueprint_settings[blueprint_type_id] = _apply_settings_update(current, update, allow_runs=False)

    def update_blueprints(self, updates_by_id: dict[int, dict]) -> None:
        for blueprint_type_id, update in updates_by_id.items():
            if blueprint_type_id in self.top_level_blueprints:
                self.top_level_blueprints[blueprint_type_id] = _apply_settings_update(
                    self.top_level_blueprints[blueprint_type_id],
                    update,
                    allow_runs=True,
                )
            else:
                current = self.blueprint_settings.get(
                    blueprint_type_id,
                    BlueprintSettings(str(blueprint_type_id), blueprint_type_id=blueprint_type_id),
                )
                self.blueprint_settings[blueprint_type_id] = _apply_settings_update(current, update, allow_runs=False)


# model that holds info for a print (either top level or override)
@dataclass(frozen=True)
class BlueprintSettings:
    name: str
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: float | None = None
    prints: int = 1
    blueprint_type_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_efficiency", _clamp(self.material_efficiency, 0, 10))
        object.__setattr__(self, "time_efficiency", _clamp(self.time_efficiency, 0, 20))
        object.__setattr__(self, "prints", max(1, int(self.prints)))

        if self.runs is None:
            return

        runs = float(self.runs)
        if runs <= 0:
            raise ValueError("runs must be positive when provided")
        object.__setattr__(self, "runs", runs)


@dataclass(frozen=True)
class BuildJob:
    blueprint_type_id: int
    blueprint_name: str
    activity: int
    product_type_id: int
    product_name: str
    output_per_run: float
    time_per_run: float
    settings: BlueprintSettings

    # Temporary estimate support: delete this method when fractional math is removed.
    def estimate_runs_for(self, required_quantity: float | None) -> float:
        if self.settings.runs is not None:
            return self.settings.runs
        if required_quantity is None:
            return 1.0

        output_per_job = self.output_per_run * self.settings.prints
        if output_per_job <= 0:
            return float(required_quantity)
        return float(required_quantity) / output_per_job

    def runs_for(self, required_quantity: float | None) -> float:
        if self.settings.runs is not None:
            return self.settings.runs
        if required_quantity is None:
            return 1.0

        output_per_job = self.output_per_run * self.settings.prints
        if output_per_job <= 0:
            return float(ceil(required_quantity))
        return float(ceil(float(required_quantity) / output_per_job))

    def planned_output(self, runs: float) -> float:
        return self.output_per_run * runs * self.settings.prints

    def material_modifier(self) -> float:
        if self.activity == MANUFACTURING_ACTIVITY:
            return 1.0 - (self.settings.material_efficiency / 100.0)
        return 1.0

    # Temporary estimate support: delete this method when fractional math is removed.
    def estimate_material_quantity(self, quantity_per_run: float, runs: float) -> float:
        quantity = float(quantity_per_run) * runs * self.settings.prints
        if self.activity == MANUFACTURING_ACTIVITY and quantity_per_run > 1.0:
            return quantity * self.material_modifier()
        return quantity

    def material_quantity(self, quantity_per_run: float, runs: float) -> float:
        quantity_per_print = runs * float(quantity_per_run) * self.material_modifier()
        required_per_print = max(runs, ceil(round(quantity_per_print, 2)))
        return float(required_per_print) * self.settings.prints

    def total_time(self, runs: float) -> float:
        seconds = self.time_per_run * runs * self.settings.prints
        if self.activity == MANUFACTURING_ACTIVITY:
            return seconds * (1.0 - (self.settings.time_efficiency / 100.0))
        return seconds

@dataclass
class BomLine:
    type_id: int
    name: str
    depth: int
    quantity: float
    build_job: BuildJob | None = None
    runs: float | None = None
    group_id: int | None = None

    @property
    def planned_output_quantity(self) -> float:
        if self.build_job is None or self.runs is None:
            return self.quantity
        return self.build_job.planned_output(self.runs)

    @property
    def total_time_seconds(self) -> float:
        if self.build_job is None or self.runs is None:
            return 0.0
        return self.build_job.total_time(self.runs)

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.build_job.settings if self.build_job is not None else None

    @property
    def blueprint_name(self) -> str | None:
        return self.build_job.blueprint_name if self.build_job is not None else None

    @property
    def blueprint_type_id(self) -> int | None:
        return self.build_job.blueprint_type_id if self.build_job is not None else None

    @property
    def material_efficiency(self) -> int:
        return self.blueprint_settings.material_efficiency if self.blueprint_settings is not None else 0

    @property
    def time_efficiency(self) -> int:
        return self.blueprint_settings.time_efficiency if self.blueprint_settings is not None else 0

    @property
    def prints(self) -> int:
        return self.blueprint_settings.prints if self.blueprint_settings is not None else 1

    @property
    def total_runs(self) -> float:
        return 0.0 if self.runs is None else self.runs * self.prints


@dataclass
class BomAggregate:
    type_id: int
    name: str
    quantity: float
    min_depth: int
    max_depth: int
    build_job: BuildJob | None = None
    total_time_seconds: float = 0.0
    mixed_blueprint_settings: bool = False
    group_id: int | None = None

    @classmethod
    def from_line(cls, line: BomLine) -> BomAggregate:
        return cls(
            type_id=line.type_id,
            name=line.name,
            quantity=line.quantity,
            min_depth=line.depth,
            max_depth=line.depth,
            build_job=line.build_job,
            total_time_seconds=line.total_time_seconds,
            group_id=line.group_id,
        )

    def absorb(self, line: BomLine) -> None:
        self.quantity += line.quantity
        self.total_time_seconds += line.total_time_seconds
        self.min_depth = min(self.min_depth, line.depth)
        self.max_depth = max(self.max_depth, line.depth)

        if line.build_job is None:
            return
        if self.build_job is None:
            self.build_job = line.build_job
        elif self.build_job != line.build_job:
            self.mixed_blueprint_settings = True

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.build_job.settings if self.build_job is not None else None

    @property
    def blueprint_type_id(self) -> int | None:
        return self.build_job.blueprint_type_id if self.build_job is not None else None


@dataclass
class BomSnapshot:
    request: PlanConfig
    rows: list[BomLine]
    aggregates: dict[int, BomAggregate]
    # Temporary estimate support: delete this field when the planner estimate switch is removed.
    use_estimate_math: bool = False

    @property
    def roots(self) -> list[BomLine]:
        return [row for row in self.rows if row.depth == 0]

    @property
    def root(self) -> BomLine | None:
        return self.roots[0] if self.roots else None

    @property
    def depths(self) -> dict[int, int]:
        return {type_id: aggregate.max_depth for type_id, aggregate in self.aggregates.items()}

    @property
    def total_time_seconds(self) -> float:
        return sum(row.total_time_seconds for row in self.rows)

    def get_shopping_list(self, item_group: str | None = None) -> list[dict]:
        group_ids = _shopping_list_group_ids(item_group)
        return [
            {
                "name": aggregate.name,
                "quantity": ceil(aggregate.quantity),
            }
            for aggregate in sorted(
                self.aggregates.values(),
                key=lambda aggregate: aggregate.type_id,
            )
            if aggregate.build_job is None and (group_ids is None or aggregate.group_id in group_ids)
        ]


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _shopping_list_group_ids(item_group: str | None) -> set[int] | None:
    if item_group is None:
        return None
    if item_group not in SHOPPING_LIST_GROUPS:
        raise ValueError(f"Unknown shopping list group: {item_group}")
    return SHOPPING_LIST_GROUPS[item_group]


def _copy_settings_by_id(
    settings: dict[int, BlueprintSettings] | None,
) -> dict[int, BlueprintSettings]:
    if settings is None:
        return {}

    by_id: dict[int, BlueprintSettings] = {}
    for blueprint_type_id, blueprint_settings in settings.items():
        if blueprint_settings.blueprint_type_id is None:
            raise ValueError(f"Blueprint type id is required for {blueprint_settings.name}.")
        if blueprint_type_id != blueprint_settings.blueprint_type_id:
            raise ValueError(f"Blueprint settings key does not match {blueprint_settings.name}.")
        if blueprint_settings.blueprint_type_id in by_id:
            raise ValueError(f"{blueprint_settings.name} is already selected.")
        by_id[blueprint_settings.blueprint_type_id] = blueprint_settings
    return by_id


def _apply_settings_update(
    settings: BlueprintSettings,
    update: dict,
    allow_runs: bool,
) -> BlueprintSettings:
    if not allow_runs and "runs" in update:
        raise ValueError("runs can only be updated for top-level blueprints")

    return BlueprintSettings(
        name=settings.name,
        material_efficiency=update.get("material_efficiency", settings.material_efficiency),
        time_efficiency=update.get("time_efficiency", settings.time_efficiency),
        runs=update.get("runs", settings.runs),
        prints=update.get("prints", settings.prints),
        blueprint_type_id=settings.blueprint_type_id,
    )
