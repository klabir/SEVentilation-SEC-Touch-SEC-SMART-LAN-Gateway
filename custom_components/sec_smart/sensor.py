from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, INACTIVE_PREFIX
from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import numeric_value, telemetry_value


@dataclass(frozen=True, kw_only=True)
class SensorDescription:
    key: str
    name: str
    extractor: Callable[[dict[str, Any]], Any]
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


SENSORS = (
    SensorDescription(
        key="co2",
        name="CO2",
        extractor=lambda data: numeric_value(
            telemetry_value(data, "co2"), integer=True
        ),
        unit=UnitOfRatio.PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDescription(
        key="humidity",
        name="Humidity",
        extractor=lambda data: numeric_value(
            telemetry_value(data, "humidity"), integer=True
        ),
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDescription(
        key="indoor_temperature",
        name="Indoor temperature",
        extractor=lambda data: numeric_value(telemetry_value(data, "Ti")),
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDescription(
        key="outdoor_temperature",
        name="Outdoor temperature",
        extractor=lambda data: numeric_value(telemetry_value(data, "Ta")),
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDescription(
        key="filter_life",
        name="Filter life remaining",
        extractor=lambda data: numeric_value(
            data.get("telemetry", {}).get("restFilterTime"), integer=True
        )
        if data.get("telemetry")
        else None,
        unit=UnitOfTime.DAYS,
        device_class=SensorDeviceClass.DURATION,
    ),
    SensorDescription(
        key="uptime",
        name="Uptime",
        extractor=lambda data: (
            data.get("telemetry", {}).get("uptime")
            if data.get("telemetry")
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.values():
        entities.extend(SecSmartSensor(coordinator, description) for description in SENSORS)
        for area_key, area in coordinator.data.get("areas", {}).items():
            if not isinstance(area, dict):
                continue
            mode = str(area.get("mode") or "")
            if mode.upper().startswith(INACTIVE_PREFIX):
                continue
            entities.append(SecSmartAreaModeSensor(coordinator, area_key, area))
            entities.append(SecSmartAreaSnoozeSensor(coordinator, area_key, area))
            entities.append(SecSmartAreaCommandSensor(coordinator, area_key, area))
        entities.append(SecSmartLastUpdateSensor(coordinator))
    async_add_entities(entities)


class SecSmartSensor(SecSmartEntity, SensorEntity):
    def __init__(self, coordinator: SecSmartCoordinator, description: SensorDescription) -> None:
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_name = description.name
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> Any:
        return self._description.extractor(self.coordinator.data)


class SecSmartAreaModeSensor(SecSmartEntity, SensorEntity):
    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._area_key = area_key
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}_mode"
        self._attr_name = f"{str(area.get('label') or area_key).strip()} mode"

    @property
    def native_value(self) -> Any:
        area = self.coordinator.data.get("areas", {}).get(self._area_key)
        return area.get("mode") if isinstance(area, dict) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        area = self.coordinator.data.get("areas", {}).get(self._area_key)
        if not isinstance(area, dict):
            return None
        timers = area.get("timers")
        return {"timers": timers} if timers is not None else None


class SecSmartAreaSnoozeSensor(SecSmartEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._area_key = area_key
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}_snooze_remaining"
        self._attr_name = f"{str(area.get('label') or area_key).strip()} snooze remaining"

    @property
    def native_value(self) -> int | None:
        telemetry = self.coordinator.data.get("telemetry")
        if not isinstance(telemetry, dict):
            return None
        rest = telemetry.get("restSleepTime")
        if not isinstance(rest, dict):
            return None
        return numeric_value(rest.get(self._area_key), integer=True)


class SecSmartAreaCommandSensor(SecSmartEntity, SensorEntity):
    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._area_key = area_key
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}_last_command"
        self._attr_name = f"{str(area.get('label') or area_key).strip()} last command"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.area_commands.get(self._area_key, {}).get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        command = self.coordinator.area_commands.get(self._area_key)
        return dict(command) if command else None


class SecSmartLastUpdateSensor(SecSmartEntity, SensorEntity):
    _attr_name = "Last successful update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_last_successful_update"

    @property
    def native_value(self) -> Any:
        return self.coordinator.last_successful_update
