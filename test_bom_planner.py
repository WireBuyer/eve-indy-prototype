import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bom_planner import BomPlanner
from db_io import load_tables
from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    BlueprintActivityTime,
    BlueprintProduct,
    BlueprintSettings,
    MaterialRow,
    PlanConfig,
    ProductionMath,
    ProductionRecipe,
    TypeInfo,
)


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
            PlanConfig(
                top_level_blueprints=self.settings_by_id(blueprints),
                blueprint_settings=self.settings_by_id(blueprint_settings),
                buy_component_type_ids=self.type_ids(buy_components),
            )
        )

    def bp(self, name, material_efficiency=0, time_efficiency=0, runs=None, prints=1):
        return BlueprintSettings(
            name=name,
            blueprint_type_id=self.to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            runs=runs,
            prints=prints,
        )

    def settings_by_id(self, settings):
        if settings is None:
            return None
        return {blueprint_settings.blueprint_type_id: blueprint_settings for blueprint_settings in settings}

    def type_ids(self, names):
        if names is None:
            return None
        return {self.to_type(name) for name in names}

    def built_entries(self, result, blueprint_name):
        return [
            entry
            for entry in result.rows
            if entry.is_built and entry.blueprint_name == blueprint_name
        ]

    def test_plan_config_normalizes_optional_collections(self):
        plan = PlanConfig(top_level_blueprints=None, blueprint_settings=None, buy_component_type_ids=None)

        self.assertIsNone(plan.plan_id)
        self.assertEqual(plan.top_level_blueprints, {})
        self.assertEqual(plan.blueprint_settings, {})
        self.assertEqual(plan.buy_component_type_ids, set())
        settings = plan.settings_for(self.rhea_blueprint_typeid, "Rhea Blueprint")
        self.assertEqual(settings.name, "Rhea Blueprint")
        self.assertEqual(settings.blueprint_type_id, self.rhea_blueprint_typeid)

    def test_root_me_reduces_direct_manufacturing_inputs(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result([self.bp("Rhea Blueprint", 10, 0, 1, 1)])

        self.assertEqual(base_result.root.blueprint_settings.material_efficiency, 0)
        self.assertEqual(updated_result.root.blueprint_settings.material_efficiency, 10)
        self.assertEqual(base_result.entries[self.capital_jump_drive].quantity, 30.0)
        self.assertEqual(updated_result.entries[self.capital_jump_drive].quantity, 27.0)
        self.assertEqual(base_result.entries[self.charon].quantity, 1.0)
        self.assertEqual(updated_result.entries[self.charon].quantity, 1.0)

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
        settings = BlueprintSettings(name="Example Blueprint", blueprint_type_id=1, prints=2)
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
        settings = BlueprintSettings(
            name="Example Blueprint",
            blueprint_type_id=1,
            material_efficiency=3,
            prints=2,
        )

        self.assertEqual(ProductionMath().material_quantity(recipe, settings, 975, 1), 1892.0)

    def test_planner_can_temporarily_use_estimate_math(self):
        estimate_planner = BomPlanner(self.idx, use_estimate_math=True)

        result = estimate_planner.build_result(
            PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        )

        self.assertTrue(result.use_estimate_math)
        self.assertEqual(result.entries[self.reinforced_carbon_fiber].quantity, 29160.0)
        self.assertEqual(result.entries[self.tritanium].quantity, 5078493.6)

    def test_duplicate_component_demand_is_aggregated_before_child_expansion(self):
        idx = self.aggregate_fixture_index()
        result = BomPlanner(idx).build_result(
            PlanConfig(
                top_level_blueprints={
                    101: BlueprintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
                    102: BlueprintSettings(name="Root B Blueprint", blueprint_type_id=102, runs=1),
                }
            )
        )

        self.assertEqual(result.entries[300].quantity, 8.0)
        self.assertEqual(result.entries[300].runs, 1.0)
        self.assertEqual(result.entries[400].quantity, 100.0)

    def test_bought_buildable_component_does_not_expand_child_materials(self):
        idx = self.aggregate_fixture_index()
        result = BomPlanner(idx).build_result(
            PlanConfig(
                top_level_blueprints={
                    101: BlueprintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
                },
                buy_component_type_ids={300},
            )
        )

        self.assertTrue(result.entries[300].is_bought)
        self.assertEqual(result.entries[300].tag, "BUY")
        self.assertNotIn(400, result.entries)
        self.assertNotIn(401, result.entries)

    def test_children_under_bought_component_still_block_top_level_selection(self):
        idx = self.aggregate_fixture_index()
        planner = BomPlanner(idx)
        plan = PlanConfig(
            top_level_blueprints={
                101: BlueprintSettings(name="Root A Blueprint", blueprint_type_id=101, runs=1),
            },
            buy_component_type_ids={300},
        )

        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            planner.add_top_level_blueprint(
                plan,
                BlueprintSettings(name="Child Y Blueprint", blueprint_type_id=104, runs=1),
            )

        self.assertNotIn(104, plan.top_level_blueprints)

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
            self.assertTrue(result.entries[fuel_block_type_id].is_bought)

        self.assertTrue(fuel_block_inputs)
        self.assertTrue(fuel_block_inputs.isdisjoint(result.entries))

    def test_child_blueprint_override_rebuilds_descendants_inline(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings=[self.bp(self.jump_drive_blueprint_name, 10, 20)],
        )

        updated_entry = self.built_entries(updated_result, self.jump_drive_blueprint_name)[0]
        self.assertEqual(updated_entry.settings.material_efficiency, 10)
        self.assertEqual(updated_entry.settings.time_efficiency, 20)
        self.assertEqual(base_result.entries[self.reinforced_carbon_fiber].quantity, 29170.0)
        self.assertEqual(updated_result.entries[self.reinforced_carbon_fiber].quantity, 28870.0)
        self.assertEqual(base_result.entries[self.tritanium].quantity, 5079056.0)
        self.assertEqual(updated_result.entries[self.tritanium].quantity, 4899056.0)

    def test_reaction_formula_me_and_te_are_ignored(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings=[self.bp(self.ferrogel_formula_name, 10, 20)],
        )

        ferrogel_entry = self.built_entries(updated_result, self.ferrogel_formula_name)[0]
        self.assertEqual(ferrogel_entry.settings.material_efficiency, 0)
        self.assertEqual(ferrogel_entry.settings.time_efficiency, 0)
        self.assertEqual(base_result.entries[self.fulleroferrocene].quantity, 660.0)
        self.assertEqual(updated_result.entries[self.fulleroferrocene].quantity, 660.0)

    def test_runs_and_prints_drive_output_quantity(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 2, 3)],
        )

        self.assertEqual(result.root.runs, 2.0)
        self.assertEqual(result.root.prints, 3)
        self.assertEqual(result.root.output_quantity, 6.0)
        self.assertEqual(result.entries[self.capital_jump_drive].quantity, 180.0)

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
        self.assertEqual(result.roots[0].blueprint_name, "Heron Blueprint")
        self.assertEqual(result.roots[1].blueprint_name, self.auto_integrity_seal_blueprint_name)

    def test_top_level_selection_cannot_duplicate_existing_selection(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))

        with self.assertRaisesRegex(ValueError, "already selected"):
            self.planner.add_top_level_blueprint(plan, self.bp("Rhea Blueprint", 10, 0, 2, 2))

    def test_time_efficiency_reduces_total_time(self):
        base_result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])
        updated_result = self.build_result([self.bp("Rhea Blueprint", 0, 20, 1, 1)])
        base_time = self.idx.activity_time(self.rhea_blueprint_typeid, 1)

        self.assertEqual(base_result.root.total_time_seconds, base_time)
        self.assertEqual(updated_result.root.total_time_seconds, base_time * 0.8)

    def test_buy_decision_stops_recursion_for_that_component(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            buy_components={"Capital Jump Drive"},
        )

        self.assertIn(self.capital_jump_drive, result.request.buy_component_type_ids)
        self.assertTrue(result.entries[self.capital_jump_drive].is_bought)
        self.assertEqual(result.entries[self.capital_jump_drive].tag, "BUY")
        self.assertIsNone(result.entries[self.capital_jump_drive].recipe)
        self.assertEqual(result.entries[self.capital_jump_drive].quantity, 30.0)
        self.assertNotIn(
            self.jump_drive_blueprint_name,
            {entry.blueprint_name for entry in result.rows if entry.is_built},
        )
        self.assertEqual(result.entries[self.wetware_mainframe].quantity, 1.0)

    def test_child_expansion_prefers_published_blueprint_when_multiple_producers_exist(self):
        recipe = self.idx.build_recipe_for(self.tungsten_carbide)

        self.assertTrue(self.idx.is_published_type(recipe.blueprint_type_id))
        self.assertEqual(recipe.blueprint_type_id, self.tungsten_carbide_formula)

    def test_shopping_list_includes_base_materials_and_bought_components(self):
        result = self.build_result(
            [self.bp("Rhea Blueprint", 0, 0, 1, 1)],
            buy_components={"Capital Jump Drive"},
        )

        shopping_list = result.get_shopping_list()
        names = {material["name"] for material in shopping_list}
        type_ids = [material["type_id"] for material in shopping_list]

        self.assertIn("Tritanium", names)
        self.assertIn("Capital Jump Drive", names)
        self.assertNotIn("Charon", names)
        self.assertEqual(result.entries[self.capital_jump_drive].tag, "BUY")
        self.assertEqual(type_ids, sorted(type_ids))

    def test_shopping_list_can_filter_minerals_and_gas(self):
        result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])

        minerals = {material["name"] for material in result.get_shopping_list("minerals")}
        gas = {material["name"] for material in result.get_shopping_list("gas")}

        self.assertIn("Tritanium", minerals)
        self.assertIn("Morphite", minerals)
        self.assertNotIn("Fullerite-C28", minerals)
        self.assertIn("Fullerite-C28", gas)
        self.assertIn("Amber Cytoserocin", gas)
        self.assertNotIn("Tritanium", gas)

    def test_shopping_list_rejects_unknown_filter(self):
        result = self.build_result([self.bp("Rhea Blueprint", 0, 0, 1, 1)])

        with self.assertRaisesRegex(ValueError, "Unknown shopping list group"):
            result.get_shopping_list("moon")

    def test_print_shopping_list_uses_plain_rows(self):
        from prints import print_shopping_list

        shopping_list = [{"type_id": 34, "name": "Tritanium", "quantity": 12}]

        output = io.StringIO()
        with redirect_stdout(output):
            result = print_shopping_list(shopping_list)

        self.assertIs(result, shopping_list)
        self.assertEqual(output.getvalue(), "\nShopping list:\n  Tritanium 12\n")

    def test_plan_config_applies_top_level_update(self):
        plan = PlanConfig(
            plan_id="test-plan",
            top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )

        plan.update_top_level_blueprints(
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

        settings = plan.top_level_blueprints[self.rhea_blueprint_typeid]
        self.assertEqual(plan.plan_id, "test-plan")
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertEqual(settings.runs, 2.0)
        self.assertEqual(settings.prints, 3)
        self.assertEqual(result.root.output_quantity, 6.0)

    def test_plan_config_updates_only_the_selected_plan_object(self):
        first_plan = PlanConfig(
            plan_id="first-plan",
            top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )
        second_plan = PlanConfig(
            plan_id="second-plan",
            top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
        )

        first_plan.update_top_level_blueprints({self.rhea_blueprint_typeid: {"material_efficiency": 10}})

        self.assertEqual(first_plan.top_level_blueprints[self.rhea_blueprint_typeid].material_efficiency, 10)
        self.assertEqual(second_plan.top_level_blueprints[self.rhea_blueprint_typeid].material_efficiency, 0)

    def test_plan_config_updates_selected_blueprints_without_depth(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type("Capital Jump Drive Blueprint")
        propulsion_id = self.to_type("Capital Propulsion Engine Blueprint")

        plan.update_blueprints(
            {
                jump_drive_id: {"material_efficiency": 10},
                propulsion_id: {"material_efficiency": 10},
            },
        )

        self.assertEqual(plan.blueprint_settings[jump_drive_id].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings[propulsion_id].material_efficiency, 10)

    def test_plan_config_applies_different_updates_in_one_request(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type("Capital Jump Drive Blueprint")
        propulsion_id = self.to_type("Capital Propulsion Engine Blueprint")
        armor_plates_id = self.to_type("Capital Armor Plates Blueprint")

        plan.update_blueprints(
            {
                jump_drive_id: {"material_efficiency": 10},
                propulsion_id: {"material_efficiency": 10},
                armor_plates_id: {"material_efficiency": 8},
            },
        )

        self.assertEqual(plan.blueprint_settings[jump_drive_id].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings[propulsion_id].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings[armor_plates_id].material_efficiency, 8)

    def test_plan_config_rebuilds_after_child_update(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))
        jump_drive_id = self.to_type(self.jump_drive_blueprint_name)

        plan.update_blueprints(
            {
                jump_drive_id: {
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            }
        )
        result = self.planner.build_result(plan)

        settings = plan.blueprint_settings[jump_drive_id]
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertIsNone(settings.runs)
        self.assertEqual(result.entries[self.reinforced_carbon_fiber].quantity, 28870.0)

    def test_plan_config_rejects_runs_update_below_top_level(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]))

        with self.assertRaisesRegex(ValueError, "runs can only be updated"):
            plan.update_blueprints({self.to_type(self.jump_drive_blueprint_name): {"runs": 2}})

    def test_plan_config_rejects_child_settings_with_manual_runs(self):
        with self.assertRaisesRegex(ValueError, "runs can only be set"):
            PlanConfig(
                top_level_blueprints=self.settings_by_id([self.bp("Rhea Blueprint", 0, 0, 1, 1)]),
                blueprint_settings=self.settings_by_id([self.bp(self.jump_drive_blueprint_name, runs=2)]),
            )

    def test_planner_add_top_level_blueprint_does_not_mutate_on_validation_failure(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Raven Blueprint", 0, 0, 1, 1)]))
        auto_integrity_seal = self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1)

        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            self.planner.add_top_level_blueprint(plan, auto_integrity_seal)

        self.assertNotIn(auto_integrity_seal.blueprint_type_id, plan.top_level_blueprints)

    def test_planner_add_top_level_blueprint_mutates_after_validation_success(self):
        plan = PlanConfig(top_level_blueprints=self.settings_by_id([self.bp("Heron Blueprint", 0, 0, 1, 1)]))
        auto_integrity_seal = self.bp(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1)

        self.planner.add_top_level_blueprint(plan, auto_integrity_seal)

        self.assertIn(auto_integrity_seal.blueprint_type_id, plan.top_level_blueprints)
        self.assertEqual(len(self.planner.build_result(plan).roots), 2)

    def test_plan_config_does_not_expose_unsafe_add_top_level_blueprint(self):
        self.assertFalse(hasattr(PlanConfig, "add_top_level_blueprint"))

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
            201: [bp_products[(101, MANUFACTURING_ACTIVITY)]],
            202: [bp_products[(102, MANUFACTURING_ACTIVITY)]],
            300: [bp_products[(103, MANUFACTURING_ACTIVITY)]],
            401: [bp_products[(104, MANUFACTURING_ACTIVITY)]],
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


if __name__ == "__main__":
    unittest.main()
