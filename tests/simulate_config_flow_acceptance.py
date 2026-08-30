"""Dependency-light acceptance checks for the conditional config flow.

Run with ``python tests/simulate_config_flow_acceptance.py``.  The workstation
does not need Home Assistant, voluptuous, or pytest; small stubs exercise the
real integration ``config_flow.py`` and inspect the forms it returns.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
from typing import Any


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "platform_sync"


def load(name: str, filename: str) -> ModuleType:
    """Load one integration module without importing package ``__init__``."""
    spec = importlib.util.spec_from_file_location(name, PACKAGE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class _Marker:
    """Small hashable stand-in for voluptuous Required/Optional markers."""

    def __init__(
        self,
        schema: str,
        *,
        default: Any = None,
        description: dict[str, Any] | None = None,
    ) -> None:
        self.schema = schema
        self.default = default
        self.description = description


class _Required(_Marker):
    pass


class _Optional(_Marker):
    pass


class _Schema:
    def __init__(self, schema: dict[Any, Any]) -> None:
        self.schema = schema

    def __call__(self, value: Any) -> Any:
        return value


class _SelectorConfig(dict):
    """Dictionary-like selector config matching HA's public surface."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.__dict__.update(kwargs)


class _Selector:
    def __init__(self, config: _SelectorConfig) -> None:
        self.config = config


def install_stubs() -> dict[str, int]:
    """Install the minimum HA and voluptuous surface used by config_flow."""
    custom_components = ModuleType("custom_components")
    package = ModuleType("custom_components.platform_sync")
    package.__path__ = [str(PACKAGE)]

    vol = ModuleType("voluptuous")
    vol.Required = _Required
    vol.Optional = _Optional
    vol.Schema = _Schema
    vol.Coerce = lambda value_type: value_type

    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")
    helpers = ModuleType("homeassistant.helpers")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    selector = ModuleType("homeassistant.helpers.selector")

    class _FlowBase:
        def __init__(self) -> None:
            self.hass: Any = None
            self.context: dict[str, Any] = {}
            self.created_entries: list[dict[str, Any]] = []

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            result = {"type": "create_entry", **deepcopy(kwargs)}
            self.created_entries.append(result)
            return result

    class ConfigFlow(_FlowBase):
        def __init_subclass__(
            cls, *, domain: str | None = None, **kwargs: Any
        ) -> None:
            super().__init_subclass__(**kwargs)
            cls.domain = domain

        async def async_set_unique_id(self, unique_id: str) -> None:
            self.context["unique_id"] = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

    class OptionsFlowWithReload(_FlowBase):
        config_entry: Any = None

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlowWithReload = OptionsFlowWithReload
    core.callback = lambda function: function
    entity_registry.async_get = lambda hass: hass.entity_registry
    helpers.entity_registry = entity_registry
    helpers.selector = selector
    selector.SelectSelectorConfig = _SelectorConfig
    selector.EntitySelectorConfig = _SelectorConfig
    selector.TextSelectorConfig = _SelectorConfig
    selector.SelectSelector = _Selector
    selector.EntitySelector = _Selector
    selector.TextSelector = _Selector
    homeassistant.config_entries = config_entries

    sys.modules.update(
        {
            "custom_components": custom_components,
            "custom_components.platform_sync": package,
            "voluptuous": vol,
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.core": core,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.helpers.selector": selector,
        }
    )

    counters = {"source_reads": 0, "target_reads": 0, "target_validations": 0}
    return counters


COUNTERS = install_stubs()
const = load("custom_components.platform_sync.const", "const.py")
models = load("custom_components.platform_sync.models", "models.py")
config = load("custom_components.platform_sync.config", "config.py")


sources_stub = ModuleType("custom_components.platform_sync.sources")


class _EmptyDashboardSourceError(RuntimeError):
    """Stub for the integration's fail-closed empty aggregate signal."""


async def _read_dashboard_source(_hass: Any, _dashboard: str, _view: str):
    return models.SourceSnapshot(frozenset({"light.dashboard"}))


async def _read_dashboard_sources(_hass: Any, pages: Any):
    pages = tuple(pages)
    assert pages, "dashboard aggregate validation requires selected pages"
    if any(view == "empty" for _dashboard, view in pages):
        raise _EmptyDashboardSourceError(
            "Selected Lovelace dashboard pages contain no entities"
        )
    return models.SourceSnapshot(frozenset({"light.dashboard"}))


async def _read_source(_hass: Any, sync_config: Any):
    COUNTERS["source_reads"] += 1
    if sync_config.source_kind is const.SourceKind.HOMEKIT:
        assert sync_config.homekit_source_entry_ids, (
            "HomeKit source validation requires explicit source entry IDs"
        )
        assert not sync_config.homekit_managed_entry_ids, (
            "HomeKit used only as a source must not require target-managed IDs"
        )
    return models.SourceSnapshot(frozenset({"light.platform_source"}))


sources_stub.EmptyDashboardSourceError = _EmptyDashboardSourceError
sources_stub.async_read_dashboard_source = _read_dashboard_source
sources_stub.async_read_dashboard_sources = _read_dashboard_sources
sources_stub.async_read_source = _read_source
sys.modules["custom_components.platform_sync.sources"] = sources_stub


targets_stub = ModuleType("custom_components.platform_sync.targets")


class _HomeKitSourceEntryMissingError(RuntimeError):
    pass


class _HomeKitSourceEntryUnavailableError(RuntimeError):
    pass


class _HomeKitSourceFilterUnsupportedError(RuntimeError):
    pass


class _EmptyHomeKitSourceError(RuntimeError):
    pass


