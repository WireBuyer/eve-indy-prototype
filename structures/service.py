from __future__ import annotations

from build_models import ProductionRecipe
from industry_index import IndustryIndex

from .bonus_data import (
    ACTIVITY_KEYS,
    CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID,
    SCIENCE_JOB_COST_RIG_REDUCTION,
    SCIENCE_JOB_COST_RIGS_BY_ACTIVITY,
    SCIENCE_JOB_COST_SECURITY_MULTIPLIER,
    SIMPLE_RIG_REDUCTION,
    SIMPLE_SECURITY_MULTIPLIER,
    STRUCTURE_MODIFIERS,
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
        modifier = self._structure_modifier(structureConfig, activity_id, BonusType.MATERIAL)
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
        modifier = self._structure_modifier(structureConfig, activity_id, BonusType.TIME)
        if structureConfig.rig_mode == RigMode.SIMPLE:
            return modifier * self._simple_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.TIME, structureConfig.te
            )
        if structureConfig.rig_mode == RigMode.ADVANCED:
            return modifier * self._advanced_rig_modifier(
                structureConfig, recipe, activity_id, BonusType.TIME
            )
        raise ValueError(f"Unknown rig mode for {structureConfig.name}: {structureConfig.rig_mode}")

    def job_cost_modifier(self, structureConfig: StructureConfig | None, activity_id: int) -> float:
        if structureConfig is None:
            return 1.0

        activity_key = ACTIVITY_KEYS.get(activity_id)
        if activity_key is None:
            return 1.0

        modifier = self._structure_modifier(structureConfig, activity_key, BonusType.JOB_COST)
        if structureConfig.rig_mode == RigMode.SIMPLE:
            return modifier * self._simple_job_cost_rig_modifier(structureConfig, activity_key)
        if structureConfig.rig_mode == RigMode.ADVANCED:
            return modifier * self._advanced_job_cost_rig_modifier(structureConfig, activity_key)
        raise ValueError(f"Unknown rig mode for {structureConfig.name}: {structureConfig.rig_mode}")

    def _structure_modifier(
        self,
        structureConfig: StructureConfig,
        activity_key: str | None,
        bonus_type: BonusType,
    ) -> float:
        if activity_key is None:
            return 1.0
        return STRUCTURE_MODIFIERS.get(structureConfig.structure, {}).get(activity_key, {}).get(bonus_type, 1.0)

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

    def _simple_job_cost_rig_modifier(
        self,
        config: StructureConfig,
        activity_key: str,
    ) -> float:
        return self._job_cost_rig_modifier(config.security, activity_key, config.job_cost)

    def _advanced_job_cost_rig_modifier(
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
            modifier *= self._job_cost_rig_modifier(config.security, activity_key, configured_tier)
        return modifier

    def _job_cost_rig_modifier(
        self,
        security: str,
        activity_key: str,
        tier: RigTier | None,
    ) -> float:
        if tier is None or activity_key not in SCIENCE_JOB_COST_RIGS_BY_ACTIVITY:
            return 1.0

        reduction = SCIENCE_JOB_COST_RIG_REDUCTION.get(tier)
        multiplier = SCIENCE_JOB_COST_SECURITY_MULTIPLIER.get(tier, {}).get(security)
        if reduction is None or multiplier is None:
            return 1.0
        return 1.0 - (reduction * multiplier)
