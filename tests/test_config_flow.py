"""Tests for the NetTest ČTÚ config flow."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_AVERAGE_SAMPLE_COUNT,
    CONF_CLIENT_UUID,
    CONF_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_AVERAGE_SAMPLE_COUNT,
    DEFAULT_CONTROL_SERVER_URL,
    DOMAIN,
)
from custom_components.ctu_nettest.rmbt_runner import RmbtError

from .conftest import CLIENT_UUID

USER_INPUT = {
    CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_HOURS: 12,
    CONF_AUTO_UPDATE_ENABLED: True,
}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_register_client
) -> None:
    """The happy path registers a client and stores its UUID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch("custom_components.ctu_nettest.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NetTest ČTÚ"
    assert result["data"] == {
        CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
        CONF_UPDATE_INTERVAL_HOURS: 12,
        CONF_AUTO_UPDATE_ENABLED: True,
        CONF_AVERAGE_SAMPLE_COUNT: DEFAULT_AVERAGE_SAMPLE_COUNT,
        CONF_CLIENT_UUID: CLIENT_UUID,
    }


async def test_user_flow_rejects_url_without_scheme(
    hass: HomeAssistant, mock_register_client
) -> None:
    """A bare host name is refused before any network call happens."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_CONTROL_SERVER_URL: "nettest.ctu.gov.cz"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CONTROL_SERVER_URL: "invalid_url"}
    mock_register_client.assert_not_called()


async def test_user_flow_handles_unreachable_server(hass: HomeAssistant) -> None:
    """An unreachable control server keeps the form open with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with patch(
        "custom_components.ctu_nettest.config_flow.register_client",
        side_effect=RmbtError("HTTP 502"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_recovers_after_error(
    hass: HomeAssistant, mock_register_client
) -> None:
    """After fixing the URL the same flow can be completed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_CONTROL_SERVER_URL: "not-a-url"}
    )
    assert result["errors"] == {CONF_CONTROL_SERVER_URL: "invalid_url"}

    with patch("custom_components.ctu_nettest.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_only_one_entry_allowed(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_register_client
) -> None:
    """The manifest declares single_config_entry."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_updates_schedule(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_register_client,
    mock_run_test,
) -> None:
    """Changing the interval is stored in the entry options."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
            CONF_UPDATE_INTERVAL_HOURS: 6,
            CONF_AUTO_UPDATE_ENABLED: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_UPDATE_INTERVAL_HOURS] == 6
    assert config_entry.options[CONF_AUTO_UPDATE_ENABLED] is True


async def test_options_flow_does_not_start_a_measurement(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_register_client,
    mock_run_test,
) -> None:
    """Saving options must not trigger a load test."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    mock_run_test.reset_mock()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
            CONF_UPDATE_INTERVAL_HOURS: 6,
            CONF_AUTO_UPDATE_ENABLED: True,
        },
    )
    await hass.async_block_till_done()

    mock_run_test.assert_not_called()
