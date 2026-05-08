from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrintSettings:
    name: str
    blueprint_type_id: int
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: float | None = None
    prints: int = 1

    def __post_init__(self) -> None:
        if self.blueprint_type_id is None:
            raise ValueError(f"Blueprint type id is required for {self.name}.")

        object.__setattr__(self, "blueprint_type_id", int(self.blueprint_type_id))
        object.__setattr__(self, "material_efficiency", _clamp(self.material_efficiency, 0, 10))
        object.__setattr__(self, "time_efficiency", _clamp(self.time_efficiency, 0, 20))
        object.__setattr__(self, "prints", max(1, int(self.prints)))

        if self.runs is None:
            return

        runs = float(self.runs)
        if runs <= 0:
            raise ValueError("runs must be positive when provided")
        object.__setattr__(self, "runs", runs)


@dataclass
class BuildPlan:
    plan_id: str | None = None
    root_prints: dict[int, PrintSettings] = field(default_factory=dict)
    print_overrides: dict[int, PrintSettings] = field(default_factory=dict)
    buy_product_type_ids: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.root_prints = _copy_prints_by_id(self.root_prints, allow_runs=True)
        self.print_overrides = _copy_prints_by_id(self.print_overrides, allow_runs=False)
        self.buy_product_type_ids = {int(type_id) for type_id in (self.buy_product_type_ids or set())}


@dataclass(frozen=True)
class ProductionRecipe:
    blueprint_type_id: int
    blueprint_name: str
    activity: int
    product_type_id: int
    product_name: str
    output_per_run: float
    time_per_run: float
    product_group_id: int | None = None


@dataclass(frozen=True)
class BomItem:
    type_id: int
    name: str
    quantity: float
    depth: int
    group_id: int | None = None
    blueprint_type_id: int | None = None
    blueprint_name: str | None = None
    material_efficiency: int = 0
    time_efficiency: int = 0
    runs: float | None = None
    prints: int = 1
    output_quantity: float = 0.0
    total_time_seconds: float = 0.0


@dataclass(frozen=True)
class BuildTree:
    roots: list[BomItem]
    depths: dict[int, int]


@dataclass(frozen=True)
class BomResult:
    plan: BuildPlan
    roots: list[BomItem]
    items_by_product_id: dict[int, BomItem]
    buy_product_type_ids: set[int]
    use_estimate_math: bool = False


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _copy_prints_by_id(
    settings: dict[int, PrintSettings] | None,
    allow_runs: bool,
) -> dict[int, PrintSettings]:
    if settings is None:
        return {}

    by_id: dict[int, PrintSettings] = {}
    for blueprint_type_id, print_settings in settings.items():
        if blueprint_type_id != print_settings.blueprint_type_id:
            raise ValueError(f"Print settings key does not match {print_settings.name}.")
        if not allow_runs and print_settings.runs is not None:
            raise ValueError("runs can only be set for root prints")
        if print_settings.blueprint_type_id in by_id:
            raise ValueError(f"{print_settings.name} is already selected.")
        by_id[print_settings.blueprint_type_id] = print_settings
    return by_id
