## Summary

Describe the user problem and the change.

## Safety and compatibility

- [ ] The integration still manages platform exposure only and does not control entity state.
- [ ] Source failures and incomplete readback fail closed.
- [ ] Migration and rollback impact has been considered.
- [ ] No credentials, private host names, household entity IDs, or diagnostics are included.

## Validation

- [ ] `python tests/simulate_acceptance.py`
- [ ] `python tests/simulate_adapter_acceptance.py`
- [ ] `python tests/simulate_config_flow_acceptance.py`
- [ ] `python tests/validate_translations.py`
- [ ] `python -m compileall custom_components/platform_sync tests`
- [ ] User-facing English and Traditional Chinese text is updated when applicable.
- [ ] `CHANGELOG.md` is updated for a user-visible change.
