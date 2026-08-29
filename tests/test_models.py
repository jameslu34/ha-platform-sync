"""Tests for pure synchronization rules."""

from custom_components.platform_sync.const import TargetPlatform
from custom_components.platform_sync.models import (
    PlatformRule,
    SourceSnapshot,
    TargetPlan,
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


def test_exact_plan_removes_target_extras_and_keeps_explicit_includes() -> None:
    plan = evaluate_target(
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
        PlatformRule(
            include=frozenset({"switch.user_included"}),
            exclude=frozenset(
                {"light.user_excluded", "input_boolean.locked_required"}
            ),
        ),
        PlatformRule(
            include=frozenset({"input_boolean.locked_required"}),
            exclude=frozenset({"input_boolean.locked_excluded"}),
        ),
        TargetPlatform.GOOGLE,
    )

    assert plan.desired == {
        "light.from_source",
        "switch.user_included",
        "input_boolean.locked_required",
    }
    assert plan.added == {"input_boolean.locked_required"}
    assert plan.removed == {
        "light.target_only",
        "light.user_excluded",
        "input_boolean.locked_excluded",
    }


def test_target_plan_rejects_an_incomplete_exact_delta() -> None:
    try:
        TargetPlan(
            platform=TargetPlatform.GOOGLE,
            desired=frozenset({"light.kept"}),
            current=frozenset({"light.kept", "light.target_only"}),
            added=frozenset(),
            removed=frozenset(),
        )
    except ValueError as error:
        assert "exactly match" in str(error)
    else:
        raise AssertionError("an exact plan must not omit target-only removals")


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
