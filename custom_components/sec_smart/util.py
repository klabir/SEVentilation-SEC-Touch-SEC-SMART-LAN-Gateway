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
