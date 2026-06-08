from __future__ import annotations

from math import ceil

from build_models import JobFees
from model import MaterialRow


SCC_SURCHARGE_RATE = 0.04


class JobFeeCalculator:
    def __init__(self, adjusted_prices: dict[int, float]):
        self.adjusted_prices = dict(adjusted_prices)

    def get_production_fees(
        self,
        materials: list[MaterialRow],
        runs: float,
        prints: int,
        system_index: float = 0.0,
        job_cost_modifier: float = 1.0,
    ) -> JobFees:
        eiv = 0.0
        for material in materials:
            adjusted_price = self.adjusted_prices[material.material_typeid]
            eiv += material.quantity * runs * adjusted_price

        scc_surcharge = ceil(eiv * SCC_SURCHARGE_RATE) * prints
        index_fee = ceil(eiv * system_index * job_cost_modifier) * prints

        return JobFees(
            scc_surcharge=scc_surcharge,
            index_fee=index_fee,
            tax_fee=0.0,
        )

    # todo: implement science fee function
