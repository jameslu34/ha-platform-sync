"""Fail-closed lifecycle helpers for owned HomeKit singleton side entries.

The synchronization manager deliberately treats HomeKit Config Entry deletion
as a separate, irreversible lifecycle operation.  This module therefore only
plans removals for entry IDs that a caller explicitly marks as both owned and
prunable, and it revalidates every live entry immediately before deletion.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence, Set
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import secrets
import shutil
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


HOMEKIT_DOMAIN = "homekit"
HOMEKIT_MODE_ACCESSORY = "accessory"
HOMEKIT_MODE_BRIDGE = "bridge"
HOMEKIT_VALID_MODES = frozenset({HOMEKIT_MODE_ACCESSORY, HOMEKIT_MODE_BRIDGE})
HOMEKIT_SOURCE_IMPORT = "import"
HOMEKIT_FILTER_KEYS = (
    "include_entities",
    "include_domains",
    "include_entity_globs",
    "exclude_entities",
    "exclude_domains",
    "exclude_entity_globs",
)
HOMEKIT_COMPETING_FILTER_KEYS = tuple(
    key for key in HOMEKIT_FILTER_KEYS if key != "include_entities"
)
ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class HomeKitAccessoryPruneCandidate:
    """One explicitly owned HomeKit singleton side entry that may be removed."""

    entry_id: str
    entity_id: str
    imported: bool
    name: str
    port: int
    mode: str | None
    yaml_relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class HomeKitAccessoryPruneResult:
    """Verified result of an owned HomeKit side-entry prune operation."""

    removed_entry_ids: frozenset[str]
    removed_entities: frozenset[str]
    already_absent_entry_ids: frozenset[str] = frozenset()
    restart_required_entry_ids: frozenset[str] = frozenset()
    uncertain_entry_ids: frozenset[str] = frozenset()
    yaml_backup_paths: tuple[str, ...] = ()


class HomeKitLifecycleError(RuntimeError):
    """A lifecycle operation failed closed, possibly after partial progress."""

    def __init__(
        self,
        message: str,
        *,
        removed_entry_ids: Iterable[str] = (),
        removed_entities: Iterable[str] = (),
        already_absent_entry_ids: Iterable[str] = (),
        restart_required_entry_ids: Iterable[str] = (),
        uncertain_entry_ids: Iterable[str] = (),
        yaml_backup_paths: Iterable[str] = (),
    ) -> None:
        self.removed_entry_ids = frozenset(removed_entry_ids)
        self.removed_entities = frozenset(removed_entities)
        self.already_absent_entry_ids = frozenset(already_absent_entry_ids)
        self.restart_required_entry_ids = frozenset(restart_required_entry_ids)
        self.uncertain_entry_ids = frozenset(uncertain_entry_ids)
        self.yaml_backup_paths = tuple(yaml_backup_paths)
        super().__init__(message)


class HomeKitLifecycleCancelled(asyncio.CancelledError):
    """Caller cancellation raised after an in-flight removal has settled.

    Cancellation remains cancellation (rather than being converted to a normal
    lifecycle error), while exposing the same durable progress fields that a
    manager must persist before it lets the cancellation escape.
    """

    def __init__(
        self,
        message: str,
        *,
        removed_entry_ids: Iterable[str] = (),
        removed_entities: Iterable[str] = (),
        already_absent_entry_ids: Iterable[str] = (),
        restart_required_entry_ids: Iterable[str] = (),
        uncertain_entry_ids: Iterable[str] = (),
        yaml_backup_paths: Iterable[str] = (),
    ) -> None:
        self.removed_entry_ids = frozenset(removed_entry_ids)
        self.removed_entities = frozenset(removed_entities)
        self.already_absent_entry_ids = frozenset(already_absent_entry_ids)
        self.restart_required_entry_ids = frozenset(restart_required_entry_ids)
        self.uncertain_entry_ids = frozenset(uncertain_entry_ids)
        self.yaml_backup_paths = tuple(yaml_backup_paths)
        super().__init__(message)


@dataclass(slots=True)
class _YamlEdit:
    """One validated, recoverable YAML mutation."""

    path: Path
    relative_path: str
    original_bytes: bytes
    updated_data: Any
    backup_path: Path | None = None
    updated_bytes: bytes | None = None


@dataclass(frozen=True, slots=True)
class _RemovalOutcome:
    """Settled inner Config Entry removal plus caller-cancellation state."""

    response: Any = None
    error: BaseException | None = None
    caller_cancellation: asyncio.CancelledError | None = None


def _strict_id_set(values: Iterable[str], *, label: str) -> frozenset[str]:
    """Return a validated ID set without accepting strings as iterables."""
    if isinstance(values, (str, bytes)):
        raise HomeKitLifecycleError(f"{label} must be an iterable of entry IDs")
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise HomeKitLifecycleError(f"{label} contains an invalid entry ID")
        if value in result:
            raise HomeKitLifecycleError(f"{label} contains a duplicate entry ID")
        result.add(value)
    return frozenset(result)


def _entry_source(entry: Any) -> str:
    """Return a normalized Config Entry source."""
    source = getattr(entry, "source", None)
    return str(getattr(source, "value", source or "")).casefold()


def _entry_mode(entry: Any) -> str | None:
    """Return a strict explicit HomeKit mode using HA option precedence."""
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping):
            continue
        key = "homekit_mode" if "homekit_mode" in source else "mode"
        if key not in source:
            continue
        value = source.get(key)
        if not isinstance(value, str) or not value.strip():
            raise HomeKitLifecycleError(
                "A prunable HomeKit entry has an invalid explicit mode"
            )
        normalized = value.casefold()
        if normalized not in HOMEKIT_VALID_MODES:
            raise HomeKitLifecycleError(
                "A prunable HomeKit entry has an unsupported explicit mode"
            )
        return normalized
    return None


def _strict_single_entity(entry: Any) -> str:
    """Read one exact effective filter and reject every competing selector."""
    entity_filter: Mapping[str, Any] | None = None
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping):
            continue
        if "filter" not in source:
            continue
        nested = source.get("filter")
        if not isinstance(nested, Mapping):
            raise HomeKitLifecycleError(
                "A prunable HomeKit entry has a malformed effective filter"
            )
        entity_filter = nested
        break
    if entity_filter is None:
        raise HomeKitLifecycleError(
            "A prunable HomeKit entry has no exact nested effective filter"
        )
    values = entity_filter.get("include_entities")
    if not isinstance(values, (list, tuple)) or len(values) != 1:
        raise HomeKitLifecycleError(
            "A prunable HomeKit entry must expose exactly one entity"
        )
    entity_id = values[0]
    if (
        not isinstance(entity_id, str)
        or entity_id != entity_id.strip()
        or ENTITY_ID_PATTERN.fullmatch(entity_id) is None
    ):
        raise HomeKitLifecycleError(
            "A prunable HomeKit entry contains an invalid entity ID"
        )
    for key in HOMEKIT_COMPETING_FILTER_KEYS:
        if key not in entity_filter:
            continue
        value = entity_filter[key]
        if not isinstance(value, (list, tuple)) or value:
            raise HomeKitLifecycleError(
                "A prunable HomeKit entry has competing filter rules"
            )
    return entity_id


def _entry_name_port(entry: Any) -> tuple[str, int]:
    """Read the immutable HomeKit network identity used for YAML matching."""
    data = getattr(entry, "data", {}) or {}
    if not isinstance(data, Mapping):
        raise HomeKitLifecycleError("A prunable HomeKit entry has invalid data")
    name = data.get("name")
    port = data.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise HomeKitLifecycleError("A prunable HomeKit entry has no exact port")
    if isinstance(name, str) and name.strip() and name == name.strip():
        return name, port
    if _entry_source(entry) == HOMEKIT_SOURCE_IMPORT:
        raise HomeKitLifecycleError("A prunable HomeKit entry has no exact name")

    # Home Assistant UI-created HomeKit Accessory entries observed in the live
    # registry can have an empty or non-canonical data.name while retaining the
    # exact immutable network identity in ConfigEntry.title. Imported entries
    # never use this fallback because YAML name matching must remain anchored to
    # the imported data itself.
    title = getattr(entry, "title", None)
    if not isinstance(title, str):
        raise HomeKitLifecycleError("A prunable HomeKit entry has no exact name")
    title_parts = title.rsplit(":", 1)
    if len(title_parts) != 2:
        raise HomeKitLifecycleError("A prunable HomeKit entry has no exact name")
    title_name, title_port = title_parts
    if (
        not title_name
        or title_name != title_name.strip()
        or title_port != str(port)
        or title != f"{title_name}:{port}"
    ):
        raise HomeKitLifecycleError("A prunable HomeKit entry has no exact name")
    return title_name, port


def _safe_relative_yaml_path(value: object) -> str:
    """Normalize a YAML path while rejecting absolute and parent traversal paths."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise HomeKitLifecycleError(
            "An imported HomeKit accessory requires a safe relative YAML path"
        )
    windows_path = PureWindowsPath(value)
    if "\x00" in value or windows_path.drive or windows_path.is_absolute():
        raise HomeKitLifecycleError("The HomeKit YAML path must be relative")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HomeKitLifecycleError("The HomeKit YAML path must stay below config")
    if path.suffix.casefold() not in {".yaml", ".yml"}:
        raise HomeKitLifecycleError("The HomeKit YAML path must name a YAML file")
    if path.name.casefold() in {"configuration.yaml", "configuration.yml"}:
        raise HomeKitLifecycleError(
            "The main Home Assistant configuration file cannot be used as a "
            "HomeKit accessory include"
        )
    return path.as_posix()


