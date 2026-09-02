from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

API_PATH = Path(__file__).parents[1] / "custom_components" / "sec_smart" / "api.py"
SPEC = importlib.util.spec_from_file_location("sec_smart_api", API_PATH)
assert SPEC is not None and SPEC.loader is not None
API_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = API_MODULE
SPEC.loader.exec_module(API_MODULE)

SecSmartApi = API_MODULE.SecSmartApi
SecSmartAuthError = API_MODULE.SecSmartAuthError
SecSmartRequestError = API_MODULE.SecSmartRequestError

BASE_URL = "https://api.example.test/v1"
DEVICE_ID = "1A2B3C"


class FakeResponse:
    def __init__(
        self,
        status: int,
        payload: Any = None,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self._payload = payload
        self.content_type = content_type

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def json(self) -> Any:
        return self._payload

    async def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload) if self._payload is not None else ""


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def build_api(*responses: FakeResponse) -> tuple[SecSmartApi, FakeSession]:
    session = FakeSession(list(responses))
    return SecSmartApi(BASE_URL, "test-token", session), session


async def test_discovers_devices() -> None:
    payload = [{"type": "device", "id": DEVICE_ID, "name": "Home"}]
    api, session = build_api(FakeResponse(200, payload))
    assert await api.async_get_devices() == payload
    assert session.calls[0]["headers"]["Authorization"] == "Bearer test-token"


async def test_normalizes_live_deviceid_field() -> None:
    payload = [{"type": "device", "deviceid": DEVICE_ID, "name": "Home"}]
    api, _ = build_api(FakeResponse(200, payload))
    devices = await api.async_get_devices()
    assert devices[0]["id"] == DEVICE_ID
    assert devices[0]["deviceid"] == DEVICE_ID


async def test_reads_documented_endpoints() -> None:
    endpoints = ("areas", "telemetry", "notifications", "gateway", "controller")
    api, session = build_api(
        *(FakeResponse(200, {"ok": item}) for item in endpoints)
    )
    assert await api.async_get_areas(DEVICE_ID) == {"ok": "areas"}
    assert await api.async_get_telemetry(DEVICE_ID) == {"ok": "telemetry"}
    assert await api.async_get_notifications(DEVICE_ID) == {"ok": "notifications"}
    assert await api.async_get_gateway(DEVICE_ID) == {"ok": "gateway"}
    assert await api.async_get_controller(DEVICE_ID) == {"ok": "controller"}
    assert [call["url"].rsplit("/", 1)[-1] for call in session.calls] == list(
        endpoints
    )


async def test_sends_mode_payload() -> None:
    api, session = build_api(FakeResponse(204))
    await api.async_set_area_mode(DEVICE_ID, 3, "Manual 4")
    assert session.calls[0]["json"] == {"areaid": 3, "mode": "Manual 4"}
    assert session.calls[0]["method"] == "PUT"


async def test_401_raises_auth_error() -> None:
    api, _ = build_api(FakeResponse(401))
    with pytest.raises(SecSmartAuthError):
        await api.async_get_devices()


async def test_bad_shape_and_server_error_are_request_errors() -> None:
    api, _ = build_api(FakeResponse(200, {"not": "a list"}))
    with pytest.raises(SecSmartRequestError, match="invalid device list"):
        await api.async_get_devices()

    api, _ = build_api(FakeResponse(503, "unavailable", "text/plain"))
    with pytest.raises(SecSmartRequestError, match="503"):
        await api.async_get_devices()
