from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    rigs: list[tuple[str, int, RigTier]] = field(default_factory=list)
    system_id: int | None = None
