"""Validate the multi-step English and zh-Hant UI without HA dependencies."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from string import Formatter
from typing import Any


ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "platform_sync"
TRANSLATIONS = COMPONENT / "translations"

CONFIG_STEP_FIELDS = {
    "user": {"enabled", "source_kind"},
    "dashboard": {"source_page"},
    "dashboard_path": {"source_dashboard", "source_view"},
    "manual": {"source_entities"},
    "homekit_source": {"homekit_source_entry_ids"},
    "targets": {"target_platforms"},
    "platform_settings": {
        "google_config_path",
        "homekit_managed_entry_ids",
        "matter_host",
        "matter_port",
        "matter_password",
        "google_include",
        "google_exclude",
        "homekit_include",
        "homekit_exclude",
        "matter_include",
        "matter_exclude",
    },
    "confirm": set(),
}
OPTIONS_STEP_FIELDS = {
    "init": CONFIG_STEP_FIELDS["user"],
    **{key: value for key, value in CONFIG_STEP_FIELDS.items() if key != "user"},
}
FIRST_STEP_DATA_DESCRIPTIONS = {"enabled"}
EXPECTED_ERRORS = {
    "required",
    "dashboard_required",
    "dashboard_selection_conflict",
    "dashboard_not_found",
    "empty_source",
    "entity_required",
    "entity_not_found",
    "target_required",
    "invalid_target",
    "invalid_path",
    "homekit_entry_required",
    "homekit_target_entry_not_found",
    "homekit_target_configuration_invalid",
    "homekit_source_entry_required",
    "homekit_source_entry_not_found",
    "homekit_source_entry_unavailable",
    "homekit_source_filter_unsupported",
    "invalid_port",
    "invalid_matter_endpoint",
    "include_exclude_conflict",
    "protected_rule_conflict",
    "google_setup_required",
    "homekit_setup_required",
    "matter_setup_required",
    "platform_unavailable",
}
EXPECTED_SOURCE_LABELS = {
    "en": {
        "dashboard": "Devices on selected Home Assistant dashboard views",
        "manual": "Manually selected devices",
        "google": "Devices in Google Home",
        "homekit": "Devices in HomeKit",
        "matter": "Devices in Matterbridge",
    },
    "zh-Hant": {
        "dashboard": "Home Assistant 儀表板中的裝置",
        "manual": "手動選取的裝置",
        "google": "Google Home 中的裝置",
        "homekit": "HomeKit 中的裝置",
        "matter": "Matterbridge 中的裝置",
    },
}
EXPECTED_TARGET_LABELS = {
    "google": "Google Home",
    "homekit": "HomeKit",
    "matter": "Matterbridge",
}

EXPECTED_ENABLED_DESCRIPTION = {
    "en": "Enable cross-platform synchronization.",
    "zh-Hant": "啟用跨平台同步功能。",
}
FORBIDDEN_UI_TEXT = {
    "ha homekit",
    "profile_name",
    "profile name",
    "synchronization profile",
    "sync profile",
    "同步設定檔",
    "設定檔名稱",
    "auto_apply",
    "auto apply",
    "home_presence_protection",
    "home presence protection",
    "家庭在家狀態保護",
    "debounce_seconds",
    "poll_seconds",
    "變更合併等待時間",
    "來源輪詢間隔",
}


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys instead of silently taking the last one."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON document with duplicate-key detection."""
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def load_translation(language: str) -> dict[str, Any]:
    return load_json(TRANSLATIONS / f"{language}.json")


def flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            result.update(flatten(child, child_path))
        return result
    return {path: value}


def placeholders(value: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(value) if field}


def validate_steps(
    language: str,
    data: dict[str, Any],
    section: str,
    expected: dict[str, set[str]],
) -> None:
    """Validate the exact fields translated for every conditional step."""
    steps = data[section]["step"]
    assert set(steps) == set(expected), f"Unexpected {language}.{section} steps"
    for step_id, expected_fields in expected.items():
        node = steps[step_id]
        assert set(node.get("data", {})) == expected_fields, (
            f"Unexpected fields in {language}.{section}.{step_id}"
        )
        expected_descriptions = (
            FIRST_STEP_DATA_DESCRIPTIONS
            if step_id in {"user", "init"}
            else expected_fields
        )
        assert set(node.get("data_description", {})) == expected_descriptions, (
            f"Unexpected field descriptions in {language}.{section}.{step_id}"
        )
        if step_id in {"user", "init"}:
            assert "description" not in node, (
                f"Retired first-page description remains in "
                f"{language}.{section}.{step_id}"
            )


