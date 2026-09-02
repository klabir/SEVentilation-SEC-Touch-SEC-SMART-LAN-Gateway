from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import random
from typing import Any, cast

import aiohttp

from .models import SecSmartDevice, SecSmartSettings, SecSmartTimer

MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})


class SecSmartError(Exception):
    """Base SEC Smart API error."""


class SecSmartAuthError(SecSmartError):
    """SEC Smart rejected the bearer token."""


class SecSmartRequestError(SecSmartError):
    """SEC Smart rejected or failed a request."""


class SecSmartApi:
    """Small async client for the documented SEC Smart endpoints."""

    def __init__(
        self,
        base_url: str,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = session

    async def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with self._session.request(
                    method,
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    if response.status == 401:
                        raise SecSmartAuthError("SEC Smart rejected the API token")
                    if response.status in RETRYABLE_STATUSES and attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue
                    if response.status >= 400:
                        raise SecSmartRequestError(
                            f"SEC Smart returned HTTP {response.status} for {method} {path}"
                        )
                    if response.status == 204:
                        return None
                    if response.content_type == "application/json":
                        return await response.json()
                    body = await response.text()
                    return body or None
            except SecSmartError:
                raise
            except (aiohttp.ClientError, TimeoutError) as err:
                if attempt >= MAX_ATTEMPTS - 1:
                    raise SecSmartRequestError(
                        f"SEC Smart request failed for {method} {path}: {type(err).__name__}"
                    ) from err
                await asyncio.sleep(0.5 * (2**attempt) + random.uniform(0, 0.25))
        raise SecSmartRequestError(f"SEC Smart request failed for {method} {path}")

    @staticmethod
    def _retry_delay(response: aiohttp.ClientResponse, attempt: int) -> float:
        """Return a bounded Retry-After delay or exponential backoff with jitter."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(30.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    target = parsedate_to_datetime(retry_after)
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=UTC)
                    delay = (target - datetime.now(UTC)).total_seconds()
                    return min(30.0, max(0.0, delay))
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(5.0, 0.5 * (2**attempt) + random.uniform(0, 0.25))

    async def async_get_devices(self) -> list[SecSmartDevice]:
        data = await self._request("GET", "/devices")
        if not isinstance(data, list):
            raise SecSmartRequestError("SEC Smart returned an invalid device list")
        devices: list[SecSmartDevice] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            device: dict[str, Any] = dict(item)
            if "id" not in device and "deviceid" in device:
                device["id"] = device["deviceid"]
            if isinstance(device.get("id"), str):
                devices.append(cast(SecSmartDevice, device))
        return devices

    async def async_get_areas(self, device_id: str) -> dict[str, Any]:
        return await self._get_mapping(f"/devices/{device_id}/areas")

    async def async_get_telemetry(self, device_id: str) -> dict[str, Any]:
        return await self._get_mapping(f"/devices/{device_id}/telemetry")

    async def async_get_notifications(self, device_id: str) -> dict[str, Any]:
        return await self._get_mapping(f"/devices/{device_id}/notifications")

    async def async_get_gateway(self, device_id: str) -> dict[str, Any]:
        return await self._get_mapping(f"/devices/{device_id}/gateway")

    async def async_get_controller(self, device_id: str) -> dict[str, Any]:
        return await self._get_mapping(f"/devices/{device_id}/controller")

    async def async_get_settings(self, device_id: str) -> SecSmartSettings:
        return cast(
            SecSmartSettings,
            await self._get_mapping(f"/devices/{device_id}/settings"),
        )

    async def _get_mapping(self, path: str) -> dict[str, Any]:
        data = await self._request("GET", path)
        if not isinstance(data, dict):
            raise SecSmartRequestError(f"SEC Smart returned invalid data for {path}")
        return data

    async def async_set_area_mode(
        self,
        device_id: str,
        area_id: int,
        mode: str,
    ) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/areas/mode",
            {"areaid": area_id, "mode": mode},
        )

    async def async_set_area_timers(
        self,
        device_id: str,
        area_id: int,
        timers: Mapping[str, SecSmartTimer],
    ) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/areas/timeprogram",
            {"areaid": area_id, "timers": dict(timers)},
        )

    async def async_set_thresholds(
        self,
        device_id: str,
        *,
        humidity: int,
        co2: int,
    ) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/settings/thresholds",
            {"thresholds": {"humidity": humidity, "co2": co2}},
        )

    async def async_set_sleep_time(self, device_id: str, minutes: int) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/settings/sleep-time",
            {"sleepTime": minutes},
        )

    async def async_set_summer_mode(self, device_id: str, enabled: bool) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/settings/summermode",
            {"summermode": enabled},
        )

    async def async_set_filter(
        self,
        device_id: str,
        *,
        max_run_time: int,
        reset: bool = False,
    ) -> None:
        await self._request(
            "PUT",
            f"/devices/{device_id}/settings/filter",
            {"filter": {"maxRunTime": max_run_time, "reset": reset}},
        )
