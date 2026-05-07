from __future__ import annotations

from math import ceil

from build_models import BomItem, BomResult


SHOPPING_LIST_GROUPS = {
    "minerals": {18},
    "gas": {711},
}


def is_built(item: BomItem) -> bool:
    return item.blueprint_type_id is not None


def is_bought(result: BomResult, item: BomItem) -> bool:
    return item.type_id in result.buy_product_type_ids


def is_base_material(result: BomResult, item: BomItem) -> bool:
    return not is_built(item) and not is_bought(result, item)


def item_tag(result: BomResult, item: BomItem) -> str:
    if is_bought(result, item):
        return "BUY"
    if is_base_material(result, item):
        return "BASE"
    return ""


def rows(result: BomResult) -> list[BomItem]:
    return result.roots + sorted(result.items_by_product_id.values(), key=lambda item: (item.depth, item.type_id))


def depth_layers(result: BomResult) -> dict[int, list[BomItem]]:
    layers: dict[int, list[BomItem]] = {}
    for item in result.items_by_product_id.values():
        layers.setdefault(item.depth, []).append(item)
    for items in layers.values():
        items.sort(key=lambda item: item.type_id)
    return layers


def total_time_seconds(result: BomResult) -> float:
    return sum(item.total_time_seconds for item in result.roots) + sum(
        item.total_time_seconds for item in result.items_by_product_id.values()
    )


def shopping_list_for(result: BomResult, item_group: str | None = None) -> list[dict]:
    group_ids = _shopping_list_group_ids(item_group)
    return [
        {
            "type_id": item.type_id,
            "name": item.name,
            "quantity": ceil(item.quantity),
            "tag": item_tag(result, item),
        }
        for item in sorted(result.items_by_product_id.values(), key=lambda item: item.type_id)
        if not is_built(item) and (group_ids is None or item.group_id in group_ids)
    ]


def _shopping_list_group_ids(item_group: str | None) -> set[int] | None:
    if item_group is None:
        return None
    if item_group not in SHOPPING_LIST_GROUPS:
        raise ValueError(f"Unknown shopping list group: {item_group}")
    return SHOPPING_LIST_GROUPS[item_group]
