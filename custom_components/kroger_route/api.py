"""Async Kroger API client for the Kroger & Ralphs Route Planner integration."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import aiohttp

from .const import (
    DEFAULT_HEADERS,
    DEFAULT_RATE_LIMIT_DELAY,
    INITIAL_BACKOFF,
    KROGER_LOCATIONS_URL,
    KROGER_PRODUCTS_URL,
    KROGER_TOKEN_URL,
    MAX_RETRIES,
    PRODUCT_SEARCH_UNAVAILABLE_CODE,
)

_LOGGER = logging.getLogger(__name__)


class KrogerApiError(Exception):
    """Generic error talking to the Kroger API."""


class KrogerAuthError(KrogerApiError):
    """Raised when Kroger OAuth credentials are invalid."""


class ProductSearchUnavailable(KrogerApiError):
    """Raised when a store location does not support product search (PRODUCT-2029)."""

    def __init__(self, location_id: str) -> None:
        super().__init__(f"Product search is not available at location {location_id}")
        self.location_id = location_id


class KrogerAPIClient:
    """Thin async wrapper around the Kroger public API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        proxy_url: str | None = None,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
    ) -> None:
        self._session = session
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._proxy_url = proxy_url.strip() if proxy_url and proxy_url.strip() else None
        self.rate_limit_delay = rate_limit_delay

        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        """Enforce request delay to avoid triggering rate limits."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    async def async_get_token(self) -> str:
        """Fetch (and cache) an OAuth2 access token using HTTP Basic Auth."""
        if self._token and time.monotonic() < self._token_expiry:
            return self._token

        async with self._lock:
            if self._token and time.monotonic() < self._token_expiry:
                return self._token

            headers = dict(DEFAULT_HEADERS)
            headers["Authorization"] = aiohttp.BasicAuth(self._client_id, self._client_secret).encode()

            await self._throttle()
            try:
                async with self._session.post(
                    KROGER_TOKEN_URL,
                    data={"grant_type": "client_credentials", "scope": "product.compact"},
                    headers=headers,
                    proxy=self._proxy_url,
                ) as resp:
                    if resp.status != 200:
                        raise KrogerAuthError(f"Failed to authenticate with Kroger: HTTP {resp.status}")
                    payload = await resp.json()
            except aiohttp.ClientError as err:
                raise KrogerApiError(f"Network error during authentication: {err}") from err

            token = payload.get("access_token")
            if not token:
                raise KrogerAuthError("Kroger token response did not include an access_token")

            self._token = token
            self._token_expiry = time.monotonic() + payload.get("expires_in", 1800) - 60
            return token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self.async_get_token()
        headers = dict(DEFAULT_HEADERS)
        headers["Authorization"] = f"Bearer {token}"
        return headers

    async def async_get_locations(self, zip_code: str) -> dict[str, str]:
        """Return a mapping of location_id -> display label for stores near a ZIP code."""
        headers = await self._auth_headers()
        params = {"filter.zipCode.near": zip_code, "filter.limit": "10"}

        await self._throttle()
        try:
            async with self._session.get(
                KROGER_LOCATIONS_URL,
                headers=headers,
                params=params,
                proxy=self._proxy_url,
            ) as resp:
                if resp.status != 200:
                    raise KrogerApiError(f"Location search failed: HTTP {resp.status}")
                payload = await resp.json()
        except aiohttp.ClientError as err:
            raise KrogerApiError(f"Network error during location search: {err}") from err

        locations: dict[str, str] = {}
        for loc in payload.get("data", []):
            location_id = loc.get("locationId")
            if not location_id:
                continue
            name = loc.get("name", "Unknown Store")
            address = loc.get("address", {})
            parts = [
                address.get("addressLine1", ""),
                address.get("city", ""),
                address.get("state", ""),
            ]
            address_str = ", ".join(p for p in parts if p)
            locations[location_id] = f"{name} - {address_str}" if address_str else name

        return locations

    async def async_validate_product_search(self, location_id: str) -> None:
        """Raise ProductSearchUnavailable if the store doesn't support product search."""
        headers = await self._auth_headers()
        params = {"filter.term": "milk", "filter.locationId": location_id, "filter.limit": "1"}

        await self._throttle()
        try:
            async with self._session.get(
                KROGER_PRODUCTS_URL,
                headers=headers,
                params=params,
                proxy=self._proxy_url,
            ) as resp:
                if resp.status == 400:
                    body = await resp.json(content_type=None)
                    code = body.get("errors", {}).get("code", "")
                    if code == PRODUCT_SEARCH_UNAVAILABLE_CODE:
                        raise ProductSearchUnavailable(location_id)
                    raise KrogerApiError(f"Product validation failed: HTTP 400 ({code})")
                if resp.status != 200:
                    raise KrogerApiError(f"Product validation failed: HTTP {resp.status}")
        except aiohttp.ClientError as err:
            raise KrogerApiError(f"Network error validating store: {err}") from err

    async def async_get_product_by_id(self, product_id: str, location_id: str) -> dict[str, Any] | None:
        """Query Kroger API directly by product ID / UPC."""
        headers = await self._auth_headers()
        url = f"{KROGER_PRODUCTS_URL}/{product_id}"
        params = {"filter.locationId": location_id}

        backoff = INITIAL_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            await self._throttle()
            try:
                async with self._session.get(
                    url,
                    headers=headers,
                    params=params,
                    proxy=self._proxy_url,
                ) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                        _LOGGER.warning("Rate limit (429) on product ID %s. Backing off %.1fs", product_id, wait)
                        await asyncio.sleep(wait)
                        backoff *= 2
                        continue

                    if resp.status == 200:
                        payload = await resp.json()
                        data = payload.get("data", {})
                        if data:
                            return self._parse_product(data, fallback_name=product_id)
                    return None
            except aiohttp.ClientError as err:
                _LOGGER.debug("Direct lookup error for %s (attempt %d): %s", product_id, attempt, err)
                if attempt == MAX_RETRIES:
                    return None
                await asyncio.sleep(backoff)
                backoff *= 2
        return None

    async def async_search_product(self, item_name: str, location_id: str) -> dict[str, Any]:
        """Search for a product and return aisle/price/image, or an UNSORTED fallback."""
        headers = await self._auth_headers()
        params = {"filter.term": item_name, "filter.locationId": location_id, "filter.limit": "1"}

        backoff = INITIAL_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            await self._throttle()
            try:
                async with self._session.get(
                    KROGER_PRODUCTS_URL,
                    headers=headers,
                    params=params,
                    proxy=self._proxy_url,
                ) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                        _LOGGER.warning("Rate limit (429) searching '%s'. Backing off %.1fs", item_name, wait)
                        await asyncio.sleep(wait)
                        backoff *= 2
                        continue

                    if resp.status == 400:
                        body = await resp.json(content_type=None)
                        code = body.get("errors", {}).get("code", "")
                        _LOGGER.debug("Search unavailable for '%s' at %s: %s", item_name, location_id, code)
                        return self._unsorted_result(item_name)

                    if resp.status != 200:
                        _LOGGER.warning("Kroger product search failed for '%s': HTTP %s", item_name, resp.status)
                        return self._unsorted_result(item_name)

                    payload = await resp.json()
                    products = payload.get("data", [])
                    if not products:
                        return self._unsorted_result(item_name)

                    return self._parse_product(products[0], fallback_name=item_name)
            except aiohttp.ClientError as err:
                _LOGGER.warning("Network error searching '%s' (attempt %d): %s", item_name, attempt, err)
                if attempt == MAX_RETRIES:
                    return self._unsorted_result(item_name)
                await asyncio.sleep(backoff)
                backoff *= 2

        return self._unsorted_result(item_name)

    def _parse_product(self, product: dict[str, Any], fallback_name: str) -> dict[str, Any]:
        item_data = product.get("items", [{}])[0] if product.get("items") else {}
        locations = product.get("aisleLocations", [])

        aisle = "UNSORTED"
        if locations:
            # Prefer explicit 'AISLE' designation if present
            for loc in locations:
                desc = loc.get("description", "")
                if "AISLE" in desc.upper():
                    aisle = desc
                    break
            if aisle == "UNSORTED":
                aisle = locations[0].get("description", "UNSORTED")

        price_info = item_data.get("price", {})
        price = price_info.get("regular", 0.0)
        if price == 0.0 and "promo" in price_info:
            price = price_info.get("promo", 0.0)

        product_title = product.get("description", fallback_name)
        image_url = self._extract_image(product)

        return {
            "product_title": product_title,
            "product_name": product_title,
            "aisle": aisle,
            "price": price,
            "image": image_url,
            "image_url": image_url,
            "unmapped": False,
            "note": None,
        }

    @staticmethod
    def _unsorted_result(item_name: str) -> dict[str, Any]:
        return {
            "product_title": item_name,
            "product_name": item_name,
            "aisle": "UNSORTED",
            "price": 0.0,
            "image": "",
            "image_url": "",
            "unmapped": True,
            "note": "No match found. Add exact product ID to mappings.yaml under direct_product_ids.",
        }

    @staticmethod
    def _extract_image(product: dict[str, Any]) -> str:
        for img in product.get("images", []):
            if img.get("perspective") == "front" or img.get("featured"):
                for size in img.get("sizes", []):
                    if size.get("size") in ("thumbnail", "small"):
                        return size.get("url", "")
        images = product.get("images", [])
        if images:
            try:
                return images[0]["sizes"][0]["url"]
            except (KeyError, IndexError):
                pass
        return ""


