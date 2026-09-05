"""Create owned HomeKit accessory entries and report manual pairing needs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

from homeassistant.const import CONF_ENTITY_ID, CONF_PORT, EntityStateAttribute


HOMEKIT_DOMAIN = "homekit"
HOMEKIT_MODE_ACCESSORY = "accessory"


class HomeKitAccessoryCreateError(RuntimeError):
    """An owned HomeKit accessory could not be created and verified."""

    def __init__(self, message: str, *, created_entry_id: str | None = None) -> None:
        self.created_entry_id = created_entry_id
        super().__init__(message)


class HomeKitAccessoryCreateCancelled(asyncio.CancelledError):
    """Accessory creation was cancelled after its config flow was settled.

    ``created_entry_id`` is populated only when the entry can be attributed to
    this call from the pre-create Config Entry snapshot.  Callers must record
    that ownership before re-raising this cancellation.
    """

    def __init__(self, *, created_entry_id: str | None = None) -> None:
        self.created_entry_id = created_entry_id
        super().__init__("HomeKit accessory creation was cancelled")


@dataclass(frozen=True, slots=True)
class ManualPairingRequirement:
    """One controller-side action that Home Assistant cannot complete."""

    platform: str
    entity_id: str
    device_name: str
    action: str
    entry_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return a user-facing service/event representation without secrets."""
        result = {
            "platform": self.platform,
            "entity_id": self.entity_id,
            "device_name": self.device_name,
            "action": self.action,
        }
        if self.entry_id:
            result["entry_id"] = self.entry_id
        return result


def _homekit_entry_exact_entities(entry: Any) -> frozenset[str] | None:
    """Return an exact include-only filter, or ``None`` when it is broad.

    Home Assistant's native HomeKit flow stores empty include/exclude lists
    alongside ``include_entities``.  Those empty keys are harmless, but any
    non-empty domain, exclusion, glob, or unknown selector makes exposure
    impossible to prove from an entity list alone and therefore fails closed.
    """
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping):
            continue
        entity_filter = source.get("filter")
        if not isinstance(entity_filter, Mapping):
            continue
        values = entity_filter.get("include_entities")
        if not isinstance(values, (list, tuple)) or not values:
            return None
        if any(not isinstance(value, str) or not value for value in values):
            return None
        if any(
            key != "include_entities" and value not in (None, False, "", (), [], {})
            for key, value in entity_filter.items()
        ):
            return None
        return frozenset(values)
    return None


def homekit_entry_entities(entry: Any) -> frozenset[str]:
    """Return only an exact explicit HomeKit entity list."""
    return _homekit_entry_exact_entities(entry) or frozenset()


def _homekit_entry_mode(entry: Any) -> str:
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if isinstance(source, Mapping):
            mode = source.get("homekit_mode", source.get("mode"))
            if isinstance(mode, str) and mode:
                return mode.casefold()
    return "bridge"


def homekit_entry_is_paired(entry: Any) -> bool | None:
    """Read native pyhap pairing state without exposing controller identities."""
    runtime = getattr(entry, "runtime_data", None)
    homekit = getattr(runtime, "homekit", None)
    driver = getattr(homekit, "driver", None)
    state = getattr(driver, "state", None)
    paired_clients = getattr(state, "paired_clients", None)
    if isinstance(paired_clients, Mapping):
        return bool(paired_clients)
    if isinstance(paired_clients, (set, frozenset, list, tuple)):
        return bool(paired_clients)
    return None


def _entity_name(hass: Any, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state is None:
        return entity_id
    name = state.attributes.get(EntityStateAttribute.FRIENDLY_NAME)
    return str(name).strip() if name else entity_id


async def _await_flow_settled(task: asyncio.Task[Any]) -> Any:
    """Do not abandon a config flow after it may have created an entry."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()
        raise cancellation


def _entry_port(entry: Any) -> int | None:
    """Read an entry's effective port without treating booleans as ports."""
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping) or CONF_PORT not in source:
            continue
        port = source.get(CONF_PORT)
        return port if isinstance(port, int) and not isinstance(port, bool) else None
    return None


def _entry_source(entry: Any) -> str:
    source = getattr(entry, "source", None)
    return str(getattr(source, "value", source or "")).casefold()


