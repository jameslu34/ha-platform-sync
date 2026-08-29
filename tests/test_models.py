"""Tests for pure synchronization rules."""

from custom_components.platform_sync.const import TargetPlatform
from custom_components.platform_sync.models import (
    PlatformRule,
    SourceSnapshot,
    evaluate_target,
    normalize_entities,
)


def test_normalize_entities_filters_invalid_values() -> None:
    assert normalize_entities(["light.one", "bad", "", 7, " switch.two "]) == {
        "light.one",
        "switch.two",
    }


def test_locked_rules_are_applied_last() -> None:
    plan = evaluate_target(
        frozenset({"switch.one", "switch.two"}),
        frozenset(),
        PlatformRule(
            include=frozenset({"input_boolean.shared"}),
            exclude=frozenset({"switch.two", "input_boolean.required"}),
        ),
        PlatformRule(
            include=frozenset({"input_boolean.required"}),
            exclude=frozenset({"switch.one", "input_boolean.shared"}),
        ),
        TargetPlatform.GOOGLE,
    )
    assert plan.desired == {"input_boolean.required"}


def test_dynamic_exclusion_cannot_be_readded_by_user() -> None:
    plan = evaluate_target(
        frozenset({"media_player.apple_tv"}),
        frozenset(),
        PlatformRule(include=frozenset({"media_player.apple_tv"})),
        PlatformRule(),
        TargetPlatform.HOMEKIT,
        dynamic_exclude=frozenset({"media_player.apple_tv"}),
    )
    assert plan.desired == set()


def test_locked_conflict_fails_closed() -> None:
    try:
        evaluate_target(
            frozenset(),
            frozenset(),
            PlatformRule(),
            PlatformRule(
                include=frozenset({"input_boolean.one"}),
                exclude=frozenset({"input_boolean.one"}),
            ),
            TargetPlatform.MATTER,
        )
    except ValueError as error:
        assert "input_boolean.one" in str(error)
    else:
        raise AssertionError("locked conflict must fail")


def test_source_fingerprint_tracks_room_and_order_independent_entities() -> None:
    first = SourceSnapshot(
        entities=frozenset({"light.one", "sensor.two"}),
        rooms={"light.one": "客廳", "sensor.two": "房間"},
        source_revision="one",
    )
    second = SourceSnapshot(
        entities=frozenset({"sensor.two", "light.one"}),
        rooms={"sensor.two": "房間", "light.one": "客廳"},
        source_revision="one",
    )
    assert first.fingerprint == second.fingerprint
