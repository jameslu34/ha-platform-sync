"""Dependency-light acceptance checks for target adapters and safety gates.

Run with ``python tests/simulate_adapter_acceptance.py``.  The test deliberately
uses only the standard library and small Home Assistant stubs so it can run on
the deployment workstation without installing Home Assistant or pytest.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
from typing import Any


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "platform_sync"
LEGACY_PROFILE_NAME = "profile_name"
TITLE_EN = "Cross-Platform Device Sync"
TITLE_ZH_HANT = "裝置平台同步"


def load(name: str, filename: str) -> ModuleType:
    """Load one integration module without importing its package __init__."""
    spec = importlib.util.spec_from_file_location(name, PACKAGE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def install_stubs() -> None:
    """Install the minimum Home Assistant surface used by these modules."""
    custom_components = ModuleType("custom_components")
    package = ModuleType("custom_components.platform_sync")
    package.__path__ = [str(PACKAGE)]
    sys.modules.update(
        {
            "custom_components": custom_components,
            "custom_components.platform_sync": package,
        }
    )

    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    const = ModuleType("homeassistant.const")
    core = ModuleType("homeassistant.core")
    helpers = ModuleType("homeassistant.helpers")
    config_validation = ModuleType("homeassistant.helpers.config_validation")
    dispatcher = ModuleType("homeassistant.helpers.dispatcher")
    event = ModuleType("homeassistant.helpers.event")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    components = ModuleType("homeassistant.components")
    lovelace = ModuleType("homeassistant.components.lovelace")
    lovelace_const = ModuleType("homeassistant.components.lovelace.const")
    util = ModuleType("homeassistant.util")
    yaml_module = ModuleType("homeassistant.util.yaml")

    class ConfigEntry:
        @classmethod
        def __class_getitem__(cls, _item: Any) -> type[ConfigEntry]:
            return cls

    class ConfigEntryState:
        LOADED = "loaded"

    class ConfigEntryChange:
        ADDED = SimpleNamespace(value="added")
        REMOVED = SimpleNamespace(value="removed")
        UPDATED = SimpleNamespace(value="updated")

    class SupportsResponse:
        ONLY = "only"
        OPTIONAL = "optional"

    class CoreState:
        starting = object()
        running = object()

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigEntryChange = ConfigEntryChange
    config_entries.ConfigEntryState = ConfigEntryState
    config_entries.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"
    const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    core.HomeAssistant = object
    core.CoreState = CoreState
    core.ServiceCall = object
    core.SupportsResponse = SupportsResponse
    core.callback = lambda function: function
    config_validation.config_entry_only_config_schema = (
        lambda domain: ("config_entry_only", domain)
    )
    dispatcher.async_dispatcher_connect = lambda *_args, **_kwargs: lambda: None
    event.async_track_time_interval = lambda *_args, **_kwargs: lambda: None
    entity_registry.EVENT_ENTITY_REGISTRY_UPDATED = "entity_registry_updated"
    helpers.entity_registry = entity_registry
    helpers.config_validation = config_validation
    helpers.dispatcher = dispatcher
    lovelace_const.EVENT_LOVELACE_UPDATED = "lovelace_updated"
    yaml_module.load_yaml = lambda _path: {}
    yaml_module.save_yaml = lambda _path, _value: None
    util.yaml = yaml_module
    homeassistant.config_entries = config_entries

    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.const": const,
            "homeassistant.core": core,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.config_validation": config_validation,
            "homeassistant.helpers.dispatcher": dispatcher,
            "homeassistant.helpers.event": event,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.components": components,
            "homeassistant.components.lovelace": lovelace,
            "homeassistant.components.lovelace.const": lovelace_const,
            "homeassistant.util": util,
            "homeassistant.util.yaml": yaml_module,
        }
    )


install_stubs()
const = load("custom_components.platform_sync.const", "const.py")
models = load("custom_components.platform_sync.models", "models.py")
runtime_config_module = load(
    "custom_components.platform_sync.config", "config.py"
)

targets = load("custom_components.platform_sync.targets", "targets.py")

sources_stub = ModuleType("custom_components.platform_sync.sources")
sources_stub.async_read_source = None
sources_stub.async_find_apple_tv_entities = None
sys.modules["custom_components.platform_sync.sources"] = sources_stub
manager_module = load("custom_components.platform_sync.manager", "manager.py")
integration_module = load("custom_components.platform_sync.__init__", "__init__.py")
diagnostics_module = load(
    "custom_components.platform_sync.diagnostics", "diagnostics.py"
)


class FakeEntry:
    """Small mutable stand-in for a Home Assistant ConfigEntry."""

    def __init__(
        self,
        entry_id: str,
        *,
        options: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        state: str = "loaded",
        domain: str = "homekit",
        title: str | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.options = deepcopy(options or {})
        self.data = deepcopy(data or {})
        self.state = state
        self.domain = domain
        self.title = title or entry_id


class FakeConfigEntries:
    def __init__(self, homekit_entries: list[FakeEntry]) -> None:
        self.homekit_entries = homekit_entries
        self.updated: list[str] = []
        self.reloaded: list[str] = []

    def async_entries(self, domain: str) -> list[FakeEntry]:
        return list(self.homekit_entries) if domain == "homekit" else []

    def async_update_entry(self, entry: FakeEntry, *, options: dict[str, Any]) -> None:
        entry.options = deepcopy(options)
        self.updated.append(entry.entry_id)

    async def async_reload(self, entry_id: str) -> bool:
        self.reloaded.append(entry_id)
        return True


class FakeHass:
    def __init__(self, entries: list[FakeEntry]) -> None:
        self.config_entries = FakeConfigEntries(entries)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_config_entry_only_schema() -> int:
    """Require YAML setup to fail closed in favor of the config flow."""
    check(
        integration_module.CONFIG_SCHEMA == ("config_entry_only", const.DOMAIN),
        "integration declares a config-entry-only schema",
    )
    return 1


async def check_homekit_adapter() -> int:
    nested = FakeEntry(
        "nested",
        options={
            "filter": {
                "include_entities": ["light.nested"],
                "include_domains": ["light"],
                "exclude_entities": ["sensor.keep_excluded"],
            },
            "include_entities": ["light.legacy_must_not_win"],
            "mode": "bridge",
        },
        data={"include_entities": ["light.data_must_not_win"]},
    )
    check(
        targets._homekit_entities(nested) == {"light.nested"},
        "HomeKit nested options.filter.include_entities must take precedence",
    )

    legacy_options = FakeEntry(
        "legacy-options", options={"include_entities": ["switch.legacy_options"]}
    )
    legacy_data = FakeEntry(
        "legacy-data", data={"include_entities": ["switch.legacy_data"]}
    )
    check(
        targets._homekit_entities(legacy_options) == {"switch.legacy_options"},
        "HomeKit legacy options fallback",
    )
    check(
        targets._homekit_entities(legacy_data) == {"switch.legacy_data"},
        "HomeKit legacy data fallback",
    )

    main = FakeEntry(
        "main",
        options={
            "filter": {
                "include_entities": ["light.one", "switch.old"],
                "include_domains": ["light"],
                "include_entity_globs": ["sensor.*"],
                "exclude_entities": ["sensor.do_not_touch"],
                "exclude_entity_globs": ["binary_sensor.*"],
            },
            "entity_config": {"light.one": {"name": "保留名稱"}},
            "mode": "bridge",
        },
    )
    accessory = FakeEntry(
        "accessory",
        options={
            "filter": {
                "include_entities": ["lock.front"],
                "exclude_domains": ["camera"],
            },
            "entity_config": {"lock.front": {"linked_battery_sensor": "sensor.battery"}},
            "mode": "accessory",
        },
    )
    original_main = deepcopy(main.options)
    original_accessory = deepcopy(accessory.options)
    hass = FakeHass([main, accessory])
    config = SimpleNamespace(homekit_managed_entry_ids=("main", "accessory"))
    await targets._apply_homekit(
        hass,
        config,
        frozenset({"light.one", "sensor.new", "lock.front"}),
    )
    check(
        main.options["filter"]["include_entities"] == ["light.one", "sensor.new"],
        "HomeKit main Bridge nested include_entities write",
    )
    check(
        accessory.options["filter"]["include_entities"] == ["lock.front"],
        "HomeKit Accessory nested include_entities write",
    )
    check(
        "include_entities" not in main.options and "include_entities" not in accessory.options,
        "HomeKit writer must not create a top-level include_entities",
    )
    for key in targets.HOMEKIT_COMPETING_SOURCE_FILTER_KEYS:
        check(
            main.options["filter"][key] == [],
            f"HomeKit main competing filter key {key} must be cleared",
        )
    check(
        main.options["entity_config"] == original_main["entity_config"]
        and main.options["mode"] == original_main["mode"],
        "HomeKit main non-filter options must be preserved",
    )
    check(
        accessory.options["filter"]["exclude_domains"] == []
        and accessory.options["entity_config"] == original_accessory["entity_config"]
        and accessory.options["mode"] == original_accessory["mode"],
        "HomeKit Accessory filter/options must be preserved",
    )
    check(
        not any(key in main.options for key in targets.HOMEKIT_FILTER_KEYS),
        "HomeKit writer removes every legacy top-level filter key",
    )
    check(
        hass.config_entries.updated == ["accessory", "main"]
        and hass.config_entries.reloaded == ["main", "accessory"],
        "Only managed HomeKit entries must be updated and reloaded",
    )

    fail_closed_hass = FakeHass([main])
    empty_managed_config = SimpleNamespace(homekit_managed_entry_ids=())
    try:
        await targets.async_read_target(
            fail_closed_hass,
            empty_managed_config,
            const.TargetPlatform.HOMEKIT,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Empty HomeKit managed-entry IDs must fail closed during readback"
        )
    try:
        await targets._apply_homekit(
            fail_closed_hass,
            empty_managed_config,
            frozenset({"light.one"}),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Empty HomeKit managed-entry IDs must fail closed")
    check(
        not fail_closed_hass.config_entries.updated
        and not fail_closed_hass.config_entries.reloaded,
        "Fail-closed HomeKit selection must not mutate or reload entries",
    )

    source_a = FakeEntry(
        "source-a",
        options={
            "filter": {
                "include_entities": ["light.source_a", "switch.shared"],
            }
        },
    )
    source_b = FakeEntry(
        "source-b",
        options={
            "filter": {
                "include_entities": ["sensor.source_b", "switch.shared"],
            }
        },
    )
    unselected_invalid = FakeEntry(
        "not-selected",
        options={
            "filter": {
                "include_entities": [],
                "include_domains": ["light"],
            }
        },
        state="setup_error",
    )
    source_hass = FakeHass([source_a, source_b, unselected_invalid])
    selected_source = await targets.async_read_homekit_source_entries(
        source_hass, ("source-b", "source-a", "source-b")
    )
    check(
        selected_source
        == frozenset({"light.source_a", "sensor.source_b", "switch.shared"}),
        "HomeKit source unions only selected entries, de-duplicates in configured order, and ignores invalid unselected entries",
    )
    check(
        await targets.async_read_platform_source(
            source_hass,
            SimpleNamespace(
                homekit_source_entry_ids=("source-a", "source-b"),
                homekit_managed_entry_ids=(),
            ),
            const.TargetPlatform.HOMEKIT,
        )
        == selected_source,
        "HomeKit source selection is independent from writable managed target entries",
    )

    try:
        await targets.async_read_homekit_source_entries(source_hass, ("missing",))
    except targets.HomeKitSourceEntryMissingError:
        check(True, "A missing selected HomeKit source entry fails closed")
    else:
        raise AssertionError("A missing selected HomeKit source entry must fail closed")

    unavailable = FakeEntry(
        "unavailable",
        options={"filter": {"include_entities": ["light.unavailable"]}},
        state="setup_retry",
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([unavailable]), ("unavailable",)
        )
    except targets.HomeKitSourceEntryUnavailableError:
        check(True, "An unloaded selected HomeKit source entry fails closed")
    else:
        raise AssertionError("An unloaded selected HomeKit source entry must fail closed")

    competing = FakeEntry(
        "competing",
        options={
            "filter": {
                "include_entities": ["light.selected"],
                "exclude_entities": ["light.excluded"],
            }
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([competing]), ("competing",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "A selected HomeKit source with competing filters fails closed")
    else:
        raise AssertionError(
            "A selected HomeKit source with competing filters must fail closed"
        )

    legacy_competing = FakeEntry(
        "legacy-competing",
        options={
            "include_entities": ["light.selected"],
            "exclude_entities": ["light.excluded"],
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([legacy_competing]), ("legacy-competing",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "Legacy top-level HomeKit filters fail closed as one source")
    else:
        raise AssertionError("Legacy competing HomeKit filters must fail closed")

    legacy_include_only = FakeEntry(
        "legacy-include-only",
        options={"include_entities": ["light.selected"]},
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([legacy_include_only]), ("legacy-include-only",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "Legacy top-level include-only HomeKit sources fail closed")
    else:
        raise AssertionError("Legacy top-level HomeKit sources must fail closed")

    glob_competing = FakeEntry(
        "glob-competing",
        options={
            "filter": {
                "include_entities": ["light.selected"],
                "include_entity_globs": ["sensor.*"],
            }
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([glob_competing]), ("glob-competing",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "HomeKit entity-glob source filters fail closed")
    else:
        raise AssertionError("HomeKit source entity globs must fail closed")

    exclude_glob_competing = FakeEntry(
        "exclude-glob-competing",
        options={
            "filter": {
                "include_entities": ["light.selected"],
                "exclude_entity_globs": ["sensor.*"],
            }
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([exclude_glob_competing]), ("exclude-glob-competing",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "HomeKit exclude-entity globs fail closed")
    else:
        raise AssertionError("HomeKit source exclude-entity globs must fail closed")

    malformed = FakeEntry(
        "malformed",
        options={
            "filter": {
                "include_entities": ["light.valid", "not-an-entity"],
            }
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([malformed]), ("malformed",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "A malformed HomeKit entity list fails without a partial union")
    else:
        raise AssertionError("Malformed HomeKit source entities must fail closed")

    malformed_type = FakeEntry(
        "malformed-type",
        options={"filter": {"include_entities": "light.not_a_list"}},
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([malformed_type]), ("malformed-type",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "A non-list HomeKit source entity value fails closed")
    else:
        raise AssertionError("A non-list HomeKit source entity value must fail closed")

    duplicate_entities = FakeEntry(
        "duplicate-entities",
        options={
            "filter": {
                "include_entities": ["light.duplicate", " light.duplicate "],
            }
        },
    )
    try:
        await targets.async_read_homekit_source_entries(
            FakeHass([duplicate_entities]), ("duplicate-entities",)
        )
    except targets.HomeKitSourceFilterUnsupportedError:
        check(True, "Duplicate HomeKit source entity IDs fail closed")
    else:
        raise AssertionError("Duplicate HomeKit source entity IDs must fail closed")

    empty = FakeEntry("empty", options={"filter": {"include_entities": []}})
    try:
        await targets.async_read_homekit_source_entries(FakeHass([empty]), ("empty",))
    except targets.EmptyHomeKitSourceError:
        check(True, "An empty selected HomeKit source entry fails closed")
    else:
        raise AssertionError("An empty selected HomeKit source entry must fail closed")

    invalid_target_cases = (
        FakeEntry(
            "target-glob",
            options={
                "filter": {
                    "include_entities": ["light.valid"],
                    "include_entity_globs": ["sensor.*"],
                }
            },
        ),
        FakeEntry(
            "target-string",
            options={"filter": {"include_entities": "light.not_an_array"}},
        ),
        FakeEntry(
            "target-legacy",
            options={"include_entities": ["light.legacy"]},
        ),
        FakeEntry(
            "target-empty",
            options={"filter": {"include_entities": []}},
        ),
        FakeEntry(
            "target-whitespace",
            options={"filter": {"include_entities": [" light.spaced"]}},
        ),
        FakeEntry(
            "target-duplicate",
            options={
                "filter": {
                    "include_entities": ["light.same", "light.same"]
                }
            },
        ),
    )
    for invalid_target in invalid_target_cases:
        try:
            await targets.async_read_target(
                FakeHass([invalid_target]),
                SimpleNamespace(
                    homekit_managed_entry_ids=(invalid_target.entry_id,)
                ),
                const.TargetPlatform.HOMEKIT,
            )
        except RuntimeError:
            check(True, "Malformed managed HomeKit target filters fail closed")
        else:
            raise AssertionError(
                "Malformed managed HomeKit target filters must never look exact"
            )
    return 38


def check_matter_runtime() -> int:
    ready_settings = {
        "matterbridgeInformation": {
            "bridgeStatus": "Started",
            "restartRequired": False,
            "fixedRestartRequired": False,
        }
    }
    ready_plugin = {
        "enabled": True,
        "loaded": True,
        "started": True,
        "error": False,
        "registeredDevices": 1,
    }
    check(
        targets._matter_runtime_ready(ready_settings, ready_plugin),
        "Matter runtime ready state",
    )
    invalid_pairs = [
        (
            {"matterbridgeInformation": {"bridgeStatus": "Stopped"}},
            ready_plugin,
        ),
        (ready_settings, {"enabled": False, "error": False}),
        (ready_settings, {"enabled": True, "error": True}),
        (
            ready_settings,
            {"enabled": True, "loaded": False, "started": True, "error": False},
        ),
        (
            ready_settings,
            {"enabled": True, "loaded": True, "started": False, "error": False},
        ),
        (
            {
                "matterbridgeInformation": {
                    "bridgeStatus": "started",
                    "restartRequired": True,
                }
            },
            ready_plugin,
        ),
        (
            {
                "bridgeStatus": "STARTED",
                "fixedRestartRequired": True,
            },
            ready_plugin,
        ),
    ]
    for settings, plugin in invalid_pairs:
        check(
            not targets._matter_runtime_ready(settings, plugin),
            f"Matter runtime must reject non-ready state: {settings!r}, {plugin!r}",
        )
    check(
        targets._matter_runtime_ready(
            {"bridgeStatus": "started", "restartRequired": False}, ready_plugin
        ),
        "Matter runtime helper accepts direct information mapping",
    )
    devices = [
        {
            "pluginName": targets.MATTER_PLUGIN,
            "name": "test device",
            "endpoint": 1,
            "uniqueId": "test-device",
            "serial": "test-serial",
        }
    ]
    check(
        targets._matter_loaded_device_count(
            ready_plugin, devices, frozenset({"light.one"})
        )
        == 1,
        "Matterbridge registered and loaded plugin-device counts match",
    )
    check(
        targets._matter_loaded_device_count(
            {**ready_plugin, "registeredDevices": 2},
            devices,
            frozenset({"light.one"}),
        )
        is None,
        "Matterbridge device-count mismatch fails closed",
    )
    check(
        targets._matter_loaded_device_count(
            {**ready_plugin, "registeredDevices": 0},
            [],
            frozenset({"light.one"}),
        )
        is None,
        "A non-empty allowlist cannot validate with zero loaded devices",
    )
    return 12


def check_matter_exact_configuration() -> int:
    """Malformed allowlists and competing Matterbridge filters fail closed."""
    exact = {
        "whiteList": ["light.one", "sensor.two"],
        "filterByArea": "",
        "filterByLabel": "",
        "virtualControlLabel": "",
        "blackList": [],
        "entityWhiteList": [],
        "entityBlackList": [],
        "deviceEntityBlackList": {},
        "splitEntities": [],
        "splitByLabel": "",
    }
    check(
        targets._strict_matter_allowlist(exact)
        == frozenset({"light.one", "sensor.two"}),
        "Matterbridge exact whiteList parses without normalization loss",
    )
    targets._require_empty_matter_filters(exact)
    check(True, "Matterbridge exact empty competing filters are accepted")

    invalid_allowlists = (
        {**exact, "whiteList": "light.not_an_array"},
        {**exact, "whiteList": []},
        {**exact, "whiteList": [" light.spaced"]},
        {**exact, "whiteList": ["light.same", " light.same "]},
        {**exact, "whiteList": ["not-an-entity"]},
    )
    for invalid in invalid_allowlists:
        try:
            targets._strict_matter_allowlist(invalid)
        except RuntimeError:
            check(True, "Malformed Matterbridge whiteList fails closed")
        else:
            raise AssertionError("Malformed Matterbridge whiteList must fail closed")

    invalid_filters = (
        {**exact, "filterByLabel": "sync"},
        {**exact, "entityBlackList": ["sensor"]},
        {**exact, "deviceEntityBlackList": {"device": ["sensor.one"]}},
    )
    for invalid in invalid_filters:
        try:
            targets._require_empty_matter_filters(invalid)
        except RuntimeError:
            check(True, "Competing Matterbridge filter fails closed")
        else:
            raise AssertionError("Competing Matterbridge filters must fail closed")
    return 10


async def check_matter_validation_contract() -> int:
    """Matter validation reads a filtered device list and reports exact runtime."""
    expected = frozenset({"light.one"})
    plugin = {
        "name": targets.MATTER_PLUGIN,
        "enabled": True,
        "loaded": True,
        "started": True,
        "error": False,
        "registeredDevices": 1,
        "configJson": {
            "whiteList": ["light.one"],
            "filterByArea": "",
            "filterByLabel": "",
            "virtualControlLabel": "",
            "blackList": [],
            "entityWhiteList": [],
            "entityBlackList": [],
            "deviceEntityBlackList": {},
            "splitEntities": [],
            "splitByLabel": "",
        },
    }
    calls: list[tuple[str, Any]] = []

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        calls.append((command, payload))
        if command == "plugins":
            return [plugin]
        if command == "settings":
            return {
                "matterbridgeInformation": {
                    "bridgeStatus": "Started",
                    "restartRequired": False,
                    "fixedRestartRequired": False,
                }
            }
        if command == "devices":
            return [
                {
                    "pluginName": targets.MATTER_PLUGIN,
                    "endpoint": 1,
                    "uniqueId": "device-one",
                    "serial": "serial-one",
                }
            ]
        raise AssertionError(f"Unexpected Matter command: {command}")

    original_request = targets._matter_request
    targets._matter_request = request
    try:
        runtime = await targets.async_validate_target(
            SimpleNamespace(), SimpleNamespace(), const.TargetPlatform.MATTER, expected
        )
    finally:
        targets._matter_request = original_request
    check(
        calls[-1]
        == ("devices", {"pluginName": targets.MATTER_PLUGIN}),
        "Matter validation requests only the selected plugin's loaded devices",
    )
    check(
        runtime["plugin_loaded"] is True
        and runtime["plugin_started"] is True
        and runtime["registered_devices"] == 1
        and runtime["loaded_devices"] == 1,
        "Matter validation reports plugin lifecycle and exact device counts",
    )
    return 2


async def check_matter_request_overall_timeout() -> int:
    """A silent websocket is bounded by the whole-request timeout."""
    sent_methods: list[str] = []

    class FakeWebSocket:
        async def send_json(self, request: dict[str, Any]) -> None:
            sent_methods.append(str(request.get("method")))

        async def receive(self) -> Any:
            await asyncio.Event().wait()
            raise AssertionError("The whole-request timeout must cancel receive")

    class AsyncContext:
        def __init__(self, value: Any) -> None:
            self.value = value

        async def __aenter__(self) -> Any:
            return self.value

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class FakeClientSession:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        def ws_connect(self, _url: str, *, heartbeat: int) -> AsyncContext:
            check(heartbeat == 20, "Matterbridge websocket retains its heartbeat")
            return AsyncContext(FakeWebSocket())

    fake_aiohttp = ModuleType("aiohttp")
    fake_aiohttp.ClientSession = FakeClientSession
    fake_aiohttp.WSMsgType = SimpleNamespace(TEXT="text")
    previous_aiohttp = sys.modules.get("aiohttp")
    previous_timeout = targets.MATTER_REQUEST_TIMEOUT
    sys.modules["aiohttp"] = fake_aiohttp
    targets.MATTER_REQUEST_TIMEOUT = 0.01
    try:
        try:
            await asyncio.wait_for(
                targets._matter_request(
                    SimpleNamespace(matter_host="127.0.0.1", matter_port=8283),
                    "plugins",
                ),
                timeout=0.1,
            )
        except RuntimeError as error:
            check(
                str(error) == "Matterbridge plugins timed out",
                "Matterbridge converts the whole-request timeout into a safe error",
            )
        else:
            raise AssertionError("A silent Matterbridge websocket must time out")
    finally:
        targets.MATTER_REQUEST_TIMEOUT = previous_timeout
        if previous_aiohttp is None:
            sys.modules.pop("aiohttp", None)
        else:
            sys.modules["aiohttp"] = previous_aiohttp

    check(
        sent_methods == ["/api/plugins"],
        "Matterbridge timeout test sends exactly one bounded request",
    )
    return 3


def check_google_room_schema() -> int:
    """Google room metadata must use HA's supported ``room`` option."""
    current = {
        "light.one": {"expose": True, "room": "客廳", "name": "主燈"},
        "switch.remove": {"expose": True, "room": "舊房間"},
    }
    desired = frozenset({"light.one", "sensor.new"})
    rooms = {"light.one": "客廳", "sensor.new": "環境"}
    check(
        targets._google_room_updates_for_config(current, desired, rooms)
        == ("sensor.new",),
        "Existing HA Google room metadata must not be rewritten",
    )
    check(
        targets._google_room_updates_for_config(
            {"light.one": {"room_hint": "客廳"}},
            frozenset({"light.one"}),
            {"light.one": "客廳"},
        )
        == ("light.one",),
        "Unsupported room_hint must never satisfy the room comparison",
    )
    updated = targets._build_google_config(current, desired, rooms)
    check(
        updated["light.one"]
        == {"expose": True, "room": "客廳", "name": "主燈"}
        and updated["sensor.new"] == {"expose": True, "room": "環境"},
        "Google writer preserves supported metadata and adds exact room values",
    )
    check(
        "switch.remove" not in updated
        and all("room_hint" not in value for value in updated.values()),
        "Google writer is exact and never emits unsupported room_hint",
    )
    return 4


