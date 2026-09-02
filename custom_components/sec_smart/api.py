from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp


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
                if response.status >= 400:
                    detail = (await response.text())[:300]
                    raise SecSmartRequestError(
                        f"SEC Smart returned HTTP {response.status}: {detail}"
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
            raise SecSmartRequestError(f"SEC Smart request failed: {err}") from err

    async def async_get_devices(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/devices")
        if not isinstance(data, list):
            raise SecSmartRequestError("SEC Smart returned an invalid device list")
        devices: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            device = dict(item)
            if "id" not in device and "deviceid" in device:
                device["id"] = device["deviceid"]
            devices.append(device)
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
