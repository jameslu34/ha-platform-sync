"""Event-driven synchronization manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.lovelace.const import EVENT_LOVELACE_UPDATED
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .config import SyncConfig
from .const import (
    CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
    CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS,
    CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS,
    DOMAIN,
    EVENT_SYNC_COMPLETED,
    EVENT_SYNC_FAILED,
    INTERNAL_DEBOUNCE_SECONDS,
    INTERNAL_HEALTH_AUDIT_SECONDS,
    INTERNAL_LIFECYCLE_CONFIRM_SECONDS,
    INTERNAL_POLL_SECONDS,
    INTERNAL_RETRY_DELAYS_SECONDS,
    INTERNAL_SOURCE_AUDIT_SECONDS,
    SourceKind,
    TargetPlatform,
)
from .homekit_lifecycle import (
    HomeKitLifecycleCancelled,
    HomeKitLifecycleError,
    async_remove_homekit_accessory_candidates,
    plan_homekit_accessory_prunes,
)
from .homekit_pairing import (
    HomeKitAccessoryCreateCancelled,
    HomeKitAccessoryCreateError,
    ManualPairingRequirement,
    async_create_homekit_accessory,
    homekit_entry_entities,
    homekit_entry_is_paired,
    pairing_requirements_markdown,
)
from .models import SourceSnapshot, TargetPlan, evaluate_target
from .notifications import (
    async_create_native_notification,
    async_dismiss_native_notification,
)
from .sources import async_find_apple_tv_entities, async_read_source
from .targets import (
    GOOGLE_SYNC_TIMEOUT,
    HOMEKIT_RELOAD_TIMEOUT,
    MATTER_BACKUP_TIMEOUT,
    MATTER_CONFIG_PERSIST_TIMEOUT,
    MATTER_REQUEST_TIMEOUT,
    MATTER_RUNTIME_TIMEOUT,
    HomeKitRuntimeUnavailableError,
    MatterbridgeRuntimeError,
    async_apply_plan,
    async_google_room_updates,
    async_matter_manual_pairing_entities,
    _google_native_sync_payload_snapshot,
    _request_google_sync,
    google_native_unrepresentable_entities,
    homekit_new_accessory_mode_entities,
    homekit_managed_main_entry_id,
    matter_native_unrepresentable_entities,
    async_prepare_target,
    async_read_target,
    async_recover_homekit_runtime,
    async_recover_matter_runtime,
    async_restore_target,
    async_validate_target,
)

_LOGGER = logging.getLogger(__name__)
ROLLBACK_SAFETY_MARGIN_SECONDS = 15.0
STOP_DRAIN_SAFETY_MARGIN_SECONDS = 5.0
# A cancelled all-target transaction may have to restore Google, HomeKit and
# Matter in reverse order. Google restoration performs a native payload check
# before and after its bounded Request Sync. Matter restoration can consume a configuration
# persistence readback, one full process restart/generation wait, and exact
# validation requests. Seven bounded management requests cover the generation
# capability preflight, pre-restart generation read, save/restart sends, and
# final three-part snapshot. Keep one explicit budget for the complete rollback
# instead of letting HA unload return while recovery is still unverified.
ROLLBACK_TIMEOUT_SECONDS = (
    3 * GOOGLE_SYNC_TIMEOUT
    + HOMEKIT_RELOAD_TIMEOUT
    + MATTER_CONFIG_PERSIST_TIMEOUT
    + MATTER_RUNTIME_TIMEOUT
    + 7 * MATTER_REQUEST_TIMEOUT
    + ROLLBACK_SAFETY_MARGIN_SECONDS
)
STOP_DRAIN_TIMEOUT_SECONDS = (
    max(ROLLBACK_TIMEOUT_SECONDS, MATTER_BACKUP_TIMEOUT)
    + STOP_DRAIN_SAFETY_MARGIN_SECONDS
)
MATTER_RECOVERY_COOLDOWN_SECONDS = 300.0
MATTER_RECOVERY_STARTUP_GRACE_SECONDS = 180.0
MATTER_RECOVERY_MIN_FAILURE_SECONDS = 30.0
MATTER_RECOVERY_MIN_FAILURE_COUNT = 2
MATTER_RECOVERY_GUARDS_KEY = "matter_recovery_guards"


@dataclass(slots=True)
class SyncState:
    """Diagnostics-safe coordinator state."""

    status: str = "disabled"
    last_reason: str | None = None
    last_run: str | None = None
    startup_scan_completed: str | None = None
    source_fingerprint: str | None = None
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None
    error_stage: str | None = None
    rollback_status: str = "not_needed"
    rollback_incomplete_targets: list[str] = field(default_factory=list)
    manual_pairing: list[dict[str, str]] = field(default_factory=list)
    pending_homekit_prune: list[str] = field(default_factory=list)
    homekit_yaml_backups: list[str] = field(default_factory=list)
    homekit_restart_required: bool = False
    homekit_controller_verified: bool = False
    google_homegraph_verified: bool = False
    matter_controller_verified: bool = False


@dataclass(slots=True)
class MatterRecoveryGuard:
    """Endpoint recovery state shared across Config Entry reloads."""

    attempted_for_episode: bool = False
    last_attempt: float | None = None
    active_token: object | None = None
    process_restart_attempted: bool = False


def _matter_recovery_guard(
    hass: HomeAssistant, config: SyncConfig
) -> MatterRecoveryGuard:
    """Return the endpoint guard retained in hass.data across entry reloads."""
    data = getattr(hass, "data", None)
    if not isinstance(data, dict):
        return MatterRecoveryGuard()
    domain_data = data.setdefault(DOMAIN, {})
    if not isinstance(domain_data, dict):
        return MatterRecoveryGuard()
    guards = domain_data.setdefault(MATTER_RECOVERY_GUARDS_KEY, {})
    if not isinstance(guards, dict):
        return MatterRecoveryGuard()
    endpoint = (
        str(getattr(config, "matter_host", "")).strip().casefold(),
        str(getattr(config, "matter_port", "")),
    )
    guard = guards.get(endpoint)
    if not isinstance(guard, MatterRecoveryGuard):
        guard = MatterRecoveryGuard()
        guards[endpoint] = guard
    return guard


class PlatformSyncManager:
    """Serialize, debounce and reconcile configured targets."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: SyncConfig,
        entry: config_entries.ConfigEntry | None = None,
    ) -> None:
        self.hass = hass
        self.config = config
        self._entry = entry
        self.state = SyncState(
            status="idle" if config.enabled else "disabled",
            homekit_restart_required=bool(
                getattr(config, "homekit_restart_required_entry_ids", ())
            ),
        )
        self._lock = asyncio.Lock()
        self._debounce_task: asyncio.Task[None] | None = None
        self._reconcile_active = False
        self._retry_backoff_active = False
        self._pending_reason: str | None = None
        self._startup_scan_pending = False
        self._startup_scan_required = False
        self._stopping = False
        self._unsubscribers: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []
        self._direct_tasks: set[asyncio.Task[Any]] = set()
        self._fallback_polling_started = False
        self._source_audit_started = False
        self._health_audit_started = False
        self._active_attempted_targets: set[TargetPlatform] = set()
        self._matter_recovery_guard = _matter_recovery_guard(hass, config)
        self._matter_transaction_restart_reserved = False
        self._started_at: float | None = None
        self._matter_failure_count = 0
        self._matter_failure_first_at: float | None = None
        self._google_noop_request_sync_fingerprint: str | None = None
        self._google_noop_request_sync_result: dict[str, Any] = {}
        self._homekit_prune_signature: tuple[str, tuple[tuple[Any, ...], ...]] | None = None
        self._homekit_prune_first_seen: float | None = None
        self._homekit_prune_unsubscribe: Callable[[], None] | None = None
        self._registry_watch_entity_ids: frozenset[str] = frozenset()
        self._registry_watch_device_ids: frozenset[str] = frozenset()

    def _refresh_registry_watch_scope(
        self,
        source_entities: frozenset[str],
        provenance_entities: frozenset[str] = frozenset(),
    ) -> None:
        """Cache only registry objects that can affect the current plan."""
        watched_entities = source_entities | provenance_entities
        watched_devices: set[str] = set()
        registry = er.async_get(self.hass)
        registry_get = getattr(registry, "async_get", None)
        registry_entities = getattr(registry, "entities", {})
        # Device-registry provenance is used only by the mandatory Apple TV
        # exclusion. Ordinary source-device telemetry and metadata updates do
        # not change entity selection or accessory mode and must not trigger a
        # three-target reconciliation.
        for entity_id in provenance_entities:
            entry = (
                registry_get(entity_id)
                if callable(registry_get)
                else registry_entities.get(entity_id)
            )
            device_id = getattr(entry, "device_id", None)
            if isinstance(device_id, str) and device_id:
                watched_devices.add(device_id)
        self._registry_watch_entity_ids = watched_entities
        self._registry_watch_device_ids = frozenset(watched_devices)

    def _is_zh_hant(self) -> bool:
        """Return whether system UI text should use Traditional Chinese."""
        language = (
            str(getattr(self.hass.config, "language", "en"))
            .casefold()
            .replace("_", "-")
        )
        return language in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"} or language.startswith(
            "zh-hant-"
        )

    def _update_homekit_tracking(
        self,
        *,
        add_entry_ids: set[str] | frozenset[str] = frozenset(),
        remove_entry_ids: set[str] | frozenset[str] = frozenset(),
        add_pending_pairing_ids: set[str] | frozenset[str] = frozenset(),
        remove_pending_pairing_ids: set[str] | frozenset[str] = frozenset(),
        add_restart_required_ids: set[str] | frozenset[str] = frozenset(),
        remove_restart_required_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        """Persist explicit ownership and pairing state after exact readback."""
        if self._entry is None:
            if (
                add_entry_ids
                or remove_entry_ids
                or add_pending_pairing_ids
                or remove_pending_pairing_ids
                or add_restart_required_ids
                or remove_restart_required_ids
            ):
                raise RuntimeError(
                    "HomeKit lifecycle changes require a Platform Sync Config Entry"
                )
            return
        managed = (
            set(getattr(self.config, "homekit_managed_entry_ids", ()))
            | set(add_entry_ids)
        ) - set(remove_entry_ids)
        lifecycle = (
            set(getattr(self.config, "homekit_lifecycle_entry_ids", ()))
            | set(add_entry_ids)
        ) - set(remove_entry_ids)
        pending = (
            set(getattr(self.config, "homekit_pending_pairing_entry_ids", ()))
            | set(add_pending_pairing_ids)
        ) - set(remove_pending_pairing_ids) - set(remove_entry_ids)
        pending &= lifecycle
        restart_required = (
            set(
                getattr(
                    self.config,
                    "homekit_restart_required_entry_ids",
                    (),
                )
            )
            | set(add_restart_required_ids)
        ) - set(remove_restart_required_ids)
        options = dict(self._entry.options or {})
        options[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = sorted(managed)
        options[CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS] = sorted(lifecycle)
        options[CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS] = sorted(pending)
        options[CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS] = sorted(
            restart_required
        )
        if options != dict(self._entry.options or {}):
            self.hass.config_entries.async_update_entry(
                self._entry, options=options
            )
        self.config = SyncConfig.from_entry(self._entry.data, options)
        self.state.homekit_restart_required = bool(restart_required)

    def _drop_missing_owned_homekit_entries(
        self, candidate_entry_ids: set[str] | frozenset[str]
    ) -> None:
        """Resolve restart-gated uncertain removals from a newly loaded Core."""
        lifecycle = set(
            getattr(self.config, "homekit_lifecycle_entry_ids", ())
        ) & set(candidate_entry_ids)
        if not lifecycle:
            return
        live = {
            entry.entry_id
            for entry in self.hass.config_entries.async_entries("homekit")
        }
        missing = lifecycle - live
        if missing:
            self._update_homekit_tracking(remove_entry_ids=missing)

    def _homekit_prune_candidates(
        self, logical_desired: frozenset[str]
    ) -> tuple[Any, ...]:
        """Plan removals using only explicitly owned lifecycle entries."""
        lifecycle = tuple(
            getattr(self.config, "homekit_lifecycle_entry_ids", ())
        )
        if not lifecycle:
            return ()
        # The main Bridge identity is durable.  Never infer it again from its
        # current entity count: after a legitimate 2 -> 1 shrink, a separate
        # singleton Bridge side entry would otherwise make the next prune
        # pass ambiguous (or, worse, target the wrong entry).
        main_entry_id = homekit_managed_main_entry_id(self.hass, self.config)
        yaml_path = str(
            getattr(self.config, "homekit_accessory_config_path", "") or ""
        ).strip()
        yaml_paths = (
            {entry_id: yaml_path for entry_id in lifecycle}
            if yaml_path
            else {}
        )
        return plan_homekit_accessory_prunes(
            self.hass.config_entries.async_entries("homekit"),
            managed_entry_ids=self.config.homekit_managed_entry_ids,
            main_entry_id=main_entry_id,
            homekit_source_entry_ids=self.config.homekit_source_entry_ids,
            owned_entry_ids=lifecycle,
            prunable_entry_ids=lifecycle,
            logical_desired=logical_desired,
            import_yaml_paths=yaml_paths,
        )

    @callback
    def _handle_homekit_prune_confirmation(self, now: Any) -> None:
        del now
        self._homekit_prune_unsubscribe = None
        self.schedule("homekit_prune_confirmation")

    def _clear_homekit_prune_confirmation(self) -> None:
        self._homekit_prune_signature = None
        self._homekit_prune_first_seen = None
        self.state.pending_homekit_prune = []
        if self._homekit_prune_unsubscribe is not None:
            self._homekit_prune_unsubscribe()
            self._homekit_prune_unsubscribe = None

    def _homekit_prune_confirmed(
        self,
        source_fingerprint: str,
        candidates: tuple[Any, ...],
        *,
        apply: bool,
    ) -> bool:
        """Require two identical source observations at least 15 seconds apart."""
        candidate_identity = tuple(
            sorted(
                (
                    candidate.entry_id,
                    candidate.entity_id,
                    bool(candidate.imported),
                    candidate.name,
                    int(candidate.port),
                    str(getattr(candidate, "mode", None) or ""),
                    str(candidate.yaml_relative_path or ""),
                )
                for candidate in candidates
            )
        )
        self.state.pending_homekit_prune = sorted(
            candidate.entity_id for candidate in candidates
        )
        if not candidate_identity or not apply:
            if not candidate_identity:
                self._clear_homekit_prune_confirmation()
            return False
        signature = (source_fingerprint, candidate_identity)
        now = asyncio.get_running_loop().time()
        if (
            signature == self._homekit_prune_signature
            and self._homekit_prune_first_seen is not None
            and now - self._homekit_prune_first_seen
            >= INTERNAL_LIFECYCLE_CONFIRM_SECONDS
        ):
            return True
        if signature != self._homekit_prune_signature:
            self._homekit_prune_signature = signature
            self._homekit_prune_first_seen = now
        if self._homekit_prune_unsubscribe is not None:
            self._homekit_prune_unsubscribe()
        self._homekit_prune_unsubscribe = async_call_later(
            self.hass,
            INTERNAL_LIFECYCLE_CONFIRM_SECONDS,
            self._handle_homekit_prune_confirmation,
        )
        return False

    def _pairing_requirements(
        self, desired: frozenset[str]
    ) -> list[ManualPairingRequirement]:
        """Read all selected HomeKit pairing needs without controller IDs."""
        pending = set(
            getattr(self.config, "homekit_pending_pairing_entry_ids", ())
        )
        managed = set(getattr(self.config, "homekit_managed_entry_ids", ()))
        tracked = pending | managed
        if not tracked:
            return []
        main_entry_id = homekit_managed_main_entry_id(self.hass, self.config)
        completed: set[str] = set()
        requirements: list[ManualPairingRequirement] = []
        for entry_id in sorted(tracked):
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                if entry_id in pending:
                    completed.add(entry_id)
                continue
            entities = homekit_entry_entities(entry)
            # Do not ask the owner to pair an entry that this exact plan is
            # removing (for example an adopted stale camera accessory).
            if entities and not (entities & desired):
                continue
            paired = homekit_entry_is_paired(entry)
            if paired is True:
                if entry_id in pending:
                    completed.add(entry_id)
                continue
            if entry_id == main_entry_id:
                requirements.append(
                    ManualPairingRequirement(
                        platform="HomeKit",
                        entity_id=f"config_entry:{entry_id}",
                        device_name=str(
                            getattr(entry, "title", None) or "HomeKit Bridge"
                        ),
                        action=(
                            (
                                "開啟 Home Assistant 的 HomeKit 配對通知，再到 Apple Home 加入這個 Bridge。"
                                if paired is False
                                else "先在 Apple Home 確認這個 Bridge 是否已存在；只有尚未配對時，才使用 Home Assistant 的 HomeKit 配對通知加入。"
                            )
                            if self._is_zh_hant()
                            else (
                                "Open the Home Assistant HomeKit notification and add this Bridge in Apple Home."
                                if paired is False
                                else "Check whether this Bridge already exists in Apple Home; use the Home Assistant HomeKit notification to add it only when it is not paired."
                            )
                        ),
                        entry_id=entry_id,
                    )
                )
                continue
            if len(entities) != 1:
                if entry_id not in pending and paired is not False and not entities:
                    # A broad/malformed entry is rejected by target validation;
                    # avoid turning that configuration error into a pairing claim.
                    continue
                requirements.append(
                    ManualPairingRequirement(
                        platform="HomeKit",
                        entity_id=f"config_entry:{entry_id}",
                        device_name=str(
                            getattr(entry, "title", None) or "HomeKit accessory"
                        ),
                        action=(
                            "開啟 Home Assistant 的 HomeKit 配對通知，再到 Apple Home 加入這個 Bridge；若內容不是預期裝置，請先回到外掛設定修正選取項目。"
                            if self._is_zh_hant()
                            else "Open the Home Assistant HomeKit notification and add this Bridge in Apple Home. If it contains unexpected devices, correct the integration selection first."
                        ),
                        entry_id=entry_id,
                    )
                )
                continue
            entity_id = next(iter(entities))
            state = self.hass.states.get(entity_id)
            name = (
                state.attributes.get("friendly_name")
                if state is not None
                else None
            )
            requirements.append(
                ManualPairingRequirement(
                    platform="HomeKit",
                    entity_id=entity_id,
                    device_name=str(name or entity_id),
                    action=(
                        (
                            "開啟 Home Assistant 的 HomeKit 配對通知，再到 Apple Home 加入 accessory。"
                            if paired is False
                            else "先在 Apple Home 確認 accessory 是否已存在；只有尚未配對時才加入。"
                        )
                        if self._is_zh_hant()
                        else (
                            "Open the Home Assistant HomeKit notification and pair this accessory in Apple Home."
                            if paired is False
                            else "Check whether the accessory already exists in Apple Home; add it only when it is not paired."
                        )
                    ),
                    entry_id=entry_id,
                )
            )
        if completed:
            self._update_homekit_tracking(
                remove_pending_pairing_ids=completed
            )
        return requirements

    def _publish_pairing_requirements(
        self, requirements: list[ManualPairingRequirement]
    ) -> None:
        """Maintain one aggregate, HA-native setup-completion notification."""
        notification_id = (
            f"{DOMAIN}_{getattr(self._entry, 'entry_id', 'runtime')}_manual_pairing"
        )
        if not requirements:
            async_dismiss_native_notification(self.hass, notification_id)
            return
        async_create_native_notification(
            self.hass,
            pairing_requirements_markdown(
                requirements, zh_hant=self._is_zh_hant()
            ),
            title=(
                "裝置平台同步：需要額外配對或確認"
                if self._is_zh_hant()
                else "Platform Sync: additional pairing or verification required"
            ),
            notification_id=notification_id,
        )

    def _publish_homekit_restart_requirement(self, required: bool) -> None:
        """Keep a native persistent warning until HA Core restarts."""
        notification_id = (
            f"{DOMAIN}_{getattr(self._entry, 'entry_id', 'runtime')}_homekit_restart"
        )
        if not required:
            async_dismiss_native_notification(self.hass, notification_id)
            return
        async_create_native_notification(
            self.hass,
            (
                "HomeKit accessory 的移除需要重新啟動 Home Assistant 才能確認設定與舊服務都已完全收斂；在重新啟動並重新驗證前，此外掛不會宣稱同步完成。"
                if self._is_zh_hant()
                else "A HomeKit accessory removal requires a Home Assistant restart to prove that its configuration and old service have fully converged. Synchronization will not be reported complete until restart and revalidation."
            ),
            title=(
                "裝置平台同步：需要重新啟動 Home Assistant"
                if self._is_zh_hant()
                else "Platform Sync: Home Assistant restart required"
            ),
            notification_id=notification_id,
        )

    async def async_start(self) -> None:
        """Start only when the master switch is enabled."""
        self._stopping = False
        restart_required_ids = set(
            getattr(
                self.config,
                "homekit_restart_required_entry_ids",
                (),
            )
        )
        if (
            restart_required_ids
            and getattr(self.hass, "state", None) is not CoreState.running
        ):
            # This integration is being set up as part of a new Core process;
            # Config Entries have now been reloaded from durable storage. Only
            # at this boundary may absence resolve an uncertain removal; a
            # same-process in-memory absence is never proof of persistence.
            self._drop_missing_owned_homekit_entries(restart_required_ids)
            self._update_homekit_tracking(
                remove_restart_required_ids=restart_required_ids
            )
            restart_required_ids.clear()
        self._publish_homekit_restart_requirement(bool(restart_required_ids))
        if not self.config.enabled:
            self._publish_pairing_requirements([])
            _LOGGER.info("Platform Sync is disabled; no listeners or polling started")
            return
        # ``homeassistant.reload_all`` reloads YAML-backed integrations but does
        # not reload this Config Entry. Treat the call itself as a mandatory
        # reconciliation boundary; the normal debounce lets the YAML reloads
        # settle before Platform Sync reads every source and target again.
        self._unsubscribers.append(
            self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._handle_service_call)
        )
        entity_registry_watched = False
        if self.config.source_kind is SourceKind.DASHBOARD:
            self._unsubscribers.append(
                self.hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._handle_event)
            )
            self._unsubscribers.append(
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_event
                )
            )
            entity_registry_watched = True
        elif self.config.source_kind in {SourceKind.GOOGLE, SourceKind.MATTER}:
            self._start_fallback_polling()

        homekit_target_relevant = (
            TargetPlatform.HOMEKIT
            in getattr(self.config, "targets", frozenset())
        )
        homekit_relevant = (
            self.config.source_kind is SourceKind.HOMEKIT
            or homekit_target_relevant
        )
        if homekit_relevant:
            signal = getattr(config_entries, "SIGNAL_CONFIG_ENTRY_CHANGED", None)
            if signal is None:
                _LOGGER.warning(
                    "HomeKit config-entry events are unavailable; using fallback polling"
                )
                self._start_fallback_polling()
            else:
                try:
                    unsubscribe = async_dispatcher_connect(
                        self.hass, signal, self._handle_homekit_config_entry_change
                    )
                except Exception:
                    _LOGGER.warning(
                        "HomeKit config-entry event registration failed; using fallback polling",
                        exc_info=True,
                    )
                    self._start_fallback_polling()
                else:
                    self._unsubscribers.append(unsubscribe)

        if homekit_target_relevant:
            # Device/Entity Registry provenance participates in the mandatory
            # Apple TV exclusion and in HomeKit accessory classification.
            # Registry mutations therefore need the same fast convergence as
            # HomeKit Config Entry changes.
            if not entity_registry_watched:
                self._unsubscribers.append(
                    self.hass.bus.async_listen(
                        er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_event
                    )
                )
            self._unsubscribers.append(
                self.hass.bus.async_listen(
                    dr.EVENT_DEVICE_REGISTRY_UPDATED, self._handle_event
                )
            )

        # Some storage-dashboard editor paths do not emit lovelace_updated.
        # Retain push events for the fast path and use a cheap source-only
        # fingerprint audit as the bounded fallback. Keep this local-only audit
        # independent from any slower full-platform compatibility poll.
        if self.config.source_kind is SourceKind.DASHBOARD:
            self._start_source_audit()
        elif (
            self.config.source_kind is SourceKind.HOMEKIT
            and not self._fallback_polling_started
        ):
            # Config Entry dispatcher events are the low-latency path. A cheap
            # source-only audit closes missed-event races without paying for a
            # full three-target reconciliation on every interval.
            self._start_source_audit(INTERNAL_POLL_SECONDS)

        # Event-driven configurations retain a slow safety audit for target
        # drift. A fallback poll already performs the same full reconciliation,
        # so do not register a second timer for Google, Matter, or HomeKit
        # compatibility fallback paths.
        if not self._fallback_polling_started:
            self._start_health_audit()

        if self.hass.state is CoreState.running:
            self._started_at = asyncio.get_running_loop().time()
            self.schedule("startup_scan")
        else:
            startup_unsubscribe: Callable[[], None]

            @callback
            def handle_started(event: Any) -> None:
                # async_listen_once has already removed itself from HA's event
                # bus before invoking us.  Drop the stale unsubscribe handle so
                # a later config-entry reload does not try to remove it twice.
                if startup_unsubscribe in self._unsubscribers:
                    self._unsubscribers.remove(startup_unsubscribe)
                self._started_at = asyncio.get_running_loop().time()
                self.schedule("startup_scan")

            startup_unsubscribe = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, handle_started
            )
            self._unsubscribers.append(startup_unsubscribe)

    async def async_stop(self) -> bool:
        """Cancel background work safely and drain direct transactions."""
        self._stopping = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._fallback_polling_started = False
        self._source_audit_started = False
        self._health_audit_started = False
        self._pending_reason = None
        self._startup_scan_pending = False
        self._startup_scan_required = False
        if self._homekit_prune_unsubscribe is not None:
            self._homekit_prune_unsubscribe()
            self._homekit_prune_unsubscribe = None
        task = self._debounce_task
        current_task = asyncio.current_task()
        if task is current_task:
            self.state.status = "error"
            self.state.error = (
                "Synchronization cannot unload from its active background task"
            )
            _LOGGER.error(self.state.error)
            return False
        direct_tasks = [
            active
            for active in self._direct_tasks
            if active is not current_task and not active.done()
        ]
        wait_tasks: list[asyncio.Task[Any]] = []
        if task and not task.done():
            # Cancellation lands inside async_reconcile, which reverses every
            # attempted target before propagating it.
            task.cancel()
            wait_tasks.append(task)
        for active in direct_tasks:
            active.cancel()
            wait_tasks.append(active)

        # One absolute deadline covers background work, direct service callers,
        # every rollback, and the final transaction-lock drain. asyncio.wait
        # observes already-cancelled tasks without issuing a second cancellation
        # that could interrupt their rollback.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STOP_DRAIN_TIMEOUT_SECONDS
        pending: set[asyncio.Task[Any]] = set()
        if wait_tasks:
            wait_futures = {
                active
                if isinstance(active, asyncio.Future)
                else asyncio.ensure_future(active)
                for active in wait_tasks
            }
            _, pending = await asyncio.wait(
                wait_futures, timeout=max(0.0, deadline - loop.time())
            )
        lock_drained = False
        remaining = max(0.0, deadline - loop.time())
        if not pending and remaining:
            try:
                async with asyncio.timeout(remaining):
                    async with self._lock:
                        lock_drained = True
            except TimeoutError:
                pass
        if pending or not lock_drained:
            self.state.status = "error"
            self.state.error = (
                "Synchronization stop deadline exceeded; rollback completion is unverified"
            )
            if self._active_attempted_targets:
                self.state.rollback_status = "incomplete"
                self.state.rollback_incomplete_targets = sorted(
                    platform.value for platform in self._active_attempted_targets
                )
            _LOGGER.error(self.state.error)
        if self._debounce_task is task and (task is None or task.done()):
            self._debounce_task = None
        return not pending and lock_drained

    def _start_fallback_polling(self) -> None:
        """Poll only when the source has no reliable push event."""
        from datetime import timedelta

        if self._fallback_polling_started:
            return
        self._fallback_polling_started = True
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._handle_poll,
                timedelta(seconds=INTERNAL_POLL_SECONDS),
            )
        )

    def _start_health_audit(self) -> None:
        """Periodically detect target drift even when the source is unchanged."""
        from datetime import timedelta

        if self._health_audit_started:
            return
        self._health_audit_started = True
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._handle_health_audit,
                timedelta(seconds=INTERNAL_HEALTH_AUDIT_SECONDS),
            )
        )

    def _start_source_audit(
        self, interval_seconds: int = INTERNAL_SOURCE_AUDIT_SECONDS
    ) -> None:
        """Detect missed local-source events without polling every target."""
        from datetime import timedelta

        if self._source_audit_started:
            return
        self._source_audit_started = True
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._handle_source_audit,
                timedelta(seconds=interval_seconds),
            )
        )

    @callback
    def _handle_service_call(self, event: Any) -> None:
        """Synchronize after Home Assistant's global quick YAML reload."""
        data = getattr(event, "data", None)
        if not isinstance(data, Mapping):
            return
        if data.get("domain") != "homeassistant" or data.get("service") != "reload_all":
            return
        self.schedule("homeassistant_reload_all")

    @callback
    def _handle_event(self, event: Any) -> None:
        event_type = getattr(event, "event_type", "event")
        if event_type == EVENT_LOVELACE_UPDATED:
            event_data = getattr(event, "data", None)
            event_dashboard = (
                event_data.get("url_path")
                if isinstance(event_data, Mapping)
                else None
            ) or "lovelace"
            selected_dashboards = {
                dashboard
                for dashboard, _view in getattr(self.config, "source_pages", ())
            }
            if selected_dashboards and event_dashboard not in selected_dashboards:
                return
        elif event_type == er.EVENT_ENTITY_REGISTRY_UPDATED:
            event_data = getattr(event, "data", None)
            entity_id = (
                event_data.get("entity_id")
                if isinstance(event_data, Mapping)
                else None
            )
            if (
                self._registry_watch_entity_ids
                and isinstance(entity_id, str)
                and entity_id not in self._registry_watch_entity_ids
            ):
                return
        elif event_type == dr.EVENT_DEVICE_REGISTRY_UPDATED:
            event_data = getattr(event, "data", None)
            device_id = (
                event_data.get("device_id")
                if isinstance(event_data, Mapping)
                else None
            )
            action = (
                str(event_data.get("action", "")).casefold()
                if isinstance(event_data, Mapping)
                else ""
            )
            changes = (
                event_data.get("changes", {})
                if isinstance(event_data, Mapping)
                else {}
            )
            apple_tv_provenance_change = action in {"create", "remove"} or (
                isinstance(changes, Mapping) and "config_entries" in changes
            )
            if (
                self._registry_watch_entity_ids
                and isinstance(device_id, str)
                and device_id not in self._registry_watch_device_ids
                and not apple_tv_provenance_change
            ):
                return
        self.schedule(event_type)

    @callback
    def _handle_poll(self, now: Any) -> None:
        self.schedule("source_poll")

    @callback
    def _handle_health_audit(self, now: Any) -> None:
        self.schedule("target_health_audit")

    async def _handle_source_audit(self, now: Any) -> None:
        """Schedule reconciliation only when the dashboard fingerprint changed."""
        del now
        if not self.config.enabled or self._stopping:
            return
        try:
            source = await async_read_source(self.hass, self.config)
        except Exception:
            # Let the normal bounded retry path record and recover the failure.
            self.schedule("source_revision_audit_error")
            return
        if source.fingerprint != self.state.source_fingerprint:
            self.schedule("source_revision_audit")

    def _clear_matter_recovery_episode(self) -> None:
        """End one failure episode while retaining its cooldown timestamp."""
        guard = self._matter_recovery_guard
        guard.attempted_for_episode = False
        guard.active_token = None
        guard.process_restart_attempted = False
        self._matter_failure_count = 0
        self._matter_failure_first_at = None

    def _reserve_matter_recovery_episode(self) -> object | None:
        """Reserve one complete recovery flow for the current failure episode."""
        guard = self._matter_recovery_guard
        if guard.attempted_for_episode:
            return None
        now = asyncio.get_running_loop().time()
        if (
            guard.last_attempt is not None
            and now - guard.last_attempt < MATTER_RECOVERY_COOLDOWN_SECONDS
        ):
            return None
        token = object()
        guard.attempted_for_episode = True
        guard.last_attempt = now
        guard.active_token = token
        guard.process_restart_attempted = False
        return token

    def _before_matter_process_restart(self, token: object | None = None) -> bool:
        """Authorize and record one process restart before the command is sent."""
        if not self.config.enabled or self._stopping:
            return False
        if token is None and self._matter_transaction_restart_reserved:
            # A removal is a normal serialized reconciliation transaction, not
            # a runtime-recovery episode. Consume its pre-write reservation
            # without touching the five-minute recovery cooldown.
            self._matter_transaction_restart_reserved = False
            return True
        guard = self._matter_recovery_guard
        now = asyncio.get_running_loop().time()
        if token is not None:
            if not guard.attempted_for_episode or guard.active_token is not token:
                return False
        else:
            if guard.attempted_for_episode or (
                guard.last_attempt is not None
                and now - guard.last_attempt < MATTER_RECOVERY_COOLDOWN_SECONDS
            ):
                return False
            guard.attempted_for_episode = True
        guard.active_token = None
        guard.last_attempt = now
        guard.process_restart_attempted = True
        return True

    def _reserve_matter_transaction_restart(self) -> bool:
        """Reserve one normal Matter removal restart before any config write."""
        if (
            not self.config.enabled
            or self._stopping
            or self._matter_transaction_restart_reserved
        ):
            return False
        self._matter_transaction_restart_reserved = True
        return True

    async def _async_attempt_matter_recovery(
        self, error: MatterbridgeRuntimeError, *, background: bool
    ) -> dict[str, Any] | None:
        """Run at most one guarded runtime recovery per failure episode."""
        if (
            not self.config.enabled
            or self._stopping
            or not background
            or not error.recoverable
        ):
            return None
        now = asyncio.get_running_loop().time()
        self._matter_failure_count += 1
        if self._matter_failure_first_at is None:
            self._matter_failure_first_at = now
        if self._started_at is None or (
            now - self._started_at < MATTER_RECOVERY_STARTUP_GRACE_SECONDS
            or self._matter_failure_count < MATTER_RECOVERY_MIN_FAILURE_COUNT
            or now - self._matter_failure_first_at
            < MATTER_RECOVERY_MIN_FAILURE_SECONDS
        ):
            _LOGGER.debug(
                "Matterbridge is inside its startup/failure observation window; retrying without restart"
            )
            return None
        recovery_token = self._reserve_matter_recovery_episode()
        if recovery_token is None:
            return None
        _LOGGER.warning(
            "Attempting one guarded Matterbridge runtime recovery (%s)",
            error.reason,
        )
        runtime = await async_recover_matter_runtime(
            self.config,
            error.expected,
            before_matter_process_restart=lambda: self._before_matter_process_restart(
                recovery_token
            ),
        )
        self._clear_matter_recovery_episode()
        return runtime

    async def _async_read_source_with_recovery(
        self, *, background: bool
    ) -> SourceSnapshot:
        try:
            source = await async_read_source(self.hass, self.config)
        except MatterbridgeRuntimeError as error:
            runtime = await self._async_attempt_matter_recovery(
                error, background=background
            )
            if runtime is None:
                raise
            source = await async_read_source(self.hass, self.config)
        if getattr(self.config, "source_kind", None) is SourceKind.MATTER:
            self._clear_matter_recovery_episode()
        return source

    async def _async_validate_target_with_recovery(
        self,
        platform: TargetPlatform,
        expected: frozenset[str],
        *,
        background: bool,
        allowed_nonrunning_homekit_entry_ids: frozenset[str] = frozenset(),
        allowed_google_unrepresentable_entities: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        try:
            if (
                allowed_nonrunning_homekit_entry_ids
                or allowed_google_unrepresentable_entities
            ):
                validation_kwargs: dict[str, frozenset[str]] = {}
                if allowed_nonrunning_homekit_entry_ids:
                    validation_kwargs[
                        "allowed_nonrunning_homekit_entry_ids"
                    ] = allowed_nonrunning_homekit_entry_ids
                if allowed_google_unrepresentable_entities:
                    validation_kwargs[
                        "allowed_google_unrepresentable_entities"
                    ] = allowed_google_unrepresentable_entities
                runtime = await async_validate_target(
                    self.hass,
                    self.config,
                    platform,
                    expected,
                    **validation_kwargs,
                )
            else:
                runtime = await async_validate_target(
                    self.hass, self.config, platform, expected
                )
        except HomeKitRuntimeUnavailableError:
            if platform is not TargetPlatform.HOMEKIT or not background:
                raise
            runtime = await async_recover_homekit_runtime(
                self.hass, self.config, expected
            )
        except MatterbridgeRuntimeError as error:
            if platform is not TargetPlatform.MATTER:
                raise
            runtime = await self._async_attempt_matter_recovery(
                error, background=background
            )
            if runtime is None:
                raise
        if platform is TargetPlatform.MATTER:
            self._clear_matter_recovery_episode()
        return runtime

    @callback
    def _handle_homekit_config_entry_change(self, change: Any, entry: Any) -> None:
        """Reconcile selected HomeKit source or managed target entries."""
        if getattr(entry, "domain", None) != "homekit":
            return
        selected = set(
            getattr(self.config, "homekit_source_entry_ids", ())
        ) | set(getattr(self.config, "homekit_managed_entry_ids", ()))
        if getattr(entry, "entry_id", None) not in selected:
            return
        change_value = str(getattr(change, "value", change)).casefold()
        self.schedule(f"homekit_config_entry_{change_value}")

    @callback
    def schedule(self, reason: str) -> None:
        """Debounce several rapid source updates into one reconciliation."""
        if not self.config.enabled or self._stopping:
            return
        if reason == "startup_scan":
            self._startup_scan_pending = True
            self._startup_scan_required = True
        if self._debounce_task and not self._debounce_task.done():
            if self._reconcile_active:
                # A target update can synchronously emit a HomeKit config-entry
                # event.  Queue one follow-up instead of cancelling the running
                # transaction from inside its own task.
                if self._startup_scan_required and reason != "startup_scan":
                    return
                self._pending_reason = reason
                return
            if self._retry_backoff_active:
                # Polls and push events must not cancel the bounded fault
                # backoff and turn a persistent outage into a hot loop.
                if self._startup_scan_required and reason != "startup_scan":
                    return
                self._pending_reason = reason
                return
            if self._startup_scan_required and reason != "startup_scan":
                # The mandatory startup scan will read the latest source.  Do
                # not let an event storm replace its retry generation before
                # the completion marker has been recorded.
                return
            self._debounce_task.cancel()
        coroutine = self._delayed_reconcile(reason)
        if self._entry is not None:
            self._debounce_task = self._entry.async_create_background_task(
                self.hass,
                coroutine,
                "platform_sync reconciliation",
                eager_start=True,
            )
        else:
            # Dependency-light tests and direct library consumers do not own a
            # Config Entry. Prefer HA's background bucket when available.
            background_creator = getattr(
                self.hass, "async_create_background_task", None
            )
            if background_creator is not None:
                self._debounce_task = background_creator(
                    coroutine,
                    "platform_sync reconciliation",
                    eager_start=True,
                )
            else:
                self._debounce_task = self.hass.async_create_task(
                    coroutine, eager_start=True
                )

    async def _delayed_reconcile(self, reason: str) -> None:
        delay = INTERNAL_DEBOUNCE_SECONDS
        retry_index = 0
        current_reason = reason
        startup_cycle_active = reason == "startup_scan"
        try:
            while self.config.enabled and not self._stopping:
                await asyncio.sleep(delay)
                self._retry_backoff_active = False
                if current_reason == "startup_scan":
                    self._startup_scan_pending = False
                    startup_cycle_active = True
                self._reconcile_active = True
                try:
                    result = await self.async_reconcile(
                        reason=current_reason,
                        apply=True,
                        _background=True,
                    )
                finally:
                    self._reconcile_active = False
                if (
                    result["status"] != "error"
                    and self._startup_scan_required
                    and startup_cycle_active
                ):
                    self.state.startup_scan_completed = (
                        self.state.last_run
                        or datetime.now(timezone.utc).isoformat()
                    )
                    self._startup_scan_required = False
                    self._notify()
                if self._pending_reason is not None:
                    current_reason = self._pending_reason
                    self._pending_reason = None
                    startup_cycle_active = (
                        startup_cycle_active or current_reason == "startup_scan"
                    )
                    if result["status"] == "error":
                        delay = INTERNAL_RETRY_DELAYS_SECONDS[retry_index]
                        retry_index = min(
                            retry_index + 1,
                            len(INTERNAL_RETRY_DELAYS_SECONDS) - 1,
                        )
                        self._retry_backoff_active = True
                    else:
                        retry_index = 0
                        delay = INTERNAL_DEBOUNCE_SECONDS
                    continue
                if result["status"] != "error":
                    return
                # HA may announce startup before every target config entry has
                # reached LOADED.  Stay fail-closed and retry without producing
                # an unhandled background-task exception or a hot loop.
                current_reason = "retry_after_error"
                delay = INTERNAL_RETRY_DELAYS_SECONDS[retry_index]
                retry_index = min(
                    retry_index + 1, len(INTERNAL_RETRY_DELAYS_SECONDS) - 1
                )
                self._retry_backoff_active = True
        except asyncio.CancelledError:
            return
        finally:
            self._retry_backoff_active = False
            if self._debounce_task is asyncio.current_task():
                self._debounce_task = None

    async def async_reconcile(
        self, reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        """Track direct callers so unload can cancel and drain them safely."""
        current_task = asyncio.current_task()
        track_direct = not _background and current_task is not None
        if track_direct:
            self._direct_tasks.add(current_task)
        try:
            return await self._async_reconcile_transaction(
                reason, apply, _background=_background
            )
        finally:
            if track_direct:
                self._direct_tasks.discard(current_task)

    async def _async_reconcile_transaction(
        self, reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        """Calculate exact plans and optionally apply them."""
        if not self.config.enabled:
            self.state.status = "disabled"
            return {"status": "disabled", "changed": False}
        if self._stopping:
            return {"status": "stopped", "changed": False}
        async with self._lock:
            if self._stopping:
                return {"status": "stopped", "changed": False}
            # Read the durable restart ledger only after acquiring the
            # transaction lock. A second reconciliation can already be queued
            # here while the first one removes an accessory and persists this
            # marker; a pre-lock check would then use stale state and cross the
            # same-process restart barrier.
            if apply and getattr(
                self.config, "homekit_restart_required_entry_ids", ()
            ):
                self.state.status = "homekit_restart_required"
                self.state.homekit_restart_required = True
                self._publish_homekit_restart_requirement(True)
                self._notify()
                return {
                    "status": self.state.status,
                    "changed": False,
                    "manual_pairing": list(self.state.manual_pairing),
                }
            self.state.status = "running"
            self.state.last_reason = reason
            self.state.error = None
            self.state.error_stage = None
            error_stage = "source_read"
            try:
                source = await self._async_read_source_with_recovery(
                    background=_background
                )
                error_stage = "homekit_provenance_read"
                dynamic_homekit_exclude = (
                    await async_find_apple_tv_entities(self.hass)
                    if getattr(
                        self.config, "locked_homekit_apple_tv_exclusion", False
                    )
                    else frozenset()
                )
                self._refresh_registry_watch_scope(
                    source.entities, dynamic_homekit_exclude
                )
                homekit_accessory_deferred = frozenset()
                homekit_logical_plan: TargetPlan | None = None
                homekit_prune_candidates: tuple[Any, ...] = ()
                homekit_prune_candidate_ids: frozenset[str] = frozenset()
                homekit_prune_ready = False
                matter_pairing_entities: frozenset[str] = frozenset()
                google_unrepresentable_entities: frozenset[str] = frozenset()
                matter_unrepresentable_entities: frozenset[str] = frozenset()
                plans: dict[TargetPlatform, TargetPlan] = {}
                runtime: dict[TargetPlatform, dict[str, Any]] = {}
                ordered_platforms = [
                    platform
                    for platform in TargetPlatform
                    if platform in self.config.targets
                ]
                for platform in ordered_platforms:
                    error_stage = f"{platform.value}_plan"
                    current = await async_read_target(self.hass, self.config, platform)
                    plan = evaluate_target(
                        source.entities,
                        current,
                        self.config.user_rules[platform],
                        self.config.locked_rules[platform],
                        platform,
                        dynamic_homekit_exclude
                        if platform is TargetPlatform.HOMEKIT
                        else frozenset(),
                    )
                    if platform is TargetPlatform.HOMEKIT:
                        homekit_logical_plan = plan
                        homekit_prune_candidates = self._homekit_prune_candidates(
                            plan.desired
                        )
                        homekit_prune_candidate_ids = frozenset(
                            candidate.entry_id
                            for candidate in homekit_prune_candidates
                        )
                        homekit_prune_ready = self._homekit_prune_confirmed(
                            source.fingerprint,
                            homekit_prune_candidates,
                            apply=bool(apply),
                        )
                        homekit_accessory_deferred = homekit_new_accessory_mode_entities(
                            self.hass, self.config, plan.desired
                        )
                        # Keep confirmed-but-not-yet-pruned side entities in
                        # their dedicated entries during the reversible target
                        # transaction. New accessory-mode entities are created
                        # only after Google/HomeKit/Matter have committed.
                        temporary_desired = (
                            plan.desired - homekit_accessory_deferred
                        ) | frozenset(
                            candidate.entity_id
                            for candidate in homekit_prune_candidates
                        )
                        plan = TargetPlan(
                            platform=platform,
                            desired=frozenset(temporary_desired),
                            current=current,
                            added=frozenset(temporary_desired) - current,
                            removed=current - frozenset(temporary_desired),
                        )
                    if platform is TargetPlatform.GOOGLE:
                        google_unrepresentable_entities = (
                            google_native_unrepresentable_entities(
                                self.hass, plan.desired
                            )
                        )
                        if google_unrepresentable_entities:
                            effective_desired = (
                                plan.desired - google_unrepresentable_entities
                            )
                            plan = TargetPlan(
                                platform=plan.platform,
                                desired=effective_desired,
                                current=plan.current,
                                added=effective_desired - plan.current,
                                removed=plan.current - effective_desired,
                            )
                        metadata_updates = await async_google_room_updates(
                            self.hass, self.config, plan.desired, source.rooms
                        )
                        if metadata_updates:
                            plan = TargetPlan(
                                platform=plan.platform,
                                desired=plan.desired,
                                current=plan.current,
                                added=plan.added,
                                removed=plan.removed,
                                metadata_updates=metadata_updates,
                            )
                    if platform is TargetPlatform.MATTER:
                        matter_unrepresentable_entities = (
                            matter_native_unrepresentable_entities(plan.desired)
                        )
                        matter_pairing_entities = (
                            await async_matter_manual_pairing_entities(
                                self.config, plan.desired
                            )
                        ).entities
                    plans[platform] = plan
                    error_stage = f"{platform.value}_validate"
                    google_current_unrepresentable = (
                        google_native_unrepresentable_entities(self.hass, current)
                        if platform is TargetPlatform.GOOGLE
                        else frozenset()
                    )
                    runtime[platform] = await self._async_validate_target_with_recovery(
                        platform,
                        current,
                        background=_background,
                        allowed_nonrunning_homekit_entry_ids=(
                            homekit_prune_candidate_ids
                            if platform is TargetPlatform.HOMEKIT
                            else frozenset()
                        ),
                        allowed_google_unrepresentable_entities=(
                            google_current_unrepresentable
                        ),
                    )

                if (
                    TargetPlatform.HOMEKIT in self.config.targets
                    and getattr(
                        self.config,
                        "locked_homekit_apple_tv_exclusion",
                        True,
                    )
                    and await async_find_apple_tv_entities(self.hass)
                    != dynamic_homekit_exclude
                ):
                    raise RuntimeError(
                        "HomeKit Apple TV provenance changed during planning"
                    )

                effective_apply = bool(apply)
                source_changed = source.fingerprint != self.state.source_fingerprint
                google_plan = plans.get(TargetPlatform.GOOGLE)
                if (
                    effective_apply
                    and google_plan is not None
                    and not google_plan.changed
                    and (
                        source_changed
                        or reason in {"startup_scan", "service_sync_now"}
                    )
                ):
                    # A pre-existing exact YAML set can still serialize to a
                    # missing/extra Google device set (for example after an HA
                    # upgrade or when an unsupported entity was already
                    # configured). Prove the native payload before reporting a
                    # startup, source-change, or manual no-op as synchronized.
                    # Stable 300-second health audits retain the lightweight
                    # validator because their source fingerprint is unchanged.
                    force_google_request = reason in {
                        "startup_scan",
                        "service_sync_now",
                    }
                    request_already_sent = (
                        self._google_noop_request_sync_fingerprint
                        == source.fingerprint
                    )
                    if force_google_request or not request_already_sent:
                        error_stage = "google_noop_sync"
                        before_sync = await _google_native_sync_payload_snapshot(
                            self.hass, google_plan.desired
                        )
                        request_sync = await _request_google_sync(self.hass)
                        after_sync = await _google_native_sync_payload_snapshot(
                            self.hass, google_plan.desired
                        )
                        self._google_noop_request_sync_fingerprint = (
                            source.fingerprint
                        )
                        self._google_noop_request_sync_result = dict(request_sync)
                        reused_request = False
                    else:
                        before_sync = {}
                        request_sync = dict(
                            self._google_noop_request_sync_result
                        )
                        after_sync = await _google_native_sync_payload_snapshot(
                            self.hass, google_plan.desired
                        )
                        reused_request = True
                    runtime[TargetPlatform.GOOGLE] = {
                        **runtime[TargetPlatform.GOOGLE],
                        **before_sync,
                        **request_sync,
                        **after_sync,
                        "request_sync_reused_for_source": reused_request,
                    }
                had_changes = any(plan.changed for plan in plans.values())
                if effective_apply and had_changes:
                    changed = [
                        plans[platform]
                        for platform in ordered_platforms
                        if plans[platform].changed
                    ]
                    backups = {}
                    for plan in changed:
                        error_stage = f"{plan.platform.value}_backup"
                        backups[plan.platform] = await async_prepare_target(
                            self.hass, self.config, plan.platform
                        )
                    attempted: list[TargetPlatform] = []
                    try:
                        for plan in changed:
                            error_stage = f"{plan.platform.value}_apply"
                            attempted.append(plan.platform)
                            self._active_attempted_targets.add(plan.platform)
                            if plan.platform is TargetPlatform.MATTER:
                                transaction_restart_reserved = False
                                if plan.removed:
                                    transaction_restart_reserved = (
                                        self._reserve_matter_transaction_restart()
                                    )
                                    if not transaction_restart_reserved:
                                        raise RuntimeError(
                                            "Matterbridge transaction restart could not be reserved"
                                        )
                                try:
                                    await async_apply_plan(
                                        self.hass,
                                        self.config,
                                        plan,
                                        source.rooms,
                                        before_matter_process_restart=(
                                            self._before_matter_process_restart
                                        ),
                                    )
                                finally:
                                    if transaction_restart_reserved:
                                        self._matter_transaction_restart_reserved = False
                            else:
                                await async_apply_plan(
                                    self.hass, self.config, plan, source.rooms
                                )

                        # A changed transaction is not complete until every
                        # target has been read back and runtime-validated.
                        verified: dict[TargetPlatform, TargetPlan] = {}
                        for platform in ordered_platforms:
                            error_stage = f"{platform.value}_readback"
                            actual = await async_read_target(
                                self.hass, self.config, platform
                            )
                            plan = plans[platform]
                            if actual != plan.desired:
                                raise RuntimeError(
                                    f"{platform.value} readback mismatch"
                                )
                            verified[platform] = plan.with_current(actual)
                            if (
                                platform is TargetPlatform.HOMEKIT
                                and homekit_prune_candidate_ids
                            ):
                                runtime[platform] = await async_validate_target(
                                    self.hass,
                                    self.config,
                                    platform,
                                    plan.desired,
                                    allowed_nonrunning_homekit_entry_ids=(
                                        homekit_prune_candidate_ids
                                    ),
                                )
                            else:
                                runtime[platform] = await async_validate_target(
                                    self.hass, self.config, platform, plan.desired
                                )
                        # The Apple TV exclusion is provenance-derived rather
                        # than a user filter.  Recheck it while the reversible
                        # target transaction is still open so a concurrent
                        # discovery change rolls every attempted target back
                        # instead of surfacing only after the commit boundary.
                        if (
                            TargetPlatform.HOMEKIT in self.config.targets
                            and getattr(
                                self.config,
                                "locked_homekit_apple_tv_exclusion",
                                True,
                            )
                            and await async_find_apple_tv_entities(self.hass)
                            != dynamic_homekit_exclude
                        ):
                            raise RuntimeError(
                                "HomeKit Apple TV provenance changed during target transaction"
                            )
                        plans = verified
                    except (Exception, asyncio.CancelledError) as apply_error:
                        rollback_errors: list[str] = []
                        rollback_order = list(reversed(attempted))
                        rollback_completed: set[TargetPlatform] = set()
                        try:
                            async with asyncio.timeout(ROLLBACK_TIMEOUT_SECONDS):
                                for platform in rollback_order:
                                    try:
                                        if (
                                            platform is TargetPlatform.HOMEKIT
                                            and homekit_prune_candidate_ids
                                        ):
                                            await async_restore_target(
                                                self.hass,
                                                self.config,
                                                backups[platform],
                                                allowed_nonrunning_homekit_entry_ids=(
                                                    homekit_prune_candidate_ids
                                                ),
                                            )
                                        else:
                                            await async_restore_target(
                                                self.hass,
                                                self.config,
                                                backups[platform],
                                            )
                                    except Exception:
                                        _LOGGER.exception(
                                            "Platform rollback failed for %s",
                                            platform.value,
                                        )
                                        rollback_errors.append(platform.value)
                                    else:
                                        rollback_completed.add(platform)
                                        self._active_attempted_targets.discard(platform)
                        except TimeoutError:
                            _LOGGER.exception(
                                "Platform rollback exceeded the safety deadline"
                            )
                            rollback_errors.extend(
                                platform.value
                                for platform in rollback_order
                                if platform not in rollback_completed
                            )
                        except asyncio.CancelledError:
                            _LOGGER.exception(
                                "Platform rollback was cancelled before completion"
                            )
                            rollback_errors.extend(
                                platform.value
                                for platform in rollback_order
                                if platform not in rollback_completed
                            )
                        if rollback_errors:
                            rollback_errors = list(dict.fromkeys(rollback_errors))
                            self.state.rollback_status = "incomplete"
                            self.state.rollback_incomplete_targets = sorted(
                                rollback_errors
                            )
                            raise RuntimeError(
                                "Platform apply failed and rollback was incomplete for "
                                + ", ".join(rollback_errors)
                            ) from apply_error
                        self.state.rollback_status = "complete"
                        self.state.rollback_incomplete_targets = []
                        self._active_attempted_targets.clear()
                        raise
                    if TargetPlatform.MATTER in verified:
                        self._clear_matter_recovery_episode()

                lifecycle_changed = False
                homekit_requirements: list[ManualPairingRequirement] = []
                if (
                    effective_apply
                    and TargetPlatform.HOMEKIT in self.config.targets
                    and homekit_logical_plan is not None
                ):
                    if (
                        getattr(
                            self.config,
                            "locked_homekit_apple_tv_exclusion",
                            True,
                        )
                        and await async_find_apple_tv_entities(self.hass)
                        != dynamic_homekit_exclude
                    ):
                        raise RuntimeError(
                            "HomeKit Apple TV provenance changed before lifecycle operation"
                        )
                    if homekit_prune_ready and homekit_prune_candidates:
                        try:
                            prune_result = (
                                await async_remove_homekit_accessory_candidates(
                                    self.hass,
                                    homekit_prune_candidates,
                                    owned_entry_ids=(
                                        self.config.homekit_lifecycle_entry_ids
                                    ),
                                    prunable_entry_ids=(
                                        self.config.homekit_lifecycle_entry_ids
                                    ),
                                )
                            )
                        except HomeKitLifecycleCancelled as cancellation:
                            completed_ids = set(
                                cancellation.removed_entry_ids
                            ) | set(cancellation.already_absent_entry_ids)
                            self._update_homekit_tracking(
                                remove_entry_ids=completed_ids,
                                add_restart_required_ids=set(
                                    cancellation.restart_required_entry_ids
                                )
                                | set(
                                    getattr(
                                        cancellation, "uncertain_entry_ids", ()
                                    )
                                ),
                            )
                            if cancellation.yaml_backup_paths:
                                self.state.homekit_yaml_backups = list(
                                    cancellation.yaml_backup_paths
                                )
                            self._publish_homekit_restart_requirement(
                                self.state.homekit_restart_required
                            )
                            raise
                        except HomeKitLifecycleError as error:
                            completed_ids = set(error.removed_entry_ids) | set(
                                error.already_absent_entry_ids
                            )
                            self._update_homekit_tracking(
                                remove_entry_ids=completed_ids,
                                add_restart_required_ids=set(
                                    error.restart_required_entry_ids
                                )
                                | set(getattr(error, "uncertain_entry_ids", ())),
                            )
                            if error.yaml_backup_paths:
                                self.state.homekit_yaml_backups = list(
                                    error.yaml_backup_paths
                                )
                            self._publish_homekit_restart_requirement(
                                self.state.homekit_restart_required
                            )
                            raise
                        self._update_homekit_tracking(
                            remove_entry_ids=(
                                set(prune_result.removed_entry_ids)
                                | set(prune_result.already_absent_entry_ids)
                            ),
                            add_restart_required_ids=set(
                                prune_result.restart_required_entry_ids
                            )
                            | set(
                                getattr(prune_result, "uncertain_entry_ids", ())
                            ),
                        )
                        self.state.homekit_yaml_backups = list(
                            prune_result.yaml_backup_paths
                        )
                        self._publish_homekit_restart_requirement(
                            self.state.homekit_restart_required
                        )
                        lifecycle_changed = bool(
                            prune_result.removed_entry_ids
                            or prune_result.already_absent_entry_ids
                        )
                        self._clear_homekit_prune_confirmation()

                    if (
                        not self.state.homekit_restart_required
                        and (
                            not homekit_prune_candidates
                            or homekit_prune_ready
                        )
                    ):
                        for entity_id in sorted(homekit_accessory_deferred):
                            try:
                                created_entry, _requirement = (
                                    await async_create_homekit_accessory(
                                        self.hass, entity_id
                                    )
                                )
                            except HomeKitAccessoryCreateCancelled as cancellation:
                                if cancellation.created_entry_id:
                                    self._update_homekit_tracking(
                                        add_entry_ids={
                                            cancellation.created_entry_id
                                        },
                                        add_pending_pairing_ids={
                                            cancellation.created_entry_id
                                        },
                                    )
                                raise
                            except HomeKitAccessoryCreateError as error:
                                if error.created_entry_id:
                                    self._update_homekit_tracking(
                                        add_entry_ids={error.created_entry_id},
                                        add_pending_pairing_ids={
                                            error.created_entry_id
                                        },
                                    )
                                raise
                            self._update_homekit_tracking(
                                add_entry_ids={created_entry.entry_id},
                                add_pending_pairing_ids={created_entry.entry_id},
                            )
                            lifecycle_changed = True

                    homekit_requirements = self._pairing_requirements(
                        homekit_logical_plan.desired
                    )

                    # Lifecycle actions are post-commit and therefore need an
                    # independent exact local readback. Controller apps remain
                    # explicitly unverified until their own UI is inspected.
                    if lifecycle_changed:
                        actual = await async_read_target(
                            self.hass, self.config, TargetPlatform.HOMEKIT
                        )
                        if (
                            not self.state.homekit_restart_required
                            and actual != homekit_logical_plan.desired
                        ):
                            raise RuntimeError(
                                "HomeKit lifecycle readback mismatch"
                            )
                        if self.state.homekit_restart_required:
                            runtime[TargetPlatform.HOMEKIT] = {
                                **runtime[TargetPlatform.HOMEKIT],
                                "restart_required": True,
                                "controller_verified": False,
                            }
                        else:
                            runtime[TargetPlatform.HOMEKIT] = (
                                await async_validate_target(
                                    self.hass,
                                    self.config,
                                    TargetPlatform.HOMEKIT,
                                    homekit_logical_plan.desired,
                                )
                            )
                        plans[TargetPlatform.HOMEKIT] = (
                            homekit_logical_plan.with_current(actual)
                        )
                matter_requirements: list[ManualPairingRequirement] = []
                for entity_id in sorted(matter_pairing_entities):
                    state = self.hass.states.get(entity_id)
                    name = (
                        state.attributes.get("friendly_name")
                        if state is not None
                        else None
                    )
                    matter_requirements.append(
                        ManualPairingRequirement(
                            platform="Matter",
                            entity_id=entity_id,
                            device_name=str(name or entity_id),
                            action=(
                                "到 Matterbridge 的 Devices 頁確認；若尚未配對，再掃描該裝置的 QR code。"
                                if self._is_zh_hant()
                                else "Check the Matterbridge Devices panel; if it is not already paired, scan that device's QR code."
                            ),
                        )
                    )
                google_compatibility_requirements: list[
                    ManualPairingRequirement
                ] = []
                for entity_id in sorted(google_unrepresentable_entities):
                    state = self.hass.states.get(entity_id)
                    name = (
                        state.attributes.get("friendly_name")
                        if state is not None
                        else None
                    )
                    domain = entity_id.split(".", 1)[0]
                    google_compatibility_requirements.append(
                        ManualPairingRequirement(
                            platform="Google Home",
                            entity_id=entity_id,
                            device_name=str(name or entity_id),
                            action=(
                                (
                                    "此攝影機實體沒有 Home Assistant 的原生串流能力，Google Home 無法建立可觀看的攝影機；請改選具備 STREAM 能力的 camera 實體。"
                                    if domain == "camera"
                                    else "這個實體沒有 Google Home 可用的原生特徵，已安全略過；請改選相容的 Home Assistant 實體。"
                                )
                                if self._is_zh_hant()
                                else (
                                    "This camera entity has no native Home Assistant stream capability, so Google Home cannot create a viewable camera. Select a camera entity with STREAM support."
                                    if domain == "camera"
                                    else "This entity has no native Google Home trait and was safely skipped. Select a compatible Home Assistant entity."
                                )
                            ),
                        )
                    )
                matter_compatibility_requirements: list[
                    ManualPairingRequirement
                ] = []
                for entity_id in sorted(matter_unrepresentable_entities):
                    state = self.hass.states.get(entity_id)
                    name = (
                        state.attributes.get("friendly_name")
                        if state is not None
                        else None
                    )
                    domain = entity_id.split(".", 1)[0]
                    matter_compatibility_requirements.append(
                        ManualPairingRequirement(
                            platform="Matter",
                            entity_id=entity_id,
                            device_name=str(name or entity_id),
                            action=(
                                (
                                    "Matter 沒有原生攝影機裝置類型；已保留同裝置可支援端點的探索，但 Matter 控制器不會顯示攝影機畫面。"
                                    if domain == "camera"
                                    else "Matter 沒有對應的原生保全系統裝置類型；已保留同裝置可支援端點的探索。"
                                )
                                if self._is_zh_hant()
                                else (
                                    "Matter has no native camera device type. Discovery remains enabled for supported endpoints on the same device, but a Matter controller cannot show the camera feed."
                                    if domain == "camera"
                                    else "Matter has no corresponding native alarm-system device type. Discovery remains enabled for supported endpoints on the same device."
                                )
                            ),
                        )
                    )
                requirements = (
                    homekit_requirements
                    + matter_requirements
                    + google_compatibility_requirements
                    + matter_compatibility_requirements
                )
                self.state.manual_pairing = [
                    item.as_dict() for item in requirements
                ]
                # Always update or dismiss the aggregate notification so that
                # removing a target or the last device cannot leave stale work.
                if effective_apply:
                    self._publish_pairing_requirements(requirements)

                self.state.plans = {}
                for platform, plan in plans.items():
                    record = plan.as_dict()
                    record["runtime"] = runtime[platform]
                    if platform is TargetPlatform.HOMEKIT:
                        record["deferred_accessory_mode"] = sorted(
                            homekit_accessory_deferred
                        )
                        record["pending_accessory_prune"] = list(
                            self.state.pending_homekit_prune
                        )
                        record["manual_pairing"] = list(
                            self.state.manual_pairing
                        )
                        record["controller_readback_verified"] = False
                    elif platform is TargetPlatform.GOOGLE:
                        record["not_exposed_platform_unsupported"] = sorted(
                            google_unrepresentable_entities
                        )
                        record["controller_readback_verified"] = False
                    elif platform is TargetPlatform.MATTER:
                        record["no_native_device_type"] = sorted(
                            matter_unrepresentable_entities
                        )
                        record["controller_readback_verified"] = False
                    self.state.plans[platform.value] = record
                # This fingerprint is the automatic source-audit baseline, so
                # it must describe a successfully applied generation. A
                # preview is observational only; advancing the baseline there
                # could hide a source change from the 15-second audit.
                if effective_apply:
                    self.state.source_fingerprint = source.fingerprint
                self.state.last_run = datetime.now(timezone.utc).isoformat()
                if effective_apply and self.state.homekit_restart_required:
                    self.state.status = "homekit_restart_required"
                elif (
                    effective_apply
                    and self.state.pending_homekit_prune
                    and not homekit_prune_ready
                ):
                    self.state.status = "pending_confirmation"
                elif effective_apply and self.state.manual_pairing:
                    self.state.status = "synced_manual_pairing_required"
                else:
                    self.state.status = "synced" if effective_apply else "preview"
                if effective_apply:
                    self.state.rollback_status = "not_needed"
                    self.state.rollback_incomplete_targets = []
                    self._active_attempted_targets.clear()
                result = {
                    "status": self.state.status,
                    "changed": had_changes or lifecycle_changed,
                    "plans": self.state.plans,
                    "manual_pairing": list(self.state.manual_pairing),
                    "homekit_restart_required": (
                        self.state.homekit_restart_required
                    ),
                }
                self.hass.bus.async_fire(EVENT_SYNC_COMPLETED, result)
                self._notify()
                return result
            except Exception as error:
                self.state.status = "error"
                self.state.error = str(error)
                self.state.error_stage = error_stage
                self.hass.bus.async_fire(EVENT_SYNC_FAILED, {"reason": reason})
                self._notify()
                if _background:
                    _LOGGER.debug(
                        "Platform synchronization is not ready; retrying safely",
                        exc_info=True,
                    )
                    return {"status": "error", "changed": False}
                _LOGGER.exception("Platform synchronization failed")
                raise

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