async def check_single_switch_runtime() -> int:
    """Version 0.6.0 has one enable switch and no sensor/button platforms."""
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    check(manifest["version"] == "0.6.0", "Manifest version is 0.6.0")
    check(const.DEFAULT_ENABLED is False, "New installations default disabled")
    check(const.PLATFORMS == (), "Version 0.4 exposes no sensor/button platforms")
    check(
        not hasattr(const, "CONF_PROFILE_NAME")
        and not hasattr(const, "DEFAULT_PROFILE_NAME"),
        "Profile-name configuration constants are completely retired",
    )
    check(
        not (PACKAGE / "sensor.py").exists() and not (PACKAGE / "button.py").exists(),
        "Retired sensor and button platform modules are absent",
    )
    runtime_defaults = runtime_config_module.SyncConfig.from_entry({}, {})
    check(
        runtime_defaults.enabled is False
        and not hasattr(runtime_defaults, "auto_apply")
        and not hasattr(runtime_defaults, "profile_name"),
        "Runtime has one disabled-by-default switch and no custom name",
    )
    legacy_dashboard = runtime_config_module.SyncConfig.from_entry(
        {
            const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
            const.CONF_SOURCE_DASHBOARD: "legacy-dashboard",
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
        },
        {const.CONF_SOURCE_VIEW: "legacy-view"},
    )
    check(
        legacy_dashboard.source_pages == (("legacy-dashboard", "legacy-view"),),
        "Runtime preserves backward fallback from one legacy dashboard/view pair",
    )
    for invalid_pages in (
        [],
        (),
        None,
        "lovelace/default-view",
        [{"dashboard": "", "view": "default-view"}],
        [{"dashboard": "lovelace", "view": ""}],
        [{"dashboard": "lovelace"}],
        [{"view": "default-view"}],
        [{"dashboard": "lovelace", "view": "default-view"}, 7],
    ):
        try:
            runtime_config_module.SyncConfig.from_entry(
                {
                    const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
                    const.CONF_SOURCE_PAGES: invalid_pages,
                    const.CONF_TARGET_PLATFORMS: [
                        const.TargetPlatform.GOOGLE.value
                    ],
                },
                {},
            )
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                "Explicit empty or malformed source_pages must fail closed: "
                f"{invalid_pages!r}"
            )
    check(
        True,
        "Explicit empty or malformed 4.1 source_pages never fall back to defaults",
    )
    multi_dashboard = runtime_config_module.SyncConfig.from_entry(
        {
            const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
            const.CONF_SOURCE_PAGES: [
                {"dashboard": "lovelace", "view": "default-view"},
                {"dashboard": "lovelace", "view": "rooms"},
                {"dashboard": "lovelace", "view": "default-view"},
            ],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
        },
        {},
    )
    check(
        multi_dashboard.source_pages
        == (("lovelace", "default-view"), ("lovelace", "rooms")),
        "Runtime normalizes ordered dashboard pairs and removes duplicates",
    )

    reads = 0
    writes = 0
    apple_tv_reads = 0
    actual = frozenset()

    async def fake_read_source(_hass: Any, _config: Any) -> Any:
        nonlocal reads
        reads += 1
        return models.SourceSnapshot(entities=frozenset({"light.one"}))

    async def fake_find_apple_tv(_hass: Any) -> frozenset[str]:
        nonlocal apple_tv_reads
        apple_tv_reads += 1
        return frozenset()

    async def fake_read_target(
        _hass: Any, _config: Any, _platform: Any
    ) -> frozenset[str]:
        return actual

    async def fake_prepare(_hass: Any, _config: Any, platform: Any) -> Any:
        return SimpleNamespace(platform=platform)

    async def fake_apply_plan(
        _hass: Any, _config: Any, plan: Any, _rooms: Any
    ) -> None:
        nonlocal writes, actual
        writes += 1
        actual = plan.desired

    async def fake_restore(_hass: Any, _config: Any, _backup: Any) -> None:
        raise AssertionError("Successful apply must not roll back")

    async def fake_room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def fake_validate_target(
        _hass: Any, _config: Any, _platform: Any, _expected: Any
    ) -> dict[str, Any]:
        return {"loaded": True}

    manager_module.async_read_source = fake_read_source
    manager_module.async_find_apple_tv_entities = fake_find_apple_tv
    manager_module.async_read_target = fake_read_target
    manager_module.async_prepare_target = fake_prepare
    manager_module.async_apply_plan = fake_apply_plan
    manager_module.async_restore_target = fake_restore
    manager_module.async_google_room_updates = fake_room_updates
    manager_module.async_validate_target = fake_validate_target

    class FakeBus:
        def __init__(self) -> None:
            self.listened: list[str] = []

        def async_listen(self, event: str, _callback: Any) -> Any:
            self.listened.append(event)
            return lambda: None

        def async_fire(self, _event: str, _data: Any) -> None:
            return None

    class RuntimeHass:
        def __init__(self) -> None:
            self.bus = FakeBus()
            self.state = manager_module.CoreState.running
            self.created = 0

        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> Any:
            self.created += 1
            coroutine.close()
            raise AssertionError("Disabled mode must not create a background task")

    disabled_hass = RuntimeHass()
    disabled_manager = manager_module.PlatformSyncManager(
        disabled_hass,
        SimpleNamespace(enabled=False, source_kind=const.SourceKind.DASHBOARD),
    )
    await disabled_manager.async_start()
    disabled_manager.schedule("lovelace_updated")
    disabled_result = await disabled_manager.async_reconcile(
        reason="service_sync_now", apply=True
    )
    check(
        disabled_result == {"status": "disabled", "changed": False},
        "Disabled manager rejects direct synchronization",
    )
    check(
        reads == 0
        and writes == 0
        and disabled_hass.bus.listened == []
        and disabled_hass.created == 0
        and disabled_manager._debounce_task is None,
        "Disabled mode is completely inert: no reads, writes, watchers, or tasks",
    )

    class ApplyBus:
        def async_fire(self, _event: str, _data: Any) -> None:
            return None

    config = SimpleNamespace(
        enabled=True,
        targets=frozenset({const.TargetPlatform.GOOGLE}),
        user_rules={const.TargetPlatform.GOOGLE: models.PlatformRule()},
        locked_rules={const.TargetPlatform.GOOGLE: models.PlatformRule()},
    )
    manager = manager_module.PlatformSyncManager(SimpleNamespace(bus=ApplyBus()), config)
    result = await manager.async_reconcile(reason="service_sync_now", apply=True)
    check(
        result["status"] == "synced"
        and reads == 1
        and writes == 1
        and apple_tv_reads == 0,
        "A fresh public configuration applies without enabling the legacy Apple TV scan",
    )
    config.locked_homekit_apple_tv_exclusion = True
    preview = await manager.async_reconcile(reason="service_preview", apply=False)
    check(
        preview["status"] == "preview" and apple_tv_reads == 1,
        "A migrated private configuration keeps its explicit Apple TV scan compatibility flag",
    )

    class FakeServices:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def async_register(
            self,
            _domain: str,
            service: str,
            handler: Any,
            **_kwargs: Any,
        ) -> None:
            self.handlers[service] = handler

    class RecordingManager:
        def __init__(self) -> None:
            self.apply_values: list[bool] = []

        async def async_reconcile(self, *, reason: str, apply: bool) -> dict[str, Any]:
            self.apply_values.append(apply)
            return {"status": "synced" if apply else "preview", "reason": reason}

    services = FakeServices()
    recording = RecordingManager()
    service_entry = SimpleNamespace(title="single-switch", runtime_data=recording)
    service_hass = SimpleNamespace(
        services=services,
        config_entries=SimpleNamespace(async_entries=lambda _domain: [service_entry]),
    )
    await integration_module.async_setup(service_hass, {})
    await services.handlers[const.SERVICE_PREVIEW](
        SimpleNamespace(service=const.SERVICE_PREVIEW)
    )
    await services.handlers[const.SERVICE_SYNC_NOW](
        SimpleNamespace(service=const.SERVICE_SYNC_NOW)
    )
    check(
        recording.apply_values == [False, True],
        "Preview remains read-only while sync_now explicitly applies",
    )
    return 15


