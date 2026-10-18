"""Config flow for the Kroger & Ralphs Route Planner integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KrogerAPIClient, KrogerApiError, KrogerAuthError, ProductSearchUnavailable
from .const import (
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
    DEFAULT_IGNORE_ITEMS,
    DEFAULT_LAYOUT_PRESET,
    DEFAULT_TODO_ENTITY,
    DEFAULT_TYPO_FIXES,
    DOMAIN,
    STORE_PRESETS,
)
from .mapping_utils import list_to_lines, mapping_to_lines

_LOGGER = logging.getLogger(__name__)


def _default_mapping_options() -> dict[str, str]:
    return {
        CONF_IGNORE_ITEMS: list_to_lines(DEFAULT_IGNORE_ITEMS),
        CONF_TYPO_FIXES: mapping_to_lines(DEFAULT_TYPO_FIXES),
        CONF_DIRECT_PRODUCT_IDS: "",
    }


class KrogerRouteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kroger & Ralphs Route Planner."""

    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._locations: dict[str, str] = {}
        self._location_id: str | None = None
        self._store_name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = KrogerAPIClient(session, user_input[CONF_CLIENT_ID], user_input[CONF_CLIENT_SECRET])
            try:
                await client.async_get_token()
            except KrogerAuthError:
                errors["base"] = "invalid_auth"
            except KrogerApiError:
                errors["base"] = "cannot_connect"
            else:
                self._client_id = user_input[CONF_CLIENT_ID].strip()
                self._client_secret = user_input[CONF_CLIENT_SECRET].strip()
                return await self.async_step_store()

        schema = vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_store(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None and CONF_LOCATION_ID in user_input and user_input.get(CONF_LOCATION_ID):
            location_id = str(user_input[CONF_LOCATION_ID]).strip()
            session = async_get_clientsession(self.hass)
            client = KrogerAPIClient(session, self._client_id, self._client_secret)
            try:
                await client.async_validate_product_search(location_id)
            except ProductSearchUnavailable:
                errors["base"] = "product_search_unavailable"
            except KrogerApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(location_id)
                self._abort_if_unique_id_configured()
                self._location_id = location_id
                self._store_name = self._locations.get(location_id, location_id)
                return await self.async_step_todo()

        elif user_input is not None and user_input.get("zip_code"):
            session = async_get_clientsession(self.hass)
            client = KrogerAPIClient(session, self._client_id, self._client_secret)
            try:
                self._locations = await client.async_get_locations(user_input["zip_code"])
            except KrogerApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._locations:
                    errors["base"] = "no_stores_found"

        if self._locations and not errors:
            schema = vol.Schema({vol.Required(CONF_LOCATION_ID): vol.In(self._locations)})
            return self.async_show_form(step_id="store", data_schema=schema, errors=errors)

        schema = vol.Schema(
            {
                vol.Optional("zip_code"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_LOCATION_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
            }
        )
        return self.async_show_form(step_id="store", data_schema=schema, errors=errors)

    async def async_step_todo(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            todo_entity = user_input.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY)
            layout_preset = user_input.get(CONF_LAYOUT_PRESET, DEFAULT_LAYOUT_PRESET)
            options = {
                CONF_TODO_ENTITY: todo_entity,
                CONF_LAYOUT_PRESET: layout_preset,
                CONF_CUSTOM_LAYOUT: "",
                **_default_mapping_options(),
            }
            return self.async_create_entry(
                title=f"Kroger - {self._store_name}",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_LOCATION_ID: self._location_id,
                    CONF_STORE_NAME: self._store_name,
                    CONF_TODO_ENTITY: todo_entity,
                },
                options=options,
            )

        preset_options = {k: v["name"] for k, v in STORE_PRESETS.items() if not v.get("hidden")}
        schema = vol.Schema(
            {
                vol.Required(CONF_TODO_ENTITY, default=DEFAULT_TODO_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="todo")
                ),
                vol.Required(CONF_LAYOUT_PRESET, default=DEFAULT_LAYOUT_PRESET): vol.In(preset_options),
            }
        )
        return self.async_show_form(step_id="todo", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "KrogerOptionsFlowHandler":
        return KrogerOptionsFlowHandler()


class KrogerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for an existing Kroger & Ralphs Route Planner entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            # Preserve any unknown existing option keys
            new_options = dict(self.config_entry.options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        options = self.config_entry.options
        defaults = _default_mapping_options()
        preset_options = {k: v["name"] for k, v in STORE_PRESETS.items() if not v.get("hidden")}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TODO_ENTITY,
                    default=options.get(
                        CONF_TODO_ENTITY,
                        self.config_entry.data.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY),
                    ),
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="todo")),
                vol.Required(
                    CONF_LAYOUT_PRESET,
                    default=options.get(CONF_LAYOUT_PRESET, DEFAULT_LAYOUT_PRESET),
                ): vol.In(preset_options),
                vol.Optional(
                    CONF_CUSTOM_LAYOUT,
                    default=options.get(CONF_CUSTOM_LAYOUT, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, multiline=False)
                ),
                vol.Optional(
                    CONF_IGNORE_ITEMS,
                    default=options.get(CONF_IGNORE_ITEMS, defaults[CONF_IGNORE_ITEMS]),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, multiline=True)
                ),
                vol.Optional(
                    CONF_TYPO_FIXES,
                    default=options.get(CONF_TYPO_FIXES, defaults[CONF_TYPO_FIXES]),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, multiline=True)
                ),
                vol.Optional(
                    CONF_DIRECT_PRODUCT_IDS,
                    default=options.get(CONF_DIRECT_PRODUCT_IDS, defaults[CONF_DIRECT_PRODUCT_IDS]),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, multiline=True)
                ),
                vol.Optional(
                    CONF_PROXY_URL,
                    default=options.get(CONF_PROXY_URL, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
