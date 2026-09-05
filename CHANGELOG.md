# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Route every user-visible Platform Sync runtime notice exclusively through
  Home Assistant's native persistent-notification component. No mobile notify
  service, webhook, custom dashboard, or external push fallback is used when
  the native notification component is unavailable.

## [0.7.1] - 2026-09-05

### Fixed

- Declare the native Home Assistant Google Assistant integration as an
  after-dependency now that Platform Sync validates Google SYNC serialization.
  This preserves optional setup ordering and satisfies hassfest dependency
  validation.

## [0.7.0] - 2026-09-05

### Added

- Add explicitly owned HomeKit accessory lifecycle management. Accessory-mode
  devices are created automatically after the reversible platform transaction;
  removed devices require two matching source observations before an exact,
  backed-up deletion. Main/source/unowned entries remain protected.
- Show the exact devices that need extra platform pairing on the setup review
  screen and in a persistent, secret-free Home Assistant notification after
  native HomeKit accessory creation. Separately commissionable Matter RVC
  server nodes are listed as controller-side checks, without reading or
  exposing a QR code, PIN, fabric identity, or token.
- Add privacy-safe diagnostic error categories so controller, runtime API, and
  platform readiness failures can be distinguished without exposing entity IDs.
- Add a five-minute target health reconciliation for event-driven and manual
  sources so target drift is detected even when no source event is emitted.
- Change Google Home, Matterbridge, and HomeKit compatibility fallback polling
  from 15 to 60 seconds, and let that full reconciliation replace the duplicate
  five-minute timer to reduce reads, traffic, and scheduler work.
- Validate Home Assistant's actual Google SYNC serialization for native locks,
  security systems, and cameras. These safety-sensitive entities must retain
  their native Google device type and are never silently downgraded to switches.
- Reconcile on Core startup, Platform Sync Config Entry reload, and the global
  `homeassistant.reload_all` quick-reload boundary. Google Home and Matterbridge
  source modes retain one 60-second fallback poll where no reliable source
  change event exists.

### Fixed

- Fail closed before deleting a YAML/import HomeKit accessory unless its
  dedicated include file contains exactly one matching name, port, and entity
  block. The main `configuration.yaml`, wrong files, absent blocks, ambiguous
  blocks, and identity changes are never treated as successful retry evidence.
- Preserve HomeKit accessory ownership when native creation is cancelled or
  fails after the Config Entry was created, reject broad competing HomeKit
  filters, and recheck concurrent duplicates so a partially completed flow
  cannot leave an unmanaged orphan.
- Migrate cameras, locks, supported TV-class media players, and activity remotes
  out of the main HomeKit Bridge even when an older configuration already put
  them there. Missing TV/remote state now fails closed instead of silently
  selecting bridge mode.
- Persist HomeKit's `restart required` result and report synchronization as
  incomplete until a new Home Assistant Core process starts. Config-entry
  reloads and concurrent Options Flow edits cannot erase lifecycle, pairing,
  or restart ledgers.
- Enable Apple TV provenance protection for fresh configurations and recheck it
  both before the reversible transaction and before an irreversible HomeKit
  lifecycle action.
- Verify every linked user's complete native Google SYNC payload before and
  after Request Sync, including exact IDs and duplicate detection. Read-only
  sensor and binary-sensor entities that the installed Home Assistant Google
  classifier explicitly reports as unsupported are counted separately rather
  than treated as missing; security and controllable devices remain strict. A
  2xx Request Sync is reported only as accepted; Google HomeGraph readback
  remains explicit as unverified.
- Use a full Matterbridge process restart and generation barrier for removal
  plans so a stale aggregator endpoint cannot pass merely because the plugin's
  local device index was cleared.
- Read storage-backed Lovelace dashboards from disk during reconciliation so
  the 15-second missed-event audit cannot be trapped on Home Assistant's cached
  `LovelaceStorage._data`. Also recognize camera-specific entity fields and
  nested presentation containers without exposing condition-only helpers. This
  local-only audit remains active even
  when a selected target also needs slower compatibility polling.
- Prevent a newly discovered HomeKit accessory-mode device (such as a camera)
  from rolling back otherwise valid Google and Matter updates. The entity is
  reported as deferred until its dedicated HomeKit accessory is paired.
- Detect storage-dashboard edits whose Home Assistant save path omits the
  `lovelace_updated` event. A 15-second source-only fingerprint audit now
  schedules reconciliation only when the selected dashboard contents changed,
  while the normal event path remains immediate. Dashboard reads explicitly
  refresh Lovelace storage so the audit cannot compare a stale in-memory cache.
- Await Home Assistant's asynchronous linked Google-user lookup during native
  capability validation so startup, preview, and periodic reconciliation do not
  fail before camera and security-device exposure can be checked.
- Inspect the native Google request-sync result instead of treating a completed
  Home Assistant service call as delivery. HTTP 404, an empty linked-user set,
  timeouts, and non-2xx results now fail closed and report that relinking is
  required when applicable.
- Make an unchanged manual, startup, reload, or source-change reconciliation
  perform native payload validation, Google Request Sync, and a second payload
  validation instead of reporting success after a local-only check.
- Prevent a Google-incompatible controllable or security entity from rolling
  back otherwise valid HomeKit and Matter updates. The effective Google plan
  omits only entities that Home Assistant's native Google classifier rejects,
  keeps observation-only omissions explicit, and publishes an exact owner
  action instead of inventing a switch fallback.
- Report camera and alarm-panel selections for which Matter has no native
  device type while retaining Matterbridge discovery for supported endpoints
  belonging to the same Home Assistant device.
- Filter Entity/Device Registry wakeups to selected source and Apple TV
  provenance changes. Unrelated telemetry and metadata churn no longer causes
  repeated three-target reconciliations; the 15-second source fingerprint and
  five-minute target audit remain as bounded safety nets.
- Recover a stopped HomeKit runtime after global quick reload only when every
  managed Config Entry is loaded and the complete exposure layout still
  exactly matches. Recovery reloads only stopped entries and revalidates the
  full layout without changing filters, ownership, or pairing data.

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

[Unreleased]: https://github.com/jameslu34/ha-platform-sync/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/jameslu34/ha-platform-sync/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.5...v0.7.0
[0.6.5]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.4...v0.6.5
[0.6.4]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/jameslu34/ha-platform-sync/releases/tag/v0.6.0
