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
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    components = ModuleType("homeassistant.components")
    persistent_notification = ModuleType(
        "homeassistant.components.persistent_notification"
    )
    homekit = ModuleType("homeassistant.components.homekit")
    homekit.__path__ = []
    homekit_util = ModuleType("homeassistant.components.homekit.util")
    lovelace = ModuleType("homeassistant.components.lovelace")
    lovelace_const = ModuleType("homeassistant.components.lovelace.const")
    lovelace_dashboard = ModuleType("homeassistant.components.lovelace.dashboard")
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

    class EntityStateAttribute:
        FRIENDLY_NAME = "friendly_name"

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigEntryChange = ConfigEntryChange
    config_entries.ConfigEntryState = ConfigEntryState
    config_entries.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"
    const.EVENT_CALL_SERVICE = "call_service"
    const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    const.CONF_ENTITY_ID = "entity_id"
    const.CONF_PORT = "port"
    const.EntityStateAttribute = EntityStateAttribute
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
    event.async_call_later = lambda *_args, **_kwargs: lambda: None
    device_registry.EVENT_DEVICE_REGISTRY_UPDATED = "device_registry_updated"
    entity_registry.EVENT_ENTITY_REGISTRY_UPDATED = "entity_registry_updated"
    device_registry.async_get = lambda _hass: SimpleNamespace(devices={})
    entity_registry.async_get = lambda _hass: SimpleNamespace(entities={})
    helpers.device_registry = device_registry
    helpers.entity_registry = entity_registry
    helpers.config_validation = config_validation
    helpers.dispatcher = dispatcher
    lovelace_const.EVENT_LOVELACE_UPDATED = "lovelace_updated"
    lovelace_dashboard.CONFIG_STORAGE_KEY = "lovelace.{}"
    lovelace_dashboard.CONFIG_STORAGE_KEY_DEFAULT = "lovelace"
    homekit_util.state_needs_accessory_mode = lambda _state: False
    persistent_notification.async_create = lambda *_args, **_kwargs: None
    persistent_notification.async_dismiss = lambda *_args, **_kwargs: None
    components.persistent_notification = persistent_notification
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
            "homeassistant.helpers.device_registry": device_registry,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.components": components,
            "homeassistant.components.persistent_notification": (
                persistent_notification
            ),
            "homeassistant.components.homekit": homekit,
            "homeassistant.components.homekit.util": homekit_util,
            "homeassistant.components.lovelace": lovelace,
            "homeassistant.components.lovelace.const": lovelace_const,
            "homeassistant.components.lovelace.dashboard": lovelace_dashboard,
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
sources_module = load(
    "custom_components.platform_sync.sources_actual", "sources.py"
)

sources_stub = ModuleType("custom_components.platform_sync.sources")
sources_stub.async_read_source = None
sources_stub.async_find_apple_tv_entities = None
sys.modules["custom_components.platform_sync.sources"] = sources_stub
manager_module = load("custom_components.platform_sync.manager", "manager.py")


async def _empty_matter_manual_pairing_snapshot(
    _config: Any, _desired: frozenset[str]
) -> Any:
    """Keep manager-only tests local; Matter helper tests call targets directly."""
    return targets.MatterManualPairingSnapshot(frozenset())


manager_module.async_matter_manual_pairing_entities = (
    _empty_matter_manual_pairing_snapshot
)
manager_module.google_native_unrepresentable_entities = (
    lambda _hass, _desired: frozenset()
)
manager_module.matter_native_unrepresentable_entities = (
    lambda _desired: frozenset()
)
integration_module = load("custom_components.platform_sync.__init__", "__init__.py")
diagnostics_module = load(
    "custom_components.platform_sync.diagnostics", "diagnostics.py"
)


_DEFAULT_HOMEKIT_RUNTIME = object()


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
        source: str | None = None,
        runtime_data: Any = _DEFAULT_HOMEKIT_RUNTIME,
    ) -> None:
        self.entry_id = entry_id
        self.options = deepcopy(options or {})
        self.data = deepcopy(data or {})
        self.state = state
        self.domain = domain
        self.title = title or entry_id
        self.source = source
        self.runtime_data = (
            SimpleNamespace(homekit=SimpleNamespace(status=1))
            if runtime_data is _DEFAULT_HOMEKIT_RUNTIME
            else runtime_data
        )


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
        self.states = SimpleNamespace(
            get=lambda entity_id: SimpleNamespace(entity_id=entity_id)
        )


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
    await targets._apply_homekit(
        hass,
        config,
        frozenset({"light.one", "sensor.new", "lock.front"}),
    )
    check(
        hass.config_entries.updated == ["accessory", "main"]
        and hass.config_entries.reloaded == ["main", "accessory"],
        "A no-op HomeKit plan does not update or reload any Config Entry",
    )

    runtime_entry = FakeEntry(
        "runtime-main",
        options={
            "filter": {"include_entities": ["light.runtime"]},
            "mode": "bridge",
        },
        runtime_data=SimpleNamespace(homekit=SimpleNamespace(status=3)),
    )
    runtime_hass = FakeHass([runtime_entry])
    runtime_config = SimpleNamespace(
        homekit_managed_entry_ids=("runtime-main",)
    )
    try:
        await targets.async_validate_target(
            runtime_hass,
            runtime_config,
            const.TargetPlatform.HOMEKIT,
            frozenset({"light.runtime"}),
        )
    except RuntimeError:
        check(True, "HomeKit loaded-but-waiting runtime is not accepted as ready")
    else:
        raise AssertionError("HomeKit WAIT runtime must fail closed")
    runtime_entry.runtime_data.homekit.status = 1
    runtime = await targets.async_validate_target(
        runtime_hass,
        runtime_config,
        const.TargetPlatform.HOMEKIT,
        frozenset({"light.runtime"}),
    )
    check(
        runtime["runtime_verified_entries"] == 1,
        "HomeKit RUNNING runtime is independently verified when supported",
    )
    runtime_entry.runtime_data = None
    try:
        await targets.async_validate_target(
            runtime_hass,
            runtime_config,
            const.TargetPlatform.HOMEKIT,
            frozenset({"light.runtime"}),
        )
    except RuntimeError:
        check(True, "HomeKit with unreadable runtime status fails closed")
    else:
        raise AssertionError("Unknown HomeKit runtime must not be accepted as ready")

    native_entry = FakeEntry(
        "native-main",
        options={
            "filter": {"include_entities": ["light.old"]},
            "mode": "bridge",
        },
        source="user",
        runtime_data=SimpleNamespace(homekit=SimpleNamespace(status=1)),
    )
    native_hass = FakeHass([native_entry])

    def native_update(entry: FakeEntry, *, options: dict[str, Any]) -> None:
        entry.options = deepcopy(options)
        native_hass.config_entries.updated.append(entry.entry_id)
        # Simulate HomeKit's built-in Config Entry update listener completing
        # its one native reload with a fresh runtime object.
        entry.runtime_data = SimpleNamespace(
            homekit=SimpleNamespace(status=1)
        )

    native_hass.config_entries.async_update_entry = native_update
    await targets._apply_homekit(
        native_hass,
        SimpleNamespace(homekit_managed_entry_ids=("native-main",)),
        frozenset({"light.new"}),
    )
    check(
        native_hass.config_entries.updated == ["native-main"]
        and native_hass.config_entries.reloaded == [],
        "HomeKit UI entries rely on their native update listener without a duplicate reload",
    )

    imported_entry = FakeEntry(
        "import-main",
        options={
            "filter": {
                "include_entities": ["light.imported"],
                "include_domains": [],
                "include_entity_globs": [],
                "exclude_entities": [],
                "exclude_domains": [],
                "exclude_entity_globs": [],
            },
            "mode": "bridge",
        },
        source="import",
    )
    imported_hass = FakeHass([imported_entry])
    imported_original = deepcopy(imported_entry.options)
    try:
        await targets._apply_homekit(
            imported_hass,
            SimpleNamespace(homekit_managed_entry_ids=("import-main",)),
            frozenset({"light.changed"}),
        )
    except RuntimeError as error:
        check(
            "YAML-managed" in str(error),
            "Changed YAML/import HomeKit targets fail with a durable-ownership reason",
        )
    else:
        raise AssertionError("Changed YAML/import HomeKit target must fail closed")
    check(
        imported_entry.options == imported_original
        and imported_hass.config_entries.updated == []
        and imported_hass.config_entries.reloaded == [],
        "YAML/import preflight rejects the whole change before any mutation",
    )
    await targets._apply_homekit(
        imported_hass,
        SimpleNamespace(homekit_managed_entry_ids=("import-main",)),
        frozenset({"light.imported"}),
    )
    check(
        imported_entry.options == imported_original,
        "An unchanged YAML/import HomeKit target remains readable without mutation",
    )
    try:
        targets.validate_target_configuration(
            imported_hass,
            SimpleNamespace(homekit_managed_entry_ids=("import-main",)),
            const.TargetPlatform.HOMEKIT,
        )
    except RuntimeError:
        check(True, "Config Flow structural validation rejects imported writable targets")
    else:
        raise AssertionError("An imported HomeKit entry must not be offered as writable")

    mixed_main = FakeEntry(
        "mixed-main",
        options={
            "filter": {"include_entities": ["light.old"]},
            "homekit_mode": "bridge",
        },
    )
    mixed_accessory = FakeEntry(
        "mixed-accessory",
        options={
            "filter": {
                "include_entities": ["lock.pinned"],
                "include_domains": [],
                "include_entity_globs": [],
                "exclude_entities": [],
                "exclude_domains": [],
                "exclude_entity_globs": [],
            },
            "homekit_mode": "accessory",
        },
        source="import",
    )
    mixed_hass = FakeHass([mixed_main, mixed_accessory])
    mixed_config = SimpleNamespace(
        homekit_managed_entry_ids=("mixed-main", "mixed-accessory")
    )
    targets.validate_target_configuration(
        mixed_hass, mixed_config, const.TargetPlatform.HOMEKIT
    )
    await targets._apply_homekit(
        mixed_hass,
        mixed_config,
        frozenset({"light.new", "lock.pinned"}),
    )
    check(
        mixed_hass.config_entries.updated == ["mixed-main"]
        and mixed_hass.config_entries.reloaded == ["mixed-main"]
        and targets._homekit_entities(mixed_accessory) == {"lock.pinned"},
        "A UI-managed main Bridge can change while an exact imported Accessory stays pinned",
    )

    imported_side_bridge = FakeEntry(
        "imported-side-bridge",
        options={
            "filter": {
                "include_entities": ["switch.fixed_side"],
                "include_domains": [],
                "include_entity_globs": [],
                "exclude_entities": [],
                "exclude_domains": [],
                "exclude_entity_globs": [],
            },
            "homekit_mode": "bridge",
        },
        source="import",
    )
    multi_entity_main = FakeEntry(
        "multi-entity-main",
        options={
            "filter": {
                "include_entities": ["light.main_one", "light.main_two"]
            },
            "homekit_mode": "bridge",
        },
    )
    bridge_mode_hass = FakeHass([multi_entity_main, imported_side_bridge])
    bridge_mode_config = SimpleNamespace(
        homekit_managed_entry_ids=(
            "multi-entity-main",
            "imported-side-bridge",
        ),
        homekit_main_entry_id="multi-entity-main",
        homekit_source_entry_ids=(),
        homekit_lifecycle_entry_ids=("imported-side-bridge",),
    )
    targets.validate_target_configuration(
        bridge_mode_hass,
        bridge_mode_config,
        const.TargetPlatform.HOMEKIT,
    )
    await targets._apply_homekit(
        bridge_mode_hass,
        bridge_mode_config,
        frozenset(
            {
                "light.main_one",
                "switch.fixed_side",
            }
        ),
    )
    check(
        targets._homekit_mode(imported_side_bridge) == "bridge"
        and targets._homekit_entities(imported_side_bridge)
        == {"switch.fixed_side"}
        and targets._homekit_entities(multi_entity_main) == {"light.main_one"}
        and bridge_mode_hass.config_entries.updated == ["multi-entity-main"]
        and bridge_mode_hass.config_entries.reloaded == ["multi-entity-main"],
        "A main Bridge can shrink from two entities to one while a Bridge-mode side stays fixed",
    )
    check(
        targets.homekit_managed_main_entry_id(
            bridge_mode_hass, bridge_mode_config
        )
        == "multi-entity-main",
        "The durable ID still identifies the main Bridge after it becomes a singleton",
    )
    check(
        await targets.async_read_target(
            bridge_mode_hass,
            bridge_mode_config,
            const.TargetPlatform.HOMEKIT,
        )
        == frozenset({"light.main_one", "switch.fixed_side"}),
        "HomeKit read uses the explicit singleton-main layout",
    )
    check(
        not targets.homekit_missing_accessory_mode_entities(
            bridge_mode_hass,
            bridge_mode_config,
            frozenset({"light.main_one", "switch.fixed_side"}),
        ),
        "HomeKit classification uses the explicit singleton-main layout",
    )
    bridge_runtime = await targets.async_validate_target(
        bridge_mode_hass,
        bridge_mode_config,
        const.TargetPlatform.HOMEKIT,
        frozenset({"light.main_one", "switch.fixed_side"}),
    )
    check(
        bridge_runtime["managed_entries"] == 2
        and bridge_runtime["runtime_verified_entries"] == 2,
        "HomeKit validation preserves the explicit singleton-main layout",
    )
    imported_side_bridge.runtime_data.homekit.status = 3
    try:
        await targets.async_validate_target(
            bridge_mode_hass,
            bridge_mode_config,
            const.TargetPlatform.HOMEKIT,
            frozenset({"light.main_one", "switch.fixed_side"}),
        )
    except RuntimeError:
        check(
            True,
            "A non-running prune candidate still fails without an explicit allowance",
        )
    else:
        raise AssertionError("Non-running HomeKit runtime cannot be generally accepted")
    pending_runtime = await targets.async_validate_target(
        bridge_mode_hass,
        bridge_mode_config,
        const.TargetPlatform.HOMEKIT,
        frozenset({"light.main_one", "switch.fixed_side"}),
        allowed_nonrunning_homekit_entry_ids=frozenset(
            {"imported-side-bridge"}
        ),
    )
    check(
        pending_runtime["loaded"] is True
        and pending_runtime["runtime_verified"] is False
        and pending_runtime["runtime_verified_entries"] == 1
        and pending_runtime["runtime_pending_prune_entries"] == 1,
        "A lifecycle-owned side candidate is counted as pending, never runtime-verified",
    )
    await targets.async_restore_target(
        bridge_mode_hass,
        bridge_mode_config,
        targets.TargetBackup(
            const.TargetPlatform.HOMEKIT,
            {
                "options": {
                    entry.entry_id: deepcopy(entry.options)
                    for entry in (multi_entity_main, imported_side_bridge)
                },
                "entities": frozenset(
                    {"light.main_one", "switch.fixed_side"}
                ),
            },
        ),
        allowed_nonrunning_homekit_entry_ids=frozenset(
            {"imported-side-bridge"}
        ),
    )
    check(
        True,
        "HomeKit rollback validation carries the exact pending-prune runtime allowance",
    )
    try:
        await targets.async_validate_target(
            bridge_mode_hass,
            bridge_mode_config,
            const.TargetPlatform.HOMEKIT,
            frozenset({"light.main_one", "switch.fixed_side"}),
            allowed_nonrunning_homekit_entry_ids=frozenset(
                {"multi-entity-main"}
            ),
        )
    except RuntimeError as error:
        check(
            "Only managed HomeKit side entries" in str(error),
            "The main Bridge can never receive a pending-prune runtime allowance",
        )
    else:
        raise AssertionError("The HomeKit main Bridge runtime cannot be exempted")
    source_overlap_config = SimpleNamespace(
        homekit_managed_entry_ids=(
            "multi-entity-main",
            "imported-side-bridge",
        ),
        homekit_main_entry_id="multi-entity-main",
        homekit_source_entry_ids=("imported-side-bridge",),
        homekit_lifecycle_entry_ids=("imported-side-bridge",),
    )
    try:
        await targets.async_validate_target(
            bridge_mode_hass,
            source_overlap_config,
            const.TargetPlatform.HOMEKIT,
            frozenset({"light.main_one", "switch.fixed_side"}),
            allowed_nonrunning_homekit_entry_ids=frozenset(
                {"imported-side-bridge"}
            ),
        )
    except RuntimeError as error:
        check(
            "source entry cannot use" in str(error),
            "A HomeKit source entry can never receive a pending-prune runtime allowance",
        )
    else:
        raise AssertionError("A HomeKit source runtime cannot be exempted")
    try:
        await targets.async_read_target(
            bridge_mode_hass,
            SimpleNamespace(
                homekit_managed_entry_ids=(
                    "multi-entity-main",
                    "imported-side-bridge",
                )
            ),
            const.TargetPlatform.HOMEKIT,
        )
    except RuntimeError as error:
        check(
            "exactly one main Bridge" in str(error),
            "Legacy singleton Bridge ambiguity fails closed instead of silently retargeting",
        )
    else:
        raise AssertionError("Ambiguous legacy singleton Bridges must fail closed")
    try:
        targets.homekit_managed_main_entry_id(
            bridge_mode_hass,
            SimpleNamespace(
                homekit_managed_entry_ids=(
                    "multi-entity-main",
                    "imported-side-bridge",
                ),
                homekit_main_entry_id="missing-main",
                homekit_source_entry_ids=(),
            ),
        )
    except RuntimeError as error:
        check(
            "not a managed target entry" in str(error),
            "An explicit main ID outside the managed set fails closed",
        )
    else:
        raise AssertionError("An unmanaged explicit main ID must fail closed")
    try:
        targets.homekit_managed_main_entry_id(
            bridge_mode_hass,
            SimpleNamespace(
                homekit_managed_entry_ids=(
                    "multi-entity-main",
                    "imported-side-bridge",
                ),
                homekit_main_entry_id="multi-entity-main",
                homekit_source_entry_ids=("multi-entity-main",),
            ),
        )
    except RuntimeError as error:
        check(
            "cannot also be a source entry" in str(error),
            "An explicit main/source ownership overlap fails closed",
        )
    else:
        raise AssertionError("The explicit main Bridge cannot also be a source")
    try:
        targets.homekit_managed_main_entry_id(
            hass,
            SimpleNamespace(
                homekit_managed_entry_ids=("main", "accessory"),
                homekit_main_entry_id="accessory",
                homekit_source_entry_ids=(),
            ),
        )
    except RuntimeError as error:
        check(
            "configured as an Accessory" in str(error),
            "An explicit main ID pointing at Accessory mode fails closed",
        )
    else:
        raise AssertionError("An Accessory entry cannot be the explicit main Bridge")

    rollback_main = FakeEntry(
        "rollback-main",
        options={
            "filter": {"include_entities": ["light.changed"]},
            "homekit_mode": "bridge",
        },
    )
    rollback_import = FakeEntry(
        "rollback-import",
        options={
            "filter": {"include_entities": ["lock.external_change"]},
            "homekit_mode": "accessory",
        },
        source="import",
    )
    rollback_hass = FakeHass([rollback_main, rollback_import])
    rollback_config = SimpleNamespace(
        homekit_managed_entry_ids=("rollback-main", "rollback-import")
    )
    rollback_backup = targets.TargetBackup(
        const.TargetPlatform.HOMEKIT,
        {
            "options": {
                "rollback-main": {
                    "filter": {"include_entities": ["light.before"]},
                    "homekit_mode": "bridge",
                },
                "rollback-import": {
                    "filter": {"include_entities": ["lock.before"]},
                    "homekit_mode": "accessory",
                },
            },
            "entities": frozenset({"light.before", "lock.before"}),
        },
    )
    try:
        await targets.async_restore_target(
            rollback_hass, rollback_config, rollback_backup
        )
    except RuntimeError as error:
        check(
            "rollback is incomplete" in str(error),
            "Imported HomeKit drift makes rollback fail closed with an incomplete result",
        )
    else:
        raise AssertionError("Imported HomeKit drift must make rollback fail closed")
    check(
        targets._homekit_entities(rollback_main) == {"light.before"}
        and rollback_hass.config_entries.updated == ["rollback-main"]
        and rollback_hass.config_entries.reloaded == ["rollback-main"],
        "Rollback still restores the UI-managed main Bridge",
    )
    check(
        targets._homekit_entities(rollback_import) == {"lock.external_change"}
        and "rollback-import" not in rollback_hass.config_entries.updated
        and "rollback-import" not in rollback_hass.config_entries.reloaded,
        "Rollback never updates or reloads a drifted YAML/import Accessory",
    )

    settle_entries = [
        FakeEntry("reload-fails", source="import"),
        FakeEntry("reload-finishes", source="import"),
    ]
    settle_hass = FakeHass(settle_entries)
    sibling_finished = False

    async def partially_failing_reload(entry_id: str) -> bool:
        nonlocal sibling_finished
        if entry_id == "reload-fails":
            return False
        await asyncio.sleep(0.01)
        sibling_finished = True
        return True

    settle_hass.config_entries.async_reload = partially_failing_reload
    try:
        await targets._reload_homekit_entries(
            settle_hass,
            settle_entries,
            previous_runtime={entry.entry_id: entry.runtime_data for entry in settle_entries},
        )
    except RuntimeError:
        check(
            sibling_finished,
            "HomeKit reload failure waits for bounded siblings before rollback can begin",
        )
    else:
        raise AssertionError("A failed HomeKit reload must propagate after siblings settle")

    cancel_entry = FakeEntry("reload-during-cancel", source="import")
    cancel_hass = FakeHass([cancel_entry])
    reload_started = asyncio.Event()
    reload_release = asyncio.Event()
    reload_finished = False
    reload_cancelled = False

    async def delayed_reload(entry_id: str) -> bool:
        nonlocal reload_finished, reload_cancelled
        check(entry_id == cancel_entry.entry_id, "The expected HomeKit entry reloads")
        reload_started.set()
        try:
            await reload_release.wait()
        except asyncio.CancelledError:
            reload_cancelled = True
            raise
        reload_finished = True
        return True

    cancel_hass.config_entries.async_reload = delayed_reload
    reload_task = asyncio.create_task(
        targets._reload_homekit_entries(
            cancel_hass,
            [cancel_entry],
            previous_runtime={cancel_entry.entry_id: cancel_entry.runtime_data},
        )
    )
    await reload_started.wait()
    reload_task.cancel()
    await asyncio.sleep(0)
    check(
        not reload_task.done() and not reload_cancelled,
        "Caller cancellation is deferred without cancelling an active HomeKit reload",
    )
    reload_task.cancel()
    await asyncio.sleep(0)
    check(
        not reload_task.done() and not reload_cancelled,
        "Repeated cancellation cannot interrupt the HomeKit reload drain",
    )
    reload_release.set()
    try:
        await reload_task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("HomeKit reload cancellation must propagate after drain")
    check(
        reload_finished and not reload_cancelled,
        "HomeKit reload cancellation propagates only after the active reload settles",
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
    structurally_valid = await targets.async_validate_homekit_source_entries(
        FakeHass([unavailable]), ("unavailable",)
    )
    check(
        structurally_valid == frozenset({"light.unavailable"}),
        "HomeKit source selection accepts a structurally valid transiently unloaded entry",
    )
    unavailable.disabled_by = "user"
    try:
        await targets.async_validate_homekit_source_entries(
            FakeHass([unavailable]), ("unavailable",)
        )
    except targets.HomeKitSourceEntryUnavailableError:
        check(True, "A disabled HomeKit source is rejected before configuration save")
    else:
        raise AssertionError("A disabled HomeKit source must fail structural validation")
    unavailable.disabled_by = None

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

    routing_entities = frozenset(
        {
            "light.keep",
            "camera.in_main",
            "lock.in_main",
            "media_player.tv_in_main",
            "remote.activity_in_main",
        }
    )
    accessory_only = routing_entities - {"light.keep"}
    routing_main = FakeEntry(
        "routing-main",
        options={
            "filter": {"include_entities": sorted(routing_entities)},
            "mode": "bridge",
        },
    )
    routing_hass = FakeHass([routing_main])
    routing_hass.states = SimpleNamespace(
        get=lambda entity_id: SimpleNamespace(entity_id=entity_id)
    )
    native_classifier = sys.modules[
        "homeassistant.components.homekit.util"
    ].state_needs_accessory_mode
    sys.modules[
        "homeassistant.components.homekit.util"
    ].state_needs_accessory_mode = lambda state: state.entity_id in {
        "media_player.tv_in_main",
        "remote.activity_in_main",
    }
    routing_config = SimpleNamespace(homekit_managed_entry_ids=(routing_main.entry_id,))
    try:
        check(
            targets.homekit_missing_accessory_mode_entities(
                routing_hass, routing_config, routing_entities
            )
            == accessory_only,
            "Accessory-only entities already on the main Bridge still require migration",
        )
        check(
            targets.homekit_new_accessory_mode_entities(
                routing_hass, routing_config, routing_entities
            )
            == accessory_only,
            "The compatibility classifier exposes the migration-safe missing-side set",
        )
        routing_options = deepcopy(routing_main.options)
        try:
            await targets._apply_homekit(
                routing_hass, routing_config, routing_entities
            )
        except RuntimeError as error:
            check(
                "created or migrated" in str(error)
                and routing_main.options == routing_options,
                "Direct HomeKit apply cannot leave accessory-only entities on the main Bridge",
            )
        else:
            raise AssertionError(
                "Accessory-only entities on the main Bridge must be deferred before apply"
            )
        await targets._apply_homekit(
            routing_hass, routing_config, routing_entities - accessory_only
        )
        check(
            targets._homekit_entities(routing_main) == {"light.keep"},
            "A manager can safely defer the missing-side set and remove it from the main Bridge",
        )
    finally:
        sys.modules[
            "homeassistant.components.homekit.util"
        ].state_needs_accessory_mode = native_classifier

    missing_state_main = FakeEntry(
        "missing-state-main",
        options={
            "filter": {"include_entities": ["light.keep"]},
            "mode": "bridge",
        },
    )
    missing_state_hass = FakeHass([missing_state_main])
    missing_state_hass.states = SimpleNamespace(get=lambda _entity_id: None)
    missing_state_config = SimpleNamespace(
        homekit_managed_entry_ids=(missing_state_main.entry_id,)
    )
    check(
        targets.homekit_missing_accessory_mode_entities(
            missing_state_hass,
            missing_state_config,
            frozenset({"camera.not_loaded", "lock.not_loaded"}),
        )
        == {"camera.not_loaded", "lock.not_loaded"},
        "Camera and lock domains remain classifiable while their HA state is absent",
    )
    try:
        targets.homekit_missing_accessory_mode_entities(
            missing_state_hass,
            missing_state_config,
            frozenset({"media_player.not_loaded", "remote.not_loaded"}),
        )
    except RuntimeError as error:
        check(
            "requires current state" in str(error),
            "State-dependent media-player and remote routing fails closed",
        )
    else:
        raise AssertionError(
            "Missing media-player or remote state must not be treated as Bridge-safe"
        )

    covered_main = FakeEntry(
        "covered-main",
        options={
            "filter": {"include_entities": ["light.keep"]},
            "mode": "bridge",
        },
    )
    covered_accessory = FakeEntry(
        "covered-accessory",
        options={
            "filter": {"include_entities": ["camera.covered"]},
            "mode": "accessory",
        },
    )
    covered_hass = FakeHass([covered_main, covered_accessory])
    covered_hass.states = SimpleNamespace(get=lambda _entity_id: None)
    check(
        not targets.homekit_missing_accessory_mode_entities(
            covered_hass,
            SimpleNamespace(
                homekit_managed_entry_ids=(
                    covered_main.entry_id,
                    covered_accessory.entry_id,
                )
            ),
            frozenset({"light.keep", "camera.covered"}),
        ),
        "A dedicated side entry is exact accessory-mode coverage even during a state gap",
    )
    recovery_main = FakeEntry(
        "recovery-main",
        options={
            "filter": {"include_entities": ["light.recovery"]},
            "homekit_mode": "bridge",
        },
    )
    recovery_accessory = FakeEntry(
        "recovery-accessory",
        options={
            "filter": {"include_entities": ["lock.recovery"]},
            "homekit_mode": "accessory",
        },
        source="user",
        runtime_data=SimpleNamespace(homekit=SimpleNamespace(status=0)),
    )
    recovery_hass = FakeHass([recovery_main, recovery_accessory])

    async def recover_reload(entry_id: str) -> bool:
        check(
            entry_id == recovery_accessory.entry_id,
            "HomeKit recovery reloads only the stopped runtime",
        )
        recovery_hass.config_entries.reloaded.append(entry_id)
        recovery_accessory.runtime_data = SimpleNamespace(
            homekit=SimpleNamespace(status=1)
        )
        return True

    recovery_hass.config_entries.async_reload = recover_reload
    recovery_result = await targets.async_recover_homekit_runtime(
        recovery_hass,
        SimpleNamespace(
            homekit_managed_entry_ids=(
                recovery_main.entry_id,
                recovery_accessory.entry_id,
            ),
            homekit_main_entry_id=recovery_main.entry_id,
            homekit_source_entry_ids=(),
            homekit_lifecycle_entry_ids=(recovery_accessory.entry_id,),
        ),
        frozenset({"light.recovery", "lock.recovery"}),
    )
    check(
        recovery_result["runtime_recovered_entries"] == 1
        and recovery_hass.config_entries.reloaded
        == [recovery_accessory.entry_id],
        "Exact loaded HomeKit layouts recover stopped runtimes by native reload",
    )
    homekit_util = sys.modules.pop("homeassistant.components.homekit.util")
    try:
        try:
            targets.homekit_new_accessory_mode_entities(
                FakeHass([main]),
                SimpleNamespace(homekit_managed_entry_ids=(main.entry_id,)),
                frozenset({"light.new"}),
            )
        except RuntimeError:
            check(True, "Unavailable HomeKit classifier fails closed")
        else:
            raise AssertionError("Unavailable HomeKit classifier must fail closed")
    finally:
        sys.modules["homeassistant.components.homekit.util"] = homekit_util
    return 78


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
            "token": "configured-test-token",
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
        and runtime["loaded_devices"] == 1
        and runtime["process_generation_verified"] is False
        and runtime["controller_verified"] is False,
        "Matter validation reports plugin lifecycle and exact device counts",
    )
    return 2


