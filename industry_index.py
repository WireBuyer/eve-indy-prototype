from typing import Dict, List, Optional

from model import TypeInfo, BlueprintProduct, MaterialRow, BlueprintActivityTime


class IndustryIndex:
    """Encapsulates SDE lookups and hides tuple-key storage details.

    Use this instead of passing raw dicts around. Methods are concise and
    focused on domain operations (outputs, inputs, blueprints_for, activity_time).
    """

    def __init__(self,
                 inv_types: Dict[int, TypeInfo],
                 bp_products: Dict[tuple, List[BlueprintProduct]],
                 bp_by_product: Dict[int, List[BlueprintProduct]],
                 materials: Dict[tuple, List[MaterialRow]],
                 activity_times: Dict[tuple, BlueprintActivityTime]):
        self._inv_types = inv_types
        self._bp_products = bp_products
        self._bp_by_product = bp_by_product
        self._materials = materials
        self._activity_times = activity_times

    def get_type(self, type_id: int) -> Optional[TypeInfo]:
        return self._inv_types.get(type_id)

    def type_name(self, type_id: int) -> str:
        type_info = self.get_type(type_id)
        return type_info.name if type_info is not None else f"<type {type_id}>"

    def find_type_id_by_name(self, name: str) -> Optional[int]:
        for type_id, type_info in self._inv_types.items():
            if type_info.name == name:
                return type_id
        return None

    def activity_for(self, blueprint_typeid: int) -> Optional[int]:
        """Return the production activity id to use for this blueprint.

        Prefer manufacturing (1) then reactions (11). Does NOT consult the
        timing table for selection — selection is based on whether outputs
        exist for the activity.
        """
        if (blueprint_typeid, 1) in self._bp_products:
            return 1
        if (blueprint_typeid, 11) in self._bp_products:
            return 11
        return None

    def outputs(self, blueprint_typeid: int, activity: Optional[int] = None) -> List[BlueprintProduct]:
        if activity is not None:
            return list(self._bp_products.get((blueprint_typeid, activity), []))
        act = self.activity_for(blueprint_typeid)
        return list(self._bp_products.get((blueprint_typeid, act), [])) if act is not None else []

    def inputs(self, blueprint_typeid: int, activity: Optional[int] = None) -> List[MaterialRow]:
        act = activity if activity is not None else self.activity_for(blueprint_typeid)
        return list(self._materials.get((blueprint_typeid, act), [])) if act is not None else []

    def blueprints_for(self, product_typeid: int) -> List[BlueprintProduct]:
        return list(self._bp_by_product.get(product_typeid, []))

    def activity_time(self, blueprint_typeid: int, activity: int) -> Optional[float]:
        row = self._activity_times.get((blueprint_typeid, activity))
        return row.time if row is not None else None

    # Expose underlying maps if necessary (read-only by convention)
    @property
    def inv_types(self) -> Dict[int, TypeInfo]:
        return self._inv_types
