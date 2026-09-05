"""Read exact entity sets from supported sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .config import SyncConfig
from .const import SourceKind, TargetPlatform
from .models import SourceSnapshot, normalize_entities


class EmptyDashboardSourceError(RuntimeError):
    """Raised when selected dashboard views contain no entities."""


def extract_dashboard_entities(config: Mapping[str, Any], view_path: str) -> SourceSnapshot:
    """Extract entity ids and room headings from a Lovelace view."""
    views = config.get("views", [])
    view = next(
        (
            item
            for item in views
            if isinstance(item, Mapping)
            and str(item.get("path") or item.get("title", "")) == view_path
        ),
        None,
    )
    if not isinstance(view, Mapping):
        raise ValueError(f"Lovelace view not found: {view_path}")

    ordered: list[str] = []
    rooms: dict[str, str] = {}

    def walk_list(values: list[Any], room: str) -> None:
        current_room = room
        for item in values:
            if isinstance(item, Mapping) and item.get("type") == "heading" and isinstance(item.get("heading"), str):
                current_room = item["heading"].strip()
                walk(item, current_room)
            else:
                walk(item, current_room)

    def walk(value: Any, room: str = "") -> None:
        if isinstance(value, Mapping):
            current_room = str(value.get("title", room)).strip() if value.get("title") else room
            if value.get("type") == "heading" and isinstance(value.get("heading"), str):
                current_room = value["heading"].strip()
            for key, entity_id in value.items():
                if not (
                    key == "entity"
                    or key == "camera_image"
                    or key.endswith("_entity")
                ):
                    continue
                if (
                    isinstance(entity_id, str)
                    and "." in entity_id
                    and " " not in entity_id
                    and entity_id not in ordered
                ):
                    ordered.append(entity_id)
                    if current_room:
                        rooms[entity_id] = current_room
            entities = value.get("entities")
            if isinstance(entities, list):
                for item in entities:
                    if isinstance(item, str):
                        walk({"entity": item}, current_room)
                    else:
                        walk(item, current_room)
            # Traverse presentation containers, but intentionally ignore
            # visibility/condition/action mappings: entities used only to gate
            # or operate a card are not devices displayed by the dashboard.
            for key in (
                "cards",
                "sections",
                "badges",
                "elements",
                "chips",
                "rows",
                "features",
                "card",
                "header",
                "footer",
            ):
                nested = value.get(key)
                if isinstance(nested, list):
                    walk_list(nested, current_room)
                elif isinstance(nested, Mapping):
                    walk(nested, current_room)
        elif isinstance(value, list):
            walk_list(value, room)

    walk(view)
    revision = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return SourceSnapshot(frozenset(ordered), rooms, revision)


def _select_dashboard_instance(
    dashboards: Mapping[str | None, Any], dashboard: str
) -> Any | None:
    """Prefer HA's named dashboard and retain the legacy default fallback."""
    instance = dashboards.get(dashboard)
    if instance is None and dashboard == "lovelace":
        instance = dashboards.get(None)
    return instance


async def async_read_dashboard_source(
    hass: HomeAssistant, dashboard: str, view: str
) -> SourceSnapshot:
    config = await _async_read_dashboard_config(hass, dashboard)
    return extract_dashboard_entities(config, view)


async def _async_read_dashboard_config(
    hass: HomeAssistant, dashboard: str
) -> Mapping[str, Any]:
    """Load one named dashboard for one or more selected views."""
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, Mapping):
        dashboards = lovelace.get("dashboards")
    if not isinstance(dashboards, Mapping):
        raise RuntimeError("Lovelace dashboards are not loaded")
    instance = _select_dashboard_instance(dashboards, dashboard)
    if instance is None:
        raise ValueError(f"Lovelace dashboard not found: {dashboard}")
    return await _async_load_dashboard_config(hass, instance)


def _load_storage_dashboard(path: str) -> Mapping[str, Any]:
    """Load one Lovelace storage document directly from disk."""
    with Path(path).open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, Mapping):
        raise RuntimeError("Lovelace storage document is not a mapping")
    data = document.get("data")
    config = data.get("config") if isinstance(data, Mapping) else None
    if not isinstance(config, Mapping):
        raise RuntimeError("Lovelace storage document has no usable config")
    return config


