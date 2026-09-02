from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    INACTIVE_PREFIX,
    MANUAL_PERCENTAGES,
    MODE_BOOST,
    MODE_OFF,
    PRESET_TO_MODE,
)
from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[SecSmartAreaFan] = []
    for coordinator in entry.runtime_data.values():
        for area_key, area in coordinator.data.get("areas", {}).items():
            if not isinstance(area, dict):
                continue
            mode = str(area.get("mode") or "")
            if mode.upper().startswith(INACTIVE_PREFIX):
                continue
            area_id_text = area_key.removeprefix("area")
            if area_id_text.isdigit():
                entities.append(
                    SecSmartAreaFan(coordinator, int(area_id_text), area_key, area)
                )
    async_add_entities(entities)


class SecSmartAreaFan(SecSmartEntity, FanEntity):
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = list(PRESET_TO_MODE)
    _attr_speed_count = 6

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_id: int,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._area_key = area_key
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}"
        self._attr_name = str(area.get("label") or area_key).strip()

    @property
    def native_value(self) -> Any:
        return self._mode

    @property
    def _mode(self) -> str | None:
        area = self.coordinator.data.get("areas", {}).get(self._area_key)
        return area.get("mode") if isinstance(area, dict) else None

    @property
    def is_on(self) -> bool | None:
        return self._mode != MODE_OFF if self._mode is not None else None

    @property
    def percentage(self) -> int | None:
        mode = self._mode
        if mode == MODE_OFF:
            return 0
        if mode == MODE_BOOST:
            return 100
        if mode and mode.startswith("Manual "):
            try:
                return MANUAL_PERCENTAGES.get(int(mode.split()[1]))
            except (IndexError, ValueError):
                return None
        return None

    @property
    def preset_mode(self) -> str | None:
        return next((preset for preset, mode in PRESET_TO_MODE.items() if mode == self._mode), None)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self._set_mode(MODE_OFF)
            return
        level = min(MANUAL_PERCENTAGES, key=lambda item: abs(MANUAL_PERCENTAGES[item] - percentage))
        await self._set_mode(f"Manual {level}")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in PRESET_TO_MODE:
            raise HomeAssistantError(f"Unsupported SEC Smart preset: {preset_mode}")
        await self._set_mode(PRESET_TO_MODE[preset_mode])

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        else:
            await self.async_set_percentage(percentage if percentage is not None else 50)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_mode(MODE_OFF)

    async def _set_mode(self, mode: str) -> None:
        await self.coordinator.async_set_area_mode(
            self._area_id,
            self._area_key,
            mode,
        )
