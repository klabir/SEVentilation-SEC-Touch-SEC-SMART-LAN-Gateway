from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_TOKEN, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.sec_smart.api import SecSmartApi
from custom_components.sec_smart.const import (
    CONF_ALLOW_CONTROL,
    CONF_ALLOW_SETTINGS,
    CONF_DEVICES,
    CONF_POLL_INTERVAL,
    DOMAIN,
)

DEVICE_ID = "device"
AREA_KEY = "area1"
AREA_2_KEY = "area2"
SWITCH_UNIQUE_ID = f"{DEVICE_ID}_{AREA_KEY}_schedule_override"
NUMBER_UNIQUE_ID = f"{DEVICE_ID}_{AREA_KEY}_schedule_override_timeout"
LEGACY_ENTITY_ID = "switch.home_office_schedule_override"


@pytest.fixture
def mock_api(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Provide one live device without allowing vendor writes."""
    responses = {
        "async_get_areas": {
            AREA_KEY: {"label": "Office", "mode": "Manual 2"},
            AREA_2_KEY: {"label": "Bedroom", "mode": "Manual 2"},
        },
        "async_get_telemetry": {},
        "async_get_notifications": {},
        "async_get_gateway": {},
        "async_get_controller": {},
        "async_get_settings": {},
    }
    for method, value in responses.items():
        monkeypatch.setattr(SecSmartApi, method, AsyncMock(return_value=value))
    write = AsyncMock()
    monkeypatch.setattr(SecSmartApi, "async_set_area_mode", write)
    return write


def make_entry(
    *,
    entry_id: str = "schedule-entry",
    allow_control: bool = True,
    allow_settings: bool = False,
) -> ConfigEntry:
    """Build the same control-enabled entry users configure through the UI."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Home",
        data={
            CONF_TOKEN: "test-token",
            CONF_DEVICES: [{"id": DEVICE_ID, "name": "Home"}],
        },
        options={
            CONF_ALLOW_CONTROL: allow_control,
            CONF_ALLOW_SETTINGS: allow_settings,
            CONF_POLL_INTERVAL: 600,
        },
        source="user",
        unique_id="test-home",
        discovery_keys={},
        subentries_data=(),
        entry_id=entry_id,
    )


async def setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> tuple[str, str]:
    """Set up the integration and resolve its public service entity IDs."""
    if entry.entry_id not in {
        item.entry_id for item in hass.config_entries.async_entries()
    }:
        await hass.config_entries.async_add(entry)
    elif entry.state is ConfigEntryState.NOT_LOADED:
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    switch_id = registry.async_get_entity_id("switch", DOMAIN, SWITCH_UNIQUE_ID)
    number_id = registry.async_get_entity_id("number", DOMAIN, NUMBER_UNIQUE_ID)
    assert switch_id is not None
    assert number_id is not None
    return switch_id, number_id


async def set_timeout(hass: HomeAssistant, entity_id: str, minutes: int) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id, "value": minutes},
        blocking=True,
    )


async def set_switch(hass: HomeAssistant, entity_id: str, service: str) -> None:
    await hass.services.async_call(
        "switch", service, {"entity_id": entity_id}, blocking=True
    )


async def advance(hass: HomeAssistant, freezer, target: datetime) -> None:
    freezer.move_to(target)
    async_fire_time_changed(hass, target)
    await hass.async_block_till_done()


async def test_public_services_drive_real_scheduler_without_vendor_writes(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    freezer,
) -> None:
    """Service changes register, renew, cancel, and fire the HA loop timer."""
    now = datetime.now(UTC)
    entry = make_entry()
    office, timeout = await setup_entry(hass, entry)
    registry = er.async_get(hass)
    bedroom = registry.async_get_entity_id(
        "switch", DOMAIN, f"{DEVICE_ID}_{AREA_2_KEY}_schedule_override"
    )
    assert bedroom is not None
    assert hass.states.get(timeout).state == "0"
    assert hass.states.get(office).state == STATE_OFF

    await set_timeout(hass, timeout, 1)
    await set_switch(hass, office, "turn_on")
    await set_switch(hass, bedroom, "turn_on")
    await advance(hass, freezer, now + timedelta(seconds=30))
    await set_switch(hass, office, "turn_on")

    await advance(hass, freezer, now + timedelta(seconds=61))
    assert hass.states.get(office).state == STATE_ON
    assert hass.states.get(bedroom).state == STATE_ON

    await set_timeout(hass, timeout, 0)
    await advance(hass, freezer, now + timedelta(minutes=2))
    assert hass.states.get(office).state == STATE_ON

    await set_timeout(hass, timeout, 1)
    await set_switch(hass, office, "turn_off")
    await advance(hass, freezer, now + timedelta(minutes=4))
    assert hass.states.get(office).state == STATE_OFF

    await set_switch(hass, office, "turn_on")
    await advance(hass, freezer, now + timedelta(minutes=5, seconds=1))
    assert hass.states.get(office).state == STATE_OFF
    assert hass.states.get(bedroom).state == STATE_ON

    coordinator = entry.runtime_data[DEVICE_ID]
    coordinator.api.async_get_areas = AsyncMock(side_effect=RuntimeError("offline"))
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert hass.states.get(office).state == STATE_OFF
    assert hass.states.get(timeout).state == "1"
    mock_api.assert_not_awaited()


