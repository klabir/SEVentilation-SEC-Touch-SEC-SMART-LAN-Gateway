from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SecSmartCoordinator


class SecSmartEntity(CoordinatorEntity[SecSmartCoordinator]):
    """Base SEC Smart entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        gateway = coordinator.data.get("gateway") or {}
        controller = coordinator.data.get("controller") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="SEVentilation",
            name=coordinator.device_name,
            model=str(gateway.get("articleCode") or "SEC-SMART LAN Gateway"),
            sw_version=str(gateway.get("firmwareVersion") or "unknown"),
            hw_version=str(controller.get("articleCode") or "unknown"),
        )
