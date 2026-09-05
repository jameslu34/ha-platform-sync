# Versioning and release policy

Platform Sync follows these project rules:

1. The version baseline is always the latest version actually published as a
   GitHub Release and Git tag. An uncommitted manifest value, an unreleased
   changelog heading, or an abandoned release candidate is not a baseline.
2. During development, all changes accumulate under `Unreleased`. Do not bump
   the manifest version unless the owner explicitly requests a version update
   or release.
3. When a version update is requested, compare the complete change set from the
   latest published tag to the intended release commit exactly once. Do not add
   `0.0.1`, `0.1`, or another increment separately for every intermediate edit.
4. Choose the next version using semantic impact:
   - patch: backward-compatible fixes and small internal improvements;
   - minor: backward-compatible user-visible capabilities or substantial
     improvements;
   - major: incompatible configuration, behavior, or API changes.
5. After an explicitly requested version update passes release verification,
   publish the matching Git tag and GitHub Release. Versioning and publication
   are separate release steps, but the original version-update request
   authorizes completing both steps without another prompt.
6. Never describe local tests as native Google Home, Apple Home, or Matter
   controller acceptance. Record any unavailable controller verification as
   unverified in the release notes.

The latest local tag at the time this policy was last updated was `v0.7.0`; the
authoritative baseline at release time must still be read back from GitHub.