def build_route(layout_order: list[str]):
    """Return a sort-key function that orders items per the given layout preset.

    Supports:
    - 'NUMERIC_AISLES': covers any numbered aisle.
    - Explicit aisle ranges: 'AISLES_1_3', 'AISLES_4_17', 'AISLE_18', 'AISLES_19_PLUS'
      for fine interleaving of perimeter departments.
    - Named departments: matched longest-first against aisle text.
    - 'UNSORTED': fallback position.
    """
    numeric_index = layout_order.index("NUMERIC_AISLES") if "NUMERIC_AISLES" in layout_order else None
    unsorted_index = layout_order.index("UNSORTED") if "UNSORTED" in layout_order else len(layout_order)

    # Pre-parse range tokens
    range_tokens: dict[tuple[int, int], int] = {}
    for idx, token in enumerate(layout_order):
        if token.startswith("AISLES_") or token.startswith("AISLE_"):
            parts = token.split("_")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                range_tokens[(int(parts[1]), int(parts[2]))] = idx
            elif len(parts) == 2 and parts[1].isdigit():
                range_tokens[(int(parts[1]), int(parts[1]))] = idx
            elif len(parts) == 3 and parts[1].isdigit() and parts[2] == "PLUS":
                range_tokens[(int(parts[1]), 9999)] = idx

    # Sort department names longest-first so specific names match before generic sub-strings
    dept_candidates = sorted(
        [
            (idx, d.upper())
            for idx, d in enumerate(layout_order)
            if not d.startswith("AISLE") and d not in ("NUMERIC_AISLES", "UNSORTED")
        ],
        key=lambda x: len(x[1]),
        reverse=True,
    )

    def _key(item: dict[str, Any]) -> tuple:
        aisle = (item.get("aisle") or "UNSORTED").upper()
        match = re.search(r"\d+", aisle)
        aisle_num = int(match.group()) if match else None

        # Only match numeric range tokens if explicitly an AISLE (e.g. 'AISLE 2' vs 'PRODUCE TABLE 2')
        if aisle_num is not None and "AISLE" in aisle:
            for (low, high), r_idx in range_tokens.items():
                if low <= aisle_num <= high:
                    return (r_idx, aisle_num, aisle)
            if numeric_index is not None:
                return (numeric_index, aisle_num, aisle)

        for idx, dept in dept_candidates:
            if dept in aisle:
                return (idx, 0, aisle)

        # Fallback for strings that have a number but don't contain the word 'AISLE'
        if aisle_num is not None:
            for (low, high), r_idx in range_tokens.items():
                if low <= aisle_num <= high:
                    return (r_idx, aisle_num, aisle)
            if numeric_index is not None:
                return (numeric_index, aisle_num, aisle)

        return (unsorted_index, 0, aisle)

    return _key
