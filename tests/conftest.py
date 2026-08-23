"""Fixtures for the NetTest ČTÚ tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_CLIENT_UUID,
    CONF_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_CONTROL_SERVER_URL,
    DOMAIN,
)
from custom_components.ctu_nettest.rmbt_runner import RmbtResult

CLIENT_UUID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the custom integration in every test."""
    return


@pytest.fixture
def result() -> RmbtResult:
    """Return a measurement result mirroring a real ČTÚ run."""
    return RmbtResult(
        timestamp=datetime(2026, 8, 18, 8, 22, 21, tzinfo=UTC),
        client_uuid=CLIENT_UUID,
        download_mbps=194.56,
        upload_mbps=208.05,
        ping_ms=9.65,
        ping_median_ms=10.81,
        jitter_ms=1.97,
        server_address="m01v4-nettest.ctu.gov.cz",
        download_threads=3,
        upload_threads=3,
        bytes_download=253939712,
        bytes_upload=266586112,
        duration_seconds=10,
        ping_count=44,
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a configured entry with automatic measurement disabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="NetTest ČTÚ",
        version=2,
        data={
            CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
            CONF_CLIENT_UUID: CLIENT_UUID,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_AUTO_UPDATE_ENABLED: False,
        },
    )


@pytest.fixture
def mock_run_test(result: RmbtResult) -> Generator[AsyncMock]:
    """Patch the blocking runner so no traffic is generated."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test", return_value=result
    ) as mocked:
        yield mocked


@pytest.fixture
def mock_register_client() -> Generator[AsyncMock]:
    """Patch the control server registration used by the config flow."""
    with patch(
        "custom_components.ctu_nettest.config_flow.register_client",
        return_value=CLIENT_UUID,
    ) as mocked:
        yield mocked
