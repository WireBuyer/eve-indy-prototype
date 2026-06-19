from __future__ import annotations

from model import (
    COPYING_ACTIVITY,
    INVENTION_ACTIVITY,
    MANUFACTURING_ACTIVITY,
    MATERIAL_RESEARCH_ACTIVITY,
    REACTION_ACTIVITY,
    TIME_RESEARCH_ACTIVITY,
)

from .models import BonusType, RigTier


RIG_TIER_BY_META_GROUP = {
    54: RigTier.T1,
    53: RigTier.T2,
    52: RigTier.THUKKER,
}

ACTIVITY_KEYS = {
    MANUFACTURING_ACTIVITY: "manufacturing",
    TIME_RESEARCH_ACTIVITY: "researching_time_efficiency",
    MATERIAL_RESEARCH_ACTIVITY: "researching_material_efficiency",
    COPYING_ACTIVITY: "copying",
    INVENTION_ACTIVITY: "invention",
    REACTION_ACTIVITY: "reaction",
}

# for thukker
CAPITAL_CONSTRUCTION_COMPONENT_GROUP_ID = 873

STRUCTURE_MODIFIERS = {
    "Raitaru": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.85, BonusType.JOB_COST: 0.97},
    },
    "Azbel": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.80, BonusType.JOB_COST: 0.96},
    },
    "Sotiyo": {
        "manufacturing": {BonusType.MATERIAL: 0.99, BonusType.TIME: 0.70, BonusType.JOB_COST: 0.95},
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

SCIENCE_JOB_COST_RIG_REDUCTION = {
    RigTier.T1: 0.10,
    RigTier.T2: 0.12,
}

SCIENCE_JOB_COST_SECURITY_MULTIPLIER = {
    RigTier.T1: {"highsec": 1.0, "lowsec": 1.9, "nullsec": 2.1, "wormhole": 2.1},
    RigTier.T2: {"highsec": 1.0, "lowsec": 1.9, "nullsec": 2.1, "wormhole": 2.1},
}

SCIENCE_JOB_COST_RIGS_BY_ACTIVITY = {
    "researching_material_efficiency": {
        43885: RigTier.T1,
        43884: RigTier.T2,
    },
    "researching_time_efficiency": {
        43887: RigTier.T1,
        43886: RigTier.T2,
    },
    "copying": {
        43891: RigTier.T1,
        43890: RigTier.T2,
    },
    "invention": {
        43879: RigTier.T1,
        43878: RigTier.T2,
    },
}
