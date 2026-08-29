"""Event-driven synchronization manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.lovelace.const import EVENT_LOVELACE_UPDATED
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval

from .config import SyncConfig
from .const import (
    DOMAIN,
    EVENT_SYNC_COMPLETED,
    EVENT_SYNC_FAILED,
    INTERNAL_DEBOUNCE_SECONDS,
    INTERNAL_POLL_SECONDS,
    INTERNAL_RETRY_DELAYS_SECONDS,
    SourceKind,
    TargetPlatform,
)
from .models import SourceSnapshot, TargetPlan, evaluate_target
from .sources import async_find_apple_tv_entities, async_read_source
from .targets import (
    GOOGLE_SYNC_TIMEOUT,
    HOMEKIT_RELOAD_TIMEOUT,
    MATTER_BACKUP_TIMEOUT,
    MATTER_REQUEST_TIMEOUT,
    MATTER_RUNTIME_TIMEOUT,
    MatterbridgeRuntimeError,
    async_apply_plan,
    async_google_room_updates,
    async_prepare_target,
    async_read_target,
    async_recover_matter_runtime,
    async_restore_target,
    async_validate_target,
)

_LOGGER = logging.getLogger(__name__)
ROLLBACK_SAFETY_MARGIN_SECONDS = 15.0
STOP_DRAIN_SAFETY_MARGIN_SECONDS = 5.0
# A cancelled all-target transaction may have to restore Google, HomeKit and
# Matter in reverse order. Matter restoration can consume two management
# requests, one runtime wait, and one three-request exact validation. Keep one
# explicit budget for the complete rollback instead of letting HA unload return
# while a process-restart rollback is still unverified.
ROLLBACK_TIMEOUT_SECONDS = (
    GOOGLE_SYNC_TIMEOUT
    + HOMEKIT_RELOAD_TIMEOUT
    + MATTER_RUNTIME_TIMEOUT
    + 5 * MATTER_REQUEST_TIMEOUT
    + ROLLBACK_SAFETY_MARGIN_SECONDS
)
STOP_DRAIN_TIMEOUT_SECONDS = (
    max(ROLLBACK_TIMEOUT_SECONDS, MATTER_BACKUP_TIMEOUT)
    + STOP_DRAIN_SAFETY_MARGIN_SECONDS
)
MATTER_RECOVERY_COOLDOWN_SECONDS = 300.0
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
    rollback_status: str = "not_needed"
    rollback_incomplete_targets: list[str] = field(default_factory=list)


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
        self.state = SyncState(status="idle" if config.enabled else "disabled")
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
        self._active_attempted_targets: set[TargetPlatform] = set()
        self._matter_recovery_guard = _matter_recovery_guard(hass, config)

    async def async_start(self) -> None:
        """Start only when the master switch is enabled."""
        self._stopping = False
        if not self.config.enabled:
            _LOGGER.info("Platform Sync is disabled; no listeners or polling started")
            return
        if self.config.source_kind is SourceKind.DASHBOARD:
            self._unsubscribers.append(
                self.hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._handle_event)
            )
            self._unsubscribers.append(
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_event
                )
            )
        elif self.config.source_kind is SourceKind.HOMEKIT:
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
        elif self.config.source_kind in {SourceKind.GOOGLE, SourceKind.MATTER}:
            self._start_fallback_polling()
        if self.hass.state is CoreState.running:
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
        self._pending_reason = None
        self._startup_scan_pending = False
        self._startup_scan_required = False
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

        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._handle_poll,
                timedelta(seconds=INTERNAL_POLL_SECONDS),
            )
        )

    @callback
    def _handle_event(self, event: Any) -> None:
        self.schedule(getattr(event, "event_type", "event"))

    @callback
    def _handle_poll(self, now: Any) -> None:
        self.schedule("source_poll")

    def _clear_matter_recovery_episode(self) -> None:
        """End one failure episode while retaining its cooldown timestamp."""
        guard = self._matter_recovery_guard
        guard.attempted_for_episode = False
        guard.active_token = None
        guard.process_restart_attempted = False

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
    ) -> dict[str, Any]:
        try:
            runtime = await async_validate_target(
                self.hass, self.config, platform, expected
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
        """Reconcile only changes to explicitly selected HomeKit source entries."""
        if getattr(entry, "domain", None) != "homekit":
            return
        if getattr(entry, "entry_id", None) not in set(
            self.config.homekit_source_entry_ids
        ):
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
            self.state.status = "running"
            self.state.last_reason = reason
            self.state.error = None
            try:
                source = await self._async_read_source_with_recovery(
                    background=_background
                )
                dynamic_homekit_exclude = (
                    await async_find_apple_tv_entities(self.hass)
                    if getattr(
                        self.config, "locked_homekit_apple_tv_exclusion", False
                    )
                    else frozenset()
                )
                plans: dict[TargetPlatform, TargetPlan] = {}
                runtime: dict[TargetPlatform, dict[str, Any]] = {}
                ordered_platforms = [
                    platform
                    for platform in TargetPlatform
                    if platform in self.config.targets
                ]
                for platform in ordered_platforms:
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
                    if platform is TargetPlatform.GOOGLE:
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
                    plans[platform] = plan
                    runtime[platform] = await self._async_validate_target_with_recovery(
                        platform,
                        current,
                        background=_background,
                    )

                effective_apply = bool(apply)
                had_changes = any(plan.changed for plan in plans.values())
                if effective_apply and had_changes:
                    changed = [
                        plans[platform]
                        for platform in ordered_platforms
                        if plans[platform].changed
                    ]
                    backups = {
                        plan.platform: await async_prepare_target(
                            self.hass, self.config, plan.platform
                        )
                        for plan in changed
                    }
                    attempted: list[TargetPlatform] = []
                    try:
                        for plan in changed:
                            attempted.append(plan.platform)
                            self._active_attempted_targets.add(plan.platform)
                            if plan.platform is TargetPlatform.MATTER:
                                await async_apply_plan(
                                    self.hass,
                                    self.config,
                                    plan,
                                    source.rooms,
                                    before_matter_process_restart=(
                                        self._before_matter_process_restart
                                    ),
                                )
                            else:
                                await async_apply_plan(
                                    self.hass, self.config, plan, source.rooms
                                )

                        # A changed transaction is not complete until every
                        # target has been read back and runtime-validated.
                        verified: dict[TargetPlatform, TargetPlan] = {}
                        for platform in ordered_platforms:
                            actual = await async_read_target(
                                self.hass, self.config, platform
                            )
                            plan = plans[platform]
                            if actual != plan.desired:
                                raise RuntimeError(
                                    f"{platform.value} readback mismatch"
                                )
                            verified[platform] = plan.with_current(actual)
                            runtime[platform] = await async_validate_target(
                                self.hass, self.config, platform, plan.desired
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

                self.state.plans = {}
                for platform, plan in plans.items():
                    record = plan.as_dict()
                    record["runtime"] = runtime[platform]
                    self.state.plans[platform.value] = record
                self.state.source_fingerprint = source.fingerprint
                self.state.last_run = datetime.now(timezone.utc).isoformat()
                self.state.status = "synced" if effective_apply else "preview"
                if effective_apply:
                    self.state.rollback_status = "not_needed"
                    self.state.rollback_incomplete_targets = []
                    self._active_attempted_targets.clear()
                result = {
                    "status": self.state.status,
                    "changed": had_changes,
                    "plans": self.state.plans,
                }
                self.hass.bus.async_fire(EVENT_SYNC_COMPLETED, result)
                self._notify()
                return result
            except Exception as error:
                self.state.status = "error"
                self.state.error = str(error)
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
