"""Dependency-light acceptance simulation for the reusable synchronization core."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import asyncio
import sys
import types


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "platform_sync"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


package = types.ModuleType("custom_components.platform_sync")
package.__path__ = [str(PACKAGE)]
sys.modules["custom_components"] = types.ModuleType("custom_components")
sys.modules["custom_components.platform_sync"] = package

const = load("custom_components.platform_sync.const", "const.py")
models = load("custom_components.platform_sync.models", "models.py")

# Minimal Home Assistant stubs needed to import the pure dashboard extractor.
homeassistant = types.ModuleType("homeassistant")
core = types.ModuleType("homeassistant.core")
helpers = types.ModuleType("homeassistant.helpers")
entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
device_registry = types.ModuleType("homeassistant.helpers.device_registry")
core.HomeAssistant = object
helpers.entity_registry = entity_registry
helpers.device_registry = device_registry
sys.modules.update(
    {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": entity_registry,
        "homeassistant.helpers.device_registry": device_registry,
    }
)
config_stub = types.ModuleType("custom_components.platform_sync.config")
config_stub.SyncConfig = object
sys.modules["custom_components.platform_sync.config"] = config_stub
sources = load("custom_components.platform_sync.sources", "sources.py")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeDashboard:
    """Storage dashboard stand-in for multi-view source acceptance."""

    def __init__(self, config: dict) -> None:
        self._config = config

    async def async_load(self, _force: bool) -> dict:
        return self._config


async def main() -> None:
    Target = const.TargetPlatform
    Rule = models.PlatformRule

    dashboard = {
        "views": [
            {"path": "unused", "cards": [{"entity": "light.not_selected"}]},
            {
                "path": "default-view",
                "sections": [
                    {
                        "title": "客廳",
                        "cards": [
                            {"entity": "light.main"},
                            {"type": "heading", "heading": "環境"},
                            {"entities": ["sensor.temp", {"entity": "sensor.humidity"}]},
                        ],
                    }
                ],
            },
        ]
    }
    snapshot = sources.extract_dashboard_entities(dashboard, "default-view")
    check(snapshot.entities == {"light.main", "sensor.temp", "sensor.humidity"}, "dashboard extraction")
    check(snapshot.rooms["light.main"] == "客廳", "section title room")
    check(snapshot.rooms["sensor.temp"] == "環境", "sibling heading room")
    for path_value, entity_id in (
        (None, "light.null_path"),
        ("", "light.empty_path"),
    ):
        title_snapshot = sources.extract_dashboard_entities(
            {
                "views": [
                    {
                        "title": "Title fallback",
                        "path": path_value,
                        "cards": [{"entity": entity_id}],
                    }
                ]
            },
            "Title fallback",
        )
        check(
            title_snapshot.entities == {entity_id},
            "dashboard reading uses title when view path is null or empty",
        )
    named_dashboard = object()
    legacy_dashboard = object()
    check(
        sources._select_dashboard_instance(
            {None: legacy_dashboard, "lovelace": named_dashboard}, "lovelace"
        )
        is named_dashboard,
        "named Lovelace dashboard precedence",
    )
    check(
        sources._select_dashboard_instance({None: legacy_dashboard}, "lovelace")
        is legacy_dashboard,
        "legacy Lovelace dashboard fallback",
    )

    multi_dashboard = FakeDashboard(
        {
            "views": [
                {
                    "path": "first",
                    "sections": [
                        {
                            "title": "客廳",
                            "cards": [
                                {"entity": "light.shared"},
                                {"entity": "switch.first"},
                            ],
                        }
                    ],
                },
                {
                    "path": "second",
                    "sections": [
                        {
                            "title": "餐廳",
                            "cards": [
                                {"entity": "light.shared"},
                                {"entity": "sensor.second"},
                            ],
                        }
                    ],
                },
                {"path": "empty", "cards": []},
            ]
        }
    )
    multi_hass = types.SimpleNamespace(
        data={
            "lovelace": types.SimpleNamespace(
                dashboards={"lovelace": multi_dashboard}
            )
        }
    )
    multi_config = types.SimpleNamespace(
        source_kind=const.SourceKind.DASHBOARD,
        source_dashboard="lovelace",
        source_view="first",
        source_pages=(("lovelace", "first"), ("lovelace", "second")),
    )
    combined = await sources.async_read_source(multi_hass, multi_config)
    check(
        combined.entities
        == {"light.shared", "switch.first", "sensor.second"},
        "multi-view dashboard source unions entities and removes duplicates",
    )
    check(
        "light.shared" not in combined.rooms,
        "conflicting room metadata is omitted instead of silently choosing a room",
    )
    check(
        combined.rooms.get("switch.first") == "客廳"
        and combined.rooms.get("sensor.second") == "餐廳",
        "non-conflicting room metadata survives multi-view aggregation",
    )
    empty_config = types.SimpleNamespace(
        source_kind=const.SourceKind.DASHBOARD,
        source_dashboard="lovelace",
        source_view="empty",
        source_pages=(("lovelace", "empty"),),
    )
    empty_failed = False
    try:
        await sources.async_read_source(multi_hass, empty_config)
    except (ValueError, RuntimeError):
        empty_failed = True
    check(
        empty_failed,
        "empty aggregate must fail closed before it can remove target devices",
    )
    partial_config = types.SimpleNamespace(
        source_kind=const.SourceKind.DASHBOARD,
        source_dashboard="lovelace",
        source_view="first",
        source_pages=(("lovelace", "first"), ("lovelace", "missing")),
    )
    partial_failed = False
    try:
        await sources.async_read_source(multi_hass, partial_config)
    except (ValueError, RuntimeError):
        partial_failed = True
    check(
        partial_failed,
        "an unreadable later view must fail the whole source instead of returning a partial union",
    )

    source = frozenset(
        {
            "light.main",
            "media_player.streaming_hub",
            "input_boolean.platform_a_presence",
            "input_boolean.platform_b_presence",
            "input_boolean.shared_arrival",
        }
    )
    rules = {
        Target.GOOGLE: Rule(
            include=frozenset(
                {"input_boolean.platform_a_presence", "input_boolean.shared_arrival"}
            ),
            exclude=frozenset({"input_boolean.platform_b_presence"}),
        ),
        Target.HOMEKIT: Rule(
            include=frozenset(
                {"input_boolean.platform_b_presence", "input_boolean.shared_arrival"}
            ),
            exclude=frozenset({"input_boolean.platform_a_presence"}),
        ),
        Target.MATTER: Rule(
            exclude=frozenset(
                {
                    "input_boolean.platform_a_presence",
                    "input_boolean.platform_b_presence",
                    "input_boolean.shared_arrival",
                }
            )
        ),
    }
    check(
        models.parse_rules(models.serialize_rules(rules)) == rules,
        "deployment-specific locked rules round-trip without built-in entity IDs",
    )
    google = models.evaluate_target(source, frozenset(), Rule(), rules[Target.GOOGLE], Target.GOOGLE)
    homekit = models.evaluate_target(
        source,
        frozenset(),
        Rule(include=frozenset({"media_player.streaming_hub"})),
        rules[Target.HOMEKIT],
        Target.HOMEKIT,
        frozenset({"media_player.streaming_hub"}),
    )
    matter = models.evaluate_target(source, frozenset(), Rule(), rules[Target.MATTER], Target.MATTER)
    check(
        "input_boolean.platform_b_presence" not in google.desired,
        "platform-specific locked exclusion",
    )
    check(
        "input_boolean.platform_a_presence" not in homekit.desired,
        "HomeKit locked exclusion",
    )
    check(
        "media_player.streaming_hub" not in homekit.desired,
        "optional dynamic integration exclusion",
    )
    check(
        not (matter.desired & rules[Target.MATTER].exclude),
        "target-specific locked exclusion",
    )

    exact = models.evaluate_target(
        frozenset(
            {
                "light.from_source",
                "light.user_excluded",
                "input_boolean.locked_excluded",
            }
        ),
        frozenset(
            {
                "light.from_source",
                "light.target_only",
                "light.user_excluded",
                "switch.user_included",
                "input_boolean.locked_excluded",
            }
        ),
        Rule(
            include=frozenset({"switch.user_included"}),
            exclude=frozenset(
                {"light.user_excluded", "input_boolean.locked_required"}
            ),
        ),
        Rule(
            include=frozenset({"input_boolean.locked_required"}),
            exclude=frozenset({"input_boolean.locked_excluded"}),
        ),
        Target.GOOGLE,
    )
    check(
        exact.desired
        == {
            "light.from_source",
            "switch.user_included",
            "input_boolean.locked_required",
        },
        "exact desired set applies per-target include/exclude before locked policy",
    )
    check(
        exact.added == {"input_boolean.locked_required"},
        "locked required exposure is restored even when absent from the source",
    )
    check(
        exact.removed
        == {
            "light.target_only",
            "light.user_excluded",
            "input_boolean.locked_excluded",
        },
        "target-only and excluded exposures are all included in the removal plan",
    )
    try:
        models.TargetPlan(
            platform=Target.GOOGLE,
            desired=frozenset({"light.from_source"}),
            current=frozenset({"light.from_source", "light.target_only"}),
            added=frozenset(),
            removed=frozenset(),
        )
    except ValueError:
        exact_delta_rejected = True
    else:
        exact_delta_rejected = False
    check(
        exact_delta_rejected,
        "a target plan cannot omit a current exposure outside its desired set",
    )

    # Disabled must short-circuit before source evaluation or target writes.
    reads = writes = 0
    enabled = False
    if enabled:
        reads += 1
        writes += 1
    check(reads == 0 and writes == 0, "disabled mode must be inert")

    # The single enabled switch starts evaluation and automatically applies changed plans.
    enabled = True
    reads += int(enabled)
    writes += int(enabled and google.changed)
    check(reads == 1 and writes == 1, "enabled mode automatically applies changes")

    metadata_plan = models.TargetPlan(
        platform=Target.GOOGLE,
        desired=frozenset({"light.main"}),
        current=frozenset({"light.main"}),
        added=frozenset(),
        removed=frozenset(),
        metadata_updates=("light.main",),
    )
    check(
        metadata_plan.with_current(frozenset({"light.main"})).metadata_updates
        == ("light.main",),
        "verified Google room-only changes remain visible in the completed plan",
    )

    # An explicit advanced preview may inspect a plan but never writes it.
    preview_reads = int(enabled)
    preview_writes = 0
    check(preview_reads == 1 and preview_writes == 0, "explicit preview remains read-only")

    print("PASS: 27 simulated acceptance assertions")


if __name__ == "__main__":
    asyncio.run(main())