def matter_snapshot(
    *,
    plugin_updates: dict[str, Any] | None = None,
    config_updates: dict[str, Any] | None = None,
    settings_updates: dict[str, Any] | None = None,
    devices: list[dict[str, Any]] | None = None,
) -> Any:
    """Build one exact, credential-redacted Matterbridge test snapshot."""
    plugin_config = {
        "token": "configured",
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
    }
    plugin_config.update(config_updates or {})
    plugin = {
        "name": targets.MATTER_PLUGIN,
        "enabled": True,
        "loaded": True,
        "started": True,
        "error": False,
        "restartRequired": False,
        "registeredDevices": 1,
        "configJson": plugin_config,
    }
    plugin.update(plugin_updates or {})
    information = {
        "bridgeStatus": "Started",
        "restartRequired": False,
        "fixedRestartRequired": False,
        "startupAt": 1_000,
        "runningTimes": 4,
    }
    information.update(settings_updates or {})
    loaded_devices = devices
    if loaded_devices is None:
        loaded_devices = [
            {
                "pluginName": targets.MATTER_PLUGIN,
                "endpoint": 1,
                "uniqueId": "device-one",
                "serial": "serial-one",
            }
        ]
    return targets.MatterRuntimeSnapshot(
        settings={"matterbridgeInformation": information},
        plugin=plugin,
        plugin_config=plugin_config,
        devices=loaded_devices,
        allowlist=frozenset(plugin_config["whiteList"]),
    )


def check_matter_recovery_guard() -> int:
    """Only exact, credentialed runtime failures permit a process restart."""
    expected = frozenset({"light.one"})
    recoverable = (
        matter_snapshot(plugin_updates={"error": True}),
        matter_snapshot(plugin_updates={"started": False}),
        matter_snapshot(plugin_updates={"restartRequired": True}),
        matter_snapshot(
            plugin_updates={"registeredDevices": 0},
            devices=[],
        ),
    )
    for snapshot in recoverable:
        check(
            targets._matter_recovery_eligible(snapshot, expected),
            "A narrowly recoverable Matterbridge runtime state is accepted",
        )

    blocked = (
        matter_snapshot(plugin_updates={"enabled": False, "error": True}),
        matter_snapshot(plugin_updates={"name": "other-plugin", "error": True}),
        matter_snapshot(
            plugin_updates={"error": True}, config_updates={"token": ""}
        ),
        matter_snapshot(
            plugin_updates={"error": True},
            config_updates={"filterByLabel": "unsafe-filter"},
        ),
        matter_snapshot(
            plugin_updates={"error": True},
            config_updates={"whiteList": ["light.other"]},
        ),
        matter_snapshot(
            plugin_updates={"error": True},
            settings_updates={"bridgeStatus": "Stopped"},
        ),
    )
    for snapshot in blocked:
        check(
            not targets._matter_recovery_eligible(snapshot, expected),
            "Unsafe Matterbridge states never authorize a process restart",
        )
    check(
        "configured" not in repr(recoverable[0]),
        "Matterbridge runtime snapshots never render credential material",
    )
    return 11


async def check_matter_process_generation_barrier() -> int:
    """A ready old process cannot satisfy a full-restart convergence wait."""
    expected = frozenset({"light.one"})
    old = matter_snapshot()
    new = matter_snapshot(
        settings_updates={"startupAt": 2_000, "runningTimes": 5}
    )
    snapshots = [old, new]
    reads = 0

    async def read_snapshot(_config: Any) -> Any:
        nonlocal reads
        reads += 1
        return snapshots.pop(0)

    async def no_delay(_delay: float) -> None:
        return None

    originals = (
        targets._read_matter_runtime_snapshot,
        targets.asyncio.sleep,
    )
    targets._read_matter_runtime_snapshot = read_snapshot
    targets.asyncio.sleep = no_delay
    try:
        runtime = await targets._wait_matter_runtime(
            SimpleNamespace(),
            expected,
            timeout=1,
            after_generation=targets.MatterProcessGeneration(1_000, 4),
        )
    finally:
        (
            targets._read_matter_runtime_snapshot,
            targets.asyncio.sleep,
        ) = originals
    check(reads == 2, "A ready old process is rejected before the new generation")
    check(
        runtime["process_generation_verified"] is True
        and runtime["controller_verified"] is False,
        "Process convergence is explicit and never claims native controller readback",
    )
    check(
        targets._matter_process_generation(old.settings)
        == targets.MatterProcessGeneration(1_000, 4),
        "Official startupAt and runningTimes fields form the process generation",
    )
    check(
        targets._matter_process_generation_advanced(
            targets.MatterProcessGeneration(2_000, 5),
            targets.MatterProcessGeneration(1_000, 4),
        ),
        "Both process generation signals advancing satisfies the barrier",
    )
    check(
        not targets._matter_process_generation_advanced(
            targets.MatterProcessGeneration(2_000, 4),
            targets.MatterProcessGeneration(1_000, 4),
        ),
        "A new startupAt alone cannot satisfy the generation barrier",
    )
    check(
        not targets._matter_process_generation_advanced(
            targets.MatterProcessGeneration(1_000, 5),
            targets.MatterProcessGeneration(1_000, 4),
        ),
        "A higher runningTimes alone cannot satisfy the generation barrier",
    )
    for invalid in (
        {"startupAt": True, "runningTimes": 5},
        {"startupAt": 2_000, "runningTimes": "5"},
        {"startupAt": 0, "runningTimes": 5},
    ):
        try:
            targets._matter_process_generation(
                {"matterbridgeInformation": invalid}
            )
        except RuntimeError:
            check(True, "Malformed Matterbridge generation fails closed")
        else:
            raise AssertionError("Malformed process generation must fail closed")
    return 9


async def check_matter_manual_pairing_snapshot() -> int:
    """RVC server-node guidance is secret-free and never claims pairing."""
    desired = frozenset({"vacuum.upstairs", "light.one"})
    enabled = True

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        check(command == "plugins", "Matter RVC pairing guidance reads plugin config")
        return [
            matter_snapshot(
                config_updates={"enableServerRvc": enabled}
            ).plugin
        ]

    original_request = targets._matter_request
    targets._matter_request = request
    try:
        snapshot = await targets.async_matter_manual_pairing_entities(
            SimpleNamespace(), desired
        )
        check(
            snapshot.entities == frozenset({"vacuum.upstairs"})
            and snapshot.controller_pairing_verified is False,
            "Server RVC mode lists only vacuum nodes without claiming fabric pairing",
        )
        check(
            "qr" not in repr(snapshot).casefold()
            and "pin" not in repr(snapshot).casefold(),
            "Matter manual pairing snapshot contains no QR code or PIN",
        )
        enabled = False
        disabled = await targets.async_matter_manual_pairing_entities(
            SimpleNamespace(), desired
        )
        check(
            not disabled.entities
            and disabled.controller_pairing_verified is False,
            "Disabled server RVC mode requires no separate-node guidance",
        )
    finally:
        targets._matter_request = original_request

    for malformed in (None, "true", 1):
        async def malformed_request(
            _config: Any,
            command: str,
            payload: Any = None,
            value: Any = malformed,
        ) -> Any:
            return [
                matter_snapshot(
                    config_updates={"enableServerRvc": value}
                ).plugin
            ]

        targets._matter_request = malformed_request
        try:
            try:
                await targets.async_matter_manual_pairing_entities(
                    SimpleNamespace(), desired
                )
            except RuntimeError:
                check(True, "Missing or malformed enableServerRvc fails closed")
            else:
                raise AssertionError("Malformed enableServerRvc must fail closed")
        finally:
            targets._matter_request = original_request
    return 7