async def _async_load_dashboard_config(
    hass: HomeAssistant, instance: Any
) -> Mapping[str, Any]:
    """Read storage dashboards fresh; use the native loader for YAML mode.

    Home Assistant 2026.9 accepts a ``force`` argument for
    ``LovelaceStorage.async_load`` but ignores it and returns ``_data`` when the
    dashboard is already cached. Reading the Core-internal storage key directly
    keeps the missed-event audit independent from that in-memory cache.
    """
    if getattr(instance, "mode", None) != "storage":
        return await instance.async_load(False)

    try:
        from homeassistant.components.lovelace.dashboard import (
            CONFIG_STORAGE_KEY,
            CONFIG_STORAGE_KEY_DEFAULT,
        )
    except (ImportError, AttributeError):
        raise RuntimeError("Lovelace storage key API is unavailable") from None

    instance_config = getattr(instance, "config", None)
    if instance_config is None:
        storage_key = CONFIG_STORAGE_KEY_DEFAULT
    elif isinstance(instance_config, Mapping) and isinstance(
        instance_config.get("id"), str
    ):
        storage_key = CONFIG_STORAGE_KEY.format(instance_config["id"])
    else:
        raise RuntimeError("Lovelace storage dashboard identity is unreadable")
    storage_path = hass.config.path(".storage", storage_key)
    return await hass.async_add_executor_job(_load_storage_dashboard, storage_path)


async def async_read_dashboard_sources(
    hass: HomeAssistant, pages: Iterable[tuple[str, str]]
) -> SourceSnapshot:
    """Read multiple dashboard views as one deterministic, de-duplicated source."""
    selected = tuple(pages)
    if not selected:
        raise ValueError("At least one Lovelace dashboard page is required")

    entities: set[str] = set()
    rooms: dict[str, str] = {}
    room_conflicts: set[str] = set()
    revisions: list[dict[str, str]] = []
    dashboard_configs: dict[str, Mapping[str, Any]] = {}
    for dashboard, view in selected:
        if dashboard not in dashboard_configs:
            dashboard_configs[dashboard] = await _async_read_dashboard_config(
                hass, dashboard
            )
        snapshot = extract_dashboard_entities(dashboard_configs[dashboard], view)
        entities.update(snapshot.entities)
        # Keep room metadata only when every selected page agrees. Conflicting
        # headings must not cause an arbitrary Google Home room reassignment.
        for entity_id, room in snapshot.rooms.items():
            if not room or entity_id in room_conflicts:
                continue
            existing = rooms.get(entity_id)
            if existing is None:
                rooms[entity_id] = room
            elif existing != room:
                rooms.pop(entity_id, None)
                room_conflicts.add(entity_id)
        revisions.append(
            {
                "dashboard": dashboard,
                "view": view,
                "revision": snapshot.source_revision,
            }
        )
    if not entities:
        raise EmptyDashboardSourceError(
            "Selected Lovelace dashboard pages contain no entities"
        )
    revision = json.dumps(
        revisions,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return SourceSnapshot(frozenset(entities), rooms, revision)


async def async_read_source(hass: HomeAssistant, config: SyncConfig) -> SourceSnapshot:
    """Read the configured authoritative source."""
    if config.source_kind is SourceKind.DASHBOARD:
        return await async_read_dashboard_sources(hass, config.source_pages)
    if config.source_kind is SourceKind.MANUAL:
        return SourceSnapshot(config.source_entities, source_revision="manual")
    platform = TargetPlatform(config.source_kind.value)
    from .targets import async_read_platform_source, async_validate_target

    entities = await async_read_platform_source(hass, config, platform)
    if platform is TargetPlatform.MATTER:
        await async_validate_target(hass, config, platform, entities)
    return SourceSnapshot(entities, source_revision=platform.value)


async def async_find_apple_tv_entities(hass: HomeAssistant) -> frozenset[str]:
    """Identify Apple TV entities from config-entry, device and entity provenance."""
    apple_entry_ids = {
        entry.entry_id for entry in hass.config_entries.async_entries("apple_tv")
    }
    device_registry = dr.async_get(hass)
    apple_device_ids = {
        device.id
        for device in device_registry.devices.values()
        if set(getattr(device, "config_entries", ())) & apple_entry_ids
    }
    registry = er.async_get(hass)
    return frozenset(
        entity.entity_id
        for entity in registry.entities.values()
        if entity.config_entry_id in apple_entry_ids
        or entity.device_id in apple_device_ids
    )
