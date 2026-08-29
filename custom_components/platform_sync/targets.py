"""Target adapters for Google Assistant, HomeKit and Matterbridge."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import yaml as yaml_util

from .config import SyncConfig
from .const import TargetPlatform
from .models import TargetPlan, normalize_entities


MATTER_PLUGIN = "matterbridge-hass"
MATTER_REQUEST_TIMEOUT = 15.0
MATTER_BACKUP_TIMEOUT = 120.0
MATTER_RUNTIME_TIMEOUT = 60.0
GOOGLE_SYNC_TIMEOUT = 30.0
HOMEKIT_RELOAD_TIMEOUT = 60.0
HOMEKIT_FILTER_KEYS = (
    "include_entities",
    "include_domains",
    "include_entity_globs",
    "exclude_entities",
    "exclude_domains",
    "exclude_entity_globs",
)
HOMEKIT_COMPETING_SOURCE_FILTER_KEYS = tuple(
    key for key in HOMEKIT_FILTER_KEYS if key != "include_entities"
)
MATTER_EMPTY_STRING_FILTER_KEYS = (
    "filterByArea",
    "filterByLabel",
    "virtualControlLabel",
    "splitByLabel",
)
MATTER_EMPTY_LIST_FILTER_KEYS = (
    "blackList",
    "entityWhiteList",
    "entityBlackList",
    "splitEntities",
)
MATTER_EMPTY_MAPPING_FILTER_KEYS = ("deviceEntityBlackList",)
ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


@dataclass(slots=True)
class TargetBackup:
    """Opaque pre-change state used for same-run rollback."""

    platform: TargetPlatform
    payload: Any


@dataclass(frozen=True, slots=True, repr=False)
class MatterRuntimeSnapshot:
    """One privacy-safe Matterbridge management snapshot."""

    settings: Mapping[str, Any]
    plugin: Mapping[str, Any]
    plugin_config: Mapping[str, Any]
    devices: Any
    allowlist: frozenset[str]


class MatterbridgeRuntimeError(RuntimeError):
    """A classified Matterbridge runtime failure without remote error material."""

    def __init__(
        self,
        reason: str,
        expected: frozenset[str],
        *,
        recoverable: bool,
    ) -> None:
        self.reason = reason
        self.expected = expected
        self.recoverable = recoverable
        super().__init__(f"Matterbridge runtime is not ready ({reason})")


class MatterbridgeProcessRestartError(RuntimeError):
    """A full Matterbridge restart was attempted but did not converge."""


class HomeKitSourceEntryMissingError(RuntimeError):
    """Raised when a selected HomeKit source Config Entry no longer exists."""


class HomeKitSourceEntryUnavailableError(RuntimeError):
    """Raised when a selected HomeKit source Config Entry is not loaded."""


class HomeKitSourceFilterUnsupportedError(RuntimeError):
    """Raised when a selected HomeKit source cannot be enumerated exactly."""


class EmptyHomeKitSourceError(RuntimeError):
    """Raised when a selected HomeKit source entry exposes no entities."""


def _state_value(entry: Any) -> str:
    state = getattr(entry, "state", None)
    return str(getattr(state, "value", state or "")).casefold()


def _homekit_filter(entry: Any) -> dict[str, Any]:
    """Return the effective HomeKit filter, including legacy fallbacks."""
    for source in (entry.options or {}, entry.data or {}):
        if not isinstance(source, Mapping):
            continue
        if "filter" in source:
            nested = source.get("filter")
            return deepcopy(dict(nested)) if isinstance(nested, Mapping) else {}
        if any(key in source for key in HOMEKIT_FILTER_KEYS):
            return {
                key: deepcopy(source.get(key))
                for key in HOMEKIT_FILTER_KEYS
                if key in source
            }
    return {}


def _homekit_entities(entry: Any) -> frozenset[str]:
    """Read HomeKit's current nested include-entity list."""
    return normalize_entities(_homekit_filter(entry).get("include_entities", []))


def _strict_homekit_source_filter(entry: Any) -> dict[str, Any]:
    """Return only an explicit nested HomeKit filter for source evaluation."""
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping):
            continue
        if "filter" in source:
            nested = source.get("filter")
            if not isinstance(nested, Mapping):
                raise HomeKitSourceFilterUnsupportedError(
                    "A selected HomeKit source entry has a malformed nested filter"
                )
            return deepcopy(dict(nested))
        if any(key in source for key in HOMEKIT_FILTER_KEYS):
            raise HomeKitSourceFilterUnsupportedError(
                "A selected HomeKit source entry uses a legacy top-level filter"
            )
    raise HomeKitSourceFilterUnsupportedError(
        "A selected HomeKit source entry has no explicit nested filter"
    )


def _strict_homekit_source_entities(entity_filter: Mapping[str, Any]) -> frozenset[str]:
    """Reject malformed HomeKit source lists instead of returning a partial set."""
    try:
        return _strict_entity_ids(
            entity_filter.get("include_entities", []),
            context="HomeKit source include_entities",
        )
    except RuntimeError as error:
        raise HomeKitSourceFilterUnsupportedError(str(error)) from error