def _validate_candidate_identity(
    candidate: HomeKitAccessoryPruneCandidate,
) -> tuple[str, str | None, str, int, str, str | None]:
    """Validate the complete immutable identity used by the removal protocol.

    ``entry_id`` anchors the live Config Entry, ``yaml_relative_path`` anchors
    the imported source document, and name/port/entity anchor exactly one block
    inside that document.  No subset of this identity authorizes deletion.
    """
    if not isinstance(candidate, HomeKitAccessoryPruneCandidate):
        raise HomeKitLifecycleError(
            "The HomeKit prune plan contains an invalid candidate"
        )
    if (
        not isinstance(candidate.entry_id, str)
        or not candidate.entry_id.strip()
        or candidate.entry_id != candidate.entry_id.strip()
    ):
        raise HomeKitLifecycleError(
            "A HomeKit prune candidate has an invalid entry ID"
        )
    if (
        not isinstance(candidate.entity_id, str)
        or candidate.entity_id != candidate.entity_id.strip()
        or ENTITY_ID_PATTERN.fullmatch(candidate.entity_id) is None
    ):
        raise HomeKitLifecycleError(
            "A HomeKit prune candidate has an invalid entity ID"
        )
    if not isinstance(candidate.imported, bool):
        raise HomeKitLifecycleError(
            "A HomeKit prune candidate has an invalid ownership source"
        )
    if not isinstance(candidate.name, str) or not candidate.name:
        raise HomeKitLifecycleError("A HomeKit prune candidate has no exact name")
    if candidate.imported and (
        not candidate.name.strip() or candidate.name != candidate.name.strip()
    ):
        raise HomeKitLifecycleError("A HomeKit prune candidate has no exact name")
    if (
        isinstance(candidate.port, bool)
        or not isinstance(candidate.port, int)
        or not 1 <= candidate.port <= 65535
    ):
        raise HomeKitLifecycleError("A HomeKit prune candidate has no exact port")
    relative_path: str | None = None
    if candidate.mode is not None and candidate.mode not in HOMEKIT_VALID_MODES:
        raise HomeKitLifecycleError(
            "A HomeKit prune candidate has an invalid explicit mode"
        )
    if candidate.imported:
        if candidate.mode is None:
            raise HomeKitLifecycleError(
                "An imported HomeKit candidate requires an explicit mode"
            )
        relative_path = _safe_relative_yaml_path(candidate.yaml_relative_path)
        if relative_path != candidate.yaml_relative_path:
            raise HomeKitLifecycleError(
                "An imported HomeKit candidate has a non-canonical YAML path"
            )
    elif candidate.yaml_relative_path is not None:
        raise HomeKitLifecycleError(
            "A UI-managed HomeKit candidate cannot name an import YAML path"
        )
    return (
        candidate.entry_id,
        relative_path,
        candidate.name,
        candidate.port,
        candidate.entity_id,
        candidate.mode,
    )


