from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MIN_TIMEOUT_MINUTES = 0
MAX_TIMEOUT_MINUTES = 1440

type AreaKey = tuple[str, str]


@dataclass(slots=True)
class ScheduleOverrideState:
    """Persistent local scheduler ownership for one SEC Smart area."""

    timeout_minutes: int = 0
    is_on: bool = False
    expires_at: datetime | None = None


class ScheduleOverrideManager:
    """Own persistent override state and expiry timers for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.schedule_overrides"
        )
        self._states: dict[AreaKey, ScheduleOverrideState] = {}
        self._listeners: dict[AreaKey, set[Callable[[], None]]] = {}
        self._cancellers: dict[AreaKey, CALLBACK_TYPE] = {}
        self._generations: dict[AreaKey, int] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False

    async def async_load(self) -> None:
        """Load stored states, retire elapsed deadlines, and restore timers."""
        raw = await self._store.async_load()
        areas = raw.get("areas") if isinstance(raw, dict) else None
        if raw is not None and not isinstance(areas, dict):
            _LOGGER.warning("Ignoring invalid SEC Smart schedule override storage")
            areas = {}

        changed = False
        for storage_key, value in (areas or {}).items():
            key = self._decode_key(storage_key)
            if key is None or not isinstance(value, dict):
                _LOGGER.warning("Ignoring invalid SEC Smart schedule override entry")
                continue
            state = self._decode_state(key, value)
            self._states[key] = state
            if state.is_on and state.expires_at is not None:
                if state.expires_at <= datetime.now(UTC):
                    state.is_on = False
                    state.expires_at = None
                    changed = True
                else:
                    self._schedule(key, state.expires_at)
        if changed:
            await self._async_save()

    def state(self, device_id: str, area_key: str) -> ScheduleOverrideState:
        """Return current state without creating persistent data."""
        return self._states.get((device_id, area_key), ScheduleOverrideState())

    async def async_migrate_legacy(
        self, device_id: str, area_key: str, legacy_is_on: bool
    ) -> None:
        """Seed a missing area from the former RestoreEntity switch state."""
        key = (device_id, area_key)
        async with self._lock:
            if key in self._states:
                return
            self._states[key] = ScheduleOverrideState(is_on=legacy_is_on)
            await self._async_save()
        self._notify(key)

    async def async_turn_on(self, device_id: str, area_key: str) -> None:
        key = (device_id, area_key)
        async with self._lock:
            state = self._states.setdefault(key, ScheduleOverrideState())
            state.is_on = True
            state.expires_at = self._deadline(state.timeout_minutes)
            self._reschedule(key, state.expires_at)
            await self._async_save()
        self._notify(key)

    async def async_turn_off(self, device_id: str, area_key: str) -> None:
        key = (device_id, area_key)
        async with self._lock:
            state = self._states.setdefault(key, ScheduleOverrideState())
            state.is_on = False
            state.expires_at = None
            self._reschedule(key, None)
            await self._async_save()
        self._notify(key)

    async def async_set_timeout(
        self, device_id: str, area_key: str, minutes: int
    ) -> None:
        if not MIN_TIMEOUT_MINUTES <= minutes <= MAX_TIMEOUT_MINUTES:
            raise ValueError("Schedule override timeout must be between 0 and 1440")
        key = (device_id, area_key)
        async with self._lock:
            state = self._states.setdefault(key, ScheduleOverrideState())
            state.timeout_minutes = minutes
            if state.is_on:
                state.expires_at = self._deadline(minutes)
                self._reschedule(key, state.expires_at)
            await self._async_save()
        self._notify(key)

    @callback
    def async_subscribe(
        self, device_id: str, area_key: str, listener: Callable[[], None]
    ) -> CALLBACK_TYPE:
        key = (device_id, area_key)
        listeners = self._listeners.setdefault(key, set())
        listeners.add(listener)

        @callback
        def remove_listener() -> None:
            listeners.discard(listener)

        return remove_listener

    @callback
    def async_shutdown(self) -> None:
        """Cancel callbacks while retaining stored state for reload."""
        self._shutdown = True
        for cancel in self._cancellers.values():
            cancel()
        self._cancellers.clear()
        for key in tuple(self._generations):
            self._generations[key] += 1
        self._listeners.clear()

    def _decode_state(
        self, key: AreaKey, value: dict[str, Any]
    ) -> ScheduleOverrideState:
        timeout = value.get("timeout_minutes")
        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or not MIN_TIMEOUT_MINUTES <= timeout <= MAX_TIMEOUT_MINUTES
        ):
            _LOGGER.warning("Invalid schedule override timeout for %s; using 0", key)
            timeout = 0
        is_on = value.get("is_on")
        if not isinstance(is_on, bool):
            _LOGGER.warning("Invalid schedule override state for %s; using off", key)
            is_on = False
        expires_at = self._parse_deadline(value.get("expires_at"))
        if timeout == 0:
            expires_at = None
        if is_on and timeout > 0 and expires_at is None:
            _LOGGER.warning(
                "Invalid active schedule override deadline for %s; preserving it indefinitely",
                key,
            )
        if not is_on:
            expires_at = None
        return ScheduleOverrideState(timeout, is_on, expires_at)

    @staticmethod
    def _parse_deadline(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            return None
        if result.tzinfo is None:
            return None
        return result.astimezone(UTC)

    @staticmethod
    def _decode_key(value: Any) -> AreaKey | None:
        if not isinstance(value, str) or "\u001f" not in value:
            return None
        device_id, area_key = value.split("\u001f", 1)
        return (device_id, area_key) if device_id and area_key else None

    @staticmethod
    def _encode_key(key: AreaKey) -> str:
        return "\u001f".join(key)

    @staticmethod
    def _deadline(minutes: int) -> datetime | None:
        return datetime.now(UTC) + timedelta(minutes=minutes) if minutes else None

    def _reschedule(self, key: AreaKey, deadline: datetime | None) -> None:
        if cancel := self._cancellers.pop(key, None):
            cancel()
        generation = self._generations.get(key, 0) + 1
        self._generations[key] = generation
        if deadline is not None and not self._shutdown:
            self._schedule(key, deadline, generation)

    def _schedule(
        self, key: AreaKey, deadline: datetime, generation: int | None = None
    ) -> None:
        if generation is None:
            generation = self._generations.get(key, 0) + 1
            self._generations[key] = generation

        @callback
        def expire(_now: datetime) -> None:
            self._hass.async_create_task(
                self._async_expire(key, generation),
                f"Expire SEC Smart schedule override {key}",
            )

        self._cancellers[key] = async_track_point_in_utc_time(
            self._hass, expire, deadline
        )

    async def _async_expire(self, key: AreaKey, generation: int) -> None:
        async with self._lock:
            if self._shutdown or self._generations.get(key) != generation:
                return
            state = self._states.get(key)
            if state is None or not state.is_on or state.expires_at is None:
                return
            if state.expires_at > datetime.now(UTC):
                self._schedule(key, state.expires_at, generation)
                return
            self._cancellers.pop(key, None)
            state.is_on = False
            state.expires_at = None
            await self._async_save()
        self._notify(key)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "areas": {
                    self._encode_key(key): {
                        "timeout_minutes": state.timeout_minutes,
                        "is_on": state.is_on,
                        "expires_at": (
                            state.expires_at.isoformat()
                            if state.expires_at is not None
                            else None
                        ),
                    }
                    for key, state in self._states.items()
                }
            }
        )

    @callback
    def _notify(self, key: AreaKey) -> None:
        for listener in tuple(self._listeners.get(key, ())):
            listener()
