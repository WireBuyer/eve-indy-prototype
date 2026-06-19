from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RigMode(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"


class RigTier(str, Enum):
    T1 = "t1"
    T2 = "t2"
    THUKKER = "thukker"


class BonusType(str, Enum):
    MATERIAL = "material"
    TIME = "time"
    JOB_COST = "job_cost"


@dataclass
class StructureConfig:
    config_id: str
    name: str
    structure: str
    security: str
    rig_mode: RigMode = RigMode.SIMPLE
    me: RigTier | None = None
    te: RigTier | None = None
    job_cost: RigTier | None = None
    rigs: list[tuple[str, int, RigTier]] = field(default_factory=list)
    system_id: int | None = None