def plan_homekit_accessory_prunes(
    entries: Iterable[Any],
    *,
    managed_entry_ids: Iterable[str],
    main_entry_id: str,
    homekit_source_entry_ids: Iterable[str],
    owned_entry_ids: Iterable[str],
    prunable_entry_ids: Iterable[str],
    logical_desired: Set[str],
    import_yaml_paths: Mapping[str, str] | None = None,
) -> tuple[HomeKitAccessoryPruneCandidate, ...]:
    """Build a fail-closed prune plan from explicit ownership and prune grants.

    A managed side entry is retained when its entity remains in the final logical
    HomeKit desired set. Entries outside ``prunable_entry_ids`` are never
    considered, even when they are single-entity accessories.
    """
    managed = _strict_id_set(managed_entry_ids, label="Managed HomeKit entry IDs")
    sources = _strict_id_set(
        homekit_source_entry_ids, label="HomeKit source entry IDs"
    )
    owned = _strict_id_set(owned_entry_ids, label="Owned HomeKit entry IDs")
    prunable = _strict_id_set(prunable_entry_ids, label="Prunable HomeKit entry IDs")
    if (
        not isinstance(main_entry_id, str)
        or not main_entry_id.strip()
        or main_entry_id != main_entry_id.strip()
    ):
        raise HomeKitLifecycleError("The managed HomeKit main Bridge is missing")
    if main_entry_id not in managed:
        raise HomeKitLifecycleError(
            "The HomeKit main Bridge is not in the explicit managed set"
        )
    if prunable - owned:
        raise HomeKitLifecycleError(
            "A prunable HomeKit entry is not explicitly owned by Platform Sync"
        )
    if prunable - managed:
        raise HomeKitLifecycleError("A prunable HomeKit entry is not managed")
    if main_entry_id in prunable:
        raise HomeKitLifecycleError("The HomeKit main Bridge cannot be pruned")
    if main_entry_id in sources:
        raise HomeKitLifecycleError(
            "The HomeKit main Bridge cannot also be a source entry"
        )
    if prunable & sources:
        raise HomeKitLifecycleError("A HomeKit source entry cannot be pruned")
    if not isinstance(logical_desired, Set) or isinstance(
        logical_desired, (str, bytes)
    ):
        raise HomeKitLifecycleError("The logical HomeKit desired set is invalid")
    desired = frozenset(logical_desired)
    if any(
        not isinstance(entity_id, str)
        or entity_id != entity_id.strip()
        or ENTITY_ID_PATTERN.fullmatch(entity_id) is None
        for entity_id in desired
    ):
        raise HomeKitLifecycleError(
            "The logical HomeKit desired set contains an invalid entity ID"
        )

    by_id: dict[str, Any] = {}
    for entry in entries:
        entry_id = getattr(entry, "entry_id", None)
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if entry_id in by_id:
            raise HomeKitLifecycleError("Duplicate live HomeKit Config Entry IDs")
        by_id[entry_id] = entry
    missing = prunable - set(by_id)
    if missing:
        raise HomeKitLifecycleError(
            "A prunable HomeKit Config Entry no longer exists; reconcile "
            "ownership first"
        )
    main_entry = by_id.get(main_entry_id)
    if main_entry is None or getattr(main_entry, "domain", None) != HOMEKIT_DOMAIN:
        raise HomeKitLifecycleError(
            "The explicit HomeKit main Bridge does not resolve to a live HomeKit entry"
        )

    yaml_paths = import_yaml_paths or {}
    candidates: list[HomeKitAccessoryPruneCandidate] = []
    seen_entities: set[str] = set()
    for entry_id in sorted(prunable):
        entry = by_id[entry_id]
        if getattr(entry, "domain", None) != HOMEKIT_DOMAIN:
            raise HomeKitLifecycleError(
                "A prunable entry is not a HomeKit Config Entry"
            )
        imported = _entry_source(entry) == HOMEKIT_SOURCE_IMPORT
        mode = _entry_mode(entry)
        # A singleton side entry can be a removable lifecycle unit in either
        # native HomeKit mode. Main/source IDs remain independently protected.
        # Imported entries additionally need an explicit mode so their exact
        # YAML source block can prove the same identity before removal.
        if imported and mode is None:
            raise HomeKitLifecycleError(
                "An imported HomeKit side entry has no explicit mode"
            )
        entity_id = _strict_single_entity(entry)
        if entity_id in desired:
            continue
        if entity_id in seen_entities:
            raise HomeKitLifecycleError(
                "Multiple prunable HomeKit accessories expose the same entity"
            )
        seen_entities.add(entity_id)
        name, port = _entry_name_port(entry)
        yaml_relative_path = None
        if imported:
            yaml_relative_path = _safe_relative_yaml_path(yaml_paths.get(entry_id))
        candidates.append(
            HomeKitAccessoryPruneCandidate(
                entry_id=entry_id,
                entity_id=entity_id,
                imported=imported,
                name=name,
                port=port,
                mode=mode,
                yaml_relative_path=yaml_relative_path,
            )
        )
    return tuple(candidates)


