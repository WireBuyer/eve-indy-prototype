from __future__ import annotations

import math
from typing import Dict, Iterable, Optional, Set

from industry_index import IndustryIndex
from model import Blueprint, BlueprintOption, BlueprintUsage, BomAggregate, BomNode, BomRequest, BomSnapshot


MANUFACTURING_ACTIVITY = 1


def select_blueprint_for_production(blueprints: Iterable) -> Optional:
    """Prefer manufacturing blueprints, otherwise use the first available option."""
    blueprints = list(blueprints)
    if not blueprints:
        return None
    for blueprint in blueprints:
        if blueprint.activity == MANUFACTURING_ACTIVITY:
            return blueprint
    return blueprints[0]


class BomPlanner:
    """Builds a stable BOM tree snapshot from top-level blueprint jobs and overrides."""

    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def build_snapshot(self, request: BomRequest) -> BomSnapshot:
        snapshot_request = request.copy()
        roots = []
        for root_index, configured_blueprint in enumerate(snapshot_request.top_level_blueprints):
            blueprint_typeid = self._resolve_blueprint_typeid(configured_blueprint.name)
            roots.append(
                self._build_node_from_blueprint(
                    blueprint_typeid=blueprint_typeid,
                    configured_blueprint=configured_blueprint,
                    required_quantity=None,
                    depth=0,
                    node_id=str(root_index),
                    request=snapshot_request,
                    stack=set(),
                )
            )

        depths: Dict[int, int] = {}
        aggregates: Dict[int, BomAggregate] = {}
        used_blueprints: Dict[str, BlueprintUsage] = {}

        for root in roots:
            self._collect_used_blueprints(root, used_blueprints)
            self._collect_aggregates(root, depths, aggregates, include_current_node=False)

        return BomSnapshot(
            request=snapshot_request,
            roots=roots,
            depths=depths,
            aggregates=aggregates,
            used_blueprints=used_blueprints,
        )

    def _build_node_from_blueprint(
        self,
        blueprint_typeid: int,
        configured_blueprint: Blueprint,
        required_quantity: Optional[float],
        depth: int,
        node_id: str,
        request: BomRequest,
        stack: Set[int],
    ) -> BomNode:
        activity = self.idx.activity_for(blueprint_typeid)
        outputs = self.idx.outputs(blueprint_typeid, activity)
        if not outputs:
            raise ValueError(f"Blueprint {blueprint_typeid} does not have a production activity.")

        primary_product = outputs[0]
        selected_blueprint = self._to_blueprint_option(primary_product)
        available_blueprints = self._blueprint_options_for_product(primary_product.product_typeid)
        effective_blueprint = self._effective_blueprint(configured_blueprint, activity)
        output_per_run = float(primary_product.quantity)
        fallback_runs = self._fallback_runs(required_quantity, output_per_run, effective_blueprint.prints)
        runs = effective_blueprint.resolved_runs(fallback_runs)
        planned_output_quantity = output_per_run * runs * effective_blueprint.prints
        node_required_quantity = planned_output_quantity if required_quantity is None else float(required_quantity)
        activity_time_per_run = self.idx.activity_time(blueprint_typeid, activity) or 0.0
        total_time_seconds = self._total_time_seconds(activity_time_per_run, runs, effective_blueprint, activity)

        node = BomNode(
            node_id=node_id,
            type_id=primary_product.product_typeid,
            name=self.idx.type_name(primary_product.product_typeid),
            required_quantity=node_required_quantity,
            planned_output_quantity=planned_output_quantity,
            depth=depth,
            selected_blueprint=selected_blueprint,
            configured_blueprint=effective_blueprint,
            available_blueprints=available_blueprints,
            material_efficiency=effective_blueprint.material_efficiency,
            time_efficiency=effective_blueprint.time_efficiency,
            output_per_run=output_per_run,
            runs=runs,
            prints=effective_blueprint.prints,
            activity_time_per_run=activity_time_per_run,
            total_time_seconds=total_time_seconds,
        )

        if blueprint_typeid in stack:
            return node

        stack.add(blueprint_typeid)
        for child_index, material in enumerate(self.idx.inputs(blueprint_typeid, activity)):
            base_quantity = float(material.quantity) * runs * effective_blueprint.prints
            adjusted_quantity = self._apply_material_efficiency(
                quantity_per_run=float(material.quantity),
                runs=runs,
                prints=effective_blueprint.prints,
                configured_blueprint=effective_blueprint,
                activity=activity,
                rounding_mode=request.material_rounding_mode,
            )

            child_blueprint_row = select_blueprint_for_production(self.idx.blueprints_for(material.material_typeid))
            if child_blueprint_row is None:
                child_node = BomNode(
                    node_id=f"{node_id}.{child_index}",
                    type_id=material.material_typeid,
                    name=self.idx.type_name(material.material_typeid),
                    required_quantity=adjusted_quantity,
                    planned_output_quantity=adjusted_quantity,
                    depth=depth + 1,
                    base_material_quantity=base_quantity,
                )
            else:
                child_blueprint_name = self.idx.type_name(child_blueprint_row.type_id)
                child_blueprint = request.blueprint_for(child_blueprint_name)
                child_node = self._build_node_from_blueprint(
                    blueprint_typeid=child_blueprint_row.type_id,
                    configured_blueprint=child_blueprint,
                    required_quantity=adjusted_quantity,
                    depth=depth + 1,
                    node_id=f"{node_id}.{child_index}",
                    request=request,
                    stack=stack,
                )
                child_node.base_material_quantity = base_quantity

            node.children.append(child_node)
        stack.remove(blueprint_typeid)

        return node

    def _collect_used_blueprints(self, node: BomNode, used_blueprints: Dict[str, BlueprintUsage]) -> None:
        if node.selected_blueprint is not None and node.configured_blueprint is not None and node.runs is not None:
            usage_key = self._blueprint_usage_key(node.selected_blueprint, node.configured_blueprint)
            entry = used_blueprints.get(usage_key)
            if entry is None:
                used_blueprints[usage_key] = BlueprintUsage(
                    usage_key=usage_key,
                    blueprint_option=node.selected_blueprint,
                    configured_blueprint=node.configured_blueprint,
                    occurrences=1,
                    total_runs=node.runs * node.prints,
                    total_planned_output_quantity=node.planned_output_quantity,
                    total_time_seconds=node.total_time_seconds,
                )
            else:
                entry.occurrences += 1
                entry.total_runs += node.runs * node.prints
                entry.total_planned_output_quantity += node.planned_output_quantity
                entry.total_time_seconds += node.total_time_seconds

        for child in node.children:
            self._collect_used_blueprints(child, used_blueprints)

    def _collect_aggregates(
        self,
        node: BomNode,
        depths: Dict[int, int],
        aggregates: Dict[int, BomAggregate],
        include_current_node: bool = True,
    ) -> None:
        if include_current_node:
            depths[node.type_id] = max(depths.get(node.type_id, 0), node.depth)
            existing = aggregates.get(node.type_id)
            if existing is None:
                aggregates[node.type_id] = BomAggregate(
                    type_id=node.type_id,
                    name=node.name,
                    quantity=node.required_quantity,
                    min_depth=node.depth,
                    max_depth=node.depth,
                    selected_blueprint=node.selected_blueprint,
                    configured_blueprint=node.configured_blueprint,
                    total_time_seconds=node.total_time_seconds,
                )
            else:
                existing.quantity += node.required_quantity
                existing.total_time_seconds += node.total_time_seconds
                existing.min_depth = min(existing.min_depth, node.depth)
                existing.max_depth = max(existing.max_depth, node.depth)
                if existing.selected_blueprint is None and node.selected_blueprint is not None:
                    existing.selected_blueprint = node.selected_blueprint
                if existing.configured_blueprint is None and node.configured_blueprint is not None:
                    existing.configured_blueprint = node.configured_blueprint
                elif (
                    existing.configured_blueprint is not None
                    and node.configured_blueprint is not None
                    and existing.configured_blueprint != node.configured_blueprint
                ):
                    existing.mixed_blueprint_config = True

        for child in node.children:
            self._collect_aggregates(child, depths, aggregates, include_current_node=True)

    def _blueprint_options_for_product(self, product_typeid: int) -> list[BlueprintOption]:
        return [self._to_blueprint_option(blueprint) for blueprint in self.idx.blueprints_for(product_typeid)]

    def _to_blueprint_option(self, blueprint_product) -> BlueprintOption:
        return BlueprintOption(
            type_id=blueprint_product.type_id,
            name=self.idx.type_name(blueprint_product.type_id),
            activity=blueprint_product.activity,
            product_typeid=blueprint_product.product_typeid,
            product_name=self.idx.type_name(blueprint_product.product_typeid),
            output_per_run=blueprint_product.quantity,
        )

    def _resolve_blueprint_typeid(self, blueprint_name: str) -> int:
        blueprint_typeid = self.idx.find_type_id_by_name(blueprint_name)
        if blueprint_typeid is None:
            raise ValueError(f"Blueprint not found: {blueprint_name}")
        return blueprint_typeid

    def _effective_blueprint(self, configured_blueprint: Blueprint, activity: Optional[int]) -> Blueprint:
        if activity != MANUFACTURING_ACTIVITY:
            return Blueprint(
                configured_blueprint.name,
                0,
                0,
                configured_blueprint.runs,
                configured_blueprint.prints,
            )
        return configured_blueprint

    def _blueprint_usage_key(self, blueprint_option: BlueprintOption, configured_blueprint: Blueprint) -> str:
        runs_key = "auto" if configured_blueprint.runs is None else configured_blueprint.runs
        return (
            f"{blueprint_option.type_id}:{configured_blueprint.material_efficiency}:"
            f"{configured_blueprint.time_efficiency}:{runs_key}:{configured_blueprint.prints}"
        )

    def _fallback_runs(self, required_quantity: Optional[float], output_per_run: float, prints: int) -> float:
        if required_quantity is None:
            return 1.0
        total_output_per_run_batch = output_per_run * prints
        if total_output_per_run_batch == 0:
            return float(required_quantity)
        return float(required_quantity) / total_output_per_run_batch

    def _apply_material_efficiency(
        self,
        quantity_per_run: float,
        runs: float,
        prints: int,
        configured_blueprint: Blueprint,
        activity: Optional[int],
        rounding_mode: str,
    ) -> float:
        base_quantity = quantity_per_run * runs
        if activity != MANUFACTURING_ACTIVITY:
            return base_quantity * prints
        if quantity_per_run <= 1.0:
            return base_quantity * prints

        reduced_quantity = base_quantity * (1.0 - (configured_blueprint.material_efficiency / 100.0))
        if rounding_mode == "job_ceiling":
            reduced_quantity = float(math.ceil(reduced_quantity))
        return reduced_quantity * prints

    def _total_time_seconds(
        self,
        activity_time_per_run: float,
        runs: float,
        configured_blueprint: Blueprint,
        activity: Optional[int],
    ) -> float:
        total_time_seconds = activity_time_per_run * runs * configured_blueprint.prints
        if activity != MANUFACTURING_ACTIVITY:
            return total_time_seconds
        return total_time_seconds * (1.0 - (configured_blueprint.time_efficiency / 100.0))


class BomPlannerSession:
    """Mutable planner state that mirrors small PATCH-style API updates."""

    def __init__(
        self,
        idx: IndustryIndex,
        top_level_blueprints: list[Blueprint],
        material_rounding_mode: str = "continuous",
        blueprint_updates: Optional[Dict[str, Blueprint]] = None,
    ):
        self.planner = BomPlanner(idx)
        self.request = BomRequest(
            top_level_blueprints=list(top_level_blueprints),
            material_rounding_mode=material_rounding_mode,
        )
        if blueprint_updates:
            self.request.blueprint_settings.update(dict(blueprint_updates))

    def snapshot(self) -> BomSnapshot:
        return self.planner.build_snapshot(self.request)

    def set_blueprint(self, blueprint: Blueprint) -> None:
        self.request.set_blueprint(blueprint)

    def set_top_level_blueprints(self, top_level_blueprints: list[Blueprint]) -> None:
        self.request.top_level_blueprints = list(top_level_blueprints)

    def update_blueprint(self, blueprint: Blueprint) -> BomSnapshot:
        self.set_blueprint(blueprint)
        return self.snapshot()
