from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfRatio, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import numeric_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[NumberEntity] = []
    for coordinator in entry.runtime_data.values():
        entities.extend(
            (
                SecSmartThresholdNumber(
                    coordinator,
                    "humidity",
                    "Humidity threshold",
                    10,
                    95,
                    1,
                    PERCENTAGE,
                ),
                SecSmartThresholdNumber(
                    coordinator,
                    "co2",
                    "CO2 threshold",
                    100,
                    5000,
                    10,
                    UnitOfRatio.PARTS_PER_MILLION,
                ),
                SecSmartSleepTimeNumber(coordinator),
                SecSmartFilterRuntimeNumber(coordinator),
            )
        )
    async_add_entities(entities)


class SecSmartNumber(SecSmartEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        key: str,
        name: str,
        minimum: float,
        maximum: float,
        step: float,
        unit: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_name = name
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit


class SecSmartThresholdNumber(SecSmartNumber):
    @property
    def native_value(self) -> float | None:
        settings = self.coordinator.data.get("settings")
        if not isinstance(settings, dict):
            return None
        thresholds = settings.get("thresholds")
        if not isinstance(thresholds, dict):
            return None
        return numeric_value(thresholds.get(self._key))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_threshold(self._key, int(value))


class SecSmartSleepTimeNumber(SecSmartNumber):
    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(
            coordinator,
            "sleep_time",
            "Snooze duration",
            10,
            250,
            1,
            UnitOfTime.MINUTES,
        )

    @property
    def native_value(self) -> float | None:
        settings = self.coordinator.data.get("settings")
        return numeric_value(settings.get("sleepTime")) if isinstance(settings, dict) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_sleep_time(int(value))


class SecSmartFilterRuntimeNumber(SecSmartNumber):
    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(
            coordinator,
            "filter_max_runtime",
            "Filter maximum runtime",
            90,
            270,
            1,
            UnitOfTime.DAYS,
        )

    @property
    def native_value(self) -> float | None:
        settings = self.coordinator.data.get("settings")
        if not isinstance(settings, dict):
            return None
        filter_settings = settings.get("filter")
        return (
            numeric_value(filter_settings.get("maxRunTime"))
            if isinstance(filter_settings, dict)
            else None
        )

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_filter_runtime(int(value))
