from __future__ import annotations

from typing import Final

DOMAIN: Final = "sec_smart"

CONF_BASE_URL: Final = "base_url"
CONF_DEVICES: Final = "devices"
CONF_ALLOW_CONTROL: Final = "allow_control"
CONF_ALLOW_SETTINGS: Final = "allow_settings"
CONF_POLL_INTERVAL: Final = "poll_interval"

DEFAULT_BASE_URL: Final = "https://api.sec-smart.app/v1"
DEFAULT_POLL_INTERVAL: Final = 60
MIN_POLL_INTERVAL: Final = 30
MAX_POLL_INTERVAL: Final = 600

MODE_OFF: Final = "Fans off"
MODE_BOOST: Final = "Boost ventilation"
MODE_HUMIDITY: Final = "Humidity regulation"
MODE_CO2: Final = "CO2 regulation"
MODE_SCHEDULE: Final = "Timed program"
MODE_SNOOZE: Final = "Snooze"
INACTIVE_PREFIX: Final = "INACTIVE"

PRESET_TO_MODE: Final = {
    "boost": MODE_BOOST,
    "humidity": MODE_HUMIDITY,
    "co2": MODE_CO2,
    "schedule": MODE_SCHEDULE,
    "snooze": MODE_SNOOZE,
}

MANUAL_PERCENTAGES: Final = {1: 16, 2: 33, 3: 50, 4: 67, 5: 83, 6: 100}
