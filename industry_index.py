from __future__ import annotations

import json
from build_models import ProductionRecipe
from model import (
    MANUFACTURING_ACTIVITY,
    REACTION_ACTIVITY,
    BlueprintActivityTime,
    BlueprintProduct,
    IndustryActivitySkill,
    MaterialRow,
    TypeInfo,
)


class IndustryIndex:
    """Read-only lookup facade over the loaded EVE industry data."""

    def __init__(
        self,
        inv_types: dict[int, TypeInfo],
        bp_products: dict[tuple[int, int], BlueprintProduct],
        bp_by_product: dict[int, BlueprintProduct],
        materials: dict[tuple[int, int], list[MaterialRow]],
        activity_times: dict[tuple[int, int], BlueprintActivityTime],
        rig_affected_groups: dict[tuple[int, str, str], set[int]] | None = None,
        rig_meta_groups: dict[int, int] | None = None,
        solar_system_ids_by_name: dict[str, int] | None = None,
        activity_skills: dict[tuple[int, int], list[IndustryActivitySkill]] | None = None,
    ):
        self._inv_types = inv_types
        self._bp_products = bp_products
        self._bp_by_product = bp_by_product
        self._materials = materials
        self._activity_times = activity_times
        self._activity_skills = activity_skills or {}
        self._rig_affected_groups = rig_affected_groups or {}
        self._rig_meta_groups = rig_meta_groups or {}
        self._adjusted_prices: dict[int, float] = {}
        self._system_indexes: dict[int, dict[int, float]] = {}
        self._type_id_by_name = {type_info.name: type_id for type_id, type_info in inv_types.items()}
        self._solar_system_ids_by_name = {
            name.casefold(): int(system_id)
            for name, system_id in (solar_system_ids_by_name or {}).items()
        }

    def get_type(self, type_id: int) -> TypeInfo | None:
        return self._inv_types.get(type_id)

    def type_name(self, type_id: int) -> str:
        type_info = self.get_type(type_id)
        return type_info.name if type_info is not None else f"<type {type_id}>"

    def find_type_id_by_name(self, name: str) -> int | None:
        return self._type_id_by_name.get(name)

    def rig_meta_group(self, type_id: int) -> int | None:
        return self._rig_meta_groups.get(type_id)

    def get_system_id(self, name: str) -> int | None:
        return self._solar_system_ids_by_name.get(name.lower())

    def load_adjusted_prices(self, path: str = "adjusted_prices.json") -> None:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Adjusted price file must contain a JSON object.")

        self._adjusted_prices = {int(type_id): float(price) for type_id, price in data.items()}
    
    def load_indexes(self, path: str = "system_indexes.json") -> None:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        system_indexes = {}
        for system_id, cost_indices in data.items():

            activity_indexes: dict[int, float] = {}
            for activity_id, cost_index in cost_indices.items():
                activity_indexes[int(activity_id)] = float(cost_index)

            system_indexes[int(system_id)] = activity_indexes

        self._system_indexes = system_indexes

    def get_system_index(self, system_id: int, activity_id: int) -> float:
        return self._system_indexes[system_id][activity_id]
    
    def is_published_type(self, type_id: int) -> bool:
        return type_id in self._inv_types

    def activity_for(self, blueprint_type_id: int) -> int | None:
        if (blueprint_type_id, MANUFACTURING_ACTIVITY) in self._bp_products:
            return MANUFACTURING_ACTIVITY
        if (blueprint_type_id, REACTION_ACTIVITY) in self._bp_products:
            return REACTION_ACTIVITY
        return None

    def output(self, blueprint_type_id: int, activity: int | None = None) -> BlueprintProduct | None:
        selected_activity = activity if activity is not None else self.activity_for(blueprint_type_id)
        if selected_activity is None:
            return None
        return self._bp_products.get((blueprint_type_id, selected_activity))

    def recipe_for_blueprint(self, blueprint_type_id: int) -> ProductionRecipe | None:
        product = self._bp_products.get((blueprint_type_id, MANUFACTURING_ACTIVITY))
        if product is not None:
            return self.recipe_from_product(product)

        product = self._bp_products.get((blueprint_type_id, REACTION_ACTIVITY))
        if product is not None:
            return self.recipe_from_product(product)

        return None

    def inputs(self, blueprint_type_id: int, activity: int | None = None) -> list[MaterialRow]:
        selected_activity = activity if activity is not None else self.activity_for(blueprint_type_id)
        if selected_activity is None:
            return []
        return list(self._materials.get((blueprint_type_id, selected_activity), []))

    def skills_for(self, blueprint_type_id: int, activity: int | None = None) -> list[IndustryActivitySkill]:
        selected_activity = activity if activity is not None else self.activity_for(blueprint_type_id)
        if selected_activity is None:
            return []
        return list(self._activity_skills.get((blueprint_type_id, selected_activity), []))

    def build_recipe_for(self, product_type_id: int) -> ProductionRecipe | None:
        blueprint = self._bp_by_product.get(product_type_id)
        if blueprint is None:
            return None
        return self.recipe_from_product(blueprint)

    def recipe_from_product(self, product: BlueprintProduct) -> ProductionRecipe:
        return ProductionRecipe(
            blueprint_type_id=product.type_id,
            blueprint_name=self.type_name(product.type_id),
            activity=product.activity,
            product_type_id=product.product_typeid,
            product_name=self.type_name(product.product_typeid),
            output_per_run=float(product.quantity),
            time_per_run=self.activity_time(product.type_id, product.activity) or 0.0,
            product_group_id=self.group_id(product.product_typeid),
        )

    def activity_time(self, blueprint_type_id: int, activity: int) -> float | None:
        row = self._activity_times.get((blueprint_type_id, activity))
        return row.time if row is not None else None

    def group_id(self, type_id: int) -> int | None:
        type_info = self.get_type(type_id)
        return None if type_info is None else type_info.group_id

    @property
    def rig_groups(self) -> dict[tuple[int, str, str], set[int]]:
        return self._rig_affected_groups

    @property
    def inv_types(self) -> dict[int, TypeInfo]:
        return self._inv_types

    @property
    def adjusted_prices(self) -> dict[int, float]:
        return dict(self._adjusted_prices)
