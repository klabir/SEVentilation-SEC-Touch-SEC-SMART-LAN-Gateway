# SEC Smart Ventilation for Home Assistant

Cloud-polling Home Assistant integration for SEVentilation systems connected through a SEC-Touch and SEC-SMART LAN Gateway.

> [!IMPORTANT]
> The SEC cloud API is the transport and may change without notice. The physical SEC-Touch and vendor app remain the authoritative fallback. Factory reset, hardware assignment, and low-level commissioning endpoints are intentionally excluded.

## Features

- Home Assistant Config Flow with masked API-token entry and reauthentication
- automatic SEC Smart device and area discovery
- CO2, humidity, indoor/outdoor temperature, filter life, uptime, and per-area Snooze sensors
- area mode and last-command confirmation sensors
- cloud/API health with per-endpoint diagnostics
- filter and active-error problem sensors
- vendor-timer ownership sensor per area
- gateway/controller firmware and hardware metadata
- optional area control with six manual levels and SEC operating modes
- persistent per-area **Schedule override** switches
- optional settings controls for thresholds, Snooze duration, summer mode, and filter lifetime
- disabled-by-default filter-life reset button
- Blueprint-based Home Assistant scheduling beyond the five vendor timer slots
- serialized writes, transient-error retries, rate-limit handling, and command read-back

## Installation

### HACS custom repository

1. Open **HACS > Integrations**.
2. Open the menu and select **Custom repositories**.
3. Add this repository as an **Integration**.
4. Install **SEC Smart Ventilation** and restart Home Assistant once.

For a manual installation, copy `custom_components/sec_smart` to `/config/custom_components/` and restart Home Assistant once.

Then add **SEC Smart Ventilation** under **Settings > Devices & services**. Enter the API token only in Home Assistant's masked configuration form; never put it in YAML, source code, URLs, or logs.

## Integration options

The initial setup is read-only. Open the integration's **Configure** dialog to opt in to:

- **Allow ventilation control**: creates one `fan` and one local Schedule-override switch per active area.
- **Allow system settings control**: exposes CO2/humidity thresholds, Snooze duration, summer mode, and filter maximum runtime.
- **Polling interval**: 30–600 seconds; 60 seconds is recommended.

The filter reset button remains disabled in the entity registry until explicitly enabled. Enabling settings does not change any value by itself.

### Area control

The `fan` entities expose Off, manual levels 1–6, Boost, humidity regulation, CO2 regulation, Timed program, and Snooze.

| SEC level | HA percentage |
| ---: | ---: |
| 1 | 16% |
| 2 | 33% |
| 3 | 50% |
| 4 | 67% |
| 5 | 83% |
| 6 | 100% |

Every cloud write is serialized per area and confirmed by reading the resulting SEC state.

## Scheduling beyond five vendor timers

Use one native Home Assistant **Schedule helper** and one Blueprint automation per area. Home Assistant becomes the schedule owner, while SEC-Touch and the vendor app remain available for deliberate manual overrides.

### 1. Prepare the vendor app

For each HA-managed area:

1. Disable all five `Schaltzeit` switches. Leave the stored times intact for rollback.
2. Select **Manual** mode.
3. Select the level that should remain active until the first HA reconciliation.

Do not leave **Timed program** selected while Home Assistant owns the schedule. The integration's **vendor timers active** sensor identifies ownership conflicts.

### 2. Create a Schedule helper

Open **Settings > Devices & services > Helpers**, create a Schedule helper, and cover the complete day with touching blocks. A gap deliberately leaves the previously applied mode active.

Each block uses **Additional data**. For a manual block:

```yaml
mode: manual
level: 2
```

Other valid modes omit `level`:

```yaml
mode: humidity
```

Supported `mode` values: `manual`, `off`, `boost`, `humidity`, `co2`, `snooze`, and `schedule`. Normally avoid `schedule` when HA owns scheduling.

Neutral example:

| Time | Additional data |
| --- | --- |
| 00:00–06:00 | `mode: manual`, `level: 1` |
| 06:00–08:00 | `mode: manual`, `level: 3` |
| 08:00–18:00 | `mode: co2` |
| 18:00–24:00 | `mode: manual`, `level: 2` |

### 3. Import and configure the Blueprint

Blueprint source:

```text
https://github.com/klabir/SEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway/blob/main/blueprints/automation/sec_smart/schedule_reconciliation.yaml
```

Import it under **Settings > Automations & scenes > Blueprints**, then create one automation per area and select the Schedule helper, SEC Smart fan, area mode sensor, Schedule-override switch, and optional failure actions.

The automation applies every block boundary, reconciles every five minutes, recovers after HA restarts, suppresses duplicate commands, and verifies the result.

### Manual override

Turn on an area's **Schedule override** switch before changing that area in the vendor app, SEC-Touch, or HA fan entity. The Blueprint leaves it untouched until the switch is turned off. The switch is local to HA and persists across restarts.

### Scheduler rollback

1. Disable the Blueprint automation.
2. Re-enable the required vendor timer switches.
3. Select **Timed program** if vendor timers should resume control.
4. Remove HA Schedule helpers only after vendor control is confirmed.

## Reliability model

- Areas and telemetry use the configured fast polling interval.
- Notifications refresh every five minutes.
- Gateway, controller, and settings metadata refresh hourly.
- HTTP 429/502/503/504 and transient network failures receive bounded retries.
- Authentication failure starts Home Assistant's reauthentication flow.
- Optional endpoint failures do not discard otherwise valid area state.
- Diagnostics redact identifiers, labels, schedules, addresses, messages, and credentials.

Automations should check the cloud-connection sensor, avoid decisions from unavailable telemetry, and use the Schedule override switch for human ownership.

## Development

```bash
python -m compileall -q custom_components tests
pytest -q
```

CI validates Python, JSON, YAML, tests, and HACS structure.

## Rollback

Disable related automations, remove the config entry, delete `/config/custom_components/sec_smart`, and restart Home Assistant once. The SEC-Touch and vendor app continue to operate independently.

## License

[MIT](LICENSE)
