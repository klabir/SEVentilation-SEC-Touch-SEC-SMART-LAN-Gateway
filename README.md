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
- optional Free Cooling and absolute-humidity schedule-overlay Blueprints
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

The Blueprint does not create a fixed schedule. The Schedule helper contains the
times and desired SEC mode; the Blueprint reads the currently active block and
applies it to the selected ventilation area. This removes the SEC app's limit of
five timer slots because a Home Assistant Schedule helper can contain as many
blocks as required and can use a different plan for every weekday.

The canonical profile for this Blueprint is **Example B — morning purge and
reduced night operation**. Its five blocks are listed below and are also shown in
the Blueprint description in Home Assistant. The reconciliation engine remains
generic, so users can add or change blocks after the canonical profile works.

### 1. Prepare the vendor app

For each HA-managed area:

1. Disable all five `Schaltzeit` switches. Leave the stored times intact for rollback.
2. Select **Manual** mode.
3. Select the level that should remain active until the first HA reconciliation.

Do not leave **Timed program** selected while Home Assistant owns the schedule. The integration's **vendor timers active** sensor identifies ownership conflicts.

### 2. Create a Schedule helper

Open **Settings > Devices & services > Helpers**, create a Schedule helper, and cover the complete day with touching blocks. A gap deliberately leaves the previously applied mode active.

Each block uses **Additional data**. The keys are case-sensitive and the mode
value must use one of the values below.

| Desired operation | Additional data | Result |
| --- | --- | --- |
| Manual level 1–6 | `mode: manual` and `level: 1` … `6` | Sets the corresponding discrete fan level |
| Fans off | `mode: off` | Turns the area fan off |
| Boost ventilation | `mode: boost` | Selects the SEC Boost mode |
| Humidity regulation | `mode: humidity` | Selects humidity-controlled operation |
| CO2 regulation | `mode: co2` | Selects CO2-controlled operation |
| Snooze | `mode: snooze` | Selects Snooze using the configured SEC Snooze duration |
| Vendor timed program | `mode: schedule` | Selects the SEC device's own five-slot timed program |

For a manual block, enter both fields:

```yaml
mode: manual
level: 2
```

All other modes omit `level`:

```yaml
mode: humidity
```

`level` is ignored for non-manual modes. A manual level outside 1–6 or an
unknown mode is rejected by the Blueprint without sending a device command.
Normally avoid `mode: schedule` when Home Assistant owns scheduling because it
hands control back to the vendor timer slots.

#### Canonical Blueprint schedule: Example B

Configure these blocks on Monday through Sunday. They cover every minute of the
day without gaps or overlaps.

| Time | Mode | Level |
| --- | --- | ---: |
| 00:00–01:00 | `manual` | 1 |
| 01:00–07:40 | `manual` | 2 |
| 07:40–09:00 | `manual` | 6 |
| 09:00–22:00 | `manual` | 2 |
| 22:00–24:00 | `manual` | 1 |

For each block, enter `mode: manual` and the listed `level` as Additional data.
After Example B is working, the helper can be extended with more blocks or with
the other supported modes. The Blueprint logic does not impose a five-block
limit.

### 3. Import and configure the Blueprint

Blueprint source:

```text
https://github.com/klabir/SEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway/blob/main/blueprints/automation/sec_smart/schedule_reconciliation.yaml
```

