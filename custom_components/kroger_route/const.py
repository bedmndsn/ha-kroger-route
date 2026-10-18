"""Constants for the Kroger & Ralphs Route Planner integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "kroger_route"
DEFAULT_NAME = "Kroger Route Planner"

PLATFORMS = ["sensor"]

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_LOCATION_ID = "location_id"
CONF_STORE_NAME = "store_name"
CONF_TODO_ENTITY = "todo_entity"
CONF_LAYOUT_PRESET = "layout_preset"
CONF_CUSTOM_LAYOUT = "custom_layout"
CONF_PROXY_URL = "proxy_url"
CONF_IGNORE_ITEMS = "ignore_items"
CONF_TYPO_FIXES = "typo_fixes"
CONF_DIRECT_PRODUCT_IDS = "direct_product_ids"

DEFAULT_TODO_ENTITY = "todo.shopping_list"
DEFAULT_LAYOUT_PRESET = "standard_right"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
DEFAULT_RATE_LIMIT_DELAY = 0.3  # seconds between API requests
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0

SERVICE_REFRESH_ROUTE = "refresh_route"
SERVICE_PROCESS_LIST = "process_list"
ATTR_FORCE_REFRESH = "force_refresh"

KROGER_TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_LOCATIONS_URL = "https://api.kroger.com/v1/locations"
KROGER_PRODUCTS_URL = "https://api.kroger.com/v1/products"

PRODUCT_SEARCH_UNAVAILABLE_CODE = "PRODUCT-2029"

# Browser-like headers to prevent WAF / 403 HTTP blocks from Kroger's Akamai front door.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Built-in default ignore lists: Catch voice-dictation noise, list headers, and store banners
DEFAULT_IGNORE_ITEMS = [
    # Generic voice noise & list headers
    "shopping list",
    "grocery list",
    "groceries",
    "my list",
    "items",
    "item",
    "things to get",
    "what to buy",
    "to buy",
    # Kroger and Kroger-owned banner/brand names
    "kroger",
    "kroger list",
    "ralphs",
    "ralph's",
    "ralphs list",
    "ralph's list",
    "fred meyer",
    "fred meyer list",
    "fry's",
    "frys",
    "king soopers",
    "qfc",
    "smith's",
    "smiths",
    "dillons",
    "dillon's",
    "harris teeter",
    "mariano's",
    "marianos",
    "pick 'n save",
    "pick n save",
    "metro market",
    "city market",
    "baker's",
    "bakers",
    "food 4 less",
    "foods co",
    "ruler foods",
    "gerbes",
    "jay c",
    "pay-less",
    "pay less",
    "roundy's",
    "roundys",
]

DEFAULT_TYPO_FIXES = {
    "milkk": "milk",
    "almond milkk": "almond milk",
    "bannana": "banana",
    "bannanas": "bananas",
    "chiken": "chicken",
    "yogrt": "yogurt",
    "oj": "orange juice",
    "pb": "peanut butter",
}

# Store Layout Presets
# "NUMERIC_AISLES" covers all numbered aisles. Range tokens like "AISLES_1_3",
# "AISLES_4_17", "AISLE_18", "AISLES_19_PLUS", "AISLES_1_20", "AISLES_21_PLUS" allow
# fine-grained interleaving of fresh departments between aisle blocks.
STORE_PRESETS = {
    "standard_right": {
        "name": "Right Entrance (Produce/Floral -> Deli -> Center Aisles -> Meat/Seafood -> Dairy -> Frozen)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL",
            "DELI", "DELI/BAKE", "BAKERY", "GROCERY",
            "NUMERIC_AISLES",
            "MEAT", "PACKAGED MEAT", "SEAFOOD",
            "DAIRY", "LEFT WALL", "RIGHT WALL",
            "FROZEN",
            "PHARMACY", "FRONT END", "FRONT-OTHER", "UNSORTED",
        ],
    },
    "standard_left": {
        "name": "Left Entrance (Produce/Bakery -> Meat/Seafood -> Center Aisles -> Dairy -> Frozen)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL", "DELI", "DELI/BAKE", "BAKERY",
            "MEAT", "SEAFOOD", "PACKAGED MEAT",
            "NUMERIC_AISLES",
            "DAIRY", "LEFT WALL", "RIGHT WALL",
            "FROZEN",
            "PHARMACY", "FRONT END", "FRONT-OTHER", "UNSORTED",
        ],
    },
    "marketplace": {
        "name": "Kroger Marketplace & Mega-Stores (Produce -> Deli -> Aisles 1-20 -> Meat/Seafood -> Dairy -> Aisles 21+)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL",
            "DELI", "DELI/BAKE", "BAKERY", "GROCERY",
            "AISLES_1_20",
            "MEAT", "SEAFOOD", "PACKAGED MEAT",
            "DAIRY", "RIGHT WALL", "LEFT WALL",
            "AISLES_21_PLUS",
            "FROZEN", "PHARMACY", "FRONT END", "FRONT-OTHER", "UNSORTED",
        ],
    },
    "perimeter_first": {
        "name": "Perimeter First (Fresh Ring: Produce -> Deli -> Meat/Seafood -> Dairy -> Center Pantry Aisles)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL",
            "DELI", "DELI/BAKE", "BAKERY",
            "SEAFOOD", "MEAT", "PACKAGED MEAT",
            "DAIRY", "LEFT WALL", "RIGHT WALL",
            "NUMERIC_AISLES",
            "FROZEN", "PHARMACY", "FRONT END", "FRONT-OTHER", "UNSORTED",
        ],
    },
    "cold_chain_last": {
        "name": "Cold Chain Last (Produce -> Dry Grocery Aisles -> Meat/Seafood -> Dairy -> Frozen at Finish)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL", "GROCERY",
            "BAKERY", "DELI", "DELI/BAKE",
            "NUMERIC_AISLES",
            "MEAT", "SEAFOOD", "PACKAGED MEAT",
            "DAIRY", "LEFT WALL", "RIGHT WALL",
            "FROZEN",
            "FRONT END", "PHARMACY", "FRONT-OTHER", "UNSORTED",
        ],
    },
    "urban_compact": {
        "name": "Urban Compact / Interleaved (Produce -> Dairy -> Aisles 1-3 -> Deli/Seafood -> Aisles 4-17 -> Meat -> Bakery -> Aisles 19+)",
        "order": [
            "PRODUCE", "FRUIT", "FLORAL",
            "DAIRY",
            "MEAT",
            "AISLES_1_3",
            "DELI", "DELI/BAKE",
            "SEAFOOD",
            "AISLES_4_17",
            "PACKAGED MEAT",
            "AISLE_18",
            "BAKERY", "BAKED GOODS",
            "AISLES_19_PLUS",
            "FRONT END", "UNSORTED",
        ],
    },
    "custom": {
        "name": "Custom Sequence (User Configured)",
        "order": [],
    },
}
