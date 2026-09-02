# Changelog

## [Unreleased]

### Added

- Add safe Free Cooling and absolute-humidity schedule-overlay Blueprints with
  persistent hysteresis latches, minimum dwell time, Schedule restoration,
  manual-override and cloud-health gates, duplicate suppression, and command
  confirmation.
- Add regression tests for Blueprint parsing and adaptive-control safety guards.

### Changed

- Document the Schedule-reconciliation Blueprint's triggers, conditions,
  supported block data, canonical schedule, inputs, confirmation behavior, and
  manual-override semantics.
- Make Example B (morning purge and reduced night operation) the canonical
  Blueprint schedule profile in the Blueprint UI and README.

## [0.3.0] - 2026-09-02

### Added

- Persistent per-area Home Assistant Schedule override switches.
- Reusable Schedule-reconciliation Blueprint with confirmation and failure actions.
- Cloud connection, endpoint health, vendor timer ownership, per-area Snooze, last-command, and last-update entities.
- Opt-in CO2/humidity thresholds, Snooze duration, summer mode, and filter-lifetime controls.
- Disabled-by-default filter-life reset button.
- Gateway/controller metadata and privacy-redacted diagnostics.
- CI, MIT license, typed API payload models, and broader API/normalization tests.

### Changed

- Split fast operational polling from slower notifications and metadata polling.
- Serialize per-area writes and confirm all area/settings changes through cloud read-back.
- Retry bounded transient network, rate-limit, and server failures.
- Normalize numeric and boolean payloads strictly.
- Replace site-specific schedule examples with neutral documentation.

### Fixed

- Accept the live `/devices` field `deviceid` in addition to documented `id`.
- Interpret notification code `00` as no active error.
- Mark an all-zero environmental telemetry block unavailable instead of reporting false zero measurements.

## [0.1.0] - 2026-09-02

- Initial SEC Smart cloud integration with Config Flow, discovery, telemetry, diagnostics, and opt-in fan control.
