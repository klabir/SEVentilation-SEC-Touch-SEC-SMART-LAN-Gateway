from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SecSmartCoordinator

TO_REDACT = {
    "id",
    "token",
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
            async_redact_data(coordinator.data, TO_REDACT)
            for coordinator in entry.runtime_data.values()
        ],
    }
