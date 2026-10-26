"""The Kroger & Ralphs Route Planner integration."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any

import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KrogerAPIClient, build_route
from .const import (
    ATTR_FORCE_REFRESH,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CUSTOM_LAYOUT,
    CONF_DIRECT_PRODUCT_IDS,
    CONF_IGNORE_ITEMS,
    CONF_LAYOUT_PRESET,
    CONF_LOCATION_ID,
    CONF_PROXY_URL,
    CONF_STORE_NAME,
    CONF_TODO_ENTITY,
    CONF_TYPO_FIXES,
    DEFAULT_CACHE_TTL,
    DEFAULT_IGNORE_ITEMS,
    DEFAULT_LAYOUT_PRESET,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TODO_ENTITY,
    DEFAULT_TYPO_FIXES,
    DOMAIN,
    PLATFORMS,
    SERVICE_PROCESS_LIST,
    SERVICE_REFRESH_ROUTE,
    STORE_PRESETS,
)
from .mapping_utils import lines_to_list, lines_to_mapping

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kroger & Ralphs Route Planner from a config entry."""
    session = async_get_clientsession(hass)
    proxy_url = entry.options.get(CONF_PROXY_URL, entry.data.get(CONF_PROXY_URL))
    client = KrogerAPIClient(
        session=session,
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        proxy_url=proxy_url,
    )

    coordinator = KrogerRouteCoordinator(hass, client, entry)
    await hass.async_add_executor_job(coordinator.load_mappings)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Initial route refresh deferred: %s", err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Automatically trigger a route rebuild whenever the to-do list changes or a todo service is called
    @callback
    def _handle_todo_state_change(event: Any) -> None:
        hass.async_create_task(coordinator.async_refresh_route())

    entry.async_on_unload(
        async_track_state_change_event(hass, [coordinator.todo_entity], _handle_todo_state_change)
    )

    @callback
    def _handle_todo_service_call(event: Any) -> None:
        data = event.data or {}
        if data.get("domain") != "todo":
            return
        service_data = data.get("service_data") or {}
        target = data.get("target") or {}
        entity_ids = service_data.get("entity_id") or target.get("entity_id")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        elif not isinstance(entity_ids, (list, tuple, set)):
            entity_ids = []

        if coordinator.todo_entity in entity_ids:
            hass.async_create_task(coordinator.async_refresh_route())

    entry.async_on_unload(
        hass.bus.async_listen("call_service", _handle_todo_service_call)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_route_refresh_service(call: ServiceCall) -> None:
        force = call.data.get(ATTR_FORCE_REFRESH, False)
        target_location = call.data.get(CONF_LOCATION_ID)
        for entry_coordinator in hass.data[DOMAIN].values():
            if target_location and entry_coordinator.location_id != target_location:
                continue
            await entry_coordinator.async_refresh_route(force_refresh=force)

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_ROUTE):
        hass.services.async_register(DOMAIN, SERVICE_REFRESH_ROUTE, _handle_route_refresh_service)

    # process_list is a legacy alias of refresh_route preserved for backwards compatibility with existing automations.
    if not hass.services.has_service(DOMAIN, SERVICE_PROCESS_LIST):
        hass.services.async_register(DOMAIN, SERVICE_PROCESS_LIST, _handle_route_refresh_service)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. layout preset or todo entity)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            if hass.services.has_service(DOMAIN, SERVICE_REFRESH_ROUTE):
                hass.services.async_remove(DOMAIN, SERVICE_REFRESH_ROUTE)
            if hass.services.has_service(DOMAIN, SERVICE_PROCESS_LIST):
                hass.services.async_remove(DOMAIN, SERVICE_PROCESS_LIST)
    return unload_ok


class KrogerRouteCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches todo items and builds the sorted shopping route."""

    def __init__(self, hass: HomeAssistant, client: KrogerAPIClient, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)
        self.client = client
        self.entry = entry
        self._existing_items: dict[str, dict[str, Any]] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._mappings: dict[str, Any] = {
            "ignore_items": set(),
            "typos": {},
            "direct_product_ids": {},
        }
        # Mappings loaded via executor during setup/refresh to avoid blocking the event loop.

    def get_mappings_file_path(self) -> str:
        """Find the mappings.yaml file path, preferring /config/mappings.yaml."""
        user_path = self.hass.config.path("mappings.yaml")
        if os.path.exists(user_path):
            return user_path
        component_path = os.path.join(os.path.dirname(__file__), "mappings.yaml")
        return component_path

    def load_mappings(self) -> None:
        """Load user-configurable mappings and combine with default ignore list."""
        ignore_set = {item.strip().lower() for item in DEFAULT_IGNORE_ITEMS}
        typos_dict = dict(DEFAULT_TYPO_FIXES)
        direct_ids_dict: dict[str, str] = {}

        mappings_path = self.get_mappings_file_path()
        if os.path.exists(mappings_path):
            try:
                with open(mappings_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    data = {}

                ignore_items = data.get("ignore_items") or []
                typos = data.get("typos") or {}
                direct_ids = data.get("direct_product_ids") or {}

                for ign in ignore_items:
                    if ign:
                        ignore_set.add(str(ign).strip().lower())

                if isinstance(typos, dict):
                    for typo, fix in typos.items():
                        if typo and fix:
                            typos_dict[str(typo).strip().lower()] = str(fix).strip()

                if isinstance(direct_ids, dict):
                    for item_name, pid in direct_ids.items():
                        if item_name and pid:
                            direct_ids_dict[str(item_name).strip().lower()] = str(pid).strip()

                _LOGGER.debug(
                    "Loaded mappings from %s: %d ignores, %d typos, %d direct IDs",
                    mappings_path,
                    len(ignore_set),
                    len(typos_dict),
                    len(direct_ids_dict),
                )
            except Exception as err:
                _LOGGER.error("Failed to parse mappings file %s: %s", mappings_path, err)

        # Options from Configure UI override/extend YAML + defaults
        options = self.entry.options if self.entry else {}
        for ign in lines_to_list(options.get(CONF_IGNORE_ITEMS)):
            ignore_set.add(ign)
        for typo, fix in lines_to_mapping(options.get(CONF_TYPO_FIXES)).items():
            typos_dict[typo] = fix
        for name, pid in lines_to_mapping(options.get(CONF_DIRECT_PRODUCT_IDS)).items():
            direct_ids_dict[name] = pid

        self._mappings = {
            "ignore_items": ignore_set,
            "typos": typos_dict,
            "direct_product_ids": direct_ids_dict,
        }

    @property
    def location_id(self) -> str:
        return self.entry.data[CONF_LOCATION_ID]

    @property
    def store_name(self) -> str:
        return self.entry.data[CONF_STORE_NAME]

    @property
    def todo_entity(self) -> str:
        return self.entry.options.get(
            CONF_TODO_ENTITY, self.entry.data.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY)
        )

    @property
    def layout_order(self) -> list[str]:
        preset_key = self.entry.options.get(CONF_LAYOUT_PRESET, DEFAULT_LAYOUT_PRESET)
        custom_layout = self.entry.options.get(CONF_CUSTOM_LAYOUT, "")
        if preset_key == "custom" and custom_layout:
            return [part.strip() for part in custom_layout.split(",") if part.strip()]
        return STORE_PRESETS.get(preset_key, STORE_PRESETS[DEFAULT_LAYOUT_PRESET])["order"]

    async def async_refresh_route(self, force_refresh: bool = False) -> None:
        """Manually trigger route rebuild."""
        if force_refresh:
            self._existing_items.clear()
            self._cache_timestamps.clear()
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        await self.hass.async_add_executor_job(self.load_mappings)
        try:
            raw_items = await self._async_fetch_todo_items()
        except Exception as err:
            raise UpdateFailed(f"Error fetching todo items from {self.todo_entity}: {err}") from err

        unique_items = await self._async_deduplicate_todo_items(raw_items)

        ignore_items = self._mappings["ignore_items"]
        typos = self._mappings["typos"]
        direct_product_ids = self._mappings["direct_product_ids"]

        processed_items: list[dict[str, Any]] = []
        unmapped_items: list[str] = []
        total_cost = 0.0

        for item in unique_items:
            name = item.get("summary", "").strip()
            status = item.get("status", "needs_action")
            uid = item.get("uid", "")
            orig_lower = name.lower()
            clean_lower = orig_lower.strip(" -•*[]#")

            if not name or orig_lower in ignore_items or clean_lower in ignore_items:
                continue

            cached = self._existing_items.get(orig_lower)
            cache_age = time.monotonic() - self._cache_timestamps.get(orig_lower, 0.0)
            if cached and cached.get("aisle") != "UNSORTED" and cache_age < DEFAULT_CACHE_TTL.total_seconds():
                aisle = cached["aisle"]
                price = cached["price"]
                product_name = cached.get("product_name") or cached.get("product_title", orig_lower)
                image_url = cached.get("image_url") or cached.get("image", "")
                unmapped = cached.get("unmapped", False)
                note = cached.get("note")
            else:
                search_name = typos.get(orig_lower, typos.get(clean_lower, name))
                direct_id = (
                    direct_product_ids.get(search_name.lower())
                    or direct_product_ids.get(orig_lower)
                    or direct_product_ids.get(clean_lower)
                )

                if direct_id:
                    result = await self.client.async_get_product_by_id(direct_id, self.location_id)
                else:
                    result = None

                if not result:
                    result = await self.client.async_search_product(search_name, self.location_id)

                aisle = result["aisle"]
                price = result["price"]
                product_name = result["product_name"]
                image_url = result.get("image_url", "")
                unmapped = result.get("unmapped", False)
                note = result.get("note")
                if aisle != "UNSORTED":
                    self._cache_timestamps[orig_lower] = time.monotonic()

            if unmapped:
                unmapped_items.append(name)

            processed_items.append(
                {
                    "uid": uid,
                    "name": name,
                    "raw_search": name,
                    "product_name": product_name,
                    "aisle": aisle,
                    "price": price,
                    "image_url": image_url,
                    "status": status,
                    "completed": status == "completed",
                    "unmapped": unmapped,
                    "note": note,
                }
            )
            total_cost += price or 0.0

        sort_key = build_route(self.layout_order)
        processed_items.sort(key=sort_key)

        self._existing_items = {i["name"].lower(): i for i in processed_items}
        self._cache_timestamps = {
            name: ts for name, ts in self._cache_timestamps.items() if name in self._existing_items
        }

        return {
            "items": processed_items,
            "total_estimated_cost": f"{total_cost:.2f}",
            "location_id": self.location_id,
            "todo_entity": self.todo_entity,
            "preset_used": self.entry.options.get(CONF_LAYOUT_PRESET, DEFAULT_LAYOUT_PRESET),
            "unmapped_items": unmapped_items,
            "last_sync": datetime.now(timezone.utc).isoformat(),
        }

    async def _async_fetch_todo_items(self) -> list[dict[str, Any]]:
        response = await self.hass.services.async_call(
            "todo",
            "get_items",
            {"entity_id": self.todo_entity},
            blocking=True,
            return_response=True,
        )
        if not response or not isinstance(response, dict):
            return []

        if self.todo_entity in response:
            return response[self.todo_entity].get("items", [])
        if "service_response" in response and self.todo_entity in response["service_response"]:
            return response["service_response"][self.todo_entity].get("items", [])
        return []

    async def _async_deduplicate_todo_items(
        self,
        raw_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deduplicate items on the HA todo list, purging exact duplicates and keeping first by name."""
        seen_keys: set[tuple[str, str]] = set()
        seen_names: set[str] = set()
        uids_to_remove: list[str] = []
        unique_items: list[dict[str, Any]] = []

        for item in raw_items:
            uid = item.get("uid")
            name = item.get("summary", "").strip()
            name_lower = name.lower()
            status = item.get("status", "needs_action")
            if not name:
                continue

            # Purge duplicate entries with identical (name, status) from the HA todo list
            key = (name_lower, status)
            if key in seen_keys:
                if uid:
                    uids_to_remove.append(uid)
                continue
            seen_keys.add(key)

            # In the final route, first occurrence by name wins
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)
            unique_items.append(item)

        for uid in uids_to_remove:
            try:
                await self.hass.services.async_call(
                    "todo",
                    "remove_item",
                    {"entity_id": self.todo_entity, "item": [uid]},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.warning("Failed to remove duplicate todo UID %s: %s", uid, err)

        return unique_items
