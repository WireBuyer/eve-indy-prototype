from collections import defaultdict

from bom_planner import BomPlannerSession
from db_io import load_tables
from model import Blueprint, BomSnapshot


BLUEPRINT_NAME = Blueprint("Scorch Bomb Blueprint", 9, 0, 12, 1)
TOP_LEVEL_BLUEPRINTS = [
    # BLUEPRINT_NAME,
    # Blueprint("Raven Blueprint", 10, 0, 1, 1),
    Blueprint("Charon Blueprint", 10, 20, 1, 1),
]

# Example API-style updates. Add or remove blueprint rows here without rebuilding
# the whole request payload.
BLUEPRINT_ME_UPDATES = {
    # "Life Support Backup Unit Blueprint": Blueprint("Life Support Backup Unit Blueprint", 10, 20),
    # "Capital Jump Drive Blueprint": Blueprint("Capital Jump Drive Blueprint", 10, 20),
}


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


def print_blueprint_settings(snapshot: BomSnapshot) -> None:
    print("\nBlueprints in tree:")
    for usage in sorted(snapshot.used_blueprints.values(), key=lambda entry: entry.blueprint_option.product_name):
        blueprint = usage.configured_blueprint
        runs_label = "auto" if blueprint.runs is None else fmt(blueprint.runs)
        print(
            f"  - {usage.blueprint_option.product_name}: {usage.blueprint_option.name} "
            f"[activity {usage.blueprint_option.activity}, ME {blueprint.material_efficiency}, "
            f"TE {blueprint.time_efficiency}, runs {runs_label}, prints {blueprint.prints}] "
            f"output:{fmt(usage.total_planned_output_quantity)} "
            f"time:{format_duration(usage.total_time_seconds)}"
        )


def print_depth_summary(snapshot: BomSnapshot) -> None:
    print("\nDepth 0:")
    for root in snapshot.roots:
        blueprint_label = root.selected_blueprint.name if root.selected_blueprint is not None else root.name
        print(
            f"  - {blueprint_label} (product: {root.name}, ME {root.material_efficiency}, "
            f"TE {root.time_efficiency}, runs {fmt(root.runs)}, prints {root.prints}, "
            f"output {fmt(root.planned_output_quantity)}, time {format_duration(root.total_time_seconds)})"
        )

    layers = defaultdict(list)
    for type_id, depth in snapshot.depths.items():
        layers[depth].append(type_id)

    max_depth = max(layers.keys()) if layers else 0
    for depth in range(1, max_depth + 1):
        items = layers.get(depth, [])
        if not items:
            continue

        print(f"\nDepth {depth}:")
        for type_id in sorted(items):
            aggregate = snapshot.aggregates[type_id]
            blueprint = aggregate.selected_blueprint
            if blueprint is None:
                print(f"  - {aggregate.name} qty:{fmt(aggregate.quantity)}")
                continue

            config_label = "mixed"
            if not aggregate.mixed_blueprint_config and aggregate.configured_blueprint is not None:
                config = aggregate.configured_blueprint
                runs_label = "auto" if config.runs is None else fmt(config.runs)
                config_label = (
                    f"ME {config.material_efficiency}, TE {config.time_efficiency}, "
                    f"runs {runs_label}, prints {config.prints}"
                )

            print(
                f"  - {aggregate.name} (->{blueprint.name} #{blueprint.type_id}, {config_label}) "
                f"qty:{fmt(aggregate.quantity)} time:{format_duration(aggregate.total_time_seconds)}"
            )


def fmt(quantity: float) -> str:
    return f"{quantity:,}" if float(quantity).is_integer() else f"{quantity:,.3f}"


def main():
    idx = load_tables("eve.db")
    session = BomPlannerSession(
        idx,
        top_level_blueprints=TOP_LEVEL_BLUEPRINTS,
        blueprint_updates=BLUEPRINT_ME_UPDATES,
    )
    snapshot = session.snapshot()

    print("Top-level blueprints:")
    for blueprint in TOP_LEVEL_BLUEPRINTS:
        blueprint_typeid = idx.find_type_id_by_name(blueprint.name)
        label = blueprint_typeid if blueprint_typeid is not None else "unknown"
        runs_label = "auto" if blueprint.runs is None else fmt(blueprint.runs)
        print(
            f"  - {blueprint.name} [ME {blueprint.material_efficiency}, TE {blueprint.time_efficiency}, "
            f"runs {runs_label}, prints {blueprint.prints}] -> typeID {label}"
        )

    if BLUEPRINT_ME_UPDATES:
        print("\nApplied blueprint overrides:")
        for blueprint in BLUEPRINT_ME_UPDATES.values():
            runs_label = "auto" if blueprint.runs is None else fmt(blueprint.runs)
            print(
                f"  - {blueprint.name}: ME {blueprint.material_efficiency}, TE {blueprint.time_efficiency}, "
                f"runs {runs_label}, prints {blueprint.prints}"
            )

    print(f"\nTotal build time: {format_duration(snapshot.total_time_seconds)}")
    print_blueprint_settings(snapshot)
    print_depth_summary(snapshot)


if __name__ == "__main__":
    main()
