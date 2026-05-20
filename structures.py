from __future__ import annotations

from dataclasses import dataclass, field

from build_models import ProductionRecipe
from industry_index import IndustryIndex
from model import MANUFACTURING_ACTIVITY, REACTION_ACTIVITY


RIG_MODE_SIMPLE = "simple"
RIG_MODE_ADVANCED = "advanced"

BONUS_MATERIAL = "material"
BONUS_TIME = "time"

ACTIVITY_KEYS = {
    MANUFACTURING_ACTIVITY: "manufacturing",
    REACTION_ACTIVITY: "reaction",
}

MANUFACTURING_MATERIAL_BONUS_ATTRIBUTE = 2594
MANUFACTURING_TIME_BONUS_ATTRIBUTE = 2593
REACTION_MATERIAL_BONUS_ATTRIBUTE = 2714
REACTION_TIME_BONUS_ATTRIBUTE = 2713

SECURITY_HIGH_BONUS_ATTRIBUTE = 2355
SECURITY_LOW_BONUS_ATTRIBUTE = 2356
SECURITY_NULL_BONUS_ATTRIBUTE = 2357

SECURITY_ATTRIBUTE_BY_KEY = {
    "highsec": SECURITY_HIGH_BONUS_ATTRIBUTE,
    "lowsec": SECURITY_LOW_BONUS_ATTRIBUTE,
    "nullsec": SECURITY_NULL_BONUS_ATTRIBUTE,
    "wormhole": SECURITY_NULL_BONUS_ATTRIBUTE,
}

SECURITY_ALIASES = {
    "high": "highsec",
    "highsec": "highsec",
    "low": "lowsec",
    "lowsec": "lowsec",
    "null": "nullsec",
    "nullsec": "nullsec",
    "wormhole": "wormhole",
    "wh": "wormhole",
}

HULL_MODIFIERS = {
    "Raitaru": {
        "manufacturing": {"material": 0.99, "time": 0.85},
    },
    "Azbel": {
        "manufacturing": {"material": 0.99, "time": 0.80},
    },
    "Sotiyo": {
        "manufacturing": {"material": 0.99, "time": 0.70},
    },
    "Athanor": {
        "reaction": {"material": 1.0, "time": 1.0},
    },
    "Tatara": {
        "reaction": {"material": 1.0, "time": 0.75},
    },
}

SIMPLE_RIG_REDUCTION = {
    "manufacturing": {
        "material": {"t1": 0.02, "t2": 0.024},
        "time": {"t1": 0.20, "t2": 0.24},
    },
    "reaction": {
        "material": {"t1": 0.02, "t2": 0.024},
        "time": {"t1": 0.20, "t2": 0.24},
    },
}

SIMPLE_SECURITY_MULTIPLIER = {
    "manufacturing": {
        "highsec": 1.0,
        "lowsec": 1.9,
        "nullsec": 2.1,
        "wormhole": 2.1,
    },
    "reaction": {
        "highsec": 0.0,
        "lowsec": 1.0,
        "nullsec": 1.1,
        "wormhole": 1.1,
    },
}

BONUS_ATTRIBUTE_BY_ACTIVITY = {
    ("manufacturing", "material"): MANUFACTURING_MATERIAL_BONUS_ATTRIBUTE,
    ("manufacturing", "time"): MANUFACTURING_TIME_BONUS_ATTRIBUTE,
    ("reaction", "material"): REACTION_MATERIAL_BONUS_ATTRIBUTE,
    ("reaction", "time"): REACTION_TIME_BONUS_ATTRIBUTE,
}


@dataclass
class StructureConfig:
    config_id: str
    name: str
    structure: str
    security: str
    rig_mode: str = RIG_MODE_SIMPLE
    manufacturing_me: str | None = None
    manufacturing_te: str | None = None
    reaction_me: str | None = None
    reaction_te: str | None = None
    rigs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.config_id = str(self.config_id)
        self.name = str(self.name)
        self.structure = str(self.structure)
        self.security = _normalize_security(self.security)
        self.rig_mode = str(self.rig_mode).lower()
        self.manufacturing_me = _normalize_tier(self.manufacturing_me)
        self.manufacturing_te = _normalize_tier(self.manufacturing_te)
        self.reaction_me = _normalize_tier(self.reaction_me)
        self.reaction_te = _normalize_tier(self.reaction_te)
        self.rigs = list(self.rigs or [])