async def test_unload_reload_restores_timer_with_disabled_number(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    freezer,
) -> None:
    """Reload keeps the original deadline and needs no number entity."""
    now = datetime.now(UTC)
    entry = make_entry(entry_id="reload-entry")
    switch_id, number_id = await setup_entry(hass, entry)
    await set_timeout(hass, number_id, 1)
    await set_switch(hass, switch_id, "turn_on")
    initial_expires_at = hass.states.get(switch_id).attributes["expires_at"]
    await advance(hass, freezer, now + timedelta(seconds=30))

    assert await hass.config_entries.async_unload(entry.entry_id)
    registry = er.async_get(hass)
    registry.async_update_entity(number_id, disabled_by=er.RegistryEntryDisabler.USER)
    switch_id, reloaded_number_id = await setup_entry(hass, entry)
    assert hass.states.get(reloaded_number_id).state == STATE_UNAVAILABLE
    assert hass.states.get(switch_id).state == STATE_ON
    assert hass.states.get(switch_id).attributes["expires_at"] == initial_expires_at

    await advance(hass, freezer, now + timedelta(seconds=61))
    assert hass.states.get(switch_id).state == STATE_OFF
    mock_api.assert_not_awaited()


async def test_legacy_restore_migrates_once_and_stored_state_wins(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    freezer,
) -> None:
    """An actually added RestoreEntity migrates legacy on as indefinite once."""
    mock_restore_cache(hass, [State(LEGACY_ENTITY_ID, STATE_ON)])
    entry = make_entry(entry_id="legacy-entry")
    switch_id, _ = await setup_entry(hass, entry)
    assert switch_id == LEGACY_ENTITY_ID
    state = hass.states.get(switch_id)
    assert state.state == STATE_ON
    assert state.attributes["timeout_minutes"] == 0
    assert state.attributes["expires_at"] is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_restore_cache(hass, [State(LEGACY_ENTITY_ID, STATE_OFF)])
    switch_id, _ = await setup_entry(hass, entry)
    assert hass.states.get(switch_id).state == STATE_ON
    await advance(hass, freezer, datetime.now(UTC) + timedelta(minutes=5))
    assert hass.states.get(switch_id).state == STATE_ON
    mock_api.assert_not_awaited()


async def test_expired_downtime_and_invalid_storage_are_recovered(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    freezer,
) -> None:
    """Real Store reload retires elapsed state and preserves malformed active state."""
    entry = make_entry(entry_id="storage-entry")
    switch_id, number_id = await setup_entry(hass, entry)
    await set_timeout(hass, number_id, 1)
    await set_switch(hass, switch_id, "turn_on")
    assert await hass.config_entries.async_unload(entry.entry_id)

    await advance(hass, freezer, datetime.now(UTC) + timedelta(minutes=2))
    switch_id, _ = await setup_entry(hass, entry)
    assert hass.states.get(switch_id).state == STATE_OFF
    assert await hass.config_entries.async_unload(entry.entry_id)

    store: Store[dict] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.schedule_overrides")
    await store.async_save(
        {
            "areas": {
                f"{DEVICE_ID}\u001f{AREA_KEY}": {
                    "timeout_minutes": 15,
                    "is_on": True,
                    "expires_at": "not-a-date",
                },
                f"{DEVICE_ID}\u001f{AREA_2_KEY}": {
                    "timeout_minutes": True,
                    "is_on": "yes",
                    "expires_at": "2026-10-24T12:00:00+00:00",
                },
            }
        }
    )
    switch_id, _ = await setup_entry(hass, entry)
    state = hass.states.get(switch_id)
    assert state.state == STATE_ON
    assert state.attributes["expires_at"] is None
    bedroom_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{DEVICE_ID}_{AREA_2_KEY}_schedule_override"
    )
    bedroom = hass.states.get(bedroom_id)
    assert bedroom.state == STATE_OFF
    assert bedroom.attributes["timeout_minutes"] == 0
    assert "preserving it indefinitely" in caplog.text
    mock_api.assert_not_awaited()


async def test_settings_only_entry_does_not_create_override_entities(
    hass: HomeAssistant,
    mock_api: AsyncMock,
) -> None:
    """The public platform surface follows control and settings permissions."""
    entry = make_entry(
        entry_id="settings-entry", allow_control=False, allow_settings=True
    )
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, SWITCH_UNIQUE_ID) is None
    assert registry.async_get_entity_id("number", DOMAIN, NUMBER_UNIQUE_ID) is None
    assert (
        registry.async_get_entity_id("number", DOMAIN, f"{DEVICE_ID}_humidity")
        is not None
    )
    mock_api.assert_not_awaited()
