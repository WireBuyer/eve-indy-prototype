from __future__ import annotations

from dataclasses import dataclass, field


MANUFACTURING_ACTIVITY = 1
REACTION_ACTIVITY = 11
PRODUCTION_ACTIVITIES = (MANUFACTURING_ACTIVITY, REACTION_ACTIVITY)


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
class PlanConfig:
    top_level_blueprints: list[BlueprintSettings] = field(default_factory=list)
    blueprint_settings: dict[str, BlueprintSettings] = field(default_factory=dict)
    buy_components: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.top_level_blueprints = list(self.top_level_blueprints or [])
        self.blueprint_settings = dict(self.blueprint_settings or {})
        self.buy_components = set(self.buy_components or set())

    def settings_for(self, blueprint_name: str) -> BlueprintSettings:
        return self.blueprint_settings.get(blueprint_name, BlueprintSettings(blueprint_name))

    def copy(self) -> PlanConfig:
        return PlanConfig(
            top_level_blueprints=self.top_level_blueprints,
            blueprint_settings=self.blueprint_settings,
            buy_components=self.buy_components,
        )


@dataclass
class BomNode:
    node_id: str
    type_id: int
    name: str
    depth: int
    quantity: float
    production: ProductionPlan | None = None
    runs: float | None = None
    children: list[BomNode] = field(default_factory=list)

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
    def from_node(cls, node: BomNode) -> BomAggregate:
        return cls(
            type_id=node.type_id,
            name=node.name,
            quantity=node.quantity,
            min_depth=node.depth,
            max_depth=node.depth,
            production=node.production,
            total_time_seconds=node.total_time_seconds,
        )

    def absorb(self, node: BomNode) -> None:
        self.quantity += node.quantity
        self.total_time_seconds += node.total_time_seconds
        self.min_depth = min(self.min_depth, node.depth)
        self.max_depth = max(self.max_depth, node.depth)

        if node.production is None:
            return
        if self.production is None:
            self.production = node.production
        elif self.production != node.production:
            self.mixed_blueprint_settings = True

    @property
    def blueprint_settings(self) -> BlueprintSettings | None:
        return self.production.settings if self.production is not None else None

    @property
    def blueprint_type_id(self) -> int | None:
        return self.production.blueprint_type_id if self.production is not None else None


@dataclass
class BlueprintUsage:
    production: ProductionPlan
    occurrences: int = 0
    min_depth: int = 0
    max_depth: int = 0
    total_runs: float = 0.0
    total_planned_output_quantity: float = 0.0
    total_time_seconds: float = 0.0

    @classmethod
    def from_node(cls, node: BomNode) -> BlueprintUsage:
        if node.production is None:
            raise ValueError("Blueprint usage can only be created from buildable nodes")
        return cls(
            production=node.production,
            occurrences=1,
            min_depth=node.depth,
            max_depth=node.depth,
            total_runs=node.total_runs,
            total_planned_output_quantity=node.planned_output_quantity,
            total_time_seconds=node.total_time_seconds,
        )

    def absorb(self, node: BomNode) -> None:
        self.occurrences += 1
        self.min_depth = min(self.min_depth, node.depth)
        self.max_depth = max(self.max_depth, node.depth)
        self.total_runs += node.total_runs
        self.total_planned_output_quantity += node.planned_output_quantity
        self.total_time_seconds += node.total_time_seconds


@dataclass
class BomSnapshot:
    request: PlanConfig
    roots: list[BomNode]
    aggregates: dict[int, BomAggregate]
    used_blueprints: list[BlueprintUsage]

    @property
    def root(self) -> BomNode | None:
        return self.roots[0] if self.roots else None

    @property
    def depths(self) -> dict[int, int]:
        return {type_id: aggregate.max_depth for type_id, aggregate in self.aggregates.items()}

    @property
    def total_time_seconds(self) -> float:
        return sum(usage.total_time_seconds for usage in self.used_blueprints)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))
