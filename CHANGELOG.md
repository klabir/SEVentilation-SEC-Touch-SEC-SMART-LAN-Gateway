# Changelog

## [Unreleased]

### Breaking Changes

### Added

- Initial SEC Smart cloud integration with Config Flow, discovery, telemetry, diagnostics and opt-in fan control.
- Documented a native Home Assistant Schedule-helper design that replaces the five-slot vendor timer limit with reconciled weekly blocks.

### Changed

### Fixed

- Accept the live SEC Smart `/devices` response field `deviceid` in addition to the documented `id` field.
- Interpret SEC notification code `00` as no active error.
- Mark an all-zero environmental telemetry block unavailable instead of reporting misleading zero measurements.

### Removed
