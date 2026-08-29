# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/jameslu34/ha-platform-sync/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/jameslu34/ha-platform-sync/releases/tag/v0.6.0
