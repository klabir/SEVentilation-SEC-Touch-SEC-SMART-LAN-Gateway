from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import active_error


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        entity
        for coordinator in entry.runtime_data.values()
        for entity in (
            SecSmartFilterSensor(coordinator),
            SecSmartErrorSensor(coordinator),
        )
    )


class SecSmartFilterSensor(SecSmartEntity, BinarySensorEntity):
    _attr_name = "Filter replacement"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_filter_problem"

    @property
    def native_value(self) -> Any:
        notifications = self.coordinator.data.get("notifications")
        return notifications.get("filterRanOut") if isinstance(notifications, dict) else None

    @property
    def is_on(self) -> bool | None:
        value = self.native_value
        return bool(value) if value is not None else None


class SecSmartErrorSensor(SecSmartEntity, BinarySensorEntity):
    _attr_name = "Active error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_active_error"

    @property
    def native_value(self) -> Any:
        return active_error(self.coordinator.data)

    @property
    def is_on(self) -> bool | None:
        value = self.native_value
        return bool(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        notifications = self.coordinator.data.get("notifications")
        if not isinstance(notifications, dict):
            return None
        return {
            "actual_message": notifications.get("actualMessage"),
            "last_message": notifications.get("lastMessage"),
        }
