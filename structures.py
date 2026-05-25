from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from build_models import ProductionRecipe
from industry_index import IndustryIndex
from model import MANUFACTURING_ACTIVITY, REACTION_ACTIVITY


class RigMode(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"


class RigTier(str, Enum):
    T1 = "t1"
    T2 = "t2"
    THUKKER = "thukker"


RIG_TIER_BY_META_GROUP = {
    54: RigTier.T1,
    53: RigTier.T2,
    52: RigTier.THUKKER,
}


class BonusType(str, Enum):
    MATERIAL = "material"
    TIME = "time"


ACTIVITY_KEYS = {
    MANUFACTURING_ACTIVITY: "manufacturing",
    REACTION_ACTIVITY: "reaction",
}

# for thukker
CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID = 873

HULL_MODIFIERS = {
    "Raitaru": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.85},
    },
    "Azbel": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.80},
    },
    "Sotiyo": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.70},
    },
    "Athanor": {
        "reaction": {BonusType.MATERIAL: 1.0, BonusType.TIME: 1.0},
    },
    "Tatara": {
        "reaction": {BonusType.MATERIAL: 1.0, BonusType.TIME: 0.75},
    },
}

SIMPLE_RIG_REDUCTION = {
    "manufacturing": {
        BonusType.MATERIAL: {RigTier.T1: 0.02, RigTier.T2: 0.024, RigTier.THUKKER: 0.02},
        BonusType.TIME: {RigTier.T1: 0.20, RigTier.T2: 0.24, RigTier.THUKKER: 0.20},
    },
    "reaction": {
        BonusType.MATERIAL: {RigTier.T1: 0.02, RigTier.T2: 0.024},
        BonusType.TIME: {RigTier.T1: 0.20, RigTier.T2: 0.24},
    },
}

SIMPLE_SECURITY_MULTIPLIER = {
    "manufacturing": {
        RigTier.T1: {"highsec": 1.0, "lowsec": 1.9, "nullsec": 2.1, "wormhole": 2.1},
        RigTier.T2: {"highsec": 1.0, "lowsec": 1.9, "nullsec": 2.1, "wormhole": 2.1},
        RigTier.THUKKER: {"highsec": 0.1, "lowsec": 1.9, "nullsec": 0.1, "wormhole": 0.1},
    },
    "reaction": {
        RigTier.T1: {"highsec": 0.0, "lowsec": 1.0, "nullsec": 1.1, "wormhole": 1.1},
        RigTier.T2: {"highsec": 0.0, "lowsec": 1.0, "nullsec": 1.1, "wormhole": 1.1},
    },
}

@dataclass
class StructureConfig:
    config_id: str
    name: str
    structure: str
    security: str
    rig_mode: RigMode = RigMode.SIMPLE
    me: RigTier | None = None
    te: RigTier | None = None
    rigs: list[tuple[str, int, RigTier]] = field(default_factory=list)


class StructureBonusService:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def material_modifier(self, structureConfig: StructureConfig | None, recipe: ProductionRecipe) -> float:
        # case for no structure setup/station
        if structureConfig is None:
            return 1.0

        activity_id = ACTIVITY_KEYS[recipe.activity]
        # modifier = self._hull_modifier(structureConfig, activity_id, BonusType.MATERIAL)
        modifier = HULL_MODIFIERS.get(structureConfig.structure).get(activity_id).get(BonusType.MATERIAL)
        if structureConfig.rig_mode == RigMode.SIMPLE:
            return modifier * self._simple_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.MATERIAL, structureConfig.me
            )
        if structureConfig.rig_mode == RigMode.ADVANCED:
            return modifier * self._advanced_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.MATERIAL
            )
        raise ValueError(f"Unknown rig mode for {structureConfig.name}: {structureConfig.rig_mode}")

    def time_modifier(self, structureConfig: StructureConfig | None, recipe: ProductionRecipe) -> float:
        if structureConfig is None:
            return 1.0

        activity_id = ACTIVITY_KEYS.get(recipe.activity)
        modifier = HULL_MODIFIERS.get(structureConfig.structure).get(activity_id).get(BonusType.TIME)
        if structureConfig.rig_mode == RigMode.SIMPLE:
            return modifier * self._simple_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.TIME, structureConfig.te
            )
        if structureConfig.rig_mode == RigMode.ADVANCED:
            return modifier * self._advanced_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.TIME
            )
        raise ValueError(f"Unknown rig mode for {structureConfig.name}: {structureConfig.rig_mode}")

    def _simple_rig_modifier(
        self,
        config: StructureConfig,
        recipe: ProductionRecipe,
        activity_key: str,
        bonus_type: BonusType,
        tier: RigTier | None,
    ) -> float:
        if tier is None:
            return 1.0

        if (
            tier == RigTier.THUKKER 
            and bonus_type == BonusType.MATERIAL 
            and recipe.product_group_id == CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID
        ):
            reduction = 0.037
        else:
            reduction = SIMPLE_RIG_REDUCTION.get(activity_key, {}).get(bonus_type, {}).get(tier)
        
        multiplier = SIMPLE_SECURITY_MULTIPLIER.get(activity_key, {}).get(tier, {}).get(config.security)
        if reduction is None or multiplier is None:
            return 1.0
        return 1.0 - (reduction * multiplier)

    def _advanced_rig_modifier(
        self,
        config: StructureConfig,
        recipe: ProductionRecipe,
        activity_key: str,
        bonus_type: BonusType,
    ) -> float:
        modifier = 1.0
        for rig_name, rig_type_id, tier in config.rigs:
            affected_groups = self.idx.rig_groups.get((rig_type_id, activity_key, bonus_type.value), set())
            if recipe.product_group_id not in affected_groups:
                continue

            if (
                tier == RigTier.THUKKER
                and bonus_type == BonusType.MATERIAL
                and recipe.product_group_id == CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID
            ):
                reduction = 0.037
            else:
                reduction = SIMPLE_RIG_REDUCTION.get(activity_key, {}).get(bonus_type, {}).get(tier)
            multiplier = SIMPLE_SECURITY_MULTIPLIER.get(activity_key, {}).get(tier, {}).get(config.security)
            if reduction is None or multiplier is None:
                continue

            modifier *= 1.0 - (reduction * multiplier)
        return modifier
    
def structure_catalog(configs: list[StructureConfig]) -> dict[str, StructureConfig]:
    return {config.config_id: config for config in configs}
