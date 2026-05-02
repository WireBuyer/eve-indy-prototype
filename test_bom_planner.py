import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bom_planner import BomPlanner
from db_io import load_tables
from model import BlueprintSettings, PlanConfig


class BomPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = load_tables("eve.db")
        cls.planner = BomPlanner(cls.idx)
        cls.rhea_blueprint_typeid = cls.idx.find_type_id_by_name("Rhea Blueprint")
        cls.jump_drive_blueprint_name = "Capital Jump Drive Blueprint"
        cls.ferrogel_formula_name = "Ferrogel Reaction Formula"
        cls.auto_integrity_seal_blueprint_name = "Auto-Integrity Preservation Seal Blueprint"

        cls.capital_jump_drive = cls.idx.find_type_id_by_name("Capital Jump Drive")
        cls.charon = cls.idx.find_type_id_by_name("Charon")
        cls.reinforced_carbon_fiber = cls.idx.find_type_id_by_name("Reinforced Carbon Fiber")
        cls.tritanium = cls.idx.find_type_id_by_name("Tritanium")
        cls.fulleroferrocene = cls.idx.find_type_id_by_name("Fulleroferrocene")
        cls.wetware_mainframe = cls.idx.find_type_id_by_name("Wetware Mainframe")

    def build_snapshot(self, blueprints, blueprint_settings=None, buy_components=None):
        return self.planner.build_snapshot(
            PlanConfig(
                top_level_blueprints=blueprints,
                blueprint_settings=blueprint_settings,
                buy_components=buy_components,
            )
        )

    def production_rows(self, snapshot, blueprint_name):
        return [
            row
            for row in snapshot.rows
            if row.production is not None and row.production.blueprint_name == blueprint_name
        ]

    def test_plan_config_normalizes_optional_collections(self):
        plan = PlanConfig(top_level_blueprints=None, blueprint_settings=None, buy_components=None)

        self.assertIsNone(plan.plan_id)
        self.assertEqual(plan.top_level_blueprints, {})
        self.assertEqual(plan.blueprint_settings, {})
        self.assertEqual(plan.buy_components, set())
        self.assertEqual(plan.settings_for("Rhea Blueprint").name, "Rhea Blueprint")

    def test_root_me_reduces_direct_manufacturing_inputs(self):
        base_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])
        updated_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 10, 0, 1, 1)])

        self.assertEqual(base_snapshot.root.blueprint_settings.material_efficiency, 0)
        self.assertEqual(updated_snapshot.root.blueprint_settings.material_efficiency, 10)
        self.assertEqual(base_snapshot.aggregates[self.capital_jump_drive].quantity, 30.0)
        self.assertEqual(updated_snapshot.aggregates[self.capital_jump_drive].quantity, 27.0)
        self.assertEqual(base_snapshot.aggregates[self.charon].quantity, 1.0)
        self.assertEqual(updated_snapshot.aggregates[self.charon].quantity, 1.0)

    def test_child_blueprint_override_rebuilds_descendants_inline(self):
        base_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])
        updated_snapshot = self.build_snapshot(
            [BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings={
                self.jump_drive_blueprint_name: BlueprintSettings(self.jump_drive_blueprint_name, 10, 20),
            },
        )

        updated_row = self.production_rows(updated_snapshot, self.jump_drive_blueprint_name)[0]
        self.assertEqual(updated_row.production.settings.material_efficiency, 10)
        self.assertEqual(updated_row.production.settings.time_efficiency, 20)
        self.assertEqual(base_snapshot.aggregates[self.reinforced_carbon_fiber].quantity, 29160.0)
        self.assertEqual(updated_snapshot.aggregates[self.reinforced_carbon_fiber].quantity, 28860.0)
        self.assertEqual(base_snapshot.aggregates[self.tritanium].quantity, 5078493.6)
        self.assertEqual(updated_snapshot.aggregates[self.tritanium].quantity, 4898493.6)

    def test_reaction_formula_me_and_te_are_ignored(self):
        base_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])
        updated_snapshot = self.build_snapshot(
            [BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
            blueprint_settings={
                self.ferrogel_formula_name: BlueprintSettings(self.ferrogel_formula_name, 10, 20),
            },
        )

        ferrogel_row = self.production_rows(updated_snapshot, self.ferrogel_formula_name)[0]
        self.assertEqual(ferrogel_row.production.settings.material_efficiency, 0)
        self.assertEqual(ferrogel_row.production.settings.time_efficiency, 0)
        self.assertEqual(base_snapshot.aggregates[self.fulleroferrocene].quantity, 660.0)
        self.assertEqual(updated_snapshot.aggregates[self.fulleroferrocene].quantity, 660.0)

    def test_runs_and_prints_drive_output_quantity(self):
        snapshot = self.build_snapshot(
            [BlueprintSettings("Rhea Blueprint", 0, 0, 2, 3)],
        )

        self.assertEqual(snapshot.root.runs, 2.0)
        self.assertEqual(snapshot.root.prints, 3)
        self.assertEqual(snapshot.root.planned_output_quantity, 6.0)
        self.assertEqual(snapshot.aggregates[self.capital_jump_drive].quantity, 180.0)

    def test_top_level_selection_cannot_duplicate_a_child_requirement(self):
        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            self.build_snapshot(
                [
                    BlueprintSettings("Raven Blueprint", 0, 0, 1, 1),
                    BlueprintSettings(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
                ],
            )

    def test_top_level_selection_cannot_absorb_existing_selection_as_child(self):
        with self.assertRaisesRegex(ValueError, "requires an existing top-level selection"):
            self.build_snapshot(
                [
                    BlueprintSettings(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
                    BlueprintSettings("Raven Blueprint", 0, 0, 1, 1),
                ],
            )

    def test_top_level_selection_allows_unrelated_component_blueprint(self):
        snapshot = self.build_snapshot(
            [
                BlueprintSettings("Heron Blueprint", 0, 0, 1, 1),
                BlueprintSettings(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1),
            ],
        )

        self.assertEqual(len(snapshot.roots), 2)
        self.assertEqual(snapshot.roots[0].blueprint_name, "Heron Blueprint")
        self.assertEqual(snapshot.roots[1].blueprint_name, self.auto_integrity_seal_blueprint_name)

    def test_top_level_selection_cannot_duplicate_existing_selection(self):
        with self.assertRaisesRegex(ValueError, "already selected"):
            self.build_snapshot(
                [
                    BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1),
                    BlueprintSettings("Rhea Blueprint", 10, 0, 2, 2),
                ],
            )

    def test_time_efficiency_reduces_total_time(self):
        base_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])
        updated_snapshot = self.build_snapshot([BlueprintSettings("Rhea Blueprint", 0, 20, 1, 1)])
        base_time = self.idx.activity_time(self.rhea_blueprint_typeid, 1)

        self.assertEqual(base_snapshot.root.total_time_seconds, base_time)
        self.assertEqual(updated_snapshot.root.total_time_seconds, base_time * 0.8)

    def test_buy_decision_stops_recursion_for_that_component(self):
        snapshot = self.build_snapshot(
            [BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
            buy_components={"Capital Jump Drive"},
        )

        self.assertIn("Capital Jump Drive", snapshot.request.buy_components)
        self.assertIsNone(snapshot.aggregates[self.capital_jump_drive].production)
        self.assertEqual(snapshot.aggregates[self.capital_jump_drive].quantity, 30.0)
        self.assertNotIn(
            self.jump_drive_blueprint_name,
            {row.production.blueprint_name for row in snapshot.rows if row.production is not None},
        )
        self.assertEqual(snapshot.aggregates[self.wetware_mainframe].quantity, 1.0)

    def test_plan_config_applies_top_level_update(self):
        plan = PlanConfig(
            plan_id="test-plan",
            top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
        )

        plan.update_top_level_blueprints(
            {
                "Rhea Blueprint": {
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                    "runs": 2,
                    "prints": 3,
                }
            },
        )
        snapshot = self.planner.build_snapshot(plan)

        settings = plan.top_level_blueprints["Rhea Blueprint"]
        self.assertEqual(plan.plan_id, "test-plan")
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertEqual(settings.runs, 2.0)
        self.assertEqual(settings.prints, 3)
        self.assertEqual(snapshot.root.planned_output_quantity, 6.0)

    def test_plan_config_updates_only_the_selected_plan_object(self):
        first_plan = PlanConfig(
            plan_id="first-plan",
            top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
        )
        second_plan = PlanConfig(
            plan_id="second-plan",
            top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)],
        )

        first_plan.update_top_level_blueprints({"Rhea Blueprint": {"material_efficiency": 10}})

        self.assertEqual(first_plan.top_level_blueprints["Rhea Blueprint"].material_efficiency, 10)
        self.assertEqual(second_plan.top_level_blueprints["Rhea Blueprint"].material_efficiency, 0)

    def test_plan_config_updates_selected_blueprints_without_depth(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])

        plan.update_blueprints(
            {
                "Capital Jump Drive Blueprint": {"material_efficiency": 10},
                "Capital Propulsion Engine Blueprint": {"material_efficiency": 10},
            },
        )

        self.assertEqual(plan.blueprint_settings["Capital Jump Drive Blueprint"].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings["Capital Propulsion Engine Blueprint"].material_efficiency, 10)

    def test_plan_config_applies_different_updates_in_one_request(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])

        plan.update_blueprints(
            {
                "Capital Jump Drive Blueprint": {"material_efficiency": 10},
                "Capital Propulsion Engine Blueprint": {"material_efficiency": 10},
                "Capital Armor Plates Blueprint": {"material_efficiency": 8},
            },
        )

        self.assertEqual(plan.blueprint_settings["Capital Jump Drive Blueprint"].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings["Capital Propulsion Engine Blueprint"].material_efficiency, 10)
        self.assertEqual(plan.blueprint_settings["Capital Armor Plates Blueprint"].material_efficiency, 8)

    def test_plan_config_rebuilds_after_child_update(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])

        plan.update_blueprints(
            {
                self.jump_drive_blueprint_name: {
                    "material_efficiency": 10,
                    "time_efficiency": 20,
                }
            }
        )
        snapshot = self.planner.build_snapshot(plan)

        settings = plan.blueprint_settings[self.jump_drive_blueprint_name]
        self.assertEqual(settings.material_efficiency, 10)
        self.assertEqual(settings.time_efficiency, 20)
        self.assertIsNone(settings.runs)
        self.assertEqual(snapshot.aggregates[self.reinforced_carbon_fiber].quantity, 28860.0)

    def test_plan_config_rejects_runs_update_below_top_level(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])

        with self.assertRaisesRegex(ValueError, "runs can only be updated"):
            plan.update_blueprints({self.jump_drive_blueprint_name: {"runs": 2}})

    def test_plan_config_add_top_level_blueprint_is_validated_by_planner(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Raven Blueprint", 0, 0, 1, 1)])
        plan.add_top_level_blueprint(BlueprintSettings(self.auto_integrity_seal_blueprint_name, 0, 0, 1, 1))

        with self.assertRaisesRegex(ValueError, "already required by another selection"):
            self.planner.build_snapshot(plan)

    def test_plan_config_rejects_added_duplicate_top_level_blueprint(self):
        plan = PlanConfig(top_level_blueprints=[BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1)])

        with self.assertRaisesRegex(ValueError, "already selected"):
            plan.add_top_level_blueprint(BlueprintSettings("Rhea Blueprint", 10, 0, 2, 2))

    def test_main_output_matches_example_fixture(self):
        from main import main

        output = io.StringIO()
        with redirect_stdout(output):
            main()

        self.assertEqual(output.getvalue(), Path("Example 2.txt").read_text())


if __name__ == "__main__":
    unittest.main()
