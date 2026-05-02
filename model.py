from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil


MANUFACTURING_ACTIVITY = 1
REACTION_ACTIVITY = 11
PRODUCTION_ACTIVITIES = (MANUFACTURING_ACTIVITY, REACTION_ACTIVITY)

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
    top_level_blueprints: dict[str, BlueprintSettings] | list[BlueprintSettings] | None = field(default_factory=dict)
    blueprint_settings: dict[str, BlueprintSettings] | None = field(default_factory=dict)
    buy_components: set[str] | None = field(default_factory=set)

    # remove this
    def __post_init__(self) -> None:
        self.top_level_blueprints = _blueprint_settings_by_name(self.top_level_blueprints)
        self.blueprint_settings = dict(self.blueprint_settings or {})
        self.buy_components = set(self.buy_components or set())

    def settings_for(self, blueprint_name: str) -> BlueprintSettings:
        return self.blueprint_settings.get(blueprint_name, BlueprintSettings(blueprint_name))

    def add_top_level_blueprint(self, settings: BlueprintSettings) -> None:
        if settings.name in self.top_level_blueprints:
            raise ValueError(f"{settings.name} is already selected.")
        self.top_level_blueprints[settings.name] = settings

    def remove_top_level_blueprints(self, blueprint_names: list[str]) -> None:
        missing_names = set(blueprint_names) - set(self.top_level_blueprints)
        if missing_names:
            raise KeyError(f"Top-level blueprints are not selected: {', '.join(sorted(missing_names))}")

        for blueprint_name in blueprint_names:
            del self.top_level_blueprints[blueprint_name]

    def set_buy_component(self, component_name: str, should_buy: bool) -> None:
        if should_buy:
            self.buy_components.add(component_name)
        else:
            self.buy_components.discard(component_name)

    def update_top_level_blueprints(self, updates_by_name: dict[str, dict]) -> None:
        missing_names = set(updates_by_name) - set(self.top_level_blueprints)
        if missing_names:
            raise KeyError(f"Top-level blueprints are not selected: {', '.join(sorted(missing_names))}")

        for blueprint_name, update in updates_by_name.items():
            self.top_level_blueprints[blueprint_name] = _apply_settings_update(
                self.top_level_blueprints[blueprint_name],
                update,
                allow_runs=True,
            )

    def update_blueprint_overrides(self, updates_by_name: dict[str, dict]) -> None:
        for blueprint_name, update in updates_by_name.items():
            current = self.blueprint_settings.get(blueprint_name, BlueprintSettings(blueprint_name))
            self.blueprint_settings[blueprint_name] = _apply_settings_update(current, update, allow_runs=False)

    def update_blueprints(self, updates_by_name: dict[str, dict]) -> None:
        for blueprint_name, update in updates_by_name.items():
            if blueprint_name in self.top_level_blueprints:
                self.top_level_blueprints[blueprint_name] = _apply_settings_update(
                    self.top_level_blueprints[blueprint_name],
                    update,
                    allow_runs=True,
                )
            else:
                current = self.blueprint_settings.get(blueprint_name, BlueprintSettings(blueprint_name))
                self.blueprint_settings[blueprint_name] = _apply_settings_update(current, update, allow_runs=False)


# model that holds info for a print (either top level or override)
@dataclass(frozen=True)
class BlueprintSettings:
    name: str
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: float | None = None
    prints: int = 1

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
class ProductionPlan:
    blueprint_type_id: int
    blueprint_name: str
    activity: int
    product_type_id: int
    product_name: str
    output_per_run: float
    time_per_run: float
    settings: BlueprintSettings

    def runs_for(self, required_quantity: float | None) -> float:
        if self.settings.runs is not None:
            return self.settings.runs
        if required_quantity is None:
            return 1.0

        output_per_job = self.output_per_run * self.settings.prints
        if output_per_job <= 0:
            return float(required_quantity)
        return float(required_quantity) / output_per_job

    def planned_output(self, runs: float) -> float:
        return self.output_per_run * runs * self.settings.prints

    def material_quantity(self, quantity_per_run: float, runs: float) -> float:
        quantity = float(quantity_per_run) * runs * self.settings.prints
        if self.activity == MANUFACTURING_ACTIVITY and quantity_per_run > 1.0:
            return quantity * (1.0 - (self.settings.material_efficiency / 100.0))
        return quantity

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
    production: ProductionPlan | None = None
    runs: float | None = None

    @property
    def planned_output_quantity(self) -> float:
        if self.production is None or self.runs is None:
            return self.quantity
        return self.production.planned_output(self.runs)

    @property
    def total_time_seconds(self) -> float:
        if self.production is None or self.runs is None:
            return 0.0
        return self.production.total_time(self.runs)

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.production.settings if self.production is not None else None

    @property
    def blueprint_name(self) -> str | None:
        return self.production.blueprint_name if self.production is not None else None

    @property
    def blueprint_type_id(self) -> int | None:
        return self.production.blueprint_type_id if self.production is not None else None

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
    production: ProductionPlan | None = None
    total_time_seconds: float = 0.0
    mixed_blueprint_settings: bool = False

    @classmethod
    def from_line(cls, line: BomLine) -> BomAggregate:
        return cls(
            type_id=line.type_id,
            name=line.name,
            quantity=line.quantity,
            min_depth=line.depth,
            max_depth=line.depth,
            production=line.production,
            total_time_seconds=line.total_time_seconds,
        )

    def absorb(self, line: BomLine) -> None:
        self.quantity += line.quantity
        self.total_time_seconds += line.total_time_seconds
        self.min_depth = min(self.min_depth, line.depth)
        self.max_depth = max(self.max_depth, line.depth)

        if line.production is None:
            return
        if self.production is None:
            self.production = line.production
        elif self.production != line.production:
            self.mixed_blueprint_settings = True

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.production.settings if self.production is not None else None

    @property
    def blueprint_type_id(self) -> int | None:
        return self.production.blueprint_type_id if self.production is not None else None


@dataclass
class BomSnapshot:
    request: PlanConfig
    rows: list[BomLine]
    aggregates: dict[int, BomAggregate]

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

    def get_shopping_list(self) -> list[dict]:
        return [
            {
                "name": aggregate.name,
                "quantity": ceil(aggregate.quantity),
            }
            for aggregate in sorted(
                self.aggregates.values(),
                key=lambda aggregate: aggregate.name,
            )
            if aggregate.production is None
        ]


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _blueprint_settings_by_name(
    settings: dict[str, BlueprintSettings] | list[BlueprintSettings] | None,
) -> dict[str, BlueprintSettings]:
    if settings is None:
        return {}
    if isinstance(settings, dict):
        return dict(settings)

    by_name: dict[str, BlueprintSettings] = {}
    for blueprint_settings in settings:
        if blueprint_settings.name in by_name:
            raise ValueError(f"{blueprint_settings.name} is already selected.")
        by_name[blueprint_settings.name] = blueprint_settings
    return by_name


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
    )