[![Open your Home Assistant instance and import the Schedule-reconciliation Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fklabir%2FSEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsec_smart%2Fschedule_reconciliation.yaml)

Import it under **Settings > Automations & scenes > Blueprints**, then create one automation per area and select the Schedule helper, SEC Smart fan, area mode sensor, Schedule-override switch, and optional failure actions.

Configure these inputs with entities from the same SEC area:

| Blueprint input | Required | Configuration |
| --- | --- | --- |
| **Schedule helper** | Yes | The `schedule` entity containing the canonical Example B blocks, or a customized version, with Additional data |
| **SEC Smart area fan** | Yes | The `fan` entity that receives mode and level commands |
| **SEC Smart area mode sensor** | Yes | The mode sensor used to suppress duplicate writes and confirm the result |
| **Manual override switch** | No | The area's Schedule override switch; when on, the Blueprint sends no commands |
| **Confirmation failure actions** | No | Actions to run when the mode sensor still differs 45 seconds after a completed command |

Create a separate Blueprint automation for every area. Do not connect the fan
from one area to the mode or override entity from another area.

An automation instance generated by the Blueprint has this shape; replace the
example entity IDs with the entities selected in the UI:

```yaml
alias: SEC Smart schedule reconciliation - Example area
use_blueprint:
  path: klabir/SEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway/schedule_reconciliation.yaml
  input:
    schedule_entity: schedule.seventilation_example_area
    fan_entity: fan.sec_smart_example_area
    mode_sensor: sensor.sec_smart_example_area_mode
    override_entity: switch.sec_smart_example_area_schedule_override
    failure_actions:
      - action: persistent_notification.create
        data:
          title: SEC Smart schedule command not confirmed
          message: Check the SEC cloud connection and the automation trace.
```

### What the Blueprint does

The automation runs in queued mode and evaluates the active Schedule block on:

1. every `schedule.block_started` event for the selected helper;
2. every Home Assistant start; and
3. every five minutes, to repair a missed transition or a temporary cloud failure.

On each run it proceeds only when:

- the Schedule helper is `on`, meaning the current time is inside a block;
- the selected fan is available; and
- the optional Schedule override switch is absent or off.

It then reads `mode` and `level` from the active block, converts them to the SEC
fan command, and compares the requested mode with the area mode sensor. If the
area already has the desired mode, it sends nothing. This duplicate suppression
prevents an unnecessary cloud write every five minutes.

After a command, the Blueprint waits up to 45 seconds for the mode sensor to
confirm the requested state. If confirmation does not arrive, it runs the
configured failure actions. A service-call exception is recorded in the
automation trace and the normal five-minute trigger provides the next retry.

Important boundary behavior:

- A new block is normally applied immediately at its start time.
- After Home Assistant restarts, the active block is reapplied if necessary.
- Turning Schedule override off does not itself trigger the Blueprint; control
  resumes at the next five-minute reconciliation or block boundary.
- A gap in the Schedule helper makes the helper `off`; the Blueprint deliberately
  sends no command and the area's last applied mode remains active.
- Disabling the automation freezes scheduling at the last mode already sent; it
  does not automatically restore the vendor timed program.

### Manual override

Turn on an area's **Schedule override** switch before changing that area in the vendor app, SEC-Touch, or HA fan entity. The Blueprint leaves it untouched until the switch is turned off. The switch is local to HA and persists across restarts. If the switch remains off, a manual change can be reverted by the next five-minute reconciliation.

## Adaptive schedule overlays

The repository includes two optional Blueprints inspired by useful automation
ideas found in other community projects. They are independent implementations
with stricter safety behavior: invalid sensors never become zero, start and stop
thresholds are separated, rapid switching is blocked, cloud writes are
deduplicated, and the resulting SEC mode is confirmed.

An adaptive overlay contains the complete schedule-reconciliation logic. For a
given area, use exactly one of these three choices:

1. the basic Schedule-reconciliation Blueprint;
2. the Free Cooling overlay; or
3. the absolute-humidity overlay.

Do not run two choices against the same area. Parallel automations would compete
for control. Both overlays require a Schedule helper that covers the complete
day, because the active Schedule block is the state restored when adaptive
ventilation ends.

For either overlay:

1. Create a dedicated **Input Boolean** helper for each area. It is an internal,
   persistent adaptive-state latch; do not share it or toggle it manually.
2. Import the chosen Blueprint and create one automation for the area.
3. Select the area's Schedule helper, SEC fan, mode sensor, Schedule-override
   switch, and the SEC cloud-connection binary sensor.
4. Select the required environmental sensors and review every threshold.
5. Disable the area's basic Schedule-reconciliation automation before enabling
   the overlay.

The Schedule override switch always wins. While it is on, the overlay neither
changes the fan nor modifies its adaptive-state latch. When it is turned off,
the next sensor update, five-minute reconciliation, or block boundary resumes
automatic control.

### Free Cooling overlay

Blueprint source:

```text
https://github.com/klabir/SEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway/blob/main/blueprints/automation/sec_smart/free_cooling_overlay.yaml
```

[![Open your Home Assistant instance and import the Free Cooling Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fklabir%2FSEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsec_smart%2Ffree_cooling_overlay.yaml)

Free Cooling raises the area to a selected manual level only when the indoor
temperature is high **and** outdoor air is sufficiently cooler. It is intended
for warm-weather night or morning ventilation, not frost or humidity protection.

| Input | Default | Meaning |
| --- | ---: | --- |
| Start indoor temperature | 24 °C | Indoor temperature must reach this value |
| Stop indoor temperature | 22.5 °C | Stop when indoor temperature falls to this value |
| Start indoor/outdoor difference | 2 °C | Indoor air must be at least this much warmer |
| Stop indoor/outdoor difference | 1 °C | Stop when the useful temperature difference falls to this value |
| Active manual level | 4 | SEC level used during Free Cooling |
| Minimum active/inactive dwell | 15 min | Earliest allowed state change after the previous one |

The stop values must be lower than the corresponding start values. This
hysteresis prevents repeated switching around a single threshold.

### Absolute-humidity overlay

Blueprint source:

```text
https://github.com/klabir/SEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway/blob/main/blueprints/automation/sec_smart/absolute_humidity_overlay.yaml
```

[![Open your Home Assistant instance and import the absolute-humidity Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fklabir%2FSEVentilation-SEC-Touch-SEC-SMART-LAN-Gateway%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsec_smart%2Fabsolute_humidity_overlay.yaml)

This overlay uses indoor/outdoor temperature and relative humidity to calculate
absolute humidity in g/m³. It raises ventilation only when indoor relative
humidity is high and outdoor air actually contains less water. Comparing raw
relative-humidity percentages would be misleading when indoor and outdoor
temperatures differ.

| Input | Default | Meaning |
| --- | ---: | --- |
| Start indoor relative humidity | 60% | Indoor humidity must reach this value |
| Stop indoor relative humidity | 55% | Stop when indoor humidity falls to this value |
| Start absolute-humidity difference | 1.5 g/m³ | Indoor air must contain at least this much more water |
| Stop absolute-humidity difference | 0.5 g/m³ | Stop when drying benefit falls to this value |
| Active manual level | 4 | SEC level used during humidity ventilation |
| Minimum active/inactive dwell | 15 min | Earliest allowed state change after the previous one |

The overlay starts only when both start conditions are true. It stops when
either stop condition becomes true. The stop thresholds must be lower than the
start thresholds.

### Overlay safety behavior

| Situation | Behavior |
| --- | --- |
| Any required sensor is unknown, unavailable, or non-numeric | Send no command and preserve the latch |
| Schedule override is on | Leave the area and latch untouched |
| Optional cloud-connection sensor is off | Send no command |
| Desired mode is already active | Suppress the duplicate cloud write |
| Command is sent | Wait up to 45 seconds for mode-sensor confirmation |
| Confirmation fails | Run the optional failure actions |
| Adaptive condition ends | Restore the currently active Schedule block |
| Home Assistant restarts | Re-evaluate sensors, latch, and current Schedule block |

The Blueprints do not replace frost, condensation, or building-protection logic
provided by SEC hardware. Start with conservative thresholds and inspect
automation traces before relying on unattended operation.

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
