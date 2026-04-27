import sqlite3
from collections import defaultdict
from typing import Tuple, Dict

from model import TypeInfo, BlueprintProduct, MaterialRow, BlueprintActivityTime
from industry_index import IndustryIndex


def load_tables(db_path: str = "eve.db") -> IndustryIndex:
    """Load relevant SDE tables from the SQLite DB and return in-memory maps.

    Returns: (inv_types, bp_products, bp_by_product, materials, activities)
    - inv_types: typeID -> TypeInfo (only published types)
    - bp_products: (blueprint_typeID, activityID) -> list of `BlueprintProduct` (blueprint outputs)
    - bp_by_product: productTypeID -> list of `BlueprintProduct` (reverse index: which blueprints produce a product)
    - materials: (blueprint_typeID, activityID) -> list of `MaterialRow` (blueprint inputs)
    - activity_times: (typeID, activityID) -> `BlueprintActivityTime` (time row for that blueprint/activity)
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

    # Load industryActivityProducts - blueprint outputs
    cur.execute('SELECT typeID, activityID, productTypeID, quantity FROM "industryActivityProducts"')
    bp_products = defaultdict(list)
    bp_by_product = defaultdict(list)
    for typeID, activityID, productTypeID, qty in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        ptype = int(productTypeID)
        q = float(qty)
        row = BlueprintProduct(type_id=tid, activity=act, product_typeid=ptype, quantity=q)
        bp_products[(tid, act)].append(row)
        bp_by_product[ptype].append(row)

    # Load industryActivityMaterials - blueprint inputs
    materials = defaultdict(list)
    cur.execute('SELECT typeID, activityID, materialTypeID, quantity FROM "industryActivityMaterials"')
    for typeID, activityID, materialTypeID, qty in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        mtype = int(materialTypeID)
        q = float(qty)
        materials[(tid, act)].append(MaterialRow(type_id=tid, activity=act, material_typeid=mtype, quantity=q))

    # Load industryActivity - blueprint activity times
    # table columns: typeID, activityID, time
    cur.execute('SELECT typeID, activityID, time FROM "industryActivity"')
    # use a single dict keyed by (typeID, activityID) -> BlueprintActivityTime to match other maps
    activity_times = {}
    for typeID, activityID, time in cur.fetchall():
        tid = int(typeID)
        act = int(activityID)
        t = float(time) if time is not None else None
        activity_times[(tid, act)] = BlueprintActivityTime(type_id=tid, activity=act, time=t)

    conn.close()
    # return an index object that hides tuple-key usage
    return IndustryIndex(inv_types, bp_products, bp_by_product, materials, activity_times)