def validate_language(language: str, data: dict[str, Any]) -> None:
    """Validate one complete translation document."""
    assert set(data) == {"title", "config", "options", "selector", "services"}
    assert "entity" not in data
    validate_steps(language, data, "config", CONFIG_STEP_FIELDS)
    validate_steps(language, data, "options", OPTIONS_STEP_FIELDS)

    assert set(data["config"]["error"]) == EXPECTED_ERRORS
    assert set(data["options"]["error"]) == EXPECTED_ERRORS
    assert data["config"]["error"] == data["options"]["error"]
    assert data["selector"]["source_kind"]["options"] == EXPECTED_SOURCE_LABELS[
        language
    ]
    assert data["selector"]["target_platforms"]["options"] == EXPECTED_TARGET_LABELS
    assert set(data["services"]) == {"preview", "sync_now"}
    enabled_description = data["config"]["step"]["user"]["data_description"][
        "enabled"
    ]
    assert enabled_description == EXPECTED_ENABLED_DESCRIPTION[language]
    assert (
        data["options"]["step"]["init"]["data_description"]["enabled"]
        == enabled_description
    )

    for section in ("config", "options"):
        dashboard_step = data[section]["step"]["dashboard"]
        dashboard_copy = " ".join(
            (
                dashboard_step["title"],
                dashboard_step["description"],
                dashboard_step["data"]["source_page"],
                dashboard_step["data_description"]["source_page"],
            )
        )
        if language == "en":
            assert "views" in dashboard_copy.casefold()
            assert "one or more" in dashboard_copy.casefold()
        else:
            assert "儀表板" in dashboard_copy
            assert "一個或多個" in dashboard_copy

        homekit_source_step = data[section]["step"]["homekit_source"]
        homekit_source_copy = " ".join(
            (
                homekit_source_step["title"],
                homekit_source_step["description"],
                homekit_source_step["data"]["homekit_source_entry_ids"],
                homekit_source_step["data_description"][
                    "homekit_source_entry_ids"
                ],
            )
        )
        assert "HomeKit" in homekit_source_copy
        assert "Bridge" in homekit_source_copy
        assert "Accessory" in homekit_source_copy or "Accessories" in homekit_source_copy
        assert (
            "Apple Home" in homekit_source_copy
            or "Apple 家庭" in homekit_source_copy
        )
        if language == "en":
            assert "read" in homekit_source_copy.casefold()
            assert "does not grant permission to update" in homekit_source_copy
        else:
            assert "唯讀" in homekit_source_copy
            assert "不會因來源選擇取得更新" in homekit_source_copy

    platform_description = data["config"]["step"]["platform_settings"]["description"]
    assert placeholders(platform_description) == {"prerequisites"}
    assert (
        data["options"]["step"]["platform_settings"]["description"]
        == platform_description
    )
    google_description = data["config"]["step"]["platform_settings"][
        "data_description"
    ]["google_config_path"]
    assert "Google Assistant" in google_description
    assert "entity_config" in google_description
    assert "expose_by_default" in google_description
    assert "Home Assistant" in data["config"]["error"]["matter_setup_required"]

    for path, value in flatten(data).items():
        if not isinstance(value, str) or not value.strip():
            raise AssertionError(f"Missing translation text: {language}.{path}")
        if "[%key:" in value:
            raise AssertionError(
                f"Build-time reference is invalid for custom integrations: "
                f"{language}.{path}"
            )
        folded = value.casefold()
        for forbidden in FORBIDDEN_UI_TEXT:
            assert forbidden.casefold() not in folded, (
                f"Retired UI text remains in {language}.{path}: {forbidden}"
            )


