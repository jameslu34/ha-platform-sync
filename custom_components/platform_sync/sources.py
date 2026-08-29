"""Read exact entity sets from supported sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
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
            entity_id = value.get("entity")
            if isinstance(entity_id, str) and "." in entity_id and entity_id not in ordered:
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
            for key in ("cards", "sections", "badges"):
                if isinstance(value.get(key), list):
                    walk_list(value[key], current_room)
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
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, Mapping):
        dashboards = lovelace.get("dashboards")
    if not isinstance(dashboards, Mapping):
        raise RuntimeError("Lovelace dashboards are not loaded")
    instance = _select_dashboard_instance(dashboards, dashboard)
    if instance is None:
        raise ValueError(f"Lovelace dashboard not found: {dashboard}")
    config = await instance.async_load(False)
    return extract_dashboard_entities(config, view)


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
    for dashboard, view in selected:
        snapshot = await async_read_dashboard_source(hass, dashboard, view)
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
