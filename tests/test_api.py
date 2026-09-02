from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any

import pytest

PACKAGE_PATH = Path(__file__).parents[1] / "custom_components" / "sec_smart"
PACKAGE = types.ModuleType("sec_smart")
PACKAGE.__path__ = [str(PACKAGE_PATH)]
sys.modules["sec_smart"] = PACKAGE
MODELS_SPEC = importlib.util.spec_from_file_location(
    "sec_smart.models", PACKAGE_PATH / "models.py"
)
assert MODELS_SPEC is not None and MODELS_SPEC.loader is not None
MODELS_MODULE = importlib.util.module_from_spec(MODELS_SPEC)
sys.modules[MODELS_SPEC.name] = MODELS_MODULE
MODELS_SPEC.loader.exec_module(MODELS_MODULE)
SPEC = importlib.util.spec_from_file_location("sec_smart.api", PACKAGE_PATH / "api.py")
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
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self.content_type = content_type
        self.headers = headers or {}

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
    endpoints = ("areas", "telemetry", "notifications", "gateway", "controller", "settings")
    api, session = build_api(
        *(FakeResponse(200, {"ok": item}) for item in endpoints)
    )
    assert await api.async_get_areas(DEVICE_ID) == {"ok": "areas"}
    assert await api.async_get_telemetry(DEVICE_ID) == {"ok": "telemetry"}
    assert await api.async_get_notifications(DEVICE_ID) == {"ok": "notifications"}
    assert await api.async_get_gateway(DEVICE_ID) == {"ok": "gateway"}
    assert await api.async_get_controller(DEVICE_ID) == {"ok": "controller"}
    assert await api.async_get_settings(DEVICE_ID) == {"ok": "settings"}
    assert [call["url"].rsplit("/", 1)[-1] for call in session.calls] == list(
        endpoints
    )


async def test_sends_mode_payload() -> None:
    api, session = build_api(FakeResponse(204))
    await api.async_set_area_mode(DEVICE_ID, 3, "Manual 4")
    assert session.calls[0]["json"] == {"areaid": 3, "mode": "Manual 4"}
    assert session.calls[0]["method"] == "PUT"


async def test_sends_documented_settings_payloads() -> None:
    api, session = build_api(
        FakeResponse(204),
        FakeResponse(204),
        FakeResponse(204),
        FakeResponse(204),
        FakeResponse(204),
    )
    await api.async_set_area_timers(
        DEVICE_ID,
        2,
        {"timer1": {"active": False, "mode": "Manual 2", "time": "06:00"}},
    )
    await api.async_set_thresholds(DEVICE_ID, humidity=60, co2=1000)
    await api.async_set_sleep_time(DEVICE_ID, 30)
    await api.async_set_summer_mode(DEVICE_ID, True)
    await api.async_set_filter(DEVICE_ID, max_run_time=180, reset=True)
    assert [call["json"] for call in session.calls] == [
        {
            "areaid": 2,
            "timers": {
                "timer1": {"active": False, "mode": "Manual 2", "time": "06:00"}
            },
        },
        {"thresholds": {"humidity": 60, "co2": 1000}},
        {"sleepTime": 30},
        {"summermode": True},
        {"filter": {"maxRunTime": 180, "reset": True}},
    ]


async def test_401_raises_auth_error() -> None:
    api, _ = build_api(FakeResponse(401))
    with pytest.raises(SecSmartAuthError):
        await api.async_get_devices()


async def test_bad_shape_and_server_error_are_request_errors() -> None:
    api, _ = build_api(FakeResponse(200, {"not": "a list"}))
    with pytest.raises(SecSmartRequestError, match="invalid device list"):
        await api.async_get_devices()

    api, _ = build_api(
        FakeResponse(503, "unavailable", "text/plain"),
        FakeResponse(503, "unavailable", "text/plain"),
        FakeResponse(503, "unavailable", "text/plain"),
    )
    with pytest.raises(SecSmartRequestError, match="503"):
        await api.async_get_devices()


async def test_retries_transient_status(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(API_MODULE.asyncio, "sleep", fake_sleep)
    api, session = build_api(
        FakeResponse(429, headers={"Retry-After": "2"}),
        FakeResponse(200, [{"id": DEVICE_ID}]),
    )
    assert await api.async_get_devices() == [{"id": DEVICE_ID}]
    assert len(session.calls) == 2
    assert delays == [2.0]


async def test_auth_error_is_not_retried() -> None:
    api, session = build_api(FakeResponse(401), FakeResponse(200, []))
    with pytest.raises(SecSmartAuthError):
        await api.async_get_devices()
    assert len(session.calls) == 1