async def check_safe_migration() -> int:
    """Migrate v1-v4.2 safely into schema 4.3 with exact HomeKit sources."""
    homekit_entries = [
        SimpleNamespace(entry_id="homekit-main"),
        SimpleNamespace(entry_id="homekit-accessory"),
    ]
    profile = SimpleNamespace(
        version=1,
        minor_version=1,
        title="使用者自訂舊標題",
        data={
            LEGACY_PROFILE_NAME: "資料層自訂名稱",
            const.LEGACY_CONF_HOME_PRESENCE_PROTECTION: True,
            const.LEGACY_CONF_DEBOUNCE_SECONDS: 59,
            const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
            const.CONF_TARGET_PLATFORMS: [
                const.TargetPlatform.GOOGLE.value,
                const.TargetPlatform.HOMEKIT.value,
                const.TargetPlatform.MATTER.value,
            ],
        },
        options={
            LEGACY_PROFILE_NAME: "選項層自訂名稱",
            const.CONF_ENABLED: True,
            const.LEGACY_CONF_AUTO_APPLY: True,
            const.LEGACY_CONF_POLL_SECONDS: 3600,
            # The old options layer wins over data during runtime merge. An
            # explicit empty value must therefore be replaced, not merely
            # shadow a snapshot written to data.
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: [],
        },
    )

    class MigrationEntries:
        def async_entries(self, domain: str) -> list[Any]:
            return homekit_entries if domain == "homekit" else []

        def async_update_entry(
            self,
            entry: Any,
            *,
            data: dict[str, Any],
            options: dict[str, Any],
            title: str,
            version: int,
            minor_version: int,
        ) -> None:
            entry.data = deepcopy(data)
            entry.options = deepcopy(options)
            entry.title = title
            entry.version = version
            entry.minor_version = minor_version

    hass_zh = SimpleNamespace(
        config_entries=MigrationEntries(),
        config=SimpleNamespace(language="zh-Hant"),
    )
    hass_en = SimpleNamespace(
        config_entries=MigrationEntries(),
        config=SimpleNamespace(language="en"),
    )
    check(
        await integration_module.async_migrate_entry(hass_zh, profile),
        "Config entry migration must succeed",
    )
    check(
        profile.version == 4
        and profile.minor_version == 3
        and profile.title == TITLE_ZH_HANT
        and LEGACY_PROFILE_NAME not in profile.data
        and LEGACY_PROFILE_NAME not in profile.options,
        "Version 1 migrates to 4.3, discards custom names, and fixes zh-Hant title",
    )
    check(
        profile.options[const.CONF_ENABLED] is False
        and const.CONF_ENABLED not in profile.data,
        "Every version 1 profile is forced disabled, even when both old gates were on",
    )
    check(
        (
            profile.options.get(const.CONF_HOMEKIT_MANAGED_ENTRY_IDS)
            or profile.data.get(const.CONF_HOMEKIT_MANAGED_ENTRY_IDS)
        )
        == ["homekit-main", "homekit-accessory"],
        "Migration must snapshot the current HomeKit entries into the effective storage layer exactly once",
    )
    check(
        profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["homekit-main", "homekit-accessory"]
        and runtime_config_module.SyncConfig.from_entry(
            profile.data, profile.options
        ).homekit_managed_entry_ids
        == ("homekit-main", "homekit-accessory"),
        "Version 1 replaces an explicit empty options-layer HomeKit list with an effective current snapshot",
    )
    locked = profile.data[const.CONF_LOCKED_RULES]
    empty_locked = integration_module.serialize_rules(
        {platform: models.PlatformRule() for platform in const.TargetPlatform}
    )
    check(
        locked == empty_locked
        and profile.data[const.CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION] is True,
        "Legacy private defaults are not embedded as entity IDs while the former Apple TV safety behavior is preserved internally",
    )
    retired = (
        const.LEGACY_CONF_AUTO_APPLY,
        const.LEGACY_CONF_HOME_PRESENCE_PROTECTION,
        const.LEGACY_CONF_DEBOUNCE_SECONDS,
        const.LEGACY_CONF_POLL_SECONDS,
    )
    check(
        all(key not in profile.data and key not in profile.options for key in retired),
        "Version 1 migration removes all retired switches and timing keys",
    )
    check(
        profile.data[const.CONF_SOURCE_KIND] == const.SourceKind.DASHBOARD.value
        and profile.data[const.CONF_TARGET_PLATFORMS]
        == [
            const.TargetPlatform.GOOGLE.value,
            const.TargetPlatform.HOMEKIT.value,
            const.TargetPlatform.MATTER.value,
        ],
        "Version 1 migration preserves source and target scope",
    )

    truth_table: list[tuple[bool, bool, bool]] = [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ]
    migrated_results: list[bool] = []
    for index, (old_enabled, old_auto_apply, expected) in enumerate(truth_table):
        legacy_v2 = SimpleNamespace(
            version=2,
            minor_version=2,
            title=f"user-custom-title-{index}",
            data={
                LEGACY_PROFILE_NAME: f"data-custom-name-{index}",
                const.CONF_ENABLED: old_enabled,
                const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
                const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
                const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["managed-homekit"],
            },
            options={
                LEGACY_PROFILE_NAME: f"options-custom-name-{index}",
                const.LEGACY_CONF_AUTO_APPLY: old_auto_apply,
            },
        )
        check(
            await integration_module.async_migrate_entry(hass_en, legacy_v2),
            f"Version 2 truth-table case {index} migrates",
        )
        migrated_results.append(legacy_v2.options[const.CONF_ENABLED])
        check(
            legacy_v2.version == 4
            and legacy_v2.minor_version == 3
            and legacy_v2.title == TITLE_EN
            and legacy_v2.options[const.CONF_ENABLED] is expected
            and const.CONF_ENABLED not in legacy_v2.data
            and const.LEGACY_CONF_AUTO_APPLY not in legacy_v2.data
            and const.LEGACY_CONF_AUTO_APPLY not in legacy_v2.options
            and LEGACY_PROFILE_NAME not in legacy_v2.data
            and LEGACY_PROFILE_NAME not in legacy_v2.options,
            f"Version 2 case {index} applies AND and replaces all custom naming",
        )
        check(
            legacy_v2.data[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
            == ["managed-homekit"]
            and legacy_v2.data[const.CONF_TARGET_PLATFORMS]
            == [const.TargetPlatform.GOOGLE.value],
            f"Version 2 case {index} preserves deployment scope",
        )
    check(
        migrated_results == [False, False, False, True],
        "Version 2 dual switches collapse using a strict logical AND",
    )

    v3_locked = integration_module.serialize_rules(
        {
            const.TargetPlatform.GOOGLE: models.PlatformRule(
                include=frozenset({"input_boolean.example_google_presence"})
            ),
            const.TargetPlatform.HOMEKIT: models.PlatformRule(
                exclude=frozenset({"media_player.example_native_device"})
            ),
            const.TargetPlatform.MATTER: models.PlatformRule(),
        }
    )
    v3_data = {
        LEGACY_PROFILE_NAME: "v3-data-custom-name",
        const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        const.CONF_SOURCE_ENTITIES: ["light.one", "switch.two"],
        const.CONF_TARGET_PLATFORMS: [
            const.TargetPlatform.GOOGLE.value,
            const.TargetPlatform.MATTER.value,
        ],
        const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["do-not-change"],
        const.CONF_LOCKED_RULES: deepcopy(v3_locked),
    }
    v3_options = {
        LEGACY_PROFILE_NAME: "v3-options-custom-name",
        const.CONF_ENABLED: True,
        const.CONF_SOURCE_VIEW: "custom-view",
        const.CONF_USER_RULES: {
            const.TargetPlatform.GOOGLE.value: {
                "include": ["input_boolean.extra"],
                "exclude": ["light.skip"],
            }
        },
    }
    expected_v3_data = deepcopy(v3_data)
    expected_v3_options = deepcopy(v3_options)
    expected_v3_data.pop(LEGACY_PROFILE_NAME)
    expected_v3_data[const.CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION] = True
    expected_v3_options.pop(LEGACY_PROFILE_NAME)
    expected_v3_options[const.CONF_SOURCE_PAGES] = [
        {"dashboard": "lovelace", "view": "custom-view"}
    ]
    legacy_v3 = SimpleNamespace(
        version=3,
        minor_version=0,
        title="v3 使用者自訂標題",
        data=deepcopy(v3_data),
        options=deepcopy(v3_options),
    )
    hass_zh_tw = SimpleNamespace(
        config_entries=MigrationEntries(),
        config=SimpleNamespace(language="zh_TW"),
    )
    check(
        await integration_module.async_migrate_entry(hass_zh_tw, legacy_v3),
        "Version 3 profile migrates",
    )
    check(
        legacy_v3.version == 4
        and legacy_v3.minor_version == 3
        and legacy_v3.title == TITLE_ZH_HANT
        and LEGACY_PROFILE_NAME not in legacy_v3.data
        and LEGACY_PROFILE_NAME not in legacy_v3.options,
        "Version 3 reaches 4.3 with the fixed localized title and no name field",
    )
    check(
        legacy_v3.data == expected_v3_data
        and legacy_v3.options == expected_v3_options,
        "Version 3 migration preserves prior values and materializes its page pair",
    )

    legacy_v4 = SimpleNamespace(
        version=4,
        minor_version=0,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.DASHBOARD.value,
            const.CONF_SOURCE_DASHBOARD: "lovelace",
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
        },
        options={
            const.CONF_ENABLED: True,
            const.CONF_SOURCE_VIEW: "rooms",
        },
    )
    check(
        await integration_module.async_migrate_entry(hass_en, legacy_v4),
        "Version 4.0 single-dashboard entry migrates",
    )
    check(
        legacy_v4.version == 4 and legacy_v4.minor_version == 3,
        "Version 4.0 reaches schema 4.3",
    )
    check(
        legacy_v4.options[const.CONF_SOURCE_PAGES]
        == [{"dashboard": "lovelace", "view": "rooms"}],
        "Version 4.0 materializes the merged legacy dashboard/view pair",
    )
    check(
        legacy_v4.data[const.CONF_SOURCE_DASHBOARD] == "lovelace"
        and legacy_v4.options[const.CONF_SOURCE_VIEW] == "rooms"
        and legacy_v4.options[const.CONF_ENABLED] is True,
        "Version 4.0 migration preserves its prior fields and enabled state",
    )

    homekit_v41 = SimpleNamespace(
        version=4,
        minor_version=1,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.HOMEKIT.value,
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
            "preserved_marker": "keep-me",
        },
        options={const.CONF_ENABLED: True},
    )
    check(
        await integration_module.async_migrate_entry(hass_en, homekit_v41),
        "Version 4.1 HomeKit source migrates",
    )
    check(
        homekit_v41.version == 4
        and homekit_v41.minor_version == 3
        and homekit_v41.options[const.CONF_HOMEKIT_SOURCE_ENTRY_IDS]
        == ["homekit-main", "homekit-accessory"]
        and homekit_v41.options[const.CONF_ENABLED] is True
        and homekit_v41.data["preserved_marker"] == "keep-me",
        "Version 4.1 snapshots all current HomeKit entries once while preserving enabled state and other settings",
    )
    migrated_runtime = runtime_config_module.SyncConfig.from_entry(
        homekit_v41.data, homekit_v41.options
    )
    check(
        migrated_runtime.homekit_source_entry_ids
        == ("homekit-main", "homekit-accessory"),
        "The migrated HomeKit source selection is valid runtime configuration",
    )
    homekit_entries.append(SimpleNamespace(entry_id="homekit-added-later"))
    check(
        await integration_module.async_migrate_entry(hass_en, homekit_v41)
        and homekit_v41.options[const.CONF_HOMEKIT_SOURCE_ENTRY_IDS]
        == ["homekit-main", "homekit-accessory"],
        "A completed 4.3 migration never auto-adopts a later HomeKit entry",
    )

    class EmptyMigrationEntries(MigrationEntries):
        def async_entries(self, domain: str) -> list[Any]:
            return []

    empty_hass = SimpleNamespace(
        config_entries=EmptyMigrationEntries(),
        config=SimpleNamespace(language="en"),
    )
    empty_homekit_v41 = SimpleNamespace(
        version=4,
        minor_version=1,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.HOMEKIT.value,
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.MATTER.value],
            "preserved_marker": {"nested": True},
        },
        options={const.CONF_ENABLED: True},
    )
    check(
        await integration_module.async_migrate_entry(empty_hass, empty_homekit_v41),
        "Version 4.1 HomeKit source with no current entries still migrates safely",
    )
    check(
        empty_homekit_v41.version == 4
        and empty_homekit_v41.minor_version == 3
        and empty_homekit_v41.options[const.CONF_HOMEKIT_SOURCE_ENTRY_IDS] == []
        and empty_homekit_v41.options[const.CONF_ENABLED] is False
        and empty_homekit_v41.data[const.CONF_TARGET_PLATFORMS]
        == [const.TargetPlatform.MATTER.value]
        and empty_homekit_v41.data["preserved_marker"] == {"nested": True},
        "An enabled empty HomeKit source fails closed by disabling only the master switch and preserving all other settings",
    )

    non_homekit_v41 = SimpleNamespace(
        version=4,
        minor_version=1,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.manual"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.GOOGLE.value],
        },
        options={const.CONF_ENABLED: True},
    )
    check(
        await integration_module.async_migrate_entry(hass_en, non_homekit_v41),
        "Version 4.1 non-HomeKit source migrates",
    )
    check(
        non_homekit_v41.version == 4
        and non_homekit_v41.minor_version == 3
        and const.CONF_HOMEKIT_SOURCE_ENTRY_IDS not in non_homekit_v41.data
        and const.CONF_HOMEKIT_SOURCE_ENTRY_IDS not in non_homekit_v41.options
        and non_homekit_v41.options[const.CONF_ENABLED] is True
        and non_homekit_v41.data[const.CONF_SOURCE_ENTITIES] == ["light.manual"],
        "Non-HomeKit sources never gain a HomeKit source selection and retain prior behavior",
    )

    v42_locked = {
        const.TargetPlatform.HOMEKIT.value: {
            "include": ["input_boolean.example_required"],
            "exclude": ["media_player.example_native"],
        }
    }
    legacy_v42 = SimpleNamespace(
        version=4,
        minor_version=2,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.example"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value],
            const.CONF_LOCKED_RULES: deepcopy(v42_locked),
        },
        options={const.CONF_ENABLED: True},
    )
    check(
        await integration_module.async_migrate_entry(hass_en, legacy_v42)
        and legacy_v42.version == 4
        and legacy_v42.minor_version == 3
        and legacy_v42.data[const.CONF_LOCKED_RULES] == v42_locked
        and legacy_v42.data[const.CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION] is True,
        "Version 4.2 preserves its immutable rules and materializes the legacy Apple TV exclusion flag",
    )
    migrated_v42_snapshot = (deepcopy(legacy_v42.data), deepcopy(legacy_v42.options))
    check(
        await integration_module.async_migrate_entry(hass_en, legacy_v42)
        and migrated_v42_snapshot
        == (legacy_v42.data, legacy_v42.options),
        "A completed 4.3 migration is idempotent",
    )
    fresh_public = runtime_config_module.SyncConfig.from_entry(
        {
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.example"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value],
        },
        {},
    )
    check(
        fresh_public.locked_homekit_apple_tv_exclusion is False,
        "A new public installation has no hidden Apple TV exclusion policy",
    )
    return 39


