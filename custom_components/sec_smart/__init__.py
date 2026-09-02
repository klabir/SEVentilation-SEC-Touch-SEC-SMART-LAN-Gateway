from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SecSmartApi
from .const import (
    CONF_ALLOW_CONTROL,
    CONF_ALLOW_SETTINGS,
    CONF_BASE_URL,
    CONF_DEVICES,
    CONF_POLL_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import SecSmartCoordinator

type SecSmartConfigEntry = ConfigEntry[dict[str, SecSmartCoordinator]]


def _requested_platforms(entry: ConfigEntry[Any]) -> list[Platform]:
    platforms: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
    if entry.options.get(CONF_ALLOW_CONTROL, False):
        platforms.extend((Platform.FAN, Platform.SWITCH))
    if entry.options.get(CONF_ALLOW_SETTINGS, False):
        platforms.extend((Platform.NUMBER, Platform.SWITCH, Platform.BUTTON))
    return list(dict.fromkeys(platforms))


async def async_setup_entry(hass: HomeAssistant, entry: SecSmartConfigEntry) -> bool:
    """Set up SEC Smart from a config entry."""
    api = SecSmartApi(
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        entry.data[CONF_TOKEN],
        async_get_clientsession(hass),
    )
    interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    coordinators: dict[str, SecSmartCoordinator] = {}
    for device in entry.data[CONF_DEVICES]:
        coordinator = SecSmartCoordinator(hass, api, device, interval)
        await coordinator.async_config_entry_first_refresh()
        coordinators[coordinator.device_id] = coordinator

    entry.runtime_data = coordinators
    platforms = _requested_platforms(entry)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = platforms
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SecSmartConfigEntry) -> bool:
    """Unload SEC Smart."""
    platforms = hass.data.get(DOMAIN, {}).get(
        entry.entry_id, _requested_platforms(entry)
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
