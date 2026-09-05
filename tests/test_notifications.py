"""Dependency-light tests for Platform Sync's native-only notifications."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "platform_sync"
MODULE_PATH = COMPONENT / "notifications.py"


def load_module() -> ModuleType:
    """Load the gateway without requiring a Home Assistant installation."""
    spec = importlib.util.spec_from_file_location(
        "custom_components.platform_sync.notifications_test", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


notifications = load_module()


class NotificationGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.created: list[tuple[object, str, str, str]] = []
        self.dismissed: list[tuple[object, str]] = []
        self.backend = SimpleNamespace(
            async_create=lambda hass, message, *, title, notification_id: (
                self.created.append((hass, message, title, notification_id))
            ),
            async_dismiss=lambda hass, notification_id: (
                self.dismissed.append((hass, notification_id))
            ),
        )
        self.original_backend = notifications._persistent_notification_backend
        notifications._persistent_notification_backend = lambda: self.backend

    def tearDown(self) -> None:
        notifications._persistent_notification_backend = self.original_backend

    def test_create_uses_exact_native_persistent_notification_backend(self) -> None:
        hass = object()
        result = notifications.async_create_native_notification(
            hass,
            "Pair this accessory in Apple Home.",
            title="Platform Sync",
            notification_id="platform_sync_entry_manual_pairing",
        )
        self.assertIs(result, True)
        self.assertEqual(
            self.created,
            [
                (
                    hass,
                    "Pair this accessory in Apple Home.",
                    "Platform Sync",
                    "platform_sync_entry_manual_pairing",
                )
            ],
        )
        self.assertEqual(self.dismissed, [])

    def test_dismiss_uses_exact_native_persistent_notification_backend(self) -> None:
        hass = object()
        result = notifications.async_dismiss_native_notification(
            hass, "platform_sync_entry_manual_pairing"
        )
        self.assertIs(result, True)
        self.assertEqual(
            self.dismissed,
            [(hass, "platform_sync_entry_manual_pairing")],
        )
        self.assertEqual(self.created, [])

    def test_unavailable_native_backend_fails_closed_without_fallback(self) -> None:
        def unavailable() -> ModuleType:
            raise ImportError("persistent_notification unavailable")

        notifications._persistent_notification_backend = unavailable
        with self.assertLogs(notifications._LOGGER, level="WARNING"):
            created = notifications.async_create_native_notification(
                object(),
                "message",
                title="title",
                notification_id="platform_sync_entry_test",
            )
            dismissed = notifications.async_dismiss_native_notification(
                object(), "platform_sync_entry_test"
            )
        self.assertIs(created, False)
        self.assertIs(dismissed, False)
        self.assertEqual(self.created, [])
        self.assertEqual(self.dismissed, [])

    def test_gateway_has_no_external_or_dashboard_delivery_surface(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        tree = ast.parse(source)
        called_surfaces = {
            ast.unparse(node.func).lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        imported_modules = {
            node.module.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        for forbidden in (
            "hass.services",
            "hass.bus",
            "mobile_app",
            "webhook",
            "family-summary",
            "family_summary",
            "lovelace",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in surface for surface in called_surfaces)
                )
                self.assertFalse(
                    any(forbidden in module for module in imported_modules)
                )

    def test_component_contains_no_forbidden_user_notification_target(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in sorted(COMPONENT.glob("*.py"))
        )
        for forbidden in (
            "notify.mobile_app",
            "notify/",
            "family-summary",
            "family_summary",
            "script.unknown",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

        manager_source = (COMPONENT / "manager.py").read_text(encoding="utf-8")
        self.assertNotIn("persistent_notification.async_create", manager_source)
        self.assertNotIn("persistent_notification.async_dismiss", manager_source)
        self.assertIn("async_create_native_notification", manager_source)
        self.assertIn("async_dismiss_native_notification", manager_source)


if __name__ == "__main__":
    unittest.main()
