"""Configuration helpers for Platform Sync."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from .const import (
    ALL_TARGETS,
    CONF_ENABLED,
    CONF_GOOGLE_CONFIG_PATH,
    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
    CONF_HOMEKIT_SOURCE_ENTRY_IDS,
    CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION,
    CONF_LOCKED_RULES,
    CONF_MATTER_HOST,
    CONF_MATTER_PASSWORD,
    CONF_MATTER_PORT,
    CONF_SOURCE_DASHBOARD,
    CONF_SOURCE_ENTITIES,
    CONF_SOURCE_KIND,
    CONF_SOURCE_PAGES,
    CONF_SOURCE_VIEW,
    CONF_TARGET_PLATFORMS,
    CONF_USER_RULES,
    DEFAULT_ENABLED,
    DEFAULT_GOOGLE_CONFIG_PATH,
    DEFAULT_MATTER_HOST,
    DEFAULT_MATTER_PASSWORD,
    DEFAULT_MATTER_PORT,
    DEFAULT_SOURCE_DASHBOARD,
    DEFAULT_SOURCE_VIEW,
    SourceKind,
    TargetPlatform,
)
from .models import PlatformRule, normalize_entities, parse_rules


@dataclass(frozen=True, slots=True)
class SyncConfig:
    """Validated runtime configuration."""

    enabled: bool
    source_kind: SourceKind
    source_dashboard: str
    source_view: str
    source_pages: tuple[tuple[str, str], ...]
    source_entities: frozenset[str]
    targets: frozenset[TargetPlatform]
    matter_host: str
    matter_port: int
    matter_password: str = field(repr=False)
    google_config_path: str
    homekit_source_entry_ids: tuple[str, ...]
    homekit_managed_entry_ids: tuple[str, ...]
    user_rules: Mapping[TargetPlatform, PlatformRule]
    locked_rules: Mapping[TargetPlatform, PlatformRule]
    locked_homekit_apple_tv_exclusion: bool = False

    @classmethod
    def from_entry(cls, data: Mapping[str, Any], options: Mapping[str, Any]) -> "SyncConfig":
        """Merge immutable policy data with user-editable options."""
        merged = merge_entry_settings(data, options)
        source = SourceKind(merged.get(CONF_SOURCE_KIND, SourceKind.DASHBOARD))
        raw_targets = merged.get(CONF_TARGET_PLATFORMS, [item.value for item in ALL_TARGETS])
        targets = frozenset(TargetPlatform(item) for item in raw_targets)
        if not targets:
            raise ValueError("At least one target platform is required")
        locked_rules = parse_rules(data.get(CONF_LOCKED_RULES))
        source_dashboard = str(
            merged.get(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)
        ).strip() or DEFAULT_SOURCE_DASHBOARD
        source_view = str(
            merged.get(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)
        ).strip() or DEFAULT_SOURCE_VIEW
        source_pages = normalize_dashboard_pages(
            merged.get(CONF_SOURCE_PAGES),
            fallback_dashboard=source_dashboard,
            fallback_view=source_view,
            allow_fallback=CONF_SOURCE_PAGES not in merged,
        )
        source_dashboard, source_view = source_pages[0]
        enabled = bool(merged.get(CONF_ENABLED, DEFAULT_ENABLED))
        homekit_source_entry_ids = normalize_config_entry_ids(
            merged.get(CONF_HOMEKIT_SOURCE_ENTRY_IDS, []),
            required=enabled and source is SourceKind.HOMEKIT,
        )
        return cls(
            enabled=enabled,
            source_kind=source,
            source_dashboard=source_dashboard,
            source_view=source_view,
            source_pages=source_pages,
            source_entities=normalize_entities(merged.get(CONF_SOURCE_ENTITIES, [])),
            targets=targets,
            matter_host=str(merged.get(CONF_MATTER_HOST, DEFAULT_MATTER_HOST)),
            matter_port=int(merged.get(CONF_MATTER_PORT, DEFAULT_MATTER_PORT)),
            matter_password=str(
                merged.get(CONF_MATTER_PASSWORD, DEFAULT_MATTER_PASSWORD)
            ),
            google_config_path=str(merged.get(CONF_GOOGLE_CONFIG_PATH, DEFAULT_GOOGLE_CONFIG_PATH)),
            homekit_source_entry_ids=homekit_source_entry_ids,
            homekit_managed_entry_ids=normalize_config_entry_ids(
                merged.get(CONF_HOMEKIT_MANAGED_ENTRY_IDS, [])
            ),
            user_rules=parse_rules(merged.get(CONF_USER_RULES)),
            locked_rules=locked_rules,
            locked_homekit_apple_tv_exclusion=bool(
                data.get(CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION, False)
            ),
        )


def merge_entry_settings(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the effective complete settings without losing partial rules.

    Home Assistant replaces an Options Flow payload as one complete object.
    Older releases and hand-edited entries can nevertheless contain only part
    of the nested ``user_rules`` mapping in ``options``.  A shallow ``dict``
    update would then erase the other platforms that still exist in ``data``.
    Merge each platform and operation by presence so an explicit empty list
    clears a rule, while an absent key inherits the stored value.
    """
    merged = deepcopy(dict(data))
    for key, value in options.items():
        if key != CONF_USER_RULES:
            merged[key] = deepcopy(value)

    data_rules = data.get(CONF_USER_RULES)
    option_rules = options.get(CONF_USER_RULES)
    data_mapping = data_rules if isinstance(data_rules, Mapping) else {}
    option_mapping = option_rules if isinstance(option_rules, Mapping) else {}
    rules: dict[str, dict[str, list[str]]] = {}
    for platform in TargetPlatform:
        data_platform = data_mapping.get(platform.value)
        option_platform = option_mapping.get(platform.value)
        data_platform_mapping = (
            data_platform if isinstance(data_platform, Mapping) else {}
        )
        option_platform_mapping = (
            option_platform if isinstance(option_platform, Mapping) else {}
        )
        rules[platform.value] = {}
        for operation in ("include", "exclude"):
            if operation in option_platform_mapping:
                raw = option_platform_mapping[operation]
            elif operation in data_platform_mapping:
                raw = data_platform_mapping[operation]
            else:
                raw = []
            rules[platform.value][operation] = sorted(normalize_entities(raw))
    merged[CONF_USER_RULES] = rules
    return merged