async def _validate_homekit_source_entries(_hass: Any, requested_entry_ids: Any):
    requested = tuple(dict.fromkeys(requested_entry_ids))
    available = {
        entry.entry_id: entry
        for entry in _hass.config_entries.async_entries("homekit")
    }
    if not requested or set(requested) - set(available):
        raise _HomeKitSourceEntryMissingError
    entities: set[str] = set()
    for entry_id in requested:
        entry = available[entry_id]
        if getattr(entry, "disabled_by", None) is not None:
            raise _HomeKitSourceEntryUnavailableError
        entity_filter = (entry.options or {}).get(
            "filter", (entry.data or {}).get("filter", {})
        )
        if any(
            entity_filter.get(key)
            for key in (
                "include_domains",
                "include_entity_globs",
                "exclude_domains",
                "exclude_entities",
                "exclude_entity_globs",
            )
        ):
            raise _HomeKitSourceFilterUnsupportedError
        selected = set(entity_filter.get("include_entities", []))
        if not selected:
            raise _EmptyHomeKitSourceError
        entities.update(selected)
    return frozenset(entities)


def _validate_target_configuration(_hass: Any, sync_config: Any, platform: Any):
    if platform is const.TargetPlatform.HOMEKIT:
        available = {
            entry.entry_id: entry
            for entry in _hass.config_entries.async_entries("homekit")
        }
        for entry_id in sync_config.homekit_managed_entry_ids:
            entry = available[entry_id]
            if getattr(entry, "disabled_by", None) is not None:
                raise RuntimeError("disabled HomeKit target")
            if str(getattr(entry, "source", "")).casefold() == "import":
                raise RuntimeError("YAML/import HomeKit target")
            entity_filter = (entry.options or {}).get("filter")
            if (
                not isinstance(entity_filter, dict)
                or not entity_filter.get("include_entities")
                or any(
                    entity_filter.get(key)
                    for key in (
                        "include_domains",
                        "include_entity_globs",
                        "exclude_domains",
                        "exclude_entities",
                        "exclude_entity_globs",
                    )
                )
            ):
                raise RuntimeError("invalid HomeKit target filter")
    elif platform is const.TargetPlatform.MATTER:
        host = str(sync_config.matter_host).strip().casefold()
        if not host or host.startswith(("ftp://", "file://")):
            raise RuntimeError("invalid Matterbridge endpoint")


async def _read_target(_hass: Any, _config: Any, _platform: Any):
    COUNTERS["target_reads"] += 1
    return frozenset({"light.target"})


async def _validate_target(
    _hass: Any, _config: Any, _platform: Any, _expected: frozenset[str]
):
    COUNTERS["target_validations"] += 1
    return {"loaded": True}


targets_stub.async_read_target = _read_target
targets_stub.async_validate_target = _validate_target
targets_stub.EmptyHomeKitSourceError = _EmptyHomeKitSourceError
targets_stub.HomeKitSourceEntryMissingError = _HomeKitSourceEntryMissingError
targets_stub.HomeKitSourceEntryUnavailableError = (
    _HomeKitSourceEntryUnavailableError
)
targets_stub.HomeKitSourceFilterUnsupportedError = (
    _HomeKitSourceFilterUnsupportedError
)
targets_stub.async_validate_homekit_source_entries = _validate_homekit_source_entries
targets_stub.validate_target_configuration = _validate_target_configuration
sys.modules["custom_components.platform_sync.targets"] = targets_stub

flow_module = load("custom_components.platform_sync.config_flow", "config_flow.py")


class FakeDashboard:
    mode = "storage"

    def __init__(self, title: str, views: list[dict[str, Any]]) -> None:
        self.title = title
        self.url_path = "lovelace"
        self._config = {"views": views}

    async def async_load(self, _force: bool) -> dict[str, Any]:
        return deepcopy(self._config)


class FakeStates:
    def __init__(self, entity_ids: set[str]) -> None:
        self._entity_ids = entity_ids

    def async_entity_ids(self) -> list[str]:
        return sorted(self._entity_ids)


class FakeConfigEntries:
    def __init__(self) -> None:
        self.homekit_entries = [
            SimpleNamespace(
                entry_id="homekit-main",
                title="Main Bridge",
                state="loaded",
                data={},
                options={
                    "homekit_mode": "bridge",
                    "filter": {"include_entities": ["light.platform_source"]},
                },
            ),
            SimpleNamespace(
                entry_id="homekit-accessory",
                title="Independent Accessory",
                state="loaded",
                data={},
                options={
                    "homekit_mode": "accessory",
                    "filter": {"include_entities": ["sensor.accessory"]},
                },
            ),
        ]
        self.updated: list[dict[str, Any]] = []

    def async_entries(self, domain: str) -> list[Any]:
        return list(self.homekit_entries) if domain == "homekit" else []

    def async_update_entry(self, entry: Any, **updates: Any) -> None:
        self.updated.append({"entry": entry, **updates})


class FakeHass:
    def __init__(
        self,
        *,
        language: str = "en",
        dashboards: dict[str | None, Any] | None = None,
        entities: set[str] | None = None,
    ) -> None:
        self.config = SimpleNamespace(language=language)
        self.data = (
            {"lovelace": SimpleNamespace(dashboards=dashboards)}
            if dashboards is not None
            else {}
        )
        entity_ids = entities or {"light.manual", "light.extra"}
        self.states = FakeStates(entity_ids)
        self.entity_registry = SimpleNamespace(
            entities={entity_id: object() for entity_id in entity_ids}
        )
        self.config_entries = FakeConfigEntries()


def new_flow(hass: FakeHass):
    flow = flow_module.PlatformSyncConfigFlow()
    flow.hass = hass
    return flow


