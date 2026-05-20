from bom_planner import BomPlanner
from bom_view import shopping_list_for
from build_models import BuildPlan, PrintSettings
from db_io import load_tables
from structures import StructureConfig, structure_catalog

from prints import *

# Selection of what to make
TOP_LEVEL_BLUEPRINTS = [
    # ("Heron Blueprint", 0, 0, 1, 1),
    # ("Raven Blueprint", 3, 14, 1, 2),
    ("Rokh Blueprint", 5, 14, 1, 1),
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

AVAILABLE_STRUCTURES = [
    StructureConfig(
        config_id="t2_large_raitaru",
        name="T2 Large Raitaru",
        structure="Raitaru",
        security="highsec",
        rig_mode="simple",
        manufacturing_me="t2",
        manufacturing_te="t2",
    ),
    StructureConfig(
        config_id="component_azbel",
        name="Component Azbel",
        structure="Azbel",
        security="highsec",
        rig_mode="simple",
        manufacturing_me="t1",
        manufacturing_te="t1",
    ),
]


STRUCTURE_OVERRIDES = {
    "Auto-Integrity Preservation Seal Blueprint": "component_azbel",
}


def main():
    idx = load_tables("eve.db")
    structure_configs = structure_catalog(AVAILABLE_STRUCTURES)
    planner = BomPlanner(idx, structure_configs=structure_configs)
    # planner = BomPlanner(idx, use_estimate_math=True)

    def to_type(name: str) -> int:
        type_id = idx.find_type_id_by_name(name)
        if type_id is None:
            raise ValueError(f"Type not found: {name}")
        return type_id
    
    root_prints = {}
    for name, material_efficiency, time_efficiency, runs, prints in TOP_LEVEL_BLUEPRINTS:
        settings = PrintSettings(
            name=name,
            blueprint_type_id=to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            runs=runs,
            prints=prints,
        )
        root_prints[settings.blueprint_type_id] = settings

    print_overrides = {}
    for name, material_efficiency, time_efficiency, runs, prints in BLUEPRINT_ME_UPDATES:
        settings = PrintSettings(
            name=name,
            blueprint_type_id=to_type(name),
            material_efficiency=material_efficiency,
            time_efficiency=time_efficiency,
            prints=prints,
        )
        print_overrides[settings.blueprint_type_id] = settings

    buy_product_type_ids = {to_type(name) for name in BUY_COMPONENTS}
    structure_overrides = {to_type(name): config_id for name, config_id in STRUCTURE_OVERRIDES.items()}

    result = planner.build_result(
        BuildPlan(
            plan_id="main-plan",
            root_prints=root_prints,
            print_overrides=print_overrides,
            buy_product_type_ids=buy_product_type_ids,
            primary_manufacturing_structure_id="t2_large_raitaru",
            primary_reaction_structure_id=None,
            structure_overrides=structure_overrides,
        )
    )

    # print_top_level_blueprints(idx, TOP_LEVEL_BLUEPRINTS)
    # print_blueprint_updates(BLUEPRINT_ME_UPDATES)
    # print_buy_components(idx, buy_product_type_ids)
    # print(f"\nTotal build time: {format_duration(result.total_time_seconds)}")
    # print_blueprint_settings(result)
    print_depth_summary(result)
    # shopping_list = shopping_list_for(result)
    # print_shopping_list(shopping_list)
    # print_shopping_list(shopping_list_for(result, "minerals"), "Minerals")
    # print_shopping_list(shopping_list_for(result, "gas"), "Gas")


if __name__ == "__main__":
    main()