def check_legacy_registry_cleanup() -> int:
    """The two retired platform rows are removed by their stable unique IDs."""

    class FakeRegistry:
        def __init__(self) -> None:
            self.lookups: list[tuple[str, str, str]] = []
            self.removed: list[str] = []
            self.entities = {
                ("sensor", const.DOMAIN, "profile-1_status"): "sensor.platform_sync_status",
                ("button", const.DOMAIN, "profile-1_sync_now"): "button.platform_sync_sync_now",
            }

        def async_get_entity_id(
            self, entity_domain: str, integration: str, unique_id: str
        ) -> str | None:
            key = (entity_domain, integration, unique_id)
            self.lookups.append(key)
            return self.entities.get(key)

        def async_remove(self, entity_id: str) -> None:
            self.removed.append(entity_id)

    registry = FakeRegistry()
    original_async_get = getattr(integration_module.er, "async_get", None)
    integration_module.er.async_get = lambda _hass: registry
    try:
        integration_module._remove_legacy_entities(
            SimpleNamespace(), SimpleNamespace(entry_id="profile-1")
        )
    finally:
        if original_async_get is None:
            del integration_module.er.async_get
        else:
            integration_module.er.async_get = original_async_get
    check(
        registry.lookups
        == [
            ("sensor", const.DOMAIN, "profile-1_status"),
            ("button", const.DOMAIN, "profile-1_sync_now"),
        ],
        "Legacy registry cleanup uses the exact historical unique IDs",
    )
    check(
        registry.removed
        == ["sensor.platform_sync_status", "button.platform_sync_sync_now"],
        "Both retired registry rows are removed without loading old platforms",
    )
    return 2