def _resolve_yaml_path(hass: HomeAssistant, relative_path: str) -> Path:
    """Resolve and recheck a relative YAML path against HA's config directory."""
    normalized = _safe_relative_yaml_path(relative_path)
    parts = PurePosixPath(normalized).parts
    root = Path(hass.config.path()).resolve()
    path = Path(hass.config.path(*parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise HomeKitLifecycleError("The HomeKit YAML path escaped config") from error
    if not path.is_file():
        raise HomeKitLifecycleError("The HomeKit YAML file does not exist")
    return path


def _yaml_block_identity(block: Any) -> tuple[str | None, int | None]:
    """Return a strict name/port identity without coercion."""
    if not isinstance(block, Mapping):
        return None, None
    name = block.get("name")
    port = block.get("port")
    return (
        name if isinstance(name, str) else None,
        port if isinstance(port, int) and not isinstance(port, bool) else None,
    )


def _yaml_block_mode(block: Any) -> str | None:
    """Return one unambiguous explicit HomeKit mode from a YAML block."""
    if not isinstance(block, Mapping):
        return None
    modes: list[str] = []
    for key in ("homekit_mode", "mode"):
        if key not in block:
            continue
        value = block.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.casefold()
        if normalized not in HOMEKIT_VALID_MODES:
            return None
        modes.append(normalized)
    if len(modes) != 1:
        return None
    return modes[0]


def _yaml_block_single_entity(block: Any) -> str | None:
    """Return an exact singleton include entity, or None for a non-exact block."""
    if not isinstance(block, Mapping):
        return None
    entity_filter = block.get("filter")
    if not isinstance(entity_filter, Mapping):
        return None
    values = entity_filter.get("include_entities")
    if not isinstance(values, (list, tuple)) or len(values) != 1:
        return None
    entity_id = values[0]
    if not isinstance(entity_id, str):
        return None
    return entity_id


def _validate_yaml_block(
    block: Any, candidate: HomeKitAccessoryPruneCandidate
) -> None:
    """Require an imported block to remain the exact accessory we planned."""
    if not isinstance(block, Mapping):
        raise HomeKitLifecycleError("The matched HomeKit YAML block is malformed")
    if _yaml_block_mode(block) != candidate.mode:
        raise HomeKitLifecycleError(
            "The matched HomeKit YAML block does not have the planned exact mode"
        )
    entity_filter = block.get("filter")
    if not isinstance(entity_filter, Mapping):
        raise HomeKitLifecycleError(
            "The matched HomeKit YAML block has no exact filter"
        )
    if _yaml_block_single_entity(block) != candidate.entity_id:
        raise HomeKitLifecycleError(
            "The matched HomeKit YAML block does not expose the planned entity"
        )
    for key in HOMEKIT_COMPETING_FILTER_KEYS:
        if key not in entity_filter:
            continue
        value = entity_filter[key]
        if not isinstance(value, (list, tuple)) or value:
            raise HomeKitLifecycleError(
                "The matched HomeKit YAML block has competing filters"
            )


def _updated_yaml_data(
    data: Any,
    candidates: Sequence[HomeKitAccessoryPruneCandidate],
    *,
    relative_path: str,
) -> tuple[Any, bool]:
    """Remove exact blocks while preserving the included YAML's root shape.

    An imported candidate is identified by its live Config Entry ID, this exact
    source path, and one unique YAML block with the planned name, port and
    entity.  The entry ID is deliberately not inferred from YAML because Home
    Assistant's import schema does not serialize it into the source block.
    """
    root_is_list = isinstance(data, list)
    if root_is_list:
        # ``homekit: !include homekit_accessories.yaml`` resolves an included
        # file whose root is the list of HomeKit configuration blocks.
        blocks = data
    elif isinstance(data, Mapping):
        # Also support a standalone configuration-shaped document without
        # ever converting it to the included-file shape (or vice versa).
        blocks = data.get(HOMEKIT_DOMAIN)
        if not isinstance(blocks, list):
            raise HomeKitLifecycleError(
                "The HomeKit YAML mapping must contain a HomeKit list"
            )
    else:
        raise HomeKitLifecycleError(
            "The HomeKit YAML root must be a list or configuration mapping"
        )

    remove_indices: set[int] = set()
    for candidate in candidates:
        if candidate.yaml_relative_path != relative_path:
            raise HomeKitLifecycleError(
                "An imported HomeKit candidate changed its YAML source path"
            )
        exact_matches = [
            index
            for index, block in enumerate(blocks)
            if _yaml_block_identity(block) == (candidate.name, candidate.port)
            and _yaml_block_single_entity(block) == candidate.entity_id
            and _yaml_block_mode(block) == candidate.mode
        ]
        related_matches = [
            index
            for index, block in enumerate(blocks)
            if _yaml_block_single_entity(block) == candidate.entity_id
            or _yaml_block_identity(block)[0] == candidate.name
            or _yaml_block_identity(block)[1] == candidate.port
        ]
        if not exact_matches:
            # An absent block is indistinguishable from a wrong-but-valid include
            # path or an out-of-band edit.  It may only become an idempotent retry
            # state once a future implementation supplies a durable two-phase
            # commit marker.  Until then, always fail closed before entry removal.
            raise HomeKitLifecycleError(
                "The imported HomeKit accessory has no exact YAML identity"
            )
        if len(exact_matches) != 1:
            raise HomeKitLifecycleError(
                "The imported HomeKit accessory has an ambiguous YAML identity"
            )
        index = exact_matches[0]
        if related_matches != [index]:
            raise HomeKitLifecycleError(
                "The imported HomeKit accessory has ambiguous related YAML blocks"
            )
        if index in remove_indices:
            raise HomeKitLifecycleError(
                "Multiple imported accessories matched one HomeKit YAML block"
            )
        _validate_yaml_block(blocks[index], candidate)
        remove_indices.add(index)

    if not remove_indices:
        # Only an empty candidate list can reach this state. Imported callers
        # with candidates must have exactly one removal index per candidate.
        return deepcopy(data), False
    updated = deepcopy(data)
    updated_blocks = updated if root_is_list else updated[HOMEKIT_DOMAIN]
    for index in sorted(remove_indices, reverse=True):
        del updated_blocks[index]
    return updated, True


def _next_backup_path(path: Path) -> Path:
    """Choose a unique sibling backup path without overwriting an older backup."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    nonce = secrets.token_hex(4)
    return path.with_name(f"{path.name}.platform-sync-homekit-{stamp}-{nonce}.bak")


def _write_exclusive(path: Path, data: bytes) -> None:
    """Write a backup without replacing any existing file."""
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_replace_bytes(
    path: Path, data: bytes, expected_current: bytes
) -> None:
    """Atomically replace one file only if its exact current bytes still match."""
    temporary = path.with_name(
        f".{path.name}.platform-sync-{secrets.token_hex(8)}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, temporary)
        if path.read_bytes() != expected_current:
            raise HomeKitLifecycleError(
                "HomeKit YAML changed before its atomic replacement"
            )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_save_yaml(
    path: Path, data: Any, expected_current: bytes
) -> None:
    """Serialize with HA's writer and atomically replace an unchanged source."""
    from homeassistant.util import yaml as yaml_util

    temporary = path.with_name(
        f".{path.name}.platform-sync-{secrets.token_hex(8)}.tmp"
    )
    try:
        yaml_util.save_yaml(str(temporary), data)
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        shutil.copymode(path, temporary)
        if path.read_bytes() != expected_current:
            raise HomeKitLifecycleError(
                "HomeKit YAML changed before its atomic lifecycle edit"
            )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


async def _load_yaml(hass: HomeAssistant, path: Path) -> Any:
    """Load YAML with Home Assistant's loader in the executor."""
    from homeassistant.util import yaml as yaml_util

    return await hass.async_add_executor_job(yaml_util.load_yaml, str(path))


async def _save_yaml(
    hass: HomeAssistant,
    path: Path,
    data: Any,
    *,
    expected_current: bytes,
) -> None:
    """Atomically save YAML and drain its worker before propagating cancel."""
    worker = asyncio.ensure_future(
        hass.async_add_executor_job(
            _atomic_save_yaml,
            path,
            data,
            expected_current,
        )
    )
    outcome = await _await_removal_settled(worker)
    if outcome.caller_cancellation is not None:
        # The worker has now settled, so the caller can safely restore the
        # staged file without a late executor replacement racing behind it.
        if outcome.error is not None:
            raise outcome.caller_cancellation from outcome.error
        raise outcome.caller_cancellation
    if outcome.error is not None:
        raise outcome.error


def _yaml_backup_relative_path(hass: HomeAssistant, edit: _YamlEdit) -> str:
    """Return one verified backup path relative to the HA config root."""
    if edit.backup_path is None:
        raise HomeKitLifecycleError("The HomeKit YAML edit has no backup")
    root = Path(hass.config.path()).resolve()
    try:
        return edit.backup_path.resolve().relative_to(root).as_posix()
    except ValueError as error:
        raise HomeKitLifecycleError(
            "The HomeKit YAML backup escaped the config directory"
        ) from error


async def _restore_yaml_edit(hass: HomeAssistant, edit: _YamlEdit) -> None:
    """Restore one uncommitted edit without overwriting concurrent changes."""
    current_bytes = await hass.async_add_executor_job(edit.path.read_bytes)
    if current_bytes == edit.original_bytes:
        return
    if edit.updated_bytes is not None:
        if current_bytes != edit.updated_bytes:
            raise HomeKitLifecycleError(
                "HomeKit YAML changed after the lifecycle edit; refusing rollback"
            )
    else:
        # A save may have completed immediately before cancellation/error. When
        # its exact bytes were not captured, accept only the exact parsed data
        # produced by this transaction before restoring the verified original.
        current_data = await _load_yaml(hass, edit.path)
        if current_data != edit.updated_data:
            raise HomeKitLifecycleError(
                "HomeKit YAML state is not owned by this lifecycle transaction"
            )
    await hass.async_add_executor_job(
        _atomic_replace_bytes,
        edit.path,
        edit.original_bytes,
        current_bytes,
    )
    restored = await hass.async_add_executor_job(edit.path.read_bytes)
    if restored != edit.original_bytes:
        raise HomeKitLifecycleError("HomeKit YAML rollback readback failed")


async def _prepare_import_yaml_removal(
    hass: HomeAssistant,
    candidate: HomeKitAccessoryPruneCandidate,
) -> tuple[_YamlEdit, str]:
    """Back up and stage exactly one imported accessory source removal."""
    if not candidate.imported or candidate.yaml_relative_path is None:
        raise HomeKitLifecycleError(
            "An imported HomeKit accessory has no safe relative YAML path"
        )
    relative_path = candidate.yaml_relative_path
    path = _resolve_yaml_path(hass, relative_path)
    original_bytes = await hass.async_add_executor_job(path.read_bytes)
    original_data = await _load_yaml(hass, path)
    updated_data, changed = _updated_yaml_data(
        original_data,
        [candidate],
        relative_path=relative_path,
    )
    if not changed:
        raise HomeKitLifecycleError(
            "The imported HomeKit accessory source did not change"
        )
    edit = _YamlEdit(
        path=path,
        relative_path=relative_path,
        original_bytes=original_bytes,
        updated_data=updated_data,
    )
    current_bytes = await hass.async_add_executor_job(path.read_bytes)
    if current_bytes != original_bytes:
        raise HomeKitLifecycleError(
            "A HomeKit YAML file changed while the prune was being prepared"
        )
    edit.backup_path = _next_backup_path(path)
    await hass.async_add_executor_job(
        _write_exclusive, edit.backup_path, edit.original_bytes
    )
    backup_path = _yaml_backup_relative_path(hass, edit)
    try:
        await _save_yaml(
            hass,
            path,
            updated_data,
            expected_current=original_bytes,
        )
        readback = await _load_yaml(hass, path)
        if readback != updated_data:
            raise HomeKitLifecycleError(
                "HomeKit YAML readback did not match the planned removal"
            )
        edit.updated_bytes = await hass.async_add_executor_job(path.read_bytes)
    except asyncio.CancelledError as error:
        rollback_error = await _settle_yaml_restore(hass, edit)
        if rollback_error is not None:
            raise HomeKitLifecycleCancelled(
                "HomeKit YAML preparation was cancelled and rollback failed",
                yaml_backup_paths=(backup_path,),
            ) from rollback_error
        raise HomeKitLifecycleCancelled(
            "HomeKit YAML preparation was cancelled and rolled back",
            yaml_backup_paths=(backup_path,),
        ) from error
    except Exception as error:
        rollback_error = await _settle_yaml_restore(hass, edit)
        if rollback_error is not None:
            raise HomeKitLifecycleError(
                "HomeKit YAML preparation and rollback failed",
                yaml_backup_paths=(backup_path,),
            ) from rollback_error
        raise HomeKitLifecycleError(
            "HomeKit YAML preparation failed and was rolled back",
            yaml_backup_paths=(backup_path,),
        ) from error
    return edit, backup_path


def _validate_live_candidate(
    entry: Any, candidate: HomeKitAccessoryPruneCandidate
) -> None:
    """Revalidate an entry immediately before the irreversible operation."""
    if getattr(entry, "domain", None) != HOMEKIT_DOMAIN:
        raise HomeKitLifecycleError("A prune candidate is no longer a HomeKit entry")
    imported = _entry_source(entry) == HOMEKIT_SOURCE_IMPORT
    if imported != candidate.imported:
        raise HomeKitLifecycleError("A prune candidate changed ownership source")
    if imported and _entry_mode(entry) != candidate.mode:
        raise HomeKitLifecycleError(
            "An imported prune candidate changed its explicit mode"
        )
    if _strict_single_entity(entry) != candidate.entity_id:
        raise HomeKitLifecycleError(
            "A prune candidate no longer exposes the planned entity"
        )
    name, port = _entry_name_port(entry)
    if (name, port) != (candidate.name, candidate.port):
        raise HomeKitLifecycleError(
            "A prune candidate changed its HomeKit network identity"
        )


async def _await_removal_settled(task: asyncio.Future[Any]) -> _RemovalOutcome:
    """Settle a shielded operation and retain outer cancellation separately."""
    try:
        return _RemovalOutcome(response=await asyncio.shield(task))
    except Exception as error:
        return _RemovalOutcome(error=error)
    except asyncio.CancelledError as cancellation:
        current = asyncio.current_task()
        caller_cancelled = current is not None and current.cancelling() > 0
        if not caller_cancelled:
            # The inner operation itself was cancelled. There is no outer
            # cancellation to defer and no response whose flags can be retained.
            raise
        # ConfigEntries.async_remove removes the live entry before awaiting the
        # integration's cleanup hook. Interrupting that await can leave memory
        # and storage inconsistent. Drain the inner task before propagating the
        # caller's cancellation. Repeated cancellation requests are also drained.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                # The settled error is retrieved below together with the
                # deferred caller cancellation.
                break
        if task.cancelled():
            return _RemovalOutcome(
                error=asyncio.CancelledError(),
                caller_cancellation=cancellation,
            )
        try:
            return _RemovalOutcome(
                response=task.result(),
                caller_cancellation=cancellation,
            )
        except BaseException as error:
            # Return the settled error so the caller can first read back whether
            # the entry was removed and preserve all earlier restart flags.
            return _RemovalOutcome(
                error=error,
                caller_cancellation=cancellation,
            )


async def _settle_yaml_restore(
    hass: HomeAssistant, edit: _YamlEdit | None
) -> BaseException | None:
    """Finish a staged YAML rollback even if the owner is being cancelled."""
    if edit is None:
        return None
    task = asyncio.create_task(
        _restore_yaml_edit(hass, edit),
        name=f"platform_sync restore HomeKit YAML {edit.relative_path}",
    )
    try:
        outcome = await _await_removal_settled(task)
    except BaseException as error:
        return error
    return outcome.error


async def async_remove_homekit_accessory_candidates(
    hass: HomeAssistant,
    candidates: Sequence[HomeKitAccessoryPruneCandidate],
    *,
    owned_entry_ids: Iterable[str],
    prunable_entry_ids: Iterable[str],
) -> HomeKitAccessoryPruneResult:
    """Remove validated owned accessories after durable YAML convergence.

    Each imported candidate is its own recoverable unit: its exact YAML block
    is backed up and staged immediately before Config Entry removal, then kept
    removed only after ``async_remove`` returns normally and absence is read
    back. Failure or cancellation restores that candidate's block while earlier
    committed candidates remain removed.

    Live absence is never inferred as prior success. Callers must durably apply
    ``removed_entry_ids`` after each result/error/cancellation and retain every
    ``uncertain_entry_ids`` ownership grant until a later reconciliation proves
    the persisted Config Entry state.
    """
    owned = _strict_id_set(owned_entry_ids, label="Owned HomeKit entry IDs")
    prunable = _strict_id_set(prunable_entry_ids, label="Prunable HomeKit entry IDs")
    candidate_identities = [
        _validate_candidate_identity(candidate) for candidate in candidates
    ]
    if len(candidate_identities) != len(set(candidate_identities)):
        raise HomeKitLifecycleError(
            "The HomeKit prune plan has duplicate complete identities"
        )
    candidate_ids = [candidate.entry_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise HomeKitLifecycleError("The HomeKit prune plan has duplicate entry IDs")
    if set(candidate_ids) - owned or set(candidate_ids) - prunable:
        raise HomeKitLifecycleError(
            "The HomeKit prune plan exceeds its explicit ownership grant"
        )
    candidate_entities = [candidate.entity_id for candidate in candidates]
    if len(candidate_entities) != len(set(candidate_entities)):
        raise HomeKitLifecycleError("The HomeKit prune plan has duplicate entities")

    removed_ids: set[str] = set()
    removed_entities: set[str] = set()
    already_absent: set[str] = set()
    restart_required: set[str] = set()
    uncertain_ids: set[str] = set()
    backups: list[str] = []

    # Validate every live identity before changing any import source file.
    # Absence alone is never proof of success: async_remove can remove an entry
    # from memory and then fail its unload hook or persistent save.
    for candidate in candidates:
        entry = hass.config_entries.async_get_entry(candidate.entry_id)
        if entry is None:
            uncertain_ids.add(candidate.entry_id)
            raise HomeKitLifecycleError(
                "A HomeKit candidate is absent without a confirmed removal",
                uncertain_entry_ids=uncertain_ids,
            )
        try:
            _validate_live_candidate(entry, candidate)
        except HomeKitLifecycleError as error:
            raise HomeKitLifecycleError(str(error)) from error

    for candidate in candidates:
        staged_edit: _YamlEdit | None = None
        entry = hass.config_entries.async_get_entry(candidate.entry_id)
        if entry is None:
            uncertain_ids.add(candidate.entry_id)
            raise HomeKitLifecycleError(
                "A HomeKit candidate disappeared before its removal began",
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            )
        try:
            _validate_live_candidate(entry, candidate)
        except HomeKitLifecycleError as error:
            raise HomeKitLifecycleError(
                str(error),
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            ) from error

        if candidate.imported:
            try:
                staged_edit, backup_path = await _prepare_import_yaml_removal(
                    hass, candidate
                )
                backups.append(backup_path)
            except HomeKitLifecycleCancelled as error:
                merged_backups = tuple(
                    dict.fromkeys([*backups, *error.yaml_backup_paths])
                )
                raise HomeKitLifecycleCancelled(
                    str(error),
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=merged_backups,
                ) from error
            except HomeKitLifecycleError as error:
                merged_backups = tuple(
                    dict.fromkeys([*backups, *error.yaml_backup_paths])
                )
                raise HomeKitLifecycleError(
                    str(error),
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=merged_backups,
                ) from error
            except asyncio.CancelledError as error:
                raise HomeKitLifecycleCancelled(
                    "HomeKit lifecycle cancelled while preparing imported YAML",
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from error
            except Exception as error:
                raise HomeKitLifecycleError(
                    "HomeKit imported YAML preparation failed",
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from error

            # Close the race between the initial preflight and YAML staging.
            entry = hass.config_entries.async_get_entry(candidate.entry_id)
            if entry is None:
                uncertain_ids.add(candidate.entry_id)
                rollback_error = await _settle_yaml_restore(hass, staged_edit)
                message = "An imported HomeKit candidate disappeared before removal"
                if rollback_error is not None:
                    message += "; YAML rollback also failed"
                raise HomeKitLifecycleError(
                    message,
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from rollback_error
            try:
                _validate_live_candidate(entry, candidate)
            except HomeKitLifecycleError as error:
                rollback_error = await _settle_yaml_restore(hass, staged_edit)
                if rollback_error is not None:
                    uncertain_ids.add(candidate.entry_id)
                    raise HomeKitLifecycleError(
                        "Imported HomeKit identity changed and YAML rollback failed",
                        removed_entry_ids=removed_ids,
                        removed_entities=removed_entities,
                        already_absent_entry_ids=already_absent,
                        restart_required_entry_ids=restart_required,
                        uncertain_entry_ids=uncertain_ids,
                        yaml_backup_paths=backups,
                    ) from rollback_error
                raise HomeKitLifecycleError(
                    str(error),
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from error

        task = asyncio.create_task(
            hass.config_entries.async_remove(candidate.entry_id),
            name=f"platform_sync remove owned HomeKit accessory {candidate.entry_id}",
        )
        try:
            outcome = await _await_removal_settled(task)
        except asyncio.CancelledError as error:
            # The inner async_remove itself was cancelled. Its in-memory absence
            # cannot prove that unload hooks and persistent storage committed.
            uncertain_ids.add(candidate.entry_id)
            rollback_error = await _settle_yaml_restore(hass, staged_edit)
            message = "HomeKit Config Entry removal was cancelled and is uncertain"
            if rollback_error is not None:
                message += "; YAML rollback also failed"
            raise HomeKitLifecycleCancelled(
                message,
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            ) from (rollback_error or error)
        if outcome.error is not None:
            uncertain_ids.add(candidate.entry_id)
            rollback_error = await _settle_yaml_restore(hass, staged_edit)
            if outcome.caller_cancellation is not None:
                message = "HomeKit lifecycle cancelled after an uncertain removal"
                if rollback_error is not None:
                    message += "; YAML rollback also failed"
                raise HomeKitLifecycleCancelled(
                    message,
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from (rollback_error or outcome.error)
            message = "Owned HomeKit accessory removal failed and is uncertain"
            if rollback_error is not None:
                message += "; YAML rollback also failed"
            raise HomeKitLifecycleError(
                message,
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            ) from (rollback_error or outcome.error)
        if (
            isinstance(outcome.response, Mapping)
            and outcome.response.get("require_restart") is True
        ):
            # Preserve the restart instruction even if subsequent exact
            # absence readback contradicts the otherwise normal return.
            restart_required.add(candidate.entry_id)
        if hass.config_entries.async_get_entry(candidate.entry_id) is not None:
            uncertain_ids.add(candidate.entry_id)
            rollback_error = await _settle_yaml_restore(hass, staged_edit)
            if outcome.caller_cancellation is not None:
                message = "HomeKit lifecycle cancelled after removal readback failed"
                if rollback_error is not None:
                    message += "; YAML rollback also failed"
                raise HomeKitLifecycleCancelled(
                    message,
                    removed_entry_ids=removed_ids,
                    removed_entities=removed_entities,
                    already_absent_entry_ids=already_absent,
                    restart_required_entry_ids=restart_required,
                    uncertain_entry_ids=uncertain_ids,
                    yaml_backup_paths=backups,
                ) from rollback_error
            message = "HomeKit Config Entry removal could not be read back"
            if rollback_error is not None:
                message += "; YAML rollback also failed"
            raise HomeKitLifecycleError(
                message,
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            ) from rollback_error

        # Only a normal async_remove return followed by exact absence readback is
        # a committed removal. Exceptions/cancellation never enter these sets.
        removed_ids.add(candidate.entry_id)
        removed_entities.add(candidate.entity_id)
        if outcome.caller_cancellation is not None:
            raise HomeKitLifecycleCancelled(
                "HomeKit lifecycle cancelled after the removal settled",
                removed_entry_ids=removed_ids,
                removed_entities=removed_entities,
                already_absent_entry_ids=already_absent,
                restart_required_entry_ids=restart_required,
                uncertain_entry_ids=uncertain_ids,
                yaml_backup_paths=backups,
            ) from outcome.caller_cancellation

    return HomeKitAccessoryPruneResult(
        removed_entry_ids=frozenset(removed_ids),
        removed_entities=frozenset(removed_entities),
        already_absent_entry_ids=frozenset(already_absent),
        restart_required_entry_ids=frozenset(restart_required),
        uncertain_entry_ids=frozenset(uncertain_ids),
        yaml_backup_paths=tuple(backups),
    )