async def check_matter_removal_restart_and_rollback() -> int:
    """Removals and compensating rollback use one generation-gated restart."""
    desired = frozenset({"light.one"})
    removed = frozenset({"camera.old"})
    old = matter_snapshot(
        config_updates={"whiteList": ["camera.old", "light.one"]}
    )
    generation = targets.MatterProcessGeneration(1_000, 4)
    calls: list[str] = []

    async def read_snapshot(_config: Any) -> Any:
        calls.append("snapshot")
        return old

    async def persist(_config: Any, plugin_config: Any) -> frozenset[str]:
        check(
            plugin_config["whiteList"] == ["light.one"],
            "Removal persists the exact reduced allowlist",
        )
        calls.append("persist")
        return desired

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        check(command == "settings", "Removal snapshots generation after persistence")
        calls.append("settings")
        return {
            "matterbridgeInformation": {
                "startupAt": 1_000,
                "runningTimes": 4,
            }
        }

    async def fire(_config: Any, command: str, payload: Any = None) -> None:
        check(command == "restart", "Removal uses the full-process restart endpoint")
        calls.append("restart")

    async def wait(
        _config: Any,
        expected: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        check(
            expected == desired and after_generation == generation,
            "Removal readback is gated by the exact pre-restart generation",
        )
        calls.append("wait")
        return {"loaded": True, "controller_verified": False}

    def authorize() -> bool:
        calls.append("authorized")
        return True

    originals = (
        targets._read_matter_runtime_snapshot,
        targets._persist_matter_config,
        targets._matter_request,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
    )
    targets._read_matter_runtime_snapshot = read_snapshot
    targets._persist_matter_config = persist
    targets._matter_request = request
    targets._matter_fire_and_forget = fire
    targets._wait_matter_runtime = wait
    try:
        process_restarted = await targets._apply_matter(
            SimpleNamespace(),
            desired,
            removed=removed,
            before_matter_process_restart=authorize,
        )
    finally:
        (
            targets._read_matter_runtime_snapshot,
            targets._persist_matter_config,
            targets._matter_request,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
        ) = originals
    check(
        process_restarted is True
        and calls
        == ["snapshot", "authorized", "persist", "settings", "restart", "wait"],
        "Removal reserves its full restart before persisting and sends it exactly once",
    )

    propagated: dict[str, Any] = {}

    async def apply_matter(
        _config: Any,
        expected: frozenset[str],
        *,
        removed: frozenset[str],
        before_matter_process_restart: Any = None,
    ) -> bool:
        propagated.update(
            expected=expected,
            removed=removed,
            callback=before_matter_process_restart,
        )
        return True

    plan = models.TargetPlan(
        platform=const.TargetPlatform.MATTER,
        desired=desired,
        current=desired | removed,
        added=frozenset(),
        removed=removed,
    )
    original_apply = targets._apply_matter
    targets._apply_matter = apply_matter
    try:
        await targets.async_apply_plan(
            SimpleNamespace(),
            SimpleNamespace(),
            plan,
            before_matter_process_restart=authorize,
        )
    finally:
        targets._apply_matter = original_apply
    check(
        propagated["removed"] == removed
        and propagated["expected"] == desired
        and propagated["callback"] is authorize,
        "TargetPlan removal provenance reaches the Matter adapter",
    )

    rollback_calls: list[str] = []
    rollback_entities = frozenset({"light.before"})
    rollback_generation = targets.MatterProcessGeneration(3_000, 8)
    rollback_setting_reads = 0

    async def rollback_request(
        _config: Any, command: str, payload: Any = None
    ) -> Any:
        nonlocal rollback_setting_reads
        check(command == "settings", "Rollback snapshots generation before restart")
        rollback_setting_reads += 1
        rollback_calls.append(f"settings-{rollback_setting_reads}")
        return {
            "matterbridgeInformation": {
                "startupAt": 2_500 if rollback_setting_reads == 1 else 3_000,
                "runningTimes": 7 if rollback_setting_reads == 1 else 8,
            }
        }

    async def rollback_persist(_config: Any, plugin_config: Any) -> frozenset[str]:
        rollback_calls.append("persist")
        return rollback_entities

    async def rollback_fire(
        _config: Any, command: str, payload: Any = None
    ) -> None:
        check(command == "restart", "Matter rollback uses a full process restart")
        rollback_calls.append("restart")

    async def rollback_wait(
        _config: Any,
        expected: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        check(
            expected == rollback_entities
            and after_generation == rollback_generation,
            "Rollback readback requires the post-rollback process generation",
        )
        rollback_calls.append("wait")
        return {"loaded": True, "controller_verified": False}

    async def validate(
        _hass: Any, _config: Any, _platform: Any, expected: frozenset[str]
    ) -> Any:
        check(expected == rollback_entities, "Rollback retains exact validation")
        rollback_calls.append("validate")
        return {"loaded": True, "controller_verified": False}

    originals = (
        targets._matter_request,
        targets._persist_matter_config,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
        targets.async_validate_target,
    )
    targets._matter_request = rollback_request
    targets._persist_matter_config = rollback_persist
    targets._matter_fire_and_forget = rollback_fire
    targets._wait_matter_runtime = rollback_wait
    targets.async_validate_target = validate
    try:
        await targets.async_restore_target(
            SimpleNamespace(),
            SimpleNamespace(),
            targets.TargetBackup(
                const.TargetPlatform.MATTER,
                {
                    "config": matter_snapshot(
                        config_updates={"whiteList": ["light.before"]}
                    ).plugin_config,
                    "entities": rollback_entities,
                },
            ),
        )
    finally:
        (
            targets._matter_request,
            targets._persist_matter_config,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
            targets.async_validate_target,
        ) = originals
    check(
        rollback_calls
        == [
            "settings-1",
            "persist",
            "settings-2",
            "restart",
            "wait",
            "validate",
        ],
        "Matter rollback never uses plugin restart and validates after generation convergence",
    )
    return 9


async def check_matter_apply_process_fallback() -> int:
    """A stuck plugin restart falls back to one full process restart."""
    expected = frozenset({"light.one"})
    calls: list[str] = []
    waits = 0

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        calls.append(command)
        if command == "plugins":
            return [matter_snapshot().plugin]
        if command in {"savepluginconfig", "restartplugin"}:
            return {}
        raise AssertionError(f"Unexpected Matterbridge command: {command}")

    async def read_snapshot(_config: Any) -> Any:
        calls.append("snapshot")
        return matter_snapshot(plugin_updates={"error": True})

    async def fire(_config: Any, command: str, payload: Any = None) -> None:
        check(command == "restart", "Fallback restarts the Matterbridge process")
        calls.append("restart")

    async def wait(
        _config: Any,
        desired: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        nonlocal waits
        check(desired == expected, "Both waits retain the exact expected allowlist")
        waits += 1
        calls.append(f"wait-{waits}")
        if waits == 1:
            check(after_generation is None, "Plugin restart has no process barrier")
            raise RuntimeError("safe test timeout")
        check(
            after_generation == targets.MatterProcessGeneration(1_000, 4),
            "Fallback wait uses the exact pre-restart process generation",
        )
        return {"loaded": True}

    def authorize() -> bool:
        calls.append("authorized")
        return True

    originals = (
        targets._matter_request,
        targets._read_matter_runtime_snapshot,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
    )
    targets._matter_request = request
    targets._read_matter_runtime_snapshot = read_snapshot
    targets._matter_fire_and_forget = fire
    targets._wait_matter_runtime = wait
    try:
        process_restarted = await targets._apply_matter(
            SimpleNamespace(),
            expected,
            before_matter_process_restart=authorize,
        )
        fallback_calls = list(calls)
        calls.clear()
        waits = 0
        try:
            await targets._apply_matter(
                SimpleNamespace(),
                expected,
                before_matter_process_restart=lambda: False,
            )
        except RuntimeError as error:
            check(
                "blocked by the recovery guard" in str(error),
                "A denied process restart fails closed",
            )
        else:
            raise AssertionError("A denied process restart must not be sent")
        denied_calls = list(calls)
    finally:
        (
            targets._matter_request,
            targets._read_matter_runtime_snapshot,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
        ) = originals
    check(
        fallback_calls
        == [
            "plugins",
            "savepluginconfig",
            "plugins",
            "restartplugin",
            "wait-1",
            "snapshot",
            "authorized",
            "restart",
            "wait-2",
        ],
        "Plugin restart precedes exactly one guarded process fallback and readback",
    )
    check(process_restarted is True, "Apply reports its full process fallback")
    check(
        denied_calls
        == [
            "plugins",
            "savepluginconfig",
            "plugins",
            "restartplugin",
            "wait-1",
            "snapshot",
        ],
        "An unauthorized fallback sends no Matterbridge process restart",
    )
    return 6


async def check_matter_restart_cancellation_marker() -> int:
    """Cancellation after a restart send cannot erase the shared attempt marker."""
    expected = frozenset({"light.one"})
    config = SimpleNamespace(
        enabled=True,
        matter_host="matterbridge.cancel.test",
        matter_port=8283,
    )
    hass = SimpleNamespace(data={})
    manager = manager_module.PlatformSyncManager(hass, config)
    runtime_waiting = asyncio.Event()
    waits = 0
    restart_calls = 0

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        if command == "plugins":
            return [matter_snapshot().plugin]
        if command in {"savepluginconfig", "restartplugin"}:
            return {}
        raise AssertionError(f"Unexpected Matterbridge command: {command}")

    async def read_snapshot(_config: Any) -> Any:
        return matter_snapshot(plugin_updates={"error": True})

    async def fire(_config: Any, command: str, payload: Any = None) -> None:
        nonlocal restart_calls
        guard = manager._matter_recovery_guard
        check(
            command == "restart"
            and guard.attempted_for_episode
            and guard.process_restart_attempted
            and guard.last_attempt is not None,
            "The shared attempt marker exists before the restart command is sent",
        )
        restart_calls += 1

    async def wait(
        _config: Any,
        desired: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        nonlocal waits
        waits += 1
        if waits == 1:
            check(after_generation is None, "Plugin restart has no process barrier")
            raise RuntimeError("safe simulated plugin restart timeout")
        check(
            after_generation == targets.MatterProcessGeneration(1_000, 4),
            "Cancelled fallback already entered generation-gated readback",
        )
        runtime_waiting.set()
        await asyncio.Event().wait()

    originals = (
        targets._matter_request,
        targets._read_matter_runtime_snapshot,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
    )
    targets._matter_request = request
    targets._read_matter_runtime_snapshot = read_snapshot
    targets._matter_fire_and_forget = fire
    targets._wait_matter_runtime = wait
    task = asyncio.create_task(
        targets._apply_matter(
            config,
            expected,
            before_matter_process_restart=manager._before_matter_process_restart,
        )
    )
    cancelled = False
    try:
        await asyncio.wait_for(runtime_waiting.wait(), timeout=0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        (
            targets._matter_request,
            targets._read_matter_runtime_snapshot,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
        ) = originals

    check(cancelled, "Cancellation during process runtime readback propagates")
    reloaded = manager_module.PlatformSyncManager(hass, config)
    check(
        reloaded._matter_recovery_guard is manager._matter_recovery_guard
        and reloaded._matter_recovery_guard.attempted_for_episode,
        "The cancellation marker survives Config Entry manager replacement",
    )
    check(
        not reloaded._before_matter_process_restart(),
        "A replacement manager cannot send another restart in the same episode",
    )
    check(restart_calls == 1, "Cancellation leaves exactly one restart command sent")
    return 5


async def check_guarded_matter_runtime_recovery() -> int:
    """Automatic recovery uses plugin restart before one process fallback."""
    expected = frozenset({"light.one"})
    calls: list[str] = []
    snapshots = 0
    waits = 0

    async def read_snapshot(_config: Any) -> Any:
        nonlocal snapshots
        snapshots += 1
        calls.append("snapshot")
        return matter_snapshot(plugin_updates={"error": True})

    async def backup(_config: Any) -> None:
        calls.append("backup-ready")

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        check(
            command == "restartplugin"
            and payload == {"pluginName": targets.MATTER_PLUGIN},
            "Recovery first restarts only the Home Assistant plugin",
        )
        calls.append("restartplugin")
        return {}

    async def fire(_config: Any, command: str, payload: Any = None) -> None:
        check(command == "restart", "Recovery restarts the full Matterbridge process")
        calls.append(command)

    async def wait(
        _config: Any,
        entities: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        nonlocal waits
        waits += 1
        check(entities == expected, "Recovery waits for the exact expected runtime")
        calls.append(f"wait-{waits}")
        if waits == 1:
            check(after_generation is None, "Plugin recovery has no process barrier")
            raise RuntimeError("safe simulated plugin restart timeout")
        if waits == 2:
            check(
                after_generation == targets.MatterProcessGeneration(1_000, 4),
                "Recovery fallback waits beyond the pre-restart generation",
            )
        else:
            check(after_generation is None, "Successful plugin recovery stays plugin-only")
        return {"loaded": True}

    originals = (
        targets._read_matter_runtime_snapshot,
        targets._matter_create_backup_ready,
        targets._matter_request,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
    )
    targets._read_matter_runtime_snapshot = read_snapshot
    targets._matter_create_backup_ready = backup
    targets._matter_request = request
    targets._matter_fire_and_forget = fire
    targets._wait_matter_runtime = wait
    try:
        runtime = await targets.async_recover_matter_runtime(
            SimpleNamespace(),
            expected,
            before_matter_process_restart=lambda: calls.append("authorized")
            is None,
        )
        fallback_calls = list(calls)
        fallback_snapshot_count = snapshots
        calls.clear()
        plugin_only_runtime = await targets.async_recover_matter_runtime(
            SimpleNamespace(),
            expected,
            before_matter_process_restart=lambda: calls.append("unexpected-authorize")
            is None,
        )
        plugin_only_calls = list(calls)
        calls.clear()

        async def backup_unverified(_config: Any) -> None:
            calls.append("backup-unverified")
            raise RuntimeError("safe simulated backup completion timeout")

        targets._matter_create_backup_ready = backup_unverified
        try:
            await targets.async_recover_matter_runtime(
                SimpleNamespace(),
                expected,
                before_matter_process_restart=lambda: calls.append(
                    "unexpected-authorize"
                )
                is None,
            )
        except RuntimeError:
            backup_failure_calls = list(calls)
        else:
            raise AssertionError("An unverified backup must block every restart")
    finally:
        (
            targets._read_matter_runtime_snapshot,
            targets._matter_create_backup_ready,
            targets._matter_request,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
        ) = originals
    check(runtime == {"loaded": True}, "Recovery returns verified runtime state")
    check(
        fallback_calls
        == [
            "snapshot",
            "backup-ready",
            "restartplugin",
            "wait-1",
            "snapshot",
            "authorized",
            "restart",
            "wait-2",
        ]
        and fallback_snapshot_count == 2,
        "Completed backup and plugin retry strictly precede one guarded process fallback",
    )
    check(
        plugin_only_runtime == {"loaded": True}
        and plugin_only_calls
        == ["snapshot", "backup-ready", "restartplugin", "wait-3"],
        "A successful plugin restart prevents a full Matterbridge process restart",
    )
    check(
        backup_failure_calls == ["snapshot", "backup-unverified"],
        "An unverified backup blocks both plugin and process restart commands",
    )
    return 7


async def check_matter_source_runtime_validation() -> int:
    """Matterbridge used only as a source still requires a healthy runtime."""
    calls: list[tuple[str, frozenset[str]]] = []
    expected = frozenset({"light.one"})

    async def read_platform_source(_hass: Any, _config: Any, _platform: Any) -> Any:
        return expected

    async def validate_target(
        _hass: Any, _config: Any, platform: Any, entities: frozenset[str]
    ) -> Any:
        calls.append((platform.value, entities))
        return {"loaded": True}

    originals = (
        targets.async_read_platform_source,
        targets.async_validate_target,
    )
    targets.async_read_platform_source = read_platform_source
    targets.async_validate_target = validate_target
    try:
        source = await sources_module.async_read_source(
            SimpleNamespace(),
            SimpleNamespace(source_kind=const.SourceKind.MATTER),
        )
    finally:
        (
            targets.async_read_platform_source,
            targets.async_validate_target,
        ) = originals
    check(source.entities == expected, "Matter source retains its exact allowlist")
    check(
        calls == [(const.TargetPlatform.MATTER.value, expected)],
        "Matter source performs full runtime validation",
    )

    async def reject_runtime(
        _hass: Any, _config: Any, _platform: Any, entities: frozenset[str]
    ) -> Any:
        raise targets.MatterbridgeRuntimeError(
            "devices_zero", entities, recoverable=True
        )

    targets.async_read_platform_source = read_platform_source
    targets.async_validate_target = reject_runtime
    try:
        try:
            await sources_module.async_read_source(
                SimpleNamespace(),
                SimpleNamespace(source_kind=const.SourceKind.MATTER),
            )
        except targets.MatterbridgeRuntimeError as error:
            check(
                error.reason == "devices_zero",
                "Matter source propagates a safe runtime reason code",
            )
        else:
            raise AssertionError("An unhealthy Matter source must fail closed")
    finally:
        (
            targets.async_read_platform_source,
            targets.async_validate_target,
        ) = originals
    return 3


async def check_dashboard_fresh_storage_and_camera_fields() -> int:
    """Storage audits bypass Lovelace cache and retain camera-only fields."""
    nested = sources_module.extract_dashboard_entities(
        {
            "views": [
                {
                    "path": "default-view",
                    "cards": [
                        {
                            "camera_image": "camera.front",
                            "elements": [{"entity": "camera.side"}],
                        },
                        {
                            "camera_entity": "camera.live",
                            "card": {"entity": "sensor.stream_health"},
                            "visibility": [
                                {"entity": "input_boolean.visibility_only"}
                            ],
                        },
                        {
                            "type": "conditional",
                            "conditions": [
                                {"entity": "binary_sensor.condition_only"}
                            ],
                            "card": {"entity": "light.visible_card"},
                        },
                    ],
                }
            ]
        },
        "default-view",
    )
    check(
        nested.entities
        == {
            "camera.front",
            "camera.side",
            "camera.live",
            "sensor.stream_health",
            "light.visible_card",
        },
        "Dashboard extraction follows camera fields and presentation containers without condition-only helpers",
    )

    stale_calls = 0

    class StorageDashboard:
        mode = "storage"
        config = {"id": "lovelace"}

        async def async_load(self, _force: bool) -> dict[str, Any]:
            nonlocal stale_calls
            stale_calls += 1
            return {
                "views": [
                    {"path": "default-view", "cards": [{"entity": "camera.stale"}]}
                ]
            }

    fresh = {
        "views": [
            {"path": "default-view", "cards": [{"entity": "camera.fresh"}]},
            {"path": "camera", "cards": [{"entity": "camera.second"}]},
        ]
    }
    loaded_paths: list[str] = []

    async def executor(function: Any, path: str) -> Any:
        loaded_paths.append(path)
        return function(path)

    hass = SimpleNamespace(
        data={
            "lovelace": SimpleNamespace(
                dashboards={"lovelace": StorageDashboard()}
            )
        },
        config=SimpleNamespace(
            path=lambda *parts: "/config/" + "/".join(parts)
        ),
        async_add_executor_job=executor,
    )
    original_loader = sources_module._load_storage_dashboard
    sources_module._load_storage_dashboard = lambda _path: fresh
    try:
        snapshot = await sources_module.async_read_dashboard_sources(
            hass,
            (("lovelace", "default-view"), ("lovelace", "camera")),
        )
    finally:
        sources_module._load_storage_dashboard = original_loader
    check(
        snapshot.entities == {"camera.fresh", "camera.second"}
        and stale_calls == 0,
        "Storage dashboard reconciliation bypasses the stale native cache",
    )
    check(
        loaded_paths == ["/config/.storage/lovelace.lovelace"],
        "Named Lovelace storage uses the official dashboard storage key",
    )

    sources_module._load_storage_dashboard = lambda _path: (_ for _ in ()).throw(
        RuntimeError("malformed storage")
    )
    try:
        try:
            await sources_module.async_read_dashboard_source(
                hass, "lovelace", "default-view"
            )
        except RuntimeError as error:
            check(
                "malformed storage" in str(error),
                "Malformed fresh storage fails closed instead of using stale cache",
            )
        else:
            raise AssertionError("Malformed fresh storage must fail closed")
    finally:
        sources_module._load_storage_dashboard = original_loader
    return 4


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


def check_matter_endpoint_compatibility() -> int:
    """Matterbridge accepts legacy hosts and secure reverse-proxy URLs."""
    check(
        targets._matter_ws_url(
            SimpleNamespace(matter_host="192.0.2.81", matter_port=8283)
        )
        == "ws://192.0.2.81:8283/",
        "legacy Matterbridge host and port remain compatible",
    )
    check(
        targets._matter_ws_url(
            SimpleNamespace(
                matter_host="https://matter.example.test/admin/ws?site=home",
                matter_port=8283,
            )
        )
        == "wss://matter.example.test:443/admin/ws?site=home",
        "HTTPS reverse-proxy endpoints retain their path and use WSS",
    )
    check(
        targets._matter_ws_url(
            SimpleNamespace(matter_host="2001:db8::81", matter_port=8283)
        )
        == "ws://[2001:db8::81]:8283/",
        "IPv6 Matterbridge hosts are bracketed correctly",
    )
    check(
        targets._matter_ws_url(
            SimpleNamespace(
                matter_host="wss://matter.example.test/ws",
                matter_port=8283,
                matter_password="test-token",
            )
        )
        == "wss://matter.example.test:443/ws?password=test-token",
        "optional Matterbridge frontend authentication is encoded in the WebSocket query",
    )
    try:
        targets._matter_ws_url(
            SimpleNamespace(
                matter_host="wss://user:secret@matter.example.test/ws",
                matter_port=8283,
            )
        )
    except RuntimeError as error:
        check(
            "secret" not in str(error),
            "Matterbridge URL credential rejection never echoes credentials",
        )
    else:
        raise AssertionError("Credentials embedded in Matterbridge URLs must fail")
    return 5


async def check_matter_save_barrier_and_uncertain_restart() -> int:
    """An uncertain plugin restart requires a generation-gated process restart."""
    expected = frozenset({"light.one"})
    old_plugin = matter_snapshot(
        config_updates={"whiteList": ["light.old"]}
    ).plugin
    new_plugin = matter_snapshot().plugin
    plugin_reads = 0
    calls: list[str] = []

    async def request(_config: Any, command: str, payload: Any = None) -> Any:
        nonlocal plugin_reads
        calls.append(command)
        if command == "plugins":
            plugin_reads += 1
            return [old_plugin if plugin_reads < 3 else new_plugin]
        raise AssertionError(f"Unexpected Matterbridge command: {command}")

    async def no_delay(_delay: float) -> None:
        return None

    original_request = targets._matter_request
    original_sleep = targets.asyncio.sleep
    targets._matter_request = request
    targets.asyncio.sleep = no_delay
    try:
        await targets._wait_matter_config_persisted(
            SimpleNamespace(), expected, timeout=1
        )
    finally:
        targets._matter_request = original_request
        targets.asyncio.sleep = original_sleep
    check(
        calls == ["plugins", "plugins", "plugins"],
        "Matterbridge save barrier polls until the new exact allowlist is readable",
    )

    restart_calls = 0
    runtime_waits = 0

    async def timeout_request(
        _config: Any, command: str, payload: Any = None
    ) -> Any:
        nonlocal restart_calls
        if command == "savepluginconfig":
            return {}
        if command == "restartplugin":
            restart_calls += 1
            raise targets.MatterbridgeCommandTimeoutError(
                "Matterbridge restartplugin timed out"
            )
        raise AssertionError(f"Unexpected Matterbridge command: {command}")

    async def persisted(_config: Any, entities: frozenset[str]) -> None:
        check(entities == expected, "save barrier keeps the exact allowlist")

    async def runtime(
        _config: Any,
        entities: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        nonlocal runtime_waits
        runtime_waits += 1
        check(entities == expected, "uncertain restart polls the exact runtime")
        check(after_generation is None, "Plugin restart readback has no process barrier")
        return {"loaded": True}

    plugin_config = deepcopy(new_plugin["configJson"])
    originals = (
        targets._matter_request,
        targets._wait_matter_config_persisted,
        targets._wait_matter_runtime,
    )
    targets._matter_request = timeout_request
    targets._wait_matter_config_persisted = persisted
    targets._wait_matter_runtime = runtime
    try:
        try:
            await targets._save_matter_config(SimpleNamespace(), plugin_config)
        except targets.MatterbridgePluginRestartUncertainError:
            check(True, "a timed-out plugin restart is classified as uncertain")
        else:
            raise AssertionError("A timed-out plugin restart must not be accepted")
    finally:
        (
            targets._matter_request,
            targets._wait_matter_config_persisted,
            targets._wait_matter_runtime,
        ) = originals
    check(
        restart_calls == 1 and runtime_waits == 0,
        "an uncertain plugin restart never accepts a stale count-only readback",
    )

    desired_addition = frozenset({"light.old", "light.one"})
    old_snapshot = matter_snapshot(
        config_updates={"whiteList": ["light.old"]}
    )
    converged_snapshot = matter_snapshot(
        plugin_updates={"registeredDevices": 2},
        config_updates={"whiteList": sorted(desired_addition)},
        devices=[
            {
                "pluginName": targets.MATTER_PLUGIN,
                "endpoint": 1,
                "uniqueId": "device-old",
                "serial": "serial-old",
            },
            {
                "pluginName": targets.MATTER_PLUGIN,
                "endpoint": 2,
                "uniqueId": "device-new",
                "serial": "serial-new",
            },
        ],
    )
    recovery_calls: list[str] = []

    async def addition_request(
        _config: Any, command: str, payload: Any = None
    ) -> Any:
        check(command == "plugins", "addition reads the current plugin config")
        return [old_snapshot.plugin]

    async def uncertain_save(_config: Any, _plugin_config: Any) -> None:
        recovery_calls.append("uncertain")
        raise targets.MatterbridgePluginRestartUncertainError("uncertain")

    async def converged_read(_config: Any) -> Any:
        recovery_calls.append("snapshot")
        return converged_snapshot

    async def full_restart(
        _config: Any, command: str, payload: Any = None
    ) -> None:
        check(command == "restart", "uncertain restart uses the process endpoint")
        recovery_calls.append("restart")

    async def generation_wait(
        _config: Any,
        entities: frozenset[str],
        timeout: float = 60,
        *,
        after_generation: Any = None,
    ) -> Any:
        check(
            entities == desired_addition
            and after_generation == targets.MatterProcessGeneration(1_000, 4),
            "uncertain restart requires the exact desired set and generation barrier",
        )
        recovery_calls.append("wait")
        return {"loaded": True}

    def authorize_recovery() -> bool:
        recovery_calls.append("authorized")
        return True

    originals = (
        targets._matter_request,
        targets._save_matter_config,
        targets._read_matter_runtime_snapshot,
        targets._matter_fire_and_forget,
        targets._wait_matter_runtime,
    )
    targets._matter_request = addition_request
    targets._save_matter_config = uncertain_save
    targets._read_matter_runtime_snapshot = converged_read
    targets._matter_fire_and_forget = full_restart
    targets._wait_matter_runtime = generation_wait
    try:
        process_restarted = await targets._apply_matter(
            SimpleNamespace(),
            desired_addition,
            before_matter_process_restart=authorize_recovery,
        )
    finally:
        (
            targets._matter_request,
            targets._save_matter_config,
            targets._read_matter_runtime_snapshot,
            targets._matter_fire_and_forget,
            targets._wait_matter_runtime,
        ) = originals
    check(
        process_restarted is True
        and recovery_calls
        == ["uncertain", "snapshot", "authorized", "restart", "wait"],
        "an uncertain addition forces one authorized generation-gated process restart",
    )
    return 8


async def check_matter_backup_completion_handshake() -> int:
    """Backup readiness requires its request ack and matching archive event."""
    orders = [
        ["ack", "archive"],
        ["archive", "ack"],
    ]
    sent: list[dict[str, Any]] = []
    send_started = asyncio.Event()

    class FakeWebSocket:
        def __init__(self, order: list[str]) -> None:
            self.order = order
            self.request_id = 0

        async def send_json(self, request: dict[str, Any]) -> None:
            sent.append(request)
            self.request_id = request["id"]
            send_started.set()

        async def receive(self) -> Any:
            kind = self.order.pop(0)
            if kind == "block":
                await asyncio.Event().wait()
                raise AssertionError("Cancellation must interrupt backup readiness")
            if kind == "ack":
                payload = {
                    "id": self.request_id,
                    "method": "/api/create-backup",
                    "success": True,
                    "response": None,
                }
            else:
                payload = {
                    "id": 0,
                    "method": "archive",
                    "success": True,
                    "response": {
                        "command": "zip",
                        "archivePath": "/tmp/matterbridge.backup.zip",
                    },
                }
            return SimpleNamespace(type="text", data=json.dumps(payload))

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
            check(heartbeat == 20, "Backup completion websocket retains its heartbeat")
            return AsyncContext(FakeWebSocket(orders.pop(0)))

    fake_aiohttp = ModuleType("aiohttp")
    fake_aiohttp.ClientSession = FakeClientSession
    fake_aiohttp.WSMsgType = SimpleNamespace(TEXT="text")
    previous_aiohttp = sys.modules.get("aiohttp")
    sys.modules["aiohttp"] = fake_aiohttp
    try:
        config = SimpleNamespace(matter_host="127.0.0.1", matter_port=8283)
        await targets._matter_create_backup_ready(config)
        await targets._matter_create_backup_ready(config)
        orders.append(["block"])
        send_started.clear()
        cancelled_backup = asyncio.create_task(
            targets._matter_create_backup_ready(config)
        )
        await asyncio.wait_for(send_started.wait(), timeout=0.1)
        cancelled_backup.cancel()
        try:
            await asyncio.wait_for(cancelled_backup, timeout=0.1)
        except asyncio.CancelledError:
            check(True, "HA unload cancellation interrupts backup readiness promptly")
        else:
            raise AssertionError("Backup readiness must never swallow cancellation")
    finally:
        if previous_aiohttp is None:
            sys.modules.pop("aiohttp", None)
        else:
            sys.modules["aiohttp"] = previous_aiohttp
    check(
        len(sent) == 3
        and all(request["method"] == "/api/create-backup" for request in sent),
        "Backup readiness sends one create request per attempted handshake",
    )
    check(
        not orders,
        "Backup readiness accepts ack and archive completion in either order",
    )
    check(
        cancelled_backup.cancelled(),
        "The bounded backup timeout does not delay a cancelled HA unload",
    )
    return 6


async def check_matter_restart_is_fire_and_forget() -> int:
    """A process restart send never waits for a response from the exiting server."""
    sent: list[dict[str, Any]] = []
    fail_on_close = False
    fail_during_send = False

    class FakeWebSocket:
        async def send_json(self, request: dict[str, Any]) -> None:
            sent.append(request)
            if fail_during_send:
                raise ConnectionResetError("simulated close during restart send")

        async def receive(self) -> Any:
            raise AssertionError("A process restart must not wait for a response")

    class AsyncContext:
        def __init__(self, value: Any) -> None:
            self.value = value

        async def __aenter__(self) -> Any:
            return self.value

        async def __aexit__(self, *_args: Any) -> None:
            if fail_on_close:
                raise ConnectionResetError("simulated restart socket close")
            return None

    class FakeClientSession:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        def ws_connect(self, _url: str, *, heartbeat: int) -> AsyncContext:
            check(heartbeat == 20, "Process restart retains websocket heartbeat")
            return AsyncContext(FakeWebSocket())

    fake_aiohttp = ModuleType("aiohttp")
    fake_aiohttp.ClientSession = FakeClientSession
    previous_aiohttp = sys.modules.get("aiohttp")
    sys.modules["aiohttp"] = fake_aiohttp
    try:
        await targets._matter_fire_and_forget(
            SimpleNamespace(matter_host="127.0.0.1", matter_port=8283),
            "restart",
            {},
        )
        fail_on_close = False
        fail_during_send = True
        await targets._matter_fire_and_forget(
            SimpleNamespace(matter_host="127.0.0.1", matter_port=8283),
            "restart",
            {},
        )
        fail_on_close = True
        await targets._matter_fire_and_forget(
            SimpleNamespace(matter_host="127.0.0.1", matter_port=8283),
            "restart",
            {},
        )
    finally:
        if previous_aiohttp is None:
            sys.modules.pop("aiohttp", None)
        else:
            sys.modules["aiohttp"] = previous_aiohttp
    check(
        len(sent) == 3,
        "Each process restart attempt sends once, including when its socket closes",
    )
    check(
        all(
            request["method"] == "/api/restart" and request["params"] == {}
            for request in sent
        ),
        "Process restart uses only the fire-and-forget restart endpoint",
    )
    return 5


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


async def check_google_native_acceptance() -> int:
    """Require exact native SYNC payloads and honest Request Sync acceptance."""

    class NativeGoogle:
        def __init__(self, status: int = 200) -> None:
            self.status = status
            self.users = ("opaque-user-a",)
            self.payloads: dict[str, list[dict[str, Any]]] = {}

        async def async_get_agent_users(self) -> tuple[str, ...]:
            return self.users

        async def async_sync_entities_all(self) -> int:
            return self.status

    native = NativeGoogle()
    runtime = native
    runtime._config = {"expose_by_default": False}
    runtime.entity_config = {
        "lock.front": {"expose": True},
        "alarm_control_panel.home": {"expose": True},
        "camera.front": {"expose": True},
        "binary_sensor.motion": {"expose": True},
    }
    entry = SimpleNamespace(state="loaded", runtime_data=runtime)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda domain: [entry] if domain == "google_assistant" else []
        )
    )
    google_package = ModuleType("homeassistant.components.google_assistant")
    google_package.__path__ = []
    google_const = ModuleType("homeassistant.components.google_assistant.const")
    google_const.DOMAIN_TO_GOOGLE_TYPES = {
        "lock": "action.devices.types.LOCK",
        "alarm_control_panel": "action.devices.types.SECURITYSYSTEM",
        "camera": "action.devices.types.CAMERA",
    }
    sys.modules["homeassistant.components.google_assistant"] = google_package
    sys.modules["homeassistant.components.google_assistant.const"] = google_const
    google_smart_home = ModuleType(
        "homeassistant.components.google_assistant.smart_home"
    )
    serialized_users: list[str] = []

    async def async_devices_sync_response(
        _hass: Any, _config: Any, agent_user_id: str
    ) -> list[dict[str, str]]:
        serialized_users.append(agent_user_id)
        return deepcopy(native.payloads[agent_user_id])

    google_smart_home.async_devices_sync_response = async_devices_sync_response
    sys.modules[
        "homeassistant.components.google_assistant.smart_home"
    ] = google_smart_home
    unsupported_entities = {"binary_sensor.motion", "sensor.illuminance"}

    class GoogleEntity:
        def __init__(self, _hass: Any, _config: Any, state: Any) -> None:
            self.state = state

        def is_supported(self) -> bool:
            return self.state.entity_id not in unsupported_entities

    google_helpers = ModuleType("homeassistant.components.google_assistant.helpers")
    google_helpers.GoogleEntity = GoogleEntity
    sys.modules["homeassistant.components.google_assistant.helpers"] = google_helpers

    def state(entity_id: str, device_class: str | None = None) -> Any:
        return SimpleNamespace(
            entity_id=entity_id,
            domain=entity_id.split(".", 1)[0],
            state="unavailable" if entity_id == "binary_sensor.motion" else "on",
            attributes={"device_class": device_class} if device_class else {},
        )

    states = {
        "lock.front": state("lock.front"),
        "alarm_control_panel.home": state("alarm_control_panel.home"),
        "camera.front": state("camera.front"),
        "binary_sensor.motion": state("binary_sensor.motion", "motion"),
        "camera.keep": state("camera.keep"),
        "lock.keep": state("lock.keep"),
        "alarm_control_panel.keep": state("alarm_control_panel.keep"),
        "binary_sensor.door": state("binary_sensor.door", "door"),
        "sensor.temperature": state("sensor.temperature", "temperature"),
        "sensor.illuminance": state("sensor.illuminance", "illuminance"),
        "light.unsupported": state("light.unsupported"),
    }
    hass.states = SimpleNamespace(get=states.get)

    snapshot = await targets._google_native_snapshot(
        hass,
        frozenset(
            {
                "lock.front",
                "alarm_control_panel.home",
                "camera.front",
                "binary_sensor.motion",
            }
        ),
    )
    check(
        snapshot["linked_users"] == 1
        and snapshot["native_security_devices"] == 3
        and snapshot["configured_but_not_native_domain"] == 1
        and snapshot["native_security_types"]["lock.front"].endswith(".LOCK"),
        "Google native snapshot distinguishes native security types from "
        "unsupported entities",
    )

    expected = frozenset(
        {
            "camera.keep",
            "lock.keep",
            "alarm_control_panel.keep",
            "binary_sensor.door",
            "sensor.temperature",
            "binary_sensor.motion",
            "sensor.illuminance",
        }
    )
    runtime.entity_config = {
        entity_id: {"expose": True} for entity_id in expected
    }
    native.users = ("opaque-user-a", "opaque-user-b")
    security_types = {
        "camera.keep": "action.devices.types.CAMERA",
        "lock.keep": "action.devices.types.LOCK",
        "alarm_control_panel.keep": "action.devices.types.SECURITYSYSTEM",
    }
    security_traits = {
        "camera.keep": "action.devices.traits.CameraStream",
        "lock.keep": "action.devices.traits.LockUnlock",
        "alarm_control_panel.keep": "action.devices.traits.ArmDisarm",
    }

    def serialized_device(entity_id: str) -> dict[str, Any]:
        device: dict[str, Any] = {
            "id": entity_id,
            "type": "action.devices.types.SENSOR",
            "traits": ["action.devices.traits.SensorState"],
        }
        if entity_id in security_types:
            device["type"] = security_types[entity_id]
            device["traits"] = [security_traits[entity_id]]
        return device

    supported_payload = [
        serialized_device(entity_id)
        for entity_id in sorted(expected - unsupported_entities)
    ]
    native.payloads = {
        "opaque-user-a": deepcopy(supported_payload),
        "opaque-user-b": deepcopy(supported_payload),
    }
    full_snapshot = await targets._google_native_sync_payload_snapshot(
        hass, expected
    )
    check(
        full_snapshot["native_supported_payload_exact"] is True
        and full_snapshot["native_sync_payload_match"] is True
        and full_snapshot["configured_sync_devices"] == 7
        and full_snapshot["native_sync_devices"] == 5
        and full_snapshot["native_unsupported_devices"] == 2
        and full_snapshot["linked_users"] == 2
        and serialized_users == ["opaque-user-a", "opaque-user-b"]
        and all(
            device["id"] != "camera.removed"
            for payload in native.payloads.values()
            for device in payload
        ),
        "Every linked user receives the exact native set after an entity is removed",
    )
    serialized_users.clear()
    await targets._google_native_snapshot(hass, expected)
    check(
        not serialized_users,
        "Periodic native health checks do not generate complete SYNC payloads",
    )

    native.payloads["opaque-user-b"] = deepcopy(supported_payload[1:])
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "missing=1" in str(error)
            and serialized_users == ["opaque-user-a", "opaque-user-b"],
            "Every linked user's native SYNC payload is checked independently",
        )
    else:
        raise AssertionError("A later linked-user payload mismatch must fail closed")

    native.users = ("opaque-user-a",)
    for missing_entity in (
        "camera.keep",
        "lock.keep",
        "alarm_control_panel.keep",
        "binary_sensor.door",
        "sensor.temperature",
    ):
        native.payloads["opaque-user-a"] = [
            deepcopy(device)
            for device in supported_payload
            if device["id"] != missing_entity
        ]
        try:
            await targets._google_native_sync_payload_snapshot(hass, expected)
        except RuntimeError as error:
            check(
                "missing=1" in str(error) and "extra=0" in str(error),
                f"A missing supported Google entity fails closed: {missing_entity}",
            )
        else:
            raise AssertionError(
                f"A missing supported Google entity must fail closed: {missing_entity}"
            )

    native.payloads["opaque-user-a"] = deepcopy(supported_payload)
    unsupported_entities.remove("binary_sensor.motion")
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "missing=1" in str(error) and "extra=0" in str(error),
            "A formerly unsupported entity becomes required when HA adds support",
        )
    else:
        raise AssertionError("New native support must restore the exact-set requirement")
    finally:
        unsupported_entities.add("binary_sensor.motion")

    missing_state = states.pop("sensor.illuminance")
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "configured-device state missing" in str(error),
            "A missing HA State is not mistaken for a platform limitation",
        )
    else:
        raise AssertionError("A configured entity without a State must fail closed")
    finally:
        states["sensor.illuminance"] = missing_state

    unsupported_entities.add("light.unsupported")
    native.payloads["opaque-user-a"] = []
    try:
        await targets._google_native_sync_payload_snapshot(
            hass, frozenset({"light.unsupported"})
        )
    except RuntimeError as error:
        check(
            "controllable-device support is missing" in str(error),
            "An unsupported controllable domain never becomes an allowed omission",
        )
    else:
        raise AssertionError("Unsupported controllable entities must fail closed")
    finally:
        unsupported_entities.remove("light.unsupported")

    unsupported_entities.add("camera.front")
    try:
        unrepresentable = targets.google_native_unrepresentable_entities(
            hass,
            frozenset(
                {
                    "camera.front",
                    "binary_sensor.motion",
                    "sensor.illuminance",
                }
            ),
        )
        check(
            unrepresentable == frozenset({"camera.front"}),
            "Google compatibility planning skips only unsupported "
            "non-observation entities",
        )
    finally:
        unsupported_entities.remove("camera.front")

    check(
        targets.matter_native_unrepresentable_entities(
            frozenset(
                {
                    "camera.front",
                    "alarm_control_panel.home",
                    "lock.front",
                    "sensor.temperature",
                }
            )
        )
        == frozenset({"camera.front", "alarm_control_panel.home"}),
        "Matter compatibility planning reports device types Matter lacks "
        "without hiding supported endpoints",
    )

    malformed_security_payload = deepcopy(supported_payload)
    next(
        device
        for device in malformed_security_payload
        if device["id"] == "camera.keep"
    )["type"] = "action.devices.types.SENSOR"
    native.payloads["opaque-user-a"] = malformed_security_payload
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "security-device payload is malformed" in str(error),
            "A security device must retain its native Google type",
        )
    else:
        raise AssertionError("A malformed security-device type must fail closed")

    for malformed_entity in security_traits:
        malformed_security_payload = deepcopy(supported_payload)
        next(
            device
            for device in malformed_security_payload
            if device["id"] == malformed_entity
        )["traits"] = ["action.devices.traits.OnOff"]
        native.payloads["opaque-user-a"] = malformed_security_payload
        try:
            await targets._google_native_sync_payload_snapshot(hass, expected)
        except RuntimeError as error:
            check(
                "security-device payload is malformed" in str(error),
                f"A security device must retain its required trait: {malformed_entity}",
            )
        else:
            raise AssertionError(
                f"A malformed security-device trait must fail closed: {malformed_entity}"
            )

    native.payloads["opaque-user-a"] = deepcopy(supported_payload) + [
        serialized_device("camera.removed")
    ]
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "missing=0" in str(error) and "extra=1" in str(error),
            "A removed entity lingering in native SYNC fails closed",
        )
    else:
        raise AssertionError("An extra native SYNC entity must fail closed")

    native.payloads["opaque-user-a"] = deepcopy(supported_payload) + [
        deepcopy(supported_payload[0])
    ]
    try:
        await targets._google_native_sync_payload_snapshot(hass, expected)
    except RuntimeError as error:
        check(
            "duplicate" in str(error),
            "Duplicate native device ids fail closed",
        )
    else:
        raise AssertionError("Duplicate native device ids must fail closed")

    sync_result = await targets._request_google_sync(hass)
    check(
        sync_result["request_sync_accepted"] is True
        and sync_result["request_sync_http_status"] == 200
        and sync_result["homegraph_readback_verified"] is False,
        "Request Sync 2xx is recorded only as accepted, not HomeGraph readback",
    )
    native.status = 404
    try:
        await targets._request_google_sync(hass)
    except RuntimeError as error:
        check("relink" in str(error), "Google HomeGraph 404 requires relinking")
    else:
        raise AssertionError("Google HomeGraph 404 must fail closed")
    native.status = 204
    try:
        await targets._request_google_sync(hass)
    except RuntimeError as error:
        check("no linked" in str(error), "Google request sync requires a linked user")
    else:
        raise AssertionError(
            "Google request sync without a linked user must fail closed"
        )
    return 21


