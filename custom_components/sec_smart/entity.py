from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SecSmartCoordinator


class SecSmartEntity(CoordinatorEntity[SecSmartCoordinator]):
    """Base SEC Smart entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="SEVentilation",
            name=coordinator.device_name,
        )

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> Any:
        raise NotImplementedError
