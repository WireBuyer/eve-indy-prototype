from __future__ import annotations

from dataclasses import dataclass


MANUFACTURING_ACTIVITY = 1
REACTION_ACTIVITY = 11
PRODUCTION_ACTIVITIES = (MANUFACTURING_ACTIVITY, REACTION_ACTIVITY)


# --- models for the db tables ---
@dataclass(frozen=True)
class TypeInfo:
    type_id: int
    name: str
    volume: float
    icon_id: int | None
    group_id: int | None
    market_group_id: int | None


@dataclass(frozen=True)
class BlueprintProduct:
    type_id: int
    activity: int
    product_typeid: int
    quantity: float


@dataclass(frozen=True)
class MaterialRow:
    type_id: int
    activity: int
    material_typeid: int
    quantity: float


@dataclass(frozen=True)
class BlueprintActivityTime:
    type_id: int
    activity: int
    time: float


@dataclass(frozen=True)
class RigModifierSource:
    rig_type_id: int
    activity_key: str
    bonus_type: str
    dogma_attribute_id: int
    filter_id: int | None


@dataclass(frozen=True)
class RigAffectedProductGroup:
    rig_type_id: int
    activity_key: str
    bonus_type: str
    product_group_id: int
    filter_id: int | None