async def check_google_mutation_payload_guards() -> int:
    """Apply and rollback validate native SYNC immediately before and after."""
    runtime_config: dict[str, dict[str, Any]] = {
        "camera.keep": {"expose": True},
        "camera.remove": {"expose": True},
    }
    runtime = SimpleNamespace(
        _config={"expose_by_default": False},
        entity_config=runtime_config,
    )
    entry = SimpleNamespace(state="loaded", runtime_data=runtime)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda domain: [entry]
            if domain == "google_assistant"
            else []
        ),
    )

    async def async_add_executor_job(function: Any, *args: Any) -> Any:
        return function(*args)

    hass.async_add_executor_job = async_add_executor_job
    config = SimpleNamespace(google_config_path="unused-google-entities.yaml")
    absent_path = PACKAGE / "__platform_sync_absent_google_test__.yaml"
    steps: list[tuple[str, frozenset[str]]] = []

    async def load_google_yaml(
        _hass: Any, _config: Any
    ) -> tuple[Path, dict[str, dict[str, Any]]]:
        return absent_path, deepcopy(runtime_config)

    async def native_snapshot(
        _hass: Any, expected: frozenset[str]
    ) -> dict[str, Any]:
        actual = frozenset(runtime_config)
        check(
            actual == expected,
            "The native guard observes the exact just-written runtime set",
        )
        steps.append(("native", expected))
        return {"native_sync_payload_match": True}

    async def request_sync(_hass: Any) -> dict[str, Any]:
        steps.append(("request", frozenset(runtime_config)))
        return {
            "request_sync_accepted": True,
            "homegraph_readback_verified": False,
        }

    async def validate_target(
        _hass: Any, _config: Any, _platform: Any, expected: frozenset[str]
    ) -> dict[str, Any]:
        steps.append(("validate", expected))
        return {"loaded": True}

    originals = (
        targets._load_google_yaml,
        targets._google_native_sync_payload_snapshot,
        targets._request_google_sync,
        targets.async_validate_target,
    )
    targets._load_google_yaml = load_google_yaml
    targets._google_native_sync_payload_snapshot = native_snapshot
    targets._request_google_sync = request_sync
    targets.async_validate_target = validate_target
    try:
        desired = frozenset({"camera.keep"})
        await targets._apply_google(hass, config, desired, {})
        check(
            steps
            == [
                ("native", desired),
                ("request", desired),
                ("native", desired),
            ],
            "Google apply brackets Request Sync with exact native payload checks",
        )

        steps.clear()
        previous = frozenset({"camera.before"})
        backup = targets.TargetBackup(
            const.TargetPlatform.GOOGLE,
            {
                "path": absent_path,
                "existed": False,
                "raw": b"",
                "runtime": {"camera.before": {"expose": True}},
                "entities": previous,
            },
        )
        await targets.async_restore_target(hass, config, backup)
        check(
            steps
            == [
                ("native", previous),
                ("request", previous),
                ("native", previous),
                ("validate", previous),
            ],
            "Google rollback brackets Request Sync with exact native payload checks",
        )
    finally:
        (
            targets._load_google_yaml,
            targets._google_native_sync_payload_snapshot,
            targets._request_google_sync,
            targets.async_validate_target,
        ) = originals
    return 4


