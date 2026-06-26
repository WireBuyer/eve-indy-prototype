from __future__ import annotations

from build_models import ProductionRecipe
from industry_index import IndustryIndex

from .bonus_data import (
    ACTIVITY_KEYS,
    CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID,
    RIG_REDUCTION,
    RIG_SECURITY_MULTIPLIER,
    SCIENCE_JOB_COST_RIG_REDUCTION,
    SCIENCE_JOB_COST_RIGS_BY_ACTIVITY,
    SCIENCE_JOB_COST_SECURITY_MULTIPLIER,
    STRUCTURE_MODIFIERS,
)
from .models import BonusType, RigTier, StructureConfig


class StructureBonusService:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def material_modifier(self, structureConfig: StructureConfig | None, recipe: ProductionRecipe) -> float:
        # case for no structure setup/station
        if structureConfig is None:
            return 1.0

        activity_key = ACTIVITY_KEYS.get(recipe.activity)
        return self._structure_modifier(
            structureConfig, activity_key, BonusType.MATERIAL
        ) * self._rig_modifier(structureConfig, recipe, activity_key, BonusType.MATERIAL)

    def time_modifier(self, structureConfig: StructureConfig | None, recipe: ProductionRecipe) -> float:
        if structureConfig is None:
            return 1.0

        activity_key = ACTIVITY_KEYS.get(recipe.activity)
        return self._structure_modifier(
            structureConfig, activity_key, BonusType.TIME
        ) * self._rig_modifier(structureConfig, recipe, activity_key, BonusType.TIME)

    def job_cost_modifier(self, structureConfig: StructureConfig | None, activity_id: int) -> float:
        if structureConfig is None:
            return 1.0

        activity_key = ACTIVITY_KEYS.get(activity_id)
        if activity_key is None:
            return 1.0

        return self._structure_modifier(
            structureConfig, activity_key, BonusType.JOB_COST
        ) * self._science_job_cost_rig_modifier(structureConfig, activity_key)

    def _structure_modifier(
        self,
        structureConfig: StructureConfig,
        activity_key: str | None,
        bonus_type: BonusType,
    ) -> float:
        if activity_key is None:
            return 1.0
        return STRUCTURE_MODIFIERS.get(structureConfig.structure, {}).get(activity_key, {}).get(bonus_type, 1.0)

    def _rig_modifier(
        self,
        config: StructureConfig,
        recipe: ProductionRecipe,
        activity_key: str | None,
        bonus_type: BonusType,
    ) -> float:
        if activity_key is None:
            return 1.0

        modifier = 1.0
        for _rig_name, rig_type_id, tier in config.rigs:
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
                reduction = RIG_REDUCTION.get(activity_key, {}).get(bonus_type, {}).get(tier)
            multiplier = RIG_SECURITY_MULTIPLIER.get(activity_key, {}).get(tier, {}).get(config.security)
            if reduction is None or multiplier is None:
                continue

            modifier *= 1.0 - (reduction * multiplier)
        return modifier

    def _science_job_cost_rig_modifier(
        self,
        config: StructureConfig,
        activity_key: str,
    ) -> float:
        modifier = 1.0
        rig_tiers = SCIENCE_JOB_COST_RIGS_BY_ACTIVITY.get(activity_key, {})
        for _rig_name, rig_type_id, _tier in config.rigs:
            configured_tier = rig_tiers.get(rig_type_id)
            if configured_tier is None:
                continue
            modifier *= self._job_cost_rig_modifier(config.security, configured_tier)
        return modifier

    def _job_cost_rig_modifier(
        self,
        security: str,
        tier: RigTier | None,
    ) -> float:
        if tier is None:
            return 1.0

        reduction = SCIENCE_JOB_COST_RIG_REDUCTION.get(tier)
        multiplier = SCIENCE_JOB_COST_SECURITY_MULTIPLIER.get(tier, {}).get(security)
        if reduction is None or multiplier is None:
            return 1.0
        return 1.0 - (reduction * multiplier)
