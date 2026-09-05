"""Dependency-light tests for native HomeKit accessory creation."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "custom_components" / "platform_sync" / "homekit_pairing.py"


def load_module() -> ModuleType:
    homeassistant = ModuleType("homeassistant")
    const = ModuleType("homeassistant.const")
    components = ModuleType("homeassistant.components")
    homekit = ModuleType("homeassistant.components.homekit")
    homekit_const = ModuleType("homeassistant.components.homekit.const")
    homekit_util = ModuleType("homeassistant.components.homekit.util")

    class EntityStateAttribute:
        FRIENDLY_NAME = "friendly_name"

    const.CONF_ENTITY_ID = "entity_id"
    const.CONF_PORT = "port"
    const.EntityStateAttribute = EntityStateAttribute
    homekit_const.DEFAULT_CONFIG_FLOW_PORT = 21063
    homekit_util.async_find_next_available_port = lambda _hass, port: port + 1
    homekit_util.state_needs_accessory_mode = (
        lambda state: state.entity_id.startswith(("camera.", "lock."))
    )
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.const": const,
            "homeassistant.components": components,
            "homeassistant.components.homekit": homekit,
            "homeassistant.components.homekit.const": homekit_const,
            "homeassistant.components.homekit.util": homekit_util,
        }
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.platform_sync.homekit_pairing", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pairing = load_module()


class FakeEntry:
    def __init__(
        self,
        entry_id: str,
        entity_id: str,
        *,
        port: int = 21064,
        source: str = "accessory",
        entity_filter=None,
    ) -> None:
        self.entry_id = entry_id
        self.domain = "homekit"
        self.source = source
        self.data = {
            "port": port,
            "homekit_mode": "accessory",
            "filter": entity_filter
            if entity_filter is not None
            else {
                "include_domains": [],
                "include_entities": [entity_id],
                "exclude_domains": [],
                "exclude_entities": [],
            },
        }
        self.options = {}
        self.runtime_data = None


class FakeConfigEntries:
    def __init__(self) -> None:
        self.entries: list[FakeEntry] = []
        self.flow = SimpleNamespace(async_init=self.async_init)
        self.result_type = "create_entry"
        self.raise_after_create = False
        self.pause_after_create: asyncio.Event | None = None
        self.created = asyncio.Event()
        self.concurrent_duplicate = False

    def async_entries(self, domain: str) -> list[FakeEntry]:
        return [entry for entry in self.entries if entry.domain == domain]

    def async_get_entry(self, entry_id: str):
        return next((entry for entry in self.entries if entry.entry_id == entry_id), None)

    async def async_init(self, _domain, *, context, data):
        assert context == {"source": "accessory"}
        assert isinstance(data["port"], int)
        entry = FakeEntry(f"created-{len(self.entries) + 1}", data["entity_id"])
        if self.result_type == "create_entry":
            self.entries.append(entry)
            if self.concurrent_duplicate:
                self.entries.append(
                    FakeEntry(
                        f"concurrent-{len(self.entries) + 1}",
                        data["entity_id"],
                        port=data["port"] + 1,
                    )
                )
            self.created.set()
            if self.pause_after_create is not None:
                await self.pause_after_create.wait()
            if self.raise_after_create:
                raise RuntimeError("flow failed after creating entry")
        return {"type": self.result_type, "result": entry}


class FakeHass:
    def __init__(self, entity_id: str = "camera.stairs") -> None:
        state = SimpleNamespace(
            entity_id=entity_id,
            attributes={"friendly_name": "九樓樓梯間攝影機"},
        )
        self.states = SimpleNamespace(get=lambda selected: state if selected == entity_id else None)
        self.config_entries = FakeConfigEntries()

    def async_create_task(self, coroutine, **_kwargs):
        return asyncio.create_task(coroutine)


class HomeKitPairingTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_exact_native_accessory_and_requirement(self) -> None:
        hass = FakeHass()
        entry, requirement = await pairing.async_create_homekit_accessory(
            hass, "camera.stairs"
        )
        self.assertEqual(
            pairing.homekit_entry_entities(entry), frozenset({"camera.stairs"})
        )
        self.assertEqual(requirement.device_name, "九樓樓梯間攝影機")
        self.assertEqual(requirement.platform, "HomeKit")
        self.assertNotIn("pin", requirement.as_dict())

    async def test_never_implicitly_adopts_existing_accessory(self) -> None:
        hass = FakeHass()
        hass.config_entries.entries.append(FakeEntry("manual", "camera.stairs"))
        with self.assertRaises(pairing.HomeKitAccessoryCreateError):
            await pairing.async_create_homekit_accessory(hass, "camera.stairs")
        self.assertEqual(len(hass.config_entries.entries), 1)

    async def test_flow_must_create_entry(self) -> None:
        hass = FakeHass()
        hass.config_entries.result_type = "abort"
        with self.assertRaises(pairing.HomeKitAccessoryCreateError):
            await pairing.async_create_homekit_accessory(hass, "camera.stairs")

    async def test_raise_after_create_reports_owned_entry(self) -> None:
        hass = FakeHass()
        hass.config_entries.raise_after_create = True
        with self.assertRaises(pairing.HomeKitAccessoryCreateError) as raised:
            await pairing.async_create_homekit_accessory(hass, "camera.stairs")
        self.assertEqual(raised.exception.created_entry_id, "created-1")

    async def test_cancel_after_create_drains_and_reports_owned_entry(self) -> None:
        hass = FakeHass()
        release = asyncio.Event()
        hass.config_entries.pause_after_create = release
        create_task = asyncio.create_task(
            pairing.async_create_homekit_accessory(hass, "camera.stairs")
        )
        await hass.config_entries.created.wait()
        create_task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(create_task.done())
        release.set()
        with self.assertRaises(
            pairing.HomeKitAccessoryCreateCancelled
        ) as cancelled:
            await create_task
        self.assertEqual(cancelled.exception.created_entry_id, "created-1")
        self.assertEqual(len(hass.config_entries.entries), 1)

    async def test_broad_legacy_bridge_fails_closed(self) -> None:
        hass = FakeHass()
        hass.config_entries.entries.append(
            FakeEntry(
                "legacy-bridge",
                "light.unrelated",
                source="user",
                entity_filter={
                    "include_domains": ["camera"],
                    "include_entities": [],
                },
            )
        )
        with self.assertRaises(pairing.HomeKitAccessoryCreateError) as raised:
            await pairing.async_create_homekit_accessory(hass, "camera.stairs")
        self.assertIn("broad", str(raised.exception))
        self.assertEqual(len(hass.config_entries.entries), 1)

    async def test_concurrent_duplicate_is_detected_and_owned_entry_reported(self) -> None:
        hass = FakeHass()
        hass.config_entries.concurrent_duplicate = True
        with self.assertRaises(pairing.HomeKitAccessoryCreateError) as raised:
            await pairing.async_create_homekit_accessory(hass, "camera.stairs")
        self.assertEqual(raised.exception.created_entry_id, "created-1")
        self.assertEqual(len(hass.config_entries.entries), 2)

    async def test_non_accessory_entity_is_rejected(self) -> None:
        hass = FakeHass("light.desk")
        with self.assertRaises(pairing.HomeKitAccessoryCreateError):
            await pairing.async_create_homekit_accessory(hass, "light.desk")

    def test_pairing_state_is_privacy_preserving(self) -> None:
        entry = FakeEntry("one", "lock.front")
        entry.runtime_data = SimpleNamespace(
            homekit=SimpleNamespace(
                driver=SimpleNamespace(
                    state=SimpleNamespace(paired_clients={"controller-secret": object()})
                )
            )
        )
        self.assertIs(pairing.homekit_entry_is_paired(entry), True)
        markdown = pairing.pairing_requirements_markdown(
            [
                pairing.ManualPairingRequirement(
                    platform="HomeKit",
                    entity_id="lock.front",
                    device_name="Front lock",
                    action="pair",
                )
            ],
            zh_hant=False,
        )
        self.assertNotIn("controller-secret", markdown)


if __name__ == "__main__":
    unittest.main()
