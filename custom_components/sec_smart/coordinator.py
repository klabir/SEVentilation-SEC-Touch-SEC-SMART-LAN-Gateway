from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SecSmartApi, SecSmartAuthError, SecSmartRequestError

_LOGGER = logging.getLogger(__name__)


class SecSmartCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll one SEC Smart device."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SecSmartApi,
        device: dict[str, Any],
        interval: int,
    ) -> None:
        self.api = api
        self.device_id = str(device["id"])
        self.device_name = str(device.get("name") or self.device_id)
        super().__init__(
            hass,
            _LOGGER,
            name=f"SEC Smart {self.device_name}",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        calls = (
            self.api.async_get_areas(self.device_id),
            self.api.async_get_telemetry(self.device_id),
            self.api.async_get_notifications(self.device_id),
            self.api.async_get_gateway(self.device_id),
            self.api.async_get_controller(self.device_id),
        )
        results = await asyncio.gather(*calls, return_exceptions=True)

        for result in results:
            if isinstance(result, SecSmartAuthError):
                raise ConfigEntryAuthFailed from result

        areas = results[0]
        if isinstance(areas, Exception):
            raise UpdateFailed(f"Unable to read SEC Smart areas: {areas}") from areas

        data: dict[str, Any] = {"areas": self._normalize_areas(areas)}
        for key, result in zip(
            ("telemetry", "notifications", "gateway", "controller"),
            results[1:],
            strict=True,
        ):
            if isinstance(result, Exception):
                _LOGGER.debug(
                    "Optional SEC Smart endpoint %s failed for %s: %s",
                    key,
                    self.device_id,
                    result,
                )
                data[key] = None
            else:
                data[key] = result
        return data

    @staticmethod
    def _normalize_areas(areas: dict[str, Any]) -> dict[str, Any]:
        for area in areas.values():
            if isinstance(area, dict) and isinstance(area.get("mode"), str):
                area["mode"] = area["mode"].strip()
        return areas