def check_internal_timing_config() -> int:
    """Legacy values cannot override the event-first internal timing policy."""
    check(
        const.INTERNAL_DEBOUNCE_SECONDS == 2,
        "Change-event coalescing is fixed internally at two seconds",
    )
    check(
        const.INTERNAL_POLL_SECONDS == 15
        and const.INTERNAL_RETRY_SECONDS == 15,
        "Platform fallback polling and readiness retry are fixed at 15 seconds",
    )
    config = runtime_config_module.SyncConfig.from_entry(
        {
            const.LEGACY_CONF_DEBOUNCE_SECONDS: 59,
            const.LEGACY_CONF_POLL_SECONDS: 3600,
        },
        {
            const.LEGACY_CONF_DEBOUNCE_SECONDS: 60,
            const.LEGACY_CONF_POLL_SECONDS: 9999,
        },
    )
    check(
        not hasattr(config, "debounce_seconds")
        and not hasattr(config, "poll_seconds"),
        "Runtime config does not expose or consume legacy timing fields",
    )
    return 3


async def check_source_watcher_policy() -> int:
    """Use push events where available and poll only unsupported sources."""

    class WatcherTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def done(self) -> bool:
            return self.cancelled

        def __await__(self) -> Any:
            async def finished() -> None:
                return None

            return finished().__await__()

    class WatcherBus:
        def __init__(self) -> None:
            self.events: list[str] = []

        def async_listen(self, event: str, _callback: Any) -> Any:
            self.events.append(event)
            return lambda: None

        def async_fire(self, _event: str, _data: Any) -> None:
            return None

    class WatcherHass:
        def __init__(self) -> None:
            self.bus = WatcherBus()
            self.state = manager_module.CoreState.running

        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> WatcherTask:
            coroutine.close()
            return WatcherTask()

    intervals: list[int] = []
    dispatcher_signals: list[Any] = []
    original_tracker = manager_module.async_track_time_interval
    original_dispatcher = manager_module.async_dispatcher_connect
    original_logger_disabled = manager_module._LOGGER.disabled

    def record_interval(_hass: Any, _callback: Any, interval: Any) -> Any:
        intervals.append(int(interval.total_seconds()))
        return lambda: None

    def record_dispatcher(_hass: Any, signal: Any, _callback: Any) -> Any:
        dispatcher_signals.append(signal)
        return lambda: None

    manager_module.async_track_time_interval = record_interval
    manager_module.async_dispatcher_connect = record_dispatcher
    manager_module._LOGGER.disabled = True
    try:
        for source_kind in const.SourceKind:
            intervals.clear()
            dispatcher_signals.clear()
            hass = WatcherHass()
            config = SimpleNamespace(
                enabled=True,
                source_kind=source_kind,
                homekit_source_entry_ids=("source-entry",),
            )
            manager = manager_module.PlatformSyncManager(hass, config)
            await manager.async_start()
            if source_kind is const.SourceKind.DASHBOARD:
                check(
                    hass.bus.events
                    == ["lovelace_updated", "entity_registry_updated"]
                    and intervals == []
                    and dispatcher_signals == [],
                    "Dashboard source uses Lovelace and entity-registry events without polling",
                )
            elif source_kind is const.SourceKind.HOMEKIT:
                check(
                    hass.bus.events == []
                    and intervals == []
                    and dispatcher_signals == ["config_entry_changed"],
                    "HomeKit source uses config-entry push events without polling",
                )
            elif source_kind is const.SourceKind.MANUAL:
                check(
                    hass.bus.events == []
                    and intervals == []
                    and dispatcher_signals == [],
                    "Manual source has no event watcher or polling loop",
                )
            else:
                check(
                    hass.bus.events == []
                    and intervals == [15]
                    and dispatcher_signals == [],
                    f"{source_kind.value} source uses only the 15-second fallback poll",
                )
            await manager.async_stop()

        signal = manager_module.config_entries.SIGNAL_CONFIG_ENTRY_CHANGED
        del manager_module.config_entries.SIGNAL_CONFIG_ENTRY_CHANGED
        intervals.clear()
        dispatcher_signals.clear()
        hass = WatcherHass()
        manager = manager_module.PlatformSyncManager(
            hass,
            SimpleNamespace(
                enabled=True,
                source_kind=const.SourceKind.HOMEKIT,
                homekit_source_entry_ids=("source-entry",),
            ),
        )
        await manager.async_start()
        check(
            intervals == [15] and dispatcher_signals == [],
            "HomeKit falls back to 15-second polling only when its signal is unavailable",
        )
        await manager.async_stop()
        manager_module.config_entries.SIGNAL_CONFIG_ENTRY_CHANGED = signal

        def failed_dispatcher(_hass: Any, _signal: Any, _callback: Any) -> Any:
            raise TypeError("simulated incompatible dispatcher API")

        intervals.clear()
        dispatcher_signals.clear()
        manager_module.async_dispatcher_connect = failed_dispatcher
        hass = WatcherHass()
        manager = manager_module.PlatformSyncManager(
            hass,
            SimpleNamespace(
                enabled=True,
                source_kind=const.SourceKind.HOMEKIT,
                homekit_source_entry_ids=("source-entry",),
            ),
        )
        await manager.async_start()
        check(
            intervals == [15],
            "HomeKit falls back to polling when event registration is incompatible",
        )
        await manager.async_stop()
        manager_module.async_dispatcher_connect = record_dispatcher

        intervals.clear()
        dispatcher_signals.clear()
        disabled_hass = WatcherHass()
        disabled_manager = manager_module.PlatformSyncManager(
            disabled_hass,
            SimpleNamespace(
                enabled=False,
                source_kind=const.SourceKind.HOMEKIT,
                homekit_source_entry_ids=("source-entry",),
            ),
        )
        await disabled_manager.async_start()
        check(
            disabled_hass.bus.events == []
            and intervals == []
            and dispatcher_signals == []
            and disabled_manager._debounce_task is None,
            "Disabled mode registers no watcher, poll, or startup scan",
        )
    finally:
        manager_module.async_track_time_interval = original_tracker
        manager_module.async_dispatcher_connect = original_dispatcher
        manager_module._LOGGER.disabled = original_logger_disabled
        if not hasattr(manager_module.config_entries, "SIGNAL_CONFIG_ENTRY_CHANGED"):
            manager_module.config_entries.SIGNAL_CONFIG_ENTRY_CHANGED = (
                "config_entry_changed"
            )
    return 8


async def check_homekit_event_trigger_and_queue() -> int:
    """HomeKit changes trigger precisely and never cancel an active reconcile."""
    config_changes = sys.modules["homeassistant.config_entries"].ConfigEntryChange
    reasons: list[str] = []
    direct_manager = manager_module.PlatformSyncManager(
        SimpleNamespace(),
        SimpleNamespace(
            enabled=True,
            homekit_source_entry_ids=("selected-source",),
        ),
    )
    direct_manager.schedule = reasons.append
    for change in (
        config_changes.ADDED,
        config_changes.UPDATED,
        config_changes.REMOVED,
    ):
        direct_manager._handle_homekit_config_entry_change(
            change,
            SimpleNamespace(domain="homekit", entry_id="selected-source"),
        )
    direct_manager._handle_homekit_config_entry_change(
        config_changes.UPDATED,
        SimpleNamespace(domain="homekit", entry_id="not-selected"),
    )
    direct_manager._handle_homekit_config_entry_change(
        config_changes.UPDATED,
        SimpleNamespace(domain="google_assistant", entry_id="selected-source"),
    )
    check(
        reasons
        == [
            "homekit_config_entry_added",
            "homekit_config_entry_updated",
            "homekit_config_entry_removed",
        ],
        "Only selected HomeKit source add, update, and remove changes schedule reconciliation",
    )

    class QueueHass:
        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> Any:
            return asyncio.create_task(coroutine)

    manager = manager_module.PlatformSyncManager(
        QueueHass(),
        SimpleNamespace(
            enabled=True,
            homekit_source_entry_ids=("queue-source",),
        ),
    )
    calls: list[str] = []

    async def fake_reconcile(
        reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        calls.append(reason)
        manager.state.last_run = "2026-08-29T00:00:00+00:00"
        if len(calls) == 1:
            manager._handle_homekit_config_entry_change(
                config_changes.UPDATED,
                SimpleNamespace(domain="homekit", entry_id="queue-source"),
            )
        return {"status": "synced", "changed": False}

    async def no_delay(_delay: int) -> None:
        return None

    manager.async_reconcile = fake_reconcile
    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = no_delay
    try:
        manager.schedule("startup_scan")
        task = manager._debounce_task
        check(task is not None, "Startup scan creates a reconciliation task")
        await task
    finally:
        manager_module.asyncio.sleep = original_sleep
    check(
        calls == ["startup_scan"],
        "The mandatory startup scan absorbs source events because it reads the latest state",
    )
    check(not task.cancelled(), "A HomeKit event never self-cancels the active transaction")
    check(
        manager.state.startup_scan_completed == "2026-08-29T00:00:00+00:00",
        "A successful startup scan records a durable completion timestamp",
    )
    return 5


async def check_startup_race_and_safe_stop() -> int:
    """Startup generations stay truthful and active transactions finish on stop."""

    class TaskHass:
        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> Any:
            return asyncio.create_task(coroutine)

    async def no_delay(_delay: int) -> None:
        return None

    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = no_delay
    try:
        race_manager = manager_module.PlatformSyncManager(
            TaskHass(), SimpleNamespace(enabled=True)
        )
        race_calls: list[str] = []

        async def race_reconcile(
            reason: str, apply: bool, *, _background: bool = False
        ) -> dict[str, Any]:
            race_calls.append(reason)
            race_manager.state.last_run = (
                "2026-08-29T00:02:00+00:00"
                if len(race_calls) == 1
                else "2026-08-29T00:03:00+00:00"
            )
            if len(race_calls) == 1:
                race_manager.schedule("startup_scan")
                race_manager.schedule("homekit_config_entry_updated")
            return {"status": "synced", "changed": False}

        race_manager.async_reconcile = race_reconcile
        race_manager.schedule("entity_registry_updated")
        race_task = race_manager._debounce_task
        check(race_task is not None, "Pre-start event creates a reconciliation task")
        await race_task
        check(
            race_calls == ["entity_registry_updated", "startup_scan"],
            "A startup request arriving during an event reconcile runs separately",
        )
        check(
            race_manager.state.startup_scan_completed
            == "2026-08-29T00:03:00+00:00",
            "Startup completion is recorded only after the startup generation runs",
        )

        stop_manager = manager_module.PlatformSyncManager(
            TaskHass(), SimpleNamespace(enabled=True)
        )
        entered = asyncio.Event()
        release = asyncio.Event()
        completed = False

        async def blocking_reconcile(
            reason: str, apply: bool, *, _background: bool = False
        ) -> dict[str, Any]:
            nonlocal completed
            entered.set()
            await release.wait()
            completed = True
            return {"status": "synced", "changed": False}

        stop_manager.async_reconcile = blocking_reconcile
        stop_manager.schedule("homekit_config_entry_updated")
        active_task = stop_manager._debounce_task
        check(active_task is not None, "Active background reconciliation is created")
        await entered.wait()
        stop_task = asyncio.create_task(stop_manager.async_stop())
        await asyncio.wait_for(stop_task, timeout=0.1)
        check(
            active_task.done() and not completed,
            "Stopping promptly cancels a stuck read-only background reconciliation",
        )
        release.set()
        check(
            stop_manager._debounce_task is None
            and stop_manager._stopping,
            "Safe stop clears cancelled background work",
        )

        class DirectBus:
            def async_fire(self, _event: str, _data: Any) -> None:
                return None

        direct_manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=DirectBus()),
            SimpleNamespace(
                enabled=True,
                targets=frozenset(),
                user_rules={},
                locked_rules={},
            ),
        )
        direct_entered = asyncio.Event()
        direct_release = asyncio.Event()
        source_calls = 0

        async def blocking_source(_hass: Any, _config: Any) -> Any:
            nonlocal source_calls
            source_calls += 1
            direct_entered.set()
            await direct_release.wait()
            return models.SourceSnapshot(entities=frozenset())

        async def empty_apple_tv(_hass: Any) -> frozenset[str]:
            return frozenset()

        original_source = manager_module.async_read_source
        original_apple_tv = manager_module.async_find_apple_tv_entities
        manager_module.async_read_source = blocking_source
        manager_module.async_find_apple_tv_entities = empty_apple_tv
        try:
            direct_task = asyncio.create_task(
                direct_manager.async_reconcile(reason="service_sync_now", apply=False)
            )
            await direct_entered.wait()
            direct_stop_task = asyncio.create_task(direct_manager.async_stop())
            await asyncio.wait_for(direct_stop_task, timeout=0.1)
            check(
                direct_task.done(),
                "Stopping promptly cancels a stuck direct service transaction",
            )
            direct_release.set()
            direct_cancelled = False
            try:
                await direct_task
            except asyncio.CancelledError:
                direct_cancelled = True
            check(
                direct_cancelled and source_calls == 1,
                "The cancelled direct transaction exits exactly once",
            )
            stopped_result = await direct_manager.async_reconcile(
                reason="after_stop", apply=False
            )
            check(
                stopped_result == {"status": "stopped", "changed": False}
                and source_calls == 1,
                "No new direct transaction starts after stopping begins",
            )
        finally:
            manager_module.async_read_source = original_source
            manager_module.async_find_apple_tv_entities = original_apple_tv
    finally:
        manager_module.asyncio.sleep = original_sleep
    return 9