def schema_keys(result: dict[str, Any]) -> set[str]:
    return {marker.schema for marker in result["data_schema"].schema}


def schema_marker(result: dict[str, Any], key: str) -> _Marker:
    return next(
        marker
        for marker in result["data_schema"].schema
        if marker.schema == key
    )


def schema_value(result: dict[str, Any], key: str) -> Any:
    marker = schema_marker(result, key)
    return result["data_schema"].schema[marker]


def schema_default(result: dict[str, Any], key: str) -> Any:
    return deepcopy(schema_marker(result, key).default)


ASSERTIONS = 0


def check(condition: bool, message: str) -> None:
    global ASSERTIONS
    ASSERTIONS += 1
    if not condition:
        raise AssertionError(message)


async def choose_source(
    flow: Any, source: Any, *, enabled: bool = True
) -> dict[str, Any]:
    return await flow.async_step_user(
        {
            const.CONF_ENABLED: enabled,
            const.CONF_SOURCE_KIND: source.value,
        }
    )


async def check_dashboard_routes() -> None:
    dashboard = FakeDashboard(
        "Home",
        [
            {"title": "Home page", "path": "default-view"},
            {"title": "Rooms", "path": "rooms"},
        ],
    )
    flow = new_flow(FakeHass(dashboards={"lovelace": dashboard}))
    result = await choose_source(flow, const.SourceKind.DASHBOARD)
    check(result["step_id"] == "dashboard", "dashboard source uses page picker")
    picker = schema_value(result, flow_module.CONF_SOURCE_PAGE)
    check(
        picker.config["multiple"] is True,
        "dashboard page picker supports selecting multiple views",
    )
    options = picker.config["options"]
    dynamic = [
        option
        for option in options
        if option["value"] != flow_module.MANUAL_DASHBOARD_PAGE
    ]
    check(len(dynamic) == 2, "all storage dashboard views are listed")
    check(
        "lovelace/default-view" in dynamic[0]["label"]
        or "lovelace/default-view" in dynamic[1]["label"],
        "dashboard option labels include the unambiguous route",
    )
    for invalid_value in (None, 7, {"unexpected": "mapping"}, object()):
        result = await flow.async_step_dashboard(
            {flow_module.CONF_SOURCE_PAGE: invalid_value}
        )
        check(
            result["errors"].get(flow_module.CONF_SOURCE_PAGE)
            == "dashboard_required",
            "non-string and non-sequence dashboard selections are safely rejected",
        )
    result = await flow.async_step_dashboard({flow_module.CONF_SOURCE_PAGE: []})
    check(
        result["errors"].get(flow_module.CONF_SOURCE_PAGE)
        == "dashboard_required",
        "dashboard source requires at least one selected view",
    )
    result = await flow.async_step_dashboard(
        {flow_module.CONF_SOURCE_PAGE: ["not-a-known-dashboard-token"]}
    )
    check(
        result["errors"].get(flow_module.CONF_SOURCE_PAGE)
        == "dashboard_not_found",
        "dashboard source rejects unknown view tokens",
    )
    result = await flow.async_step_dashboard(
        {
            flow_module.CONF_SOURCE_PAGE: [
                dynamic[0]["value"],
                flow_module.MANUAL_DASHBOARD_PAGE,
            ]
        }
    )
    check(
        result["errors"].get(flow_module.CONF_SOURCE_PAGE)
        == "dashboard_selection_conflict",
        "manual dashboard fallback cannot be mixed with discovered views",
    )

    selected_tokens = [item["value"] for item in dynamic]
    selected_pages = [
        {
            "dashboard": flow._dashboard_pages[token][0],
            "view": flow._dashboard_pages[token][1],
        }
        for token in selected_tokens
    ]
    result = await flow.async_step_dashboard(
        {flow_module.CONF_SOURCE_PAGE: selected_tokens}
    )
    check(result["step_id"] == "targets", "dashboard views advance to targets")
    check(
        flow._values[const.CONF_SOURCE_PAGES] == selected_pages,
        "all selected dashboard views are staged in selection order",
    )
    await flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    result = await flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": [],
            "google_exclude": [],
        }
    )
    check(result["step_id"] == "confirm", "multi-view source reaches confirm")
    result = await flow.async_step_confirm({})
    check(
        result["data"][const.CONF_SOURCE_PAGES] == selected_pages,
        "saving a multi-view source persists every selected dashboard/view pair",
    )

    manual_fallback = new_flow(
        FakeHass(dashboards={"lovelace": dashboard})
    )
    await choose_source(manual_fallback, const.SourceKind.DASHBOARD)
    result = await manual_fallback.async_step_dashboard(
        {flow_module.CONF_SOURCE_PAGE: [flow_module.MANUAL_DASHBOARD_PAGE]}
    )
    check(
        result["step_id"] == "dashboard_path",
        "manual fallback alone opens the dashboard path fields",
    )

    empty_dashboard = FakeDashboard(
        "Empty dashboard", [{"title": "Empty", "path": "empty"}]
    )
    empty_flow = new_flow(
        FakeHass(dashboards={"lovelace": empty_dashboard})
    )
    result = await choose_source(empty_flow, const.SourceKind.DASHBOARD)
    empty_token = next(
        option["value"]
        for option in schema_value(result, flow_module.CONF_SOURCE_PAGE).config[
            "options"
        ]
        if option["value"] != flow_module.MANUAL_DASHBOARD_PAGE
    )
    result = await empty_flow.async_step_dashboard(
        {flow_module.CONF_SOURCE_PAGE: [empty_token]}
    )
    check(
        result["errors"].get(flow_module.CONF_SOURCE_PAGE) == "empty_source",
        "empty multi-view aggregate is shown as an empty-source safety error",
    )

    title_fallback_dashboard = FakeDashboard(
        "Title fallback dashboard",
        [
            {"title": "Null path title", "path": None},
            {"title": "Empty path title", "path": ""},
        ],
    )
    title_fallback_flow = new_flow(
        FakeHass(dashboards={"lovelace": title_fallback_dashboard})
    )
    result = await choose_source(
        title_fallback_flow, const.SourceKind.DASHBOARD
    )
    title_pairs = set(title_fallback_flow._dashboard_pages.values())
    check(
        {
            ("lovelace", "Null path title"),
            ("lovelace", "Empty path title"),
        }
        <= title_pairs,
        "dashboard enumeration uses the view title when path is null or empty",
    )

    fallback = new_flow(FakeHass(dashboards=None))
    result = await choose_source(fallback, const.SourceKind.DASHBOARD)
    check(result["step_id"] == "dashboard_path", "missing list uses path fallback")
    check(
        schema_keys(result)
        == {const.CONF_SOURCE_DASHBOARD, const.CONF_SOURCE_VIEW},
        "dashboard fallback contains only dashboard and view paths",
    )
    result = await fallback.async_step_dashboard_path(
        {
            const.CONF_SOURCE_DASHBOARD: "lovelace",
            const.CONF_SOURCE_VIEW: "custom-view",
        }
    )
    check(result["step_id"] == "targets", "valid path fallback advances")
    check(
        fallback._values[const.CONF_SOURCE_PAGES]
        == [{"dashboard": "lovelace", "view": "custom-view"}],
        "manual path fallback stores the same canonical source-pages format",
    )


