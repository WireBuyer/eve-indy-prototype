from __future__ import annotations

from collections import defaultdict

from build_models import (
    BuildInfo,
    BuildPlan,
    BomItem,
    BomResult,
    PrintSettings,
    ProductionRecipe,
)
from industry_index import IndustryIndex
from industry_fees import IndustryFeeCalculator
from model import MANUFACTURING_ACTIVITY, REACTION_ACTIVITY
from production_math import ProductionMath
from structures import StructureBonusService, StructureConfig


class BomPlanner:

    def __init__(
        self,
        idx: IndustryIndex,
        structure_configs: dict[str, StructureConfig] | None = None,
        use_estimate_math: bool = False,
        fee_calculator: IndustryFeeCalculator | None = None,
    ):
        self.idx = idx
        self.math = ProductionMath(use_estimate_math)
        self.fees = fee_calculator or IndustryFeeCalculator()
        self.structure_bonus = StructureBonusService(idx)
        self.structure_configs = structure_configs or {}
        self.use_estimate_math = use_estimate_math

    def build_result(self, plan: BuildPlan) -> BomResult:
        depths = self._build_tree(plan)

        roots: list[BomItem] = []
        demand: defaultdict[int, float] = defaultdict(float)
        items_by_product_id: dict[int, BomItem] = {}

        # First get the root items built
        for settings in plan.root_prints.values():
            recipe = self.idx.recipe_for_blueprint(settings.blueprint_type_id)
            if recipe is None:
                raise ValueError(f"{settings.name} does not produce an item.")
            roots.append(self._record_build(plan, recipe, settings, None, 0, demand))

        # Depth order ensures child demand exists before deeper products are built.
        for type_id, depth in sorted(depths.items(), key=lambda item: (item[1], item[0])):
            quantity = demand[type_id]
            if quantity <= 0:
                continue

            recipe = None if type_id in plan.buy_product_type_ids else self.idx.build_recipe_for(type_id)
            if recipe is None:
                items_by_product_id[type_id] = BomItem(
                    type_id=type_id,
                    name=self.idx.type_name(type_id),
                    quantity=quantity,
                    depth=depth,
                    group_id=self.idx.group_id(type_id),
                )
                continue

            settings = plan.print_overrides.get(
                recipe.blueprint_type_id,
                PrintSettings(recipe.blueprint_name, blueprint_type_id=recipe.blueprint_type_id),
            )
            items_by_product_id[type_id] = self._record_build(
                plan,
                recipe,
                settings,
                quantity,
                depth,
                demand,
            )

        return BomResult(
            plan=plan,
            roots=roots,
            items_by_product_id=items_by_product_id,
            buy_product_type_ids=set(plan.buy_product_type_ids),
            use_estimate_math=self.use_estimate_math,
        )

    def _build_tree(self, plan: BuildPlan) -> dict[int, int]:
        selected_products: set[int] = set()
        used_children: set[int] = set()
        depths: dict[int, int] = {}

        # Buy choices do not hide descendants here; the complete tree is needed
        # to prevent a root print from duplicating any selected child product.
        for settings in plan.root_prints.values():
            recipe = self.idx.recipe_for_blueprint(settings.blueprint_type_id)
            if recipe is None:
                raise ValueError(f"{settings.name} does not produce an item.")

            children: set[int] = set()
            child_depths: dict[int, int] = {}
            self._walk_recipe_tree(recipe, plan, children, child_depths)

            if recipe.product_type_id in selected_products:
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"{recipe.product_name} is already selected."
                )
            if recipe.product_type_id in used_children:
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"{recipe.product_name} is already required by another selection."
                )

            conflicting_roots = selected_products.intersection(children)
            if conflicting_roots:
                conflict_name = self.idx.type_name(next(iter(conflicting_roots)))
                raise ValueError(
                    f"{recipe.blueprint_name} cannot be selected because "
                    f"it requires an existing top-level selection: {conflict_name}."
                )

            selected_products.add(recipe.product_type_id)
            used_children.update(children)
            for type_id, depth in child_depths.items():
                depths[type_id] = max(depth, depths.get(type_id, 0))

        return depths

    def _walk_recipe_tree(
        self,
        recipe: ProductionRecipe,
        plan: BuildPlan,
        descendants: set[int],
        depths: dict[int, int],
        depth: int = 0,
        active_blueprints: set[int] | None = None,
        include_in_bom: bool = True,
    ) -> None:
        active_blueprints = {recipe.blueprint_type_id} if active_blueprints is None else active_blueprints

        for material in self.idx.inputs(recipe.blueprint_type_id, recipe.activity):
            type_id = material.material_typeid
            material_depth = depth + 1

            descendants.add(type_id)
            if include_in_bom:
                depths[type_id] = max(material_depth, depths.get(type_id, 0))

            child_recipe = self.idx.build_recipe_for(type_id)
            if child_recipe is None or child_recipe.blueprint_type_id in active_blueprints:
                continue

            # Bought products still count as descendants for duplicate blocking,
            # but their child products are excluded from BOM output.
            self._walk_recipe_tree(
                recipe=child_recipe,
                plan=plan,
                descendants=descendants,
                depths=depths,
                depth=material_depth,
                active_blueprints=active_blueprints | {child_recipe.blueprint_type_id},
                include_in_bom=include_in_bom and type_id not in plan.buy_product_type_ids,
            )

    def _record_build(
        self,
        plan: BuildPlan,
        recipe: ProductionRecipe,
        settings: PrintSettings,
        required_quantity: float | None,
        depth: int,
        demand: defaultdict[int, float],
    ) -> BomItem:
        if recipe.activity != MANUFACTURING_ACTIVITY:
            settings = PrintSettings(
                settings.name,
                settings.blueprint_type_id,
                runs=settings.runs,
                prints=settings.prints,
            )

        runs = self.math.runs_for(recipe, settings, required_quantity)
        output_quantity = self.math.output_quantity(recipe, settings, runs)
        structure_config = self._structure_config_for(plan, recipe)
        structure_material_modifier = self.structure_bonus.material_modifier(structure_config, recipe)
        structure_time_modifier = self.structure_bonus.time_modifier(structure_config, recipe)
        materials = self.idx.inputs(recipe.blueprint_type_id, recipe.activity)
        fees = self.fees.job_fees(materials, runs, settings.prints)

        for material in materials:
            demand[material.material_typeid] += self.math.material_quantity(
                recipe,
                settings,
                material.quantity,
                runs,
                structure_material_modifier,
            )

        return BomItem(
            type_id=recipe.product_type_id,
            name=recipe.product_name,
            quantity=output_quantity if required_quantity is None else float(required_quantity),
            depth=depth,
            group_id=recipe.product_group_id,
            build=BuildInfo(
                activity=recipe.activity,
                blueprint_type_id=recipe.blueprint_type_id,
                blueprint_name=recipe.blueprint_name,
                material_efficiency=settings.material_efficiency,
                time_efficiency=settings.time_efficiency,
                runs=runs,
                prints=settings.prints,
                output_quantity=output_quantity,
                total_time_seconds=self.math.total_time(recipe, settings, runs, structure_time_modifier),
                structure_config_id=None if structure_config is None else structure_config.config_id,
                structure_name=None if structure_config is None else structure_config.name,
                fees=fees,
            ),
        )

    def _structure_config_for(self, plan: BuildPlan, recipe: ProductionRecipe) -> StructureConfig | None:
        config_id = plan.structure_overrides.get(recipe.blueprint_type_id)
        if config_id is None and recipe.activity == MANUFACTURING_ACTIVITY:
            config_id = plan.primary_manufacturing_structure_id
        if config_id is None and recipe.activity == REACTION_ACTIVITY:
            config_id = plan.primary_reaction_structure_id
        if config_id is None:
            return None
        if config_id not in self.structure_configs:
            raise ValueError(f"Structure config not found: {config_id}")
        return self.structure_configs[config_id]

    def add_root_print(self, plan: BuildPlan, settings: PrintSettings) -> None:
        if settings.blueprint_type_id in plan.root_prints:
            raise ValueError(f"{settings.name} is already selected.")

        # Validate a temporary selection first. If validation raises, the caller's
        # plan remains unchanged.
        self._build_tree(
            BuildPlan(
                plan_id=plan.plan_id,
                root_prints={**plan.root_prints, settings.blueprint_type_id: settings},
                print_overrides=plan.print_overrides,
                buy_product_type_ids=plan.buy_product_type_ids,
                primary_manufacturing_structure_id=plan.primary_manufacturing_structure_id,
                primary_reaction_structure_id=plan.primary_reaction_structure_id,
                structure_overrides=plan.structure_overrides,
            )
        )
        plan.root_prints[settings.blueprint_type_id] = settings