async def check_startup_listener_lifecycle() -> int:
    """A fired one-time startup listener must not be unsubscribed twice."""

    class FakeTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def done(self) -> bool:
            return self.cancelled

        def __await__(self) -> Any:
            async def finished() -> None:
                return None

            return finished().__await__()

    class LifecycleBus:
        def __init__(self) -> None:
            self.once_callback: Any = None
            self.normal_unsubscribe_calls = 0
            self.once_unsubscribe_calls = 0

        def async_listen(self, _event: str, _callback: Any) -> Any:
            def unsubscribe() -> None:
                self.normal_unsubscribe_calls += 1

            return unsubscribe

        def async_listen_once(self, _event: str, callback: Any) -> Any:
            self.once_callback = callback

            def unsubscribe() -> None:
                self.once_unsubscribe_calls += 1

            return unsubscribe

        def async_fire(self, _event: str, _data: Any) -> None:
            return None

    class LifecycleHass:
        def __init__(self) -> None:
            self.bus = LifecycleBus()
            self.state = manager_module.CoreState.starting
            self.created_task: FakeTask | None = None

        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> FakeTask:
            coroutine.close()
            self.created_task = FakeTask()
            return self.created_task

    config = SimpleNamespace(
        enabled=True,
        source_kind=const.SourceKind.DASHBOARD,
    )
    hass = LifecycleHass()
    manager = manager_module.PlatformSyncManager(hass, config)
    startup_reasons: list[str] = []
    original_schedule = manager.schedule

    def record_schedule(reason: str) -> None:
        startup_reasons.append(reason)
        original_schedule(reason)

    manager.schedule = record_schedule
    await manager.async_start()
    check(len(manager._unsubscribers) == 3, "Startup listener is initially tracked")

    hass.bus.once_callback(SimpleNamespace(event_type="homeassistant_started"))
    check(
        len(manager._unsubscribers) == 2 and hass.bus.once_unsubscribe_calls == 0,
        "Fired startup listener removes only its manager-side stale handle",
    )
    check(
        startup_reasons == ["startup_scan"],
        "Home Assistant started event schedules exactly one full startup scan",
    )
    await manager.async_stop()
    check(
        hass.bus.normal_unsubscribe_calls == 2 and hass.bus.once_unsubscribe_calls == 0,
        "Manager stop must not unsubscribe a fired one-time listener again",
    )
    check(
        hass.created_task is not None and hass.created_task.cancelled,
        "Manager stop cancels pending startup reconciliation",
    )

    running_hass = LifecycleHass()
    running_hass.state = manager_module.CoreState.running
    running_manager = manager_module.PlatformSyncManager(
        running_hass,
        SimpleNamespace(
            enabled=True,
            source_kind=const.SourceKind.MANUAL,
        ),
    )
    running_reasons: list[str] = []
    running_manager.schedule = running_reasons.append
    await running_manager.async_start()
    check(
        running_reasons == ["startup_scan"],
        "An integration loaded after startup schedules exactly one full startup scan",
    )
    await running_manager.async_stop()

    class RunningHass:
        state = manager_module.CoreState.running

        def async_create_task(self, coroutine: Any, *, eager_start: bool) -> Any:
            return asyncio.create_task(coroutine)

    executing_manager = manager_module.PlatformSyncManager(
        RunningHass(),
        SimpleNamespace(
            enabled=True,
            source_kind=const.SourceKind.MANUAL,
        ),
    )
    executed_reasons: list[str] = []

    async def fake_reconcile(
        reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        executed_reasons.append(reason)
        executing_manager.state.last_run = "2026-08-29T00:01:00+00:00"
        return {"status": "preview", "changed": False}

    async def no_delay(_delay: int) -> None:
        return None

    executing_manager.async_reconcile = fake_reconcile
    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = no_delay
    try:
        await executing_manager.async_start()
        task = executing_manager._debounce_task
        check(task is not None, "Running integration creates its startup scan task")
        await task
    finally:
        manager_module.asyncio.sleep = original_sleep
    check(
        executed_reasons == ["startup_scan"],
        "The mandatory startup scan executes one full reconciliation",
    )
    check(
        executing_manager.state.startup_scan_completed
        == "2026-08-29T00:01:00+00:00",
        "The executed startup scan exposes its completion timestamp",
    )
    await executing_manager.async_stop()
    return 9


async def check_background_readiness_retry() -> int:
    """Background reconciliation retries transient startup readiness failures."""
    config = SimpleNamespace(
        enabled=True,
    )
    manager = manager_module.PlatformSyncManager(SimpleNamespace(), config)
    calls: list[tuple[str, bool, bool]] = []
    sleeps: list[int] = []

    async def fake_reconcile(
        reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        calls.append((reason, apply, _background))
        return {
            "status": "error" if len(calls) == 1 else "synced",
            "changed": False,
        }

    async def fake_sleep(delay: int) -> None:
        sleeps.append(delay)

    manager.async_reconcile = fake_reconcile
    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = fake_sleep
    try:
        await manager._delayed_reconcile("startup_scan")
    finally:
        manager_module.asyncio.sleep = original_sleep

    check(
        calls
        == [
            ("startup_scan", True, True),
            ("retry_after_error", True, True),
        ],
        "Background readiness failure retries with an explicit reason",
    )
    check(sleeps == [2, 15], "Background retry uses debounce then safe backoff")
    check(len(calls) == 2, "Background retry stops immediately after convergence")
    return 3


async def check_config_entry_background_task_ownership() -> int:
    """A managed ConfigEntry exclusively owns scheduled background work."""

    class OwnedTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def done(self) -> bool:
            return self.cancelled

        def __await__(self) -> Any:
            async def finished() -> None:
                return None

            return finished().__await__()

    class OwnerEntry:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, str, bool]] = []
            self.task = OwnedTask()

        def async_create_background_task(
            self,
            hass: Any,
            coroutine: Any,
            name: str,
            *,
            eager_start: bool,
        ) -> OwnedTask:
            coroutine.close()
            self.calls.append((hass, name, eager_start))
            return self.task

    class OwnerHass:
        def async_create_background_task(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("ConfigEntry-owned work must not use hass background tasks")

        def async_create_task(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("ConfigEntry-owned work must not use hass tasks")

    hass = OwnerHass()
    entry = OwnerEntry()
    manager = manager_module.PlatformSyncManager(
        hass,
        SimpleNamespace(enabled=True),
        entry,
    )
    manager.schedule("entity_registry_updated")
    check(
        entry.calls
        == [(hass, "platform_sync reconciliation", True)],
        "A ConfigEntry schedule uses only ConfigEntry.async_create_background_task",
    )
    check(
        manager._debounce_task is entry.task,
        "The manager tracks the exact ConfigEntry-owned background task",
    )
    await manager.async_stop()
    check(
        entry.task.cancelled and manager._debounce_task is None,
        "Stopping cancels and clears the ConfigEntry-owned task",
    )
    return 3


async def check_permanent_error_retry_stop() -> int:
    """A permanent readiness error remains promptly cancellable during backoff."""

    class RetryHass:
        def async_create_background_task(
            self, coroutine: Any, _name: str, *, eager_start: bool
        ) -> Any:
            check(eager_start, "Permanent-error retry task starts eagerly")
            return asyncio.get_running_loop().create_task(coroutine)

    manager = manager_module.PlatformSyncManager(
        RetryHass(), SimpleNamespace(enabled=True)
    )
    calls: list[str] = []
    sleeps: list[int] = []
    waiting_in_backoff = asyncio.Event()
    never_release = asyncio.Event()

    async def permanent_error(
        reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        check(apply and _background, "Permanent error runs only as an apply background job")
        calls.append(reason)
        return {"status": "error", "changed": False}

    async def controlled_sleep(delay: int) -> None:
        sleeps.append(delay)
        if len(sleeps) <= 2:
            return
        waiting_in_backoff.set()
        await never_release.wait()

    manager.async_reconcile = permanent_error
    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = controlled_sleep
    try:
        manager.schedule("startup_scan")
        task = manager._debounce_task
        check(task is not None, "Permanent-error retry creates a background task")
        await asyncio.wait_for(waiting_in_backoff.wait(), timeout=0.1)
        await asyncio.wait_for(manager.async_stop(), timeout=0.1)
    finally:
        manager_module.asyncio.sleep = original_sleep

    check(
        calls == ["startup_scan", "retry_after_error"]
        and sleeps == [2, 15, 15],
        "Permanent errors enter repeated 15-second backoff before cancellation",
    )
    check(
        task.done()
        and manager._debounce_task is None
        and manager._stopping,
        "async_stop promptly cancels a permanent-error retry loop",
    )
    return 6


def transaction_config() -> SimpleNamespace:
    """Return one all-target configuration for manager transaction tests."""
    rules = {platform: models.PlatformRule() for platform in const.TargetPlatform}
    return SimpleNamespace(
        enabled=True,
        targets=frozenset(
            {
                const.TargetPlatform.MATTER,
                const.TargetPlatform.GOOGLE,
                const.TargetPlatform.HOMEKIT,
            }
        ),
        user_rules=rules,
        locked_rules=rules,
    )


class TransactionBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def async_fire(self, event: str, data: Any) -> None:
        self.events.append((event, data))


async def check_selected_target_exact_reconciliation() -> int:
    """Only selected targets converge, including removal of target-only exposures."""
    selected = const.TargetPlatform.GOOGLE
    user_rules = {
        platform: models.PlatformRule() for platform in const.TargetPlatform
    }
    locked_rules = {
        platform: models.PlatformRule() for platform in const.TargetPlatform
    }
    user_rules[selected] = models.PlatformRule(
        include=frozenset({"switch.user_included"}),
        exclude=frozenset(
            {"light.user_excluded", "input_boolean.locked_required"}
        ),
    )
    locked_rules[selected] = models.PlatformRule(
        include=frozenset({"input_boolean.locked_required"}),
        exclude=frozenset({"input_boolean.locked_excluded"}),
    )
    config = SimpleNamespace(
        enabled=True,
        targets=frozenset({selected}),
        user_rules=user_rules,
        locked_rules=locked_rules,
    )
    desired = frozenset(
        {
            "light.from_source",
            "switch.user_included",
            "input_boolean.locked_required",
        }
    )
    expected_removed = frozenset(
        {
            "light.target_only",
            "light.user_excluded",
            "input_boolean.locked_excluded",
        }
    )
    actual = {
        selected: frozenset(
            {
                "light.from_source",
                "light.target_only",
                "light.user_excluded",
                "switch.user_included",
                "input_boolean.locked_excluded",
            }
        ),
        const.TargetPlatform.HOMEKIT: frozenset({"light.homekit_untouched"}),
        const.TargetPlatform.MATTER: frozenset({"light.matter_untouched"}),
    }
    touched: list[tuple[str, Any]] = []
    applied_plans: list[Any] = []

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset(
                {
                    "light.from_source",
                    "light.user_excluded",
                    "input_boolean.locked_excluded",
                }
            )
        )

    async def read_target(
        _hass: Any, _config: Any, platform: Any
    ) -> frozenset[str]:
        touched.append(("read", platform))
        if platform is not selected:
            raise AssertionError("an unselected target must not be read")
        return actual[platform]

    async def validate_target(
        _hass: Any, _config: Any, platform: Any, _expected: Any
    ) -> dict[str, Any]:
        touched.append(("validate", platform))
        if platform is not selected:
            raise AssertionError("an unselected target must not be validated")
        return {"loaded": True}

    async def no_room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def prepare_target(_hass: Any, _config: Any, platform: Any) -> Any:
        touched.append(("prepare", platform))
        if platform is not selected:
            raise AssertionError("an unselected target must not be prepared")
        return SimpleNamespace(platform=platform)

    async def apply_target(
        _hass: Any, _config: Any, plan: Any, _rooms: Any
    ) -> None:
        touched.append(("apply", plan.platform))
        if plan.platform is not selected:
            raise AssertionError("an unselected target must not be applied")
        applied_plans.append(plan)
        actual[plan.platform] = plan.desired

    async def unexpected_restore(_hass: Any, _config: Any, _backup: Any) -> None:
        raise AssertionError("successful exact reconciliation must not roll back")

    original_functions = (
        manager_module.async_read_source,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.async_google_room_updates,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
        manager_module.async_restore_target,
    )
    manager_module.async_read_source = read_source
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_google_room_updates = no_room_updates
    manager_module.async_prepare_target = prepare_target
    manager_module.async_apply_plan = apply_target
    manager_module.async_restore_target = unexpected_restore
    try:
        manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=TransactionBus()), config
        )
        preview = await manager.async_reconcile(reason="exact_preview", apply=False)
        preview_plan = preview["plans"][selected.value]
        check(
            preview["status"] == "preview" and preview["changed"] is True,
            "A selected target with extras produces a changed exact preview",
        )
        check(
            preview_plan["added"] == ["input_boolean.locked_required"],
            "The exact preview restores locked required exposure last",
        )
        check(
            preview_plan["removed"] == sorted(expected_removed),
            "Every target-only or excluded exposure appears in the removal plan",
        )
        check(
            set(preview["plans"]) == {selected.value},
            "The preview contains no unselected target plan",
        )
        check(
            all(platform is selected for _, platform in touched),
            "Preview reads and validates only the selected target",
        )

        touched.clear()
        synced = await manager.async_reconcile(reason="exact_apply", apply=True)
        check(
            len(applied_plans) == 1
            and applied_plans[0].desired == desired
            and applied_plans[0].removed == expected_removed,
            "Apply receives the complete selected-target exact removal plan",
        )
        check(
            actual[selected] == desired,
            "The selected target converges to source minus exclude plus include",
        )
        check(
            actual[const.TargetPlatform.HOMEKIT]
            == frozenset({"light.homekit_untouched"})
            and actual[const.TargetPlatform.MATTER]
            == frozenset({"light.matter_untouched"}),
            "Unselected targets remain unchanged",
        )
        check(
            all(platform is selected for _, platform in touched),
            "Read, validate, prepare, apply, and readback touch only the selected target",
        )
        synced_plan = synced["plans"][selected.value]
        check(
            synced["status"] == "synced"
            and set(synced["plans"]) == {selected.value}
            and synced_plan["missing"] == []
            and synced_plan["extra"] == [],
            "Post-apply readback proves exact convergence for the selected target",
        )
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
        ) = original_functions
    return 10


