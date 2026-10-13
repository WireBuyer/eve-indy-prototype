from __future__ import annotations

from math import ceil

from build_models import PrintSettings, ProductionRecipe
from model import MANUFACTURING_ACTIVITY


class ProductionMath:
    def __init__(self, use_estimate_math: bool = False):
        self.use_estimate_math = use_estimate_math

    def runs_for(
        self,
        recipe: ProductionRecipe,
        settings: PrintSettings,
        required_quantity: float | None,
    ) -> float:
        if settings.runs is not None:
            return settings.runs
        if required_quantity is None:
            return 1.0

        output_per_job = recipe.output_per_run * settings.prints
        if output_per_job <= 0:
            return float(required_quantity if self.use_estimate_math else ceil(required_quantity))
        if self.use_estimate_math:
            return float(required_quantity) / output_per_job
        return float(ceil(float(required_quantity) / output_per_job))

    def output_quantity(self, recipe: ProductionRecipe, settings: PrintSettings, runs: float) -> float:
        return recipe.output_per_run * runs * settings.prints

    def material_quantity(
        self,
        recipe: ProductionRecipe,
        settings: PrintSettings,
        quantity_per_run: float,
        runs: float,
        structure_modifier: float = 1.0,
    ) -> float:
        if self.use_estimate_math:
            quantity = quantity_per_run * runs * settings.prints
            if recipe.activity == MANUFACTURING_ACTIVITY and quantity_per_run > 1.0:
                return quantity * self.material_modifier(recipe, settings) * structure_modifier
            if recipe.activity != MANUFACTURING_ACTIVITY:
                return quantity * structure_modifier
            return quantity

        quantity_per_print = runs * quantity_per_run * self.material_modifier(recipe, settings) * structure_modifier
        required_per_print = max(runs, ceil(round(quantity_per_print, 2)))
        return required_per_print * settings.prints

    def total_time(
        self,
        recipe: ProductionRecipe,
        settings: PrintSettings,
        runs: float,
        structure_modifier: float = 1.0,
    ) -> float:
        seconds = recipe.time_per_run * runs * settings.prints
        if recipe.activity == MANUFACTURING_ACTIVITY:
            return seconds * (1.0 - (settings.time_efficiency / 100.0)) * structure_modifier
        return seconds * structure_modifier

    def material_modifier(self, recipe: ProductionRecipe, settings: PrintSettings) -> float:
        if recipe.activity == MANUFACTURING_ACTIVITY:
            return 1.0 - (settings.material_efficiency / 100.0)
        return 1.0