def normalize_config_entry_ids(
    value: object, *, required: bool = False
) -> tuple[str, ...]:
    """Return unique non-empty Config Entry IDs without accepting malformed data."""
    if value is None:
        values: list[object] = []
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise ValueError("Config Entry IDs must be a list or tuple")

    result: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Config Entry IDs must be non-empty strings")
        entry_id = item.strip()
        if entry_id not in result:
            result.append(entry_id)
    if required and not result:
        raise ValueError("At least one HomeKit source Config Entry is required")
    return tuple(result)


def normalize_dashboard_pages(
    value: object,
    *,
    fallback_dashboard: str = DEFAULT_SOURCE_DASHBOARD,
    fallback_view: str = DEFAULT_SOURCE_VIEW,
    allow_fallback: bool = True,
) -> tuple[tuple[str, str], ...]:
    """Return unique dashboard/view pairs while preserving configured order."""
    pages: list[tuple[str, str]] = []
    invalid_item = False
    if isinstance(value, (list, tuple)):
        for item in value:
            dashboard = ""
            view = ""
            if isinstance(item, Mapping):
                dashboard = str(item.get("dashboard", "")).strip()
                view = str(item.get("view", "")).strip()
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                dashboard = str(item[0]).strip()
                view = str(item[1]).strip()
            pair = (dashboard, view)
            if dashboard and view and pair not in pages:
                pages.append(pair)
            elif not dashboard or not view:
                invalid_item = True
    elif value is not None:
        invalid_item = True
    if pages and (allow_fallback or not invalid_item):
        return tuple(pages)
    if not allow_fallback:
        raise ValueError("At least one valid dashboard page is required")
    dashboard = str(fallback_dashboard).strip() or DEFAULT_SOURCE_DASHBOARD
    view = str(fallback_view).strip() or DEFAULT_SOURCE_VIEW
    return ((dashboard, view),)