async def check_manager_transaction() -> int:
    """Verify deterministic prepare/apply/rollback and post-apply readback."""
    platforms = list(const.TargetPlatform)
    check(
        platforms
        == [
            const.TargetPlatform.GOOGLE,
            const.TargetPlatform.HOMEKIT,
            const.TargetPlatform.MATTER,
        ],
        "TargetPlatform declaration defines the deterministic transaction order",
    )

    success_steps: list[str] = []
    success_actual = {platform: frozenset() for platform in platforms}

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset({"light.one"}),
            rooms={"light.one": "客廳"},
        )

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_success(
        _hass: Any, _config: Any, platform: Any
    ) -> frozenset[str]:
        return success_actual[platform]

    async def validate(
        _hass: Any, _config: Any, _platform: Any, _expected: Any
    ) -> dict[str, Any]:
        return {"loaded": True}

    async def room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def prepare_success(_hass: Any, _config: Any, platform: Any) -> Any:
        success_steps.append(f"prepare:{platform.value}")
        return SimpleNamespace(platform=platform)

    async def apply_success(
        _hass: Any, _config: Any, plan: Any, _rooms: Any
    ) -> None:
        success_steps.append(f"apply:{plan.platform.value}")
        success_actual[plan.platform] = plan.desired

    async def unexpected_restore(_hass: Any, _config: Any, _backup: Any) -> None:
        raise AssertionError("Successful transaction must not roll back")

    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_success
    manager_module.async_validate_target = validate
    manager_module.async_google_room_updates = room_updates
    manager_module.async_prepare_target = prepare_success
    manager_module.async_apply_plan = apply_success
    manager_module.async_restore_target = unexpected_restore

    success_hass = SimpleNamespace(bus=TransactionBus())
    success_manager = manager_module.PlatformSyncManager(
        success_hass, transaction_config()
    )
    success_result = await success_manager.async_reconcile(
        reason="transaction_success", apply=True
    )
    check(
        success_steps
        == [
            "prepare:google",
            "prepare:homekit",
            "prepare:matter",
            "apply:google",
            "apply:homekit",
            "apply:matter",
        ],
        "All changed targets must prepare before deterministic ordered apply",
    )
    check(success_result["status"] == "synced", "Successful transaction status")
    for platform in platforms:
        record = success_manager.state.plans[platform.value]
        check(
            record["expected"] == 1
            and record["actual"] == 1
            and record["missing"] == []
            and record["extra"] == []
            and record["added"] == []
            and record["removed"] == [],
            f"{platform.value} state plan must reflect post-apply exact readback",
        )

    failure_steps: list[str] = []
    failure_original = {
        platform: frozenset({f"light.preexisting_{platform.value}"})
        for platform in platforms
    }
    failure_actual = dict(failure_original)

    async def read_failure(
        _hass: Any, _config: Any, platform: Any
    ) -> frozenset[str]:
        return failure_actual[platform]

    async def prepare_failure(_hass: Any, _config: Any, platform: Any) -> Any:
        failure_steps.append(f"prepare:{platform.value}")
        return SimpleNamespace(platform=platform, entities=failure_actual[platform])

    async def apply_failure(
        _hass: Any, _config: Any, plan: Any, _rooms: Any
    ) -> None:
        failure_steps.append(f"apply:{plan.platform.value}")
        # Model a target that changed partially before raising.  Its own backup
        # must therefore be included in reverse rollback.
        failure_actual[plan.platform] = plan.desired
        if plan.platform is const.TargetPlatform.HOMEKIT:
            raise RuntimeError("simulated HomeKit apply failure")

    async def restore_failure(_hass: Any, _config: Any, backup: Any) -> None:
        failure_steps.append(f"rollback:{backup.platform.value}")
        failure_actual[backup.platform] = backup.entities

    manager_module.async_read_target = read_failure
    manager_module.async_prepare_target = prepare_failure
    manager_module.async_apply_plan = apply_failure
    manager_module.async_restore_target = restore_failure

    failure_hass = SimpleNamespace(bus=TransactionBus())
    failure_manager = manager_module.PlatformSyncManager(
        failure_hass, transaction_config()
    )
    previous_log_state = manager_module._LOGGER.disabled
    manager_module._LOGGER.disabled = True
    try:
        try:
            await failure_manager.async_reconcile(
                reason="transaction_failure", apply=True
            )
        except RuntimeError as error:
            check(
                "simulated HomeKit apply failure" in str(error),
                "Original second-target apply failure must propagate after rollback",
            )
        else:
            raise AssertionError("Second-target apply failure must fail reconciliation")
    finally:
        manager_module._LOGGER.disabled = previous_log_state
    check(
        failure_steps
        == [
            "prepare:google",
            "prepare:homekit",
            "prepare:matter",
            "apply:google",
            "apply:homekit",
            "rollback:homekit",
            "rollback:google",
        ],
        "Failure must reverse-roll back every attempted target, including the failing one",
    )
    check(
        failure_actual == failure_original,
        "Reverse rollback restores target-only exposures removed earlier in the transaction",
    )
    check(failure_manager.state.status == "error", "Failed transaction state")
    return 10


async def check_noop_single_read_validation() -> int:
    """A no-op reuses its initial read and validation for every target."""
    platforms = list(const.TargetPlatform)
    reads = {platform: 0 for platform in platforms}
    validations = {platform: 0 for platform in platforms}
    current = {
        platform: frozenset({"light.already_exact"}) for platform in platforms
    }
    prepare_calls = 0
    apply_calls = 0

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(entities=frozenset({"light.already_exact"}))

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_target(
        _hass: Any, _config: Any, platform: Any
    ) -> frozenset[str]:
        reads[platform] += 1
        return current[platform]

    async def validate_target(
        _hass: Any, _config: Any, platform: Any, expected: Any
    ) -> dict[str, Any]:
        validations[platform] += 1
        check(
            expected == current[platform],
            f"{platform.value} no-op validates the initial exact set",
        )
        return {"loaded": True}

    async def no_room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def unexpected_prepare(_hass: Any, _config: Any, _platform: Any) -> Any:
        nonlocal prepare_calls
        prepare_calls += 1
        raise AssertionError("A no-op must not prepare a target")

    async def unexpected_apply(
        _hass: Any, _config: Any, _plan: Any, _rooms: Any
    ) -> None:
        nonlocal apply_calls
        apply_calls += 1
        raise AssertionError("A no-op must not apply a target")

    original_functions = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.async_google_room_updates,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_google_room_updates = no_room_updates
    manager_module.async_prepare_target = unexpected_prepare
    manager_module.async_apply_plan = unexpected_apply
    try:
        manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=TransactionBus()), transaction_config()
        )
        result = await manager.async_reconcile(reason="noop", apply=True)
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
        ) = original_functions

    check(
        result["status"] == "synced" and result["changed"] is False,
        "An exact target set completes as a no-op sync",
    )
    check(
        reads == {platform: 1 for platform in platforms},
        "A no-op reads every target exactly once without post-apply readback",
    )
    check(
        validations == {platform: 1 for platform in platforms},
        "A no-op validates every target exactly once",
    )
    check(
        prepare_calls == 0 and apply_calls == 0,
        "A no-op performs no prepare or apply operation",
    )
    return 7


