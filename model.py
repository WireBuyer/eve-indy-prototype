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
# model that holds info for a print (either top level or override)
@dataclass(frozen=True)
class BlueprintSettings:
    name: str
    blueprint_type_id: int
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: float | None = None
    prints: int = 1

    def __post_init__(self) -> None:
        if self.blueprint_type_id is None:
            raise ValueError(f"Blueprint type id is required for {self.name}.")

        object.__setattr__(self, "blueprint_type_id", int(self.blueprint_type_id))
        object.__setattr__(self, "material_efficiency", _clamp(self.material_efficiency, 0, 10))
        object.__setattr__(self, "time_efficiency", _clamp(self.time_efficiency, 0, 20))
        object.__setattr__(self, "prints", max(1, int(self.prints)))

        if self.runs is None:
            return

        runs = float(self.runs)
        if runs <= 0:
            raise ValueError("runs must be positive when provided")
        object.__setattr__(self, "runs", runs)


# model that holds all info for a plan
@dataclass
class PlanConfig:
    plan_id: str | None = None
    top_level_blueprints: dict[int, BlueprintSettings] = field(default_factory=dict)
    blueprint_settings: dict[int, BlueprintSettings] = field(default_factory=dict)
    buy_component_type_ids: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.top_level_blueprints = _copy_settings_by_id(self.top_level_blueprints, allow_runs=True)
        self.blueprint_settings = _copy_settings_by_id(self.blueprint_settings, allow_runs=False)
        self.buy_component_type_ids = {int(type_id) for type_id in (self.buy_component_type_ids or set())}

    def settings_for(self, blueprint_type_id: int, blueprint_name: str) -> BlueprintSettings:
        return self.blueprint_settings.get(
            blueprint_type_id,
            BlueprintSettings(blueprint_name, blueprint_type_id=blueprint_type_id),
        )

    def remove_top_level_blueprints(self, blueprint_type_ids: list[int]) -> None:
        missing_ids = set(blueprint_type_ids) - set(self.top_level_blueprints)
        if missing_ids:
            raise KeyError(
                "Top-level blueprints are not selected: "
                f"{', '.join(str(type_id) for type_id in sorted(missing_ids))}"
            )

        for blueprint_type_id in blueprint_type_ids:
            del self.top_level_blueprints[blueprint_type_id]

    def set_buy_component(self, component_type_id: int, should_buy: bool) -> None:
        if should_buy:
            self.buy_component_type_ids.add(component_type_id)
        else:
            self.buy_component_type_ids.discard(component_type_id)

    def update_top_level_blueprints(self, updates_by_id: dict[int, dict]) -> None:
        missing_ids = set(updates_by_id) - set(self.top_level_blueprints)
        if missing_ids:
            raise KeyError(
                "Top-level blueprints are not selected: "
                f"{', '.join(str(type_id) for type_id in sorted(missing_ids))}"
            )

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


@dataclass(frozen=True)
class ProductionRecipe:
    blueprint_type_id: int
    blueprint_name: str
    activity: int
    product_type_id: int
    product_name: str
    output_per_run: float
    time_per_run: float
    product_group_id: int | None = None


@dataclass(frozen=True)
class BomEntry:
    type_id: int
    name: str
    quantity: float
    depth: int
    group_id: int | None = None
    recipe: ProductionRecipe | None = None
    settings: BlueprintSettings | None = None
    runs: float | None = None
    output_quantity: float = 0.0
    total_time_seconds: float = 0.0
    bought: bool = False

    @property
    def is_built(self) -> bool:
        return self.recipe is not None

    @property
    def is_bought(self) -> bool:
        return self.bought

    @property
    def is_base_material(self) -> bool:
        return not self.is_built and not self.bought

    @property
    def tag(self) -> str:
        if self.bought:
            return "BUY"
        if self.is_base_material:
            return "BASE"
        return ""

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.settings

    @property
    def blueprint_name(self) -> str | None:
        return None if self.recipe is None else self.recipe.blueprint_name

    @property
    def blueprint_type_id(self) -> int | None:
        return None if self.recipe is None else self.recipe.blueprint_type_id

    @property
    def material_efficiency(self) -> int:
        return 0 if self.settings is None else self.settings.material_efficiency

    @property
    def time_efficiency(self) -> int:
        return 0 if self.settings is None else self.settings.time_efficiency

    @property
    def prints(self) -> int:
        return 1 if self.settings is None else self.settings.prints

    @property
    def total_runs(self) -> float:
        return 0.0 if self.runs is None else self.runs * self.prints


