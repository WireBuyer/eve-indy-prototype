from __future__ import annotations

from collections.abc import Iterator

from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    BlueprintProduct,
    BlueprintSettings,
    BlueprintUsage,
    BomAggregate,
    BomNode,
    BomSnapshot,
    MaterialRow,
    PlanConfig,
    ProductionPlan,
)


class BomPlanner:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def build_snapshot(self, request: PlanConfig) -> BomSnapshot:
        plan = request.copy()
        roots = [
            self._build_node(
                production=self._production_for_settings(settings),
                required_quantity=None,
                depth=0,
                node_id=str(root_index),
                plan=plan,
                active_blueprints=set(),
            )
            for root_index, settings in enumerate(plan.top_level_blueprints)
        ]
        aggregates, used_blueprints = self._summarize(roots)
        return BomSnapshot(
            request=plan,
            roots=roots,
            aggregates=aggregates,
            used_blueprints=used_blueprints,
        )

    def _build_node(
        self,
        production: ProductionPlan,
        required_quantity: float | None,
        depth: int,
        node_id: str,
        plan: PlanConfig,
        active_blueprints: set[int],
    ) -> BomNode:
        runs = production.runs_for(required_quantity)
        quantity = production.planned_output(runs) if required_quantity is None else float(required_quantity)
        node = BomNode(
            node_id=node_id,
            type_id=production.product_type_id,
            name=production.product_name,
            depth=depth,
            quantity=quantity,
            production=production,
            runs=runs,
        )

        if production.blueprint_type_id in active_blueprints:
            return node

        active_blueprints.add(production.blueprint_type_id)
        try:
            node.children = [
                self._build_child(node, material, child_index, plan, active_blueprints)
                for child_index, material in enumerate(self.idx.inputs(production.blueprint_type_id, production.activity))
            ]
        finally:
            active_blueprints.remove(production.blueprint_type_id)
        return node

    def _build_child(
        self,
        parent: BomNode,
        material: MaterialRow,
        child_index: int,
        plan: PlanConfig,
        active_blueprints: set[int],
    ) -> BomNode:
        if parent.production is None or parent.runs is None:
            raise ValueError("Material nodes require a buildable parent")

        node_id = f"{parent.node_id}.{child_index}"
        depth = parent.depth + 1
        type_id = material.material_typeid
        name = self.idx.type_name(type_id)
        quantity = parent.production.material_quantity(material.quantity, parent.runs)

        blueprint_product = None if name in plan.buy_components else self.idx.production_blueprint_for(type_id)
        if blueprint_product is None:
            return BomNode(node_id=node_id, type_id=type_id, name=name, depth=depth, quantity=quantity)

        return self._build_node(
            production=self._production_from_product(
                blueprint_product,
                plan.settings_for(self.idx.type_name(blueprint_product.type_id)),
            ),
            required_quantity=quantity,
            depth=depth,
            node_id=node_id,
            plan=plan,
            active_blueprints=active_blueprints,
        )

    def _production_for_settings(self, settings: BlueprintSettings) -> ProductionPlan:
        blueprint_type_id = self.idx.find_type_id_by_name(settings.name)
        if blueprint_type_id is None:
            raise ValueError(f"Blueprint not found: {settings.name}")

        activity = self.idx.activity_for(blueprint_type_id)
        outputs = self.idx.outputs(blueprint_type_id, activity)
        if not outputs:
            raise ValueError(f"Blueprint {settings.name} does not have a production activity.")
        return self._production_from_product(outputs[0], settings)

    def _production_from_product(self, product: BlueprintProduct, settings: BlueprintSettings) -> ProductionPlan:
        if product.activity != MANUFACTURING_ACTIVITY:
            settings = BlueprintSettings(name=settings.name, runs=settings.runs, prints=settings.prints)

        return ProductionPlan(
            blueprint_type_id=product.type_id,
            blueprint_name=self.idx.type_name(product.type_id),
            activity=product.activity,
            product_type_id=product.product_typeid,
            product_name=self.idx.type_name(product.product_typeid),
            output_per_run=float(product.quantity),
            time_per_run=self.idx.activity_time(product.type_id, product.activity) or 0.0,
            settings=settings,
        )

    def _summarize(self, roots: list[BomNode]) -> tuple[dict[int, BomAggregate], list[BlueprintUsage]]:
        aggregates: dict[int, BomAggregate] = {}
        usage_by_production: dict[ProductionPlan, BlueprintUsage] = {}

        for node in _iter_nodes(roots):
            if node.depth > 0:
                aggregate = aggregates.get(node.type_id)
                if aggregate is None:
                    aggregates[node.type_id] = BomAggregate.from_node(node)
                else:
                    aggregate.absorb(node)

            if node.production is None:
                continue

            usage = usage_by_production.get(node.production)
            if usage is None:
                usage_by_production[node.production] = BlueprintUsage.from_node(node)
            else:
                usage.absorb(node)

        return aggregates, list(usage_by_production.values())


def _iter_nodes(nodes: list[BomNode]) -> Iterator[BomNode]:
    for node in nodes:
        yield node
        yield from _iter_nodes(node.children)
