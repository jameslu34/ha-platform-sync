"""Pure synchronization models and rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping

from .const import TargetPlatform


def normalize_entities(values: object) -> frozenset[str]:
    """Return valid, normalized entity identifiers."""
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        value.strip()
        for value in values
        if isinstance(value, str)
        and value.strip()
        and "." in value
        and " " not in value
    )


@dataclass(frozen=True, slots=True)
class PlatformRule:
    """Additional include/exclude rules for one platform."""

    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, value: object) -> "PlatformRule":
        """Parse one rule from stored configuration."""
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            include=normalize_entities(value.get("include")),
            exclude=normalize_entities(value.get("exclude")),
        )


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Entities and room hints read from one source."""

    entities: frozenset[str]
    rooms: Mapping[str, str] = field(default_factory=dict)
    source_revision: str = ""

    @property
    def fingerprint(self) -> str:
        """Return a stable source fingerprint."""
        payload = {
            "entities": sorted(self.entities),
            "rooms": sorted(
                (entity_id, room)
                for entity_id, room in self.rooms.items()
                if entity_id in self.entities and room
            ),
            "source_revision": self.source_revision,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class TargetPlan:
    """Exact desired set and delta for one target."""

    platform: TargetPlatform
    desired: frozenset[str]
    current: frozenset[str]
    added: frozenset[str]
    removed: frozenset[str]
    metadata_updates: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Return whether applying the plan changes the target."""
        return bool(self.added or self.removed or self.metadata_updates)

    def with_current(self, current: frozenset[str]) -> "TargetPlan":
        """Return a post-apply plan whose delta reflects verified readback."""
        return TargetPlan(
            platform=self.platform,
            desired=self.desired,
            current=current,
            added=self.desired - current,
            removed=current - self.desired,
            metadata_updates=self.metadata_updates,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics-safe data."""
        return {
            "platform": self.platform.value,
            "expected": len(self.desired),
            "actual": len(self.current),
            "added": sorted(self.added),
            "removed": sorted(self.removed),
            "missing": sorted(self.desired - self.current),
            "extra": sorted(self.current - self.desired),
            "metadata_updates": list(self.metadata_updates),
            "changed": self.changed,
        }


def evaluate_target(
    source_entities: frozenset[str],
    current_entities: frozenset[str],
    user_rule: PlatformRule,
    locked_rule: PlatformRule,
    platform: TargetPlatform,
    dynamic_exclude: frozenset[str] = frozenset(),
) -> TargetPlan:
    """Apply normal rules, then non-overridable locked policy rules."""
    locked_exclude = locked_rule.exclude | dynamic_exclude
    conflict = locked_rule.include & locked_exclude
    if conflict:
        names = ", ".join(sorted(conflict))
        raise ValueError(f"Locked include/exclude conflict: {names}")

    desired = (source_entities - user_rule.exclude) | user_rule.include
    desired = (desired - locked_exclude) | locked_rule.include
    desired = frozenset(desired)
    return TargetPlan(
        platform=platform,
        desired=desired,
        current=current_entities,
        added=desired - current_entities,
        removed=current_entities - desired,
    )


def parse_rules(
    value: object,
) -> dict[TargetPlatform, PlatformRule]:
    """Parse rules for all targets."""
    mapping = value if isinstance(value, Mapping) else {}
    return {
        platform: PlatformRule.from_mapping(mapping.get(platform.value))
        for platform in TargetPlatform
    }


def serialize_rules(
    rules: Mapping[TargetPlatform, PlatformRule],
) -> dict[str, dict[str, list[str]]]:
    """Serialize rules for config entries."""
    return {
        platform.value: {
            "include": sorted(rule.include),
            "exclude": sorted(rule.exclude),
        }
        for platform, rule in rules.items()
    }
