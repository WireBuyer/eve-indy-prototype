from __future__ import annotations

from build_models import ProductionRecipe
from model import (
    MANUFACTURING_ACTIVITY,
    REACTION_ACTIVITY,
    BlueprintActivityTime,
    BlueprintProduct,
    MaterialRow,
    RigModifierSource,
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
        rig_modifier_sources: dict[int, list[RigModifierSource]] | None = None,
        rig_affected_groups: dict[tuple[int, str, str], set[int]] | None = None,
        affected_groups_by_activity: dict[tuple[str, str], set[int]] | None = None,
        rig_attribute_values: dict[int, dict[int, float]] | None = None,
    ):
        self._inv_types = inv_types
        self._bp_products = bp_products
        self._bp_by_product = bp_by_product
        self._materials = materials
        self._activity_times = activity_times
        self._rig_modifier_sources = rig_modifier_sources or {}
        self._rig_affected_groups = rig_affected_groups or {}
        self._affected_groups_by_activity = affected_groups_by_activity or {}
        self._rig_attribute_values = rig_attribute_values or {}
        self._type_id_by_name = {type_info.name: type_id for type_id, type_info in inv_types.items()}

    def get_type(self, type_id: int) -> TypeInfo | None:
        return self._inv_types.get(type_id)

    def type_name(self, type_id: int) -> str:
        type_info = self.get_type(type_id)
        return type_info.name if type_info is not None else f"<type {type_id}>"

    def find_type_id_by_name(self, name: str) -> int | None:
        return self._type_id_by_name.get(name)

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

    def rig_modifier_sources(self, rig_type_id: int, activity_key: str, bonus_type: str) -> list[RigModifierSource]:
        return [
            source
            for source in self._rig_modifier_sources.get(rig_type_id, [])
            if source.activity_key == activity_key and source.bonus_type == bonus_type
        ]

    def rig_affected_product_groups(self, rig_type_id: int, activity_key: str, bonus_type: str) -> set[int]:
        return set(self._rig_affected_groups.get((rig_type_id, activity_key, bonus_type), set()))

    def has_rig_for_product_group(self, activity_key: str, bonus_type: str, product_group_id: int | None) -> bool:
        if product_group_id is None:
            return False
        return product_group_id in self._affected_groups_by_activity.get((activity_key, bonus_type), set())

    def rig_attribute_value(self, rig_type_id: int, attribute_id: int) -> float | None:
        return self._rig_attribute_values.get(rig_type_id, {}).get(attribute_id)

    @property
    def inv_types(self) -> dict[int, TypeInfo]:
        return self._inv_types
