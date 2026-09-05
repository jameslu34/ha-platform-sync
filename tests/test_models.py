"""Dependency-light tests for pure synchronization rules."""

from simulate_adapter_acceptance import const, models

TargetPlatform = const.TargetPlatform
PlatformRule = models.PlatformRule
SourceSnapshot = models.SourceSnapshot
TargetPlan = models.TargetPlan
evaluate_target = models.evaluate_target
normalize_entities = models.normalize_entities


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


def test_every_source_kind_routes_to_every_target_with_exact_rules() -> None:
    """Exercise the complete 5-source by 3-target compatibility matrix."""
    for source_kind in const.SourceKind:
        for target in const.TargetPlatform:
            source_entity = f"light.from_{source_kind.value}"
            included = f"switch.include_{target.value}"
            excluded = f"sensor.exclude_{target.value}"
            plan = evaluate_target(
                frozenset({source_entity, excluded}),
                frozenset({excluded, f"light.stale_{target.value}"}),
                PlatformRule(
                    include=frozenset({included}),
                    exclude=frozenset({excluded}),
                ),
                PlatformRule(),
                target,
            )
            assert plan.desired == {source_entity, included}
            assert plan.added == {source_entity, included}
            assert plan.removed == {excluded, f"light.stale_{target.value}"}


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().copy().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} pure model tests, including 15 source-target routes")
