from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
from time import monotonic
from typing import Any, cast

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SecSmartApi, SecSmartAuthError
from .models import AreaCommandState, SecSmartDevice, SecSmartSettings
from .util import boolean_value, numeric_value

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_INTERVAL = 5 * 60
METADATA_INTERVAL = 60 * 60
COMMAND_CONFIRM_ATTEMPTS = 5
COMMAND_CONFIRM_DELAY = 1


class SecSmartCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll one SEC Smart device and serialize cloud writes."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SecSmartApi,
        device: SecSmartDevice,
        interval: int,
    ) -> None:
        self.api = api
        self.device_id = str(device["id"])
        self.device_name = str(device.get("name") or self.device_id)
        self.last_successful_update: datetime | None = None
        self.endpoint_health: dict[str, bool] = {}
        self.area_commands: dict[str, AreaCommandState] = {}
        self._area_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._settings_lock = asyncio.Lock()
        self._last_notification_poll = 0.0
        self._last_metadata_poll = 0.0
        super().__init__(
            hass,
            _LOGGER,
            name=f"SEC Smart {self.device_name}",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        now = monotonic()
        previous = dict(self.data) if self.data else {}
        data: dict[str, Any] = previous | {"endpoint_health": dict(self.endpoint_health)}

        try:
            areas, telemetry = await asyncio.gather(
                self.api.async_get_areas(self.device_id),
                self.api.async_get_telemetry(self.device_id),
                return_exceptions=True,
            )
            if isinstance(areas, SecSmartAuthError) or isinstance(
                telemetry, SecSmartAuthError
            ):
                raise ConfigEntryAuthFailed
            if isinstance(areas, Exception):
                self.endpoint_health["areas"] = False
                raise UpdateFailed(f"Unable to read SEC Smart areas: {areas}") from areas
            data["areas"] = self._normalize_areas(areas)
            self.endpoint_health["areas"] = True
            if isinstance(telemetry, Exception):
                data["telemetry"] = None
                self.endpoint_health["telemetry"] = False
            else:
                data["telemetry"] = telemetry
                self.endpoint_health["telemetry"] = True

            if not self.data or now - self._last_notification_poll >= NOTIFICATION_INTERVAL:
                await self._refresh_optional(
                    data,
                    "notifications",
                    self.api.async_get_notifications(self.device_id),
                )
                if self.endpoint_health.get("notifications"):
                    self._last_notification_poll = now

            if not self.data or now - self._last_metadata_poll >= METADATA_INTERVAL:
                await asyncio.gather(
                    self._refresh_optional(
                        data,
                        "gateway",
                        self.api.async_get_gateway(self.device_id),
                    ),
                    self._refresh_optional(
                        data,
                        "controller",
                        self.api.async_get_controller(self.device_id),
                    ),
                    self._refresh_optional(
                        data,
                        "settings",
                        self.api.async_get_settings(self.device_id),
                    ),
                )
                if all(
                    self.endpoint_health.get(key)
                    for key in ("gateway", "controller", "settings")
                ):
                    self._last_metadata_poll = now
        except ConfigEntryAuthFailed:
            raise
        except SecSmartAuthError as err:
            raise ConfigEntryAuthFailed from err

        self.last_successful_update = datetime.now(UTC)
        data["endpoint_health"] = dict(self.endpoint_health)
        return data

    async def _refresh_optional(
        self,
        data: dict[str, Any],
        key: str,
        call: Awaitable[dict[str, Any]],
    ) -> None:
        try:
            data[key] = await call
        except SecSmartAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            _LOGGER.debug(
                "Optional SEC Smart endpoint %s failed for %s: %s",
                key,
                self.device_id,
                type(err).__name__,
            )
            data[key] = None
            self.endpoint_health[key] = False
        else:
            self.endpoint_health[key] = True

    async def async_set_area_mode(self, area_id: int, area_key: str, mode: str) -> None:
        """Serialize one area command and confirm eventual cloud state."""
        async with self._area_locks[area_id]:
            current = self.data.get("areas", {}).get(area_key, {}).get("mode")
            if current == mode:
                self._record_command(area_key, "confirmed", mode)
                return
            self._record_command(area_key, "sending", mode)
            try:
                await self.api.async_set_area_mode(self.device_id, area_id, mode)
                for _ in range(COMMAND_CONFIRM_ATTEMPTS):
                    areas = self._normalize_areas(
                        await self.api.async_get_areas(self.device_id)
                    )
                    self._set_areas(areas)
                    if areas.get(area_key, {}).get("mode") == mode:
                        self._record_command(area_key, "confirmed", mode)
                        return
                    await asyncio.sleep(COMMAND_CONFIRM_DELAY)
            except Exception as err:
                self._record_command(area_key, "failed", mode, type(err).__name__)
                raise
            self._record_command(area_key, "failed", mode, "confirmation_timeout")
            raise UpdateFailed(
                f"SEC Smart did not confirm {mode!r} for area {area_id}"
            )

    async def async_set_threshold(self, key: str, value: int) -> None:
        async with self._settings_lock:
            settings = self._settings()
            thresholds = settings.get("thresholds", {})
            humidity_current = numeric_value(thresholds.get("humidity"), integer=True)
            co2_current = numeric_value(thresholds.get("co2"), integer=True)
            if humidity_current is None or co2_current is None:
                raise UpdateFailed("SEC Smart thresholds are unavailable")
            humidity = value if key == "humidity" else humidity_current
            co2 = value if key == "co2" else co2_current
            await self._write_and_confirm_settings(
                lambda: self.api.async_set_thresholds(
                    self.device_id, humidity=humidity, co2=co2
                ),
                lambda current: numeric_value(
                    current.get("thresholds", {}).get(key), integer=True
                )
                == value,
            )

    async def async_set_sleep_time(self, minutes: int) -> None:
        async with self._settings_lock:
            await self._write_and_confirm_settings(
                lambda: self.api.async_set_sleep_time(self.device_id, minutes),
                lambda current: numeric_value(current.get("sleepTime"), integer=True)
                == minutes,
            )

    async def async_set_summer_mode(self, enabled: bool) -> None:
        async with self._settings_lock:
            await self._write_and_confirm_settings(
                lambda: self.api.async_set_summer_mode(self.device_id, enabled),
                lambda current: boolean_value(current.get("summermode")) is enabled,
            )

    async def async_set_filter_runtime(self, days: int, *, reset: bool = False) -> None:
        async with self._settings_lock:
            await self._write_and_confirm_settings(
                lambda: self.api.async_set_filter(
                    self.device_id, max_run_time=days, reset=reset
                ),
                lambda current: numeric_value(
                    current.get("filter", {}).get("maxRunTime"), integer=True
                )
                == days,
            )

    async def _write_and_confirm_settings(
        self,
        write: Callable[[], Awaitable[None]],
        confirmed: Callable[[SecSmartSettings], bool],
    ) -> None:
        await write()
        for _ in range(COMMAND_CONFIRM_ATTEMPTS):
            settings = await self.api.async_get_settings(self.device_id)
            self._set_settings(settings)
            if confirmed(settings):
                return
            await asyncio.sleep(COMMAND_CONFIRM_DELAY)
        raise UpdateFailed("SEC Smart did not confirm the settings update")

    def _settings(self) -> SecSmartSettings:
        settings = self.data.get("settings")
        if not isinstance(settings, dict):
            raise UpdateFailed("SEC Smart settings are unavailable")
        return cast(SecSmartSettings, settings)

    def _set_areas(self, areas: dict[str, Any]) -> None:
        data = dict(self.data)
        data["areas"] = areas
        self.async_set_updated_data(data)

    def _set_settings(self, settings: SecSmartSettings) -> None:
        data = dict(self.data)
        data["settings"] = settings
        self.async_set_updated_data(data)

    def _record_command(
        self,
        area_key: str,
        status: str,
        target: str,
        error: str | None = None,
    ) -> None:
        command: AreaCommandState = {
            "status": status,
            "target": target,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if error:
            command["error"] = error
        self.area_commands[area_key] = command
        self.async_update_listeners()

    @staticmethod
    def _normalize_areas(areas: dict[str, Any]) -> dict[str, Any]:
        for area in areas.values():
            if isinstance(area, dict) and isinstance(area.get("mode"), str):
                area["mode"] = area["mode"].strip()
        return areas
