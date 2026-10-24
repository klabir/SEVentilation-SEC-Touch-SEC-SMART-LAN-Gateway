from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ALLOW_CONTROL, CONF_ALLOW_SETTINGS, INACTIVE_PREFIX
from .coordinator import SecSmartCoordinator
from .entity import SecSmartEntity
from .util import boolean_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[dict[str, SecSmartCoordinator]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[SwitchEntity] = []
    for coordinator in entry.runtime_data.values():
        if entry.options.get(CONF_ALLOW_CONTROL, False):
            for area_key, area in coordinator.data.get("areas", {}).items():
                if not isinstance(area, dict):
                    continue
                if str(area.get("mode") or "").upper().startswith(INACTIVE_PREFIX):
                    continue
                entities.append(
                    SecSmartScheduleOverrideSwitch(coordinator, area_key, area)
                )
        if entry.options.get(CONF_ALLOW_SETTINGS, False):
            entities.append(SecSmartSummerModeSwitch(coordinator))
    async_add_entities(entities)


class SecSmartScheduleOverrideSwitch(SecSmartEntity, SwitchEntity, RestoreEntity):
    """Local scheduler ownership switch; it never writes to SEC Smart directly."""

    _attr_icon = "mdi:hand-back-right"

    def __init__(
        self,
        coordinator: SecSmartCoordinator,
        area_key: str,
        area: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        label = str(area.get("label") or area_key).strip()
        self._attr_unique_id = f"{coordinator.device_id}_{area_key}_schedule_override"
        self._attr_name = f"{label} schedule override"
        self._area_key = area_key

    @property
    def available(self) -> bool:
        """The override is local even if the cloud coordinator is unavailable."""
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.override_manager.state(
            self.coordinator.device_id, self._area_key
        ).is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        await self.coordinator.override_manager.async_migrate_legacy(
            self.coordinator.device_id,
            self._area_key,
            last_state is not None and last_state.state == "on",
        )
        self.async_on_remove(
            self.coordinator.override_manager.async_subscribe(
                self.coordinator.device_id, self._area_key, self.async_write_ha_state
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.override_manager.async_turn_on(
            self.coordinator.device_id, self._area_key
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.override_manager.async_turn_off(
            self.coordinator.device_id, self._area_key
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | int | None]:
        state = self.coordinator.override_manager.state(
            self.coordinator.device_id, self._area_key
        )
        return {
            "description": (
                "When enabled, Home Assistant scheduling leaves this area unchanged "
                "for manual control from Home Assistant, SEC-Touch, or the vendor app."
            ),
            "schedule_owner": "manual" if self.is_on else "home_assistant",
            "writes_to_sec_smart": False,
            "timeout_minutes": state.timeout_minutes,
            "expires_at": (
                state.expires_at.isoformat() if state.expires_at is not None else None
            ),
        }


class SecSmartSummerModeSwitch(SecSmartEntity, SwitchEntity):
    _attr_name = "Summer mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SecSmartCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_summer_mode"

    @property
    def is_on(self) -> bool | None:
        settings = self.coordinator.data.get("settings")
        return (
            boolean_value(settings.get("summermode"))
            if isinstance(settings, dict)
            else None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_summer_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_summer_mode(False)
