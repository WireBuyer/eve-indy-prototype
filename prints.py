from collections import defaultdict

from model import BlueprintSettings, BomEntry, BomResult


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def fmt(quantity: float) -> str:
    return f"{int(quantity):,}" if float(quantity).is_integer() else f"{quantity:,.3f}"


def format_runs(runs: float | None) -> str:
    return "auto" if runs is None else fmt(runs)


def format_job_cell(material_efficiency: int, time_efficiency: int, runs: float | None, prints: int) -> str:
    return (
        f"ME {material_efficiency} | TE {time_efficiency} | "
        f"runs {format_runs(runs)} | prints {prints}"
    )


def build_qty_cell(entry: BomEntry) -> str:
    suffix = f" [{entry.tag}]" if entry.tag else ""
    return f"qty {fmt(entry.quantity)}{suffix}"


def print_table_rows(rows: list[tuple[str, str, str, str]]) -> None:
    if not rows:
        print("  (none)")
        return

    name_width = max(len(name) for name, _, _, _ in rows)
    show_detail = any(detail for _, detail, _, _ in rows)
    show_qty = any(qty for _, _, qty, _ in rows)
    show_time = any(time_cell for _, _, _, time_cell in rows)

    detail_width = max((len(detail) for _, detail, _, _ in rows), default=0)
    qty_width = max((len(qty) for _, _, qty, _ in rows), default=0)

    for name, detail, qty, time_cell in rows:
        parts = [f"  {name:<{name_width}}"]
        if show_detail:
            parts.append(f"{detail:<{detail_width}}")
        if show_qty:
            parts.append(f"{qty:<{qty_width}}")
        if show_time:
            parts.append(time_cell)
        print(" | ".join(parts))


def print_blueprint_settings(result: BomResult) -> None:
    print("\nBlueprints in tree:")

    blueprints_by_depth = defaultdict(list)
    for entry in result.rows:
        if not entry.is_built:
            continue
        blueprints_by_depth[entry.depth].append(entry)

    for depth in sorted(blueprints_by_depth):
        print(f"\nDepth {depth}:")
        rows: list[tuple[str, str, str, str]] = []
        for entry in sorted(blueprints_by_depth[depth], key=lambda item: item.blueprint_name):
            rows.append(
                (
                    entry.blueprint_name,
                    f"output {fmt(entry.output_quantity)}",
                    f"time {format_duration(entry.total_time_seconds)}",
                    format_job_cell(
                        entry.material_efficiency,
                        entry.time_efficiency,
                        entry.runs,
                        entry.prints,
                    ),
                )
            )
        print_table_rows(rows)


def entry_detail_cell(entry: BomEntry) -> str:
    if not entry.is_built:
        return ""

    return format_job_cell(
        entry.material_efficiency,
        entry.time_efficiency,
        entry.runs,
        entry.prints,
    )


def print_depth_summary(result: BomResult) -> None:
    print("\nDepth 0:")
    root_rows: list[tuple[str, str, str, str]] = []
    for root in result.roots:
        root_rows.append(
            (
                root.name,
                f"output {fmt(root.output_quantity)}",
                f"time {format_duration(root.total_time_seconds)}",
                entry_detail_cell(root),
            )
        )
    print_table_rows(root_rows)

    max_depth = max(result.depth_layers.keys()) if result.depth_layers else 0
    for depth in range(1, max_depth + 1):
        entries = result.depth_layers.get(depth, [])
        if not entries:
            continue

        print(f"\nDepth {depth}:")
        rows: list[tuple[str, str, str, str]] = []
        for entry in entries:
            rows.append(
                (
                    entry.name,
                    build_qty_cell(entry),
                    f"time {format_duration(entry.total_time_seconds)}" if entry.total_time_seconds else "",
                    entry_detail_cell(entry),
                )
            )
        print_table_rows(rows)


def print_shopping_list(shopping_list: list[dict], title: str = "Shopping list") -> list[dict]:
    print(f"\n{title}:")
    if not shopping_list:
        print("  (none)")
        return shopping_list

    name_width = max(len(material["name"]) for material in shopping_list)
    for material in shopping_list:
        print(f"  {material['name']:<{name_width}} {fmt(material['quantity'])}")
    return shopping_list


def print_top_level_blueprints(idx, blueprints: dict[int, BlueprintSettings]) -> None:
    print("Top-level blueprints:")
    rows: list[tuple[str, str, str, str]] = []
    for blueprint in blueprints.values():
        rows.append(
            (
                blueprint.name,
                f"typeID {blueprint.blueprint_type_id}",
                "",
                format_job_cell(
                    blueprint.material_efficiency,
                    blueprint.time_efficiency,
                    blueprint.runs,
                    blueprint.prints,
                ),
            )
        )
    print_table_rows(rows)


def print_blueprint_updates(blueprint_updates: dict[int, BlueprintSettings]) -> None:
    if not blueprint_updates:
        return

    print("\nApplied blueprint overrides:")
    rows: list[tuple[str, str, str, str]] = []
    for blueprint in sorted(blueprint_updates.values(), key=lambda entry: entry.name):
        rows.append(
            (
                blueprint.name,
                "",
                "",
                format_job_cell(
                    blueprint.material_efficiency,
                    blueprint.time_efficiency,
                    blueprint.runs,
                    blueprint.prints,
                ),
            )
        )
    print_table_rows(rows)


def print_buy_components(idx, buy_component_type_ids: set[int]) -> None:
    if not buy_component_type_ids:
        return

    print("\nBuy decisions:")
    rows = [(idx.type_name(type_id), "", "[BUY]", "") for type_id in sorted(buy_component_type_ids)]
    print_table_rows(rows)
