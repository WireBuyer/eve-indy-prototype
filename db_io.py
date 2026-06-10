import sqlite3
from collections import defaultdict

from model import (
    PRODUCTION_ACTIVITIES,
    BlueprintActivityTime,
    BlueprintProduct,
    IndustryActivitySkill,
    MaterialRow,
    RigAffectedProductGroup,
    TypeInfo,
)
from industry_index import IndustryIndex


def load_tables(db_path: str = "eve.db") -> IndustryIndex:
    """Load relevant SDE tables from the SQLite DB and return in-memory maps.

    Returns an `IndustryIndex` with loaded production and rig lookup data.

    - inv_types: typeID -> TypeInfo (only published types)
    - bp_products: (blueprint_typeID, activityID) -> `BlueprintProduct` (blueprint output)
    - bp_by_product: productTypeID -> `BlueprintProduct` (published blueprint that produces a product)
    - materials: (blueprint_typeID, activityID) -> list of `MaterialRow` (blueprint inputs)
    - activity_times: (typeID, activityID) -> `BlueprintActivityTime` (time row for that blueprint/activity)
    - activity_skills: (typeID, activityID) -> list of `IndustryActivitySkill` (required skills)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # only load published types
    cur.execute('''SELECT typeID, typeName, volume, iconID, groupID, marketGroupID
                   FROM "invTypes" WHERE published = 1''')

    # Load invTypes
    inv_types = {}
    for typeID, typeName, volume, iconID, groupID, marketGroupID in cur.fetchall():
        tid = int(typeID)
        name = typeName
        vol = float(volume) if volume is not None else 0.0
        icon = int(iconID) if iconID is not None else None
        group = int(groupID) if groupID is not None else None
        mgroup = int(marketGroupID) if marketGroupID is not None else None
        inv_types[tid] = TypeInfo(type_id=tid, name=name, volume=vol, icon_id=icon, group_id=group, market_group_id=mgroup)

    # Load industryActivityProducts - published blueprint outputs
    cur.execute(
        '''
        SELECT p.typeID, p.activityID, p.productTypeID, p.quantity
        FROM "industryActivityProducts" p
        JOIN "invTypes" bp ON bp.typeID = p.typeID
        JOIN "invTypes" prod ON prod.typeID = p.productTypeID
        WHERE bp.published = 1
        AND prod.published = 1
        '''
    )
    bp_products = {}
    bp_by_product = {}
    for typeID, activityID, productTypeID, qty in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        if act not in PRODUCTION_ACTIVITIES:
            continue
        ptype = int(productTypeID)
        q = float(qty)
        row = BlueprintProduct(type_id=tid, activity=act, product_typeid=ptype, quantity=q)
        key = (tid, act)
        if key in bp_products:
            raise ValueError(f"Multiple production outputs found for blueprint {tid}, activity {act}")
        if ptype in bp_by_product:
            raise ValueError(f"Multiple published production blueprints found for product {ptype}")
        bp_products[key] = row
        bp_by_product[ptype] = row

    # Load industryActivityMaterials - published blueprint inputs
    materials = defaultdict(list)
    cur.execute(
        '''
        SELECT m.typeID, m.activityID, m.materialTypeID, m.quantity
        FROM "industryActivityMaterials" m
        JOIN "invTypes" bp ON bp.typeID = m.typeID
        JOIN "invTypes" mat ON mat.typeID = m.materialTypeID
        WHERE bp.published = 1
        AND mat.published = 1
        '''
    )
    for typeID, activityID, materialTypeID, qty in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        mtype = int(materialTypeID)
        q = float(qty)
        materials[(tid, act)].append(MaterialRow(type_id=tid, activity=act, material_typeid=mtype, quantity=q))

    # Load industryActivity - blueprint activity times
    # table columns: typeID, activityID, time
    cur.execute(
        '''
        SELECT a.typeID, a.activityID, a.time
        FROM "industryActivity" a
        JOIN "invTypes" bp ON bp.typeID = a.typeID
        WHERE bp.published = 1
        '''
    )
    # use a single dict keyed by (typeID, activityID) -> BlueprintActivityTime to match other maps
    activity_times = {}
    for typeID, activityID, time in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        t = float(time) if time is not None else None
        activity_times[(tid, act)] = BlueprintActivityTime(type_id=tid, activity=act, time=t)

    # Load industryActivitySkills - skills required to run production jobs.
    activity_skills = defaultdict(list)
    cur.execute(
        '''
        SELECT s.typeID, s.activityID, s.skillID, s.level
        FROM "industryActivitySkills" s
        JOIN "invTypes" bp ON bp.typeID = s.typeID
        JOIN "invTypes" skill ON skill.typeID = s.skillID
        WHERE bp.published = 1
        AND skill.published = 1
        '''
    )
    for typeID, activityID, skillID, level in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        if act not in PRODUCTION_ACTIVITIES:
            continue
        activity_skills[(tid, act)].append(
            IndustryActivitySkill(
                type_id=tid,
                activity=act,
                skill_id=int(skillID),
                level=int(level),
            )
        )

    cur.execute(
        '''
        SELECT rigTypeID, activityKey, bonusType, productGroupID, filterID
        FROM "rigAffectedProductGroups"
        '''
    )
    rig_affected_groups = defaultdict(set)
    for rigTypeID, activityKey, bonusType, productGroupID, filterID in cur.fetchall():
        row = RigAffectedProductGroup(
            rig_type_id=int(rigTypeID),
            activity_key=str(activityKey),
            bonus_type=str(bonusType),
            product_group_id=int(productGroupID),
            filter_id=int(filterID) if filterID is not None else None,
        )
        key = (row.rig_type_id, row.activity_key, row.bonus_type)
        rig_affected_groups[key].add(row.product_group_id)

    cur.execute(
        '''
        SELECT DISTINCT mt.typeID, mt.metaGroupID
        FROM "invMetaTypes" mt
        JOIN "rigAffectedProductGroups" r ON r.rigTypeID = mt.typeID
        '''
    )
    rig_meta_groups = {
        int(typeID): int(metaGroupID)
        for typeID, metaGroupID in cur.fetchall()
        if metaGroupID is not None
    }

    cur.execute(
        '''
        SELECT solarSystemName, solarSystemID
        FROM "mapSolarSystems"
        WHERE solarSystemName IS NOT NULL
        '''
    )
    solar_system_ids_by_name = {
        str(solarSystemName): int(solarSystemID)
        for solarSystemName, solarSystemID in cur.fetchall()
    }

    conn.close()
    # return an index object that hides tuple-key usage
    return IndustryIndex(
        inv_types,
        bp_products,
        bp_by_product,
        materials,
        activity_times,
        dict(rig_affected_groups),
        rig_meta_groups,
        solar_system_ids_by_name,
        dict(activity_skills),
    )
