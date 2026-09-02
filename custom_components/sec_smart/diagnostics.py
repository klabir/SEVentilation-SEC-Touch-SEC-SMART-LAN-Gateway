from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SecSmartCoordinator

TO_REDACT = {
    "id",
    "deviceid",
    "name",
    "label",
    "token",
    "timers",
    "serial",
    "serialNumber",
    "mac",
    "macAddress",
    "ip",
    "ipAddress",
    "actualMessage",
    "lastMessage",
    "articleCode",
    "articleCodeTouchPanel1",
    "articleCodeTouchPanel2",
    "articleCodeTouchPanel3",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
) -> dict[str, Any]:
    """Return redacted SEC Smart diagnostics."""
    return {
        "integration": DOMAIN,
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": [
            async_redact_data(
                {
                    "data": coordinator.data,
                    "endpoint_health": coordinator.endpoint_health,
                    "last_successful_update": coordinator.last_successful_update,
                    "last_commands": coordinator.area_commands,
                },
                TO_REDACT,
            )
            for coordinator in entry.runtime_data.values()
        ],
    }
