from __future__ import annotations

from typing import Dict, Iterator, Optional, Set

from industry_index import IndustryIndex
from model import (
    Blueprint,
    BlueprintRecipe,
    BlueprintUsage,
    BomAggregate,
    BomNode,
    PlanConfig,
    BomSnapshot,
)


class BomPlanner:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def build_snapshot(self, request: PlanConfig) -> BomSnapshot:
        snapshot_request = request.copy()
        roots = [
            self._build_root(blueprint, index, snapshot_request)
            for index, blueprint in enumerate(snapshot_request.top_level_blueprints)
        ]
        return BomSnapshot(
            request=snapshot_request,
            roots=roots,
            aggregates=self._collect_aggregates(roots),
            used_blueprints=self._collect_blueprint_usage(roots),
        )

    def _build_root(self, blueprint: Blueprint, root_index: int, request: PlanConfig) -> BomNode:
        recipe = self._recipe_for_blueprint_name(blueprint.name, blueprint)
        return self._build_node(recipe, required_quantity=None, depth=0, node_id=str(root_index), request=request, stack=set())

    def _build_node(
        self,
        recipe: BlueprintRecipe,
        required_quantity: Optional[float],
        depth: int,
        node_id: str,
        request: PlanConfig,
        stack: Set[int],
    ) -> BomNode:
        node = BomNode.build(
            node_id=node_id,
            depth=depth,
            required_quantity=required_quantity,
            recipe=recipe,
        )

        if recipe.blueprint_type_id in stack:
            return node

        stack.add(recipe.blueprint_type_id)
        node.children.extend(self._build_children(node, request, stack))
        stack.remove(recipe.blueprint_type_id)
        return node

    def _build_children(self, parent: BomNode, request: PlanConfig, stack: Set[int]) -> list[BomNode]:
        recipe = parent.recipe
        if recipe is None or parent.runs is None:
            return []

        children = []
        materials = self.idx.inputs(recipe.blueprint_type_id, recipe.activity)
        for child_index, material in enumerate(materials):
            child_name = self.idx.type_name(material.material_typeid)
            quantity = recipe.material_quantity(float(material.quantity), parent.runs)
            base_quantity = recipe.base_material_quantity(float(material.quantity), parent.runs)
            child_node_id = f"{parent.node_id}.{child_index}"

            if child_name in request.buy_components:
                children.append(self._leaf_node(child_node_id, material.material_typeid, child_name, parent.depth + 1, quantity, base_quantity))
                continue

            child_blueprint_row = self._blueprint_row_for_product(material.material_typeid)
            if child_blueprint_row is None:
                children.append(self._leaf_node(child_node_id, material.material_typeid, child_name, parent.depth + 1, quantity, base_quantity))
                continue

            child_blueprint_name = self.idx.type_name(child_blueprint_row.type_id)
            child_recipe = self._recipe_from_row(
                child_blueprint_row,
                request.blueprint_for(child_blueprint_name),
            )
            child_node = self._build_node(
                child_recipe,
                required_quantity=quantity,
                depth=parent.depth + 1,
                node_id=child_node_id,
                request=request,
                stack=stack,
            )
            child_node.base_material_quantity = base_quantity
            children.append(child_node)
        return children

    def _leaf_node(
        self,
        node_id: str,
        type_id: int,
        name: str,
        depth: int,
        quantity: float,
        base_material_quantity: float,
    ) -> BomNode:
        return BomNode.leaf(
            node_id=node_id,
            type_id=type_id,
            name=name,
            depth=depth,
            quantity=quantity,
            base_material_quantity=base_material_quantity,
        )

    def _collect_blueprint_usage(self, roots: list[BomNode]) -> Dict[str, BlueprintUsage]:
        used_blueprints: Dict[str, BlueprintUsage] = {}
        for root in roots:
            for node in self._iter_nodes(root):
                if node.recipe is None:
                    continue
                usage = used_blueprints.get(node.recipe.usage_key)
                if usage is None:
                    used_blueprints[node.recipe.usage_key] = BlueprintUsage.from_node(node)
                else:
                    usage.absorb(node)
        return used_blueprints

    def _collect_aggregates(self, roots: list[BomNode]) -> Dict[int, BomAggregate]:
        aggregates: Dict[int, BomAggregate] = {}
        for root in roots:
            for node in self._iter_nodes(root, include_root=False):
                aggregate = aggregates.get(node.type_id)
                if aggregate is None:
                    aggregates[node.type_id] = BomAggregate.from_node(node)
                else:
                    aggregate.absorb(node)
        return aggregates

    def _iter_nodes(self, node: BomNode, include_root: bool = True) -> Iterator[BomNode]:
        if include_root:
            yield node
        for child in node.children:
            yield from self._iter_nodes(child, include_root=True)

    def _recipe_for_blueprint_name(self, blueprint_name: str, blueprint: Blueprint) -> BlueprintRecipe:
        blueprint_typeid = self.idx.find_type_id_by_name(blueprint_name)
        if blueprint_typeid is None:
            raise ValueError(f"Blueprint not found: {blueprint_name}")

        activity = self.idx.activity_for(blueprint_typeid)
        outputs = self.idx.outputs(blueprint_typeid, activity)
        if not outputs:
            raise ValueError(f"Blueprint {blueprint_name} does not have a production activity.")
        return self._recipe_from_row(outputs[0], blueprint)

    def _blueprint_row_for_product(self, product_typeid: int):
        return self.idx.production_blueprint_for(product_typeid)

    def _recipe_from_row(self, blueprint_product, blueprint: Blueprint) -> BlueprintRecipe:
        effective_blueprint = blueprint.effective_for_activity(blueprint_product.activity)
        return BlueprintRecipe(
            blueprint_type_id=blueprint_product.type_id,
            blueprint_name=self.idx.type_name(blueprint_product.type_id),
            activity=blueprint_product.activity,
            product_type_id=blueprint_product.product_typeid,
            product_name=self.idx.type_name(blueprint_product.product_typeid),
            output_per_run=float(blueprint_product.quantity),
            time_per_run=self.idx.activity_time(blueprint_product.type_id, blueprint_product.activity) or 0.0,
            blueprint=effective_blueprint,
        )


class BomPlannerSession:
    def __init__(        self,        idx: IndustryIndex,        top_level_blueprints: list[Blueprint],        blueprint_updates: Optional[Dict[str, Blueprint]] = None,buy_components: Optional[set[str]] = None,
    ):
        self.planner = BomPlanner(idx)
        self.request = PlanConfig(
            top_level_blueprints=list(top_level_blueprints),
            buy_components=set(buy_components or set()),
        )
        # this should be part of the constructor
        if blueprint_updates:
            self.request.blueprint_settings.update(dict(blueprint_updates))

    def snapshot(self) -> BomSnapshot:
        return self.planner.build_snapshot(self.request)

    def set_blueprint(self, blueprint: Blueprint) -> None:
        self.request.set_blueprint(blueprint)

    def set_top_level_blueprints(self, top_level_blueprints: list[Blueprint]) -> None:
        self.request.top_level_blueprints = list(top_level_blueprints)

    def set_buy_components(self, buy_components: set[str]) -> None:
        self.request.buy_components = set(buy_components)

    def update_blueprint(self, blueprint: Blueprint) -> BomSnapshot:
        self.set_blueprint(blueprint)
        return self.snapshot()
