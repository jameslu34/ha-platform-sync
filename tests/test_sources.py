"""Tests for Lovelace source extraction."""

import asyncio
from types import SimpleNamespace

from custom_components.platform_sync.const import SourceKind
from custom_components.platform_sync.sources import (
    _select_dashboard_instance,
    async_read_source,
    extract_dashboard_entities,
)


def test_extract_selected_view_and_nested_entities() -> None:
    result = extract_dashboard_entities(
        {
            "views": [
                {"path": "other", "cards": [{"entity": "light.skip"}]},
                {
                    "path": "default-view",
                    "sections": [
                        {
                            "type": "heading",
                            "heading": "客廳",
                            "cards": [
                                {"entity": "light.main"},
                                {"entities": ["switch.fan", {"entity": "sensor.temp"}]},
                            ],
                        }
                    ],
                },
            ]
        },
        "default-view",
    )
    assert result.entities == {"light.main", "switch.fan", "sensor.temp"}
    assert "light.skip" not in result.entities
    assert result.rooms["switch.fan"] == "客廳"


def test_named_lovelace_dashboard_precedes_legacy_default() -> None:
    named = object()
    legacy = object()
    assert (
        _select_dashboard_instance({None: legacy, "lovelace": named}, "lovelace")
        is named
    )


def test_legacy_default_remains_supported() -> None:
    legacy = object()
    assert _select_dashboard_instance({None: legacy}, "lovelace") is legacy


def test_view_title_is_used_when_path_is_null_or_empty() -> None:
    for path_value, entity_id in (
        (None, "light.null_path"),
        ("", "light.empty_path"),
    ):
        result = extract_dashboard_entities(
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
        assert result.entities == {entity_id}


class _Dashboard:
    def __init__(self, config: dict) -> None:
        self._config = config

    async def async_load(self, _force: bool) -> dict:
        return self._config


def test_multiple_dashboard_views_union_and_drop_conflicting_room() -> None:
    dashboard = _Dashboard(
        {
            "views": [
                {
                    "path": "one",
                    "sections": [
                        {
                            "title": "客廳",
                            "cards": [
                                {"entity": "light.shared"},
                                {"entity": "switch.one"},
                            ],
                        }
                    ],
                },
                {
                    "path": "two",
                    "sections": [
                        {
                            "title": "餐廳",
                            "cards": [
                                {"entity": "light.shared"},
                                {"entity": "sensor.two"},
                            ],
                        }
                    ],
                },
            ]
        }
    )
    hass = SimpleNamespace(
        data={"lovelace": SimpleNamespace(dashboards={"lovelace": dashboard})}
    )
    config = SimpleNamespace(
        source_kind=SourceKind.DASHBOARD,
        source_dashboard="lovelace",
        source_view="one",
        source_pages=(("lovelace", "one"), ("lovelace", "two")),
    )

    result = asyncio.run(async_read_source(hass, config))

    assert result.entities == {"light.shared", "switch.one", "sensor.two"}
    assert "light.shared" not in result.rooms
    assert result.rooms == {"switch.one": "客廳", "sensor.two": "餐廳"}


def test_multiple_dashboard_views_empty_aggregate_fails_closed() -> None:
    dashboard = _Dashboard({"views": [{"path": "empty", "cards": []}]})
    hass = SimpleNamespace(
        data={"lovelace": SimpleNamespace(dashboards={"lovelace": dashboard})}
    )
    config = SimpleNamespace(
        source_kind=SourceKind.DASHBOARD,
        source_dashboard="lovelace",
        source_view="empty",
        source_pages=(("lovelace", "empty"),),
    )

    try:
        asyncio.run(async_read_source(hass, config))
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("empty multi-view source must fail closed")
