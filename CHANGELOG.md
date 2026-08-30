# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.5] - 2026-08-30

### Fixed

- Never write a YAML/import-owned HomeKit side entry during rollback. If an
  imported side entry changes after backup, writable entries are still restored
  and the rollback is reported as incomplete instead of overwriting YAML-owned
  state.
- Keep fixed imported single-entity HomeKit side targets compatible regardless
  of their stored HomeKit mode, and clarify in the English and Traditional
  Chinese setup UI which selected targets are writable or fixed and read-only.

## [0.6.4] - 2026-08-30

### Fixed

- Allow an exact YAML/import-managed single-entity HomeKit side entry to remain
  as a fixed member of a target layout while requiring the writable main Bridge
  to be UI-managed. This preserves durable mixed layouts used by existing Home
  Assistant installations without ever rewriting YAML-owned side entries.

## [0.6.3] - 2026-08-30

### Added

- Added optional Matterbridge frontend-password authentication and support for
  complete `ws`, `wss`, `http`, or `https` management endpoints, including
  reverse-proxy paths and IPv6 hosts. TLS verification remains enabled by
  default and credentials are omitted from diagnostics and error messages.
- Added fail-closed HomeKit runtime-status readback. A target is accepted only
  when every selected Bridge or Accessory is loaded and its runtime is
  verifiably running.

### Changed

- Runtime warm-up no longer blocks the final configuration step. Complete
  settings are saved first, then the existing bounded background retries wait
  for Google Home, HomeKit, or Matterbridge to converge.
- Matterbridge automatic recovery now observes a three-minute startup grace and
  a sustained failure window before any guarded restart is eligible.
- HomeKit target Config Entry changes now wake reconciliation. UI-created
  HomeKit entries rely on their native update listener instead of receiving a
  duplicate reload, and unchanged entries are not reloaded at all.
- Changed HomeKit source selection to validate its durable entity filters
  without blocking on a temporary startup state; runtime readiness is retried
  after the complete configuration has been saved.

### Fixed

- Preserve the current form values after validation errors instead of
  reverting fields to their previous saved values.
- Save and reopen a complete canonical options snapshot, including source
  details, Google Assistant YAML path, selected HomeKit entries, Matterbridge
  connection fields, and all three platforms' additions and exclusions.
  Settings for temporarily unselected platforms remain stored but inactive.
- Deep-merge partial historical `user_rules` options so one platform cannot
  erase another platform's additions or exclusions.
- Wait for Matterbridge to report the newly saved exact allowlist before
  restarting `matterbridge-hass`; a restart timeout is treated as an uncertain
  result and is resolved by readback without sending a second restart.
- Extend Matterbridge restart and runtime deadlines for larger installations,
  and extend rollback/unload budgets to cover those verified operations.
- Reject YAML/import-managed HomeKit entries as writable targets while still
  allowing them as read-only sources, preventing temporary updates that would
  revert after an HA restart. Multiple HomeKit reloads now settle before
  rollback begins.

## [0.6.2] - 2026-08-29

### Added

- Added guarded Matterbridge runtime recovery for enabled background checks.
  A recoverable runtime-only failure now waits for a verified Matterbridge
  backup, tries a plugin restart first, and uses one full-process restart only
  when exact runtime readback still does not converge.
- Added one-attempt-per-failure-episode protection, a five-minute recovery
  cooldown, and bounded retry delays of 15, 30, 60, 120, then 300 seconds.

### Fixed

- Wait for Matterbridge's asynchronous archive-complete event instead of
  treating the initial backup request acknowledgement as a completed backup.
- Validate Matterbridge runtime and loaded devices when Matterbridge is the
  selected source, not only when it is a target.
- Allow enough time for a cancelled multi-platform transaction to complete its
  full reverse-order rollback before Home Assistant unload finishes.

## [0.6.1] - 2026-08-29

### Changed

- Changed the license for version 0.6.1 and later from MIT to the PolyForm
  Noncommercial License 1.0.0. The source may be inspected, modified, and
  redistributed for permitted noncommercial purposes; commercial use is not
  licensed.
- Documented HACS installation through Custom repositories and retained
  Home Assistant hassfest validation. The noncommercial license is not eligible
  for the OSI-license check required by the default HACS catalog.

## [0.6.0] - 2026-08-29

### Added

- Conditional, multilingual configuration flow with English and Traditional
  Chinese text.
- Dashboard multi-view, manual entity, Google Home, HomeKit, and Matterbridge
  sources.
- Independent Google Home, HomeKit, and Matterbridge targets with per-platform
  additions and exclusions.
- Event-driven dashboard and HomeKit change detection with guarded 15-second
  fallback polling where needed.
- Startup reconciliation, two-second change coalescing, no-op detection,
  transactional backup, rollback, and exact readback.
- Exact selected-target convergence removes pre-existing extra exposures while
  preserving per-platform additions, exclusions, and protected rules.
- Preview and synchronize-now actions without creating extra entities.
- HACS-compatible repository structure, public documentation, and automated
  validation.

[Unreleased]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.5...HEAD
[0.6.5]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.4...v0.6.5
[0.6.4]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/jameslu34/ha-platform-sync/releases/tag/v0.6.0