async def check_google_executor_mutation_cancellation() -> int:
    """Google apply/restore drain non-cancellable executor writes before escape."""

    class MutationPath:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def __str__(self) -> str:
            return "delayed-google-entities.yaml"

        def write_bytes(self, value: bytes) -> int:
            self.writes.append(value)
            return len(value)

    path = MutationPath()
    mutation_started = asyncio.Event()
    mutation_release = asyncio.Event()
    mutation_finished = asyncio.Event()

    async def delayed_executor(function: Any, *args: Any) -> Any:
        mutation_started.set()
        await mutation_release.wait()
        result = function(*args)
        mutation_finished.set()
        return result

    hass = SimpleNamespace(async_add_executor_job=delayed_executor)
    config = SimpleNamespace(google_config_path="unused-google-entities.yaml")
    original_loader = targets._load_google_yaml

    async def load_google_yaml(
        _hass: Any, _config: Any
    ) -> tuple[Any, dict[str, dict[str, Any]]]:
        return path, {"camera.before": {"expose": True}}

    targets._load_google_yaml = load_google_yaml
    try:
        apply_task = asyncio.create_task(
            targets._apply_google(
                hass,
                config,
                frozenset({"camera.after"}),
                {},
            )
        )
        await mutation_started.wait()
        apply_task.cancel()
        await asyncio.sleep(0)
        apply_task.cancel()
        await asyncio.sleep(0)
        check(
            not apply_task.done() and not mutation_finished.is_set(),
            "Google apply cancellation waits for its executor writer to settle",
        )
        mutation_release.set()
        try:
            await apply_task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Google apply cancellation must propagate after drain")
        check(
            mutation_finished.is_set(),
            "Google apply mutation finishes before cancellation reaches rollback",
        )

        mutation_started = asyncio.Event()
        mutation_release = asyncio.Event()
        mutation_finished = asyncio.Event()
        backup = targets.TargetBackup(
            const.TargetPlatform.GOOGLE,
            {
                "path": path,
                "existed": True,
                "raw": b"before",
                "runtime": {"camera.before": {"expose": True}},
                "entities": frozenset({"camera.before"}),
            },
        )
        restore_task = asyncio.create_task(
            targets.async_restore_target(hass, config, backup)
        )
        await mutation_started.wait()
        restore_task.cancel()
        await asyncio.sleep(0)
        restore_task.cancel()
        await asyncio.sleep(0)
        check(
            not restore_task.done() and not mutation_finished.is_set(),
            "Google restore cancellation waits for its executor writer to settle",
        )
        mutation_release.set()
        try:
            await restore_task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Google restore cancellation must propagate after drain")
        check(
            mutation_finished.is_set() and path.writes == [b"before"],
            "Google restore mutation finishes before cancellation is reported incomplete",
        )
    finally:
        targets._load_google_yaml = original_loader
    return 4


async def check_single_switch_runtime() -> int:
    """Version 0.7.1 has one enable switch and no sensor/button platforms."""
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    check(manifest["version"] == "0.7.1", "Manifest version matches the 0.7.1 release")
    check(
        "google_assistant" in manifest["after_dependencies"],
        "Native Google imports are declared as an after-dependency",
    )
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
        and runtime_defaults.homekit_main_entry_id == ""
        and not hasattr(runtime_defaults, "auto_apply")
        and not hasattr(runtime_defaults, "profile_name"),
        "Runtime has one disabled-by-default switch, legacy main-ID inference, and no custom name",
    )
    explicit_main = runtime_config_module.SyncConfig.from_entry(
        {const.CONF_HOMEKIT_MAIN_ENTRY_ID: "old-main"},
        {const.CONF_HOMEKIT_MAIN_ENTRY_ID: "new-main"},
    )
    check(
        explicit_main.homekit_main_entry_id == "new-main",
        "Runtime options override data for the durable HomeKit main entry ID",
    )
    for invalid_main_id in (7, " main-with-spaces "):
        try:
            runtime_config_module.SyncConfig.from_entry(
                {const.CONF_HOMEKIT_MAIN_ENTRY_ID: invalid_main_id}, {}
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Malformed HomeKit main entry IDs must fail closed: "
                f"{invalid_main_id!r}"
            )
    check(
        True,
        "Runtime rejects non-string and whitespace-mutated main entry IDs",
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
    return 17


async def check_safe_migration() -> int:
    """Migrate v1-v4.3 safely into schema 4.4 with durable HomeKit identity."""
    homekit_entries = [
        FakeEntry(
            "homekit-main",
            options={
                "filter": {
                    "include_entities": ["light.main_one", "light.main_two"]
                },
                "homekit_mode": "bridge",
            },
        ),
        FakeEntry(
            "homekit-accessory",
            options={
                "filter": {"include_entities": ["lock.front"]},
                "homekit_mode": "accessory",
            },
        ),
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
        and profile.minor_version == 4
        and profile.title == TITLE_ZH_HANT
        and LEGACY_PROFILE_NAME not in profile.data
        and LEGACY_PROFILE_NAME not in profile.options,
        "Version 1 migrates to 4.4, discards custom names, and fixes zh-Hant title",
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
        and profile.options[const.CONF_HOMEKIT_MAIN_ENTRY_ID] == "homekit-main"
        and runtime_config_module.SyncConfig.from_entry(
            profile.data, profile.options
        ).homekit_main_entry_id
        == "homekit-main",
        "Version 1 snapshots its managed entries and durably identifies the main Bridge",
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
            and legacy_v2.minor_version == 4
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
        and legacy_v3.minor_version == 4
        and legacy_v3.title == TITLE_ZH_HANT
        and LEGACY_PROFILE_NAME not in legacy_v3.data
        and LEGACY_PROFILE_NAME not in legacy_v3.options,
        "Version 3 reaches 4.4 with the fixed localized title and no name field",
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
        legacy_v4.version == 4 and legacy_v4.minor_version == 4,
        "Version 4.0 reaches schema 4.4",
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
        and homekit_v41.minor_version == 4
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
        "A completed 4.4 migration never auto-adopts a later HomeKit entry",
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
        and empty_homekit_v41.minor_version == 4
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
        and non_homekit_v41.minor_version == 4
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
        and legacy_v42.minor_version == 4
        and legacy_v42.data[const.CONF_LOCKED_RULES] == v42_locked
        and legacy_v42.data[const.CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION] is True,
        "Version 4.2 preserves its immutable rules and materializes the legacy Apple TV exclusion flag",
    )
    migrated_v42_snapshot = (deepcopy(legacy_v42.data), deepcopy(legacy_v42.options))
    check(
        await integration_module.async_migrate_entry(hass_en, legacy_v42)
        and migrated_v42_snapshot
        == (legacy_v42.data, legacy_v42.options),
        "A completed 4.4 migration is idempotent",
    )

    class CountingMigrationEntries(MigrationEntries):
        def __init__(self, entries: list[FakeEntry]) -> None:
            self.entries = entries
            self.update_calls = 0

        def async_entries(self, domain: str) -> list[Any]:
            return list(self.entries) if domain == "homekit" else []

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
            self.update_calls += 1
            super().async_update_entry(
                entry,
                data=data,
                options=options,
                title=title,
                version=version,
                minor_version=minor_version,
            )

    inferred_entries = [
        FakeEntry(
            "v43-main",
            options={
                "filter": {"include_entities": ["light.one", "light.two"]},
                "homekit_mode": "bridge",
            },
        ),
        FakeEntry(
            "v43-side",
            options={
                "filter": {"include_entities": ["switch.side"]},
                "homekit_mode": "bridge",
            },
        ),
    ]
    inferred_config_entries = CountingMigrationEntries(inferred_entries)
    inferred_hass = SimpleNamespace(
        config_entries=inferred_config_entries,
        config=SimpleNamespace(language="en"),
    )
    legacy_v43 = SimpleNamespace(
        version=4,
        minor_version=3,
        title=TITLE_EN,
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.one"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value],
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: ["v43-main", "v43-side"],
        },
        options={const.CONF_ENABLED: True},
    )
    check(
        await integration_module.async_migrate_entry(inferred_hass, legacy_v43),
        "A 4.3 HomeKit target with one provable main Bridge migrates",
    )
    check(
        legacy_v43.version == 4
        and legacy_v43.minor_version == 4
        and legacy_v43.options[const.CONF_HOMEKIT_MAIN_ENTRY_ID] == "v43-main"
        and inferred_config_entries.update_calls == 1,
        "The 4.4 migration durably stores the inferred main ID before setup",
    )
    inferred_snapshot = (
        deepcopy(legacy_v43.data),
        deepcopy(legacy_v43.options),
        legacy_v43.title,
    )
    check(
        await integration_module.async_migrate_entry(inferred_hass, legacy_v43)
        and inferred_snapshot
        == (legacy_v43.data, legacy_v43.options, legacy_v43.title)
        and inferred_config_entries.update_calls == 1,
        "A completed 4.4 main-ID migration is idempotent",
    )

    ambiguous_entries = [
        FakeEntry(
            "ambiguous-one",
            options={
                "filter": {"include_entities": ["light.one"]},
                "homekit_mode": "bridge",
            },
        ),
        FakeEntry(
            "ambiguous-two",
            options={
                "filter": {"include_entities": ["light.two"]},
                "homekit_mode": "bridge",
            },
        ),
    ]
    ambiguous_config_entries = CountingMigrationEntries(ambiguous_entries)
    ambiguous_hass = SimpleNamespace(
        config_entries=ambiguous_config_entries,
        config=SimpleNamespace(language="en"),
    )
    ambiguous_v43 = SimpleNamespace(
        version=4,
        minor_version=3,
        title="keep-title",
        data={
            const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
            const.CONF_SOURCE_ENTITIES: ["light.one"],
            const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value],
            const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: [
                "ambiguous-one",
                "ambiguous-two",
            ],
        },
        options={const.CONF_ENABLED: True},
    )
    ambiguous_snapshot = (
        deepcopy(ambiguous_v43.data),
        deepcopy(ambiguous_v43.options),
        ambiguous_v43.title,
        ambiguous_v43.version,
        ambiguous_v43.minor_version,
    )
    check(
        not await integration_module.async_migrate_entry(
            ambiguous_hass, ambiguous_v43
        ),
        "A 4.3 HomeKit target with no unique main Bridge fails migration closed",
    )
    check(
        ambiguous_snapshot
        == (
            ambiguous_v43.data,
            ambiguous_v43.options,
            ambiguous_v43.title,
            ambiguous_v43.version,
            ambiguous_v43.minor_version,
        )
        and ambiguous_config_entries.update_calls == 0,
        "Failed main-ID migration leaves the Config Entry byte-for-byte equivalent",
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
        fresh_public.locked_homekit_apple_tv_exclusion is True,
        "A new installation fail-safely excludes Apple TV provenance from HomeKit",
    )
    return 44


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
        const.INTERNAL_POLL_SECONDS == 60
        and const.INTERNAL_SOURCE_AUDIT_SECONDS == 15
        and const.INTERNAL_HEALTH_AUDIT_SECONDS == 300
        and const.INTERNAL_RETRY_SECONDS == 15
        and const.INTERNAL_RETRY_MAX_SECONDS == 300
        and const.INTERNAL_RETRY_DELAYS_SECONDS == (15, 30, 60, 120, 300),
        "Local dashboard audits run every 15 seconds while remote fallback polling stays at 60 seconds",
    )
    minimum_rollback_budget = (
        3 * targets.GOOGLE_SYNC_TIMEOUT
        + targets.HOMEKIT_RELOAD_TIMEOUT
        + targets.MATTER_CONFIG_PERSIST_TIMEOUT
        + targets.MATTER_RUNTIME_TIMEOUT
        + 7 * targets.MATTER_REQUEST_TIMEOUT
        + manager_module.ROLLBACK_SAFETY_MARGIN_SECONDS
    )
    check(
        manager_module.ROLLBACK_TIMEOUT_SECONDS >= minimum_rollback_budget,
        "Rollback covers both Google payload checks, Request Sync, every target, and one Matter process-generation restart",
    )
    check(
        manager_module.STOP_DRAIN_TIMEOUT_SECONDS
        >= max(
            manager_module.ROLLBACK_TIMEOUT_SECONDS,
            targets.MATTER_BACKUP_TIMEOUT,
        )
        + manager_module.STOP_DRAIN_SAFETY_MARGIN_SECONDS,
        "HA unload covers backup completion or rollback with an explicit safety margin",
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
    return 5


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
                    == ["call_service", "lovelace_updated", "entity_registry_updated"]
                    and intervals == [15, 300]
                    and dispatcher_signals == [],
                    "Dashboard source uses push events, a source-only audit, and a five-minute target health audit",
                )
            elif source_kind is const.SourceKind.HOMEKIT:
                check(
                    hass.bus.events == ["call_service"]
                    and intervals == [60, 300]
                    and dispatcher_signals == ["config_entry_changed"],
                    "HomeKit source uses config-entry events plus a target health audit",
                )
            elif source_kind is const.SourceKind.MANUAL:
                check(
                    hass.bus.events == ["call_service"]
                    and intervals == [300]
                    and dispatcher_signals == [],
                    "Manual source still audits target health every five minutes",
                )
            else:
                check(
                    hass.bus.events == ["call_service"]
                    and intervals == [60]
                    and dispatcher_signals == [],
                    f"{source_kind.value} source uses one bounded fallback poll",
                )
            await manager.async_stop()

        intervals.clear()
        dispatcher_signals.clear()
        target_hass = WatcherHass()
        target_manager = manager_module.PlatformSyncManager(
            target_hass,
            SimpleNamespace(
                enabled=True,
                source_kind=const.SourceKind.DASHBOARD,
                targets=frozenset({const.TargetPlatform.HOMEKIT}),
                homekit_source_entry_ids=(),
                homekit_managed_entry_ids=("managed-entry",),
            ),
        )
        await target_manager.async_start()
        check(
            target_hass.bus.events
            == [
                "call_service",
                "lovelace_updated",
                "entity_registry_updated",
                "device_registry_updated",
            ]
            and dispatcher_signals == ["config_entry_changed"]
            and intervals == [15, 300],
            "Dashboard sources also watch explicitly managed HomeKit targets",
        )
        await target_manager.async_stop()

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
            intervals == [60] and dispatcher_signals == [],
            "HomeKit falls back to one 60-second poll when its signal is unavailable",
        )
        await manager.async_stop()

        intervals.clear()
        target_fallback_hass = WatcherHass()
        target_fallback_manager = manager_module.PlatformSyncManager(
            target_fallback_hass,
            SimpleNamespace(
                enabled=True,
                source_kind=const.SourceKind.DASHBOARD,
                targets=frozenset({const.TargetPlatform.HOMEKIT}),
                homekit_source_entry_ids=(),
                homekit_managed_entry_ids=("managed-entry",),
            ),
        )
        await target_fallback_manager.async_start()
        check(
            sorted(intervals) == [15, 60],
            "A Dashboard retains its local audit when a HomeKit target also needs fallback polling",
        )
        await target_fallback_manager.async_stop()

        intervals.clear()
        deduplicated_hass = WatcherHass()
        deduplicated_manager = manager_module.PlatformSyncManager(
            deduplicated_hass,
            SimpleNamespace(
                enabled=True,
                source_kind=const.SourceKind.MATTER,
                targets=frozenset({const.TargetPlatform.HOMEKIT}),
                homekit_source_entry_ids=(),
                homekit_managed_entry_ids=("managed-entry",),
            ),
        )
        await deduplicated_manager.async_start()
        check(
            intervals == [60],
            "Fallback polling subsumes target health auditing without a duplicate timer",
        )
        await deduplicated_manager.async_stop()
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
            intervals == [60],
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
    return 11


def check_quick_reload_trigger() -> int:
    """Only the global quick YAML reload schedules mandatory reconciliation."""
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    reasons: list[str] = []
    manager.schedule = reasons.append
    manager._handle_service_call(
        SimpleNamespace(
            data={"domain": "homeassistant", "service": "reload_all"}
        )
    )
    check(
        reasons == ["homeassistant_reload_all"],
        "Global Quick reload schedules one full reconciliation",
    )
    for data in (
        {"domain": "homeassistant", "service": "restart"},
        {"domain": "platform_sync", "service": "sync_now"},
        {},
        None,
    ):
        manager._handle_service_call(SimpleNamespace(data=data))
    check(
        reasons == ["homeassistant_reload_all"],
        "Unrelated service calls never schedule Quick-reload reconciliation",
    )
    return 2


