from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


MANUFACTURING_ACTIVITY = 1


@dataclass(frozen=True)
class TypeInfo:
    type_id: int
    name: str
    volume: float
    icon_id: Optional[int]
    group_id: Optional[int]
    market_group_id: Optional[int]


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
class Blueprint:
    name: str
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: Optional[float] = None
    prints: int = 1

    def __post_init__(self):
        object.__setattr__(self, "material_efficiency", self._clamp_material_efficiency(self.material_efficiency))
        object.__setattr__(self, "time_efficiency", self._clamp_time_efficiency(self.time_efficiency))
        object.__setattr__(self, "prints", max(1, int(self.prints)))
        if self.runs is not None:
            runs = float(self.runs)
            if runs <= 0:
                raise ValueError("runs must be positive when provided")
            object.__setattr__(self, "runs", runs)

    @staticmethod
    def _clamp_material_efficiency(material_efficiency: int) -> int:
        return max(0, min(10, int(material_efficiency)))

    @staticmethod
    def _clamp_time_efficiency(time_efficiency: int) -> int:
        return max(0, min(20, int(time_efficiency)))

    def effective_for_activity(self, activity: Optional[int]) -> "Blueprint":
        if activity == MANUFACTURING_ACTIVITY:
            return self
        return Blueprint(
            self.name,
            0,
            0,
            self.runs,
            self.prints,
        )

    def resolve_runs(self, required_quantity: Optional[float], output_per_run: float) -> float:
        if self.runs is not None:
            return float(self.runs)
        if required_quantity is None:
            return 1.0
        total_output_per_job = output_per_run * self.prints
        if total_output_per_job == 0:
            return float(required_quantity)
        return float(required_quantity) / total_output_per_job

    def usage_key(self, blueprint_type_id: int) -> str:
        runs_key = "auto" if self.runs is None else self.runs
        return (
            f"{blueprint_type_id}:{self.material_efficiency}:"
            f"{self.time_efficiency}:{runs_key}:{self.prints}"
        )


@dataclass(frozen=True)
class BlueprintRecipe:
    blueprint_type_id: int
    blueprint_name: str
    activity: int
    product_type_id: int
    product_name: str
    output_per_run: float
    time_per_run: float
    blueprint: Blueprint

    def resolve_runs(self, required_quantity: Optional[float]) -> float:
        return self.blueprint.resolve_runs(required_quantity, self.output_per_run)

    def planned_output(self, runs: float) -> float:
        return self.output_per_run * runs * self.blueprint.prints

    def base_material_quantity(self, quantity_per_run: float, runs: float) -> float:
        return float(quantity_per_run) * runs * self.blueprint.prints

    def material_quantity(self, quantity_per_run: float, runs: float) -> float:
        base_quantity = quantity_per_run * runs
        if self.activity != MANUFACTURING_ACTIVITY or quantity_per_run <= 1.0:
            return base_quantity * self.blueprint.prints
        reduced_quantity = base_quantity * (1.0 - (self.blueprint.material_efficiency / 100.0))
        return reduced_quantity * self.blueprint.prints

    def total_time(self, runs: float) -> float:
        total_time_seconds = self.time_per_run * runs * self.blueprint.prints
        if self.activity != MANUFACTURING_ACTIVITY:
            return total_time_seconds
        return total_time_seconds * (1.0 - (self.blueprint.time_efficiency / 100.0))

    @property
    def usage_key(self) -> str:
        return self.blueprint.usage_key(self.blueprint_type_id)


# plan config
@dataclass
class PlanConfig:
    top_level_blueprints: List[Blueprint] = field(default_factory=list)
    blueprint_settings: Dict[str, Blueprint] = field(default_factory=dict)
    buy_components: Set[str] = field(default_factory=set)

    def blueprint_for(self, blueprint_name: str) -> Blueprint:
        return self.blueprint_settings.get(blueprint_name, Blueprint(blueprint_name))

    def set_blueprint(self, blueprint: Blueprint) -> None:
        self.blueprint_settings[blueprint.name] = blueprint

    def copy(self) -> "PlanConfig":
        return PlanConfig(
            top_level_blueprints=list(self.top_level_blueprints),
            blueprint_settings=dict(self.blueprint_settings),
            buy_components=set(self.buy_components),
        )


