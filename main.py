from bom_planner import BomPlanner
from db_io import load_tables
from model import BlueprintSettings, PlanConfig

from prints import *

# Selection of what to make
TOP_LEVEL_BLUEPRINTS = [
    ("Heron Blueprint", 0, 0, 1, 1),
    ("Raven Blueprint", 3, 14, 1, 1),
    # ("Charon Blueprint", 10, 20, 1, 1),
]

# Blueprint ME modifiers. Users will be able to add their own prints and configs.
# The same settings object works for top-level jobs and component overrides.
BLUEPRINT_ME_UPDATES = [
    # ("Life Support Backup Unit Blueprint", 10, 20),
    # ("Capital Jump Drive Blueprint", 10, 20),
    # ("Life Support Backup Unit Blueprint", 10, 20),
    # ("Auto-Integrity Preservation Seal Blueprint", 10, 20),
]

# Default behavior is build. If a component name appears here, it will be bought and not built,
# and the planner will stop before expanding its child inputs.
BUY_COMPONENTS = [
    # "Capital Jump Drive",
    "Nitrogen Fuel Block",
    "Hydrogen Fuel Block",
    "Helium Fuel Block",
    "Oxygen Fuel Block",
]


def main():
    idx = load_tables("eve.db")
    planner = BomPlanner(idx)
    # planner = BomPlanner(idx, use_estimate_math=True)

    def to_type(name: str) -> int:
        type_id = idx.find_type_id_by_name(name)
        if type_id is None:
            raise ValueError(f"Type not found: {name}")
        return type_id
    
    top_level_blueprints = {}
    for name, material_efficiency, time_efficiency, runs, prints in TOP_LEVEL_BLUEPRINTS:
        settings = BlueprintSettings(
            name=name,
            blueprint_type_id=to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            runs=runs,
            prints=prints,
        )
        top_level_blueprints[settings.blueprint_type_id] = settings

    blueprint_updates = {}
    for name, material_efficiency, time_efficiency, runs, prints in BLUEPRINT_ME_UPDATES:
        settings = BlueprintSettings(
            name=name,
            blueprint_type_id=to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            prints=prints,
        )
        blueprint_updates[settings.blueprint_type_id] = settings

    buy_component_type_ids = {to_type(name) for name in BUY_COMPONENTS}

    result = planner.build_result(
        PlanConfig(
            plan_id="main-plan",
            top_level_blueprints=top_level_blueprints,
            blueprint_settings=blueprint_updates,
            buy_component_type_ids=buy_component_type_ids,
        )
    )

    # print_top_level_blueprints(idx, TOP_LEVEL_BLUEPRINTS)
    # print_blueprint_updates(BLUEPRINT_ME_UPDATES)
    # print_buy_components(idx, buy_component_type_ids)
    # print(f"\nTotal build time: {format_duration(result.total_time_seconds)}")
    # print_blueprint_settings(result)
    print_depth_summary(result)
    shopping_list = result.get_shopping_list()
    # print_shopping_list(shopping_list)
    print_shopping_list(result.get_shopping_list("minerals"), "Minerals")
    print_shopping_list(result.get_shopping_list("gas"), "Gas")


if __name__ == "__main__":
    main()
