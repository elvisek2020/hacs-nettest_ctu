"""Constants for the NetTest ČTÚ integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ctu_nettest"

# Bumped when stored settings change shape; see async_migrate_entry.
CONFIG_ENTRY_VERSION: Final = 2

CONF_CONTROL_SERVER_URL: Final = "control_server_url"
CONF_UPDATE_INTERVAL_MINUTES: Final = "update_interval_minutes"
CONF_AUTO_UPDATE_ENABLED: Final = "auto_update_enabled"
CONF_CLIENT_UUID: Final = "client_uuid"
CONF_AVERAGE_SAMPLE_COUNT: Final = "average_sample_count"

# Entries created before the interval moved from hours to minutes.
LEGACY_CONF_UPDATE_INTERVAL_HOURS: Final = "update_interval_hours"

DEFAULT_CONTROL_SERVER_URL: Final = "https://nettest.ctu.gov.cz/RMBTControlServer"
DEFAULT_UPDATE_INTERVAL_MINUTES: Final = 30
# The repeated measurement mode on the ČTÚ website clamps its own interval to
# at least 10 minutes, so we do not go below what ČTÚ allows its own users.
MIN_UPDATE_INTERVAL_MINUTES: Final = 10
MAX_UPDATE_INTERVAL_MINUTES: Final = 10080

DEFAULT_AVERAGE_SAMPLE_COUNT: Final = 10
MIN_AVERAGE_SAMPLE_COUNT: Final = 2
MAX_AVERAGE_SAMPLE_COUNT: Final = 100

STORAGE_VERSION: Final = 1

# A full measurement is a pre-test plus a 10 s download and a 10 s upload phase.
# The cap only guards against a stalled server, it is not a target runtime.
TEST_TIMEOUT_SECONDS: Final = 180

SERVICE_RUN_TEST: Final = "run_test"

ATTRIBUTION: Final = "Měřeno proti infrastruktuře NetTest ČTÚ (nettest.ctu.gov.cz)"

DISCLAIMER: Final = (
    "Neoficiální integrace bez vazby na ČTÚ. Výsledek je orientační a není "
    "certifikovaným měřením pro reklamaci u poskytovatele — to vyžaduje kabelové "
    "připojení přímo do koncového zařízení a musí proběhnout přes oficiální "
    "aplikaci nebo web ČTÚ."
)
