from dataclasses import dataclass
from typing import Dict, Optional

from bom_planner import BomPlanner
from industry_index import IndustryIndex
from model import Blueprint, PlanConfig


@dataclass
class AggregateEntry:
    qty: float = 0.0
    min_depth: Optional[int] = None


@dataclass
class DepthInfo:
    root_product_typeid: Optional[int]
    depths: Dict[int, int]
    blueprint_for_material: Dict[int, int]


def aggregate_all(
    blueprint_typeid: int,
    idx: IndustryIndex,
    runs: float = 1.0,
    prints: int = 1,
    depth: int = 0,
    stack=None,
    aggregates=None,
):
    blueprint_name = idx.type_name(blueprint_typeid)
    planner = BomPlanner(idx)
    snapshot = planner.build_snapshot(
        PlanConfig(
            top_level_blueprints=[Blueprint(blueprint_name, 0, 0, runs, prints)],
        )
    )

    results: Dict[int, AggregateEntry] = {}
    for type_id, aggregate in snapshot.aggregates.items():
        results[type_id] = AggregateEntry(qty=aggregate.quantity, min_depth=aggregate.min_depth)
    return results


def compute_max_depths(root_bp_typeid: int, idx: IndustryIndex) -> DepthInfo:
    blueprint_name = idx.type_name(root_bp_typeid)
    planner = BomPlanner(idx)
    snapshot = planner.build_snapshot(PlanConfig(top_level_blueprints=[Blueprint(blueprint_name)]))

    blueprint_for_material = {}
    for aggregate in snapshot.aggregates.values():
        if aggregate.blueprint_type_id is not None:
            blueprint_for_material[aggregate.type_id] = aggregate.blueprint_type_id

    root = snapshot.root
    return DepthInfo(
        root_product_typeid=root.type_id if root is not None else None,
        depths=dict(snapshot.depths),
        blueprint_for_material=blueprint_for_material,
    )


def fmt(q):
    return str(int(q)) if float(q).is_integer() else f"{q:.6f}"
