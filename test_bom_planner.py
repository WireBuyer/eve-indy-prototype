import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bom_planner import BomPlanner
from bom_view import is_bought, is_built, item_tag, rows, shopping_list_for
from build_models import BuildPlan, PrintSettings, ProductionRecipe
from db_io import load_tables
from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    REACTION_ACTIVITY,
    BlueprintActivityTime,
    BlueprintProduct,
    MaterialRow,
    TypeInfo,
)
from plan_service import update_prints, update_root_prints
from production_math import ProductionMath
from structures import RigMode, RigTier, StructureConfig, structure_catalog


class BomPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = load_tables("eve.db")
        cls.planner = BomPlanner(cls.idx)
        cls.rhea_blueprint_typeid = cls.to_type("Rhea Blueprint")
        cls.jump_drive_blueprint_name = "Capital Jump Drive Blueprint"
        cls.ferrogel_formula_name = "Ferrogel Reaction Formula"
        cls.auto_integrity_seal_blueprint_name = "Auto-Integrity Preservation Seal Blueprint"

        cls.capital_jump_drive = cls.to_type("Capital Jump Drive")
        cls.charon = cls.to_type("Charon")
        cls.reinforced_carbon_fiber = cls.to_type("Reinforced Carbon Fiber")
        cls.tritanium = cls.to_type("Tritanium")
        cls.fulleroferrocene = cls.to_type("Fulleroferrocene")
        cls.wetware_mainframe = cls.to_type("Wetware Mainframe")
        cls.tungsten_carbide = cls.to_type("Tungsten Carbide")
        cls.tungsten_carbide_formula = cls.to_type("Tungsten Carbide Reaction Formula")

    @classmethod
    def to_type(cls, name):
        type_id = cls.idx.find_type_id_by_name(name)
        if type_id is None:
            raise ValueError(f"Type not found: {name}")
        return type_id

    def build_result(self, blueprints, blueprint_settings=None, buy_components=None):
        return self.planner.build_result(
            BuildPlan(
                root_prints=self.settings_catalog(blueprints),
                print_overrides=self.settings_catalog(blueprint_settings),
                buy_product_type_ids=self.type_ids(buy_components),
            )
        )

    def bp(self, name, material_efficiency=0, time_efficiency=0, runs=None, prints=1):
        return PrintSettings(
            name=name,
            blueprint_type_id=self.to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            runs=runs,
            prints=prints,
        )

    def settings_catalog(self, settings):
        if settings is None:
            return None
        return {print_settings.blueprint_type_id: print_settings for print_settings in settings}

    def type_ids(self, names):
        if names is None:
            return None
        return {self.to_type(name) for name in names}

    def built_entries(self, result, blueprint_name):
        return [
            entry
            for entry in rows(result)
            if is_built(entry) and entry.build.blueprint_name == blueprint_name
        ]

    def test_build_plan_normalizes_optional_collections(self):
        plan = BuildPlan(root_prints=None, print_overrides=None, buy_product_type_ids=None)

        self.assertIsNone(plan.plan_id)
        self.assertEqual(plan.root_prints, {})
        self.assertEqual(plan.print_overrides, {})
        self.assertEqual(plan.buy_product_type_ids, set())
        self.assertEqual(plan.structure_overrides, {})

    def test_root_me_reduces_direct_manufacturing_inputs(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result([self.bp("Rhea Blueprint", 10, 0, 1, 1)])

        self.assertEqual(base_result.roots[0].build.material_efficiency, 0)
        self.assertEqual(updated_result.roots[0].build.material_efficiency, 10)
        self.assertEqual(base_result.items_by_product_id[self.capital_jump_drive].quantity, 30.0)
        self.assertEqual(updated_result.items_by_product_id[self.capital_jump_drive].quantity, 27.0)
        self.assertEqual(base_result.items_by_product_id[self.charon].quantity, 1.0)
        self.assertEqual(updated_result.items_by_product_id[self.charon].quantity, 1.0)

    def test_runs_for_auto_child_prints_rounds_up_to_whole_runs(self):
        recipe = ProductionRecipe(
            blueprint_type_id=1,
            blueprint_name="Example Blueprint",
            activity=MANUFACTURING_ACTIVITY,
            product_type_id=2,
            product_name="Example Product",
            output_per_run=1000,
            time_per_run=0,
        )
        settings = PrintSettings(name="Example Blueprint", blueprint_type_id=1, prints=2)
        math = ProductionMath()

        self.assertEqual(math.runs_for(recipe, settings, 9500), 5.0)
        self.assertEqual(math.output_quantity(recipe, settings, 5), 10000.0)

    def test_material_quantity_uses_eve_rounding_before_prints(self):
        recipe = ProductionRecipe(
            blueprint_type_id=1,
            blueprint_name="Example Blueprint",
            activity=MANUFACTURING_ACTIVITY,
            product_type_id=2,
            product_name="Example Product",
            output_per_run=1,
            time_per_run=0,
        )
        settings = PrintSettings(
            name="Example Blueprint",
            blueprint_type_id=1,
            material_efficiency=3,
            prints=2,
        )

        self.assertEqual(ProductionMath().material_quantity(recipe, settings, 975, 1), 1892.0)
        self.assertEqual(ProductionMath().material_quantity(recipe, settings, 975, 1, 0.99), 1874.0)

    def test_primary_manufacturing_structure_applies_hull_and_simple_matching_rig(self):
        idx = self.structure_fixture_index()
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="raitaru",
                        name="Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        me=RigTier.T1,
                        te=RigTier.T1,
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="raitaru",
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 98.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 971.0)
        self.assertEqual(result.roots[0].build.total_time_seconds, 68.0)
        self.assertEqual(result.roots[0].build.structure_config_id, "raitaru")

    def test_simple_rig_mode_uses_enum_tier_without_rig_lookup(self):
        idx = self.structure_fixture_index()
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="raitaru",
                        name="Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        me=RigTier.T1,
                        te=RigTier.T1,
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="raitaru",
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 98.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 971.0)

    def test_simple_thukker_uses_capital_material_reduction(self):
        idx = self.structure_fixture_index(component_group_id=873)
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="thukker",
                        name="Thukker Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        me=RigTier.THUKKER,
                        te=RigTier.THUKKER,
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="thukker",
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 99.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 987.0)
        self.assertAlmostEqual(result.roots[0].build.total_time_seconds, 83.3)

    def test_simple_thukker_uses_standard_material_reduction_for_noncapital(self):
        idx = self.structure_fixture_index()
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="thukker",
                        name="Thukker Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        me=RigTier.THUKKER,
                        te=RigTier.THUKKER,
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="thukker",
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 99.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 989.0)
        self.assertAlmostEqual(result.roots[0].build.total_time_seconds, 83.3)

    def test_structure_override_replaces_primary_for_print_node(self):
        idx = self.structure_fixture_index()
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="raitaru",
                        name="Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        me=RigTier.T1,
                        te=RigTier.T1,
                    ),
                    StructureConfig(
                        config_id="azbel",
                        name="Azbel",
                        structure="Azbel",
                        security="highsec",
                        me=RigTier.T2,
                        te=RigTier.T2,
                    ),
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="raitaru",
                structure_overrides={103: "azbel"},
            )
        )

        component = result.items_by_product_id[300]
        self.assertEqual(component.build.structure_config_id, "azbel")
        self.assertEqual(component.build.structure_name, "Azbel")
        self.assertEqual(result.items_by_product_id[400].quantity, 967.0)
        self.assertAlmostEqual(component.build.total_time_seconds, 608.0)

    def test_advanced_rig_mode_uses_exact_affected_groups(self):
        idx = self.structure_fixture_index(
            rig_affected_groups={
                (9001, "manufacturing", "material"): {20},
            },
        )
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="exact",
                        name="Exact Raitaru",
                        structure="Raitaru",
                        security="highsec",
                        rig_mode=RigMode.ADVANCED,
                        rigs=[("Exact Material Rig", 9001, RigTier.T1)],
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={101: PrintSettings("Root Blueprint", 101, runs=1)},
                primary_manufacturing_structure_id="exact",
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 99.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 971.0)
        self.assertEqual(result.items_by_product_id[300].build.total_time_seconds, 850.0)

    def test_primary_reaction_structure_applies_reaction_bonuses(self):
        idx = self.structure_fixture_index()
        planner = BomPlanner(
            idx,
            structure_configs=structure_catalog(
                [
                    StructureConfig(
                        config_id="tatara",
                        name="Tatara",
                        structure="Tatara",
                        security="lowsec",
                        me=RigTier.T1,
                        te=RigTier.T1,
                    )
                ]
            ),
        )

        result = planner.build_result(
            BuildPlan(
                root_prints={102: PrintSettings("Reaction Formula", 102, runs=1)},
                primary_reaction_structure_id="tatara",
            )
        )

        self.assertEqual(result.roots[0].build.material_efficiency, 0)
        self.assertEqual(result.items_by_product_id[600].quantity, 98.0)
        self.assertAlmostEqual(result.roots[0].build.total_time_seconds, 60.0)

    def test_planner_can_temporarily_use_estimate_math(self):
        estimate_planner = BomPlanner(self.idx, use_estimate_math=True)

        result = estimate_planner.build_result(
            BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        )

        self.assertTrue(result.use_estimate_math)
        self.assertEqual(result.items_by_product_id[self.reinforced_carbon_fiber].quantity, 29160.0)
        self.assertEqual(result.items_by_product_id[self.tritanium].quantity, 5078493.6)

    def test_duplicate_component_demand_is_aggregated_before_child_expansion(self):
        idx = self.aggregate_fixture_index()
        result = BomPlanner(idx).build_result(
            BuildPlan(
                root_prints={
                    101: PrintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
                    102: PrintSettings(name="Root B Blueprint", blueprint_type_id=102, runs=1),
                }
            )
        )

        self.assertEqual(result.items_by_product_id[300].quantity, 8.0)
        self.assertEqual(result.items_by_product_id[300].build.runs, 1.0)
        self.assertEqual(result.items_by_product_id[400].quantity, 100.0)

    def test_bought_buildable_component_does_not_expand_child_materials(self):
        idx = self.aggregate_fixture_index()
        result = BomPlanner(idx).build_result(
            BuildPlan(
                root_prints={
                    101: PrintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
                },
                buy_product_type_ids={300},
            )
        )

        self.assertTrue(is_bought(result, result.items_by_product_id[300]))
        self.assertEqual(item_tag(result, result.items_by_product_id[300]), "BUY")
        self.assertNotIn(400, result.items_by_product_id)
        self.assertNotIn(401, result.items_by_product_id)

    def test_children_under_bought_component_still_block_top_level_selection(self):
        idx = self.aggregate_fixture_index()
        planner = BomPlanner(idx)
        plan = BuildPlan(
            root_prints={
                101: PrintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
            },
            buy_product_type_ids={300},
        )

        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            planner.add_root_print(
                plan,
                PrintSettings(name="Child Y Blueprint", blueprint_type_id=104, runs=1),
            )

        self.assertNotIn(104, plan.root_prints)

    def test_fuel_block_buy_decisions_stop_fuel_block_inputs(self):
        fuel_blocks = {
            self.to_type("Nitrogen Fuel Block"),
            self.to_type("Hydrogen Fuel Block"),
            self.to_type("Helium Fuel Block"),
            self.to_type("Oxygen Fuel Block"),
        }
        result = self.build_result(
            [self.bp("Paladin Blueprint", 3, 14, 1, 1)],
            buy_components={
                "Nitrogen Fuel Block",
                "Hydrogen Fuel Block",
                "Helium Fuel Block",
                "Oxygen Fuel Block",
            },
        )

        fuel_block_inputs = set()
        for fuel_block_type_id in fuel_blocks:
            recipe = self.idx.build_recipe_for(fuel_block_type_id)
            fuel_block_inputs.update(row.material_typeid for row in self.idx.inputs(recipe.blueprint_type_id, recipe.activity))
            self.assertTrue(is_bought(result, result.items_by_product_id[fuel_block_type_id]))

        self.assertTrue(fuel_block_inputs)
        self.assertTrue(fuel_block_inputs.isdisjoint(result.items_by_product_id))

    def test_child_blueprint_override_rebuilds_descendants_inline(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings=[self.bp(self.jump_drive_blueprint_name, 10, 20)],
        )

        updated_entry = self.built_entries(updated_result, self.jump_drive_blueprint_name)[0]
        self.assertEqual(updated_entry.build.material_efficiency, 10)
        self.assertEqual(updated_entry.build.time_efficiency, 20)
        self.assertEqual(base_result.items_by_product_id[self.reinforced_carbon_fiber].quantity, 29170.0)
        self.assertEqual(updated_result.items_by_product_id[self.reinforced_carbon_fiber].quantity, 28870.0)
        self.assertEqual(base_result.items_by_product_id[self.tritanium].quantity, 5079056.0)
        self.assertEqual(updated_result.items_by_product_id[self.tritanium].quantity, 4899056.0)

    def test_reaction_formula_me_and_te_are_ignored(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings=[self.bp(self.ferrogel_formula_name, 10, 20)],
        )

        ferrogel_entry = self.built_entries(updated_result, self.ferrogel_formula_name)[0]
        self.assertEqual(ferrogel_entry.build.material_efficiency, 0)
        self.assertEqual(ferrogel_entry.build.time_efficiency, 0)
        self.assertEqual(base_result.items_by_product_id[self.fulleroferrocene].quantity, 660.0)
        self.assertEqual(updated_result.items_by_product_id[self.fulleroferrocene].quantity, 660.0)

    def test_runs_and_prints_drive_output_quantity(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 2, 3)],
        )

        self.assertEqual(result.roots[0].build.runs, 2.0)
        self.assertEqual(result.roots[0].build.prints, 3)
        self.assertEqual(result.roots[0].build.output_quantity, 6.0)
        self.assertEqual(result.items_by_product_id[self.capital_jump_drive].quantity, 180.0)

    def test_top_level_selection_cannot_duplicate_a_child_requirement(self):
        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            self.build_result(
                [
                    self.bp("Raven Blueprint", 0, 0, 1, 1),
                    self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
                ],
            )

    def test_top_level_selection_cannot_absorb_existing_selection_as_child(self):
        with self.assertRaisesRegex(ValueError, "requires an existing top-level selection"):
            self.build_result(
                [
                    self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
                    self.bp("Raven Blueprint", 0, 0, 1, 1),
                ],
            )

    def test_top_level_selection_allows_unrelated_component_blueprint(self):
        result = self.build_result(
            [
                self.bp("Heron Blueprint", 0, 0, 1, 1),
                self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
            ],
        )

        self.assertEqual(len(result.roots), 2)
        self.assertEqual(result.roots[0].build.blueprint_name, "Heron Blueprint")
        self.assertEqual(result.roots[1].build.blueprint_name, self.auto_integrity_seal_blueprint_name)

    def test_top_level_selection_cannot_duplicate_existing_selection(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))

        with self.assertRaisesRegex(ValueError, "already selected"):
            self.planner.add_root_print(plan, self.bp("Rhea Blueprint", 10, 0, 2, 2))

    def test_time_efficiency_reduces_total_time(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result([self.bp("Rhea Blueprint", 0, 20, 1, 1)])
        base_time = self.idx.activity_time(self.rhea_blueprint_typeid, 1)

        self.assertEqual(base_result.roots[0].build.total_time_seconds, base_time)
        self.assertEqual(updated_result.roots[0].build.total_time_seconds, base_time * 0.8)

    def test_buy_decision_stops_recursion_for_that_component(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            buy_components={"Capital Jump Drive"},
        )

        self.assertIn(self.capital_jump_drive, result.plan.buy_product_type_ids)
        self.assertTrue(is_bought(result, result.items_by_product_id[self.capital_jump_drive]))
        self.assertEqual(item_tag(result, result.items_by_product_id[self.capital_jump_drive]), "BUY")
        self.assertIsNone(result.items_by_product_id[self.capital_jump_drive].build)
        self.assertEqual(result.items_by_product_id[self.capital_jump_drive].quantity, 30.0)
        self.assertNotIn(
            self.jump_drive_blueprint_name,
            {entry.build.blueprint_name for entry in rows(result) if is_built(entry)},
        )
        self.assertEqual(result.items_by_product_id[self.wetware_mainframe].quantity, 1.0)

    def test_child_expansion_uses_published_blueprint_mapping(self):
        recipe = self.idx.build_recipe_for(self.tungsten_carbide)

        self.assertTrue(self.idx.is_published_type(recipe.blueprint_type_id))
        self.assertEqual(recipe.blueprint_type_id, self.tungsten_carbide_formula)

    def test_shopping_list_includes_base_materials_and_bought_components(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            buy_components={"Capital Jump Drive"},
        )

        shopping_list = shopping_list_for(result)
        names = {material["name"] for material in shopping_list}
        type_ids = [material["type_id"] for material in shopping_list]

        self.assertIn("Tritanium", names)
        self.assertIn("Capital Jump Drive", names)
        self.assertNotIn("Charon", names)
        self.assertEqual(item_tag(result, result.items_by_product_id[self.capital_jump_drive]), "BUY")
        self.assertEqual(type_ids, sorted(type_ids))

    def test_shopping_list_can_filter_minerals_and_gas(self):
        result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])

        minerals = {material["name"] for material in shopping_list_for(result, "minerals")}
        gas = {material["name"] for material in shopping_list_for(result, "gas")}

        self.assertIn("Tritanium", minerals)
        self.assertIn("Morphite", minerals)
        self.assertNotIn("Fullerite-C28", minerals)
        self.assertIn("Fullerite-C28", gas)
        self.assertIn("Amber Cytoserocin", gas)
        self.assertNotIn("Tritanium", gas)

    def test_shopping_list_rejects_unknown_filter(self):
        result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])

        with self.assertRaisesRegex(ValueError, "Unknown shopping list group"):
            shopping_list_for(result, "moon")

    def test_print_shopping_list_uses_plain_rows(self):
        from prints import print_shopping_list

        shopping_list = [{"type_id": 34, "name": "Tritanium", "quantity": 12}]

        output = io.StringIO()
        with redirect_stdout(output):
            result = print_shopping_list(shopping_list)

        self.assertIs(result, shopping_list)
        self.assertEqual(output.getvalue(), "\nShopping list:\n  Tritanium 12\n")

    def test_plan_service_applies_root_print_update(self):
        plan = BuildPlan(
            plan_id="test-plan",
            root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )

        update_root_prints(
            plan,
            {
                self.rhea_blueprint_typeid: {
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                    "runs": 2,
                    "prints": 3,
                }
            },
        )
        result = self.planner.build_result(plan)

        settings = plan.root_prints[self.rhea_blueprint_typeid]
        self.assertEqual(plan.plan_id, "test-plan")
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertEqual(settings.runs, 2.0)
        self.assertEqual(settings.prints, 3)
        self.assertEqual(result.roots[0].build.output_quantity, 6.0)

    def test_plan_service_updates_only_the_selected_plan_object(self):
        first_plan = BuildPlan(
            plan_id="first-plan",
            root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )
        second_plan = BuildPlan(
            plan_id="second-plan",
            root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )

        update_root_prints(first_plan, {self.rhea_blueprint_typeid: {"material_efficiency": 10}})

        self.assertEqual(first_plan.root_prints[self.rhea_blueprint_typeid].material_efficiency, 10)
        self.assertEqual(second_plan.root_prints[self.rhea_blueprint_typeid].material_efficiency, 0)

    def test_plan_service_updates_selected_prints_without_depth(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type("Capital Jump Drive Blueprint")
        propulsion_id = self.to_type("Capital Propulsion Engine Blueprint")

        update_prints(
            plan,
            {
                jump_drive_id: {"material_efficiency": 10},
                propulsion_id: {"material_efficiency": 10},
            },
        )

        self.assertEqual(plan.print_overrides[jump_drive_id].material_efficiency, 10)
        self.assertEqual(plan.print_overrides[propulsion_id].material_efficiency, 10)

    def test_plan_service_applies_different_updates_in_one_request(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type("Capital Jump Drive Blueprint")
        propulsion_id = self.to_type("Capital Propulsion Engine Blueprint")
        armor_plates_id = self.to_type("Capital Armor Plates Blueprint")

        update_prints(
            plan,
            {
                jump_drive_id: {"material_efficiency": 10},
                propulsion_id: {"material_efficiency": 10},
                armor_plates_id: {"material_efficiency": 8},
            },
        )

        self.assertEqual(plan.print_overrides[jump_drive_id].material_efficiency, 10)
        self.assertEqual(plan.print_overrides[propulsion_id].material_efficiency, 10)
        self.assertEqual(plan.print_overrides[armor_plates_id].material_efficiency, 8)

    def test_plan_service_rebuilds_after_child_update(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type(self.jump_drive_blueprint_name)

        update_prints(
            plan,
            {
                jump_drive_id: {
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            }
        )
        result = self.planner.build_result(plan)

        settings = plan.print_overrides[jump_drive_id]
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertIsNone(settings.runs)
        self.assertEqual(result.items_by_product_id[self.reinforced_carbon_fiber].quantity, 28870.0)

    def test_plan_service_rejects_runs_update_below_root(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))

        with self.assertRaisesRegex(ValueError, "runs can only be updated"):
            update_prints(plan, {self.to_type(self.jump_drive_blueprint_name): {"runs": 2}})

    def test_build_plan_rejects_child_settings_with_manual_runs(self):
        with self.assertRaisesRegex(ValueError, "runs can only be set"):
            BuildPlan(
                root_prints=self.settings_catalog([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
                print_overrides=self.settings_catalog([self.bp(self.jump_drive_blueprint_name, runs=2)]),
            )

    def test_planner_add_top_level_blueprint_does_not_mutate_on_validation_failure(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Raven Blueprint", 0, 0, 1, 1)]))
        auto_integrity_seal = self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1)

        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            self.planner.add_root_print(plan, auto_integrity_seal)

        self.assertNotIn(auto_integrity_seal.blueprint_type_id, plan.root_prints)

    def test_planner_add_top_level_blueprint_mutates_after_validation_success(self):
        plan = BuildPlan(root_prints=self.settings_catalog([self.bp("Heron Blueprint", 0, 0, 1, 1)]))
        auto_integrity_seal = self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1)

        self.planner.add_root_print(plan, auto_integrity_seal)

        self.assertIn(auto_integrity_seal.blueprint_type_id, plan.root_prints)
        self.assertEqual(len(self.planner.build_result(plan).roots), 2)

    def test_build_plan_does_not_expose_unsafe_add_root_print(self):
        self.assertFalse(hasattr(BuildPlan, "add_root_print"))

    def test_main_output_matches_example_fixture(self):
        from main import main

        output = io.StringIO()
        with redirect_stdout(output):
            main()

        self.assertEqual(output.getvalue(), Path("Example 2.txt").read_text())

    def aggregate_fixture_index(self):
        names = {
            101: "Root A Blueprint",
            102: "Root B Blueprint",
            103: "Component X Blueprint",
            104: "Child Y Blueprint",
            201: "Root A",
            202: "Root B",
            300: "Component X",
            400: "Base Material",
            401: "Child Y",
        }
        inv_types = {
            type_id: TypeInfo(type_id, name, 0, None, None, None)
            for type_id, name in names.items()
        }
        bp_products = {
            (101, MANUFACTURING_ACTIVITY): BlueprintProduct(101, MANUFACTURING_ACTIVITY, 201, 1),
            (102, MANUFACTURING_ACTIVITY): BlueprintProduct(102, MANUFACTURING_ACTIVITY, 202, 1),
            (103, MANUFACTURING_ACTIVITY): BlueprintProduct(103, MANUFACTURING_ACTIVITY, 300, 10),
            (104, MANUFACTURING_ACTIVITY): BlueprintProduct(104, MANUFACTURING_ACTIVITY, 401, 1),
        }
        bp_by_product = {
            201: bp_products[(101, MANUFACTURING_ACTIVITY)],
            202: bp_products[(102, MANUFACTURING_ACTIVITY)],
            300: bp_products[(103, MANUFACTURING_ACTIVITY)],
            401: bp_products[(104, MANUFACTURING_ACTIVITY)],
        }
        materials = {
            (101, MANUFACTURING_ACTIVITY): [MaterialRow(101, MANUFACTURING_ACTIVITY, 300, 4)],
            (102, MANUFACTURING_ACTIVITY): [MaterialRow(102, MANUFACTURING_ACTIVITY, 300, 4)],
            (103, MANUFACTURING_ACTIVITY): [
                MaterialRow(103, MANUFACTURING_ACTIVITY, 400, 100),
                MaterialRow(103, MANUFACTURING_ACTIVITY, 401, 1),
            ],
        }
        activity_times = {
            (101, MANUFACTURING_ACTIVITY): BlueprintActivityTime(101, MANUFACTURING_ACTIVITY, 0),
            (102, MANUFACTURING_ACTIVITY): BlueprintActivityTime(102, MANUFACTURING_ACTIVITY, 0),
            (103, MANUFACTURING_ACTIVITY): BlueprintActivityTime(103, MANUFACTURING_ACTIVITY, 0),
            (104, MANUFACTURING_ACTIVITY): BlueprintActivityTime(104, MANUFACTURING_ACTIVITY, 0),
        }
        return IndustryIndex(inv_types, bp_products, bp_by_product, materials, activity_times)

    def structure_fixture_index(
        self,
        rig_affected_groups=None,
        component_group_id=20,
    ):
        names = {
            101: "Root Blueprint",
            102: "Reaction Formula",
            103: "Component Blueprint",
            201: "Root Product",
            300: "Component",
            400: "Base Material",
            500: "Reaction Product",
            600: "Reaction Material",
            9001: "Exact Material Rig",
        }
        groups = {
            201: 10,
            300: component_group_id,
            400: 30,
            500: 40,
            600: 50,
        }
        inv_types = {
            type_id: TypeInfo(type_id, name, 0, None, groups.get(type_id), None)
            for type_id, name in names.items()
        }
        bp_products = {
            (101, MANUFACTURING_ACTIVITY): BlueprintProduct(101, MANUFACTURING_ACTIVITY, 201, 1),
            (102, REACTION_ACTIVITY): BlueprintProduct(102, REACTION_ACTIVITY, 500, 10),
            (103, MANUFACTURING_ACTIVITY): BlueprintProduct(103, MANUFACTURING_ACTIVITY, 300, 10),
        }
        bp_by_product = {
            201: bp_products[(101, MANUFACTURING_ACTIVITY)],
            300: bp_products[(103, MANUFACTURING_ACTIVITY)],
            500: bp_products[(102, REACTION_ACTIVITY)],
        }
        materials = {
            (101, MANUFACTURING_ACTIVITY): [MaterialRow(101, MANUFACTURING_ACTIVITY, 300, 100)],
            (102, REACTION_ACTIVITY): [MaterialRow(102, REACTION_ACTIVITY, 600, 100)],
            (103, MANUFACTURING_ACTIVITY): [MaterialRow(103, MANUFACTURING_ACTIVITY, 400, 100)],
        }
        activity_times = {
            (101, MANUFACTURING_ACTIVITY): BlueprintActivityTime(101, MANUFACTURING_ACTIVITY, 100),
            (102, REACTION_ACTIVITY): BlueprintActivityTime(102, REACTION_ACTIVITY, 100),
            (103, MANUFACTURING_ACTIVITY): BlueprintActivityTime(103, MANUFACTURING_ACTIVITY, 100),
        }
        rig_affected_groups = dict(rig_affected_groups or {})

        return IndustryIndex(
            inv_types,
            bp_products,
            bp_by_product,
            materials,
            activity_times,
            rig_affected_groups,
        )


if __name__ == "__main__":
    unittest.main()
