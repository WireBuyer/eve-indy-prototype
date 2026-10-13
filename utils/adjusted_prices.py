from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ESI_MARKET_PRICES_URL = "https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
OUTPUT_PATH = Path(__file__).with_name("adjusted_prices.json")


def main() -> None:
    request = Request(
        ESI_MARKET_PRICES_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "eveindytest/0.1",
        },
    )

    with urlopen(request, timeout=30) as response:
        prices = json.loads(response.read().decode("utf-8"))

    adjusted_prices = {
        str(price["type_id"]): float(price["adjusted_price"])
        for price in prices
        if price.get("adjusted_price") is not None
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(adjusted_prices, file, indent=2)
        file.write("\n")

    print(f"Wrote {len(adjusted_prices)} adjusted price rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
