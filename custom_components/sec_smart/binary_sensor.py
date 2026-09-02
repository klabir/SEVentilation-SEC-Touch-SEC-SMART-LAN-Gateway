from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import INACTIVE_PREFIX
from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import active_error, boolean_value, vendor_timers_active


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[BinarySensorEntity] = []
    for coordinator in entry.runtime_data.values():
        entities.extend(
            (
                SecSmartConnectionSensor(coordinator),
                SecSmartFilterSensor(coordinator),
                SecSmartErrorSensor(coordinator),
            )
        )
        for area_key, area in coordinator.data.get("areas", {}).items():
            if not isinstance(area, dict):
                continue
            if str(area.get("mode") or "").upper().startswith(INACTIVE_PREFIX):
                continue
            entities.append(SecSmartVendorTimersSensor(coordinator, area_key, area))
    async_add_entities(entities)


class SecSmartConnectionSensor(SecSmartEntity, BinarySensorEntity):
    _attr_name = "Cloud connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_cloud_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success and bool(
            self.coordinator.endpoint_health.get("areas")
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"endpoints": dict(self.coordinator.endpoint_health)}


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
        return boolean_value(self.native_value)


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


class SecSmartVendorTimersSensor(SecSmartEntity, BinarySensorEntity):
    _attr_name = None

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._area_key = area_key
        label = str(area.get("label") or area_key).strip()
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}_vendor_timers_active"
        self._attr_name = f"{label} vendor timers active"

    @property
    def is_on(self) -> bool | None:
        area = self.coordinator.data.get("areas", {}).get(self._area_key)
        return vendor_timers_active(area)
