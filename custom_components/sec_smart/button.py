from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import numeric_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        SecSmartFilterResetButton(coordinator)
        for coordinator in entry.runtime_data.values()
    )


class SecSmartFilterResetButton(SecSmartEntity, ButtonEntity):
    _attr_name = "Reset filter life"
    _attr_icon = "mdi:air-filter"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_filter_reset"

    async def async_press(self) -> None:
        settings = self.coordinator.data.get("settings")
        filter_settings = settings.get("filter") if isinstance(settings, dict) else None
        days = (
            numeric_value(filter_settings.get("maxRunTime"), integer=True)
            if isinstance(filter_settings, dict)
            else None
        )
        if days is None:
            raise HomeAssistantError("SEC Smart filter settings are unavailable")
        await self.coordinator.async_set_filter_runtime(days, reset=True)
