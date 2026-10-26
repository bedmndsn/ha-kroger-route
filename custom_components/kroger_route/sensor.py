"""Sensor platform for the Kroger & Ralphs Route Planner integration."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LAYOUT_PRESET,
    CONF_LOCATION_ID,
    CONF_STORE_NAME,
    DEFAULT_LAYOUT_PRESET,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Kroger route sensor for this config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KrogerRouteSensor(coordinator, entry)])


class KrogerRouteSensor(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Representation of a store's sorted shopping route."""

    _attr_icon = "mdi:cart-outline"
    _attr_has_entity_name = False

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        location_id = entry.data[CONF_LOCATION_ID]
        store_name = entry.data.get(CONF_STORE_NAME, location_id)
        self._attr_unique_id = f"kroger_route_{location_id}"
        self._attr_name = f"Kroger Route ({store_name})"
        location_slug = re.sub(r"[^a-z0-9_]", "_", location_id.lower())
        self.entity_id = f"sensor.kroger_route_{location_slug}"

        self._restored_items: list[dict[str, Any]] = []
        self._restored_total_cost: str = "0.00"
        self._restored_location_id: str | None = location_id
        self._restored_todo_entity: str | None = coordinator.todo_entity
        self._restored_preset_used: str | None = entry.options.get(CONF_LAYOUT_PRESET, DEFAULT_LAYOUT_PRESET)
        self._restored_unmapped: list[str] = []
        self._restored_last_sync: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and (self.coordinator.data is None):
            attrs = last_state.attributes
            self._restored_items = attrs.get("items", [])
            self._restored_total_cost = attrs.get("total_estimated_cost", "0.00")
            self._restored_location_id = attrs.get("location_id", self._restored_location_id)
            self._restored_todo_entity = attrs.get("todo_entity", self._restored_todo_entity)
            self._restored_preset_used = attrs.get("preset_used", self._restored_preset_used)
            self._restored_unmapped = attrs.get("unmapped_items", [])
            self._restored_last_sync = attrs.get("last_sync")

    @property
    def native_value(self) -> int:
        data = self.coordinator.data or {}
        items = data.get("items")
        if items is not None:
            return len([i for i in items if not i.get("completed")])
        return len([i for i in self._restored_items if not i.get("completed")])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        if data:
            return {
                "items": data.get("items", []),
                "total_estimated_cost": data.get("total_estimated_cost", "0.00"),
                "location_id": data.get("location_id"),
                "todo_entity": data.get("todo_entity"),
                "preset_used": data.get("preset_used"),
                "unmapped_items": data.get("unmapped_items", []),
                "last_sync": data.get("last_sync"),
            }

        return {
            "items": self._restored_items,
            "total_estimated_cost": self._restored_total_cost,
            "location_id": self._restored_location_id,
            "todo_entity": self._restored_todo_entity,
            "preset_used": self._restored_preset_used,
            "unmapped_items": self._restored_unmapped,
            "last_sync": self._restored_last_sync,
        }
