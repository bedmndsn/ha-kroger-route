"""Utility script to harvest raw Kroger API aisle location data across multiple stores.

Run standalone (outside Home Assistant) to sample how different store
locations describe aisle/department locations. This is useful when building
a custom STORE_PRESETS entry for a chain or store layout not already covered
by the built-in presets in custom_components/kroger_route/const.py.

Usage:
    python3 harvest_aisle_data.py
"""
import asyncio
import json

import aiohttp

CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

# Kroger sits behind an Akamai WAF that rejects the default aiohttp/requests
# User-Agent with a 403. A normal browser UA is required.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "*/*",
}

SAMPLE_STORES = {
    "01400123": "Kroger - Sample Store 1",
    "01400456": "Ralphs - Sample Store 2",
}

BASKET_ITEMS = [
    "bananas", "bagels", "cream cheese", "ground beef",
    "salmon", "pasta sauce", "cereal", "frozen pizza",
    "paper towels", "deli turkey", "tofu", "almond milk",
]


async def harvest() -> None:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Kroger's token endpoint requires HTTP Basic Auth for the
        # client_credentials grant. Encode credentials manually into the
        # Authorization header to avoid the deprecated aiohttp `auth=` kwarg
        # and avoid incorrectly sending credentials in the POST body.
        auth_header = aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET).encode()
        async with session.post(
            "https://api.kroger.com/v1/connect/oauth2/token",
            data={"grant_type": "client_credentials", "scope": "product.compact"},
            headers={"Authorization": auth_header},
        ) as resp:
            if resp.status != 200:
                print(f"Auth failed: HTTP {resp.status} - {await resp.text()}")
                return
            token = (await resp.json()).get("access_token")

        auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}
        output: dict[str, dict[str, object]] = {}

        for store_id, store_name in SAMPLE_STORES.items():
            print(f"Scraping store: {store_name} ({store_id})...")
            output[store_name] = {}
            for item in BASKET_ITEMS:
                params = {
                    "filter.term": item,
                    "filter.locationId": store_id,
                    "filter.limit": "1",
                }
                async with session.get(
                    "https://api.kroger.com/v1/products", headers=auth_headers, params=params
                ) as resp:
                    if resp.status != 200:
                        print(f"  Failed fetching '{item}': HTTP {resp.status}")
                        output[store_name][item] = "NO_LOCATION"
                        continue
                    res = await resp.json()
                    products = res.get("data", [])
                    if products and "aisleLocations" in products[0]:
                        output[store_name][item] = products[0]["aisleLocations"]
                    else:
                        output[store_name][item] = "NO_LOCATION"
                await asyncio.sleep(0.3)  # Rate limiting safety

        with open("harvested_aisle_data.json", "w") as f:
            json.dump(output, f, indent=2)
        print("Data saved to harvested_aisle_data.json!")


if __name__ == "__main__":
    asyncio.run(harvest())
