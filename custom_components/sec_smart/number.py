from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfRatio, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ALLOW_CONTROL, CONF_ALLOW_SETTINGS, INACTIVE_PREFIX
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
        if entry.options.get(CONF_ALLOW_CONTROL, False):
            for area_key, area in coordinator.data.get("areas", {}).items():
                if not isinstance(area, dict):
                    continue
                if str(area.get("mode") or "").upper().startswith(INACTIVE_PREFIX):
                    continue
                entities.append(
                    SecSmartScheduleOverrideTimeoutNumber(coordinator, area_key, area)
                )
        if entry.options.get(CONF_ALLOW_SETTINGS, False):
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


class SecSmartScheduleOverrideTimeoutNumber(SecSmartNumber):
    """Local auto-off duration for an area's Schedule override switch."""

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        label = str(area.get("label") or area_key).strip()
        super().__init__(
            coordinator,
            f"{area_key}_schedule_override_timeout",
            f"{label} schedule override timeout",
            0,
            1440,
            1,
            UnitOfTime.MINUTES,
        )
        self._area_key = area_key

    @property
    def available(self) -> bool:
        """The timeout is local even if the cloud coordinator is unavailable."""
        return True

    @property
    def native_value(self) -> float:
        return self.coordinator.override_manager.state(
            self.coordinator.device_id, self._area_key
        ).timeout_minutes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.override_manager.async_subscribe(
                self.coordinator.device_id, self._area_key, self.async_write_ha_state
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)
        if value != minutes:
            raise ValueError("Schedule override timeout must be a whole number")
        await self.coordinator.override_manager.async_set_timeout(
            self.coordinator.device_id, self._area_key, minutes
        )


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
        return (
            numeric_value(settings.get("sleepTime"))
            if isinstance(settings, dict)
            else None
        )

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
