# SEC Smart Ventilation for Home Assistant

Cloud-polling Home Assistant integration for SEVentilation systems connected through a SEC-Touch and SEC-SMART LAN Gateway.

## Status

Version 0.1.0 is a staged beta. It provides:

- UI configuration with masked bearer-token entry
- automatic discovery of SEC Smart devices
- area mode, CO2, humidity, indoor/outdoor temperature, filter life and uptime sensors
- filter and active-error binary sensors
- gateway/controller metadata in the Home Assistant device registry
- optional area control, disabled by default
- reauthentication on expired credentials

The SEC cloud API is the transport. The physical SEC-Touch and vendor app remain the fallback.

## Installation

### HACS custom repository

1. Open **HACS > Integrations**.
2. Open the menu and select **Custom repositories**.
3. Add this repository as an **Integration**.
4. Install **SEC Smart Ventilation** and restart Home Assistant once.

For a manual installation, copy `custom_components/sec_smart` into Home Assistant's `/config/custom_components/` and restart Home Assistant once.

After installation, add **SEC Smart Ventilation** under **Settings > Devices & services**.

Enter the API token only in Home Assistant's masked configuration form. Do not put it in YAML, source code or logs.

## Enabling control

The initial setup is read-only. After verifying sensor values, open the integration's **Configure** dialog and enable **Allow ventilation control**. This creates one `fan` entity for each active area. Commands are read back after every write.

Exposed modes:

- Off
- Manual levels 1-6
- Boost ventilation
- Humidity regulation
- CO2 regulation
- Timed program
- Snooze

Factory reset, hardware assignment and low-level I/O setup are intentionally not implemented.

## Home Assistant scheduler

The SEC app provides only five timer slots per area. Home Assistant's native Schedule helper can replace that limit with as many weekly blocks as the Home Assistant schedule supports.

The recommended design is:

- one native Schedule helper per ventilation area
- the requested SEC mode and manual level stored as block **Additional data**
- one queued automation that applies block changes
- a startup and five-minute reconciliation trigger for outage recovery
- the SEC app and SEC-Touch retained as fallbacks

### 1. Prepare the SEC app

For each area:

1. Disable all five `Schaltzeit`/timer switches. The original times and modes can remain stored for rollback.
2. Select **Manual** mode.
3. Select an initial manual level that matches the currently active Home Assistant block.

Do not leave the area in **Timed program** mode while Home Assistant owns the schedule. Humidity, CO2, Boost and Snooze modes should only be selected when a Home Assistant schedule block or a deliberate manual override requires them.

### 2. Create Schedule helpers

Open **Settings > Devices & services > Helpers**, create one **Schedule** helper per area and cover the entire day with touching blocks. Gaps leave the previously applied SEC mode active because no new block is selected.

Open each block and add one of these mappings under **Additional data**:

```yaml
mode: manual
level: 2
```

For manual operation, `level` must be an integer from 1 through 6. Other supported mappings do not need `level`:

```yaml
mode: off
```

Supported `mode` values are:

| Value | SEC operating mode |
| --- | --- |
| `manual` | Manual level 1-6 |
| `off` | Fans off |
| `boost` | Boost ventilation |
| `humidity` | Humidity regulation |
| `co2` | CO2 regulation |
| `snooze` | Snooze |
| `schedule` | SEC timed program; normally avoid when HA owns scheduling |

Manual levels map to Home Assistant fan percentages as follows:

| SEC level | HA percentage |
| ---: | ---: |
| 1 | 16% |
| 2 | 33% |
| 3 | 50% |
| 4 | 67% |
| 5 | 83% |
| 6 | 100% |

Example weekly blocks currently used for two areas:

**Office**

| Time | Additional data |
| --- | --- |
| 00:00-05:00 | `mode: manual`, `level: 2` |
| 05:00-05:30 | `mode: manual`, `level: 6` |
| 05:30-13:15 | `mode: manual`, `level: 2` |
| 13:15-13:30 | `mode: manual`, `level: 6` |
| 13:30-24:00 | `mode: manual`, `level: 2` |

**Bedroom**

