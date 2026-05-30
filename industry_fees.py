from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from model import MaterialRow


DEFAULT_SCC_SURCHARGE_RATE = 0.04


@dataclass(frozen=True)
class JobFees:
    scc_fee: float = 0.0
    system_index_fee: float = 0.0
    tax_fee: float = 0.0


class IndustryFeeCalculator:
    def job_fees(self, materials: Iterable[MaterialRow], runs: float, prints: int) -> JobFees:
        estimated_item_value = self.estimated_item_value(materials, runs, prints)
        return JobFees(
            scc_fee=estimated_item_value * self.scc_surcharge_rate(),
            system_index_fee=0.0,
            tax_fee=0.0,
        )

    def estimated_item_value(self, materials: Iterable[MaterialRow], runs: float, prints: int) -> float:
        base_material_value = sum(
            material.quantity * self.adjusted_price(material.material_typeid)
            for material in materials
        )
        return base_material_value * runs * prints

    def adjusted_price(self, type_id: int) -> float:
        return 0.0

    def scc_surcharge_rate(self) -> float:
        return DEFAULT_SCC_SURCHARGE_RATE