def _is_created_accessory(
    entry: Any, *, entity_id: str, port: int
) -> bool:
    """Return whether an entry exactly matches the native flow request."""
    return (
        getattr(entry, "domain", None) == HOMEKIT_DOMAIN
        and _entry_source(entry) == HOMEKIT_MODE_ACCESSORY
        and _homekit_entry_mode(entry) == HOMEKIT_MODE_ACCESSORY
        and _homekit_entry_exact_entities(entry) == frozenset({entity_id})
        and _entry_port(entry) == port
    )


def _created_entry_id_from_snapshot(
    hass: Any,
    *,
    before_entry_ids: frozenset[str],
    entity_id: str,
    port: int,
    result: Any = None,
) -> str | None:
    """Attribute a newly-created exact accessory to this flow invocation."""
    new_matching_entries = [
        entry
        for entry in hass.config_entries.async_entries(HOMEKIT_DOMAIN)
        if isinstance(getattr(entry, "entry_id", None), str)
        and entry.entry_id not in before_entry_ids
        and _is_created_accessory(entry, entity_id=entity_id, port=port)
    ]
    result_entry = result.get("result") if isinstance(result, Mapping) else None
    result_entry_id = getattr(result_entry, "entry_id", None)
    if any(entry.entry_id == result_entry_id for entry in new_matching_entries):
        return result_entry_id
    if len(new_matching_entries) == 1:
        return new_matching_entries[0].entry_id
    return None


def _settled_task_result(task: asyncio.Task[Any]) -> Any:
    """Retrieve a drained task result without leaking its exception."""
    if not task.done() or task.cancelled():
        return None
    try:
        return task.result()
    except BaseException:
        return None


