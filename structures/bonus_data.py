from __future__ import annotations

from model import MANUFACTURING_ACTIVITY, REACTION_ACTIVITY

from .models import BonusType, RigTier


RIG_TIER_BY_META_GROUP = {
    54: RigTier.T1,
    53: RigTier.T2,
    52: RigTier.THUKKER,
}

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
