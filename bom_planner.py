from __future__ import annotations

from collections.abc import Iterator

from industry_index import IndustryIndex
from model import (
    Blueprint,
    BlueprintProduct,
    BlueprintRecipe,
    BlueprintUsage,
    BomAggregate,
    BomNode,
    BomSnapshot,
    MaterialRow,
    PlanConfig,
)


class BomPlanner:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def build_snapshot(self, request: PlanConfig) -> BomSnapshot:
        plan = request.copy()
        roots = [
            self._build_root(blueprint, root_index, plan)
            for root_index, blueprint in enumerate(plan.top_level_blueprints)
        ]
        return BomSnapshot(
            request=plan,
            roots=roots,
            aggregates=self._collect_aggregates(roots),
            used_blueprints=self._collect_blueprint_usage(roots),
        )

    def _build_root(self, blueprint: Blueprint, root_index: int, plan: PlanConfig) -> BomNode:
        recipe = self._recipe_for_blueprint(blueprint)
        return self._build_recipe_node(
            recipe=recipe,
            required_quantity=None,
            depth=0,
            node_id=str(root_index),
            plan=plan,
            active_blueprints=set(),
        )

    def _build_recipe_node(
        self,
        recipe: BlueprintRecipe,
        required_quantity: float | None,
        depth: int,
        node_id: str,
        plan: PlanConfig,
        active_blueprints: set[int],
    ) -> BomNode:
        node = BomNode.from_recipe(
            node_id=node_id,
            depth=depth,
            required_quantity=required_quantity,
            recipe=recipe,
        )

        if recipe.blueprint_type_id in active_blueprints:
            return node

        active_blueprints.add(recipe.blueprint_type_id)
        try:
            node.children = [
                self._build_material_node(node, material, child_index, plan, active_blueprints)
                for child_index, material in enumerate(self.idx.inputs(recipe.blueprint_type_id, recipe.activity))
            ]
        finally:
            active_blueprints.remove(recipe.blueprint_type_id)
        return node

    def _build_material_node(
        self,
        parent: BomNode,
        material: MaterialRow,
        child_index: int,
        plan: PlanConfig,
        active_blueprints: set[int],
    ) -> BomNode:
        if parent.recipe is None or parent.runs is None:
            raise ValueError("Material nodes require a buildable parent")

        node_id = f"{parent.node_id}.{child_index}"
        depth = parent.depth + 1
        name = self.idx.type_name(material.material_typeid)
        quantity = parent.recipe.material_quantity(material.quantity, parent.runs)
        base_quantity = parent.recipe.base_material_quantity(material.quantity, parent.runs)

        if name in plan.buy_components:
            return self._leaf_node(node_id, material.material_typeid, name, depth, quantity, base_quantity)

        blueprint_product = self.idx.production_blueprint_for(material.material_typeid)
        if blueprint_product is None:
            return self._leaf_node(node_id, material.material_typeid, name, depth, quantity, base_quantity)

        child_recipe = self._recipe_from_product(
            blueprint_product,
            plan.blueprint_for(self.idx.type_name(blueprint_product.type_id)),
        )
        child = self._build_recipe_node(
            recipe=child_recipe,
            required_quantity=quantity,
            depth=depth,
            node_id=node_id,
            plan=plan,
            active_blueprints=active_blueprints,
        )
        child.base_material_quantity = base_quantity
        return child

    def _recipe_for_blueprint(self, blueprint: Blueprint) -> BlueprintRecipe:
        blueprint_type_id = self.idx.find_type_id_by_name(blueprint.name)
        if blueprint_type_id is None:
            raise ValueError(f"Blueprint not found: {blueprint.name}")

        activity = self.idx.activity_for(blueprint_type_id)
        outputs = self.idx.outputs(blueprint_type_id, activity)
        if not outputs:
            raise ValueError(f"Blueprint {blueprint.name} does not have a production activity.")
        return self._recipe_from_product(outputs[0], blueprint)

    def _recipe_from_product(self, product: BlueprintProduct, blueprint: Blueprint) -> BlueprintRecipe:
        effective_blueprint = blueprint.effective_for_activity(product.activity)
        return BlueprintRecipe(
            blueprint_type_id=product.type_id,
            blueprint_name=self.idx.type_name(product.type_id),
            activity=product.activity,
            product_type_id=product.product_typeid,
            product_name=self.idx.type_name(product.product_typeid),
            output_per_run=float(product.quantity),
            time_per_run=self.idx.activity_time(product.type_id, product.activity) or 0.0,
            blueprint=effective_blueprint,
        )

    @staticmethod
    def _leaf_node(
        node_id: str,
        type_id: int,
        name: str,
        depth: int,
        quantity: float,
        base_quantity: float,
    ) -> BomNode:
        return BomNode.leaf(
            node_id=node_id,
            type_id=type_id,
            name=name,
            depth=depth,
            quantity=quantity,
            base_material_quantity=base_quantity,
        )

    def _collect_aggregates(self, roots: list[BomNode]) -> dict[int, BomAggregate]:
        aggregates: dict[int, BomAggregate] = {}
        for node in self._walk_all(roots, include_roots=False):
            aggregate = aggregates.get(node.type_id)
            if aggregate is None:
                aggregates[node.type_id] = BomAggregate.from_node(node)
            else:
                aggregate.absorb(node)
        return aggregates

    def _collect_blueprint_usage(self, roots: list[BomNode]) -> dict[str, BlueprintUsage]:
        used_blueprints: dict[str, BlueprintUsage] = {}
        for node in self._walk_all(roots):
            if node.recipe is None:
                continue

            usage = used_blueprints.get(node.recipe.usage_key)
            if usage is None:
                used_blueprints[node.recipe.usage_key] = BlueprintUsage.from_node(node)
            else:
                usage.absorb(node)
        return used_blueprints

    def _walk_all(self, roots: list[BomNode], include_roots: bool = True) -> Iterator[BomNode]:
        for root in roots:
            yield from self._walk(root, include_root=include_roots)

    def _walk(self, node: BomNode, include_root: bool = True) -> Iterator[BomNode]:
        if include_root:
            yield node
        for child in node.children:
            yield from self._walk(child)
