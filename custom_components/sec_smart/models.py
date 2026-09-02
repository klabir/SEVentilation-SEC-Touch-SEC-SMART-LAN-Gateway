from __future__ import annotations

from typing import NotRequired, TypedDict


class SecSmartTimer(TypedDict):
    active: bool
    mode: str
    time: str


class SecSmartArea(TypedDict, total=False):
    label: str
    mode: str
    timers: dict[str, SecSmartTimer]


class SecSmartTelemetry(TypedDict, total=False):
    restSleepTime: dict[str, int]
    restFilterTime: int
    co2: int
    humidity: int
    Ti: str
    Ta: str
    uptime: str


class SecSmartFilterSettings(TypedDict, total=False):
    maxRunTime: int


class SecSmartThresholds(TypedDict, total=False):
    humidity: int
    co2: int


class SecSmartSettings(TypedDict, total=False):
    filter: SecSmartFilterSettings
    thresholds: SecSmartThresholds
    sleepTime: int
    deviceTime: dict[str, str | bool]
    summermode: bool


class SecSmartDevice(TypedDict):
    id: str
    name: NotRequired[str]
    deviceid: NotRequired[str]


class AreaCommandState(TypedDict, total=False):
    status: str
    target: str
    timestamp: str
    error: str