async def check_manual_and_platform_routes() -> None:
    flow = new_flow(FakeHass())
    result = await choose_source(flow, const.SourceKind.MANUAL)
    check(result["step_id"] == "manual", "manual source opens entity picker")
    result = await flow.async_step_manual({const.CONF_SOURCE_ENTITIES: []})
    check(
        result["errors"].get(const.CONF_SOURCE_ENTITIES) == "entity_required",
        "manual source requires at least one entity",
    )
    result = await flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    check(result["step_id"] == "targets", "valid manual source advances")

    for source in (
        const.SourceKind.GOOGLE,
        const.SourceKind.MATTER,
    ):
        platform_flow = new_flow(FakeHass())
        result = await choose_source(platform_flow, source)
        check(
            result["step_id"] == "targets",
            f"{source.value} source skips source-detail steps",
        )


async def check_homekit_source_selection() -> None:
    hass = FakeHass(language="en")
    flow = new_flow(hass)
    result = await choose_source(flow, const.SourceKind.HOMEKIT)
    check(
        result["step_id"] == "homekit_source",
        "HomeKit source opens its integration-entry picker before targets",
    )
    check(
        schema_keys(result) == {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS},
        "HomeKit source step contains only the source-entry selection",
    )
    picker = schema_value(result, const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
    check(picker.config["multiple"] is True, "HomeKit source picker is multi-select")
    check(
        picker.config["mode"] == "list",
        "HomeKit source picker renders as a direct checkbox list",
    )
    labels = {item["value"]: item["label"] for item in picker.config["options"]}
    check(
        "Bridge" in labels["homekit-main"]
        and "Accessory" in labels["homekit-accessory"],
        "HomeKit choices distinguish Bridge and Accessory integration entries",
    )

    for invalid_value in (None, "homekit-main", [], [""], [7], object()):
        result = await flow.async_step_homekit_source(
            {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: invalid_value}
        )
        check(
            result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
            == "homekit_source_entry_required",
            "malformed or empty HomeKit source selections are rejected",
        )

    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["missing-entry"]}
    )
    check(
        result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
        == "homekit_source_entry_not_found",
        "a missing HomeKit source entry fails closed",
    )

    hass.config_entries.homekit_entries[0].state = "setup_retry"
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["step_id"] == "targets",
        "a structurally valid but transiently unloaded HomeKit source can be saved",
    )
    hass.config_entries.homekit_entries[0].state = "loaded"

    hass.config_entries.homekit_entries[0].disabled_by = "user"
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
        == "homekit_source_entry_unavailable",
        "a disabled HomeKit source entry is rejected as a permanent selection error",
    )
    del hass.config_entries.homekit_entries[0].disabled_by

    main_filter = hass.config_entries.homekit_entries[0].options["filter"]
    main_filter["exclude_entities"] = ["light.platform_source"]
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
        == "homekit_source_filter_unsupported",
        "a HomeKit source entry with competing filters fails closed",
    )
    main_filter.pop("exclude_entities")

    main_filter["include_entities"] = []
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
        == "empty_source",
        "an empty selected HomeKit source entry fails closed",
    )
    main_filter["include_entities"] = ["light.platform_source"]

    original_reader = flow_module.async_validate_homekit_source_entries

    async def unexpected_failure(_hass: Any, _entry_ids: Any):
        raise RuntimeError("simulated unexpected read failure")

    flow_module.async_validate_homekit_source_entries = unexpected_failure
    try:
        result = await flow.async_step_homekit_source(
            {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
        )
    finally:
        flow_module.async_validate_homekit_source_entries = original_reader
    check(
        result["errors"].get(const.CONF_HOMEKIT_SOURCE_ENTRY_IDS)
        == "homekit_source_entry_unavailable",
        "an unexpected HomeKit source read failure stays in a fail-closed form",
    )

    hass.config_entries.homekit_entries[0].source = "import"
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["step_id"] == "targets",
        "a YAML/import HomeKit entry remains valid as a read-only source",
    )
    del hass.config_entries.homekit_entries[0].source

    selected = ["homekit-accessory", "homekit-main"]
    result = await flow.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: selected}
    )
    check(result["step_id"] == "targets", "valid HomeKit selection advances")
    check(
        flow._values[const.CONF_HOMEKIT_SOURCE_ENTRY_IDS] == selected,
        "all selected HomeKit source entries persist in user order",
    )

    await flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    result = await flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": [],
            "google_exclude": [],
        }
    )
    check(result["step_id"] == "confirm", "HomeKit source reaches review")
    summary = result["description_placeholders"]["summary"]
    check(
        "Independent Accessory" in summary and "Main Bridge" in summary,
        "review summary names every selected HomeKit source entry",
    )


