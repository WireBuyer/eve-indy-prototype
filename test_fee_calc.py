import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_models import JobFees
from fee_calc import JobFeeCalculator
from industry_index import IndustryIndex
from model import MANUFACTURING_ACTIVITY, MaterialRow


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

    def test_job_fees_str_formats_all_fee_fields(self):
        fees = JobFees(scc_surcharge=1234, index_fee=56.7, tax_fee=0)

        self.assertEqual(
            str(fees),
            "SCC surcharge 1,234.00 ISK | System index 56.70 ISK | "
            "Tax 0.00 ISK | Total 1,290.70 ISK",
        )

    def test_calculate_raises_when_adjusted_price_is_missing(self):
        calculator = JobFeeCalculator({})
        materials = [MaterialRow(100, MANUFACTURING_ACTIVITY, 34, 100)]

        with self.assertRaisesRegex(KeyError, "Missing adjusted price for type 34"):
            calculator.get_production_fees(materials, runs=1, prints=1)


if __name__ == "__main__":
    unittest.main()
