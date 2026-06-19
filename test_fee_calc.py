import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_models import JobFees
from fee_calc import JobFeeCalculator
from industry_index import IndustryIndex
from model import (
    COPYING_ACTIVITY,
    INVENTION_ACTIVITY,
    MANUFACTURING_ACTIVITY,
    MATERIAL_RESEARCH_ACTIVITY,
    REACTION_ACTIVITY,
    TIME_RESEARCH_ACTIVITY,
    MaterialRow,
)
from structures import RigMode, RigTier, StructureBonusService, StructureConfig


class JobFeeCalculatorTests(unittest.TestCase):
    def test_load_adjusted_prices_converts_json_keys_to_int(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "adjusted_prices.json"
            path.write_text(json.dumps({"34": 5.25, "35": "12.5"}), encoding="utf-8")
            idx = IndustryIndex({}, {}, {}, {}, {})

            idx.load_adjusted_prices(str(path))

            self.assertEqual(idx.adjusted_prices, {34: 5.25, 35: 12.5})

    def test_calculate_uses_base_material_quantities_runs_and_prints(self):
        calculator = JobFeeCalculator({34: 5.0, 35: 10.0})
        materials = [
            MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 100),
            MaterialRow(100, MANUFACTURING_ACTIVITY, 35, 20),
        ]

        fees = calculator.get_production_fees(materials, runs=2, prints=3)

        self.assertEqual(fees.scc_surcharge, 168.0)
        self.assertEqual(fees.index_fee, 0.0)
        self.assertEqual(fees.tax_fee, 0.0)

    def test_calculate_rounds_each_print_fee_before_multiplying_prints(self):
        calculator = JobFeeCalculator({34: 10.1})
        materials = [MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 1)]

        fees = calculator.get_production_fees(materials, runs=1, prints=3)

        self.assertEqual(fees.scc_surcharge, 3.0)

    def test_calculate_applies_job_cost_modifier_to_index_fee_only(self):
        calculator = JobFeeCalculator({34: 101.0})
        materials = [MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 1)]

        fees = calculator.get_production_fees(
            materials,
            runs=1,
            prints=1,
            system_index=0.1,
            job_cost_modifier=0.97,
        )

        self.assertEqual(fees.scc_surcharge, 5.0)
        self.assertEqual(fees.index_fee, 10.0)

    def test_calculate_applies_facility_tax(self):
        calculator = JobFeeCalculator({34: 101.0})
        materials = [MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 1)]

        fees = calculator.get_production_fees(
            materials,
            runs=1,
            prints=2,
            facility_tax_rate=0.05,
        )

        self.assertEqual(fees.scc_surcharge, 10.0)
        self.assertEqual(fees.index_fee, 0.0)
        self.assertEqual(fees.tax_fee, 12.0)

    def test_job_fees_str_formats_all_fee_fields(self):
        fees = JobFees(scc_surcharge=1234, index_fee=56.7, tax_fee=0)

        self.assertEqual(
            str(fees),
            "SCC surcharge 1,234.00 ISK | index fee 56.70 ISK | tax fee 0.00 ISK | total 1,290.70 ISK",
        )

    def test_structure_job_cost_modifier_applies_engineering_complex_role_bonus(self):
        service = StructureBonusService(IndustryIndex({}, {}, {}, {}, {}))

        self.assertEqual(
            service.job_cost_modifier(StructureConfig("raitaru", "Raitaru", "Raitaru", "highsec"), MANUFACTURING_ACTIVITY),
            0.97,
        )
        self.assertEqual(
            service.job_cost_modifier(StructureConfig("azbel", "Azbel", "Azbel", "highsec"), MANUFACTURING_ACTIVITY),
            0.96,
        )
        self.assertEqual(
            service.job_cost_modifier(StructureConfig("sotiyo", "Sotiyo", "Sotiyo", "nullsec"), MANUFACTURING_ACTIVITY),
            0.95,
        )

    def test_structure_job_cost_modifier_does_not_apply_to_reactions(self):
        service = StructureBonusService(IndustryIndex({}, {}, {}, {}, {}))

        self.assertEqual(
            service.job_cost_modifier(StructureConfig("tatara", "Tatara", "Tatara", "lowsec"), REACTION_ACTIVITY),
            1.0,
        )

    def test_simple_science_job_cost_rig_uses_security_multiplier(self):
        service = StructureBonusService(IndustryIndex({}, {}, {}, {}, {}))

        self.assertAlmostEqual(
            service.job_cost_modifier(
                StructureConfig(
                    "science",
                    "Science Raitaru",
                    "Raitaru",
                    "lowsec",
                    job_cost=RigTier.T2,
                ),
                INVENTION_ACTIVITY,
            ),
            0.772,
        )

    def test_science_job_cost_rig_only_applies_to_matching_activity(self):
        service = StructureBonusService(IndustryIndex({}, {}, {}, {}, {}))
        config = StructureConfig(
            "science",
            "Advanced Science Raitaru",
            "Raitaru",
            "nullsec",
            rig_mode=RigMode.ADVANCED,
            rigs=[("Standup M-Set ME Research Cost Optimization II", 43884, RigTier.T2)],
        )

        self.assertAlmostEqual(
            service.job_cost_modifier(config, MATERIAL_RESEARCH_ACTIVITY),
            0.748,
        )
        self.assertEqual(service.job_cost_modifier(config, TIME_RESEARCH_ACTIVITY), 1.0)
        self.assertEqual(service.job_cost_modifier(config, COPYING_ACTIVITY), 1.0)

    def test_calculate_raises_when_adjusted_price_is_missing(self):
        calculator = JobFeeCalculator({})
        materials = [MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 100)]

        with self.assertRaises(KeyError):
            calculator.get_production_fees(materials, runs=1, prints=1)


if __name__ == "__main__":
    unittest.main()