async def check_homekit_event_trigger_and_queue() -> int:
    """HomeKit changes trigger precisely and never cancel an active reconcile."""
    config_changes = sys.modules["homeassistant.config_entries"].ConfigEntryChange
    reasons: list[str] = []
    direct_manager = manager_module.PlatformSyncManager(
        SimpleNamespace(),
        SimpleNamespace(
            enabled=True,
            homekit_source_entry_ids=("selected-source",),
            homekit_managed_entry_ids=("selected-target",),
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
        SimpleNamespace(domain="homekit", entry_id="selected-target"),
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
            "homekit_config_entry_updated",
        ],
        "Selected HomeKit source and managed target changes schedule reconciliation",
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
    return 6


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
    check(len(manager._unsubscribers) == 6, "Startup listener is initially tracked")

    hass.bus.once_callback(SimpleNamespace(event_type="homeassistant_started"))
    check(
        len(manager._unsubscribers) == 5 and hass.bus.once_unsubscribe_calls == 0,
        "Fired startup listener removes only its manager-side stale handle",
    )
    check(
        startup_reasons == ["startup_scan"],
        "Home Assistant started event schedules exactly one full startup scan",
    )
    await manager.async_stop()
    check(
        hass.bus.normal_unsubscribe_calls == 3 and hass.bus.once_unsubscribe_calls == 0,
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

        def __init__(self) -> None:
            self.bus = LifecycleBus()

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


async def check_retry_backoff_resets_after_success() -> int:
    """One successful reconciliation resets the next failure to 15 seconds."""
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    calls = 0
    sleeps: list[int] = []

    async def reconcile(
        reason: str, apply: bool, *, _background: bool = False
    ) -> dict[str, Any]:
        nonlocal calls
        del reason, apply, _background
        calls += 1
        if calls == 2:
            manager._pending_reason = "fresh_source_change"
        return {
            "status": "error" if calls in {1, 3} else "synced",
            "changed": False,
        }

    async def sleep(delay: int) -> None:
        sleeps.append(delay)

    manager.async_reconcile = reconcile
    original_sleep = manager_module.asyncio.sleep
    manager_module.asyncio.sleep = sleep
    try:
        await manager._delayed_reconcile("startup_scan")
    finally:
        manager_module.asyncio.sleep = original_sleep
    check(
        sleeps == [2, 15, 2, 15],
        "A successful run resets both debounce and fault backoff",
    )
    check(calls == 4, "Reset backoff still converges and exits normally")
    return 2


async def check_dashboard_source_audit() -> int:
    """A missed Lovelace event is detected without polling every target."""
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(),
        SimpleNamespace(
            enabled=True,
            source_kind=const.SourceKind.DASHBOARD,
            source_pages=(("lovelace", "default-view"),),
        ),
    )
    reasons: list[str] = []
    manager.schedule = reasons.append
    stable = models.SourceSnapshot(
        frozenset({"light.one"}), source_revision="stable"
    )
    changed = models.SourceSnapshot(
        frozenset({"light.one", "camera.new"}), source_revision="changed"
    )
    manager.state.source_fingerprint = stable.fingerprint
    snapshots = [stable, changed]

    async def read_source(_hass: Any, _config: Any) -> Any:
        return snapshots.pop(0)

    original_read = manager_module.async_read_source
    manager_module.async_read_source = read_source
    try:
        await manager._handle_source_audit(None)
        check(reasons == [], "Unchanged dashboard audit performs no target work")
        await manager._handle_source_audit(None)
        check(
            reasons == ["source_revision_audit"],
            "Changed dashboard fingerprint schedules one reconciliation",
        )

        async def failed_read(_hass: Any, _config: Any) -> Any:
            raise RuntimeError("dashboard unavailable")

        manager_module.async_read_source = failed_read
        await manager._handle_source_audit(None)
        check(
            reasons[-1] == "source_revision_audit_error",
            "Dashboard audit failures enter the bounded reconcile retry path",
        )
    finally:
        manager_module.async_read_source = original_read
    reasons.clear()
    manager._handle_event(
        SimpleNamespace(
            event_type="lovelace_updated", data={"url_path": "family-summary"}
        )
    )
    check(reasons == [], "Unselected dashboard events do not read target platforms")
    manager._handle_event(
        SimpleNamespace(event_type="lovelace_updated", data={"url_path": "lovelace"})
    )
    check(reasons == ["lovelace_updated"], "Selected dashboard events reconcile")
    manager._handle_event(
        SimpleNamespace(event_type="lovelace_updated", data={"url_path": None})
    )
    check(
        reasons == ["lovelace_updated", "lovelace_updated"],
        "Legacy default dashboard events map to lovelace",
    )
    manager._registry_watch_entity_ids = frozenset({"camera.source"})
    manager._registry_watch_device_ids = frozenset({"source-device"})
    manager._handle_event(
        SimpleNamespace(
            event_type="entity_registry_updated",
            data={"entity_id": "sensor.unrelated"},
        )
    )
    manager._handle_event(
        SimpleNamespace(
            event_type="device_registry_updated",
            data={
                "action": "update",
                "device_id": "unrelated-device",
                "changes": {"name_by_user": "old name"},
            },
        )
    )
    check(
        reasons == ["lovelace_updated", "lovelace_updated"],
        "Unrelated registry churn does not trigger a full reconciliation",
    )
    manager._handle_event(
        SimpleNamespace(
            event_type="entity_registry_updated",
            data={"entity_id": "camera.source"},
        )
    )
    manager._handle_event(
        SimpleNamespace(
            event_type="device_registry_updated",
            data={"device_id": "source-device"},
        )
    )
    manager._handle_event(
        SimpleNamespace(
            event_type="device_registry_updated",
            data={
                "action": "update",
                "device_id": "new-apple-tv-device",
                "changes": {"config_entries": ()},
            },
        )
    )
    check(
        reasons[-3:]
        == [
            "entity_registry_updated",
            "device_registry_updated",
            "device_registry_updated",
        ],
        "Selected provenance and newly changed Apple TV associations still reconcile",
    )
    return 9


def check_source_events_preserve_fault_backoff() -> int:
    """A 15-second source poll cannot collapse a longer fault backoff."""

    class BackoffTask:
        cancelled = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

    class NoNewTaskHass:
        def async_create_task(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("A source event must not replace the backoff task")

    manager = manager_module.PlatformSyncManager(
        NoNewTaskHass(), SimpleNamespace(enabled=True)
    )
    task = BackoffTask()
    manager._debounce_task = task
    manager._retry_backoff_active = True
    manager.schedule("source_poll")
    check(not task.cancelled, "Source polling preserves the active fault backoff")
    check(
        manager._pending_reason == "source_poll",
        "The newest source event is queued behind the fault backoff",
    )
    return 2


async def check_matter_startup_recovery_grace() -> int:
    """Normal Matterbridge warm-up never triggers an immediate restart."""
    class StartupBus:
        def __init__(self) -> None:
            self.started_callback: Any = None

        def async_listen(self, _event: str, _callback: Any) -> Any:
            return lambda: None

        def async_listen_once(self, event: str, callback: Any) -> Any:
            check(
                event == "homeassistant_started",
                "Matterbridge grace waits for Home Assistant's started event",
            )
            self.started_callback = callback
            return lambda: None

    startup_hass = SimpleNamespace(
        state=manager_module.CoreState.starting,
        bus=StartupBus(),
    )
    startup_manager = manager_module.PlatformSyncManager(
        startup_hass,
        SimpleNamespace(
            enabled=True,
            source_kind=const.SourceKind.MANUAL,
            targets=frozenset(),
        ),
    )
    startup_reasons: list[str] = []
    startup_manager.schedule = startup_reasons.append
    await startup_manager.async_start()
    check(
        startup_manager._started_at is None,
        "Matterbridge startup grace does not begin while HA Core is still starting",
    )
    startup_hass.bus.started_callback(SimpleNamespace())
    check(
        startup_manager._started_at is not None
        and startup_reasons == ["startup_scan"],
        "Matterbridge startup grace begins exactly when the mandatory startup scan is scheduled",
    )

    expected = frozenset({"light.one"})
    error = targets.MatterbridgeRuntimeError(
        "plugin_not_started", expected, recoverable=True
    )
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    now = asyncio.get_running_loop().time()
    manager._started_at = now
    recovered: list[frozenset[str]] = []

    async def recover(
        _config: Any,
        entities: frozenset[str],
        *,
        before_matter_process_restart: Any,
    ) -> dict[str, Any]:
        del before_matter_process_restart
        recovered.append(entities)
        return {"loaded": True}

    original_recover = manager_module.async_recover_matter_runtime
    manager_module.async_recover_matter_runtime = recover
    try:
        prestart_manager = manager_module.PlatformSyncManager(
            SimpleNamespace(), SimpleNamespace(enabled=True)
        )
        prestart = await prestart_manager._async_attempt_matter_recovery(
            error, background=True
        )
        check(
            prestart is None and recovered == [],
            "a fallback poll before HA_STARTED can never trigger Matterbridge recovery",
        )
        first = await manager._async_attempt_matter_recovery(
            error, background=True
        )
        check(
            first is None and recovered == [],
            "the first startup observation performs no Matterbridge restart",
        )
        manager._started_at -= (
            manager_module.MATTER_RECOVERY_STARTUP_GRACE_SECONDS + 1
        )
        assert manager._matter_failure_first_at is not None
        manager._matter_failure_first_at -= (
            manager_module.MATTER_RECOVERY_MIN_FAILURE_SECONDS + 1
        )
        second = await manager._async_attempt_matter_recovery(
            error, background=True
        )
    finally:
        manager_module.async_recover_matter_runtime = original_recover
    check(
        second == {"loaded": True} and recovered == [expected],
        "persistent post-grace failure permits one guarded recovery",
    )
    check(
        manager._matter_failure_count == 0,
        "successful Matterbridge recovery clears the observation episode",
    )
    return 7


async def check_matter_recovery_episode_and_cooldown() -> int:
    """Background recovery is once per episode and never more often than five minutes."""
    expected = frozenset({"light.one"})
    recoverable = targets.MatterbridgeRuntimeError(
        "plugin_error", expected, recoverable=True
    )
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    calls: list[frozenset[str]] = []

    def make_recovery_eligible(instance: Any) -> None:
        now = asyncio.get_running_loop().time()
        instance._started_at = (
            now - manager_module.MATTER_RECOVERY_STARTUP_GRACE_SECONDS - 1
        )
        instance._matter_failure_count = 1
        instance._matter_failure_first_at = (
            now - manager_module.MATTER_RECOVERY_MIN_FAILURE_SECONDS - 1
        )

    async def recover(
        _config: Any,
        entities: frozenset[str],
        *,
        before_matter_process_restart: Any,
    ) -> dict[str, Any]:
        calls.append(entities)
        check(
            before_matter_process_restart(),
            "Background recovery authorizes its full restart before send",
        )
        return {"loaded": True}

    original_recover = manager_module.async_recover_matter_runtime
    manager_module.async_recover_matter_runtime = recover
    try:
        make_recovery_eligible(manager)
        first = await manager._async_attempt_matter_recovery(
            recoverable, background=True
        )
        second = await manager._async_attempt_matter_recovery(
            recoverable, background=True
        )
        manager._matter_recovery_guard.last_attempt -= (
            manager_module.MATTER_RECOVERY_COOLDOWN_SECONDS + 1
        )
        make_recovery_eligible(manager)
        third = await manager._async_attempt_matter_recovery(
            recoverable, background=True
        )
        disabled = manager_module.PlatformSyncManager(
            SimpleNamespace(), SimpleNamespace(enabled=False)
        )
        stopping = manager_module.PlatformSyncManager(
            SimpleNamespace(), SimpleNamespace(enabled=True)
        )
        stopping._stopping = True
        direct = manager_module.PlatformSyncManager(
            SimpleNamespace(), SimpleNamespace(enabled=True)
        )
        blocked_by_lifecycle = (
            await disabled._async_attempt_matter_recovery(
                recoverable, background=True
            ),
            await stopping._async_attempt_matter_recovery(
                recoverable, background=True
            ),
            await direct._async_attempt_matter_recovery(
                recoverable, background=False
            ),
        )
    finally:
        manager_module.async_recover_matter_runtime = original_recover
    check(
        first == {"loaded": True} and second is None and third == {"loaded": True},
        "A recovered episode resets, while the five-minute cooldown remains enforced",
    )
    check(
        calls == [expected, expected],
        "Cooldown prevents repeated full Matterbridge process restarts",
    )
    check(
        blocked_by_lifecycle == (None, None, None),
        "Automatic process recovery runs only in an enabled background lifecycle",
    )

    failing = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    make_recovery_eligible(failing)
    failed_calls = 0

    async def fail_recovery(
        _config: Any,
        _entities: frozenset[str],
        *,
        before_matter_process_restart: Any,
    ) -> Any:
        nonlocal failed_calls
        del before_matter_process_restart
        failed_calls += 1
        raise RuntimeError("safe simulated recovery failure")

    manager_module.async_recover_matter_runtime = fail_recovery
    try:
        try:
            await failing._async_attempt_matter_recovery(
                recoverable, background=True
            )
        except RuntimeError:
            check(True, "A failed recovery remains fail-closed")
        else:
            raise AssertionError("A failed recovery must propagate")
        repeated = await failing._async_attempt_matter_recovery(
            recoverable, background=True
        )
        blocked = await failing._async_attempt_matter_recovery(
            targets.MatterbridgeRuntimeError(
                "token_missing", expected, recoverable=False
            ),
            background=True,
        )
    finally:
        manager_module.async_recover_matter_runtime = original_recover
    check(
        failed_calls == 1 and repeated is None,
        "A failed episode never performs a second recovery attempt",
    )
    check(blocked is None, "Non-recoverable Matterbridge states never restart")
    return 6


def check_matter_transaction_restart_is_not_recovery_throttled() -> int:
    """Back-to-back exact removals do not consume the recovery cooldown."""
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(data={}),
        SimpleNamespace(
            enabled=True,
            matter_host="matterbridge.test",
            matter_port=8283,
        ),
    )
    for index in range(2):
        check(
            manager._reserve_matter_transaction_restart(),
            f"normal removal {index + 1} reserves its restart before the write",
        )
        check(
            manager._before_matter_process_restart(),
            f"normal removal {index + 1} consumes its own restart reservation",
        )
    check(
        manager._matter_recovery_guard.last_attempt is None
        and not manager._matter_recovery_guard.process_restart_attempted,
        "normal removal restarts do not consume or arm the recovery cooldown",
    )

    check(
        manager._before_matter_process_restart(),
        "a separate runtime recovery can still reserve its guarded restart",
    )
    recovery_timestamp = manager._matter_recovery_guard.last_attempt
    check(
        manager._reserve_matter_transaction_restart()
        and manager._before_matter_process_restart()
        and manager._matter_recovery_guard.last_attempt == recovery_timestamp,
        "a later normal removal remains legal during a recovery cooldown",
    )
    return 7


async def check_matter_apply_restart_guard_across_reload() -> int:
    """A later target failure cannot cause a second process restart on retry."""
    selected = frozenset(
        {const.TargetPlatform.GOOGLE, const.TargetPlatform.MATTER}
    )
    rules = {platform: models.PlatformRule() for platform in const.TargetPlatform}
    config = SimpleNamespace(
        enabled=True,
        targets=selected,
        user_rules=rules,
        locked_rules=rules,
        matter_host="matterbridge.test",
        matter_port=8283,
    )
    hass = SimpleNamespace(bus=TransactionBus(), data={})
    first_manager = manager_module.PlatformSyncManager(hass, config)
    actual = {platform: frozenset() for platform in selected}
    google_reads = 0
    restart_authorizations: list[bool] = []
    restarts_sent = 0

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(entities=frozenset({"light.one"}))

    async def read_target(
        _hass: Any, _config: Any, platform: Any
    ) -> frozenset[str]:
        nonlocal google_reads
        if platform is const.TargetPlatform.GOOGLE:
            google_reads += 1
            if google_reads == 2:
                return frozenset()
        return actual[platform]

    async def validate_target(
        _hass: Any, _config: Any, _platform: Any, _expected: Any
    ) -> dict[str, Any]:
        return {"loaded": True}

    async def room_updates(
        _hass: Any, _config: Any, _desired: Any, _rooms: Any
    ) -> tuple[str, ...]:
        return ()

    async def prepare_target(_hass: Any, _config: Any, platform: Any) -> Any:
        return SimpleNamespace(platform=platform, entities=actual[platform])

    async def apply_target(
        _hass: Any,
        _config: Any,
        plan: Any,
        _rooms: Any,
        **kwargs: Any,
    ) -> bool:
        nonlocal restarts_sent
        actual[plan.platform] = plan.desired
        if plan.platform is not const.TargetPlatform.MATTER:
            return False
        authorize = kwargs.get("before_matter_process_restart")
        allowed = bool(authorize and authorize())
        restart_authorizations.append(allowed)
        if not allowed:
            raise RuntimeError("simulated process restart blocked by guard")
        guard = first_manager._matter_recovery_guard
        check(
            guard.process_restart_attempted and guard.last_attempt is not None,
            "The manager records a process restart before the command is sent",
        )
        restarts_sent += 1
        return True

    async def restore_target(_hass: Any, _config: Any, backup: Any) -> None:
        actual[backup.platform] = backup.entities

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
    manager_module.async_google_room_updates = room_updates
    manager_module.async_prepare_target = prepare_target
    manager_module.async_apply_plan = apply_target
    manager_module.async_restore_target = restore_target
    previous_log_state = manager_module._LOGGER.disabled
    manager_module._LOGGER.disabled = True
    try:
        try:
            await first_manager.async_reconcile(reason="first_apply", apply=True)
        except RuntimeError as error:
            check(
                "google readback mismatch" in str(error),
                "A later Google readback failure aborts the first transaction",
            )
        else:
            raise AssertionError("The first transaction must fail after Matter restart")
        check(
            first_manager._matter_recovery_guard.attempted_for_episode,
            "A later platform failure retains the Matter process-restart episode marker",
        )

        reloaded_manager = manager_module.PlatformSyncManager(hass, config)
        check(
            reloaded_manager._matter_recovery_guard
            is first_manager._matter_recovery_guard,
            "Config Entry reload reuses the endpoint recovery guard from hass.data",
        )
        try:
            await reloaded_manager.async_reconcile(reason="retry_after_error", apply=True)
        except RuntimeError as error:
            check(
                "blocked by guard" in str(error),
                "The immediate retry fails closed when another restart is unauthorized",
            )
        else:
            raise AssertionError("The cooldown must block an immediate process restart")
    finally:
        manager_module._LOGGER.disabled = previous_log_state
        (
            manager_module.async_read_source,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
        ) = original_functions

    check(
        restart_authorizations == [True, False] and restarts_sent == 1,
        "Apply and retry share one five-minute process-restart authorization",
    )
    check(
        actual == {platform: frozenset() for platform in selected},
        "Both failed transactions restore their exact pre-change target sets",
    )
    return 7


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
        if len(sleeps) <= 7:
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
        calls
        == [
            "startup_scan",
            "retry_after_error",
            "retry_after_error",
            "retry_after_error",
            "retry_after_error",
            "retry_after_error",
            "retry_after_error",
        ]
        and sleeps == [2, 15, 30, 60, 120, 300, 300, 300],
        "Permanent errors follow the exact bounded retry schedule",
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


class LifecycleConfigEntries:
    """Mutable Config Entry registry for manager lifecycle acceptance tests."""

    def __init__(self, profile: FakeEntry, homekit_entries: list[FakeEntry]) -> None:
        self.profile = profile
        self.homekit_entries = homekit_entries
        self.updated: list[tuple[str, dict[str, Any]]] = []

    def async_entries(self, domain: str) -> list[FakeEntry]:
        if domain == "homekit":
            return list(self.homekit_entries)
        if domain == const.DOMAIN:
            return [self.profile]
        return []

    def async_get_entry(self, entry_id: str) -> FakeEntry | None:
        if entry_id == self.profile.entry_id:
            return self.profile
        return next(
            (
                entry
                for entry in self.homekit_entries
                if entry.entry_id == entry_id
            ),
            None,
        )

    def async_update_entry(
        self, entry: FakeEntry, *, options: dict[str, Any]
    ) -> None:
        entry.options = deepcopy(options)
        self.updated.append((entry.entry_id, deepcopy(options)))


def lifecycle_manager_fixture(
    *,
    enabled: bool = True,
    managed: tuple[str, ...] = ("main",),
    lifecycle: tuple[str, ...] = (),
    pending: tuple[str, ...] = (),
    restart_required: tuple[str, ...] = (),
    homekit_entries: list[FakeEntry] | None = None,
    core_state: Any = None,
) -> tuple[Any, FakeEntry, Any]:
    """Build one real SyncConfig plus mutable Config Entry ledger."""
    data = {
        const.CONF_SOURCE_KIND: const.SourceKind.MANUAL.value,
        const.CONF_TARGET_PLATFORMS: [const.TargetPlatform.HOMEKIT.value],
    }
    options = {
        const.CONF_ENABLED: enabled,
        const.CONF_SOURCE_ENTITIES: [],
        const.CONF_HOMEKIT_MANAGED_ENTRY_IDS: list(managed),
        const.CONF_HOMEKIT_MAIN_ENTRY_ID: "main",
        const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS: list(lifecycle),
        const.CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS: list(pending),
        const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS: list(restart_required),
    }
    profile = FakeEntry(
        "platform-sync-profile",
        domain=const.DOMAIN,
        data=data,
        options=options,
    )
    entries = homekit_entries or [
        FakeEntry(
            "main",
            options={
                "mode": "bridge",
                "filter": {"include_entities": []},
            },
        )
    ]
    config_entries = LifecycleConfigEntries(profile, entries)
    hass = SimpleNamespace(
        bus=TransactionBus(),
        config=SimpleNamespace(language="en"),
        config_entries=config_entries,
        data={},
        state=(
            manager_module.CoreState.running
            if core_state is None
            else core_state
        ),
        states=SimpleNamespace(
            get=lambda entity_id: SimpleNamespace(
                entity_id=entity_id,
                attributes={"friendly_name": entity_id},
            )
        ),
    )
    config = runtime_config_module.SyncConfig.from_entry(data, options)
    return hass, profile, config


def check_homekit_selected_pairing_requirements() -> int:
    """Selected unpaired entries are listed even without a pending ledger row."""

    def pairing_runtime(paired: bool) -> Any:
        return SimpleNamespace(
            homekit=SimpleNamespace(
                driver=SimpleNamespace(
                    state=SimpleNamespace(
                        paired_clients={"controller": object()} if paired else {}
                    )
                )
            )
        )

    main = FakeEntry(
        "main",
        options={
            "mode": "bridge",
            "filter": {"include_entities": ["light.one", "light.two"]},
        },
        runtime_data=pairing_runtime(True),
    )
    wanted = FakeEntry(
        "wanted-side",
        source="accessory",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.wanted"]},
        },
        runtime_data=pairing_runtime(False),
    )
    stale = FakeEntry(
        "stale-side",
        source="accessory",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.stale"]},
        },
        runtime_data=pairing_runtime(False),
    )
    hass, profile, config = lifecycle_manager_fixture(
        managed=("main", "wanted-side", "stale-side"),
        lifecycle=("wanted-side", "stale-side"),
        pending=(),
        homekit_entries=[main, wanted, stale],
    )
    manager = manager_module.PlatformSyncManager(hass, config, profile)
    requirements = manager._pairing_requirements(
        frozenset({"light.one", "light.two", "camera.wanted"})
    )
    check(
        [item.entity_id for item in requirements] == ["camera.wanted"],
        "an adopted unpaired desired accessory is listed while a stale prune target is not",
    )

    main.runtime_data = pairing_runtime(False)
    main.options["filter"]["include_entities"] = ["light.one"]
    requirements = manager._pairing_requirements(
        frozenset({"light.one", "camera.wanted"})
    )
    check(
        {item.entity_id for item in requirements}
        == {"config_entry:main", "camera.wanted"},
        "an unpaired one-entity main Bridge is still listed as one Bridge pairing action",
    )

    manager._update_homekit_tracking(add_pending_pairing_ids={"wanted-side"})
    wanted.runtime_data = pairing_runtime(True)
    main.runtime_data = pairing_runtime(True)
    requirements = manager._pairing_requirements(
        frozenset({"light.one", "light.two", "camera.wanted"})
    )
    check(
        requirements == []
        and profile.options[const.CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS] == [],
        "a paired selected accessory clears its durable pending marker",
    )
    return 3


async def check_homekit_prune_confirmation_identity() -> int:
    """Every prune-candidate identity field participates in confirmation."""
    manager = manager_module.PlatformSyncManager(
        SimpleNamespace(), SimpleNamespace(enabled=True)
    )
    base = SimpleNamespace(
        entry_id="side-entry",
        entity_id="camera.stairs",
        imported=False,
        name="Stairs Camera",
        port=21064,
        mode="accessory",
        yaml_relative_path=None,
    )
    check(
        manager._homekit_prune_confirmed("source-a", (base,), apply=True)
        is False,
        "A first prune observation never confirms deletion",
    )
    variants = (
        ("entry ID", {"entry_id": "replacement-entry"}),
        ("entity ID", {"entity_id": "camera.replacement"}),
        ("import provenance", {"imported": True}),
        ("name", {"name": "Replacement Camera"}),
        ("port", {"port": 21065}),
        ("mode", {"mode": "bridge"}),
        ("YAML path", {"yaml_relative_path": "other-homekit.yaml"}),
    )
    base_values = vars(base)
    for label, change in variants:
        manager._homekit_prune_first_seen = (
            asyncio.get_running_loop().time()
            - manager_module.INTERNAL_LIFECYCLE_CONFIRM_SECONDS
            - 1
        )
        variant = SimpleNamespace(**{**base_values, **change})
        check(
            manager._homekit_prune_confirmed(
                "source-a", (variant,), apply=True
            )
            is False,
            f"A changed prune candidate {label} resets confirmation",
        )
        # Restore a known base signature before testing the next single field.
        manager._homekit_prune_confirmed("source-a", (base,), apply=True)

    manager._homekit_prune_first_seen = (
        asyncio.get_running_loop().time()
        - manager_module.INTERNAL_LIFECYCLE_CONFIRM_SECONDS
        - 1
    )
    check(
        manager._homekit_prune_confirmed("source-b", (base,), apply=True)
        is False,
        "A changed source fingerprint resets prune confirmation",
    )
    manager._homekit_prune_first_seen = (
        asyncio.get_running_loop().time()
        - manager_module.INTERNAL_LIFECYCLE_CONFIRM_SECONDS
        - 1
    )
    check(
        manager._homekit_prune_confirmed("source-b", (base,), apply=True)
        is True,
        "Two identical full prune identities separated by the hold time confirm",
    )
    manager._clear_homekit_prune_confirmation()
    return 10