@dataclass(frozen=True)
class BomResult:
    request: PlanConfig
    roots: list[BomEntry]
    entries: dict[int, BomEntry]
    use_estimate_math: bool = False

    @property
    def root(self) -> BomEntry | None:
        return self.roots[0] if self.roots else None

    @property
    def depths(self) -> dict[int, int]:
        return {type_id: entry.depth for type_id, entry in self.entries.items()}

    @property
    def depth_layers(self) -> dict[int, list[BomEntry]]:
        layers: dict[int, list[BomEntry]] = {}
        for entry in self.entries.values():
            layers.setdefault(entry.depth, []).append(entry)
        for entries in layers.values():
            entries.sort(key=lambda entry: entry.type_id)
        return layers

    @property
    def total_time_seconds(self) -> float:
        return sum(entry.total_time_seconds for entry in self.roots) + sum(
            entry.total_time_seconds for entry in self.entries.values()
        )

    @property
    def rows(self) -> list[BomEntry]:
        return self.roots + sorted(self.entries.values(), key=lambda entry: (entry.depth, entry.type_id))

    def get_shopping_list(self, item_group: str | None = None) -> list[dict]:
        group_ids = _shopping_list_group_ids(item_group)
        return [
            {
                "type_id": entry.type_id,
                "name": entry.name,
                "quantity": ceil(entry.quantity),
                "tag": entry.tag,
            }
            for entry in sorted(self.entries.values(), key=lambda entry: entry.type_id)
            if not entry.is_built and (group_ids is None or entry.group_id in group_ids)
        ]


class ProductionMath:
    def __init__(self, use_estimate_math: bool = False):
        self.use_estimate_math = use_estimate_math

    def runs_for(
        self,
        recipe: ProductionRecipe,
        settings: BlueprintSettings,
        required_quantity: float | None,
    ) -> float:
        if settings.runs is not None:
            return settings.runs
        if required_quantity is None:
            return 1.0

        output_per_job = recipe.output_per_run * settings.prints
        if output_per_job <= 0:
            return float(required_quantity if self.use_estimate_math else ceil(required_quantity))
        if self.use_estimate_math:
            return float(required_quantity) / output_per_job
        return float(ceil(float(required_quantity) / output_per_job))

    def output_quantity(self, recipe: ProductionRecipe, settings: BlueprintSettings, runs: float) -> float:
        return recipe.output_per_run * runs * settings.prints

    def material_quantity(
        self,
        recipe: ProductionRecipe,
        settings: BlueprintSettings,
        quantity_per_run: float,
        runs: float,
    ) -> float:
        if self.use_estimate_math:
            quantity = float(quantity_per_run) * runs * settings.prints
            if recipe.activity == MANUFACTURING_ACTIVITY and quantity_per_run > 1.0:
                return quantity * self.material_modifier(recipe, settings)
            return quantity

        quantity_per_print = runs * float(quantity_per_run) * self.material_modifier(recipe, settings)
        required_per_print = max(runs, ceil(round(quantity_per_print, 2)))
        return float(required_per_print) * settings.prints

    def total_time(self, recipe: ProductionRecipe, settings: BlueprintSettings, runs: float) -> float:
        seconds = recipe.time_per_run * runs * settings.prints
        if recipe.activity == MANUFACTURING_ACTIVITY:
            return seconds * (1.0 - (settings.time_efficiency / 100.0))
        return seconds

    def material_modifier(self, recipe: ProductionRecipe, settings: BlueprintSettings) -> float:
        if recipe.activity == MANUFACTURING_ACTIVITY:
            return 1.0 - (settings.material_efficiency / 100.0)
        return 1.0


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
    allow_runs: bool,
) -> dict[int, BlueprintSettings]:
    if settings is None:
        return {}

    by_id: dict[int, BlueprintSettings] = {}
    for blueprint_type_id, blueprint_settings in settings.items():
        if blueprint_type_id != blueprint_settings.blueprint_type_id:
            raise ValueError(f"Blueprint settings key does not match {blueprint_settings.name}.")
        if not allow_runs and blueprint_settings.runs is not None:
            raise ValueError("runs can only be set for top-level blueprints")
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
        blueprint_type_id=settings.blueprint_type_id,
        material_efficiency=update.get("material_efficiency", settings.material_efficiency),
        time_efficiency=update.get("time_efficiency", settings.time_efficiency),
        runs=update.get("runs", settings.runs),
        prints=update.get("prints", settings.prints),
    )
