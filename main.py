from bom_planner import BomPlannerSession
from db_io import load_tables
from model import Blueprint

from prints import print_depth_summary


TOP_LEVEL_BLUEPRINTS = [
    # Blueprint("Heron Blueprint", 0, 0, 1, 1),
    Blueprint("Raven Blueprint", 10, 20, 1, 1),
    # Blueprint("Charon Blueprint", 10, 20, 1, 1),
]

# Blueprint ME modifiers. Users will be able to add their own prints and configs. Uses the same 
# blueprint model since everything in eve online is a print
BLUEPRINT_ME_UPDATES = {
    # "Life Support Backup Unit Blueprint": Blueprint("Life Support Backup Unit Blueprint", 10, 20),
    # "Capital Jump Drive Blueprint": Blueprint("Capital Jump Drive Blueprint", 10, 20),
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
    # passs in the idx and our plan config
    session = BomPlannerSession(
        idx,
        top_level_blueprints=TOP_LEVEL_BLUEPRINTS,
        blueprint_updates=BLUEPRINT_ME_UPDATES,
        buy_components=BUY_COMPONENTS,
    )
    # run the planner
    snapshot = session.snapshot()

    # print_top_level_blueprints(idx, TOP_LEVEL_BLUEPRINTS)
    # print_blueprint_updates(BLUEPRINT_ME_UPDATES)
    # print_buy_components(BUY_COMPONENTS)
    # print(f"\nTotal build time: {format_duration(snapshot.total_time_seconds)}")
    # print_blueprint_settings(snapshot)
    print_depth_summary(snapshot)


if __name__ == "__main__":
    main()
