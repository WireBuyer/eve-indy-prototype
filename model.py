from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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


@dataclass
class AggregateEntry:
    qty: float = 0.0
    min_depth: Optional[int] = None


@dataclass
class DepthInfo:
    root_product_typeid: Optional[int]
    depths: Dict[int, int]
    blueprint_for_material: Dict[int, int]


def clamp_material_efficiency(material_efficiency: int) -> int:
    return max(0, min(10, int(material_efficiency)))


def clamp_time_efficiency(time_efficiency: int) -> int:
    return max(0, min(20, int(time_efficiency)))


@dataclass(frozen=True)
class Blueprint:
    name: str
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: Optional[float] = None
    prints: int = 1

    def __post_init__(self):
        object.__setattr__(self, "material_efficiency", clamp_material_efficiency(self.material_efficiency))
        object.__setattr__(self, "time_efficiency", clamp_time_efficiency(self.time_efficiency))
        object.__setattr__(self, "prints", max(1, int(self.prints)))
        if self.runs is not None:
            runs = float(self.runs)
            if runs <= 0:
                raise ValueError("runs must be positive when provided")
            object.__setattr__(self, "runs", runs)

    def resolved_runs(self, fallback_runs: float) -> float:
        return float(self.runs) if self.runs is not None else float(fallback_runs)

    def total_runs(self, fallback_runs: float) -> float:
        return self.resolved_runs(fallback_runs) * self.prints


@dataclass(frozen=True)
class BlueprintOption:
    type_id: int
    name: str
    activity: int
    product_typeid: int
    product_name: str
    output_per_run: float


@dataclass
class BomRequest:
    top_level_blueprints: List[Blueprint] = field(default_factory=list)
    blueprint_settings: Dict[str, Blueprint] = field(default_factory=dict)
    material_rounding_mode: str = "continuous"

    def blueprint_for(self, blueprint_name: str) -> Blueprint:
        return self.blueprint_settings.get(blueprint_name, Blueprint(blueprint_name))

    def set_blueprint(self, blueprint: Blueprint) -> None:
        self.blueprint_settings[blueprint.name] = blueprint

    def copy(self) -> "BomRequest":
        return BomRequest(
            top_level_blueprints=list(self.top_level_blueprints),
            blueprint_settings=dict(self.blueprint_settings),
            material_rounding_mode=self.material_rounding_mode,
        )


@dataclass
class BomNode:
    node_id: str
    type_id: int
    name: str
    required_quantity: float
    planned_output_quantity: float
    depth: int
    base_material_quantity: Optional[float] = None
    selected_blueprint: Optional[BlueprintOption] = None
    configured_blueprint: Optional[Blueprint] = None
    available_blueprints: List[BlueprintOption] = field(default_factory=list)
    material_efficiency: int = 0
    time_efficiency: int = 0
    output_per_run: Optional[float] = None
    runs: Optional[float] = None
    prints: int = 1
    activity_time_per_run: float = 0.0
    total_time_seconds: float = 0.0
    children: List["BomNode"] = field(default_factory=list)


@dataclass
class BomAggregate:
    type_id: int
    name: str
    quantity: float
    min_depth: int
    max_depth: int
    selected_blueprint: Optional[BlueprintOption] = None
    configured_blueprint: Optional[Blueprint] = None
    total_time_seconds: float = 0.0
    mixed_blueprint_config: bool = False


@dataclass
class BlueprintUsage:
    usage_key: str
    blueprint_option: BlueprintOption
    configured_blueprint: Blueprint
    occurrences: int = 0
    total_runs: float = 0.0
    total_planned_output_quantity: float = 0.0
    total_time_seconds: float = 0.0


@dataclass
class BomSnapshot:
    request: BomRequest
    roots: List[BomNode]
    depths: Dict[int, int]
    aggregates: Dict[int, BomAggregate]
    used_blueprints: Dict[str, BlueprintUsage]

    @property
    def root(self) -> Optional[BomNode]:
        return self.roots[0] if self.roots else None

    @property
    def total_time_seconds(self) -> float:
        return sum(usage.total_time_seconds for usage in self.used_blueprints.values())
