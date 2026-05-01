from collections import defaultdict

from model import BlueprintSettings, BomAggregate, BomSnapshot


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


def build_qty_cell(quantity: float, is_base_material: bool = False, is_bought: bool = False) -> str:
    tags = []
    if is_base_material:
        tags.append("[BASE]")
    if is_bought:
        tags.append("[BUY]")
    suffix = f" {' '.join(tags)}" if tags else ""
    return f"qty {fmt(quantity)}{suffix}"


def is_bought(snapshot: BomSnapshot, name: str) -> bool:
    return name in snapshot.request.buy_components


def is_base_material(snapshot: BomSnapshot, aggregate: BomAggregate) -> bool:
    return aggregate.production is None and not is_bought(snapshot, aggregate.name)


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


def print_blueprint_settings(snapshot: BomSnapshot) -> None:
    print("\nBlueprints in tree:")
    usage_by_production = {}
    for row in snapshot.rows:
        if row.production is None:
            continue

        usage = usage_by_production.get(row.production)
        if usage is None:
            usage_by_production[row.production] = {
                "min_depth": row.depth,
                "total_output": row.planned_output_quantity,
                "total_time": row.total_time_seconds,
            }
        else:
            usage["min_depth"] = min(usage["min_depth"], row.depth)
            usage["total_output"] += row.planned_output_quantity
            usage["total_time"] += row.total_time_seconds

    blueprints_by_depth = defaultdict(list)
    for production, usage in usage_by_production.items():
        blueprints_by_depth[usage["min_depth"]].append((production, usage))

    for depth in sorted(blueprints_by_depth):
        print(f"\nDepth {depth}:")
        rows: list[tuple[str, str, str, str]] = []
        for production, usage in sorted(blueprints_by_depth[depth], key=lambda entry: entry[0].blueprint_name):
            settings = production.settings
            rows.append(
                (
                    production.blueprint_name,
                    f"output {fmt(usage['total_output'])}",
                    f"time {format_duration(usage['total_time'])}",
                    format_job_cell(
                        settings.material_efficiency,
                        settings.time_efficiency,
                        settings.runs,
                        settings.prints,
                    ),
                )
            )
        print_table_rows(rows)


def aggregate_detail_cell(snapshot: BomSnapshot, aggregate: BomAggregate) -> str:
    if is_bought(snapshot, aggregate.name) or aggregate.blueprint_settings is None:
        return ""
    if aggregate.mixed_blueprint_settings:
        return "config mixed"

    settings = aggregate.blueprint_settings
    return format_job_cell(
        settings.material_efficiency,
        settings.time_efficiency,
        settings.runs,
        settings.prints,
    )


def print_depth_summary(snapshot: BomSnapshot) -> None:
    print("\nDepth 0:")
    root_rows: list[tuple[str, str, str, str]] = []
    for root in snapshot.roots:
        root_rows.append(
            (
                root.name,
                f"output {fmt(root.planned_output_quantity)}",
                f"time {format_duration(root.total_time_seconds)}",
                format_job_cell(root.material_efficiency, root.time_efficiency, root.runs, root.prints),
            )
        )
    print_table_rows(root_rows)

    layers = defaultdict(list)
    for type_id, depth in snapshot.depths.items():
        layers[depth].append(type_id)

    max_depth = max(layers.keys()) if layers else 0
    for depth in range(1, max_depth + 1):
        items = layers.get(depth, [])
        if not items:
            continue

        print(f"\nDepth {depth}:")
        rows: list[tuple[str, str, str, str]] = []
        for type_id in sorted(items):
            aggregate = snapshot.aggregates[type_id]
            rows.append(
                (
                    aggregate.name,
                    build_qty_cell(
                        aggregate.quantity,
                        is_base_material=is_base_material(snapshot, aggregate),
                        is_bought=is_bought(snapshot, aggregate.name),
                    ),
                    f"time {format_duration(aggregate.total_time_seconds)}" if aggregate.total_time_seconds else "",
                    aggregate_detail_cell(snapshot, aggregate),
                )
            )
        print_table_rows(rows)


def print_top_level_blueprints(idx, blueprints: list[BlueprintSettings]) -> None:
    print("Top-level blueprints:")
    rows: list[tuple[str, str, str, str]] = []
    for blueprint in blueprints:
        blueprint_typeid = idx.find_type_id_by_name(blueprint.name)
        label = blueprint_typeid if blueprint_typeid is not None else "unknown"
        rows.append(
            (
                blueprint.name,
                f"typeID {label}",
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


def print_blueprint_updates(blueprint_updates: dict[str, BlueprintSettings]) -> None:
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


def print_buy_components(buy_components: set[str]) -> None:
    if not buy_components:
        return

    print("\nBuy decisions:")
    rows = [(name, "", "[BUY]", "") for name in sorted(buy_components)]
    print_table_rows(rows)

