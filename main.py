from bom_planner import BomPlannerSession
from db_io import load_tables
from model import Blueprint

# import the print statements from the prints module
from prints import *


BLUEPRINT_NAME = Blueprint("Heron Blueprint", 0, 0, 1, 1)
TOP_LEVEL_BLUEPRINTS = [
    # BLUEPRINT_NAME,
    Blueprint("Raven Blueprint", 10, 20, 1, 1),
    # Blueprint("Charon Blueprint", 10, 20, 1, 1),
]

# Example API-style updates. Add or remove blueprint rows here without rebuilding
# the whole request payload.
BLUEPRINT_ME_UPDATES = {
    "Life Support Backup Unit Blueprint": Blueprint("Life Support Backup Unit Blueprint", 10, 20),
    # "Capital Jump Drive Blueprint": Blueprint("Capital Jump Drive Blueprint", 10, 20),
}

# Default behavior is build. If a component name appears here, it will be bought
# and the planner will stop before expanding its child inputs.
BUY_COMPONENTS = {
    # "Capital Jump Drive",
}


def main():
    idx = load_tables("eve.db")
    session = BomPlannerSession(
        idx,
        top_level_blueprints=TOP_LEVEL_BLUEPRINTS,
        blueprint_updates=BLUEPRINT_ME_UPDATES,
        buy_components=BUY_COMPONENTS,
    )
    snapshot = session.snapshot()

    # print_top_level_blueprints(idx, TOP_LEVEL_BLUEPRINTS)
    print_blueprint_updates(BLUEPRINT_ME_UPDATES)
    print_buy_components(BUY_COMPONENTS)
    print(f"\nTotal build time: {format_duration(snapshot.total_time_seconds)}")
    print_blueprint_settings(snapshot)
    print_depth_summary(snapshot)


if __name__ == "__main__":
    main()