async def check_target_selection_and_fields() -> None:
    flow = new_flow(FakeHass())
    await choose_source(flow, const.SourceKind.MANUAL)
    await flow.async_step_manual({const.CONF_SOURCE_ENTITIES: ["light.manual"]})
    result = await flow.async_step_targets({const.CONF_TARGET_PLATFORMS: []})
    check(
        result["errors"].get(const.CONF_TARGET_PLATFORMS) == "target_required",
        "at least one target is required",
    )
    result = await flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    keys = schema_keys(result)
    check(result["step_id"] == "platform_settings", "targets open settings")
    check(
        keys
        == {
            const.CONF_GOOGLE_CONFIG_PATH,
            "google_include",
            "google_exclude",
        },
        "only selected Google target fields are shown",
    )

    matter_source = new_flow(FakeHass())
    await choose_source(matter_source, const.SourceKind.MATTER)
    result = await matter_source.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    keys = schema_keys(result)
    check(
        const.CONF_MATTER_HOST in keys and const.CONF_MATTER_PORT in keys,
        "Matterbridge used only as source still receives connection fields",
    )
    check(
        "matter_include" not in keys and "matter_exclude" not in keys,
        "source-only Matterbridge does not expose target write rules",
    )

    homekit_source = new_flow(FakeHass())
    await choose_source(homekit_source, const.SourceKind.HOMEKIT, enabled=True)
    result = await homekit_source.async_step_homekit_source(
        {const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: ["homekit-main"]}
    )
    check(
        result["step_id"] == "targets",
        "HomeKit source selection precedes target selection",
    )
    result = await homekit_source.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    check(
        const.CONF_HOMEKIT_MANAGED_ENTRY_IDS not in schema_keys(result),
        "source-only HomeKit does not require managed target entries",
    )
    result = await homekit_source.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": [],
            "google_exclude": [],
        }
    )
    check(
        result["step_id"] == "confirm",
        "enabled source-only HomeKit passes without managed target IDs",
    )


async def check_hints_and_validation() -> None:
    flow = new_flow(FakeHass(language="en"))
    await choose_source(flow, const.SourceKind.MANUAL)
    await flow.async_step_manual({const.CONF_SOURCE_ENTITIES: ["light.manual"]})
    result = await flow.async_step_targets(
        {
            const.CONF_TARGET_PLATFORMS: [
                const.TargetPlatform.GOOGLE.value,
                const.TargetPlatform.MATTER.value,
            ]
        }
    )
    hint = result["description_placeholders"]["prerequisites"]
    check("Google Home" in hint, "Google prerequisite hint is conditional")
    check("Matterbridge" in hint, "Matterbridge prerequisite hint is conditional")

    conflict = new_flow(FakeHass())
    await choose_source(conflict, const.SourceKind.MANUAL, enabled=True)
    await conflict.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await conflict.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    result = await conflict.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": ["light.extra"],
            "google_exclude": ["light.extra"],
        }
    )
    check(
        result["errors"].get("google_exclude") == "include_exclude_conflict",
        "the same entity cannot be included and excluded",
    )


async def check_disabled_and_final_save() -> None:
    for key in COUNTERS:
        COUNTERS[key] = 0
    flow = new_flow(FakeHass())
    result = await choose_source(flow, const.SourceKind.GOOGLE, enabled=False)
    check(
        result["type"] == "create_entry",
        "a newly disabled ConfigFlow finishes directly from the first step",
    )
    check(
        "step_id" not in result,
        "a newly disabled ConfigFlow never enters targets or confirm",
    )
    check(
        COUNTERS == {
            "source_reads": 0,
            "target_reads": 0,
            "target_validations": 0,
        },
        "the direct disabled path performs no platform readiness reads",
    )
    check(len(flow.created_entries) == 1, "the direct disabled path saves once")

    confirm_flow = new_flow(FakeHass())
    await choose_source(confirm_flow, const.SourceKind.MANUAL, enabled=True)
    await confirm_flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await confirm_flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    result = await confirm_flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": [],
            "google_exclude": [],
        }
    )
    check(result["step_id"] == "confirm", "enabled flow reaches confirmation")
    check(
        not confirm_flow.created_entries,
        "enabled configuration is not saved before confirmation",
    )
    result = await confirm_flow.async_step_confirm({})
    check(result["type"] == "create_entry", "confirmation performs the save")
    check(len(confirm_flow.created_entries) == 1, "confirmation saves once")


