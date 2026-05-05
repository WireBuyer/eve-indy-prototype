from __future__ import annotations

from model import (
    PRODUCTION_ACTIVITIES,
    BlueprintActivityTime,
    BlueprintProduct,
    MaterialRow,
    TypeInfo,
)


class IndustryIndex:
    """Read-only lookup facade over the loaded EVE industry data."""

    def __init__(
        self,
        inv_types: dict[int, TypeInfo],
        bp_products: dict[tuple[int, int], list[BlueprintProduct]],
        bp_by_product: dict[int, list[BlueprintProduct]],
        materials: dict[tuple[int, int], list[MaterialRow]],
        activity_times: dict[tuple[int, int], BlueprintActivityTime],
    ):
        self._inv_types = inv_types
        self._bp_products = bp_products
        self._bp_by_product = bp_by_product
        self._materials = materials
        self._activity_times = activity_times
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
        for activity in PRODUCTION_ACTIVITIES:
            if (blueprint_type_id, activity) in self._bp_products:
                return activity
        return None

    def outputs(self, blueprint_type_id: int, activity: int | None = None) -> list[BlueprintProduct]:
        selected_activity = activity if activity is not None else self.activity_for(blueprint_type_id)
        if selected_activity is None:
            return []
        return list(self._bp_products.get((blueprint_type_id, selected_activity), []))

    def inputs(self, blueprint_type_id: int, activity: int | None = None) -> list[MaterialRow]:
        selected_activity = activity if activity is not None else self.activity_for(blueprint_type_id)
        if selected_activity is None:
            return []
        return list(self._materials.get((blueprint_type_id, selected_activity), []))

    def blueprints_for(self, product_type_id: int) -> list[BlueprintProduct]:
        return list(self._bp_by_product.get(product_type_id, []))

    def build_blueprint_for(self, product_type_id: int) -> BlueprintProduct | None:
        blueprints = self.blueprints_for(product_type_id)
        published_blueprints = [
            blueprint
            for blueprint in blueprints
            if self.is_published_type(blueprint.type_id)
        ]
        selected_blueprints = published_blueprints or blueprints

        for activity in PRODUCTION_ACTIVITIES:
            for blueprint in selected_blueprints:
                if blueprint.activity == activity:
                    return blueprint
        return selected_blueprints[0] if selected_blueprints else None

    def activity_time(self, blueprint_type_id: int, activity: int) -> float | None:
        row = self._activity_times.get((blueprint_type_id, activity))
        return row.time if row is not None else None

    @property
    def inv_types(self) -> dict[int, TypeInfo]:
        return self._inv_types
