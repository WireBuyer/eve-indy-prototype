import json

# with open("response.json", "r", encoding="utf-8") as f:
#     items = json.load(f)

# nodes = [it for it in items if "depth" in it.get("data", {})]

# nodes.sort(key=lambda it: (int(it["data"]["depth"]), int(it["data"]["id"])))

# for it in nodes:
#     d = it["data"]
#     for k in ("image", "bg_image", "cf_node_amount", "cf_unit_mats"):
#         if k in d:
#             del d[k]

# with open("response_clean.json", "w", encoding="utf-8") as f:
#     json.dump(nodes, f, indent=2, ensure_ascii=False)

# print("Wrote response_clean.json with", len(nodes), "nodes (items with depth).")

with open("response_clean.json", "r") as f:
    nodes = json.load(f)

with open("response_clean.txt", "w") as out:
    depth = 0
    print(f"DEPTH: {depth}\n")
    out.write(f"DEPTH: {depth}\n\n")
    for it in nodes:
        data = it["data"]
        if data["depth"] != depth:
            depth += 1
            print(f"\nDEPTH: {depth}\n")
            out.write(f"\nDEPTH: {depth}\n\n")
        name = data["name"]
        id = data["id"]
        qty = data["base_node_amount"]
        # pad name with spaces to make column width consistent
        print(f"{name:<{40}} {qty:<15,.3f} {id}")
        out.write(f"{name:<{40}} {qty:<15,.3f} {id}\n")