@dataclass
class BomNode:
    node_id: str
    type_id: int
    name: str
    depth: int
    required_quantity: float
    planned_output_quantity: float
    runs: Optional[float] = None
    total_time_seconds: float = 0.0
    base_material_quantity: Optional[float] = None
    recipe: Optional[BlueprintRecipe] = None
    children: List["BomNode"] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        node_id: str,
        depth: int,
        required_quantity: Optional[float],
        recipe: BlueprintRecipe,
    ) -> "BomNode":
        runs = recipe.resolve_runs(required_quantity)
        planned_output_quantity = recipe.planned_output(runs)
        node_required_quantity = planned_output_quantity if required_quantity is None else float(required_quantity)
        return cls(
            node_id=node_id,
            type_id=recipe.product_type_id,
            name=recipe.product_name,
            depth=depth,
            required_quantity=node_required_quantity,
            planned_output_quantity=planned_output_quantity,
            runs=runs,
            total_time_seconds=recipe.total_time(runs),
            recipe=recipe,
        )

    @classmethod
    def leaf(
        cls,
        node_id: str,
        type_id: int,
        name: str,
        depth: int,
        quantity: float,
        base_material_quantity: Optional[float],
    ) -> "BomNode":
        return cls(
            node_id=node_id,
            type_id=type_id,
            name=name,
            depth=depth,
            required_quantity=quantity,
            planned_output_quantity=quantity,
            base_material_quantity=base_material_quantity,
        )

    @property
    def blueprint(self) -> Optional[Blueprint]:
        return self.recipe.blueprint if self.recipe is not None else None

    @property
    def blueprint_name(self) -> Optional[str]:
        return self.recipe.blueprint_name if self.recipe is not None else None

    @property
    def blueprint_type_id(self) -> Optional[int]:
        return self.recipe.blueprint_type_id if self.recipe is not None else None

    @property
    def material_efficiency(self) -> int:
        return self.blueprint.material_efficiency if self.blueprint is not None else 0

    @property
    def time_efficiency(self) -> int:
        return self.blueprint.time_efficiency if self.blueprint is not None else 0

    @property
    def prints(self) -> int:
        return self.blueprint.prints if self.blueprint is not None else 1

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
    recipe: Optional[BlueprintRecipe] = None
    total_time_seconds: float = 0.0
    mixed_blueprint_config: bool = False

    @classmethod
    def from_node(cls, node: BomNode) -> "BomAggregate":
        return cls(
            type_id=node.type_id,
            name=node.name,
            quantity=node.required_quantity,
            min_depth=node.depth,
            max_depth=node.depth,
            recipe=node.recipe,
            total_time_seconds=node.total_time_seconds,
        )

    def absorb(self, node: BomNode) -> None:
        self.quantity += node.required_quantity
        self.total_time_seconds += node.total_time_seconds
        self.min_depth = min(self.min_depth, node.depth)
        self.max_depth = max(self.max_depth, node.depth)

        if self.recipe is None and node.recipe is not None:
            self.recipe = node.recipe
        elif self.recipe is not None and node.recipe is not None and self.recipe.blueprint != node.recipe.blueprint:
            self.mixed_blueprint_config = True

    @property
    def blueprint(self) -> Optional[Blueprint]:
        return self.recipe.blueprint if self.recipe is not None else None

    @property
    def blueprint_type_id(self) -> Optional[int]:
        return self.recipe.blueprint_type_id if self.recipe is not None else None


@dataclass
class BlueprintUsage:
    usage_key: str
    recipe: BlueprintRecipe
    occurrences: int = 0
    min_depth: int = 0
    max_depth: int = 0
    total_runs: float = 0.0
    total_planned_output_quantity: float = 0.0
    total_time_seconds: float = 0.0

    @classmethod
    def from_node(cls, node: BomNode) -> "BlueprintUsage":
        return cls(
            usage_key=node.recipe.usage_key,
            recipe=node.recipe,
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
    roots: List[BomNode]
    aggregates: Dict[int, BomAggregate]
    used_blueprints: Dict[str, BlueprintUsage]

    @property
    def root(self) -> Optional[BomNode]:
        return self.roots[0] if self.roots else None

    @property
    def depths(self) -> Dict[int, int]:
        return {type_id: aggregate.max_depth for type_id, aggregate in self.aggregates.items()}

    @property
    def total_time_seconds(self) -> float:
        return sum(usage.total_time_seconds for usage in self.used_blueprints.values())
