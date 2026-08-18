"""Config flow for the ČTÚ NetTest integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_CLIENT_UUID,
    CONF_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_CONTROL_SERVER_URL,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DISCLAIMER,
    DOMAIN,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_UPDATE_INTERVAL_HOURS,
)
from .coordinator import CtuNetTestConfigEntry, entry_settings
from .rmbt_runner import RmbtError, register_client

_LOGGER = logging.getLogger(__name__)

TITLE = "ČTÚ NetTest"


def _schema(defaults: dict[str, Any], *, with_url: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_url:
        fields[
            vol.Required(
                CONF_CONTROL_SERVER_URL,
                default=defaults.get(
                    CONF_CONTROL_SERVER_URL, DEFAULT_CONTROL_SERVER_URL
                ),
            )
        ] = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
    fields[
        vol.Required(
            CONF_UPDATE_INTERVAL_HOURS,
            default=defaults.get(
                CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
            ),
        )
    ] = NumberSelector(
        NumberSelectorConfig(
            min=MIN_UPDATE_INTERVAL_HOURS,
            max=MAX_UPDATE_INTERVAL_HOURS,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="h",
        )
    )
    fields[
        vol.Required(
            CONF_AUTO_UPDATE_ENABLED,
            default=defaults.get(CONF_AUTO_UPDATE_ENABLED, True),
        )
    ] = BooleanSelector()
    return vol.Schema(fields)


def _normalise(user_input: dict[str, Any]) -> dict[str, Any]:
    """Coerce selector output into the types stored in the entry."""
    normalised = dict(user_input)
    normalised[CONF_UPDATE_INTERVAL_HOURS] = int(normalised[CONF_UPDATE_INTERVAL_HOURS])
    if CONF_CONTROL_SERVER_URL in normalised:
        normalised[CONF_CONTROL_SERVER_URL] = (
            normalised[CONF_CONTROL_SERVER_URL].strip().rstrip("/")
        )
    return normalised


def _url_is_valid(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


class CtuNetTestConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the control server and the measurement schedule."""
        errors: dict[str, str] = {}

        if user_input is not None:
            settings = _normalise(user_input)
            url = settings[CONF_CONTROL_SERVER_URL]
            if not _url_is_valid(url):
                errors[CONF_CONTROL_SERVER_URL] = "invalid_url"
            else:
                try:
                    client_uuid = await self.hass.async_add_executor_job(
                        register_client, url
                    )
                except RmbtError as err:
                    _LOGGER.debug("Control server %s unreachable: %s", url, err)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=TITLE,
                        data={**settings, CONF_CLIENT_UUID: client_uuid},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, with_url=True),
            errors=errors,
            description_placeholders={"disclaimer": DISCLAIMER},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: CtuNetTestConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return CtuNetTestOptionsFlow()


class CtuNetTestOptionsFlow(OptionsFlow):
    """Allow the schedule and the control server to be changed later.

    The entry is not reloaded on purpose: the coordinator picks the new interval
    up in place, so saving options never kicks off an unexpected measurement.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            settings = _normalise(user_input)
            url = settings[CONF_CONTROL_SERVER_URL]
            if not _url_is_valid(url):
                errors[CONF_CONTROL_SERVER_URL] = "invalid_url"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        register_client,
                        url,
                        self.config_entry.data.get(CONF_CLIENT_UUID),
                    )
                except RmbtError as err:
                    _LOGGER.debug("Control server %s unreachable: %s", url, err)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(data=settings)

        defaults = user_input or entry_settings(self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults, with_url=True),
            errors=errors,
            description_placeholders={"disclaimer": DISCLAIMER},
        )