async def check_runtime_readiness_is_deferred() -> None:
    """Transient platform startup state never blocks a complete saved form."""
    for key in COUNTERS:
        COUNTERS[key] = 0
    flow = new_flow(FakeHass())
    await choose_source(flow, const.SourceKind.MANUAL, enabled=True)
    await flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await flow.async_step_targets(
        {
            const.CONF_TARGET_PLATFORMS: [
                const.TargetPlatform.GOOGLE.value,
                const.TargetPlatform.MATTER.value,
            ]
        }
    )
    result = await flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: (
                "google_assistant_entity_config.yaml"
            ),
            const.CONF_MATTER_HOST: "matterbridge.local",
            const.CONF_MATTER_PORT: 8283,
            const.CONF_MATTER_PASSWORD: "",
            "google_include": [],
            "google_exclude": [],
            "matter_include": [],
            "matter_exclude": [],
        }
    )
    check(
        result["step_id"] == "confirm",
        "transient Google and Matterbridge runtime state is deferred to background retry",
    )
    check(
        COUNTERS
        == {
            "source_reads": 0,
            "target_reads": 0,
            "target_validations": 0,
        },
        "Config Flow performs no full runtime convergence probe before saving",
    )

    invalid_matter = new_flow(FakeHass())
    await choose_source(invalid_matter, const.SourceKind.MANUAL, enabled=True)
    await invalid_matter.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await invalid_matter.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.MATTER.value]}
    )
    result = await invalid_matter.async_step_platform_settings(
        {
            const.CONF_MATTER_HOST: "ftp://unsupported.example",
            const.CONF_MATTER_PORT: 8283,
            const.CONF_MATTER_PASSWORD: "",
            "matter_include": [],
            "matter_exclude": [],
        }
    )
    check(
        result["errors"].get("base") == "invalid_matter_endpoint",
        "a permanently malformed Matterbridge endpoint is rejected locally",
    )

    invalid_homekit_hass = FakeHass()
    invalid_homekit_hass.config_entries.homekit_entries[0].options["filter"][
        "include_domains"
    ] = ["light"]
    invalid_homekit = new_flow(invalid_homekit_hass)
    await choose_source(invalid_homekit, const.SourceKind.MANUAL, enabled=True)
    await invalid_homekit.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await invalid_homekit.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value]}
    )
    result = await invalid_homekit.async_step_platform_settings(
        {
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["homekit-main"],
            "homekit_include": [],
            "homekit_exclude": [],
        }
    )
    check(
        result["errors"].get("base")
        == "homekit_target_configuration_invalid",
        "a permanently ambiguous HomeKit target filter is rejected locally",
    )

    imported_target_hass = FakeHass()
    imported_target_hass.config_entries.homekit_entries[0].source = "import"
    imported_target = new_flow(imported_target_hass)
    await choose_source(imported_target, const.SourceKind.MANUAL, enabled=True)
    await imported_target.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await imported_target.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value]}
    )
    result = await imported_target.async_step_platform_settings(
        {
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["homekit-main"],
            "homekit_include": [],
            "homekit_exclude": [],
        }
    )
    check(
        result["errors"].get("base")
        == "homekit_target_configuration_invalid",
        "a YAML/import HomeKit entry can be a source but never a writable target",
    )


async def _create_disabled_entry(language: str) -> tuple[Any, dict[str, Any]]:
    """Complete a safe inert flow and return its final create-entry result."""
    flow = new_flow(FakeHass(language=language))
    result = await flow.async_step_user()
    check(
        schema_keys(result) == {const.CONF_ENABLED, const.CONF_SOURCE_KIND},
        "the first step contains only enabled and source kind",
    )
    check(
        "description_placeholders" not in result,
        "the first step has no page-level description",
    )
    result = await choose_source(
        flow, const.SourceKind.MANUAL, enabled=False
    )
    check(
        result["type"] == "create_entry",
        "localized disabled title flow finishes immediately",
    )
    return flow, result


async def check_fixed_localized_titles() -> None:
    _english_flow, result = await _create_disabled_entry("en")
    check(
        result["title"] == const.DEFAULT_ENTRY_TITLE_EN,
        "English system language creates the fixed English entry title",
    )
    _traditional_flow, result = await _create_disabled_entry("zh-Hant")
    check(
        result["title"] == const.DEFAULT_ENTRY_TITLE_ZH_HANT,
        "Traditional Chinese creates the fixed Traditional Chinese entry title",
    )


async def check_options_disable_preserves_configuration() -> None:
    hass = FakeHass(language="en")
    existing_rules = {
        "google": {
            "include": ["light.extra"],
            "exclude": ["sensor.legacy_excluded"],
        },
        "homekit": {"include": [], "exclude": []},
        "matter": {"include": [], "exclude": []},
    }
    entry = SimpleNamespace(
        title="Owner supplied legacy title",
        data={},
        options={
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.manual"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            const.CONF_SOURCE_PAGES: [
                {"dashboard": "lovelace", "view": "default-view"},
                {"dashboard": "lovelace", "view": "rooms"},
            ],
            const.CONF_USER_RULES: deepcopy(existing_rules),
        },
    )
    options_flow = flow_module.PlatformSyncOptionsFlow()
    options_flow.hass = hass
    options_flow.config_entry = entry
    result = await options_flow.async_step_init()
    check(
        schema_keys(result) == {const.CONF_ENABLED, const.CONF_SOURCE_KIND},
        "OptionsFlow also has no profile-name field",
    )
    result = await options_flow.async_step_init(
        {
            const.CONF_ENABLED: False,
            # A source change submitted together with disabling must not replace
            # the already configured source or any of its dependent settings.
            const.CONF_SOURCE_KIND: const.SourceKind.MATTER.value,
        }
    )
    check(
        result["type"] == "create_entry" and "step_id" not in result,
        "disabling OptionsFlow finishes directly from the first step",
    )
    saved = result["data"]
    check(saved[const.CONF_ENABLED] is False, "OptionsFlow stores the disabled gate")
    check(
        saved[const.CONF_SOURCE_KIND] == const.SourceKind.MANUAL.value
        and saved[const.CONF_SOURCE_ENTITIES] == ["light.manual"],
        "disabling preserves the existing source and source details",
    )
    check(
        saved[const.CONF_SOURCE_PAGES]
        == [
            {"dashboard": "lovelace", "view": "default-view"},
            {"dashboard": "lovelace", "view": "rooms"},
        ],
        "disabling preserves every configured dashboard source view",
    )
    check(
        saved[const.CONF_TARGET_PLATFORMS]
        == [const.TargetPlatform.GOOGLE.value]
        and saved[const.CONF_GOOGLE_CONFIG_PATH]
        == "google_assistant_entity_config.yaml",
        "disabling preserves existing targets and platform settings",
    )
    check(
        saved[const.CONF_USER_RULES] == existing_rules,
        "disabling preserves every existing include/exclude rule",
    )
    check(
        entry.title == "Owner supplied legacy title"
        and not hass.config_entries.updated,
        "OptionsFlow never changes the config-entry title",
    )

    # Simulate opening Configure again after the disabled options were saved.
    entry.options = deepcopy(saved)
    reenable_flow = flow_module.PlatformSyncOptionsFlow()
    reenable_flow.hass = hass
    reenable_flow.config_entry = entry
    await reenable_flow.async_step_init()
    result = await reenable_flow.async_step_init(
        {
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        }
    )
    check(
        result["step_id"] == "manual",
        "re-enabling expands the saved source-specific configuration steps",
    )


