from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

UTIL_PATH = Path(__file__).parents[1] / "custom_components" / "sec_smart" / "util.py"
SPEC = importlib.util.spec_from_file_location("sec_smart_util", UTIL_PATH)
assert SPEC is not None and SPEC.loader is not None
UTIL_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = UTIL_MODULE
SPEC.loader.exec_module(UTIL_MODULE)

active_error = UTIL_MODULE.active_error
telemetry_value = UTIL_MODULE.telemetry_value


def test_all_zero_environment_is_unavailable() -> None:
    data = {
        "telemetry": {"co2": 0, "humidity": 0, "Ti": "0", "Ta": "0"}
    }
    assert telemetry_value(data, "co2") is None
    assert telemetry_value(data, "Ti") is None


def test_real_environment_value_is_preserved() -> None:
    data = {
        "telemetry": {"co2": 650, "humidity": 45, "Ti": "21.4", "Ta": "8.2"}
    }
    assert telemetry_value(data, "co2") == 650
    assert telemetry_value(data, "Ti") == "21.4"


def test_notification_code_00_is_not_an_error() -> None:
    assert active_error({"notifications": {"actualMessage": "00        "}}) is False


def test_real_notification_is_an_error() -> None:
    assert active_error({"notifications": {"actualMessage": "E12 failure"}}) is True


def test_missing_notifications_are_unknown() -> None:
    assert active_error({"notifications": None}) is None
