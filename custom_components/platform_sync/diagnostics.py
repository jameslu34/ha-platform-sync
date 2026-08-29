"""Privacy-preserving diagnostics for Platform Sync."""

from __future__ import annotations

from typing import Any


def _rule_counts(rules: Any) -> dict[str, dict[str, int]]:
    """Return rule sizes without exposing entity identifiers."""
    return {
        platform.value: {
            "include": len(rule.include),
            "exclude": len(rule.exclude),
        }
        for platform, rule in rules.items()
    }


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """Return reconciliation counts and non-identifying runtime state."""
    runtime = plan.get("runtime", {})
    return {
        "expected": int(plan.get("expected", 0)),
        "actual": int(plan.get("actual", 0)),
        "added": len(plan.get("added", ())),
        "removed": len(plan.get("removed", ())),
        "missing": len(plan.get("missing", ())),
        "extra": len(plan.get("extra", ())),
        "metadata_updates": len(plan.get("metadata_updates", ())),
        "changed": bool(plan.get("changed", False)),
        "runtime": {
            key: value
            for key, value in runtime.items()
            if isinstance(value, (bool, int, float))
            or (
                isinstance(value, str)
                and value
                in {"", "started", "stopped", "loaded", "unloaded", "running"}
            )
        },
    }


async def async_get_config_entry_diagnostics(hass, entry):
    """Return useful diagnostics without hosts, paths, entity IDs, or entry IDs."""
    manager = entry.runtime_data
    config = manager.config
    state = manager.state
    return {
        "config": {
            "enabled": config.enabled,
            "source_kind": config.source_kind.value,
            "source_page_count": len(config.source_pages),
            "source_entity_count": len(config.source_entities),
            "targets": sorted(platform.value for platform in config.targets),
            "google_config_path_configured": bool(config.google_config_path),
            "matter_endpoint_configured": bool(config.matter_host),
            "homekit_source_entry_count": len(config.homekit_source_entry_ids),
            "homekit_managed_entry_count": len(config.homekit_managed_entry_ids),
            "user_rule_counts": _rule_counts(config.user_rules),
            "locked_rule_counts": _rule_counts(config.locked_rules),
            "locked_homekit_apple_tv_exclusion": (
                config.locked_homekit_apple_tv_exclusion
            ),
        },
        "state": {
            "status": state.status,
            "last_reason": state.last_reason,
            "last_run": state.last_run,
            "startup_scan_completed": state.startup_scan_completed,
            "has_source_fingerprint": state.source_fingerprint is not None,
            "plans": {
                platform: _plan_summary(plan)
                for platform, plan in state.plans.items()
            },
            "has_error": state.error is not None,
            "rollback_status": state.rollback_status,
            "rollback_incomplete_target_count": len(
                state.rollback_incomplete_targets
            ),
        },
    }