async def check_options_complete_persistence() -> None:
    """Every visible and hidden option survives errors and future edits."""
    hass = FakeHass(
        entities={
            "light.manual",
            "light.extra",
            "light.new",
            "sensor.homekit_keep",
            "sensor.matter_keep",
        }
    )
    data_rules = {
        "google": {"include": ["light.extra"], "exclude": []},
        "homekit": {"include": ["sensor.homekit_keep"], "exclude": []},
        "matter": {"include": ["sensor.matter_keep"], "exclude": []},
    }
    # A historical partial options object must override only the operation it
    # actually contains, not erase HomeKit and Matter rules stored in data.
    entry = SimpleNamespace(
        title="Cross-Platform Device Sync",
        data={const.CONF_USER_RULES: deepcopy(data_rules)},
        options={
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.manual"],
            const.CONF_TARGET_PLATFORMS: [
                const.TargetPlatform.GOOGLE.value,
                const.TargetPlatform.HOMEKIT.value,
                const.TargetPlatform.MATTER.value,
            ],
            const.CONF_GOOGLE_CONFIG_PATH: "old.yaml",
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["homekit-main"],
            const.CONF_MATTER_HOST: "matterbridge.local",
            const.CONF_MATTER_PORT: 8283,
            const.CONF_USER_RULES: {
                "google": {"include": ["light.extra"]}
            },
        },
    )
    options_flow = flow_module.PlatformSyncOptionsFlow()
    options_flow.hass = hass
    options_flow.config_entry = entry
    await options_flow.async_step_init()
    await options_flow.async_step_init(
        {
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        }
    )
    await options_flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    result = await options_flow.async_step_targets(
        {
            const.CONF_TARGET_PLATFORMS: [
                const.TargetPlatform.GOOGLE.value,
                const.TargetPlatform.HOMEKIT.value,
                const.TargetPlatform.MATTER.value,
            ]
        }
    )
    check(
        schema_default(result, "homekit_include")
        == ["sensor.homekit_keep"]
        and schema_default(result, "matter_include")
        == ["sensor.matter_keep"],
        "partial historical user_rules are deep-merged per platform",
    )

    invalid_input = {
        const.CONF_GOOGLE_CONFIG_PATH: "../bad.yaml",
        const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: [
            "homekit-main",
            "homekit-accessory",
        ],
        const.CONF_MATTER_HOST: "192.0.2.44",
        const.CONF_MATTER_PORT: 9123,
        const.CONF_MATTER_PASSWORD: "test-front-end-password",
        "google_include": ["light.new"],
        "google_exclude": [],
        "homekit_include": ["sensor.homekit_keep"],
        "homekit_exclude": [],
        "matter_include": ["sensor.matter_keep"],
        "matter_exclude": [],
    }
    result = await options_flow.async_step_platform_settings(invalid_input)
    check(
        result["errors"].get(const.CONF_GOOGLE_CONFIG_PATH) == "invalid_path",
        "invalid Google path redraws the platform form",
    )
    check(
        schema_default(result, const.CONF_GOOGLE_CONFIG_PATH) == "../bad.yaml"
        and schema_default(result, const.CONF_MATTER_HOST) == "192.0.2.44"
        and schema_default(result, const.CONF_MATTER_PORT) == 9123
        and schema_default(result, const.CONF_MATTER_PASSWORD)
        == "test-front-end-password"
        and schema_default(result, "google_include") == ["light.new"]
        and schema_default(result, const.CONF_HOMEKIT_MANAGED_ENTRY_IDS)
        == ["homekit-main", "homekit-accessory"],
        "validation redraw preserves every value entered on the current page",
    )

    valid_input = deepcopy(invalid_input)
    valid_input[const.CONF_GOOGLE_CONFIG_PATH] = (
        "google_assistant_entity_config.yaml"
    )
    result = await options_flow.async_step_platform_settings(valid_input)
    check(result["step_id"] == "confirm", "corrected settings reach confirmation")
    saved_result = await options_flow.async_step_confirm({})
    saved = saved_result["data"]
    check(
        saved[const.CONF_GOOGLE_CONFIG_PATH]
        == "google_assistant_entity_config.yaml"
        and saved[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["homekit-main", "homekit-accessory"]
        and saved[const.CONF_MATTER_HOST] == "192.0.2.44"
        and saved[const.CONF_MATTER_PORT] == 9123
        and saved[const.CONF_MATTER_PASSWORD]
        == "test-front-end-password",
        "the complete target configuration is saved as one snapshot",
    )
    check(
        saved[const.CONF_USER_RULES]["homekit"]["include"]
        == ["sensor.homekit_keep"]
        and saved[const.CONF_USER_RULES]["matter"]["include"]
        == ["sensor.matter_keep"],
        "the complete snapshot retains every platform rule",
    )

    # Reopen the exact saved options and verify all platform fields are filled.
    entry.options = deepcopy(saved)
    reopened = flow_module.PlatformSyncOptionsFlow()
    reopened.hass = hass
    reopened.config_entry = entry
    await reopened.async_step_init()
    await reopened.async_step_init(
        {
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        }
    )
    await reopened.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    result = await reopened.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: saved[const.CONF_TARGET_PLATFORMS]}
    )
    check(
        schema_default(result, const.CONF_GOOGLE_CONFIG_PATH)
        == saved[const.CONF_GOOGLE_CONFIG_PATH]
        and schema_default(result, const.CONF_HOMEKIT_MANAGED_ENTRY_IDS)
        == saved[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        and schema_default(result, const.CONF_MATTER_HOST)
        == saved[const.CONF_MATTER_HOST]
        and schema_default(result, const.CONF_MATTER_PORT)
        == saved[const.CONF_MATTER_PORT]
        and schema_default(result, const.CONF_MATTER_PASSWORD)
        == saved[const.CONF_MATTER_PASSWORD],
        "reopening Configure repopulates every platform connection field",
    )

    hidden_flow = flow_module.PlatformSyncOptionsFlow()
    hidden_flow.hass = hass
    hidden_flow.config_entry = entry
    await hidden_flow.async_step_init()
    await hidden_flow.async_step_init(
        {
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        }
    )
    await hidden_flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    result = await hidden_flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    check(
        schema_keys(result)
        == {
            const.CONF_GOOGLE_CONFIG_PATH,
            "google_include",
            "google_exclude",
        },
        "only the currently selected target fields are rendered during editing",
    )
    await hidden_flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: (
                "google_assistant_entity_config.yaml"
            ),
            "google_include": ["light.new"],
            "google_exclude": [],
        }
    )
    hidden_saved = (await hidden_flow.async_step_confirm({}))["data"]
    check(
        hidden_saved[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == saved[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        and hidden_saved[const.CONF_MATTER_HOST]
        == saved[const.CONF_MATTER_HOST]
        and hidden_saved[const.CONF_MATTER_PORT]
        == saved[const.CONF_MATTER_PORT]
        and hidden_saved[const.CONF_MATTER_PASSWORD]
        == saved[const.CONF_MATTER_PASSWORD],
        "unselected target connection settings remain stored but hidden",
    )
    check(
        hidden_saved[const.CONF_USER_RULES]["homekit"]
        == saved[const.CONF_USER_RULES]["homekit"]
        and hidden_saved[const.CONF_USER_RULES]["matter"]
        == saved[const.CONF_USER_RULES]["matter"],
        "unselected target include and exclude rules remain stored but inactive",
    )

    malformed_entry = SimpleNamespace(
        title="Cross-Platform Device Sync",
        data={},
        options={
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.manual"],
            const.CONF_SOURCE_PAGES: "not-a-page-list",
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
            const.CONF_MATTER_PORT: {"invalid": True},
            const.CONF_HOMEKIT_SOURCE_ENTRY_IDS: "not-a-list",
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: [7],
        },
    )
    malformed_flow = flow_module.PlatformSyncOptionsFlow()
    malformed_flow.hass = hass
    malformed_flow.config_entry = malformed_entry
    await malformed_flow.async_step_init()
    await malformed_flow.async_step_init(
        {
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        }
    )
    await malformed_flow.async_step_manual(
        {const.CONF_SOURCE_ENTITIES: ["light.manual"]}
    )
    await malformed_flow.async_step_targets(
        {const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value]}
    )
    await malformed_flow.async_step_platform_settings(
        {
            const.CONF_GOOGLE_CONFIG_PATH: "google_assistant_entity_config.yaml",
            "google_include": [],
            "google_exclude": [],
        }
    )
    repaired = (await malformed_flow.async_step_confirm({}))["data"]
    check(
        repaired[const.CONF_MATTER_PORT] == const.DEFAULT_MATTER_PORT
        and repaired[const.CONF_HOMEKIT_SOURCE_ENTRY_IDS] == []
        and repaired[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS] == []
        and repaired[const.CONF_SOURCE_PAGES]
        == [
            {
                "dashboard": const.DEFAULT_SOURCE_DASHBOARD,
                "view": const.DEFAULT_SOURCE_VIEW,
            }
        ],
        "malformed hidden legacy fields are safely canonicalized during an unrelated edit",
    )


async def main() -> None:
    check(
        flow_module.PlatformSyncConfigFlow.VERSION == 4
        and flow_module.PlatformSyncConfigFlow.MINOR_VERSION == 3,
        "ConfigFlow schema version is 4.3",
    )
    await check_dashboard_routes()
    await check_manual_and_platform_routes()
    await check_homekit_source_selection()
    await check_target_selection_and_fields()
    await check_hints_and_validation()
    await check_disabled_and_final_save()
    await check_runtime_readiness_is_deferred()
    await check_fixed_localized_titles()
    await check_options_disable_preserves_configuration()
    await check_options_complete_persistence()
    print(f"PASS: {ASSERTIONS} config-flow acceptance assertions")


if __name__ == "__main__":
    asyncio.run(main())
