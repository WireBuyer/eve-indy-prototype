from __future__ import annotations

from build_models import ProductionRecipe
from industry_index import IndustryIndex

from .bonus_data import (
    ACTIVITY_KEYS,
    CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID,
    HULL_MODIFIERS,
    SIMPLE_RIG_REDUCTION,
    SIMPLE_SECURITY_MULTIPLIER,
)
from .models import BonusType, RigMode, RigTier, StructureConfig


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