def _strict_entity_ids(
    values: Any, *, context: str, allow_empty: bool = True
) -> frozenset[str]:
    """Parse an exact entity-ID array without silently dropping bad values."""
    raw_entities = values
    if not isinstance(raw_entities, (list, tuple)):
        raise RuntimeError(f"{context} is not an array")
    cleaned: list[str] = []
    for value in raw_entities:
        if not isinstance(value, str):
            raise RuntimeError(f"{context} contains a non-string entity ID")
        if value != value.strip():
            raise RuntimeError(f"{context} contains surrounding whitespace")
        entity_id = value
        if not ENTITY_ID_PATTERN.fullmatch(entity_id):
            raise RuntimeError(f"{context} contains a malformed entity ID")
        if entity_id in cleaned:
            raise RuntimeError(f"{context} contains duplicate entity IDs")
        cleaned.append(entity_id)
    if not allow_empty and not cleaned:
        raise RuntimeError(f"{context} must not be empty")
    return frozenset(cleaned)


def _require_empty_homekit_competing_filters(
    entity_filter: Mapping[str, Any], *, source: bool
) -> None:
    """Require every competing HomeKit filter to be an explicit empty array."""
    for key in HOMEKIT_COMPETING_SOURCE_FILTER_KEYS:
        if key not in entity_filter:
            continue
        value = entity_filter[key]
        if not isinstance(value, (list, tuple)) or value:
            if source:
                raise HomeKitSourceFilterUnsupportedError(
                    "A selected HomeKit source entry has unsupported filter rules"
                )
            raise RuntimeError("A managed HomeKit entry has competing filter rules")


def _strict_homekit_target_entities(entry: Any) -> frozenset[str]:
    """Read one managed HomeKit entry only when its filter is exactly enumerable."""
    options = getattr(entry, "options", {}) or {}
    if not isinstance(options, Mapping) or "filter" not in options:
        raise RuntimeError(
            "A managed HomeKit entry has no explicit nested options filter"
        )
    nested = options.get("filter")
    if not isinstance(nested, Mapping):
        raise RuntimeError("A managed HomeKit entry has a malformed options filter")
    entity_filter = dict(nested)
    if "include_entities" not in entity_filter:
        raise RuntimeError(
            "A managed HomeKit entry has no explicit include_entities filter"
        )
    _require_empty_homekit_competing_filters(entity_filter, source=False)
    return _strict_entity_ids(
        entity_filter["include_entities"],
        context="HomeKit target include_entities",
        allow_empty=False,
    )


def _homekit_options_with_entities(
    entry: Any, entities: frozenset[str]
) -> dict[str, Any]:
    """Build exact HomeKit options while preserving non-filter customization."""
    options = deepcopy(dict(entry.options or {}))
    if not entities:
        raise RuntimeError(
            "A managed HomeKit entry cannot use an empty include_entities filter"
        )
    entity_filter: dict[str, Any] = {"include_entities": sorted(entities)}
    # Explicit entity mode must not compete with domain or exclusion filters.
    for key in HOMEKIT_COMPETING_SOURCE_FILTER_KEYS:
        entity_filter[key] = []
    options["filter"] = entity_filter
    for key in HOMEKIT_FILTER_KEYS:
        options.pop(key, None)
    return options


def _homekit_mode(entry: Any) -> str:
    for source in (entry.options or {}, entry.data or {}):
        if not isinstance(source, Mapping):
            continue
        value = source.get("homekit_mode", source.get("mode"))
        if isinstance(value, str) and value:
            return value.casefold()
    return "bridge"


def _managed_homekit_entries(hass: HomeAssistant, config: SyncConfig) -> list[Any]:
    requested = tuple(dict.fromkeys(config.homekit_managed_entry_ids))
    if not requested:
        raise RuntimeError("HomeKit managed config entries are not explicitly configured")
    available = {
        entry.entry_id: entry
        for entry in hass.config_entries.async_entries("homekit")
    }
    missing = sorted(set(requested) - set(available))
    if missing:
        raise RuntimeError(f"Managed HomeKit config entries are missing: {len(missing)}")
    return [available[entry_id] for entry_id in requested]


async def async_read_homekit_source_entries(
    hass: HomeAssistant, requested_entry_ids: tuple[str, ...]
) -> frozenset[str]:
    """Read only explicitly selected HomeKit entries as an exact source set."""
    requested = tuple(dict.fromkeys(requested_entry_ids))
    if not requested:
        raise HomeKitSourceEntryMissingError(
            "HomeKit source Config Entries are not explicitly configured"
        )
    available = {
        entry.entry_id: entry
        for entry in hass.config_entries.async_entries("homekit")
    }
    missing = sorted(set(requested) - set(available))
    if missing:
        raise HomeKitSourceEntryMissingError(
            f"Selected HomeKit source Config Entries are missing: {len(missing)}"
        )

    entities: set[str] = set()
    for entry_id in requested:
        entry = available[entry_id]
        if _state_value(entry) != "loaded":
            raise HomeKitSourceEntryUnavailableError(
                "A selected HomeKit source Config Entry is not loaded"
            )
        entity_filter = _strict_homekit_source_filter(entry)
        _require_empty_homekit_competing_filters(entity_filter, source=True)
        selected_entities = _strict_homekit_source_entities(entity_filter)
        if not selected_entities:
            raise EmptyHomeKitSourceError(
                "A selected HomeKit source entry contains no entities"
            )
        entities.update(selected_entities)
    if not entities:
        raise EmptyHomeKitSourceError("Selected HomeKit source entries are empty")
    return frozenset(entities)


