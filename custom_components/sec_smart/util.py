from __future__ import annotations

from typing import Any

ENVIRONMENT_KEYS = ("co2", "humidity", "Ti", "Ta")


def telemetry_value(data: dict[str, Any], key: str) -> Any:
    """Return telemetry without presenting a missing sensor block as real zeros."""
    telemetry = data.get("telemetry")
    if not isinstance(telemetry, dict):
        return None
    if all(_is_zero(telemetry.get(item)) for item in ENVIRONMENT_KEYS):
        return None
    return telemetry.get(key)


def numeric_value(value: object, *, integer: bool = False) -> int | float | None:
    """Convert documented numeric values while rejecting booleans and invalid text."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if integer else number


def boolean_value(value: object) -> bool | None:
    """Convert strict API booleans without treating the string 'false' as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return None


def vendor_timers_active(area: object) -> bool | None:
    """Return whether any of an area's vendor timers is active."""
    if not isinstance(area, dict) or not isinstance(area.get("timers"), dict):
        return None
    states = [
        boolean_value(timer.get("active"))
        for timer in area["timers"].values()
        if isinstance(timer, dict)
    ]
    known = [state for state in states if state is not None]
    return any(known) if known else None


def active_error(data: dict[str, Any]) -> bool | None:
    """Interpret the SEC notification code; 00 means no active error."""
    notifications = data.get("notifications")
    if not isinstance(notifications, dict):
        return None
    message = notifications.get("actualMessage")
    if message is None:
        return False
    return str(message).strip() not in {"", "00"}


def _is_zero(value: Any) -> bool:
    if value is None:
        return True
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False
