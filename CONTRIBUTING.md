# Contributing

Thank you for helping improve Cross-Platform Device Sync.

## Before starting

- Search existing issues and pull requests before opening a new one.
- Use a feature request issue for behavior changes that affect synchronization
  rules or supported platforms.
- Keep changes focused. Avoid unrelated formatting or refactoring in the same
  pull request.
- Never include real credentials, private host names, household entity IDs, or
  unredacted Home Assistant diagnostics.

English is the primary language for repository discussions and code-facing
documentation so the project remains accessible worldwide. Traditional Chinese
documentation and interface text are maintained alongside English; changes to a
user-visible string should update both languages when possible.

## Development setup

1. Fork the repository and create a branch from `main`.
2. Copy or link `custom_components/platform_sync` into a non-production Home
   Assistant test configuration.
3. Make the smallest change that solves the issue.
4. Add or update acceptance coverage.
5. Run all local checks:

   ```bash
   python tests/simulate_acceptance.py
   python tests/simulate_adapter_acceptance.py
   python tests/simulate_config_flow_acceptance.py
   python tests/validate_translations.py
   python -m compileall custom_components/platform_sync tests
   ```

6. Test the configuration flow in Home Assistant when user-visible behavior
   changes.

## Brand assets

`custom_components/platform_sync/brand/icon.svg` is the editable source of
truth for the project icon. Do not edit the PNG files independently. After an
SVG change, export it on a transparent canvas as:

- `icon.png`: 256 × 256 pixels
- `icon@2x.png`: 512 × 512 pixels

Commit the SVG and both generated PNG files together so HACS users receive the
required raster assets while maintainers retain a resolution-independent
source.

## Pull requests

A pull request should:

- Explain the user problem and the chosen behavior.
- Identify any migration, compatibility, safety, or rollback impact.
- Include tests for changed synchronization logic.
- Keep platform writes exact and fail closed when source or readback data is
  incomplete.
- Preserve the rule that the integration manages exposure only and never calls
  entity-control actions.
- Update `CHANGELOG.md` under **Unreleased** for user-visible changes.
- Pass the acceptance-test and Home Assistant hassfest workflows.

## Maintainer releases

After `main` passes all workflows, open **Actions → Release → Run workflow** and
enter a tag such as `v0.6.2`. The tag must exactly match the version in
`custom_components/platform_sync/manifest.json`. The workflow reruns the
acceptance checks, creates the tag, and publishes the GitHub release. Pushing a
matching `v*.*.*` tag remains supported for command-line release workflows.

By submitting a contribution, you confirm that you have the right to submit it
and agree that it is licensed under the project's
[PolyForm Noncommercial License 1.0.0](LICENSE). This permits noncommercial use,
modification, and redistribution, but does not grant commercial-use rights.