def _homekit_layout(entries: list[Any]) -> tuple[Any, list[Any]]:
    """Identify one main Bridge and preserve every explicitly managed side entry."""
    mode_bridges = [entry for entry in entries if _homekit_mode(entry) != "accessory"]
    if len(mode_bridges) == 1:
        main = mode_bridges[0]
    else:
        multi_entity = [
            entry for entry in entries if len(_strict_homekit_target_entities(entry)) > 1
        ]
        if len(multi_entity) != 1:
            raise RuntimeError("Managed HomeKit entries do not identify exactly one main Bridge")
        main = multi_entity[0]
    dedicated = [entry for entry in entries if entry is not main]
    if any(len(_homekit_entities(entry)) > 1 for entry in dedicated):
        raise RuntimeError("A managed HomeKit side entry exposes more than one entity")
    return main, dedicated


def _google_context(hass: HomeAssistant) -> tuple[Any, Any, dict[str, Any]]:
    entries = hass.config_entries.async_entries("google_assistant")
    if len(entries) != 1:
        raise RuntimeError("Exactly one Google Assistant config entry is required")
    entry = entries[0]
    if _state_value(entry) and _state_value(entry) != "loaded":
        raise RuntimeError("Google Assistant config entry is not loaded")
    runtime = getattr(entry, "runtime_data", None)
    runtime_config = getattr(runtime, "_config", None)
    if not isinstance(runtime_config, Mapping):
        raise RuntimeError("Google Assistant runtime configuration is unavailable")
    if runtime_config.get("expose_by_default") is not False:
        raise RuntimeError("Google Assistant expose_by_default must be false for exact sync")
    entity_config = getattr(runtime, "entity_config", None)
    if not isinstance(entity_config, dict):
        raise RuntimeError("Google Assistant runtime entity_config is not mutable")
    return entry, runtime, entity_config


async def _load_google_yaml(
    hass: HomeAssistant, config: SyncConfig
) -> tuple[Path, dict[str, Any]]:
    path = Path(hass.config.path(config.google_config_path))
    if not path.exists():
        return path, {}
    loaded = await hass.async_add_executor_job(yaml_util.load_yaml, str(path))
    if loaded is None:
        return path, {}
    if not isinstance(loaded, Mapping):
        raise RuntimeError("Google Assistant entity config YAML is not a mapping")
    return path, deepcopy(dict(loaded))


async def async_google_room_updates(
    hass: HomeAssistant,
    config: SyncConfig,
    desired: frozenset[str],
    rooms: Mapping[str, str],
) -> tuple[str, ...]:
    """Return entities whose supported Google room differs from the source."""
    _, current = await _load_google_yaml(hass, config)
    return _google_room_updates_for_config(current, desired, rooms)


def _google_room_updates_for_config(
    current: Mapping[str, Any],
    desired: frozenset[str],
    rooms: Mapping[str, str],
) -> tuple[str, ...]:
    """Compare the HA Google Assistant entity_config ``room`` field."""
    return tuple(
        entity_id
        for entity_id in sorted(desired & rooms.keys())
        if not isinstance(current.get(entity_id), Mapping)
        or current[entity_id].get("room") != rooms[entity_id]
    )


