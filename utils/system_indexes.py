from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ESI_INDUSTRY_SYSTEMS_URL = "https://esi.evetech.net/latest/industry/systems/?datasource=tranquility"
OUTPUT_PATH = Path(__file__).with_name("system_indexes.json")


def main() -> None:
    request = Request(
        ESI_INDUSTRY_SYSTEMS_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "eveindytest/0.1",
        },
    )

    with urlopen(request, timeout=30) as response:
        systems = json.loads(response.read().decode("utf-8"))

    system_indexes = {
        # system["solar_system_id"]: {
        #     cost_index["activity"]: float(cost_index["cost_index"])
        #     for cost_index in system["cost_indices"]
        # }
        # for system in systems
    }

    for system in systems:
        system_id = system["solar_system_id"]
        cost_indices = system["cost_indices"]

        activity_index = {}
        for index in cost_indices:
            activity = index["activity"]
            cost_index = float(index["cost_index"])
            activity_index[activity] = cost_index
        
        system_indexes[system_id] = activity_index


        

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(system_indexes, file, indent=2)
        file.write("\n")

    print(f"Wrote {len(system_indexes)} system index rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
