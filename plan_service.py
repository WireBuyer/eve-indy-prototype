from __future__ import annotations

from build_models import BuildPlan, PrintSettings


def remove_root_prints(plan: BuildPlan, blueprint_type_ids: list[int]) -> None:
    missing_ids = set(blueprint_type_ids) - set(plan.root_prints)
    if missing_ids:
        raise KeyError(
            "Root prints are not selected: "
            f"{', '.join(str(type_id) for type_id in sorted(missing_ids))}"
        )

    for blueprint_type_id in blueprint_type_ids:
        del plan.root_prints[blueprint_type_id]


def set_buy_product(plan: BuildPlan, product_type_id: int, should_buy: bool) -> None:
    if should_buy:
        plan.buy_product_type_ids.add(product_type_id)
    else:
        plan.buy_product_type_ids.discard(product_type_id)


def update_root_prints(plan: BuildPlan, updates_by_id: dict[int, dict]) -> None:
    missing_ids = set(updates_by_id) - set(plan.root_prints)
    if missing_ids:
        raise KeyError(
            "Root prints are not selected: "
            f"{', '.join(str(type_id) for type_id in sorted(missing_ids))}"
        )

    for blueprint_type_id, update in updates_by_id.items():
        plan.root_prints[blueprint_type_id] = _apply_print_update(
            plan.root_prints[blueprint_type_id],
            update,
            allow_runs=True,
        )


def update_print_overrides(plan: BuildPlan, updates_by_id: dict[int, dict]) -> None:
    for blueprint_type_id, update in updates_by_id.items():
        current = plan.print_overrides.get(
            blueprint_type_id,
            PrintSettings(str(blueprint_type_id), blueprint_type_id=blueprint_type_id),
        )
        plan.print_overrides[blueprint_type_id] = _apply_print_update(current, update, allow_runs=False)


def update_prints(plan: BuildPlan, updates_by_id: dict[int, dict]) -> None:
    for blueprint_type_id, update in updates_by_id.items():
        if blueprint_type_id in plan.root_prints:
            plan.root_prints[blueprint_type_id] = _apply_print_update(
                plan.root_prints[blueprint_type_id],
                update,
                allow_runs=True,
            )
        else:
            current = plan.print_overrides.get(
                blueprint_type_id,
                PrintSettings(str(blueprint_type_id), blueprint_type_id=blueprint_type_id),
            )
            plan.print_overrides[blueprint_type_id] = _apply_print_update(current, update, allow_runs=False)


def _apply_print_update(
    settings: PrintSettings,
    update: dict,
    allow_runs: bool,
) -> PrintSettings:
    if not allow_runs and "runs" in update:
        raise ValueError("runs can only be updated for root prints")

    return PrintSettings(
        name=settings.name,
        blueprint_type_id=settings.blueprint_type_id,
        material_efficiency=update.get("material_efficiency", settings.material_efficiency),
        time_efficiency=update.get("time_efficiency", settings.time_efficiency),
        runs=update.get("runs", settings.runs),
        prints=update.get("prints", settings.prints),
    )
