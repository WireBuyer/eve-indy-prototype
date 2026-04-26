from collections import defaultdict

from bom_planner import BomPlannerSession
from db_io import load_tables
from model import Blueprint, BomSnapshot


BLUEPRINT_NAME = Blueprint("Heron Blueprint", 0)
TOP_LEVEL_BLUEPRINTS = [
    # BLUEPRINT_NAME,
    Blueprint("Raven Blueprint", 10),
    # Blueprint("Charon Blueprint", 10),
]

# Example API-style updates. Add or remove blueprint rows here without rebuilding
# the whole request payload.
BLUEPRINT_ME_UPDATES = {
    "Life Support Backup Unit Blueprint": Blueprint("Life Support Backup Unit Blueprint", 10),
    # "Capital Jump Drive Blueprint": Blueprint("Capital Jump Drive Blueprint", 10),
}


def print_blueprint_settings(snapshot: BomSnapshot) -> None:
    print("\nBlueprints in tree:")
    for usage in sorted(snapshot.used_blueprints.values(), key=lambda entry: entry.blueprint_option.product_name):
        print(
            f"  - {usage.blueprint_option.product_name}: {usage.blueprint_option.name} "
            f"[activity {usage.blueprint_option.activity}, ME {usage.configured_blueprint.material_efficiency}]"
        )


def print_depth_summary(snapshot: BomSnapshot) -> None:
    print("\nDepth 0:")
    for root in snapshot.roots:
        blueprint_label = root.selected_blueprint.name if root.selected_blueprint is not None else root.name
        print(f"  - {blueprint_label} (product: {root.name}, ME {root.material_efficiency})")

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
                print(f"  - {aggregate.name} qty - {fmt(aggregate.quantity)}")
                continue

            configured_blueprint = snapshot.request.blueprint_for(blueprint.name)
            print(
                f"  - {aggregate.name} (->{blueprint.name} #{blueprint.type_id}, "
                f"ME {configured_blueprint.material_efficiency}) qty:{fmt(aggregate.quantity)}"
            )


def fmt(quantity: float) -> str:
    return f"{quantity:,}" if float(quantity).is_integer() else f"{quantity:,.3f}"
    # return str(int(quantity)) if float(quantity).is_integer() else f"{quantity:.6f}"


def main():
    idx = load_tables("eve.db")
    session = BomPlannerSession(
        idx,
        top_level_blueprints=TOP_LEVEL_BLUEPRINTS,
        desired_output_units=1.0,
        blueprint_updates=BLUEPRINT_ME_UPDATES,
    )
    snapshot = session.snapshot()

    print("Top-level blueprints:")
    for blueprint in TOP_LEVEL_BLUEPRINTS:
        blueprint_typeid = idx.find_type_id_by_name(blueprint.name)
        label = blueprint_typeid if blueprint_typeid is not None else "unknown"
        print(f"  - {blueprint.name} [ME {blueprint.material_efficiency}] -> typeID {label}")

    if BLUEPRINT_ME_UPDATES:
        print("\nApplied ME overrides:")
        for blueprint in BLUEPRINT_ME_UPDATES.values():
            print(f"  - {blueprint.name}: ME {blueprint.material_efficiency}")

    # print_blueprint_settings(snapshot)
    print_depth_summary(snapshot)


if __name__ == "__main__":
    main()