async def check_homekit_lifecycle_progress_persistence() -> int:
    """Partial prune progress is durable before errors or cancellation escape."""

    async def run_scenario(cancelled: bool) -> tuple[Any, FakeEntry, list[bool]]:
        main = FakeEntry(
            "main",
            options={"mode": "bridge", "filter": {"include_entities": []}},
        )
        removed = FakeEntry(
            "side-removed",
            options={
                "mode": "accessory",
                "filter": {"include_entities": ["camera.removed"]},
            },
        )
        absent = FakeEntry(
            "side-absent",
            options={
                "mode": "accessory",
                "filter": {"include_entities": ["camera.absent"]},
            },
        )
        hass, profile, config = lifecycle_manager_fixture(
            managed=(main.entry_id, removed.entry_id, absent.entry_id),
            lifecycle=(removed.entry_id, absent.entry_id),
            pending=(removed.entry_id, absent.entry_id),
            homekit_entries=[main, removed, absent],
        )
        candidates = (
            SimpleNamespace(
                entry_id=removed.entry_id,
                entity_id="camera.removed",
                imported=False,
                name="Removed",
                port=21064,
                yaml_relative_path=None,
            ),
            SimpleNamespace(
                entry_id=absent.entry_id,
                entity_id="camera.absent",
                imported=False,
                name="Absent",
                port=21065,
                yaml_relative_path=None,
            ),
        )
        current = frozenset(candidate.entity_id for candidate in candidates)
        published: list[bool] = []

        async def read_source(_hass: Any, _config: Any) -> Any:
            return models.SourceSnapshot(
                entities=frozenset(),
                source_revision="lifecycle-partial-progress",
            )

        async def find_apple_tv(_hass: Any) -> frozenset[str]:
            return frozenset()

        async def read_target(
            _hass: Any, _config: Any, _platform: Any
        ) -> frozenset[str]:
            return current

        async def validate_target(
            _hass: Any,
            _config: Any,
            _platform: Any,
            _expected: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            return {"loaded": True}

        async def remove_candidates(
            _hass: Any, _candidates: Any, **_kwargs: Any
        ) -> Any:
            hass.config_entries.homekit_entries[:] = [main]
            kwargs = {
                "removed_entry_ids": {removed.entry_id},
                "removed_entities": {"camera.removed"},
                "already_absent_entry_ids": set(),
                "restart_required_entry_ids": {removed.entry_id},
                "uncertain_entry_ids": {absent.entry_id},
                "yaml_backup_paths": ("backup/homekit.yaml",),
            }
            if cancelled:
                raise manager_module.HomeKitLifecycleCancelled(
                    "cancelled after verified progress", **kwargs
                )
            raise manager_module.HomeKitLifecycleError(
                "failed after verified progress", **kwargs
            )

        async def unexpected_prepare(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("A retained prune candidate must not be prepared")

        async def unexpected_apply(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("A retained prune candidate must not be applied")

        originals = (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_remove_homekit_accessory_candidates,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
        )
        manager_module.async_read_source = read_source
        manager_module.async_find_apple_tv_entities = find_apple_tv
        manager_module.async_read_target = read_target
        manager_module.async_validate_target = validate_target
        manager_module.homekit_new_accessory_mode_entities = (
            lambda *_args, **_kwargs: frozenset()
        )
        manager_module.async_remove_homekit_accessory_candidates = remove_candidates
        manager_module.async_prepare_target = unexpected_prepare
        manager_module.async_apply_plan = unexpected_apply
        manager = manager_module.PlatformSyncManager(hass, config, profile)
        manager._homekit_prune_candidates = lambda _desired: candidates
        manager._homekit_prune_confirmed = (
            lambda _fingerprint, _candidates, *, apply: apply
        )
        manager._publish_homekit_restart_requirement = published.append
        manager._publish_pairing_requirements = lambda _requirements: None
        try:
            if cancelled:
                try:
                    await manager.async_reconcile(
                        reason="lifecycle_cancelled", apply=True
                    )
                except manager_module.HomeKitLifecycleCancelled:
                    pass
                else:
                    raise AssertionError("Lifecycle cancellation must propagate")
            else:
                logger_disabled = manager_module._LOGGER.disabled
                manager_module._LOGGER.disabled = True
                try:
                    try:
                        await manager.async_reconcile(
                            reason="lifecycle_error", apply=True
                        )
                    except manager_module.HomeKitLifecycleError:
                        pass
                    else:
                        raise AssertionError("Lifecycle error must propagate")
                finally:
                    manager_module._LOGGER.disabled = logger_disabled
        finally:
            (
                manager_module.async_read_source,
                manager_module.async_find_apple_tv_entities,
                manager_module.async_read_target,
                manager_module.async_validate_target,
                manager_module.homekit_new_accessory_mode_entities,
                manager_module.async_remove_homekit_accessory_candidates,
                manager_module.async_prepare_target,
                manager_module.async_apply_plan,
            ) = originals
        return manager, profile, published

    for cancelled in (True, False):
        manager, profile, published = await run_scenario(cancelled)
        check(
            profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
            == ["main", "side-absent"]
            and profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
            == ["side-absent"]
            and profile.options[const.CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS]
            == ["side-absent"],
            "Partial lifecycle progress removes only confirmed IDs and retains uncertain ownership",
        )
        check(
            profile.options[const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS]
            == ["side-absent", "side-removed"]
            and manager.state.homekit_restart_required is True,
            "Partial lifecycle progress persists confirmed-restart and uncertain-removal markers before propagation",
        )
        check(
            manager.state.homekit_yaml_backups == ["backup/homekit.yaml"]
            and published == [True],
            "Partial lifecycle progress preserves backup evidence and publishes the restart gate",
        )
        blocked = await manager.async_reconcile(
            reason="uncertain_lifecycle_followup", apply=True
        )
        check(
            blocked["status"] == "homekit_restart_required"
            and profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
            == ["side-absent"],
            "A same-process follow-up is restart-gated before live absence can drop uncertain ownership",
        )
    return 8


async def check_homekit_restart_required_postcommit() -> int:
    """A successful prune requiring restart stops all same-turn lifecycle work."""
    main = FakeEntry(
        "main",
        options={"mode": "bridge", "filter": {"include_entities": []}},
    )
    old = FakeEntry(
        "old-side",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.old"]},
        },
    )
    hass, profile, config = lifecycle_manager_fixture(
        managed=(main.entry_id, old.entry_id),
        lifecycle=(old.entry_id,),
        homekit_entries=[main, old],
    )
    candidate = SimpleNamespace(
        entry_id=old.entry_id,
        entity_id="camera.old",
        imported=False,
        name="Old Camera",
        port=21064,
        yaml_relative_path=None,
    )
    actual = frozenset({"camera.old"})
    reads = 0
    validations = 0
    creates = 0

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset({"camera.new"}),
            source_revision="restart-required",
        )

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_target(
        _hass: Any, _config: Any, _platform: Any
    ) -> frozenset[str]:
        nonlocal reads
        reads += 1
        return actual

    async def validate_target(
        _hass: Any,
        _config: Any,
        _platform: Any,
        _expected: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal validations
        validations += 1
        return {"loaded": True, "controller_verified": False}

    async def remove_candidates(
        _hass: Any, _candidates: Any, **_kwargs: Any
    ) -> Any:
        nonlocal actual
        actual = frozenset()
        hass.config_entries.homekit_entries[:] = [main]
        return SimpleNamespace(
            removed_entry_ids=frozenset({old.entry_id}),
            already_absent_entry_ids=frozenset(),
            restart_required_entry_ids=frozenset({old.entry_id}),
            yaml_backup_paths=("backup/old-side.yaml",),
        )

    async def create_accessory(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal creates
        creates += 1
        raise AssertionError("A restart-gated turn cannot create an accessory")

    async def unexpected_prepare(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Temporary HomeKit desired set should already be exact")

    async def unexpected_apply(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Temporary HomeKit desired set should already be exact")

    originals = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.homekit_new_accessory_mode_entities,
        manager_module.async_remove_homekit_accessory_candidates,
        manager_module.async_create_homekit_accessory,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.homekit_new_accessory_mode_entities = (
        lambda *_args, **_kwargs: frozenset({"camera.new"})
    )
    manager_module.async_remove_homekit_accessory_candidates = remove_candidates
    manager_module.async_create_homekit_accessory = create_accessory
    manager_module.async_prepare_target = unexpected_prepare
    manager_module.async_apply_plan = unexpected_apply
    manager = manager_module.PlatformSyncManager(hass, config, profile)
    manager._homekit_prune_candidates = lambda _desired: (candidate,)
    manager._homekit_prune_confirmed = (
        lambda _fingerprint, _candidates, *, apply: apply
    )
    manager._publish_homekit_restart_requirement = lambda _required: None
    manager._publish_pairing_requirements = lambda _requirements: None
    try:
        result = await manager.async_reconcile(
            reason="restart_required_postcommit", apply=True
        )
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_remove_homekit_accessory_candidates,
            manager_module.async_create_homekit_accessory,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
        ) = originals
    check(
        result["status"] == "homekit_restart_required"
        and result["homekit_restart_required"] is True,
        "A verified prune requiring restart cannot report synchronized",
    )
    check(
        reads == 2 and validations == 1,
        "Restart-required readback skips the post-lifecycle exact runtime validator",
    )
    check(
        creates == 0
        and "camera.new"
        not in profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS],
        "Restart-required reconciliation defers all new accessory creation",
    )
    check(
        profile.options[const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS]
        == [old.entry_id]
        and result["plans"]["homekit"]["runtime"]["restart_required"]
        is True,
        "Restart ledger and diagnostics retain the exact removed entry marker",
    )
    return 4


async def check_homekit_pending_prune_defers_accessory_creation() -> int:
    """Pending prune confirmation blocks creation until topology is safe."""
    main = FakeEntry(
        "main",
        options={
            "mode": "bridge",
            "filter": {"include_entities": ["light.old"]},
        },
    )
    old = FakeEntry(
        "old-side",
        source="accessory",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.old"]},
        },
    )
    hass, profile, config = lifecycle_manager_fixture(
        managed=(main.entry_id, old.entry_id),
        lifecycle=(old.entry_id,),
        homekit_entries=[main, old],
    )
    candidate = SimpleNamespace(
        entry_id=old.entry_id,
        entity_id="camera.old",
        imported=False,
        name="Old Camera",
        port=21064,
        mode="accessory",
        yaml_relative_path=None,
    )
    actual = frozenset({"light.old", "camera.old"})
    validation_allowances: list[frozenset[str]] = []
    lifecycle_calls: list[str] = []

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset({"light.new", "camera.new"}),
            source_revision="pending-prune-before-create",
        )

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_target(
        _hass: Any, _config: Any, _platform: Any
    ) -> frozenset[str]:
        return actual

    async def validate_target(
        _hass: Any,
        _config: Any,
        _platform: Any,
        _expected: Any,
        *,
        allowed_nonrunning_homekit_entry_ids: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        validation_allowances.append(allowed_nonrunning_homekit_entry_ids)
        old_is_live = old in hass.config_entries.homekit_entries
        if old_is_live:
            check(
                allowed_nonrunning_homekit_entry_ids
                == frozenset({old.entry_id}),
                "A non-running pending prune entry has the exact runtime allowance",
            )
        else:
            check(
                not allowed_nonrunning_homekit_entry_ids,
                "The final post-prune validator has no runtime allowance",
            )
        return {
            "loaded": True,
            "runtime_verified": not old_is_live,
            "runtime_pending_prune_entries": int(old_is_live),
        }

    async def prepare_target(
        _hass: Any, _config: Any, platform: Any
    ) -> Any:
        return targets.TargetBackup(platform=platform, payload=actual)

    async def apply_target(
        _hass: Any,
        _config: Any,
        plan: Any,
        _rooms: Any,
        **_kwargs: Any,
    ) -> bool:
        nonlocal actual
        actual = plan.desired
        return False

    async def unexpected_restore(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("The successful pending-prune path must not roll back")

    async def remove_candidates(
        _hass: Any, candidates: Any, **_kwargs: Any
    ) -> Any:
        nonlocal actual
        lifecycle_calls.append("prune")
        check(
            tuple(candidates) == (candidate,),
            "The confirmed prune removes only its exact candidate",
        )
        hass.config_entries.homekit_entries.remove(old)
        actual -= frozenset({"camera.old"})
        return SimpleNamespace(
            removed_entry_ids=frozenset({old.entry_id}),
            already_absent_entry_ids=frozenset(),
            restart_required_entry_ids=frozenset(),
            uncertain_entry_ids=frozenset(),
            yaml_backup_paths=(),
        )

    async def create_accessory(_hass: Any, entity_id: str) -> Any:
        nonlocal actual
        lifecycle_calls.append("create")
        check(
            entity_id == "camera.new"
            and old not in hass.config_entries.homekit_entries,
            "Deferred creation starts only after the stale side entry is gone",
        )
        created = FakeEntry(
            "new-side",
            source="accessory",
            options={
                "mode": "accessory",
                "filter": {"include_entities": [entity_id]},
            },
        )
        hass.config_entries.homekit_entries.append(created)
        actual |= frozenset({entity_id})
        return created, None

    originals = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
        manager_module.async_restore_target,
        manager_module.homekit_new_accessory_mode_entities,
        manager_module.async_remove_homekit_accessory_candidates,
        manager_module.async_create_homekit_accessory,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_prepare_target = prepare_target
    manager_module.async_apply_plan = apply_target
    manager_module.async_restore_target = unexpected_restore
    manager_module.homekit_new_accessory_mode_entities = (
        lambda *_args, **_kwargs: frozenset({"camera.new"})
    )
    manager_module.async_remove_homekit_accessory_candidates = remove_candidates
    manager_module.async_create_homekit_accessory = create_accessory
    manager = manager_module.PlatformSyncManager(hass, config, profile)
    manager._homekit_prune_candidates = lambda _desired: (candidate,)
    manager._publish_homekit_restart_requirement = lambda _required: None
    manager._publish_pairing_requirements = lambda _requirements: None
    try:
        pending_result = await manager.async_reconcile(
            reason="pending_prune", apply=True
        )
        check(
            pending_result["status"] == "pending_confirmation"
            and lifecycle_calls == [],
            "The first pending-prune turn performs neither prune nor creation",
        )
        check(
            actual == frozenset({"light.new", "camera.old"})
            and validation_allowances
            == [frozenset({old.entry_id}), frozenset({old.entry_id})],
            "The reversible main update validates around the retained candidate",
        )

        manager._homekit_prune_first_seen = (
            asyncio.get_running_loop().time()
            - manager_module.INTERNAL_LIFECYCLE_CONFIRM_SECONDS
            - 1
        )
        completed_result = await manager.async_reconcile(
            reason="confirmed_prune", apply=True
        )
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_remove_homekit_accessory_candidates,
            manager_module.async_create_homekit_accessory,
        ) = originals

    check(
        lifecycle_calls == ["prune", "create"],
        "The confirmed turn prunes before creating the replacement accessory",
    )
    check(
        completed_result["status"] == "synced_manual_pairing_required"
        and actual == frozenset({"light.new", "camera.new"}),
        "Confirmed prune and deferred creation converge to the logical set",
    )
    check(
        validation_allowances
        == [
            frozenset({old.entry_id}),
            frozenset({old.entry_id}),
            frozenset({old.entry_id}),
            frozenset(),
        ],
        "The runtime allowance exists only while the prune candidate remains live",
    )
    check(
        profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["main", "new-side"]
        and profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
        == ["new-side"]
        and old not in hass.config_entries.homekit_entries,
        "Ownership moves from the pruned side entry to the created replacement",
    )
    return 6


async def check_homekit_restart_marker_startup_scope() -> int:
    """Only a new Core process clears the persisted HomeKit restart gate."""
    main = FakeEntry(
        "main",
        options={"mode": "bridge", "filter": {"include_entities": ["light.one"]}},
    )
    starting_hass, starting_profile, starting_config = lifecycle_manager_fixture(
        enabled=False,
        managed=("main", "uncertain-side"),
        lifecycle=("uncertain-side",),
        pending=("uncertain-side",),
        restart_required=("uncertain-side",),
        homekit_entries=[main],
        core_state=manager_module.CoreState.starting,
    )
    starting_manager = manager_module.PlatformSyncManager(
        starting_hass, starting_config, starting_profile
    )
    starting_published: list[bool] = []
    starting_manager._publish_homekit_restart_requirement = (
        starting_published.append
    )
    starting_manager._publish_pairing_requirements = lambda _requirements: None
    await starting_manager.async_start()
    check(
        starting_profile.options[
            const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS
        ]
        == []
        and starting_profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["main"]
        and starting_profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
        == []
        and starting_profile.options[const.CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS]
        == []
        and starting_manager.state.homekit_restart_required is False
        and starting_published == [False],
        "A full Core startup uses durable absence to clear uncertain ownership and the restart marker",
    )

    resurrected = FakeEntry(
        "uncertain-side",
        source="accessory",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.uncertain"]},
        },
    )
    live_hass, live_profile, live_config = lifecycle_manager_fixture(
        enabled=False,
        managed=("main", "uncertain-side"),
        lifecycle=("uncertain-side",),
        pending=("uncertain-side",),
        restart_required=("uncertain-side",),
        homekit_entries=[main, resurrected],
        core_state=manager_module.CoreState.starting,
    )
    live_manager = manager_module.PlatformSyncManager(
        live_hass, live_config, live_profile
    )
    live_manager._publish_homekit_restart_requirement = lambda _required: None
    live_manager._publish_pairing_requirements = lambda _requirements: None
    await live_manager.async_start()
    check(
        live_profile.options[const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS]
        == []
        and live_profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["main", "uncertain-side"]
        and live_profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
        == ["uncertain-side"],
        "A Config Entry resurrected from storage keeps lifecycle ownership for a safe retry",
    )

    running_hass, running_profile, running_config = lifecycle_manager_fixture(
        enabled=False,
        managed=("main", "uncertain-side"),
        lifecycle=("uncertain-side",),
        pending=("uncertain-side",),
        restart_required=("uncertain-side",),
        homekit_entries=[main],
        core_state=manager_module.CoreState.running,
    )
    running_manager = manager_module.PlatformSyncManager(
        running_hass, running_config, running_profile
    )
    running_published: list[bool] = []
    running_manager._publish_homekit_restart_requirement = running_published.append
    running_manager._publish_pairing_requirements = lambda _requirements: None
    await running_manager.async_start()
    check(
        running_profile.options[
            const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS
        ]
        == ["uncertain-side"]
        and running_profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["main", "uncertain-side"]
        and running_profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
        == ["uncertain-side"]
        and running_manager.state.homekit_restart_required is True
        and running_published == [True],
        "A same-process Config Entry reload preserves uncertain ownership and the restart gate",
    )

    # The marker can be created by a transaction while another direct/manual
    # reconciliation is already queued on the same manager lock. The queued
    # transaction must re-read the ledger after serialization and perform no
    # source or target work in that same Core process.
    queued_hass, queued_profile, queued_config = lifecycle_manager_fixture(
        enabled=True,
        managed=("main", "uncertain-side"),
        lifecycle=("uncertain-side",),
        homekit_entries=[main],
        core_state=manager_module.CoreState.running,
    )
    queued_manager = manager_module.PlatformSyncManager(
        queued_hass, queued_config, queued_profile
    )
    queued_manager._publish_homekit_restart_requirement = lambda _required: None
    reads = 0

    async def unexpected_source_read(*, background: bool) -> Any:
        nonlocal reads
        del background
        reads += 1
        raise AssertionError("A queued restart-gated apply must not read its source")

    class GateLock:
        def __init__(self) -> None:
            self.waiting = asyncio.Event()
            self.release = asyncio.Event()

        async def __aenter__(self) -> None:
            self.waiting.set()
            await self.release.wait()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    gate = GateLock()
    queued_manager._lock = gate
    queued_manager._async_read_source_with_recovery = unexpected_source_read
    queued_task = asyncio.create_task(
        queued_manager.async_reconcile(reason="queued_after_prune", apply=True)
    )
    await gate.waiting.wait()
    queued_profile.options = {
        **queued_profile.options,
        const.CONF_HOMEKIT_RESTART_REQUIRED_ENTRY_IDS: ["uncertain-side"],
    }
    queued_manager.config = runtime_config_module.SyncConfig.from_entry(
        queued_profile.data, queued_profile.options
    )
    gate.release.set()
    queued_result = await queued_task
    check(
        queued_result["status"] == "homekit_restart_required" and reads == 0,
        "A reconciliation queued before prune honors the restart marker after acquiring the transaction lock",
    )
    return 4


async def check_homekit_create_cancellation_persistence() -> int:
    """An attributed entry created during cancellation is owned before escape."""
    main = FakeEntry(
        "main",
        options={"mode": "bridge", "filter": {"include_entities": []}},
    )
    hass, profile, config = lifecycle_manager_fixture(
        homekit_entries=[main]
    )

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset({"camera.new"}),
            source_revision="create-cancelled",
        )

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return frozenset()

    async def read_target(
        _hass: Any, _config: Any, _platform: Any
    ) -> frozenset[str]:
        return frozenset()

    async def validate_target(
        _hass: Any, _config: Any, _platform: Any, _expected: Any
    ) -> dict[str, Any]:
        return {"loaded": True}

    async def create_accessory(_hass: Any, entity_id: str) -> Any:
        check(entity_id == "camera.new", "The deferred camera is created exactly")
        hass.config_entries.homekit_entries.append(
            FakeEntry(
                "new-side",
                options={
                    "mode": "accessory",
                    "filter": {"include_entities": [entity_id]},
                },
            )
        )
        raise manager_module.HomeKitAccessoryCreateCancelled(
            created_entry_id="new-side"
        )

    async def unexpected_prepare(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Deferred HomeKit creation needs no reversible apply")

    async def unexpected_apply(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Deferred HomeKit creation needs no reversible apply")

    originals = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.homekit_new_accessory_mode_entities,
        manager_module.async_create_homekit_accessory,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.homekit_new_accessory_mode_entities = (
        lambda *_args, **_kwargs: frozenset({"camera.new"})
    )
    manager_module.async_create_homekit_accessory = create_accessory
    manager_module.async_prepare_target = unexpected_prepare
    manager_module.async_apply_plan = unexpected_apply
    manager = manager_module.PlatformSyncManager(hass, config, profile)
    manager._publish_homekit_restart_requirement = lambda _required: None
    manager._publish_pairing_requirements = lambda _requirements: None
    try:
        try:
            await manager.async_reconcile(
                reason="create_cancelled", apply=True
            )
        except manager_module.HomeKitAccessoryCreateCancelled:
            pass
        else:
            raise AssertionError("Accessory creation cancellation must propagate")
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_create_homekit_accessory,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
        ) = originals
    check(
        profile.options[const.CONF_HOMEKIT_MANAGED_ENTRY_IDS]
        == ["main", "new-side"]
        and profile.options[const.CONF_HOMEKIT_LIFECYCLE_ENTRY_IDS]
        == ["new-side"]
        and profile.options[const.CONF_HOMEKIT_PENDING_PAIRING_ENTRY_IDS]
        == ["new-side"],
        "Cancelled creation persists exact ownership and pairing ledgers before propagation",
    )
    return 2


async def check_homekit_apple_tv_provenance_races() -> int:
    """Apple TV provenance changes fail closed before lifecycle mutation."""

    async def run_scenario(values: list[frozenset[str]]) -> tuple[str, list[Any]]:
        main = FakeEntry(
            "main",
            options={
                "mode": "bridge",
                "filter": {"include_entities": ["light.one"]},
            },
        )
        hass, profile, config = lifecycle_manager_fixture(
            homekit_entries=[main]
        )
        observed_prune_desired: list[frozenset[str]] = []
        lifecycle_calls: list[Any] = []

        async def read_source(_hass: Any, _config: Any) -> Any:
            return models.SourceSnapshot(
                entities=frozenset({"light.one"}),
                source_revision="apple-tv-race",
            )

        async def find_apple_tv(_hass: Any) -> frozenset[str]:
            return values.pop(0)

        async def read_target(
            _hass: Any, _config: Any, _platform: Any
        ) -> frozenset[str]:
            return frozenset({"light.one"})

        async def validate_target(
            _hass: Any, _config: Any, _platform: Any, _expected: Any
        ) -> dict[str, Any]:
            return {"loaded": True}

        async def lifecycle_mutation(*_args: Any, **_kwargs: Any) -> Any:
            lifecycle_calls.append((_args, _kwargs))
            raise AssertionError("A provenance race must precede lifecycle mutation")

        originals = (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_remove_homekit_accessory_candidates,
            manager_module.async_create_homekit_accessory,
        )
        manager_module.async_read_source = read_source
        manager_module.async_find_apple_tv_entities = find_apple_tv
        manager_module.async_read_target = read_target
        manager_module.async_validate_target = validate_target
        manager_module.homekit_new_accessory_mode_entities = (
            lambda *_args, **_kwargs: frozenset()
        )
        manager_module.async_remove_homekit_accessory_candidates = (
            lifecycle_mutation
        )
        manager_module.async_create_homekit_accessory = lifecycle_mutation
        manager = manager_module.PlatformSyncManager(hass, config, profile)
        manager._homekit_prune_candidates = lambda desired: (
            observed_prune_desired.append(frozenset(desired)) or ()
        )
        manager._publish_homekit_restart_requirement = lambda _required: None
        manager._publish_pairing_requirements = lambda _requirements: None
        logger_disabled = manager_module._LOGGER.disabled
        manager_module._LOGGER.disabled = True
        try:
            try:
                await manager.async_reconcile(
                    reason="apple_tv_provenance_race", apply=True
                )
            except RuntimeError as error:
                message = str(error)
            else:
                raise AssertionError("A changed Apple TV provenance set must fail")
        finally:
            manager_module._LOGGER.disabled = logger_disabled
            (
                manager_module.async_read_source,
                manager_module.async_find_apple_tv_entities,
                manager_module.async_read_target,
                manager_module.async_validate_target,
                manager_module.homekit_new_accessory_mode_entities,
                manager_module.async_remove_homekit_accessory_candidates,
                manager_module.async_create_homekit_accessory,
            ) = originals
        check(
            observed_prune_desired
            == [frozenset({"light.one"})],
            "Dynamic Apple TV exclusions remain absent from the lifecycle desired set so explicitly owned side entries can be pruned",
        )
        check(
            lifecycle_calls == [],
            "A changed Apple TV provenance set performs no lifecycle mutation",
        )
        return message, lifecycle_calls

    planning_message, _ = await run_scenario(
        [
            frozenset({"media_player.apple_tv"}),
            frozenset({"media_player.replacement"}),
        ]
    )
    check(
        "changed during planning" in planning_message,
        "Apple TV provenance changes during planning fail closed",
    )
    postcommit_message, _ = await run_scenario(
        [
            frozenset({"media_player.apple_tv"}),
            frozenset({"media_player.apple_tv"}),
            frozenset({"media_player.replacement"}),
        ]
    )
    check(
        "changed before lifecycle operation" in postcommit_message,
        "Apple TV provenance changes before post-commit lifecycle fail closed",
    )
    apple_side = FakeEntry(
        "apple-tv-side",
        data={"name": "Apple TV side", "port": 21064},
        options={
            "mode": "bridge",
            "filter": {"include_entities": ["media_player.apple_tv"]},
        },
    )
    prune_hass, prune_profile, prune_config = lifecycle_manager_fixture(
        managed=("main", "apple-tv-side"),
        lifecycle=("apple-tv-side",),
        homekit_entries=[
            FakeEntry(
                "main",
                options={
                    "mode": "bridge",
                    "filter": {"include_entities": ["light.one"]},
                },
            ),
            apple_side,
        ],
    )
    prune_manager = manager_module.PlatformSyncManager(
        prune_hass, prune_config, prune_profile
    )
    candidates = prune_manager._homekit_prune_candidates(
        frozenset({"light.one"})
    )
    check(
        len(candidates) == 1
        and candidates[0].entry_id == "apple-tv-side"
        and candidates[0].entity_id == "media_player.apple_tv",
        "An explicitly lifecycle-owned Apple TV side Bridge is removable when exclusion removes it from the exact HomeKit plan",
    )
    return 7


async def check_homekit_apple_tv_target_transaction_race_rolls_back() -> int:
    """A provenance change rolls back around a non-running prune candidate."""
    main = FakeEntry(
        "main",
        options={
            "mode": "bridge",
            "filter": {"include_entities": ["light.old"]},
        },
    )
    old = FakeEntry(
        "old-side",
        source="accessory",
        options={
            "mode": "accessory",
            "filter": {"include_entities": ["camera.old"]},
        },
    )
    hass, profile, config = lifecycle_manager_fixture(
        managed=(main.entry_id, old.entry_id),
        lifecycle=(old.entry_id,),
        homekit_entries=[main, old],
    )
    candidate = SimpleNamespace(
        entry_id=old.entry_id,
        entity_id="camera.old",
        imported=False,
        name="Old Camera",
        port=21064,
        mode="accessory",
        yaml_relative_path=None,
    )
    current = frozenset({"light.old", "camera.old"})
    provenance = [
        frozenset({"media_player.apple_tv"}),
        frozenset({"media_player.apple_tv"}),
        frozenset({"media_player.replacement"}),
    ]
    calls: list[str] = []
    validation_allowances: list[frozenset[str]] = []
    restore_allowances: list[frozenset[str]] = []

    async def read_source(_hass: Any, _config: Any) -> Any:
        return models.SourceSnapshot(
            entities=frozenset({"light.one"}),
            source_revision="apple-tv-target-race",
        )

    async def find_apple_tv(_hass: Any) -> frozenset[str]:
        return provenance.pop(0)

    async def read_target(
        _hass: Any, _config: Any, _platform: Any
    ) -> frozenset[str]:
        return current

    async def validate_target(
        _hass: Any,
        _config: Any,
        _platform: Any,
        _expected: Any,
        *,
        allowed_nonrunning_homekit_entry_ids: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        validation_allowances.append(allowed_nonrunning_homekit_entry_ids)
        return {
            "loaded": True,
            "runtime_verified": False,
            "runtime_pending_prune_entries": 1,
        }

    async def prepare_target(_hass: Any, _config: Any, platform: Any) -> Any:
        return targets.TargetBackup(platform=platform, payload=current)

    async def apply_target(
        _hass: Any, _config: Any, plan: Any, _rooms: Any, **_kwargs: Any
    ) -> bool:
        nonlocal current
        calls.append("apply")
        current = plan.desired
        return False

    async def restore_target(
        _hass: Any,
        _config: Any,
        backup: Any,
        *,
        allowed_nonrunning_homekit_entry_ids: frozenset[str] = frozenset(),
    ) -> None:
        nonlocal current
        calls.append("rollback")
        restore_allowances.append(allowed_nonrunning_homekit_entry_ids)
        current = backup.payload

    async def unexpected_lifecycle(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("lifecycle")
        raise AssertionError("The provenance race must roll back before lifecycle work")

    originals = (
        manager_module.async_read_source,
        manager_module.async_find_apple_tv_entities,
        manager_module.async_read_target,
        manager_module.async_validate_target,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
        manager_module.async_restore_target,
        manager_module.homekit_new_accessory_mode_entities,
        manager_module.async_remove_homekit_accessory_candidates,
        manager_module.async_create_homekit_accessory,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_prepare_target = prepare_target
    manager_module.async_apply_plan = apply_target
    manager_module.async_restore_target = restore_target
    manager_module.homekit_new_accessory_mode_entities = (
        lambda *_args, **_kwargs: frozenset()
    )
    manager_module.async_remove_homekit_accessory_candidates = unexpected_lifecycle
    manager_module.async_create_homekit_accessory = unexpected_lifecycle
    manager = manager_module.PlatformSyncManager(hass, config, profile)
    manager._homekit_prune_candidates = lambda _desired: (candidate,)
    manager._publish_homekit_restart_requirement = lambda _required: None
    manager._publish_pairing_requirements = lambda _requirements: None
    logger_disabled = manager_module._LOGGER.disabled
    manager_module._LOGGER.disabled = True
    try:
        try:
            await manager.async_reconcile(
                reason="apple_tv_target_transaction_race", apply=True
            )
        except RuntimeError as error:
            message = str(error)
        else:
            raise AssertionError("A target-transaction provenance race must fail")
    finally:
        manager_module._LOGGER.disabled = logger_disabled
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
            manager_module.async_restore_target,
            manager_module.homekit_new_accessory_mode_entities,
            manager_module.async_remove_homekit_accessory_candidates,
            manager_module.async_create_homekit_accessory,
        ) = originals
    check(
        "changed during target transaction" in message,
        "Apple TV provenance is rechecked before the reversible commit boundary",
    )
    check(
        calls == ["apply", "rollback"]
        and current == frozenset({"light.old", "camera.old"}),
        "a target-transaction provenance race restores the exact prior exposure",
    )
    check(
        manager.state.rollback_status == "complete",
        "the provenance-race rollback is recorded as complete",
    )
    check(
        validation_allowances
        == [frozenset({old.entry_id}), frozenset({old.entry_id})]
        and restore_allowances == [frozenset({old.entry_id})],
        "Initial, post-write, and rollback validation preserve the exact pending-prune runtime allowance",
    )
    return 4


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
        _hass: Any, _config: Any, plan: Any, _rooms: Any, **_kwargs: Any
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
        _hass: Any, _config: Any, plan: Any, _rooms: Any, **_kwargs: Any
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
    google_native_validations = 0
    google_request_syncs = 0
    google_native_failure = False
    google_request_failure = False
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

    async def validate_google_native(
        _hass: Any, expected: frozenset[str]
    ) -> dict[str, Any]:
        nonlocal google_native_validations
        google_native_validations += 1
        check(
            expected == current[const.TargetPlatform.GOOGLE],
            "Google no-op validation serializes the exact desired set",
        )
        if google_native_failure:
            raise RuntimeError("simulated Google native payload mismatch")
        return {"native_sync_payload_match": True}

    async def request_google_sync(_hass: Any) -> dict[str, Any]:
        nonlocal google_request_syncs
        google_request_syncs += 1
        if google_request_failure:
            raise RuntimeError("simulated Google Request Sync failure")
        return {
            "request_sync_accepted": True,
            "request_sync_http_status": 200,
        }

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
        manager_module._google_native_sync_payload_snapshot,
        manager_module._request_google_sync,
        manager_module.async_prepare_target,
        manager_module.async_apply_plan,
    )
    manager_module.async_read_source = read_source
    manager_module.async_find_apple_tv_entities = find_apple_tv
    manager_module.async_read_target = read_target
    manager_module.async_validate_target = validate_target
    manager_module.async_google_room_updates = no_room_updates
    manager_module._google_native_sync_payload_snapshot = validate_google_native
    manager_module._request_google_sync = request_google_sync
    manager_module.async_prepare_target = unexpected_prepare
    manager_module.async_apply_plan = unexpected_apply
    try:
        manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=TransactionBus()), transaction_config()
        )
        preview_result = await manager.async_reconcile(reason="preview", apply=False)
        check(
            preview_result["status"] == "preview"
            and manager.state.source_fingerprint is None
            and google_native_validations == 0,
            "A preview neither advances the applied source baseline nor runs the full Google serializer",
        )
        result = await manager.async_reconcile(
            reason="service_sync_now", apply=True
        )
        check(
            google_native_validations == 2
            and google_request_syncs == 1
            and result["plans"]["google"]["runtime"][
                "native_sync_payload_match"
            ]
            is True
            and result["plans"]["google"]["runtime"][
                "request_sync_accepted"
            ]
            is True,
            "A manual no-op validates, requests, and revalidates Google SYNC",
        )
        manager.state.source_fingerprint = None
        retry_result = await manager.async_reconcile(
            reason="retry_after_error", apply=True
        )
        check(
            google_native_validations == 3
            and google_request_syncs == 1
            and retry_result["plans"]["google"]["runtime"][
                "request_sync_reused_for_source"
            ]
            is True,
            "A later-target retry revalidates but does not resend Google Request Sync for the same source fingerprint",
        )
        await manager.async_reconcile(reason="target_health_audit", apply=True)
        check(
            google_native_validations == 3 and google_request_syncs == 1,
            "A stable 300-second health audit keeps Google validation lightweight",
        )

        request_failure_manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=TransactionBus()), transaction_config()
        )
        google_request_failure = True
        try:
            await request_failure_manager.async_reconcile(
                reason="service_sync_now", apply=True
            )
        except RuntimeError as error:
            check(
                "Request Sync failure" in str(error)
                and request_failure_manager._google_noop_request_sync_fingerprint
                is None,
                "A failed Google Request Sync is not cached as delivered",
            )
        else:
            raise AssertionError("A failed Google Request Sync must fail closed")
        google_request_failure = False
        request_retry = await request_failure_manager.async_reconcile(
            reason="retry_after_error", apply=True
        )
        check(
            google_request_syncs == 3
            and request_retry["plans"]["google"]["runtime"][
                "request_sync_reused_for_source"
            ]
            is False,
            "A failed Google Request Sync is sent again on the bounded retry",
        )

        failing_manager = manager_module.PlatformSyncManager(
            SimpleNamespace(bus=TransactionBus()), transaction_config()
        )
        google_native_failure = True
        try:
            await failing_manager.async_reconcile(
                reason="startup_scan", apply=True
            )
        except RuntimeError as error:
            check(
                "payload mismatch" in str(error),
                "A startup no-op fails closed on a native Google payload mismatch",
            )
        else:
            raise AssertionError(
                "A Google native payload mismatch must not report a no-op as synced"
            )
    finally:
        (
            manager_module.async_read_source,
            manager_module.async_find_apple_tv_entities,
            manager_module.async_read_target,
            manager_module.async_validate_target,
            manager_module.async_google_room_updates,
            manager_module._google_native_sync_payload_snapshot,
            manager_module._request_google_sync,
            manager_module.async_prepare_target,
            manager_module.async_apply_plan,
        ) = original_functions

    check(
        result["status"] == "synced" and result["changed"] is False,
        "An exact target set completes as a no-op sync",
    )
    check(
        reads == {platform: 7 for platform in platforms},
        "Each no-op reads every target once without post-apply readback",
    )
    check(
        validations == {platform: 7 for platform in platforms},
        "Each no-op validates every target exactly once",
    )
    check(
        prepare_calls == 0 and apply_calls == 0,
        "A no-op performs no prepare or apply operation",
    )
    return 13


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
            _hass: Any, _config: Any, plan: Any, _rooms: Any, **_kwargs: Any
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
        stopped = await asyncio.wait_for(stop_manager.async_stop(), timeout=0.2)
        check(
            stopped is False,
            "A stop deadline refuses to report a safely drained manager",
        )
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

    class RejectedStop:
        async def async_stop(self) -> bool:
            return False

    unloaded = await integration_module.async_unload_entry(
        SimpleNamespace(), SimpleNamespace(runtime_data=RejectedStop())
    )
    check(
        unloaded is False,
        "Config Entry unload remains loaded when manager drain is unverified",
    )
    manager_module._LOGGER.disabled = original_logger_disabled
    return 7


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
        error_stage="google_validate",
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
        and result["state"]["has_error"] is True
        and result["state"]["error_code"] == "sync_error"
        and result["state"]["error_stage"] == "google_validate",
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
    assertions += check_matter_recovery_guard()
    assertions += await check_matter_process_generation_barrier()
    assertions += await check_matter_manual_pairing_snapshot()
    assertions += await check_matter_removal_restart_and_rollback()
    assertions += await check_matter_apply_process_fallback()
    assertions += await check_matter_restart_cancellation_marker()
    assertions += await check_guarded_matter_runtime_recovery()
    assertions += await check_matter_source_runtime_validation()
    assertions += await check_dashboard_fresh_storage_and_camera_fields()
    assertions += await check_matter_request_overall_timeout()
    assertions += check_matter_endpoint_compatibility()
    assertions += await check_matter_save_barrier_and_uncertain_restart()
    assertions += await check_matter_backup_completion_handshake()
    assertions += await check_matter_restart_is_fire_and_forget()
    assertions += check_google_room_schema()
    assertions += await check_google_native_acceptance()
    assertions += await check_google_mutation_payload_guards()
    assertions += await check_google_executor_mutation_cancellation()
    assertions += await check_single_switch_runtime()
    assertions += await check_safe_migration()
    assertions += check_legacy_registry_cleanup()
    assertions += check_internal_timing_config()
    assertions += await check_source_watcher_policy()
    assertions += check_quick_reload_trigger()
    assertions += await check_dashboard_source_audit()
    assertions += await check_homekit_event_trigger_and_queue()
    assertions += await check_startup_race_and_safe_stop()
    assertions += await check_startup_listener_lifecycle()
    assertions += await check_background_readiness_retry()
    assertions += await check_retry_backoff_resets_after_success()
    assertions += check_source_events_preserve_fault_backoff()
    assertions += await check_matter_startup_recovery_grace()
    assertions += await check_matter_recovery_episode_and_cooldown()
    assertions += check_matter_transaction_restart_is_not_recovery_throttled()
    assertions += await check_matter_apply_restart_guard_across_reload()
    assertions += await check_config_entry_background_task_ownership()
    assertions += await check_permanent_error_retry_stop()
    assertions += check_homekit_selected_pairing_requirements()
    assertions += await check_homekit_prune_confirmation_identity()
    assertions += await check_homekit_lifecycle_progress_persistence()
    assertions += await check_homekit_restart_required_postcommit()
    assertions += await check_homekit_pending_prune_defers_accessory_creation()
    assertions += await check_homekit_restart_marker_startup_scope()
    assertions += await check_homekit_create_cancellation_persistence()
    assertions += await check_homekit_apple_tv_provenance_races()
    assertions += await check_homekit_apple_tv_target_transaction_race_rolls_back()
    assertions += await check_selected_target_exact_reconciliation()
    assertions += await check_manager_transaction()
    assertions += await check_noop_single_read_validation()
    assertions += await check_cancelled_transaction_rollback()
    assertions += await check_rollback_and_stop_deadlines()
    assertions += await check_diagnostics_privacy()
    print(f"PASS: {assertions} adapter and safety-gate acceptance assertions")


if __name__ == "__main__":
    asyncio.run(main())