| Time | Additional data |
| --- | --- |
| 00:00-01:00 | `mode: manual`, `level: 1` |
| 01:00-07:40 | `mode: manual`, `level: 2` |
| 07:40-09:00 | `mode: manual`, `level: 6` |
| 09:00-22:00 | `mode: manual`, `level: 2` |
| 22:00-24:00 | `mode: manual`, `level: 1` |

Apply the blocks to every required weekday.

### 3. Add the reconciliation automation

Replace the example schedule, fan and mode-sensor entity IDs with the entities from your Home Assistant instance. Add or remove entries under `for_each` for additional areas.

```yaml
alias: SEC Smart schedule reconciliation
description: Applies the active HA Schedule block to each SEC Smart area and confirms the resulting mode.
triggers:
  - trigger: schedule.block_started
    target:
      entity_id:
        - schedule.seventilation_office
        - schedule.seventilation_bedroom
  - trigger: homeassistant
    event: start
  - trigger: time_pattern
    minutes: /5
conditions: []
actions:
  - repeat:
      for_each:
        - schedule: schedule.seventilation_office
          fan: fan.sec_smart_office
          mode_sensor: sensor.sec_smart_office_mode
        - schedule: schedule.seventilation_bedroom
          fan: fan.sec_smart_bedroom
          mode_sensor: sensor.sec_smart_bedroom_mode
      sequence:
        - variables:
            desired_mode: "{{ state_attr(repeat.item.schedule, 'mode') | default('', true) }}"
            desired_level: "{{ state_attr(repeat.item.schedule, 'level') | int(0) }}"
            expected_mode: >-
              {% if desired_mode == 'manual' %}Manual {{ desired_level }}
              {% elif desired_mode == 'off' %}Fans off
              {% elif desired_mode == 'boost' %}Boost ventilation
              {% elif desired_mode == 'humidity' %}Humidity regulation
              {% elif desired_mode == 'co2' %}CO2 regulation
              {% elif desired_mode == 'schedule' %}Timed program
              {% elif desired_mode == 'snooze' %}Snooze
              {% else %}invalid{% endif %}
        - if:
            - condition: template
              value_template: >-
                {{ is_state(repeat.item.schedule, 'on')
                   and states(repeat.item.fan) not in ['unavailable', 'unknown']
                   and expected_mode != 'invalid'
                   and states(repeat.item.mode_sensor) != expected_mode }}
          then:
            - choose:
                - conditions: "{{ desired_mode == 'manual' and 1 <= desired_level <= 6 }}"
                  sequence:
                    - action: fan.set_percentage
                      target:
                        entity_id: "{{ repeat.item.fan }}"
                      data:
                        percentage: "{{ [0, 16, 33, 50, 67, 83, 100][desired_level] }}"
                - conditions: "{{ desired_mode == 'off' }}"
                  sequence:
                    - action: fan.turn_off
                      target:
                        entity_id: "{{ repeat.item.fan }}"
              default:
                - action: fan.set_preset_mode
                  target:
                    entity_id: "{{ repeat.item.fan }}"
                  data:
                    preset_mode: "{{ desired_mode }}"
            - wait_template: "{{ states(repeat.item.mode_sensor) == expected_mode }}"
              timeout: "00:00:45"
              continue_on_timeout: true
mode: queued
max: 10
max_exceeded: warning
```

The automation suppresses duplicate commands, confirms changes through the area mode sensor, runs at every block boundary, recovers after Home Assistant restarts and reconciles missed changes every five minutes.

### Manual override

Changes made in the SEC app or through the fan entity are restored to the active Schedule block within five minutes. For a longer manual override, disable **SEC Smart schedule reconciliation** first, make the manual change, and re-enable the automation when Home Assistant should resume ownership.

### Scheduler rollback

1. Disable **SEC Smart schedule reconciliation**.
2. Re-enable the required five timer switches in the SEC app.
3. Select **Timed program** in the SEC app if the vendor timers should resume control.
4. Remove the Home Assistant Schedule helpers only after vendor control is confirmed.

## Rollback

Disable related automations, remove the config entry, delete `/config/custom_components/sec_smart`, and restart Home Assistant. The SEC-Touch and SEC app continue to operate independently.