async def check_cancelled_transaction_rollback() -> int:
    """Cancellation during apply or readback rolls back every attempted target."""
    platforms = list(const.TargetPlatform)

    async def run_scenario(cancel_stage: str) -> tuple[bool, list[str], dict[Any, Any]]:
        actual = {platform: frozenset() for platform in platforms}
        read_counts = {platform: 0 for platform in platforms}
        mutation_steps: list[str] = []

        async def read_source(_hass: Any, _config: Any) -> Any:
            return models.SourceSnapshot(entities=frozenset({"light.one"}))

        async def find_apple_tv(_hass: Any) -> frozenset[str]:
            return frozenset()

        async def read_target(
            _hass: Any, _config: Any, platform: Any
        ) -> frozenset[str]:
            read_counts[platform] += 1
            if (
                cancel_stage == "readback"
                and platform is const.TargetPlatform.HOMEKIT
                and read_counts[platform] == 2
            ):
                mutation_steps.append("cancel:readback:homekit")
                raise asyncio.CancelledError("simulated post-apply readback cancellation")
            return actual[platform]

        async def validate_target(
            _hass: Any, _config: Any, _platform: Any, _expected: Any
        ) -> dict[str, Any]:
            return {"loaded": True}

        async def no_room_updates(
            _hass: Any, _config: Any, _desired: Any, _rooms: Any
        ) -> tuple[str, ...]:
            return ()

        async def prepare_target(_hass: Any, _config: Any, platform: Any) -> Any:
            mutation_steps.append(f"prepare:{platform.value}")
            return SimpleNamespace(platform=platform)

        async def apply_target(
            _hass: Any, _config: Any, plan: Any, _rooms: Any
        ) -> None:
            mutation_steps.append(f"apply:{plan.platform.value}")
            actual[plan.platform] = plan.desired
            if (
                cancel_stage == "apply"
                and plan.platform is const.TargetPlatform.HOMEKIT
            ):
                raise asyncio.CancelledError("simulated apply cancellation")

        async def restore_target(_hass: Any, _config: Any, backup: Any) -> None:
            mutation_steps.append(f"rollback:{backup.platform.value}")
            actual[backup.platform] = frozenset()

        original_functions = (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
        )
        manager_module.async_read_source = read_source
        manager_module.async_find_apple_tv_entities = find_apple_tv
        manager_module.async_read_target = read_target
        manager_module.async_validate_target = validate_target
        manager_module.async_google_room_updates = no_room_updates
        manager_module.async_prepare_target = prepare_target
        manager_module.async_apply_plan = apply_target
        manager_module.async_restore_target = restore_target
        cancelled = False
        try:
            manager = manager_module.PlatformSyncManager(
                SimpleNamespace(bus=TransactionBus()), transaction_config()
            )
            try:
                await manager.async_reconcile(
                    reason=f"cancel_during_{cancel_stage}", apply=True
                )
            except asyncio.CancelledError:
                cancelled = True
        finally:
            (
                manager_module.async_read_source,
                manager_module.async_find_apple_tv_entities,
                manager_module.async_read_target,
                manager_module.async_validate_target,
                manager_module.async_google_room_updates,
                manager_module.async_prepare_target,
                manager_module.async_apply_plan,
                manager_module.async_restore_target,
            ) = original_functions
        return cancelled, mutation_steps, actual

    apply_cancelled, apply_steps, apply_actual = await run_scenario("apply")
    check(
        apply_cancelled,
        "CancelledError from an apply operation propagates after rollback",
    )
    check(
        apply_steps
        == [
            "prepare:google",
            "prepare:homekit",
            "prepare:matter",
            "apply:google",
            "apply:homekit",
            "rollback:homekit",
            "rollback:google",
        ],
        "Apply cancellation reverse-rolls back every attempted target",
    )
    check(
        apply_actual == {platform: frozenset() for platform in platforms},
        "Apply cancellation restores all attempted target sets",
    )

    read_cancelled, read_steps, read_actual = await run_scenario("readback")
    check(
        read_cancelled,
        "CancelledError from post-apply readback propagates after rollback",
    )
    check(
        read_steps
        == [
            "prepare:google",
            "prepare:homekit",
            "prepare:matter",
            "apply:google",
            "apply:homekit",
            "apply:matter",
            "cancel:readback:homekit",
            "rollback:matter",
            "rollback:homekit",
            "rollback:google",
        ],
        "Readback cancellation reverse-rolls back every attempted target",
    )
    check(
        read_actual == {platform: frozenset() for platform in platforms},
        "Readback cancellation restores all attempted target sets",
    )
    return 6


async def check_rollback_and_stop_deadlines() -> int:
    """Rollback and unload share bounded, explicitly observable failure states."""
    original_logger_disabled = manager_module._LOGGER.disabled
    manager_module._LOGGER.disabled = True
    platform = const.TargetPlatform.GOOGLE
    rules = {target: models.PlatformRule() for target in const.TargetPlatform}
    config = SimpleNamespace(
        enabled=True,
        targets=frozenset({platform}),
        user_rules=rules,
        locked_rules=rules,
    )

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(entities=frozenset({"light.one"}))

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_target(_hass: Any, _config: Any, _platform: Any) -> frozenset[str]:
        return frozenset()

    async def validate_target(
        _hass: Any, _config: Any, _platform: Any, _expected: Any
    ) -> dict[str, Any]:
        return {"loaded": True}

    async def no_room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def prepare_target(_hass: Any, _config: Any, target: Any) -> Any:
        return SimpleNamespace(platform=target)

    async def failed_apply(
        _hass: Any, _config: Any, _plan: Any, _rooms: Any
    ) -> None:
        raise RuntimeError("simulated apply failure")

    async def stuck_restore(_hass: Any, _config: Any, _backup: Any) -> None:
        await asyncio.Event().wait()

    original_functions = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.async_google_room_updates,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
        manager_module.async_restore_target,
    )
    original_rollback_timeout = manager_module.ROLLBACK_TIMEOUT_SECONDS
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_google_room_updates = no_room_updates
    manager_module.async_prepare_target = prepare_target
    manager_module.async_apply_plan = failed_apply
    manager_module.async_restore_target = stuck_restore
    manager_module.ROLLBACK_TIMEOUT_SECONDS = 0.01
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(bus=TransactionBus()), config
    )
    try:
        try:
            await asyncio.wait_for(
                manager.async_reconcile(reason="deadline", apply=True),
                timeout=0.2,
            )
        except RuntimeError as error:
            check(
                "rollback was incomplete for google" in str(error),
                "A rollback deadline reports its exact incomplete target",
            )
        else:
            raise AssertionError("A timed-out rollback must fail explicitly")
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
        ) = original_functions
        manager_module.ROLLBACK_TIMEOUT_SECONDS = original_rollback_timeout
    check(
        manager.state.rollback_status == "incomplete"
        and manager.state.rollback_incomplete_targets == ["google"],
        "A timed-out rollback remains visible in diagnostics",
    )

    stop_manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def stubborn_transaction(
        _reason: str, _apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
        return {"status": "stopped", "changed": False}

    stop_manager._async_reconcile_transaction = stubborn_transaction
    direct_task = asyncio.create_task(
        stop_manager.async_reconcile(reason="stubborn", apply=True)
    )
    await entered.wait()
    stop_manager._active_attempted_targets.add(const.TargetPlatform.MATTER)
    original_stop_timeout = manager_module.STOP_DRAIN_TIMEOUT_SECONDS
    manager_module.STOP_DRAIN_TIMEOUT_SECONDS = 0.01
    try:
        await asyncio.wait_for(stop_manager.async_stop(), timeout=0.2)
        check(
            stop_manager.state.rollback_status == "incomplete"
            and stop_manager.state.rollback_incomplete_targets == ["matter"],
            "The single stop deadline marks an unverified rollback incomplete",
        )
        check(
            direct_task in stop_manager._direct_tasks and not direct_task.done(),
            "A still-running task remains tracked after the stop deadline",
        )
    finally:
        manager_module.STOP_DRAIN_TIMEOUT_SECONDS = original_stop_timeout
        release.set()
        await direct_task
    check(
        direct_task not in stop_manager._direct_tasks,
        "A late-finishing direct task removes its own tracking entry",
    )
    manager_module._LOGGER.disabled = original_logger_disabled
    return 5


async def check_diagnostics_privacy() -> int:
    """Shared diagnostics never expose topology, entity IDs, paths, or hosts."""
    rule = models.PlatformRule(
        include=frozenset({"input_boolean.private_helper"}),
        exclude=frozenset({"camera.private_camera"}),
    )
    config = SimpleNamespace(
        enabled=True,
        source_kind=const.SourceKind.DASHBOARD,
        source_pages=(("private-dashboard", "private-view"),),
        source_entities=frozenset({"light.private_light"}),
        targets=frozenset({const.TargetPlatform.GOOGLE}),
        google_config_path="/config/private-google.yaml",
        matter_host="192.0.2.10",
        homekit_source_entry_ids=("private-source-entry",),
        homekit_managed_entry_ids=("private-target-entry",),
        user_rules={platform: rule for platform in const.TargetPlatform},
        locked_rules={platform: rule for platform in const.TargetPlatform},
        locked_homekit_apple_tv_exclusion=True,
    )
    state = SimpleNamespace(
        status="synced",
        last_reason="startup_scan",
        last_run="2026-01-01T00:00:00+00:00",
        startup_scan_completed="2026-01-01T00:00:00+00:00",
        source_fingerprint="safe-hash",
        plans={
            "google": {
                "expected": 2,
                "actual": 1,
                "added": ["light.private_light"],
                "removed": ["switch.private_switch"],
                "missing": ["light.private_light"],
                "extra": ["switch.private_switch"],
                "metadata_updates": ["light.private_light"],
                "changed": True,
                "runtime": {"loaded": True, "config_entries": 1},
            }
        },
        error="Connection failed for 192.0.2.10",
        rollback_status="not_needed",
        rollback_incomplete_targets=[],
    )
    result = await diagnostics_module.async_get_config_entry_diagnostics(
        SimpleNamespace(),
        SimpleNamespace(runtime_data=SimpleNamespace(config=config, state=state)),
    )
    encoded = json.dumps(result, sort_keys=True)
    check(
        not any(
            secret in encoded
            for secret in (
                "private-dashboard",
                "private-view",
                "private_light",
                "private_switch",
                "private_helper",
                "private_camera",
                "private-google.yaml",
                "192.0.2.10",
                "private-source-entry",
                "private-target-entry",
                "safe-hash",
            )
        ),
        "Diagnostics contain no entity IDs, dashboard paths, hostnames, file paths, or Config Entry IDs",
    )
    check(
        result["config"]["source_entity_count"] == 1
        and "source_fingerprint" not in result["state"]
        and result["config"]["user_rule_counts"]["google"]
        == {"include": 1, "exclude": 1}
        and result["state"]["plans"]["google"]["added"] == 1
        and result["state"]["plans"]["google"]["missing"] == 1
        and result["state"]["has_source_fingerprint"] is True
        and result["state"]["has_error"] is True,
        "Diagnostics retain useful counts and health state after redaction",
    )
    return 2


async def main() -> None:
    assertions = 0
    assertions += check_config_entry_only_schema()
    assertions += await check_homekit_adapter()
    assertions += check_matter_runtime()
    assertions += check_matter_exact_configuration()
    assertions += await check_matter_validation_contract()
    assertions += await check_matter_request_overall_timeout()
    assertions += check_google_room_schema()
    assertions += await check_single_switch_runtime()
    assertions += await check_safe_migration()
    assertions += check_legacy_registry_cleanup()
    assertions += check_internal_timing_config()
    assertions += await check_source_watcher_policy()
    assertions += await check_homekit_event_trigger_and_queue()
    assertions += await check_startup_race_and_safe_stop()
    assertions += await check_startup_listener_lifecycle()
    assertions += await check_background_readiness_retry()
    assertions += await check_config_entry_background_task_ownership()
    assertions += await check_permanent_error_retry_stop()
    assertions += await check_selected_target_exact_reconciliation()
    assertions += await check_manager_transaction()
    assertions += await check_noop_single_read_validation()
    assertions += await check_cancelled_transaction_rollback()
    assertions += await check_rollback_and_stop_deadlines()
    assertions += await check_diagnostics_privacy()
    print(f"PASS: {assertions} adapter and safety-gate acceptance assertions")


if __name__ == "__main__":
    asyncio.run(main())
