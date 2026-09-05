"""Privacy-preserving diagnostics for Platform Sync."""

from __future__ import annotations

from typing import Any


def _safe_error_code(error: str | None) -> str | None:
    """Classify known failures without exposing topology or entity identifiers."""
    if not error:
        return None
    lowered = error.lower()
    markers = (
        ("no linked google home user", "google_not_linked"),
        ("native runtime configuration is unavailable", "google_runtime_api_unavailable"),
        ("native type mapping is unavailable", "google_type_mapping_unavailable"),
        ("native security-device type is missing", "google_security_type_missing"),
        ("native security-device state missing", "google_security_state_missing"),
        ("configured-device state missing", "google_entity_state_missing"),
        ("request sync", "google_request_sync_failed"),
        (
            "managed homekit config entry is not loaded",
            "homekit_entry_not_loaded",
        ),
        (
            "managed homekit runtime is not verifiably running",
            "homekit_runtime_not_running",
        ),
        ("homekit exact readback mismatch", "homekit_readback_mismatch"),
        ("matterbridge", "matterbridge_unavailable"),
        ("homekit", "homekit_unavailable"),
    )
    return next((code for marker, code in markers if marker in lowered), "sync_error")


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
        "not_exposed_platform_unsupported": len(
            plan.get("not_exposed_platform_unsupported", ())
        ),
        "no_native_device_type": len(plan.get("no_native_device_type", ())),
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
            "matter_password_configured": bool(
                getattr(config, "matter_password", "")
            ),
            "homekit_source_entry_count": len(config.homekit_source_entry_ids),
            "homekit_managed_entry_count": len(config.homekit_managed_entry_ids),
            "homekit_main_entry_configured": bool(
                getattr(config, "homekit_main_entry_id", "")
            ),
            "homekit_lifecycle_entry_count": len(
                getattr(config, "homekit_lifecycle_entry_ids", ())
            ),
            "homekit_pending_pairing_count": len(
                getattr(config, "homekit_pending_pairing_entry_ids", ())
            ),
            "homekit_restart_required_entry_count": len(
                getattr(config, "homekit_restart_required_entry_ids", ())
            ),
            "homekit_accessory_config_path_configured": bool(
                getattr(config, "homekit_accessory_config_path", "")
            ),
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
            "error_code": _safe_error_code(state.error),
            "error_stage": getattr(state, "error_stage", None),
            "rollback_status": state.rollback_status,
            "rollback_incomplete_target_count": len(
                state.rollback_incomplete_targets
            ),
            "manual_pairing_required_count": len(
                getattr(state, "manual_pairing", ())
            ),
            "pending_homekit_prune_count": len(
                getattr(state, "pending_homekit_prune", ())
            ),
            "homekit_yaml_backup_count": len(
                getattr(state, "homekit_yaml_backups", ())
            ),
            "homekit_restart_required": bool(
                getattr(state, "homekit_restart_required", False)
            ),
            "controller_readback": {
                "google_homegraph_verified": bool(
                    getattr(state, "google_homegraph_verified", False)
                ),
                "homekit_verified": bool(
                    getattr(state, "homekit_controller_verified", False)
                ),
                "matter_verified": bool(
                    getattr(state, "matter_controller_verified", False)
                ),
            },
            "transaction": {
                "locked": bool(getattr(manager, "_lock", None))
                and manager._lock.locked(),
                "background_reconcile_active": bool(
                    getattr(manager, "_reconcile_active", False)
                ),
                "background_task_active": bool(
                    getattr(manager, "_debounce_task", None)
                    and not manager._debounce_task.done()
                ),
                "direct_call_count": len(
                    getattr(manager, "_direct_tasks", ())
                ),
                "pending_event": getattr(manager, "_pending_reason", None)
                is not None,
            },
        },
    }