def assigned_literal(tree: ast.Module, name: str) -> Any:
    """Return a module-level literal assignment by name."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"Missing assignment: {name}")


def main() -> None:
    if (COMPONENT / "strings.json").exists():
        raise AssertionError(
            "Custom integrations must use translations/en.json, not strings.json"
        )

    documents = {language: load_translation(language) for language in ("en", "zh-Hant")}
    flattened = {
        language: flatten(document) for language, document in documents.items()
    }
    assert set(flattened["en"]) == set(flattened["zh-Hant"])
    for path in flattened["en"]:
        assert placeholders(flattened["en"][path]) == placeholders(
            flattened["zh-Hant"][path]
        ), f"Placeholder mismatch at {path}"
    for language, document in documents.items():
        validate_language(language, document)

    assert documents["en"]["title"] == "Cross-Platform Device Sync"
    assert documents["zh-Hant"]["title"] == "裝置平台同步"
    for section, first_step in (("config", "user"), ("options", "init")):
        en_fields = documents["en"][section]["step"]["platform_settings"]["data"]
        zh_fields = documents["zh-Hant"][section]["step"]["platform_settings"]["data"]
        assert en_fields["homekit_include"] == "Always include in HomeKit"
        assert en_fields["homekit_exclude"] == "Exclude from HomeKit"
        assert (
            en_fields["homekit_managed_entry_ids"]
            == "Managed HomeKit target entries"
        )
        assert zh_fields["homekit_include"] == "HomeKit 額外加入"
        assert zh_fields["homekit_exclude"] == "HomeKit 排除"
        assert zh_fields["homekit_managed_entry_ids"] == "受管理的 HomeKit 目標項目"
        en_homekit_description = documents["en"][section]["step"][
            "platform_settings"
        ]["data_description"]["homekit_managed_entry_ids"]
        zh_homekit_description = documents["zh-Hant"][section]["step"][
            "platform_settings"
        ]["data_description"]["homekit_managed_entry_ids"]
        assert "fixed and read-only" in en_homekit_description
        assert "固定唯讀" in zh_homekit_description
        assert set(documents["en"][section]["step"][first_step]["data"]) == {
            "enabled",
            "source_kind",
        }
        en_target_description = documents["en"][section]["step"]["targets"][
            "description"
        ]
        zh_target_description = documents["zh-Hant"][section]["step"]["targets"][
            "description"
        ]
        en_confirm_description = documents["en"][section]["step"]["confirm"][
            "description"
        ]
        zh_confirm_description = documents["zh-Hant"][section]["step"]["confirm"][
            "description"
        ]
        assert "exact final set" in en_target_description
        assert "existing exposures" in en_target_description
        assert "精確最終清單" in zh_target_description
        assert "既有曝光會移除" in zh_target_description
        assert "unselected targets stay unchanged" in en_confirm_description
        assert "未勾選平台維持不變" in zh_confirm_description

    manifest = load_json(COMPONENT / "manifest.json")
    assert manifest["name"] == "Cross-Platform Device Sync"
    assert manifest["version"] == "0.6.5"

    config_source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    ast.parse(config_source)
    assert 'translation_key="source_kind"' in config_source
    assert 'translation_key="target_platforms"' in config_source
    assert "multiple=True" in config_source
    for retired_name in (
        "CONF_PROFILE_NAME",
        "CONF_AUTO_APPLY",
        "CONF_HOME_PRESENCE_PROTECTION",
        "CONF_DEBOUNCE_SECONDS",
        "CONF_POLL_SECONDS",
    ):
        assert retired_name not in config_source
    for required_hint in (
        "Google Assistant integration",
        "Google 帳戶連結",
        "dedicated entity configuration file",
        "專用裝置設定檔",
        "Home Assistant plugin",
        "Home Assistant 外掛",
    ):
        assert required_hint in config_source, f"Missing platform hint: {required_hint}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "HA HomeKit" not in readme

    const_source = (COMPONENT / "const.py").read_text(encoding="utf-8")
    const_tree = ast.parse(const_source)
    assert assigned_literal(const_tree, "PLATFORMS") == ()

    print(
        "PASS: multi-step English and zh-Hant UI, platform hints, retired fields, "
        "and zero entity platforms are exact"
    )


if __name__ == "__main__":
    main()