async def async_create_homekit_accessory(
    hass: Any, entity_id: str
) -> tuple[Any, ManualPairingRequirement]:
    """Create and verify one native accessory-mode Config Entry.

    Existing entries are never adopted implicitly: ownership must be granted
    explicitly in Platform Sync options before this function is called.
    """
    state = hass.states.get(entity_id)
    if state is None:
        raise HomeKitAccessoryCreateError(
            "The HomeKit accessory entity is unavailable"
        )
    try:
        from homeassistant.components.homekit.const import DEFAULT_CONFIG_FLOW_PORT
        from homeassistant.components.homekit.util import (
            async_find_next_available_port,
            state_needs_accessory_mode,
        )
    except (ImportError, AttributeError) as error:
        raise HomeKitAccessoryCreateError(
            "Home Assistant HomeKit accessory creation API is unavailable"
        ) from error
    if not state_needs_accessory_mode(state):
        raise HomeKitAccessoryCreateError(
            "The entity no longer requires HomeKit accessory mode"
        )

    existing_entries = list(hass.config_entries.async_entries(HOMEKIT_DOMAIN))
    before_entry_ids = frozenset(
        entry.entry_id
        for entry in existing_entries
        if isinstance(getattr(entry, "entry_id", None), str)
    )
    for existing in existing_entries:
        exact_entities = _homekit_entry_exact_entities(existing)
        if exact_entities is None:
            raise HomeKitAccessoryCreateError(
                "An unmanaged HomeKit entry has a broad or non-exact filter; "
                "select or narrow it before creating another accessory"
            )
        if entity_id in exact_entities:
            raise HomeKitAccessoryCreateError(
                "An unmanaged HomeKit entry already exposes this entity; "
                "select it explicitly before lifecycle management"
            )

    port = async_find_next_available_port(hass, DEFAULT_CONFIG_FLOW_PORT)
    task = hass.async_create_task(
        hass.config_entries.flow.async_init(
            HOMEKIT_DOMAIN,
            context={"source": "accessory"},
            data={CONF_ENTITY_ID: entity_id, CONF_PORT: port},
        ),
        eager_start=True,
    )
    try:
        result = await _await_flow_settled(task)
    except asyncio.CancelledError as cancellation:
        created_entry_id = _created_entry_id_from_snapshot(
            hass,
            before_entry_ids=before_entry_ids,
            entity_id=entity_id,
            port=port,
            result=_settled_task_result(task),
        )
        raise HomeKitAccessoryCreateCancelled(
            created_entry_id=created_entry_id
        ) from cancellation
    except Exception as error:
        created_entry_id = _created_entry_id_from_snapshot(
            hass,
            before_entry_ids=before_entry_ids,
            entity_id=entity_id,
            port=port,
        )
        raise HomeKitAccessoryCreateError(
            "HomeKit accessory Config Entry creation failed",
            created_entry_id=created_entry_id,
        ) from error

    created_entry_id = _created_entry_id_from_snapshot(
        hass,
        before_entry_ids=before_entry_ids,
        entity_id=entity_id,
        port=port,
        result=result,
    )
    if not isinstance(result, Mapping) or result.get("type") != "create_entry":
        raise HomeKitAccessoryCreateError(
            "HomeKit did not create the requested accessory Config Entry",
            created_entry_id=created_entry_id,
        )
    entry = result.get("result")
    entry_id = getattr(entry, "entry_id", None)
    if not isinstance(entry_id, str) or not entry_id:
        raise HomeKitAccessoryCreateError(
            "The created HomeKit accessory has no Config Entry identity",
            created_entry_id=created_entry_id,
        )
    if created_entry_id != entry_id:
        raise HomeKitAccessoryCreateError(
            "The HomeKit flow result could not be attributed to this request",
            created_entry_id=created_entry_id,
        )
    live = hass.config_entries.async_get_entry(entry_id)
    if live is None:
        raise HomeKitAccessoryCreateError(
            "The created HomeKit accessory could not be read back",
            created_entry_id=entry_id,
        )
    if (
        not _is_created_accessory(live, entity_id=entity_id, port=port)
    ):
        raise HomeKitAccessoryCreateError(
            "The created HomeKit accessory failed exact readback validation",
            created_entry_id=entry_id,
        )
    post_create_entries = list(hass.config_entries.async_entries(HOMEKIT_DOMAIN))
    if any(
        _homekit_entry_exact_entities(candidate) is None
        for candidate in post_create_entries
    ):
        raise HomeKitAccessoryCreateError(
            "A concurrent broad HomeKit entry prevents duplicate-exposure validation",
            created_entry_id=entry_id,
        )
    exposing_entries = [
        candidate
        for candidate in post_create_entries
        if entity_id in homekit_entry_entities(candidate)
    ]
    if len(exposing_entries) != 1 or exposing_entries[0].entry_id != entry_id:
        raise HomeKitAccessoryCreateError(
            "A concurrent HomeKit entry also exposes this entity",
            created_entry_id=entry_id,
        )
    requirement = ManualPairingRequirement(
        platform="HomeKit",
        entity_id=entity_id,
        device_name=_entity_name(hass, entity_id),
        action="Open the Home Assistant HomeKit notification and pair this accessory in Apple Home.",
        entry_id=entry_id,
    )
    return live, requirement


def pairing_requirements_markdown(
    requirements: list[ManualPairingRequirement], *, zh_hant: bool
) -> str:
    """Render a secret-free persistent-notification body."""
    if not requirements:
        return ""
    if zh_hant:
        lines = [
            "下列裝置需要在目標平台完成配對，或確認是否已經配對：",
            "",
        ]
        lines.extend(
            f"- {item.platform}｜{item.device_name}（{item.entity_id}）：{item.action}"
            for item in requirements
        )
        lines.extend(
            [
                "",
                "Google Home 帳戶已連結後不需逐裝置配對；一般 Matter Bridge 端點也不需逐裝置配對。Matter 獨立 server node 的控制器配對狀態無法由此外掛可靠讀回，因此只會提示確認，不會宣稱尚未配對。",
                "本清單不含 PIN、Token 或其他敏感資料。",
            ]
        )
        return "\n".join(lines)
    lines = [
        "The following devices require pairing or a controller-side pairing check:",
        "",
    ]
    lines.extend(
        f"- {item.platform} | {item.device_name} ({item.entity_id}): {item.action}"
        for item in requirements
    )
    lines.extend(
        [
            "",
            "Linked Google Home accounts and normal Matter Bridge endpoints do not require per-device pairing. Matter controller pairing for separate server nodes cannot be read back reliably, so those entries are checks rather than claims that the device is unpaired.",
            "This list never contains PINs, tokens, or other secrets.",
        ]
    )
    return "\n".join(lines)