def _build_google_config(
    current: Mapping[str, Any],
    desired: frozenset[str],
    rooms: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Build an exact Google entity_config using HA-supported keys only."""
    updated = {
        entity_id: deepcopy(dict(current.get(entity_id, {})))
        if isinstance(current.get(entity_id), Mapping)
        else {}
        for entity_id in sorted(desired)
    }
    for entity_id, value in updated.items():
        value.pop("room_hint", None)
        value["expose"] = True
        if entity_id in rooms and rooms[entity_id]:
            value["room"] = rooms[entity_id]
    return updated


async def _matter_request(
    config: SyncConfig, command: str, payload: Mapping[str, Any] | None = None
) -> Any:
    """Call the local Matterbridge websocket API without logging credentials."""
    import aiohttp

    url = f"ws://{config.matter_host}:{config.matter_port}/"
    request_id = secrets.randbelow(9_990_000) + 10_000
    request = {
        "id": request_id,
        "sender": "PlatformSync",
        "method": f"/api/{command}",
        "src": "Frontend",
        "dst": "Matterbridge",
        "params": dict(payload or {}),
    }
    try:
        async with asyncio.timeout(MATTER_REQUEST_TIMEOUT):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    await ws.send_json(request)
                    while True:
                        message = await ws.receive()
                        if message.type is not aiohttp.WSMsgType.TEXT:
                            raise RuntimeError(
                                f"Matterbridge {command} returned no JSON response"
                            )
                        response = json.loads(message.data)
                        if response.get("id") != request_id:
                            continue
                        if response.get("error") or not response.get("success"):
                            raise RuntimeError(f"Matterbridge {command} failed")
                        return response.get("response")
    except TimeoutError as error:
        raise RuntimeError(f"Matterbridge {command} timed out") from error


async def _matter_fire_and_forget(
    config: SyncConfig, command: str, payload: Mapping[str, Any] | None = None
) -> None:
    """Send a command whose successful execution closes the management socket."""
    import aiohttp

    url = f"ws://{config.matter_host}:{config.matter_port}/"
    request = {
        "id": secrets.randbelow(9_990_000) + 10_000,
        "sender": "PlatformSync",
        "method": f"/api/{command}",
        "src": "Frontend",
        "dst": "Matterbridge",
        "params": dict(payload or {}),
    }
    try:
        async with asyncio.timeout(MATTER_REQUEST_TIMEOUT):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    await ws.send_json(request)
    except TimeoutError as error:
        raise RuntimeError(
            f"Matterbridge {command} command could not be sent"
        ) from error
    except Exception as error:
        raise RuntimeError(
            f"Matterbridge {command} command could not be sent"
        ) from error


async def _matter_create_backup_ready(config: SyncConfig) -> None:
    """Wait for both the backup request acknowledgement and archive completion."""
    import aiohttp

    url = f"ws://{config.matter_host}:{config.matter_port}/"
    request_id = secrets.randbelow(9_990_000) + 10_000
    request = {
        "id": request_id,
        "sender": "PlatformSync",
        "method": "/api/create-backup",
        "src": "Frontend",
        "dst": "Matterbridge",
        "params": {},
    }
    acknowledged = False
    archive_ready = False
    try:
        async with asyncio.timeout(MATTER_BACKUP_TIMEOUT):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    await ws.send_json(request)
                    while not (acknowledged and archive_ready):
                        message = await ws.receive()
                        if message.type is not aiohttp.WSMsgType.TEXT:
                            raise RuntimeError(
                                "Matterbridge backup returned no JSON response"
                            )
                        response = json.loads(message.data)
                        if response.get("id") == request_id:
                            if response.get("error") or not response.get("success"):
                                raise RuntimeError(
                                    "Matterbridge backup request failed"
                                )
                            acknowledged = True
                            continue
                        archive = response.get("response")
                        if (
                            response.get("id") == 0
                            and response.get("method") == "archive"
                            and response.get("success") is True
                            and isinstance(archive, Mapping)
                            and archive.get("command") == "zip"
                            and isinstance(archive.get("archivePath"), str)
                            and archive["archivePath"].endswith(
                                "matterbridge.backup.zip"
                            )
                        ):
                            archive_ready = True
    except TimeoutError as error:
        raise RuntimeError(
            "Matterbridge backup did not complete before the safety deadline"
        ) from error
    except Exception as error:
        raise RuntimeError("Matterbridge backup completion is unverified") from error


def _find_matter_plugin(value: Any) -> Mapping[str, Any]:
    candidates = (
        value
        if isinstance(value, list)
        else value.get("plugins", [])
        if isinstance(value, Mapping)
        else []
    )
    for plugin in candidates:
        if isinstance(plugin, Mapping) and str(plugin.get("name", "")) == MATTER_PLUGIN:
            return plugin
    raise RuntimeError("Matterbridge Home Assistant plugin not found")


def _matter_plugin_config(plugin: Mapping[str, Any]) -> dict[str, Any]:
    value = plugin.get("configJson", plugin.get("config", plugin))
    if not isinstance(value, Mapping):
        raise RuntimeError("Matterbridge Home Assistant plugin config is unavailable")
    return deepcopy(dict(value))


def _strict_matter_allowlist(plugin_config: Mapping[str, Any]) -> frozenset[str]:
    """Read Matterbridge's allowlist without hiding malformed or duplicate rows."""
    if "whiteList" not in plugin_config:
        raise RuntimeError("Matterbridge exact whiteList is missing")
    return _strict_entity_ids(
        plugin_config["whiteList"],
        context="Matterbridge whiteList",
        allow_empty=False,
    )


def _require_empty_matter_filters(plugin_config: Mapping[str, Any]) -> None:
    """Reject every filter that can broaden, narrow, or reshape the allowlist."""
    for key in MATTER_EMPTY_STRING_FILTER_KEYS:
        if key in plugin_config and plugin_config[key] != "":
            raise RuntimeError("Matterbridge has a competing string filter")
    for key in MATTER_EMPTY_LIST_FILTER_KEYS:
        if key in plugin_config and (
            not isinstance(plugin_config[key], (list, tuple)) or plugin_config[key]
        ):
            raise RuntimeError("Matterbridge has a competing list filter")
    for key in MATTER_EMPTY_MAPPING_FILTER_KEYS:
        if key in plugin_config and (
            not isinstance(plugin_config[key], Mapping) or plugin_config[key]
        ):
            raise RuntimeError("Matterbridge has a competing mapping filter")


def _matter_runtime_ready(
    settings: Mapping[str, Any], plugin: Mapping[str, Any]
) -> bool:
    """Return whether Matterbridge and its HA plugin have fully converged."""
    information = settings.get("matterbridgeInformation", settings)
    if not isinstance(information, Mapping):
        return False
    return bool(
        str(information.get("bridgeStatus", "")).casefold() == "started"
        and plugin.get("enabled") is True
        and plugin.get("loaded") is True
        and plugin.get("started") is True
        and not plugin.get("error")
        and not plugin.get("restartRequired")
        and not information.get("restartRequired")
        and not information.get("fixedRestartRequired")
    )


def _matter_loaded_device_count(
    plugin: Mapping[str, Any], devices: Any, expected: frozenset[str]
) -> int | None:
    """Return the exact loaded plugin-device count, or None when unverified."""
    registered = plugin.get("registeredDevices")
    if isinstance(registered, bool) or not isinstance(registered, int) or registered < 0:
        return None
    if not isinstance(devices, list) or any(
        not isinstance(device, Mapping) for device in devices
    ):
        return None
    if any(device.get("pluginName") != MATTER_PLUGIN for device in devices):
        return None
    identities: set[tuple[Any, Any, Any]] = set()
    for device in devices:
        endpoint = device.get("endpoint")
        unique_id = device.get("uniqueId")
        serial = device.get("serial")
        if (
            isinstance(endpoint, bool)
            or not isinstance(endpoint, int)
            or endpoint < 0
            or not isinstance(unique_id, str)
            or not unique_id
            or not isinstance(serial, str)
            or not serial
        ):
            return None
        identity = (endpoint, unique_id, serial)
        if identity in identities:
            return None
        identities.add(identity)
    if len(devices) != registered:
        return None
    if expected and registered == 0:
        return None
    return registered


def _matter_information(settings: Mapping[str, Any]) -> Mapping[str, Any] | None:
    information = settings.get("matterbridgeInformation", settings)
    return information if isinstance(information, Mapping) else None


def _matter_token_configured(plugin_config: Mapping[str, Any]) -> bool:
    token = plugin_config.get("token")
    return isinstance(token, str) and bool(token.strip())


def _matter_runtime_issue(
    snapshot: MatterRuntimeSnapshot, expected: frozenset[str]
) -> str | None:
    """Return a stable, non-sensitive runtime reason code."""
    information = _matter_information(snapshot.settings)
    if information is None:
        return "bridge_state_unverified"
    if str(information.get("bridgeStatus", "")).casefold() != "started":
        return "bridge_not_started"
    if snapshot.plugin.get("enabled") is not True:
        return "plugin_disabled"
    if not _matter_token_configured(snapshot.plugin_config):
        return "token_missing"
    if not expected or snapshot.allowlist != expected:
        return "allowlist_mismatch"
    if snapshot.plugin.get("error"):
        return "plugin_error"
    if (
        snapshot.plugin.get("restartRequired")
        or information.get("restartRequired")
        or information.get("fixedRestartRequired")
    ):
        return "restart_required"
    if (
        snapshot.plugin.get("loaded") is not True
        or snapshot.plugin.get("started") is not True
    ):
        return "plugin_not_started"
    loaded_devices = _matter_loaded_device_count(
        snapshot.plugin, snapshot.devices, expected
    )
    if loaded_devices is not None:
        return None
    registered = snapshot.plugin.get("registeredDevices")
    if (
        expected
        and registered == 0
        and isinstance(snapshot.devices, list)
        and not snapshot.devices
    ):
        return "devices_zero"
    return "device_state_unverified"


def _matter_recovery_eligible(
    snapshot: MatterRuntimeSnapshot, expected: frozenset[str]
) -> bool:
    """Allow process recovery only for a narrow, fully verified failure set."""
    information = _matter_information(snapshot.settings)
    if (
        not expected
        or information is None
        or str(information.get("bridgeStatus", "")).casefold() != "started"
        or snapshot.plugin.get("name") != MATTER_PLUGIN
        or snapshot.plugin.get("enabled") is not True
        or not _matter_token_configured(snapshot.plugin_config)
    ):
        return False
    try:
        configured = _strict_matter_allowlist(snapshot.plugin_config)
        _require_empty_matter_filters(snapshot.plugin_config)
    except RuntimeError:
        return False
    if configured != expected or snapshot.allowlist != expected:
        return False
    return _matter_runtime_issue(snapshot, expected) in {
        "plugin_error",
        "restart_required",
        "plugin_not_started",
        "devices_zero",
    }


def _matter_runtime_payload(
    snapshot: MatterRuntimeSnapshot, expected: frozenset[str]
) -> dict[str, Any]:
    loaded_devices = _matter_loaded_device_count(
        snapshot.plugin, snapshot.devices, expected
    )
    if loaded_devices is None:
        raise MatterbridgeRuntimeError(
            "device_state_unverified", expected, recoverable=False
        )
    return {
        "loaded": True,
        "bridge_status": "started",
        "plugin_enabled": True,
        "plugin_loaded": True,
        "plugin_started": True,
        "plugin_error": False,
        "restart_required": False,
        "registered_devices": loaded_devices,
        "loaded_devices": loaded_devices,
        "filter_by_area": "",
        "filter_by_label": "",
        "virtual_control_label": "",
    }


async def _read_matter_runtime_snapshot(
    config: SyncConfig,
) -> MatterRuntimeSnapshot:
    """Read all Matterbridge state needed for one bounded validation attempt."""
    plugins = await _matter_request(config, "plugins")
    plugin = _find_matter_plugin(plugins)
    plugin_config = _matter_plugin_config(plugin)
    allowlist = _strict_matter_allowlist(plugin_config)
    _require_empty_matter_filters(plugin_config)
    settings = await _matter_request(config, "settings")
    if not isinstance(settings, Mapping):
        raise RuntimeError("Matterbridge settings response is unavailable")
    devices = await _matter_request(
        config, "devices", {"pluginName": MATTER_PLUGIN}
    )
    return MatterRuntimeSnapshot(
        settings=settings,
        plugin=plugin,
        plugin_config=plugin_config,
        devices=devices,
        allowlist=allowlist,
    )


async def _wait_matter_runtime(
    config: SyncConfig, expected: frozenset[str], timeout: float = MATTER_RUNTIME_TIMEOUT
) -> dict[str, Any]:
    last_error: Exception | None = None
    try:
        async with asyncio.timeout(timeout):
            while True:
                try:
                    snapshot = await _read_matter_runtime_snapshot(config)
                    reason = _matter_runtime_issue(snapshot, expected)
                    if reason is None:
                        return _matter_runtime_payload(snapshot, expected)
                    last_error = MatterbridgeRuntimeError(
                        reason,
                        expected,
                        recoverable=_matter_recovery_eligible(snapshot, expected),
                    )
                except Exception as error:  # Briefly unavailable while restarting.
                    last_error = error
                await asyncio.sleep(2)
    except TimeoutError:
        pass
    if last_error:
        raise RuntimeError("Matterbridge runtime did not become ready") from last_error
    raise RuntimeError("Matterbridge runtime did not converge to the expected allowlist")


async def async_recover_matter_runtime(
    config: SyncConfig,
    expected: frozenset[str],
    *,
    before_matter_process_restart: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Back up, restart the plugin, then use one guarded process fallback."""
    snapshot = await _read_matter_runtime_snapshot(config)
    reason = _matter_runtime_issue(snapshot, expected)
    if reason is None:
        return _matter_runtime_payload(snapshot, expected)
    if not _matter_recovery_eligible(snapshot, expected):
        raise MatterbridgeRuntimeError(reason, expected, recoverable=False)
    await _matter_create_backup_ready(config)
    await _matter_request(config, "restartplugin", {"pluginName": MATTER_PLUGIN})
    try:
        return await _wait_matter_runtime(config, expected)
    except Exception as plugin_restart_error:
        snapshot = await _read_matter_runtime_snapshot(config)
        reason = _matter_runtime_issue(snapshot, expected)
        if reason is None:
            return _matter_runtime_payload(snapshot, expected)
        if not _matter_recovery_eligible(snapshot, expected):
            raise RuntimeError(
                "Matterbridge plugin restart did not converge safely"
            ) from plugin_restart_error
        if (
            before_matter_process_restart is None
            or not before_matter_process_restart()
        ):
            raise RuntimeError(
                "Matterbridge process restart was blocked by the recovery guard"
            ) from plugin_restart_error
        try:
            await _matter_fire_and_forget(config, "restart", {})
            return await _wait_matter_runtime(config, expected)
        except Exception as process_restart_error:
            raise MatterbridgeProcessRestartError(
                "Matterbridge process restart did not restore the runtime"
            ) from process_restart_error


async def async_read_target(
    hass: HomeAssistant, config: SyncConfig, platform: TargetPlatform
) -> frozenset[str]:
    """Read the exact current target exposure set."""
    if platform is TargetPlatform.GOOGLE:
        _, _, entity_config = _google_context(hass)
        return frozenset(
            key
            for key, value in entity_config.items()
            if not isinstance(value, Mapping) or value.get("expose", True)
        )
    if platform is TargetPlatform.HOMEKIT:
        entries = _managed_homekit_entries(hass, config)
        return frozenset().union(
            *(_strict_homekit_target_entities(entry) for entry in entries)
        )
    plugins = await _matter_request(config, "plugins")
    plugin = _find_matter_plugin(plugins)
    plugin_config = _matter_plugin_config(plugin)
    _require_empty_matter_filters(plugin_config)
    return _strict_matter_allowlist(plugin_config)


async def async_read_platform_source(
    hass: HomeAssistant, config: SyncConfig, platform: TargetPlatform
) -> frozenset[str]:
    """Read a platform as a source without granting write ownership."""
    if platform is not TargetPlatform.HOMEKIT:
        return await async_read_target(hass, config, platform)

    return await async_read_homekit_source_entries(
        hass, config.homekit_source_entry_ids
    )


async def async_validate_target(
    hass: HomeAssistant,
    config: SyncConfig,
    platform: TargetPlatform,
    expected: frozenset[str],
) -> dict[str, Any]:
    """Fail closed unless exact configuration and runtime state are readable."""
    if platform is TargetPlatform.GOOGLE:
        entry, _, entity_config = _google_context(hass)
        if _state_value(entry) != "loaded":
            raise RuntimeError("Google Assistant config entry is not loaded")
        if not hass.services.has_service("google_assistant", "request_sync"):
            raise RuntimeError("Google Assistant Request Sync service is unavailable")
        path, file_config = await _load_google_yaml(hass, config)
        if not path.exists():
            raise RuntimeError(
                "Google Assistant dedicated entity configuration file is missing"
            )
        if file_config != entity_config:
            raise RuntimeError("Google Assistant YAML and runtime entity_config differ")
        actual = frozenset(
            key
            for key, value in entity_config.items()
            if not isinstance(value, Mapping) or value.get("expose", True)
        )
        if actual != expected:
            raise RuntimeError("Google Assistant exact readback mismatch")
        return {
            "loaded": True,
            "config_entries": 1,
            "expose_by_default": False,
            "yaml_runtime_match": True,
        }

    if platform is TargetPlatform.HOMEKIT:
        entries = _managed_homekit_entries(hass, config)
        _homekit_layout(entries)
        seen: set[str] = set()
        duplicates: set[str] = set()
        loaded = 0
        for entry in entries:
            if _state_value(entry) != "loaded":
                raise RuntimeError("A managed HomeKit config entry is not loaded")
            loaded += 1
            values = set(_strict_homekit_target_entities(entry))
            duplicates.update(seen & values)
            seen.update(values)
        if duplicates:
            raise RuntimeError(f"HomeKit duplicate exposure detected: {len(duplicates)}")
        if frozenset(seen) != expected:
            raise RuntimeError("HomeKit exact readback mismatch")
        return {
            "loaded": loaded == len(entries),
            "loaded_entries": loaded,
            "managed_entries": len(entries),
            "duplicates": 0,
        }

    snapshot = await _read_matter_runtime_snapshot(config)
    if snapshot.allowlist != expected:
        raise RuntimeError("Matterbridge exact allowlist readback mismatch")
    reason = _matter_runtime_issue(snapshot, expected)
    if reason is not None:
        raise MatterbridgeRuntimeError(
            reason,
            expected,
            recoverable=_matter_recovery_eligible(snapshot, expected),
        )
    return _matter_runtime_payload(snapshot, expected)


async def async_prepare_target(
    hass: HomeAssistant, config: SyncConfig, platform: TargetPlatform
) -> TargetBackup:
    """Capture recoverable state for one target before any target is changed."""
    if platform is TargetPlatform.GOOGLE:
        _, _, runtime_config = _google_context(hass)
        path, _ = await _load_google_yaml(hass, config)
        existed = path.exists()
        raw = await hass.async_add_executor_job(path.read_bytes) if existed else b""
        backup_path = path.with_suffix(path.suffix + ".platform-sync.bak")
        if existed:
            await hass.async_add_executor_job(backup_path.write_bytes, raw)
        return TargetBackup(
            platform,
            {
                "path": path,
                "existed": existed,
                "raw": raw,
                "runtime": deepcopy(runtime_config),
                "entities": await async_read_target(hass, config, platform),
            },
        )

    if platform is TargetPlatform.HOMEKIT:
        entries = _managed_homekit_entries(hass, config)
        return TargetBackup(
            platform,
            {
                "options": {
                    entry.entry_id: deepcopy(dict(entry.options or {}))
                    for entry in entries
                },
                "entities": await async_read_target(hass, config, platform),
            },
        )

    plugins = await _matter_request(config, "plugins")
    plugin_config = _matter_plugin_config(_find_matter_plugin(plugins))
    _require_empty_matter_filters(plugin_config)
    await _matter_create_backup_ready(config)
    return TargetBackup(
        platform,
        {
            "config": plugin_config,
            "entities": _strict_matter_allowlist(plugin_config),
        },
    )


async def _request_google_sync(hass: HomeAssistant) -> None:
    """Request Google synchronization within a fixed overall deadline."""
    try:
        async with asyncio.timeout(GOOGLE_SYNC_TIMEOUT):
            await hass.services.async_call(
                "google_assistant", "request_sync", blocking=True
            )
    except TimeoutError as error:
        raise RuntimeError("Google Assistant Request Sync timed out") from error


async def _reload_homekit_entries(
    hass: HomeAssistant, entries: list[Any], *, rollback: bool = False
) -> None:
    """Reload all managed HomeKit entries within one total deadline."""
    try:
        async with asyncio.timeout(HOMEKIT_RELOAD_TIMEOUT):
            for entry in entries:
                if await hass.config_entries.async_reload(entry.entry_id) is False:
                    action = "rollback reload" if rollback else "config entry reload"
                    raise RuntimeError(f"HomeKit {action} failed")
                if not rollback and _state_value(entry) != "loaded":
                    raise RuntimeError(
                        "HomeKit config entry did not return to loaded"
                    )
    except TimeoutError as error:
        action = "rollback reload" if rollback else "config entry reload"
        raise RuntimeError(f"HomeKit {action} timed out") from error


async def _apply_google(
    hass: HomeAssistant,
    config: SyncConfig,
    desired: frozenset[str],
    rooms: Mapping[str, str],
) -> None:
    path, current = await _load_google_yaml(hass, config)
    updated = _build_google_config(current, desired, rooms)
    await hass.async_add_executor_job(yaml_util.save_yaml, str(path), updated)
    _, _, runtime_config = _google_context(hass)
    runtime_config.clear()
    runtime_config.update(deepcopy(updated))
    await _request_google_sync(hass)


async def _apply_homekit(
    hass: HomeAssistant, config: SyncConfig, desired: frozenset[str]
) -> None:
    entries = _managed_homekit_entries(hass, config)
    main, dedicated = _homekit_layout(entries)
    current_total = frozenset().union(*(_homekit_entities(entry) for entry in entries))
    assigned: set[str] = set()
    for entry in dedicated:
        assigned.update(_homekit_entities(entry) & desired)

    # Accessory creation includes a pairing flow. New entities that require it
    # fail closed until the user creates and selects that side entry.
    try:
        from homeassistant.components.homekit.util import state_needs_accessory_mode

        needs_accessory = {
            entity_id
            for entity_id in desired - current_total
            if (state := hass.states.get(entity_id)) is not None
            and state_needs_accessory_mode(state)
        }
    except (ImportError, AttributeError):
        needs_accessory = frozenset()
    if needs_accessory:
        raise RuntimeError(
            f"New HomeKit accessory-mode entries must be created first: {len(needs_accessory)}"
        )

    for entry in dedicated:
        kept = _homekit_entities(entry) & desired
        if not kept:
            raise RuntimeError(
                "A managed HomeKit Accessory would become empty; remove or unmanage it first"
            )
        hass.config_entries.async_update_entry(
            entry, options=_homekit_options_with_entities(entry, kept)
        )
    main_entities = desired - assigned
    if not main_entities:
        raise RuntimeError("The managed HomeKit main Bridge would become empty")
    hass.config_entries.async_update_entry(
        main, options=_homekit_options_with_entities(main, main_entities)
    )
    await _reload_homekit_entries(hass, [main, *dedicated])


async def _save_matter_config(
    config: SyncConfig, plugin_config: Mapping[str, Any]
) -> None:
    await _matter_request(
        config,
        "savepluginconfig",
        {"pluginName": MATTER_PLUGIN, "formData": deepcopy(dict(plugin_config))},
    )
    await _matter_request(config, "restartplugin", {"pluginName": MATTER_PLUGIN})


async def _apply_matter(
    config: SyncConfig,
    desired: frozenset[str],
    *,
    before_matter_process_restart: Callable[[], bool] | None = None,
) -> bool:
    if not desired:
        raise RuntimeError(
            "Matterbridge whiteList cannot be empty because empty exposes everything"
        )
    plugins = await _matter_request(config, "plugins")
    plugin_config = _matter_plugin_config(_find_matter_plugin(plugins))
    plugin_config["whiteList"] = sorted(desired)
    plugin_config["filterByArea"] = ""
    plugin_config["filterByLabel"] = ""
    plugin_config["virtualControlLabel"] = ""
    plugin_config["blackList"] = []
    plugin_config["entityWhiteList"] = []
    plugin_config["entityBlackList"] = []
    plugin_config["deviceEntityBlackList"] = {}
    plugin_config["splitEntities"] = []
    plugin_config["splitByLabel"] = ""
    await _save_matter_config(config, plugin_config)
    try:
        await _wait_matter_runtime(config, desired)
        return False
    except Exception as plugin_restart_error:
        # A plugin restart can remain wedged after a Home Assistant outage.  A
        # whole-process restart is allowed once only when the management API
        # can prove that credentials and the exact filter configuration are
        # intact.  The caller already captured a pre-change backup.
        snapshot = await _read_matter_runtime_snapshot(config)
        reason = _matter_runtime_issue(snapshot, desired)
        if reason is None:
            return False
        if not _matter_recovery_eligible(snapshot, desired):
            raise RuntimeError(
                "Matterbridge plugin restart did not converge safely"
            ) from plugin_restart_error
        if (
            before_matter_process_restart is None
            or not before_matter_process_restart()
        ):
            raise RuntimeError(
                "Matterbridge process restart was blocked by the recovery guard"
            ) from plugin_restart_error
        try:
            await _matter_fire_and_forget(config, "restart", {})
            await _wait_matter_runtime(config, desired)
        except Exception as process_restart_error:
            raise MatterbridgeProcessRestartError(
                "Matterbridge process restart did not restore the runtime"
            ) from process_restart_error
        return True


async def async_apply_plan(
    hass: HomeAssistant,
    config: SyncConfig,
    plan: TargetPlan,
    rooms: Mapping[str, str] | None = None,
    *,
    before_matter_process_restart: Callable[[], bool] | None = None,
) -> bool:
    """Apply one exact plan and report a full Matterbridge process restart."""
    if plan.platform is TargetPlatform.GOOGLE:
        await _apply_google(hass, config, plan.desired, rooms or {})
        return False
    elif plan.platform is TargetPlatform.HOMEKIT:
        await _apply_homekit(hass, config, plan.desired)
        return False
    return await _apply_matter(
        config,
        plan.desired,
        before_matter_process_restart=before_matter_process_restart,
    )


async def async_restore_target(
    hass: HomeAssistant, config: SyncConfig, backup: TargetBackup
) -> None:
    """Restore one target and verify its pre-change exact set."""
    payload = backup.payload
    if backup.platform is TargetPlatform.GOOGLE:
        path: Path = payload["path"]
        if payload["existed"]:
            await hass.async_add_executor_job(path.write_bytes, payload["raw"])
        elif path.exists():
            await hass.async_add_executor_job(path.unlink)
        _, _, runtime_config = _google_context(hass)
        runtime_config.clear()
        runtime_config.update(deepcopy(payload["runtime"]))
        await _request_google_sync(hass)
    elif backup.platform is TargetPlatform.HOMEKIT:
        entries = _managed_homekit_entries(hass, config)
        by_id = {entry.entry_id: entry for entry in entries}
        for entry_id, options in payload["options"].items():
            hass.config_entries.async_update_entry(
                by_id[entry_id], options=deepcopy(options)
            )
        await _reload_homekit_entries(hass, entries, rollback=True)
    else:
        await _save_matter_config(config, payload["config"])
        await _wait_matter_runtime(config, payload["entities"])
    await async_validate_target(hass, config, backup.platform, payload["entities"])
