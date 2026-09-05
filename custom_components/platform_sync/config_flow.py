"""Conditional UI configuration for Cross-Platform Device Sync."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
import json
import logging
from pathlib import PurePosixPath
from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .config import (
    SyncConfig,
    merge_entry_settings,
    normalize_config_entry_ids,
    normalize_optional_config_entry_id,
    normalize_dashboard_pages,
)
from .const import (
    ALL_TARGETS,
    CONF_ENABLED,
    CONF_GOOGLE_CONFIG_PATH,
    CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
    CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
    CONF_HOMEKIT_MAIN_ENTRY_ID,
    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
    CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS,
    CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS,
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
    DEFAULT_HOMEKIT_ACCESSORY_CONFIG_PATH,
    DEFAULT_MATTER_HOST,
    DEFAULT_MATTER_PASSWORD,
    DEFAULT_MATTER_PORT,
    DEFAULT_ENTRY_TITLE_EN,
    DEFAULT_ENTRY_TITLE_ZH_HANT,
    DEFAULT_SOURCE_DASHBOARD,
    DEFAULT_SOURCE_VIEW,
    DOMAIN,
    SourceKind,
    TargetPlatform,
)
from .models import evaluate_target, normalize_entities, parse_rules
from .homekit_pairing import homekit_entry_entities, homekit_entry_is_paired
from .sources import (
    EmptyDashboardSourceError,
    async_find_apple_tv_entities,
    async_read_dashboard_source,
    async_read_dashboard_sources,
)
from .targets import (
    EmptyHomeKitSourceError,
    HomeKitSourceEntryMissingError,
    HomeKitSourceEntryUnavailableError,
    HomeKitSourceFilterUnsupportedError,
    async_validate_homekit_source_entries,
    homekit_managed_main_entry_id,
    homekit_new_accessory_mode_entities,
    validate_target_configuration,
)

_LOGGER = logging.getLogger(__name__)

CONF_SOURCE_PAGE = "source_page"
MANUAL_DASHBOARD_PAGE = "__manual_dashboard_path__"

_EDITABLE_KEYS = {
    CONF_ENABLED,
    CONF_SOURCE_KIND,
    CONF_SOURCE_DASHBOARD,
    CONF_SOURCE_VIEW,
    CONF_SOURCE_PAGES,
    CONF_SOURCE_ENTITIES,
    CONF_TARGET_PLATFORMS,
    CONF_MATTER_HOST,
    CONF_MATTER_PORT,
    CONF_MATTER_PASSWORD,
    CONF_GOOGLE_CONFIG_PATH,
    CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
    CONF_HOMEKIT_MAIN_ENTRY_ID,
    CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
    CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS,
    CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS,
    CONF_HOMEKIT_SOURCE_ENTRY_IDS,
    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
}


def _is_zh_hant(hass: Any) -> bool:
    """Return whether the Home Assistant system language is Traditional Chinese."""
    language = (
        str(getattr(hass.config, "language", "en"))
        .casefold()
        .replace("_", "-")
    )
    return language in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"} or language.startswith(
        "zh-hant-"
    )


def _default_entry_title(hass: Any) -> str:
    return DEFAULT_ENTRY_TITLE_ZH_HANT if _is_zh_hant(hass) else DEFAULT_ENTRY_TITLE_EN


def _homekit_mode(entry: Any) -> str:
    """Return the HomeKit entry mode used for an unambiguous UI label."""
    for source in (
        getattr(entry, "options", {}) or {},
        getattr(entry, "data", {}) or {},
    ):
        if not isinstance(source, Mapping):
            continue
        mode = source.get("homekit_mode", source.get("mode"))
        if isinstance(mode, str) and mode:
            return mode.casefold()
    return "bridge"


def _config_entry_source(entry: Any) -> str:
    source = getattr(entry, "source", None)
    return str(getattr(source, "value", source or "")).casefold()


def _homekit_choices(
    hass: Any, configured_entry_ids: Iterable[str] = ()
) -> list[dict[str, str]]:
    """Build a live HomeKit-entry multi-select without adopting future entries."""
    choices = {}
    for entry in hass.config_entries.async_entries("homekit"):
        mode = "Accessory" if _homekit_mode(entry) == "accessory" else "Bridge"
        choices[entry.entry_id] = (
            f"{entry.title} — {mode} ({entry.entry_id[:8]})"
        )
    for entry_id in configured_entry_ids:
        choices.setdefault(str(entry_id), str(entry_id))
    return [
        {"value": entry_id, "label": label}
        for entry_id, label in sorted(choices.items(), key=lambda item: item[1])
    ]


def _lovelace_dashboards(hass: Any) -> Mapping[str | None, Any] | None:
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, Mapping):
        dashboards = lovelace.get("dashboards")
    return dashboards if isinstance(dashboards, Mapping) else None


def _dashboard_page_token(dashboard: str, view: str) -> str:
    """Encode one dashboard/view pair as a stable selector value."""
    return json.dumps([dashboard, view], ensure_ascii=False, separators=(",", ":"))


def _serialize_dashboard_pages(
    pages: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> list[dict[str, str]]:
    """Serialize selected dashboard pages for Config Entry storage."""
    return [
        {"dashboard": dashboard, "view": view}
        for dashboard, view in pages
    ]


async def _dashboard_page_choices(
    hass: Any,
) -> tuple[list[dict[str, str]], dict[str, tuple[str, str]]]:
    """Enumerate storage dashboard pages without writing Lovelace state."""
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        return [], {}

    result: list[tuple[str, str]] = []
    pages: dict[str, tuple[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for key, dashboard in dashboards.items():
        class_name = dashboard.__class__.__name__.casefold()
        mode = str(getattr(dashboard, "mode", "")).casefold()
        if class_name.endswith("yaml") or (mode and mode != "storage"):
            continue
        dashboard_path = str(
            key or getattr(dashboard, "url_path", None) or DEFAULT_SOURCE_DASHBOARD
        )
        try:
            config = await dashboard.async_load(False)
        except Exception:
            _LOGGER.debug("Unable to enumerate Lovelace dashboard %s", dashboard_path)
            continue
        if not isinstance(config, Mapping):
            continue
        dashboard_title = getattr(dashboard, "title", None)
        if not isinstance(dashboard_title, str) or not dashboard_title.strip():
            dashboard_title = dashboard_path
        for view in config.get("views", []):
            if not isinstance(view, Mapping):
                continue
            view_path = str(view.get("path") or view.get("title") or "").strip()
            if not view_path or (dashboard_path, view_path) in seen:
                continue
            seen.add((dashboard_path, view_path))
            view_title = str(view.get("title") or view_path).strip()
            token = _dashboard_page_token(dashboard_path, view_path)
            pages[token] = (dashboard_path, view_path)
            result.append(
                (
                    f"{dashboard_title} — {view_title} "
                    f"({dashboard_path}/{view_path})",
                    token,
                )
            )
    return (
        [
            {"value": token, "label": label}
            for label, token in sorted(result, key=lambda item: item[0].casefold())
        ],
        pages,
    )


def _known_entity_ids(hass: Any) -> set[str]:
    registry = er.async_get(hass)
    return set(registry.entities) | set(hass.states.async_entity_ids())


def _platform_name(platform: TargetPlatform) -> str:
    if platform is TargetPlatform.GOOGLE:
        return "Google Home"
    if platform is TargetPlatform.HOMEKIT:
        return "HomeKit"
    return "Matterbridge"


class _ConditionalFlowMixin:
    """Shared multi-step implementation for config and options flows."""

    _defaults: dict[str, Any]
    _values: dict[str, Any]
    _form_values: dict[str, Any]
    _dashboard_pages: dict[str, tuple[str, str]]
    _dashboard_options: list[dict[str, str]]

    def _initialize(self, defaults: Mapping[str, Any]) -> None:
        self._defaults = deepcopy(dict(defaults))
        self._values = {
            key: deepcopy(value)
            for key, value in defaults.items()
            if key in _EDITABLE_KEYS
        }
        self._form_values = {}
        self._dashboard_pages = {}
        self._dashboard_options = []

    def _value(self, key: str, fallback: Any) -> Any:
        return deepcopy(
            self._form_values.get(
                key, self._values.get(key, self._defaults.get(key, fallback))
            )
        )

    def _remember_form_values(self, values: Mapping[str, Any]) -> None:
        """Keep the current page values when validation redraws the form."""
        self._form_values.update(deepcopy(dict(values)))

    def _accept_values(self, values: Mapping[str, Any]) -> None:
        """Commit validated values and discard their temporary form copies."""
        self._values.update(deepcopy(dict(values)))
        for key in values:
            self._form_values.pop(key, None)

    def _rule_default(self, platform: TargetPlatform, operation: str) -> list[str]:
        rules = self._defaults.get(CONF_USER_RULES, {})
        return list(rules.get(platform.value, {}).get(operation, []))

    def _source_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_ENABLED,
                    default=self._value(CONF_ENABLED, DEFAULT_ENABLED),
                ): bool,
                vol.Required(
                    CONF_SOURCE_KIND,
                    default=self._value(
                        CONF_SOURCE_KIND, SourceKind.DASHBOARD.value
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[item.value for item in SourceKind],
                        translation_key="source_kind",
                    )
                ),
            }
        )

    async def _async_source_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            if not bool(user_input[CONF_ENABLED]):
                if getattr(self, "_entry", None) is None:
                    self._accept_values(user_input)
                else:
                    # Disabling is a single-purpose action. Preserve the entire
                    # existing source/target configuration for later re-enable.
                    self._values[CONF_ENABLED] = False
                return self._finish(self._compose_user_data())
            self._accept_values(user_input)
            source = SourceKind(user_input[CONF_SOURCE_KIND])
            if source is SourceKind.DASHBOARD:
                return await self.async_step_dashboard()
            if source is SourceKind.MANUAL:
                return await self.async_step_manual()
            if source is SourceKind.HOMEKIT:
                return await self.async_step_homekit_source()
            return await self.async_step_targets()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._source_schema(),
            errors=errors,
        )

    async def async_step_dashboard(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        if not self._dashboard_options:
            self._dashboard_options, self._dashboard_pages = (
                await _dashboard_page_choices(self.hass)
            )
        if not self._dashboard_pages:
            return await self.async_step_dashboard_path(user_input)

        options = list(self._dashboard_options)
        options.append(
            {
                "value": MANUAL_DASHBOARD_PAGE,
                "label": (
                    "手動輸入儀表板路徑"
                    if _is_zh_hant(self.hass)
                    else "Enter a dashboard path manually"
                ),
            }
        )
        current_pages = normalize_dashboard_pages(
            self._value(CONF_SOURCE_PAGES, []),
            fallback_dashboard=str(
                self._value(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)
            ),
            fallback_view=str(self._value(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)),
        )
        default_tokens: list[str] = []
        available_tokens = {option["value"] for option in options}
        for dashboard, view in current_pages:
            token = _dashboard_page_token(dashboard, view)
            if token not in self._dashboard_pages:
                self._dashboard_pages[token] = (dashboard, view)
            if token not in available_tokens:
                options.append(
                    {
                        "value": token,
                        "label": (
                            f"已設定 — {dashboard}/{view}"
                            if _is_zh_hant(self.hass)
                            else f"Configured — {dashboard}/{view}"
                        ),
                    }
                )
                available_tokens.add(token)
            default_tokens.append(token)

        if user_input is not None:
            raw_tokens = user_input.get(CONF_SOURCE_PAGE, [])
            if isinstance(raw_tokens, str):
                raw_tokens = [raw_tokens]
            elif not isinstance(raw_tokens, (list, tuple)):
                raw_tokens = []
            tokens = list(
                dict.fromkeys(
                    str(token)
                    for token in raw_tokens
                    if isinstance(token, str) and token
                )
            )
            if not tokens:
                errors[CONF_SOURCE_PAGE] = "dashboard_required"
            elif MANUAL_DASHBOARD_PAGE in tokens and len(tokens) != 1:
                errors[CONF_SOURCE_PAGE] = "dashboard_selection_conflict"
            elif tokens == [MANUAL_DASHBOARD_PAGE]:
                return await self.async_step_dashboard_path()
            elif any(token not in self._dashboard_pages for token in tokens):
                errors[CONF_SOURCE_PAGE] = "dashboard_not_found"
            else:
                pages = [self._dashboard_pages[token] for token in tokens]
                try:
                    snapshot = await async_read_dashboard_sources(self.hass, pages)
                    if not snapshot.entities:
                        errors[CONF_SOURCE_PAGE] = "empty_source"
                except EmptyDashboardSourceError:
                    errors[CONF_SOURCE_PAGE] = "empty_source"
                except Exception:
                    errors[CONF_SOURCE_PAGE] = "dashboard_not_found"
                if not errors:
                    self._values[CONF_SOURCE_PAGES] = _serialize_dashboard_pages(pages)
                    self._values[CONF_SOURCE_DASHBOARD] = pages[0][0]
                    self._values[CONF_SOURCE_VIEW] = pages[0][1]
                    return await self.async_step_targets()
            if errors:
                self._remember_form_values({CONF_SOURCE_PAGE: tokens})

        remembered_tokens = self._form_values.get(CONF_SOURCE_PAGE)
        if isinstance(remembered_tokens, list):
            default_tokens = list(remembered_tokens)

        return self.async_show_form(
            step_id="dashboard",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCE_PAGE, default=default_tokens
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_dashboard_path(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            dashboard = str(user_input.get(CONF_SOURCE_DASHBOARD, "")).strip()
            view = str(user_input.get(CONF_SOURCE_VIEW, "")).strip()
            if not dashboard:
                errors[CONF_SOURCE_DASHBOARD] = "required"
            if not view:
                errors[CONF_SOURCE_VIEW] = "required"
            if not errors:
                try:
                    snapshot = await async_read_dashboard_source(
                        self.hass, dashboard, view
                    )
                    if not snapshot.entities:
                        errors["base"] = "empty_source"
                except Exception:
                    errors["base"] = "dashboard_not_found"
            if not errors:
                self._accept_values(
                    {
                        CONF_SOURCE_DASHBOARD: dashboard,
                        CONF_SOURCE_VIEW: view,
                        CONF_SOURCE_PAGES: _serialize_dashboard_pages(
                            [(dashboard, view)]
                        ),
                    }
                )
                return await self.async_step_targets()
            self._remember_form_values(
                {
                    CONF_SOURCE_DASHBOARD: dashboard,
                    CONF_SOURCE_VIEW: view,
                }
            )
        return self.async_show_form(
            step_id="dashboard_path",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCE_DASHBOARD,
                        default=self._value(
                            CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD
                        ),
                    ): str,
                    vol.Required(
                        CONF_SOURCE_VIEW,
                        default=self._value(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = normalize_entities(user_input.get(CONF_SOURCE_ENTITIES, []))
            if not entities:
                errors[CONF_SOURCE_ENTITIES] = "entity_required"
            elif entities - _known_entity_ids(self.hass):
                errors[CONF_SOURCE_ENTITIES] = "entity_not_found"
            if not errors:
                self._accept_values({CONF_SOURCE_ENTITIES: sorted(entities)})
                return await self.async_step_targets()
            self._remember_form_values({CONF_SOURCE_ENTITIES: sorted(entities)})
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCE_ENTITIES,
                        default=self._value(CONF_SOURCE_ENTITIES, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_homekit_source(
        self, user_input: dict[str, Any] | None = None
    ):
        """Select exact HomeKit Bridge/Accessory Config Entries as the source."""
        errors: dict[str, str] = {}
        configured = self._value(CONF_HOMEKIT_SOURCE_ENTRY_IDS, [])
        try:
            default_entry_ids = list(normalize_config_entry_ids(configured))
        except ValueError:
            default_entry_ids = []

        if user_input is not None:
            try:
                selected_entry_ids = normalize_config_entry_ids(
                    user_input.get(CONF_HOMEKIT_SOURCE_ENTRY_IDS), required=True
                )
            except ValueError:
                errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = (
                    "homekit_source_entry_required"
                )
            else:
                self._remember_form_values(
                    {CONF_HOMEKIT_SOURCE_ENTRY_IDS: list(selected_entry_ids)}
                )
                try:
                    await async_validate_homekit_source_entries(
                        self.hass, selected_entry_ids
                    )
                except HomeKitSourceEntryMissingError:
                    errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = (
                        "homekit_source_entry_not_found"
                    )
                except HomeKitSourceEntryUnavailableError:
                    errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = (
                        "homekit_source_entry_unavailable"
                    )
                except HomeKitSourceFilterUnsupportedError:
                    errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = (
                        "homekit_source_filter_unsupported"
                    )
                except EmptyHomeKitSourceError:
                    errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = "empty_source"
                except Exception as error:
                    _LOGGER.debug(
                        "HomeKit source selection validation failed: %s", error
                    )
                    errors[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = (
                        "homekit_source_entry_unavailable"
                    )
                if not errors:
                    self._accept_values(
                        {
                            CONF_HOMEKIT_SOURCE_ENTRY_IDS: list(
                                selected_entry_ids
                            )
                        }
                    )
                    return await self.async_step_targets()

        return self.async_show_form(
            step_id="homekit_source",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOMEKIT_SOURCE_ENTRY_IDS,
                        default=default_entry_ids,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_homekit_choices(
                                self.hass, default_entry_ids
                            ),
                            multiple=True,
                            mode="list",
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_targets(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            raw_targets = list(user_input.get(CONF_TARGET_PLATFORMS, []))
            if not raw_targets:
                errors[CONF_TARGET_PLATFORMS] = "target_required"
            else:
                try:
                    targets = [TargetPlatform(value).value for value in raw_targets]
                except ValueError:
                    errors[CONF_TARGET_PLATFORMS] = "invalid_target"
                else:
                    self._accept_values({CONF_TARGET_PLATFORMS: targets})
                    return await self.async_step_platform_settings()
            self._remember_form_values(
                {
                    CONF_TARGET_PLATFORMS: [
                        str(value)
                        for value in raw_targets
                        if isinstance(value, str)
                    ]
                }
            )
        return self.async_show_form(
            step_id="targets",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TARGET_PLATFORMS,
                        default=self._value(
                            CONF_TARGET_PLATFORMS,
                            [item.value for item in ALL_TARGETS],
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[item.value for item in ALL_TARGETS],
                            multiple=True,
                            translation_key="target_platforms",
                        )
                    )
                }
            ),
            errors=errors,
        )

    def _selected_targets(self) -> tuple[TargetPlatform, ...]:
        selected = set(self._value(CONF_TARGET_PLATFORMS, []))
        return tuple(platform for platform in TargetPlatform if platform.value in selected)

    def _platform_settings_schema(self) -> vol.Schema:
        schema: dict[Any, Any] = {}
        source = SourceKind(self._value(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value))
        targets = self._selected_targets()

        if TargetPlatform.GOOGLE in targets:
            schema[
                vol.Required(
                    CONF_GOOGLE_CONFIG_PATH,
                    default=self._value(
                        CONF_GOOGLE_CONFIG_PATH, DEFAULT_GOOGLE_CONFIG_PATH
                    ),
                )
            ] = str
        if TargetPlatform.HOMEKIT in targets:
            schema[
                vol.Required(
                    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
                    default=self._value(CONF_HOMEKIT_MANAGED_ENTRY_IDS, []),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_homekit_choices(
                        self.hass,
                        self._value(CONF_HOMEKIT_MANAGED_ENTRY_IDS, []),
                    ),
                    multiple=True,
                )
            )
            schema[
                vol.Optional(
                    CONF_HOMEKIT_MAIN_ENTRY_ID,
                    default=self._value(CONF_HOMEKIT_MAIN_ENTRY_ID, ""),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_homekit_choices(
                        self.hass,
                        [self._value(CONF_HOMEKIT_MAIN_ENTRY_ID, "")],
                    ),
                    multiple=False,
                )
            )
            schema[
                vol.Optional(
                    CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
                    default=self._value(CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS, []),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_homekit_choices(
                        self.hass,
                        self._value(CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS, []),
                    ),
                    multiple=True,
                )
            )
            schema[
                vol.Optional(
                    CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
                    default=self._value(
                        CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
                        DEFAULT_HOMEKIT_ACCESSORY_CONFIG_PATH,
                    ),
                )
            ] = str
        if source is SourceKind.MATTER or TargetPlatform.MATTER in targets:
            schema[
                vol.Required(
                    CONF_MATTER_HOST,
                    default=self._value(CONF_MATTER_HOST, DEFAULT_MATTER_HOST),
                )
            ] = str
            schema[
                vol.Required(
                    CONF_MATTER_PORT,
                    default=self._value(CONF_MATTER_PORT, DEFAULT_MATTER_PORT),
                )
            ] = vol.Coerce(int)
            schema[
                vol.Optional(
                    CONF_MATTER_PASSWORD,
                    default=self._value(
                        CONF_MATTER_PASSWORD, DEFAULT_MATTER_PASSWORD
                    ),
                )
            ] = selector.TextSelector(
                selector.TextSelectorConfig(type="password")
            )

        for platform in targets:
            for operation in ("include", "exclude"):
                key = f"{platform.value}_{operation}"
                schema[
                    vol.Optional(
                        key,
                        default=self._value(
                            key, self._rule_default(platform, operation)
                        ),
                    )
                ] = selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                )
        return vol.Schema(schema)

    def _prerequisites(self) -> str:
        source = SourceKind(self._value(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value))
        targets = set(self._selected_targets())
        zh = _is_zh_hant(self.hass)
        messages: list[str] = []
        if source is SourceKind.GOOGLE or TargetPlatform.GOOGLE in targets:
            messages.append(
                "使用 Google Home 前，請先完成 Google Assistant 整合與 Google 帳戶連結。若 Google Home 是目標平台，還必須使用專用裝置設定檔並關閉預設公開所有裝置。"
                if zh
                else "Before using Google Home, configure the Google Assistant integration and link your Google account. When Google Home is a target, also use a dedicated entity configuration file and disable default device exposure."
            )
        if source is SourceKind.MATTER or TargetPlatform.MATTER in targets:
            messages.append(
                "使用 Matterbridge 前，請先安裝並啟用 Matterbridge 的 Home Assistant 外掛，並完成連線設定。"
                if zh
                else "Before using Matterbridge, install and enable its Home Assistant plugin and complete the connection setup."
            )
        return "\n\n".join(messages)

    def _compose_user_data(self) -> dict[str, Any]:
        result = {
            key: deepcopy(value)
            for key, value in self._values.items()
            if key in _EDITABLE_KEYS
        }
        result.setdefault(CONF_ENABLED, DEFAULT_ENABLED)
        result.setdefault(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value)
        result.setdefault(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)
        result.setdefault(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)
        result.setdefault(
            CONF_SOURCE_PAGES,
            _serialize_dashboard_pages(
                normalize_dashboard_pages(
                    None,
                    fallback_dashboard=str(result[CONF_SOURCE_DASHBOARD]),
                    fallback_view=str(result[CONF_SOURCE_VIEW]),
                )
            ),
        )
        result.setdefault(CONF_SOURCE_ENTITIES, [])
        result.setdefault(
            CONF_TARGET_PLATFORMS, [platform.value for platform in ALL_TARGETS]
        )
        result.setdefault(CONF_MATTER_HOST, DEFAULT_MATTER_HOST)
        result.setdefault(CONF_MATTER_PORT, DEFAULT_MATTER_PORT)
        result.setdefault(CONF_MATTER_PASSWORD, DEFAULT_MATTER_PASSWORD)
        result.setdefault(CONF_GOOGLE_CONFIG_PATH, DEFAULT_GOOGLE_CONFIG_PATH)
        result.setdefault(CONF_HOMEKIT_SOURCE_ENTRY_IDS, [])
        result.setdefault(CONF_HOMEKIT_MANAGED_ENTRY_IDS, [])
        result.setdefault(CONF_HOMEKIT_MAIN_ENTRY_ID, "")
        result.setdefault(CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS, [])
        result.setdefault(CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS, [])
        result.setdefault(CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS, [])
        result.setdefault(
            CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
            DEFAULT_HOMEKIT_ACCESSORY_CONFIG_PATH,
        )

        # Canonicalize every persisted field, including values currently hidden
        # by the conditional UI.  This keeps a malformed legacy or manually
        # edited inactive field from crashing an unrelated Options Flow edit.
        try:
            result[CONF_SOURCE_KIND] = SourceKind(
                result.get(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value)
            ).value
        except (TypeError, ValueError):
            result[CONF_SOURCE_KIND] = SourceKind.DASHBOARD.value
        source_dashboard = (
            str(result.get(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)).strip()
            or DEFAULT_SOURCE_DASHBOARD
        )
        source_view = (
            str(result.get(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)).strip()
            or DEFAULT_SOURCE_VIEW
        )
        result[CONF_SOURCE_DASHBOARD] = source_dashboard
        result[CONF_SOURCE_VIEW] = source_view
        result[CONF_SOURCE_PAGES] = _serialize_dashboard_pages(
            normalize_dashboard_pages(
                result.get(CONF_SOURCE_PAGES),
                fallback_dashboard=source_dashboard,
                fallback_view=source_view,
            )
        )
        result[CONF_SOURCE_ENTITIES] = sorted(
            normalize_entities(result.get(CONF_SOURCE_ENTITIES, []))
        )
        normalized_targets: list[str] = []
        raw_targets = result.get(CONF_TARGET_PLATFORMS, [])
        if isinstance(raw_targets, (list, tuple, set, frozenset)):
            for raw_target in raw_targets:
                try:
                    target = TargetPlatform(raw_target).value
                except (TypeError, ValueError):
                    continue
                if target not in normalized_targets:
                    normalized_targets.append(target)
        result[CONF_TARGET_PLATFORMS] = normalized_targets or [
            platform.value for platform in ALL_TARGETS
        ]
        result[CONF_MATTER_HOST] = (
            str(result.get(CONF_MATTER_HOST, DEFAULT_MATTER_HOST)).strip()
            or DEFAULT_MATTER_HOST
        )
        try:
            matter_port = int(result.get(CONF_MATTER_PORT, DEFAULT_MATTER_PORT))
        except (TypeError, ValueError):
            matter_port = DEFAULT_MATTER_PORT
        result[CONF_MATTER_PORT] = (
            matter_port if 1 <= matter_port <= 65535 else DEFAULT_MATTER_PORT
        )
        result[CONF_MATTER_PASSWORD] = str(
            result.get(CONF_MATTER_PASSWORD, DEFAULT_MATTER_PASSWORD) or ""
        )
        result[CONF_GOOGLE_CONFIG_PATH] = str(
            result.get(CONF_GOOGLE_CONFIG_PATH, DEFAULT_GOOGLE_CONFIG_PATH)
        )
        for entry_key in (
            CONF_HOMEKIT_SOURCE_ENTRY_IDS,
            CONF_HOMEKIT_MANAGED_ENTRY_IDS,
            CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
            CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS,
            CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS,
        ):
            try:
                result[entry_key] = list(
                    normalize_config_entry_ids(result.get(entry_key, []))
                )
            except ValueError:
                result[entry_key] = []
        try:
            result[CONF_HOMEKIT_MAIN_ENTRY_ID] = normalize_optional_config_entry_id(
                result.get(CONF_HOMEKIT_MAIN_ENTRY_ID)
            )
        except ValueError:
            result[CONF_HOMEKIT_MAIN_ENTRY_ID] = ""
        result[CONF_HOMEKIT_ACCESSORY_CONFIG_PATH] = str(
            result.get(
                CONF_HOMEKIT_ACCESSORY_CONFIG_PATH,
                DEFAULT_HOMEKIT_ACCESSORY_CONFIG_PATH,
            )
            or ""
        ).strip()
        existing_rules = deepcopy(self._defaults.get(CONF_USER_RULES, {}))
        targets = set(result.get(CONF_TARGET_PLATFORMS, []))
        packed_rules: dict[str, dict[str, list[str]]] = {}
        for platform in TargetPlatform:
            previous = existing_rules.get(platform.value, {})
            packed_rules[platform.value] = {}
            for operation in ("include", "exclude"):
                key = f"{platform.value}_{operation}"
                values = (
                    self._values.get(key, previous.get(operation, []))
                    if platform.value in targets
                    else previous.get(operation, [])
                )
                packed_rules[platform.value][operation] = sorted(
                    normalize_entities(values)
                )
        result[CONF_USER_RULES] = packed_rules
        return result

    def _candidate_config(self, user_data: Mapping[str, Any]) -> SyncConfig:
        entry = getattr(self, "_entry", None)
        if entry is None:
            return SyncConfig.from_entry(user_data, {})
        return SyncConfig.from_entry(entry.data, user_data)

    async def _validate_platform_readiness(
        self, user_data: Mapping[str, Any]
    ) -> str | None:
        """Reject permanent local selection errors, not transient runtime state.

        Runtime convergence is owned by the manager's bounded retry loop.  A
        Home Assistant startup race, HomeKit reload, or Matterbridge plugin
        warm-up must never prevent an otherwise complete options snapshot from
        being saved for the next automatic attempt.
        """
        config = self._candidate_config(user_data)
        if not config.enabled:
            return None
        if TargetPlatform.HOMEKIT in config.targets:
            available = {
                entry.entry_id: entry
                for entry in self.hass.config_entries.async_entries("homekit")
            }
            if set(config.homekit_managed_entry_ids) - set(available):
                return "homekit_target_entry_not_found"
            lifecycle = set(config.homekit_lifecycle_entry_ids)
            try:
                main_entry_id = homekit_managed_main_entry_id(self.hass, config)
            except RuntimeError:
                return "homekit_target_configuration_invalid"
            if (
                lifecycle - set(config.homekit_managed_entry_ids)
                or lifecycle & set(config.homekit_source_entry_ids)
                or main_entry_id in lifecycle
                or any(
                    len(homekit_entry_entities(available[entry_id])) != 1
                    for entry_id in lifecycle
                )
                or any(
                    _config_entry_source(available[entry_id]) == "import"
                    for entry_id in lifecycle
                )
                and not config.homekit_accessory_config_path
            ):
                return "homekit_lifecycle_invalid"
            try:
                validate_target_configuration(
                    self.hass, config, TargetPlatform.HOMEKIT
                )
            except RuntimeError:
                return "homekit_target_configuration_invalid"
        if (
            config.source_kind is SourceKind.MATTER
            or TargetPlatform.MATTER in config.targets
        ):
            try:
                validate_target_configuration(
                    self.hass, config, TargetPlatform.MATTER
                )
            except (TypeError, ValueError, RuntimeError):
                return "invalid_matter_endpoint"
        return None

    async def async_step_platform_settings(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            source = SourceKind(
                self._value(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value)
            )
            targets = self._selected_targets()
            relevant_google = TargetPlatform.GOOGLE in targets
            relevant_homekit = TargetPlatform.HOMEKIT in targets
            relevant_matter = source is SourceKind.MATTER or TargetPlatform.MATTER in targets

            if relevant_google:
                path = str(user_input.get(CONF_GOOGLE_CONFIG_PATH, "")).strip()
                parsed = PurePosixPath(path)
                if (
                    not path
                    or parsed.is_absolute()
                    or ".." in parsed.parts
                    or "\\" in path
                ):
                    errors[CONF_GOOGLE_CONFIG_PATH] = "invalid_path"
                else:
                    user_input[CONF_GOOGLE_CONFIG_PATH] = path
            if relevant_homekit and not user_input.get(
                CONF_HOMEKIT_MANAGED_ENTRY_IDS
            ):
                errors[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = "homekit_entry_required"
            elif relevant_homekit:
                try:
                    user_input[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = list(
                        normalize_config_entry_ids(
                            user_input.get(CONF_HOMEKIT_MANAGED_ENTRY_IDS),
                            required=True,
                        )
                    )
                except ValueError:
                    errors[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = (
                        "homekit_entry_required"
                    )
                try:
                    lifecycle_ids = list(
                        normalize_config_entry_ids(
                            user_input.get(CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS, [])
                        )
                    )
                except ValueError:
                    errors[CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS] = (
                        "homekit_lifecycle_invalid"
                    )
                    lifecycle_ids = []
                managed_ids = set(user_input.get(CONF_HOMEKIT_MANAGED_ENTRY_IDS, []))
                try:
                    main_entry_id = normalize_optional_config_entry_id(
                        user_input.get(CONF_HOMEKIT_MAIN_ENTRY_ID)
                    )
                except ValueError:
                    main_entry_id = ""
                    errors[CONF_HOMEKIT_MAIN_ENTRY_ID] = (
                        "homekit_target_configuration_invalid"
                    )
                if main_entry_id and main_entry_id not in managed_ids:
                    errors[CONF_HOMEKIT_MAIN_ENTRY_ID] = (
                        "homekit_target_configuration_invalid"
                    )
                user_input[CONF_HOMEKIT_MAIN_ENTRY_ID] = main_entry_id
                if set(lifecycle_ids) - managed_ids:
                    errors[CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS] = (
                        "homekit_lifecycle_invalid"
                    )
                user_input[CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS] = lifecycle_ids
                yaml_path = str(
                    user_input.get(CONF_HOMEKIT_ACCESSORY_CONFIG_PATH, "")
                ).strip()
                if yaml_path:
                    parsed_yaml = PurePosixPath(yaml_path)
                    if (
                        parsed_yaml.is_absolute()
                        or ".." in parsed_yaml.parts
                        or "\\" in yaml_path
                        or parsed_yaml.suffix.casefold() not in {".yaml", ".yml"}
                        or parsed_yaml.name.casefold()
                        in {"configuration.yaml", "configuration.yml"}
                    ):
                        errors[CONF_HOMEKIT_ACCESSORY_CONFIG_PATH] = "invalid_path"
                    else:
                        user_input[CONF_HOMEKIT_ACCESSORY_CONFIG_PATH] = yaml_path
                else:
                    user_input[CONF_HOMEKIT_ACCESSORY_CONFIG_PATH] = ""
            if relevant_matter:
                host = str(user_input.get(CONF_MATTER_HOST, "")).strip()
                try:
                    port = int(user_input.get(CONF_MATTER_PORT, 0))
                except (TypeError, ValueError):
                    port = 0
                if not host:
                    errors[CONF_MATTER_HOST] = "required"
                if not 1 <= port <= 65535:
                    errors[CONF_MATTER_PORT] = "invalid_port"
                user_input[CONF_MATTER_HOST] = host
                user_input[CONF_MATTER_PASSWORD] = str(
                    user_input.get(CONF_MATTER_PASSWORD, "")
                )

            known = _known_entity_ids(self.hass)
            entry_data = getattr(getattr(self, "_entry", None), "data", {})
            locked = parse_rules(entry_data.get(CONF_LOCKED_RULES))
            for platform in targets:
                include_key = f"{platform.value}_include"
                exclude_key = f"{platform.value}_exclude"
                include = normalize_entities(user_input.get(include_key, []))
                exclude = normalize_entities(user_input.get(exclude_key, []))
                if include & exclude:
                    errors[exclude_key] = "include_exclude_conflict"
                elif (include | exclude) - known:
                    errors[exclude_key] = "entity_not_found"
                elif (
                    include & locked[platform].exclude
                    or exclude & locked[platform].include
                ):
                    errors[exclude_key] = "protected_rule_conflict"
                user_input[include_key] = sorted(include)
                user_input[exclude_key] = sorted(exclude)

            self._remember_form_values(user_input)
            if not errors:
                self._accept_values(user_input)
                user_data = self._compose_user_data()
                if relevant_homekit and not user_data.get(
                    CONF_HOMEKIT_MAIN_ENTRY_ID
                ):
                    try:
                        inferred_main = homekit_managed_main_entry_id(
                            self.hass, self._candidate_config(user_data)
                        )
                    except RuntimeError:
                        errors[CONF_HOMEKIT_MAIN_ENTRY_ID] = (
                            "homekit_target_configuration_invalid"
                        )
                    else:
                        self._accept_values(
                            {CONF_HOMEKIT_MAIN_ENTRY_ID: inferred_main}
                        )
                        user_data = self._compose_user_data()
                readiness_error = await self._validate_platform_readiness(user_data)
                if readiness_error:
                    errors["base"] = readiness_error
                else:
                    return await self.async_step_confirm()

        return self.async_show_form(
            step_id="platform_settings",
            data_schema=self._platform_settings_schema(),
            errors=errors,
            description_placeholders={
                "prerequisites": self._prerequisites() or " "
            },
        )

    def _summary(self) -> str:
        source = SourceKind(self._value(CONF_SOURCE_KIND, SourceKind.DASHBOARD.value))
        zh = _is_zh_hant(self.hass)
        source_names = {
            SourceKind.DASHBOARD: (
                "Home Assistant 儀表板中的裝置"
                if zh
                else "Devices on selected Home Assistant dashboard views"
            ),
            SourceKind.MANUAL: "手動選取的裝置" if zh else "Manually selected devices",
            SourceKind.GOOGLE: (
                "Google Home 中的裝置" if zh else "Devices in Google Home"
            ),
            SourceKind.HOMEKIT: (
                "HomeKit 中的裝置" if zh else "Devices in HomeKit"
            ),
            SourceKind.MATTER: (
                "Matterbridge 中的裝置" if zh else "Devices in Matterbridge"
            ),
        }
        target_names = ", ".join(
            _platform_name(platform) for platform in self._selected_targets()
        )
        source_detail = ""
        if source is SourceKind.DASHBOARD:
            pages = normalize_dashboard_pages(
                self._value(CONF_SOURCE_PAGES, []),
                fallback_dashboard=str(
                    self._value(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)
                ),
                fallback_view=str(
                    self._value(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)
                ),
            )
            routes = "、".join(f"{dashboard}/{view}" for dashboard, view in pages)
            source_detail = (
                f"\n儀表板頁面：{routes}"
                if zh
                else "\nDashboard views: "
                + ", ".join(f"{dashboard}/{view}" for dashboard, view in pages)
            )
        elif source is SourceKind.HOMEKIT:
            configured = self._value(CONF_HOMEKIT_SOURCE_ENTRY_IDS, [])
            try:
                selected_entry_ids = normalize_config_entry_ids(configured)
            except ValueError:
                selected_entry_ids = ()
            entry_titles = {
                entry.entry_id: entry.title
                for entry in self.hass.config_entries.async_entries("homekit")
            }
            selected_titles = [
                entry_titles.get(entry_id, entry_id)
                for entry_id in selected_entry_ids
            ]
            source_detail = (
                "\nHomeKit 來源項目：" + "、".join(selected_titles)
                if zh
                else "\nHomeKit source entries: " + ", ".join(selected_titles)
            )
        enabled = bool(self._value(CONF_ENABLED, False))
        if zh:
            return (
                f"同步來源：{source_names[source]}{source_detail}\n\n"
                f"目標平台：{target_names}\n\n"
                f"自動同步：{'啟用' if enabled else '停用'}"
            )
        return (
            f"Source: {source_names[source]}{source_detail}\n\n"
            f"Targets: {target_names}\n\n"
            f"Automatic synchronization: {'Enabled' if enabled else 'Disabled'}"
        )

    async def _manual_pairing_preview(self) -> str:
        """List controller-side pairing that the current exact plan will require."""
        zh = _is_zh_hant(self.hass)
        user_data = self._compose_user_data()
        try:
            config = self._candidate_config(user_data)
        except (TypeError, ValueError):
            return (
                "首次同步完成後會顯示需要額外配對的裝置。"
                if zh
                else "Devices requiring extra pairing will be listed after the first synchronization."
            )
        if not config.enabled:
            return "同步目前停用。" if zh else "Synchronization is currently disabled."

        source_entities: frozenset[str] | None = None
        deferred_message: str | None = None
        try:
            if config.source_kind is SourceKind.MANUAL:
                source_entities = config.source_entities
            elif config.source_kind is SourceKind.DASHBOARD:
                source_entities = (
                    await async_read_dashboard_sources(
                        self.hass, config.source_pages
                    )
                ).entities
            elif config.source_kind is SourceKind.HOMEKIT:
                source_entities = await async_validate_homekit_source_entries(
                    self.hass, config.homekit_source_entry_ids
                )
            else:
                deferred_message = (
                    "此同步來源需在設定儲存後才能安全讀取；首次同步完成時會用 Home Assistant 持續通知逐項列出需要配對或確認的裝置。"
                    if zh
                    else "This source can be read safely only after the configuration is saved. The first synchronization will list every device requiring pairing or verification in a persistent Home Assistant notification."
                )
        except Exception:
            _LOGGER.debug("Unable to preview the synchronization source", exc_info=True)
            deferred_message = (
                "目前無法預先讀取完整來源清單；首次同步完成後會在 Home Assistant 持續通知中逐項列出。"
                if zh
                else "The complete source list cannot be previewed now; the first synchronization will list every item in a persistent Home Assistant notification."
            )

        homekit_pair_entities: set[str] = set()
        homekit_check_entities: set[str] = set()
        homekit_pair_bridges: list[tuple[str, str]] = []
        homekit_check_bridges: list[tuple[str, str]] = []
        matter_entities: set[str] = set()
        malformed_pending: list[str] = []
        if TargetPlatform.HOMEKIT in config.targets:
            desired_homekit: frozenset[str] | None = None
            main_entry_id: str | None = None
            if config.homekit_managed_entry_ids:
                try:
                    main_entry_id = homekit_managed_main_entry_id(self.hass, config)
                except RuntimeError:
                    # The previous form's readiness validation normally catches
                    # this. Keep the review truthful if entries change while the
                    # final step is open.
                    deferred_message = (
                        "HomeKit 主 Bridge 目前無法精確辨識；請返回上一頁重新確認選取項目。"
                        if zh
                        else "The main HomeKit Bridge cannot currently be identified exactly; return to the previous page and review the selection."
                    )
            if source_entities is not None:
                try:
                    dynamic_exclude = (
                        await async_find_apple_tv_entities(self.hass)
                        if config.locked_homekit_apple_tv_exclusion
                        else frozenset()
                    )
                    plan = evaluate_target(
                        source_entities,
                        frozenset(),
                        config.user_rules[TargetPlatform.HOMEKIT],
                        config.locked_rules[TargetPlatform.HOMEKIT],
                        TargetPlatform.HOMEKIT,
                        dynamic_exclude,
                    )
                    desired_homekit = plan.desired
                    # These entries do not exist yet, so every item will need a
                    # native Apple Home pairing after the first reconciliation.
                    homekit_pair_entities.update(
                        homekit_new_accessory_mode_entities(
                            self.hass, config, plan.desired
                        )
                    )
                except Exception:
                    _LOGGER.debug(
                        "Unable to preview new HomeKit accessory entries",
                        exc_info=True,
                    )
                    deferred_message = deferred_message or (
                        "目前無法預先讀取完整 HomeKit 清單；首次同步完成後會在 Home Assistant 持續通知中逐項列出。"
                        if zh
                        else "The complete HomeKit list cannot be previewed now; the first synchronization will list every item in a persistent Home Assistant notification."
                    )

            pending_ids = set(config.homekit_pending_pairing_entry_ids)
            lifecycle_ids = set(config.homekit_lifecycle_entry_ids)
            inspect_ids = pending_ids | set(config.homekit_managed_entry_ids)
            for entry_id in sorted(inspect_ids):
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry is None:
                    continue
                if entry_id == main_entry_id:
                    paired = homekit_entry_is_paired(entry)
                    bridge = (
                        str(getattr(entry, "title", None) or "HomeKit Bridge"),
                        entry_id,
                    )
                    if paired is False:
                        homekit_pair_bridges.append(bridge)
                    elif paired is None:
                        homekit_check_bridges.append(bridge)
                    continue
                # The managed set also contains the main Bridge.  Only native
                # accessory entries, explicit lifecycle side entries, or a
                # durable pending record can require per-device pairing.
                if (
                    entry_id not in pending_ids
                    and entry_id not in lifecycle_ids
                    and _homekit_mode(entry) != "accessory"
                ):
                    continue
                entities = homekit_entry_entities(entry)
                if len(entities) != 1:
                    if entry_id in pending_ids:
                        malformed_pending.append(entry_id)
                    continue
                entity_id = next(iter(entities))
                # Do not ask the owner to pair an accessory that the submitted
                # exact plan will remove.  With a remote source, the desired set
                # is intentionally unknown until the first safe reconciliation,
                # so retain only durable pending items rather than guessing from
                # every currently managed accessory.
                if desired_homekit is not None and entity_id not in desired_homekit:
                    continue
                if desired_homekit is None and entry_id not in pending_ids:
                    continue
                paired = homekit_entry_is_paired(entry)
                if paired is True:
                    continue
                if paired is False:
                    homekit_pair_entities.add(entity_id)
                else:
                    homekit_check_entities.add(entity_id)

        # A newly-created accessory is known to need pairing even if an
        # overlapping stale entry had no readable runtime state.
        homekit_check_entities.difference_update(homekit_pair_entities)

        if TargetPlatform.MATTER in config.targets and source_entities is not None:
            try:
                plan = evaluate_target(
                    source_entities,
                    frozenset(),
                    config.user_rules[TargetPlatform.MATTER],
                    config.locked_rules[TargetPlatform.MATTER],
                    TargetPlatform.MATTER,
                )
                # Config Flow deliberately performs no Matterbridge network
                # probe. Runtime sync refines this list using enableServerRvc;
                # here every desired vacuum is shown as a possible separate
                # server node so completion never hides required owner work.
                matter_entities.update(
                    entity_id
                    for entity_id in plan.desired
                    if entity_id.startswith("vacuum.")
                )
            except Exception:
                _LOGGER.debug(
                    "Unable to preview Matter manual pairing requirements",
                    exc_info=True,
                )
                deferred_message = deferred_message or (
                    "目前無法預先讀取完整 Matter 清單；首次同步完成後會在 Home Assistant 持續通知中逐項列出。"
                    if zh
                    else "The complete Matter list cannot be previewed now; the first synchronization will list every item in a persistent Home Assistant notification."
                )
        sections: list[str] = []

        def _labels(entities: frozenset[str]) -> list[str]:
            labels: list[str] = []
            for entity_id in sorted(entities):
                state = self.hass.states.get(entity_id)
                name = (
                    state.attributes.get("friendly_name")
                    if state is not None
                    else None
                )
                labels.append(
                    f"{name or entity_id}（{entity_id}）"
                    if zh
                    else f"{name or entity_id} ({entity_id})"
                )
            return labels

        def _bridge_labels(entries: list[tuple[str, str]]) -> list[str]:
            return [
                f"{title}（HomeKit Bridge，{entry_id[:8]}）"
                if zh
                else f"{title} (HomeKit Bridge, {entry_id[:8]})"
                for title, entry_id in entries
            ]

        if homekit_pair_bridges:
            heading = (
                "需要在 Apple Home 額外配對 HomeKit Bridge："
                if zh
                else "Requires additional HomeKit Bridge pairing in Apple Home:"
            )
            sections.append(
                heading
                + "\n"
                + "\n".join(
                    f"- {label}" for label in _bridge_labels(homekit_pair_bridges)
                )
            )
        if homekit_check_bridges:
            heading = (
                "需要在 Apple Home 確認 HomeKit Bridge 配對狀態（尚未配對才加入）："
                if zh
                else "Check HomeKit Bridge pairing status in Apple Home (add it only if it is not already paired):"
            )
            sections.append(
                heading
                + "\n"
                + "\n".join(
                    f"- {label}" for label in _bridge_labels(homekit_check_bridges)
                )
            )

        if homekit_pair_entities:
            heading = (
                "需要在 Apple Home 額外配對："
                if zh
                else "Requires additional pairing in Apple Home:"
            )
            sections.append(
                heading
                + "\n"
                + "\n".join(
                    f"- {label}" for label in _labels(frozenset(homekit_pair_entities))
                )
            )
        if homekit_check_entities:
            heading = (
                "需要在 Apple Home 確認配對狀態（尚未配對才加入 accessory）："
                if zh
                else "Check pairing status in Apple Home (add the accessory only if it is not already paired):"
            )
            sections.append(
                heading
                + "\n"
                + "\n".join(
                    f"- {label}" for label in _labels(frozenset(homekit_check_entities))
                )
            )
        if malformed_pending:
            sections.append(
                (
                    "HomeKit 尚有配對追蹤項目無法精確辨識，請開啟此外掛設定重新選取對應的單一 accessory："
                    if zh
                    else "Some pending HomeKit pairing entries cannot be identified exactly; reopen this integration and select the corresponding single-entity accessories:"
                )
                + "\n"
                + "\n".join(f"- {entry_id}" for entry_id in malformed_pending)
            )
        if matter_entities:
            heading = (
                "可能是 Matter 獨立 server node；首次同步會依 Matterbridge 設定確認。若清單仍出現在通知中，請到 Matterbridge Devices 頁確認配對狀態（若尚未配對才掃描 QR code）："
                if zh
                else "Possible separate Matter server nodes; the first sync will verify the Matterbridge setting. If an item remains in the notification, check it in the Devices panel (scan its QR code only if it is not already paired):"
            )
            sections.append(
                heading
                + "\n"
                + "\n".join(f"- {label}" for label in _labels(matter_entities))
            )
        if deferred_message:
            sections.append(deferred_message)
        if not sections:
            statuses: list[str] = []
            if TargetPlatform.GOOGLE in config.targets:
                statuses.append(
                    "- Google Home：帳戶完成一次連結後，不需逐裝置配對。"
                    if zh
                    else "- Google Home: once the account is linked, individual synchronized devices do not require pairing."
                )
            if TargetPlatform.HOMEKIT in config.targets:
                statuses.append(
                    "- HomeKit：目前沒有已知需要在 Apple Home 額外配對的裝置。"
                    if zh
                    else "- HomeKit: no device is currently known to require additional Apple Home pairing."
                )
            if TargetPlatform.MATTER in config.targets:
                statuses.append(
                    "- Matter：一般 Bridge 端點不需逐裝置配對；只有獨立 server node 需要另行確認。"
                    if zh
                    else "- Matter: normal Bridge endpoints do not require per-device pairing; only separate server nodes need an additional check."
                )
            return "\n".join(statuses) or (
                "目前沒有新裝置需要逐裝置人工配對。"
                if zh
                else "No new device currently requires per-device pairing."
            )
        return "\n\n".join(sections)

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self._finish(self._compose_user_data())
        pairing = await self._manual_pairing_preview()
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "summary": self._summary(),
                "manual_pairing": pairing,
            },
            last_step=True,
        )

    def _finish(self, user_data: dict[str, Any]):
        raise NotImplementedError


class PlatformSyncConfigFlow(
    _ConditionalFlowMixin, config_entries.ConfigFlow, domain=DOMAIN
):
    VERSION = 4
    MINOR_VERSION = 4

    def __init__(self) -> None:
        super().__init__()
        self._initialize({})

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self._async_source_step("user", user_input)

    def _finish(self, user_data: dict[str, Any]):
        user_data = dict(user_data)
        user_data[CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION] = True
        return self.async_create_entry(
            title=_default_entry_title(self.hass), data=user_data
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PlatformSyncOptionsFlow()


class PlatformSyncOptionsFlow(
    _ConditionalFlowMixin, config_entries.OptionsFlowWithReload
):
    def __init__(self) -> None:
        super().__init__()
        self._entry = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if self._entry is None:
            self._entry = self.config_entry
            defaults = merge_entry_settings(
                self._entry.data, self._entry.options
            )
            self._initialize(defaults)
        return await self._async_source_step("init", user_input)

    def _finish(self, user_data: dict[str, Any]):
        # A running reconciliation may create or remove an owned HomeKit
        # accessory while this multi-step Options Flow is open. Apply only the
        # user's selection delta to the latest ledger instead of overwriting
        # it with the flow's opening snapshot.
        latest = merge_entry_settings(
            self._entry.data, self._entry.options
        )
        merged = dict(user_data)

        def _safe_ids(value: Any) -> set[str]:
            try:
                return set(normalize_config_entry_ids(value))
            except ValueError:
                return set()

        for key in (
            CONF_HOMEKIT_MANAGED_ENTRY_IDS,
            CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS,
        ):
            baseline_ids = _safe_ids(self._defaults.get(key, []))
            requested_ids = _safe_ids(user_data.get(key, []))
            latest_ids = _safe_ids(latest.get(key, []))
            final_ids = (
                latest_ids | (requested_ids - baseline_ids)
            ) - (baseline_ids - requested_ids)
            merged[key] = list(
                dict.fromkeys(
                    entry_id
                    for entry_id in (
                        *user_data.get(key, []),
                        *latest.get(key, []),
                    )
                    if entry_id in final_ids
                )
            )
        latest_pending = _safe_ids(
            latest.get(CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS, [])
        )
        merged[CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS] = sorted(
            latest_pending
            & set(merged[CONF_HOMEKIT_MANAGED_ENTRY_IDS])
            & set(merged[CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS])
        )
        merged[CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS] = sorted(
            _safe_ids(latest.get(CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS, []))
        )
        return self.async_create_entry(data=merged)
