from __future__ import annotations

from dataclasses import dataclass

from bom_planner import BomPlanner
from industry_index import IndustryIndex
from model import Blueprint, PlanConfig


@dataclass(frozen=True)
class AggregateEntry:
    quantity: float
    min_depth: int
    max_depth: int

    @property
    def qty(self) -> float:
        return self.quantity


@dataclass(frozen=True)
class DepthInfo:
    root_product_type_id: int | None
    depths: dict[int, int]
    blueprint_for_material: dict[int, int]

    @property
    def root_product_typeid(self) -> int | None:
        return self.root_product_type_id


def aggregate_all(
    blueprint_type_id: int,
    idx: IndustryIndex,
    runs: float = 1.0,
    prints: int = 1,
) -> dict[int, AggregateEntry]:
    snapshot = _snapshot_for_blueprint(blueprint_type_id, idx, runs=runs, prints=prints)
    return {
        type_id: AggregateEntry(
            quantity=aggregate.quantity,
            min_depth=aggregate.min_depth,
            max_depth=aggregate.max_depth,
        )
        for type_id, aggregate in snapshot.aggregates.items()
    }


def compute_max_depths(root_blueprint_type_id: int, idx: IndustryIndex) -> DepthInfo:
    snapshot = _snapshot_for_blueprint(root_blueprint_type_id, idx)
    return DepthInfo(
        root_product_type_id=snapshot.root.type_id if snapshot.root is not None else None,
        depths=dict(snapshot.depths),
        blueprint_for_material={
            aggregate.type_id: aggregate.blueprint_type_id
            for aggregate in snapshot.aggregates.values()
            if aggregate.blueprint_type_id is not None
        },
    )


def _snapshot_for_blueprint(
    blueprint_type_id: int,
    idx: IndustryIndex,
    runs: float | None = None,
    prints: int = 1,
):
    planner = BomPlanner(idx)
    return planner.build_snapshot(
        PlanConfig(
            top_level_blueprints=[
                Blueprint(
                    name=idx.type_name(blueprint_type_id),
                    runs=runs,
                    prints=prints,
                )
            ],
        )
    )
