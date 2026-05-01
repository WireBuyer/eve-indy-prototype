from __future__ import annotations

from dataclasses import dataclass

from bom_planner import BomPlanner
from model import BlueprintSettings, BomSnapshot, PlanConfig


@dataclass(frozen=True)
class BlueprintSettingsUpdate:
    material_efficiency: int | None = None
    time_efficiency: int | None = None
    runs: float | None = None
    clear_runs: bool = False
    prints: int | None = None


@dataclass(frozen=True)
class PlanEditResult:
    plan: PlanConfig
    snapshot: BomSnapshot


class PlanEditor:
    def __init__(self, planner: BomPlanner):
        self.planner = planner

    def preview(self, plan: PlanConfig) -> BomSnapshot:
        return self.planner.build_snapshot(plan)

    def add_top_level_blueprint(self, plan: PlanConfig, settings: BlueprintSettings) -> PlanEditResult:
        updated_plan = _copy_plan(
            plan,
            top_level_blueprints=[*plan.top_level_blueprints, settings],
        )
        return self._validated(updated_plan)

    def remove_top_level_blueprint(self, plan: PlanConfig, index: int) -> PlanEditResult:
        top_level_blueprints = list(plan.top_level_blueprints)
        if index < 0 or index >= len(top_level_blueprints):
            raise IndexError("top-level blueprint index is out of range")

        del top_level_blueprints[index]
        return self._validated(_copy_plan(plan, top_level_blueprints=top_level_blueprints))

    def set_buy_component(self, plan: PlanConfig, component_name: str, should_buy: bool) -> PlanEditResult:
        buy_components = set(plan.buy_components)
        if should_buy:
            buy_components.add(component_name)
        else:
            buy_components.discard(component_name)
        return self._validated(_copy_plan(plan, buy_components=buy_components))

    def update_top_level_blueprints(
        self,
        plan: PlanConfig,
        indexes: list[int],
        update: BlueprintSettingsUpdate,
    ) -> PlanEditResult:
        top_level_blueprints = list(plan.top_level_blueprints)
        for index in indexes:
            if index < 0 or index >= len(top_level_blueprints):
                raise IndexError("top-level blueprint index is out of range")
            top_level_blueprints[index] = _apply_update(top_level_blueprints[index], update, allow_runs=True)

        return self._validated(_copy_plan(plan, top_level_blueprints=top_level_blueprints))

    def update_blueprint_overrides(
        self,
        plan: PlanConfig,
        blueprint_names: list[str],
        update: BlueprintSettingsUpdate,
    ) -> PlanEditResult:
        blueprint_settings = dict(plan.blueprint_settings)
        for blueprint_name in blueprint_names:
            current = blueprint_settings.get(blueprint_name, BlueprintSettings(blueprint_name))
            blueprint_settings[blueprint_name] = _apply_update(current, update, allow_runs=False)

        return self._validated(_copy_plan(plan, blueprint_settings=blueprint_settings))

    def update_depth_blueprints(
        self,
        plan: PlanConfig,
        depth: int,
        blueprint_names: list[str],
        update: BlueprintSettingsUpdate,
    ) -> PlanEditResult:
        snapshot = self.preview(plan)
        available_names = {
            row.production.blueprint_name
            for row in snapshot.rows
            if row.depth == depth and row.production is not None
        }
        missing_names = set(blueprint_names) - available_names
        if missing_names:
            raise ValueError(f"Blueprints are not buildable at depth {depth}: {', '.join(sorted(missing_names))}")

        if depth == 0:
            indexes = [
                index
                for index, settings in enumerate(plan.top_level_blueprints)
                if settings.name in blueprint_names
            ]
            return self.update_top_level_blueprints(plan, indexes, update)

        return self.update_blueprint_overrides(plan, blueprint_names, update)

    def _validated(self, plan: PlanConfig) -> PlanEditResult:
        snapshot = self.preview(plan)
        return PlanEditResult(plan=plan, snapshot=snapshot)


def _copy_plan(
    plan: PlanConfig,
    top_level_blueprints: list[BlueprintSettings] | None = None,
    blueprint_settings: dict[str, BlueprintSettings] | None = None,
    buy_components: set[str] | None = None,
) -> PlanConfig:
    return PlanConfig(
        top_level_blueprints=top_level_blueprints if top_level_blueprints is not None else plan.top_level_blueprints,
        blueprint_settings=blueprint_settings if blueprint_settings is not None else plan.blueprint_settings,
        buy_components=buy_components if buy_components is not None else plan.buy_components,
    )


def _apply_update(
    settings: BlueprintSettings,
    update: BlueprintSettingsUpdate,
    allow_runs: bool,
) -> BlueprintSettings:
    if not allow_runs and (update.runs is not None or update.clear_runs):
        raise ValueError("runs can only be updated for top-level blueprints")

    runs = settings.runs
    if update.clear_runs:
        runs = None
    elif update.runs is not None:
        runs = update.runs

    return BlueprintSettings(
        name=settings.name,
        material_efficiency=(
            settings.material_efficiency
            if update.material_efficiency is None
            else update.material_efficiency
        ),
        time_efficiency=settings.time_efficiency if update.time_efficiency is None else update.time_efficiency,
        runs=runs,
        prints=settings.prints if update.prints is None else update.prints,
    )