class StructureBonusService:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx
        self._rig_type_ids_by_name: dict[str, int] = {}

    def material_modifier(self, config: StructureConfig | None, recipe: ProductionRecipe) -> float:
        return self._modifier(config, recipe, BONUS_MATERIAL)

    def time_modifier(self, config: StructureConfig | None, recipe: ProductionRecipe) -> float:
        return self._modifier(config, recipe, BONUS_TIME)

    def _modifier(self, config: StructureConfig | None, recipe: ProductionRecipe, bonus_type: str) -> float:
        if config is None:
            return 1.0

        activity_key = ACTIVITY_KEYS.get(recipe.activity)
        if activity_key is None:
            return 1.0

        modifier = _hull_modifier(config, activity_key, bonus_type)
        if config.rig_mode == RIG_MODE_SIMPLE:
            return modifier * self._simple_rig_modifier(config, recipe, activity_key, bonus_type)
        if config.rig_mode == RIG_MODE_ADVANCED:
            return modifier * self._advanced_rig_modifier(config, recipe, activity_key, bonus_type)
        raise ValueError(f"Unknown rig mode for {config.name}: {config.rig_mode}")

    def _simple_rig_modifier(
        self,
        config: StructureConfig,
        recipe: ProductionRecipe,
        activity_key: str,
        bonus_type: str,
    ) -> float:
        tier = _simple_tier(config, activity_key, bonus_type)
        if tier is None:
            return 1.0
        if not self.idx.has_rig_for_product_group(activity_key, bonus_type, recipe.product_group_id):
            return 1.0

        reduction = SIMPLE_RIG_REDUCTION[activity_key][bonus_type][tier]
        multiplier = SIMPLE_SECURITY_MULTIPLIER[activity_key][config.security]
        return 1.0 - (reduction * multiplier)

    def _advanced_rig_modifier(
        self,
        config: StructureConfig,
        recipe: ProductionRecipe,
        activity_key: str,
        bonus_type: str,
    ) -> float:
        modifier = 1.0
        for rig_name in config.rigs:
            rig_type_id = self._rig_type_id(rig_name)
            if not self.idx.rig_modifier_sources(rig_type_id, activity_key, bonus_type):
                continue
            affected_groups = self.idx.rig_affected_product_groups(rig_type_id, activity_key, bonus_type)
            if recipe.product_group_id not in affected_groups:
                continue

            bonus_attribute_id = BONUS_ATTRIBUTE_BY_ACTIVITY[(activity_key, bonus_type)]
            bonus_percent = self.idx.rig_attribute_value(rig_type_id, bonus_attribute_id)
            if bonus_percent is None:
                continue

            multiplier = self._advanced_security_multiplier(config, rig_type_id)
            modifier *= 1.0 + ((bonus_percent * multiplier) / 100.0)
        return modifier

    def _advanced_security_multiplier(self, config: StructureConfig, rig_type_id: int) -> float:
        attribute_id = SECURITY_ATTRIBUTE_BY_KEY[config.security]
        value = self.idx.rig_attribute_value(rig_type_id, attribute_id)
        if value is None:
            return 0.0
        return value

    def _rig_type_id(self, rig_name: str) -> int:
        if rig_name not in self._rig_type_ids_by_name:
            type_id = self.idx.find_type_id_by_name(rig_name)
            if type_id is None:
                raise ValueError(f"Rig not found: {rig_name}")
            self._rig_type_ids_by_name[rig_name] = type_id
        return self._rig_type_ids_by_name[rig_name]


def structure_catalog(configs: list[StructureConfig]) -> dict[str, StructureConfig]:
    catalog: dict[str, StructureConfig] = {}
    for config in configs:
        if config.config_id in catalog:
            raise ValueError(f"Structure config id is already used: {config.config_id}")
        catalog[config.config_id] = config
    return catalog


def _hull_modifier(config: StructureConfig, activity_key: str, bonus_type: str) -> float:
    return HULL_MODIFIERS.get(config.structure, {}).get(activity_key, {}).get(bonus_type, 1.0)


def _simple_tier(config: StructureConfig, activity_key: str, bonus_type: str) -> str | None:
    if activity_key == "manufacturing" and bonus_type == "material":
        return config.manufacturing_me
    if activity_key == "manufacturing" and bonus_type == "time":
        return config.manufacturing_te
    if activity_key == "reaction" and bonus_type == "material":
        return config.reaction_me
    if activity_key == "reaction" and bonus_type == "time":
        return config.reaction_te
    return None


def _normalize_security(value: str) -> str:
    key = str(value).lower()
    if key not in SECURITY_ALIASES:
        raise ValueError(f"Unknown structure security: {value}")
    return SECURITY_ALIASES[key]


def _normalize_tier(value: str | None) -> str | None:
    if value is None:
        return None
    key = str(value).lower()
    if key in {"", "none", "no rig"}:
        return None
    if key not in {"t1", "t2"}:
        raise ValueError(f"Unknown rig tier: {value}")
    return key
