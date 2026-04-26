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
class ActivityRow:
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


@dataclass(frozen=True)
class Blueprint:
    name: str
    material_efficiency: int = 0

    def __post_init__(self):
        object.__setattr__(self, "material_efficiency", clamp_material_efficiency(self.material_efficiency))


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
    desired_output_units: float = 1.0
    blueprint_settings: Dict[str, Blueprint] = field(default_factory=dict)
    material_rounding_mode: str = "continuous"

    def blueprint_for(self, blueprint_name: str) -> Blueprint:
        return self.blueprint_settings.get(blueprint_name, Blueprint(blueprint_name, 0))

    def set_blueprint(self, blueprint: Blueprint) -> None:
        self.blueprint_settings[blueprint.name] = blueprint

    def copy(self) -> "BomRequest":
        return BomRequest(
            top_level_blueprints=list(self.top_level_blueprints),
            desired_output_units=self.desired_output_units,
            blueprint_settings=dict(self.blueprint_settings),
            material_rounding_mode=self.material_rounding_mode,
        )


@dataclass
class BomNode:
    node_id: str
    type_id: int
    name: str
    required_quantity: float
    depth: int
    base_material_quantity: Optional[float] = None
    selected_blueprint: Optional[BlueprintOption] = None
    configured_blueprint: Optional[Blueprint] = None
    available_blueprints: List[BlueprintOption] = field(default_factory=list)
    material_efficiency: int = 0
    output_per_run: Optional[float] = None
    runs_required: Optional[float] = None
    children: List["BomNode"] = field(default_factory=list)


@dataclass
class BomAggregate:
    type_id: int
    name: str
    quantity: float
    min_depth: int
    max_depth: int
    selected_blueprint: Optional[BlueprintOption] = None


@dataclass
class BlueprintUsage:
    usage_key: str
    blueprint_option: BlueprintOption
    configured_blueprint: Blueprint
    occurrences: int = 0


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
