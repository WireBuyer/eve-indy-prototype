from bom_planner import BomPlanner
from bom_view import shopping_list_for
from build_models import BuildPlan, PrintSettings
from db_io import load_tables
from structures import RIG_TIER_BY_META_GROUP, RigTier, StructureConfig

from prints import *

# Selection of what to make
TOP_LEVEL_BLUEPRINTS = [
    # ("Heron Blueprint", 0, 0, 1, 1),
    # ("Raven Blueprint", 3, 14, 1, 2),
    # ("Rokh Blueprint", 10, 14, 1, 1),
    ("Charon Blueprint", 10, 20, 1, 1),
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

STRUCTURE_OVERRIDES = {
    "Auto-Integrity Preservation Seal Blueprint": "component_azbel",
}



def main():
    idx = load_tables("eve.db")
    idx.load_adjusted_prices("adjusted_prices.json")
    idx.load_indexes("system_indexes.json")

    def to_type(name: str) -> int:
        type_id = idx.find_type_id_by_name(name)
        if type_id is None:
            raise ValueError(f"Type not found: {name}")
        return type_id

    def structure_config(
        config_id: str,
        name: str,
        structure: str,
        security: str,
        rigs: list[str] | None = None,
        system_name: str | None = None,
    ) -> StructureConfig:
        def resolved_rig(rig_name: str) -> tuple[str, int, RigTier]:
            rig_type_id = to_type(rig_name)
            return rig_name, rig_type_id, RIG_TIER_BY_META_GROUP[idx.rig_meta_group(rig_type_id)]

        system_id = None
        if system_name is not None:
            system_id = idx.get_system_id(system_name)
            if system_id is None:
                raise ValueError(f"Solar system not found: {system_name}")

        return StructureConfig(
            config_id=config_id,
            name=name,
            structure=structure,
            security=security,
            rigs=[resolved_rig(rig_name) for rig_name in (rigs or [])],
            system_id=system_id,
        )

    def structure_catalog(configs: list[StructureConfig]) -> dict[str, StructureConfig]:
        return {config.config_id: config for config in configs}
    
    available_structures = [
        structure_config(
            config_id="t2_large_raitaru",
            name="T2 Large Raitaru",
            structure="Raitaru",
            security="highsec",
            rigs=[
                "Standup M-Set Basic Large Ship Manufacturing Material Efficiency II",
                "Standup M-Set Basic Large Ship Manufacturing Time Efficiency II",
            ],
        ),
        structure_config(
            config_id="component_azbel",
            name="Component Azbel",
            structure="Azbel",
            security="highsec",
            rigs=[
                "Standup L-Set Advanced Component Manufacturing Efficiency I",
            ],
        ),
        structure_config(
            config_id="advanced_large_ship_raitaru",
            name="Advanced Large Ship Raitaru",
            structure="Raitaru",
            security="highsec",
            rigs=[
                "Standup M-Set Basic Large Ship Manufacturing Material Efficiency II",
                "Standup M-Set Basic Large Ship Manufacturing Time Efficiency II",
            ],
        ),
    ]

    # generate a key value dict of root prints with the blueprint type id as the key
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

    # generate a key value dict of print overrides with the blueprint type id as the key
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
    # generates a key value dict of structure configs with the id as the key
    structure_configs = structure_catalog(available_structures)
    planner = BomPlanner(idx, structure_configs=structure_configs)
    # planner = BomPlanner(idx, use_estimate_math=True)

    result = planner.build_result(
        BuildPlan(
            plan_id="main-plan",
            root_prints=root_prints,
            print_overrides=print_overrides,
            buy_product_type_ids=buy_product_type_ids,
            # primary_manufacturing_structure_id="t2_large_raitaru",
            primary_manufacturing_structure_id=None,
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
    print_job_fees(result)
    shopping_list = shopping_list_for(result)
    print_shopping_list(shopping_list)
    print_shopping_list(shopping_list_for(result, "minerals"), "Minerals")
    print_shopping_list(shopping_list_for(result, "gas"), "Gas")


if __name__ == "__main__":
    main()
