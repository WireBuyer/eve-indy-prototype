from __future__ import annotations

from collections import defaultdict

from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    BomEntry,
    BomResult,
    BlueprintSettings,
    PlanConfig,
    ProductionMath,
    ProductionRecipe,
)


class BomPlanner:
    """Builds a BOM in two passes: discover the blueprint tree, then aggregate demand."""

    def __init__(self, idx: IndustryIndex, use_estimate_math: bool = False):
        self.idx = idx
        self.math = ProductionMath(use_estimate_math)
        self.use_estimate_math = use_estimate_math

    def build_result(self, plan: PlanConfig) -> BomResult:
        roots, max_depth_by_type_id = self._collect_top_level_blueprints(plan)
        demand_by_type_id: defaultdict[int, float] = defaultdict(float)
        root_entries: list[BomEntry] = []
        entries: dict[int, BomEntry] = {}

        # Roots seed material demand. Child blueprints are not expanded here because
        # the same child product may be required by multiple parents and must be
        # aggregated before its runs and child materials are calculated.
        for recipe, settings in roots:
            runs = self.math.runs_for(recipe, settings, None)
            output_quantity = self.math.output_quantity(recipe, settings, runs)
            root_entries.append(
                BomEntry(
                    type_id=recipe.product_type_id,
                    name=recipe.product_name,
                    quantity=output_quantity,
                    depth=0,
                    group_id=recipe.product_group_id,
                    recipe=recipe,
                    settings=settings,
                    runs=runs,
                    output_quantity=output_quantity,
                    total_time_seconds=self.math.total_time(recipe, settings, runs),
                )
            )

            for material in self.idx.inputs(recipe.blueprint_type_id, recipe.activity):
                demand_by_type_id[material.material_typeid] += self.math.material_quantity(
                    recipe,
                    settings,
                    material.quantity,
                    runs,
                )

        # Depth order turns parent demand into child demand before deeper products
        # are evaluated. A bought component stays terminal even if it has a recipe.
        for type_id, depth in sorted(max_depth_by_type_id.items(), key=lambda item: (item[1], item[0])):
            quantity = demand_by_type_id[type_id]
            if quantity <= 0:
                continue

            bought = type_id in plan.buy_component_type_ids
            recipe = None if bought else self.idx.build_recipe_for(type_id)
            if recipe is None:
                entries[type_id] = BomEntry(
                    type_id=type_id,
                    name=self.idx.type_name(type_id),
                    quantity=quantity,
                    depth=depth,
                    group_id=self.idx.group_id(type_id),
                    output_quantity=quantity,
                    bought=bought,
                )
                continue

            settings = plan.settings_for(recipe.blueprint_type_id, recipe.blueprint_name)
            if recipe.activity != MANUFACTURING_ACTIVITY:
                # Reaction formulas ignore ME/TE, but still respect runs and prints.
                settings = BlueprintSettings(
                    settings.name,
                    settings.blueprint_type_id,
                    runs=settings.runs,
                    prints=settings.prints,
                )

            runs = self.math.runs_for(recipe, settings, quantity)
            output_quantity = self.math.output_quantity(recipe, settings, runs)
            entries[type_id] = BomEntry(
                type_id=recipe.product_type_id,
                name=recipe.product_name,
                quantity=float(quantity),
                depth=depth,
                group_id=recipe.product_group_id,
                recipe=recipe,
                settings=settings,
                runs=runs,
                output_quantity=output_quantity,
                total_time_seconds=self.math.total_time(recipe, settings, runs),
            )

            for material in self.idx.inputs(recipe.blueprint_type_id, recipe.activity):
                demand_by_type_id[material.material_typeid] += self.math.material_quantity(
                    recipe,
                    settings,
                    material.quantity,
                    runs,
                )

        return BomResult(
            request=plan,
            roots=root_entries,
            entries=entries,
            use_estimate_math=self.use_estimate_math,
        )

    def _collect_top_level_blueprints(
        self,
        plan: PlanConfig,
    ) -> tuple[list[tuple[ProductionRecipe, BlueprintSettings]], dict[int, int]]:
        roots: list[tuple[ProductionRecipe, BlueprintSettings]] = []
        selected_product_type_ids: set[int] = set()
        used_child_type_ids: set[int] = set()
        max_depth_by_type_id: dict[int, int] = {}

        # This validates complete selected blueprint trees before quantity math.
        # Buy choices do not hide descendants from duplicate selection checks.
        for settings in plan.top_level_blueprints.values():
            recipe = self.idx.recipe_for_blueprint(settings.blueprint_type_id)
            if recipe is None:
                raise ValueError(f"{settings.name} does not produce an item.")

            child_type_ids: set[int] = set()
            child_depths: dict[int, int] = {}
            self._walk_blueprint_tree(recipe, plan, child_type_ids, child_depths)

            # Selected root products must be disjoint from other selected roots
            # and from every descendant of every selected root.
            if recipe.product_type_id in selected_product_type_ids:
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"{recipe.product_name} is already selected."
                )
            if recipe.product_type_id in used_child_type_ids:
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"{recipe.product_name} is already required by another selection."
                )

            conflicting_roots = selected_product_type_ids.intersection(child_type_ids)
            if conflicting_roots:
                conflict_name = self.idx.type_name(next(iter(conflicting_roots)))
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"it requires an existing top-level selection: {conflict_name}."
                )

            if recipe.activity != MANUFACTURING_ACTIVITY:
                # Reaction formulas ignore ME/TE, but still respect runs and prints.
                settings = BlueprintSettings(
                    settings.name,
                    settings.blueprint_type_id,
                    runs=settings.runs,
                    prints=settings.prints,
                )
            roots.append((recipe, settings))
            selected_product_type_ids.add(recipe.product_type_id)
            used_child_type_ids.update(child_type_ids)
            for type_id, depth in child_depths.items():
                max_depth_by_type_id[type_id] = max(depth, max_depth_by_type_id.get(type_id, 0))

        return roots, max_depth_by_type_id

    def _walk_blueprint_tree(
        self,
        recipe: ProductionRecipe,
        plan: PlanConfig,
        descendants: set[int],
        max_depth_by_type_id: dict[int, int],
        depth: int = 0,
        active_blueprints: set[int] | None = None,
        include_in_bom: bool = True,
    ) -> None:
        active_blueprints = {recipe.blueprint_type_id} if active_blueprints is None else active_blueprints

        for material in self.idx.inputs(recipe.blueprint_type_id, recipe.activity):
            type_id = material.material_typeid
            material_depth = depth + 1

            # Descendants are always recorded for duplicate blocking. Depth is
            # recorded only while the branch is still part of the build BOM.
            descendants.add(type_id)
            if include_in_bom:
                max_depth_by_type_id[type_id] = max(material_depth, max_depth_by_type_id.get(type_id, 0))

            child_recipe = self.idx.build_recipe_for(type_id)
            if child_recipe is None or child_recipe.blueprint_type_id in active_blueprints:
                continue

            # Bought components still get traversed for duplicate blocking, but
            # their children are excluded from BOM output and demand expansion.
            self._walk_blueprint_tree(
                recipe=child_recipe,
                plan=plan,
                descendants=descendants,
                max_depth_by_type_id=max_depth_by_type_id,
                depth=material_depth,
                active_blueprints=active_blueprints | {child_recipe.blueprint_type_id},
                include_in_bom=include_in_bom and type_id not in plan.buy_component_type_ids,
            )

    def add_top_level_blueprint(self, plan: PlanConfig, settings: BlueprintSettings) -> None:
        if settings.blueprint_type_id in plan.top_level_blueprints:
            raise ValueError(f"{settings.name} is already selected.")

        # Validate a temporary selection first. If validation raises, the caller's
        # plan remains unchanged.
        self._collect_top_level_blueprints(
            PlanConfig(
                plan_id=plan.plan_id,
                top_level_blueprints={**plan.top_level_blueprints, settings.blueprint_type_id: settings},
                blueprint_settings=plan.blueprint_settings,
                buy_component_type_ids=plan.buy_component_type_ids,
            )
        )
        plan.top_level_blueprints[settings.blueprint_type_id] = settings
