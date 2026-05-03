from bom_planner import BomPlanner
from db_io import load_tables
from model import BlueprintSettings, PlanConfig

from prints import *

# Selection of what to make
TOP_LEVEL_BLUEPRINTS = {
    # "Heron Blueprint": BlueprintSettings("Heron Blueprint", 0, 0, 1, 1),
    "Rhea Blueprint": BlueprintSettings("Rhea Blueprint", 0, 14, 1, 1),
    # "Charon Blueprint": BlueprintSettings("Charon Blueprint", 10, 20, 1, 1),
}

# Blueprint ME modifiers. Users will be able to add their own prints and configs.
# The same settings object works for top-level jobs and component overrides.
BLUEPRINT_ME_UPDATES = {
    # "Life Support Backup Unit Blueprint": BlueprintSettings("Life Support Backup Unit Blueprint", 10, 20),
    # "Capital Jump Drive Blueprint": BlueprintSettings("Capital Jump Drive Blueprint", 10, 20),
    # "Life Support Backup Unit Blueprint": BlueprintSettings("Life Support Backup Unit Blueprint", 10, 20),
    # "Auto-Integrity Preservation Seal Blueprint": BlueprintSettings("Auto-Integrity Preservation Seal Blueprint", 10, 20),
    "Charon Blueprint": BlueprintSettings("Charon Blueprint", 10, 20, 1, 1)
}

# Default behavior is build. If a component name appears here, it will be bought and not built,
# and the planner will stop before expanding its child inputs.
BUY_COMPONENTS = {
    # "Capital Jump Drive",
    "Nitrogen Fuel Block",
    "Hydrogen Fuel Block",
    "Helium Fuel Block",
    "Oxygen Fuel Block",
}


def main():
    idx = load_tables("eve.db")
    planner = BomPlanner(idx)
    snapshot = planner.build_snapshot(
        PlanConfig(
            plan_id="main-plan",
            top_level_blueprints=TOP_LEVEL_BLUEPRINTS,
            blueprint_settings=BLUEPRINT_ME_UPDATES,
            buy_components=BUY_COMPONENTS,
        )
    )

    # print_top_level_blueprints(idx, TOP_LEVEL_BLUEPRINTS)
    # print_blueprint_updates(BLUEPRINT_ME_UPDATES)
    # print_buy_components(BUY_COMPONENTS)
    # print(f"\nTotal build time: {format_duration(snapshot.total_time_seconds)}")
    # print_blueprint_settings(snapshot)
    print_depth_summary(snapshot)
    shopping_list = snapshot.get_shopping_list()
    print_shopping_list(shopping_list)
    # print_shopping_list(snapshot.get_shopping_list("minerals"), "Minerals")
    # print_shopping_list(snapshot.get_shopping_list("gas"), "Gas")


if __name__ == "__main__":
    main()
