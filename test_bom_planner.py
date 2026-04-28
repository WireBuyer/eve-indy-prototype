import unittest

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

        updated_usage = next(
            usage
            for usage in updated_snapshot.used_blueprints
            if usage.production.blueprint_name == self.jump_drive_blueprint_name
        )
        self.assertEqual(updated_usage.production.settings.material_efficiency, 10)
        self.assertEqual(updated_usage.production.settings.time_efficiency, 20)
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

        ferrogel_usage = next(
            usage
            for usage in updated_snapshot.used_blueprints
            if usage.production.blueprint_name == self.ferrogel_formula_name
        )
        self.assertEqual(ferrogel_usage.production.settings.material_efficiency, 0)
        self.assertEqual(ferrogel_usage.production.settings.time_efficiency, 0)
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

    def test_multiple_top_level_blueprints_can_use_different_job_sizes(self):
        snapshot = self.build_snapshot(
            [
                BlueprintSettings("Rhea Blueprint", 0, 0, 1, 1),
                BlueprintSettings("Rhea Blueprint", 10, 0, 2, 2),
            ],
        )

        self.assertEqual(len(snapshot.roots), 2)
        self.assertEqual(snapshot.roots[0].planned_output_quantity, 1.0)
        self.assertEqual(snapshot.roots[1].planned_output_quantity, 4.0)
        self.assertEqual(snapshot.aggregates[self.capital_jump_drive].quantity, 138.0)

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
        self.assertNotIn(self.jump_drive_blueprint_name, {usage.production.blueprint_name for usage in snapshot.used_blueprints})
        self.assertEqual(snapshot.aggregates[self.wetware_mainframe].quantity, 1.0)


if __name__ == "__main__":
    unittest.main()
