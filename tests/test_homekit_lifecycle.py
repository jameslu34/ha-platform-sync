"""Dependency-light tests for owned HomeKit accessory lifecycle helpers."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any
import unittest


ROOT = Path(__file__).parents[1]
MODULE_PATH = (
    ROOT
    / "custom_components"
    / "platform_sync"
    / "homekit_lifecycle.py"
)
SPEC = importlib.util.spec_from_file_location(
    "platform_sync_homekit_lifecycle_tested", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
lifecycle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lifecycle
SPEC.loader.exec_module(lifecycle)


def exact_filter(entity_id: str) -> dict[str, Any]:
    """Return the explicit exact filter required by the lifecycle module."""
    return {
        "filter": {
            "include_entities": [entity_id],
            "include_domains": [],
            "include_entity_globs": [],
            "exclude_entities": [],
            "exclude_domains": [],
            "exclude_entity_globs": [],
        },
        "homekit_mode": "accessory",
    }


class FakeEntry:
    """Small mutable Home Assistant Config Entry stand-in."""

    def __init__(
        self,
        entry_id: str,
        entity_id: str,
        *,
        mode: str = "accessory",
        source: str = "user",
        domain: str = "homekit",
        name: str | None = None,
        title: str | None = None,
        port: int = 21064,
        multiple: bool = False,
        filter_in_data: bool | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.domain = domain
        self.source = source
        effective = exact_filter(entity_id)
        effective["homekit_mode"] = mode
        if multiple:
            effective["filter"]["include_entities"].append("light.second")
        if filter_in_data is None:
            filter_in_data = source == "import"
        self.options = {} if filter_in_data else effective
        self.data = {"name": entry_id if name is None else name, "port": port}
        self.title = entry_id if title is None else title
        if filter_in_data:
            self.data.update(effective)


class FakeConfig:
    """Resolve Home Assistant config paths below a temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class FakeConfigEntries:
    """Config Entry registry with an overridable async removal hook."""

    def __init__(self, entries: list[FakeEntry]) -> None:
        self.entries = {entry.entry_id: entry for entry in entries}
        self.remove_calls: list[str] = []

    def async_get_entry(self, entry_id: str) -> FakeEntry | None:
        return self.entries.get(entry_id)

    async def async_remove(self, entry_id: str) -> dict[str, bool]:
        self.remove_calls.append(entry_id)
        self.entries.pop(entry_id)
        return {"require_restart": False}


class FakeHass:
    """Minimal Home Assistant surface used by the lifecycle helpers."""

    def __init__(self, root: Path, entries: FakeConfigEntries) -> None:
        self.config = FakeConfig(root)
        self.config_entries = entries

    async def async_add_executor_job(self, target: Any, *args: Any) -> Any:
        return target(*args)


def plan(
    entries: list[FakeEntry],
    *,
    owned: list[str],
    prunable: list[str],
    desired: set[str] | None = None,
    sources: list[str] | None = None,
    yaml_paths: dict[str, str] | None = None,
) -> tuple[Any, ...]:
    """Plan with a stable main Bridge and all supplied side entries managed."""
    main = FakeEntry(
        "main",
        "light.main",
        mode="bridge",
        name="Main Bridge",
        port=21063,
    )
    return lifecycle.plan_homekit_accessory_prunes(
        [main, *entries],
        managed_entry_ids=["main", *(entry.entry_id for entry in entries)],
        main_entry_id="main",
        homekit_source_entry_ids=sources or [],
        owned_entry_ids=owned,
        prunable_entry_ids=prunable,
        logical_desired=desired or set(),
        import_yaml_paths=yaml_paths,
    )


class CandidatePlanningTests(unittest.TestCase):
    """Prove that only explicitly owned dedicated side entries can be planned."""

    def test_retains_desired_and_unlisted_side_entries(self) -> None:
        removable = FakeEntry("owned-lock", "lock.front", port=21064)
        retained = FakeEntry("owned-camera", "camera.driveway", port=21065)
        manual = FakeEntry("manual-tv", "media_player.tv", port=21066)

        candidates = plan(
            [removable, retained, manual],
            owned=["owned-lock", "owned-camera"],
            prunable=["owned-lock", "owned-camera"],
            desired={"camera.driveway"},
        )

        self.assertEqual([item.entry_id for item in candidates], ["owned-lock"])
        self.assertEqual(candidates[0].entity_id, "lock.front")

    def test_rejects_unowned_main_source_and_multi_entity(self) -> None:
        side = FakeEntry("side", "camera.side", port=21064)
        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            plan([side], owned=[], prunable=["side"])

        main = FakeEntry(
            "main",
            "light.main",
            mode="bridge",
            name="Main Bridge",
            port=21063,
        )
        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            lifecycle.plan_homekit_accessory_prunes(
                [main],
                managed_entry_ids=["main"],
                main_entry_id="main",
                homekit_source_entry_ids=[],
                owned_entry_ids=["main"],
                prunable_entry_ids=["main"],
                logical_desired=set(),
            )

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            lifecycle.plan_homekit_accessory_prunes(
                [main, side],
                managed_entry_ids=["main", "side"],
                main_entry_id="not-the-live-main",
                homekit_source_entry_ids=[],
                owned_entry_ids=["side"],
                prunable_entry_ids=["side"],
                logical_desired=set(),
            )

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            plan(
                [side],
                owned=["side"],
                prunable=["side"],
                sources=["side"],
            )

        bridge_side = FakeEntry(
            "bridge-side", "camera.side", mode="bridge", port=21065
        )
        bridge_candidates = plan(
            [bridge_side],
            owned=["bridge-side"],
            prunable=["bridge-side"],
        )
        self.assertEqual(
            [(item.entry_id, item.mode) for item in bridge_candidates],
            [("bridge-side", "bridge")],
        )

        multi = FakeEntry("multi", "camera.one", multiple=True, port=21066)
        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            plan([multi], owned=["multi"], prunable=["multi"])

    def test_import_requires_safe_relative_yaml_path(self) -> None:
        imported = FakeEntry(
            "imported", "camera.imported", source="import", port=21064
        )
        for unsafe in (
            None,
            "../configuration.yaml",
            "configuration.yaml",
            "nested/configuration.yml",
            "/config/homekit.yaml",
            "C:\\x.yaml",
            "C:drive-relative.yaml",
        ):
            paths = {} if unsafe is None else {"imported": unsafe}
            with self.assertRaises(lifecycle.HomeKitLifecycleError):
                plan(
                    [imported],
                    owned=["imported"],
                    prunable=["imported"],
                    yaml_paths=paths,
                )

    def test_rejects_invalid_logical_desired_set_before_planning(self) -> None:
        side = FakeEntry("side", "camera.side", port=21064)
        for desired in (["camera.side"], {" camera.side"}, {"not-an-entity"}):
            with self.assertRaises(lifecycle.HomeKitLifecycleError):
                plan(
                    [side],
                    owned=["side"],
                    prunable=["side"],
                    desired=desired,  # type: ignore[arg-type]
                )

    def test_null_competing_live_filter_fails_closed(self) -> None:
        side = FakeEntry("side", "camera.side", mode="bridge", port=21064)
        side.options["filter"]["exclude_domains"] = None

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            plan([side], owned=["side"], prunable=["side"])

    def test_ui_entry_uses_only_exact_title_name_fallback(self) -> None:
        for data_name in ("", " ", " Camera from data"):
            with self.subTest(data_name=data_name):
                side = FakeEntry(
                    "side",
                    "camera.side",
                    name=data_name,
                    title="九樓樓梯間攝影機:21064",
                    port=21064,
                )
                candidates = plan([side], owned=["side"], prunable=["side"])
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].name, "九樓樓梯間攝影機")
                self.assertEqual(candidates[0].port, 21064)

    def test_imported_entry_never_uses_title_name_fallback(self) -> None:
        for data_name in ("", " Imported Camera"):
            with self.subTest(data_name=data_name):
                imported = FakeEntry(
                    "imported",
                    "camera.imported",
                    source="import",
                    name=data_name,
                    title="Imported Camera:21064",
                    port=21064,
                )
                with self.assertRaises(lifecycle.HomeKitLifecycleError):
                    plan(
                        [imported],
                        owned=["imported"],
                        prunable=["imported"],
                        yaml_paths={"imported": "homekit.yaml"},
                    )

    def test_ui_title_fallback_rejects_noncanonical_identity(self) -> None:
        for title in (
            "Camera",
            "Camera:21065",
            "Camera:021064",
            ":21064",
            " Camera:21064",
            "Camera :21064",
        ):
            with self.subTest(title=title):
                side = FakeEntry(
                    "side",
                    "camera.side",
                    name="",
                    title=title,
                    port=21064,
                )
                with self.assertRaises(lifecycle.HomeKitLifecycleError):
                    plan([side], owned=["side"], prunable=["side"])


class LifecycleExecutionTests(unittest.IsolatedAsyncioTestCase):
    """Verify deletion, YAML durability, cancellation, and retry behavior."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self._old_modules = {
            name: sys.modules.get(name)
            for name in (
                "homeassistant",
                "homeassistant.util",
                "homeassistant.util.yaml",
            )
        }
        homeassistant = ModuleType("homeassistant")
        util = ModuleType("homeassistant.util")
        yaml_module = ModuleType("homeassistant.util.yaml")
        self.yaml_save_calls: list[str] = []

        def load_yaml(path: str) -> Any:
            return json.loads(Path(path).read_text(encoding="utf-8"))

        def save_yaml(path: str, data: Any) -> None:
            self.yaml_save_calls.append(path)
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

        yaml_module.load_yaml = load_yaml
        yaml_module.save_yaml = save_yaml
        util.yaml = yaml_module
        homeassistant.util = util
        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.util"] = util
        sys.modules["homeassistant.util.yaml"] = yaml_module

    async def asyncTearDown(self) -> None:
        for name, module in self._old_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        self.temp_dir.cleanup()

    async def test_removes_only_planned_ui_singleton_side_entry(self) -> None:
        removable = FakeEntry(
            "owned-lock", "lock.front", mode="bridge", port=21064
        )
        removable.options["mode"] = removable.options.pop("homekit_mode")
        manual = FakeEntry("manual-camera", "camera.manual", port=21065)
        candidates = plan(
            [removable, manual],
            owned=["owned-lock"],
            prunable=["owned-lock"],
        )
        entries = FakeConfigEntries([removable, manual])
        hass = FakeHass(self.root, entries)

        result = await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates,
            owned_entry_ids=["owned-lock"],
            prunable_entry_ids=["owned-lock"],
        )

        self.assertEqual(result.removed_entry_ids, {"owned-lock"})
        self.assertEqual(result.removed_entities, {"lock.front"})
        self.assertEqual(entries.remove_calls, ["owned-lock"])
        self.assertIs(entries.async_get_entry("manual-camera"), manual)

    async def test_ui_title_or_port_identity_race_prevents_removal(self) -> None:
        for mutation in ("title", "port"):
            with self.subTest(mutation=mutation):
                accessory = FakeEntry(
                    "owned-camera",
                    "camera.front",
                    name="",
                    title="Front Camera:21064",
                    port=21064,
                )
                candidates = plan(
                    [accessory],
                    owned=["owned-camera"],
                    prunable=["owned-camera"],
                )
                if mutation == "title":
                    accessory.title = "Changed Camera:21064"
                else:
                    accessory.data["port"] = 21065
                entries = FakeConfigEntries([accessory])
                hass = FakeHass(self.root, entries)

                with self.assertRaises(lifecycle.HomeKitLifecycleError):
                    await lifecycle.async_remove_homekit_accessory_candidates(
                        hass,
                        candidates,
                        owned_entry_ids=["owned-camera"],
                        prunable_entry_ids=["owned-camera"],
                    )

                self.assertEqual(entries.remove_calls, [])
                self.assertIs(entries.async_get_entry("owned-camera"), accessory)

    async def test_absence_without_normal_remove_return_is_uncertain(self) -> None:
        accessory = FakeEntry("owned-camera", "camera.front", port=21064)
        candidates = plan(
            [accessory],
            owned=["owned-camera"],
            prunable=["owned-camera"],
        )
        entries = FakeConfigEntries([])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["owned-camera"],
                prunable_entry_ids=["owned-camera"],
            )

        self.assertEqual(raised.exception.removed_entry_ids, set())
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"owned-camera"}
        )
        self.assertEqual(entries.remove_calls, [])

    async def test_normal_remove_return_without_absence_is_uncertain(self) -> None:
        accessory = FakeEntry("owned-camera", "camera.front", port=21064)
        candidates = plan(
            [accessory],
            owned=["owned-camera"],
            prunable=["owned-camera"],
        )

        class NonRemovingConfigEntries(FakeConfigEntries):
            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                return {"require_restart": True}

        entries = NonRemovingConfigEntries([accessory])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["owned-camera"],
                prunable_entry_ids=["owned-camera"],
            )

        self.assertEqual(raised.exception.removed_entry_ids, set())
        self.assertEqual(
            raised.exception.restart_required_entry_ids, {"owned-camera"}
        )
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"owned-camera"}
        )
        self.assertEqual(entries.remove_calls, ["owned-camera"])

    async def test_import_yaml_is_backed_up_per_candidate_and_read_back(self) -> None:
        imported_camera = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        imported_lock = FakeEntry(
            "imported-lock",
            "lock.imported",
            source="import",
            name="Imported Lock",
            port=22002,
        )
        candidates = plan(
            [imported_camera, imported_lock],
            owned=["imported-camera", "imported-lock"],
            prunable=["imported-camera", "imported-lock"],
            yaml_paths={
                "imported-camera": "includes/homekit.yaml",
                "imported-lock": "includes/homekit.yaml",
            },
        )
        yaml_path = self.root / "includes" / "homekit.yaml"
        yaml_path.parent.mkdir(parents=True)
        original = [
            {
                "name": "Imported Camera",
                "port": 22001,
                "mode": "accessory",
                "filter": {
                    "include_entities": ["camera.imported"],
                    "include_domains": [],
                },
            },
            {
                "name": "Imported Lock",
                "port": 22002,
                "mode": "accessory",
                "filter": {"include_entities": ["lock.imported"]},
            },
            {
                "name": "Keep Bridge",
                "port": 22003,
                "mode": "bridge",
                "filter": {"include_entities": ["light.keep"]},
            },
        ]
        original_bytes = json.dumps(original, ensure_ascii=False).encode("utf-8")
        yaml_path.write_bytes(original_bytes)
        entries = FakeConfigEntries([imported_camera, imported_lock])
        hass = FakeHass(self.root, entries)

        result = await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates,
            owned_entry_ids=["imported-camera", "imported-lock"],
            prunable_entry_ids=["imported-camera", "imported-lock"],
        )

        self.assertEqual(len(self.yaml_save_calls), 2)
        readback = json.loads(yaml_path.read_text(encoding="utf-8"))
        self.assertIsInstance(readback, list)
        self.assertEqual([item["name"] for item in readback], ["Keep Bridge"])
        self.assertEqual(len(result.yaml_backup_paths), 2)
        first_backup = self.root / result.yaml_backup_paths[0]
        self.assertEqual(first_backup.read_bytes(), original_bytes)
        self.assertEqual(
            result.removed_entry_ids, {"imported-camera", "imported-lock"}
        )
        self.assertIsNone(entries.async_get_entry("imported-camera"))
        self.assertIsNone(entries.async_get_entry("imported-lock"))

    async def test_import_mapping_root_keeps_mapping_shape(self) -> None:
        imported = FakeEntry(
            "imported-lock",
            "lock.imported",
            source="import",
            name="Imported Lock",
            port=22003,
        )
        candidates = plan(
            [imported],
            owned=["imported-lock"],
            prunable=["imported-lock"],
            yaml_paths={"imported-lock": "homekit-standalone.yaml"},
        )
        yaml_path = self.root / "homekit-standalone.yaml"
        original = {
            "homekit": [
                {
                    "name": "Imported Lock",
                    "port": 22003,
                    "mode": "accessory",
                    "filter": {"include_entities": ["lock.imported"]},
                },
                {
                    "name": "Keep Bridge",
                    "port": 22004,
                    "mode": "bridge",
                    "filter": {"include_entities": ["light.keep"]},
                },
            ],
            "unrelated": {"preserved": True},
        }
        yaml_path.write_text(json.dumps(original), encoding="utf-8")
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates,
            owned_entry_ids=["imported-lock"],
            prunable_entry_ids=["imported-lock"],
        )

        readback = json.loads(yaml_path.read_text(encoding="utf-8"))
        self.assertIsInstance(readback, dict)
        self.assertEqual(readback["unrelated"], {"preserved": True})
        self.assertEqual(
            [item["name"] for item in readback["homekit"]], ["Keep Bridge"]
        )

    async def test_live_imported_singleton_bridge_matches_exact_yaml_mode(self) -> None:
        imported = FakeEntry(
            "imported-speaker",
            "media_player.apple_tv_speaker",
            source="import",
            mode="bridge",
            name="Apple TV Speaker",
            port=22005,
        )
        imported.options = {
            "mode": imported.data.pop("homekit_mode"),
            "filter": imported.data.pop("filter"),
        }
        candidates = plan(
            [imported],
            owned=["imported-speaker"],
            prunable=["imported-speaker"],
            yaml_paths={"imported-speaker": "homekit.yaml"},
        )
        self.assertEqual(candidates[0].mode, "bridge")
        yaml_path = self.root / "homekit.yaml"
        yaml_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Apple TV Speaker",
                        "port": 22005,
                        "mode": "bridge",
                        "filter": {
                            "include_entities": [
                                "media_player.apple_tv_speaker"
                            ]
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        result = await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates,
            owned_entry_ids=["imported-speaker"],
            prunable_entry_ids=["imported-speaker"],
        )

        self.assertEqual(result.removed_entry_ids, {"imported-speaker"})
        self.assertEqual(json.loads(yaml_path.read_text(encoding="utf-8")), [])
        self.assertEqual(entries.remove_calls, ["imported-speaker"])

    async def test_imported_yaml_mode_mismatch_fails_before_write_or_delete(self) -> None:
        imported = FakeEntry(
            "imported-speaker",
            "media_player.apple_tv_speaker",
            source="import",
            mode="bridge",
            name="Apple TV Speaker",
            port=22005,
        )
        candidates = plan(
            [imported],
            owned=["imported-speaker"],
            prunable=["imported-speaker"],
            yaml_paths={"imported-speaker": "homekit.yaml"},
        )
        yaml_path = self.root / "homekit.yaml"
        original = [
            {
                "name": "Apple TV Speaker",
                "port": 22005,
                "mode": "accessory",
                "filter": {
                    "include_entities": ["media_player.apple_tv_speaker"]
                },
            }
        ]
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-speaker"],
                prunable_entry_ids=["imported-speaker"],
            )

        self.assertEqual(yaml_path.read_bytes(), original_bytes)
        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(entries.remove_calls, [])

    async def test_null_competing_yaml_filter_fails_before_write_or_delete(self) -> None:
        imported = FakeEntry(
            "imported-speaker",
            "media_player.apple_tv_speaker",
            source="import",
            mode="bridge",
            name="Apple TV Speaker",
            port=22005,
        )
        candidates = plan(
            [imported],
            owned=["imported-speaker"],
            prunable=["imported-speaker"],
            yaml_paths={"imported-speaker": "homekit.yaml"},
        )
        yaml_path = self.root / "homekit.yaml"
        original = [
            {
                "name": "Apple TV Speaker",
                "port": 22005,
                "mode": "bridge",
                "filter": {
                    "include_entities": ["media_player.apple_tv_speaker"],
                    "exclude_domains": None,
                },
            }
        ]
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-speaker"],
                prunable_entry_ids=["imported-speaker"],
            )

        self.assertEqual(yaml_path.read_bytes(), original_bytes)
        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(entries.remove_calls, [])

    async def test_cancelled_slow_yaml_worker_settles_before_exact_restore(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            mode="accessory",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        original = [
            {
                "name": "Imported Camera",
                "port": 22001,
                "mode": "accessory",
                "filter": {"include_entities": ["camera.imported"]},
            }
        ]
        yaml_path = self.root / "homekit.yaml"
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)
        entries = FakeConfigEntries([imported])

        class DelayedWorkerHass(FakeHass):
            def __init__(self, root: Path, config_entries: FakeConfigEntries) -> None:
                super().__init__(root, config_entries)
                self.worker_started = asyncio.Event()
                self.worker_release = asyncio.Event()
                self.worker_cancelled = False

            async def async_add_executor_job(
                self, target: Any, *args: Any
            ) -> Any:
                if target is lifecycle._atomic_save_yaml:
                    self.worker_started.set()
                    try:
                        await self.worker_release.wait()
                    except asyncio.CancelledError:
                        self.worker_cancelled = True
                        raise
                return target(*args)

        hass = DelayedWorkerHass(self.root, entries)
        outer = asyncio.create_task(
            lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )
        )
        await hass.worker_started.wait()
        outer.cancel()
        await asyncio.sleep(0)
        self.assertFalse(outer.done())
        outer.cancel()
        await asyncio.sleep(0)
        self.assertFalse(outer.done())
        hass.worker_release.set()

        with self.assertRaises(lifecycle.HomeKitLifecycleCancelled):
            await outer

        self.assertFalse(hass.worker_cancelled)
        self.assertEqual(yaml_path.read_bytes(), original_bytes)
        self.assertIs(entries.async_get_entry("imported-camera"), imported)
        self.assertEqual(entries.remove_calls, [])
        self.assertEqual(list(self.root.glob(".*.platform-sync-*.tmp")), [])

    async def test_changed_import_identity_fails_before_write_or_delete(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        yaml_path = self.root / "homekit.yaml"
        yaml_path.write_text(
            json.dumps(
                {
                    "homekit": [
                        {
                            "name": "Imported Camera",
                            "port": 22999,
                            "mode": "accessory",
                            "filter": {"include_entities": ["camera.imported"]},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(entries.remove_calls, [])
        self.assertEqual(list(self.root.glob("*.bak")), [])

    async def test_changed_live_identity_fails_before_yaml_write_or_delete(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "includes/homekit.yaml"},
        )
        yaml_path = self.root / "includes" / "homekit.yaml"
        yaml_path.parent.mkdir(parents=True)
        original = [
            {
                "name": "Imported Camera",
                "port": 22001,
                "mode": "accessory",
                "filter": {"include_entities": ["camera.imported"]},
            }
        ]
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)
        imported.data["name"] = "Identity Mutated After Planning"
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(yaml_path.read_bytes(), original_bytes)
        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(entries.remove_calls, [])
        self.assertEqual(list(self.root.rglob("*.bak")), [])

    async def test_wrong_valid_yaml_path_and_no_exact_match_fail_closed(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        for relative_path, contents in (
            (
                "wrong-but-valid.yaml",
                [
                    {
                        "name": "Other Accessory",
                        "port": 22999,
                        "mode": "accessory",
                        "filter": {"include_entities": ["camera.other"]},
                    }
                ],
            ),
            ("empty-valid.yaml", []),
        ):
            with self.subTest(relative_path=relative_path):
                yaml_path = self.root / relative_path
                original_bytes = json.dumps(contents).encode("utf-8")
                yaml_path.write_bytes(original_bytes)
                candidates = plan(
                    [imported],
                    owned=["imported-camera"],
                    prunable=["imported-camera"],
                    yaml_paths={"imported-camera": relative_path},
                )

                with self.assertRaises(lifecycle.HomeKitLifecycleError):
                    await lifecycle.async_remove_homekit_accessory_candidates(
                        hass,
                        candidates,
                        owned_entry_ids=["imported-camera"],
                        prunable_entry_ids=["imported-camera"],
                    )

                self.assertEqual(yaml_path.read_bytes(), original_bytes)
                self.assertEqual(entries.remove_calls, [])

        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(list(self.root.glob("*.bak")), [])

    async def test_related_duplicate_import_block_fails_closed(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        yaml_path = self.root / "homekit.yaml"
        yaml_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Imported Camera",
                        "port": 22001,
                        "mode": "accessory",
                        "filter": {"include_entities": ["camera.imported"]},
                    },
                    {
                        "name": "Unexpected Duplicate",
                        "port": 22002,
                        "mode": "accessory",
                        "filter": {"include_entities": ["camera.imported"]},
                    },
                ]
            ),
            encoding="utf-8",
        )
        entries = FakeConfigEntries([imported])
        hass = FakeHass(self.root, entries)

        with self.assertRaises(lifecycle.HomeKitLifecycleError):
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(self.yaml_save_calls, [])
        self.assertEqual(entries.remove_calls, [])
        self.assertEqual(list(self.root.glob("*.bak")), [])

    async def test_outer_cancellation_preserves_confirmed_remove_and_restart(
        self,
    ) -> None:
        accessory = FakeEntry("owned-camera", "camera.front", port=21064)
        candidates = plan(
            [accessory],
            owned=["owned-camera"],
            prunable=["owned-camera"],
        )

        class SlowConfigEntries(FakeConfigEntries):
            def __init__(self, entries: list[FakeEntry]) -> None:
                super().__init__(entries)
                self.started = asyncio.Event()
                self.release = asyncio.Event()
                self.inner_cancelled = False

            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                self.started.set()
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    self.inner_cancelled = True
                    raise
                self.entries.pop(entry_id)
                return {"require_restart": True}

        entries = SlowConfigEntries([accessory])
        hass = FakeHass(self.root, entries)
        outer = asyncio.create_task(
            lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["owned-camera"],
                prunable_entry_ids=["owned-camera"],
            )
        )
        await entries.started.wait()
        outer.cancel()
        entries.release.set()
        with self.assertRaises(lifecycle.HomeKitLifecycleCancelled) as raised:
            await outer

        self.assertFalse(entries.inner_cancelled)
        self.assertIsNone(entries.async_get_entry("owned-camera"))
        self.assertEqual(raised.exception.removed_entry_ids, {"owned-camera"})
        self.assertEqual(raised.exception.removed_entities, {"camera.front"})
        self.assertEqual(
            raised.exception.restart_required_entry_ids, {"owned-camera"}
        )
        self.assertEqual(raised.exception.uncertain_entry_ids, set())
        self.assertEqual(entries.remove_calls, ["owned-camera"])

    async def test_import_remove_failure_restores_yaml_and_can_retry(self) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        yaml_path = self.root / "homekit.yaml"
        yaml_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Imported Camera",
                        "port": 22001,
                        "mode": "accessory",
                        "filter": {"include_entities": ["camera.imported"]},
                    }
                ]
            ),
            encoding="utf-8",
        )

        class FailOnceConfigEntries(FakeConfigEntries):
            def __init__(self, entries: list[FakeEntry]) -> None:
                super().__init__(entries)
                self.failed = False

            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                if not self.failed:
                    self.failed = True
                    raise RuntimeError("simulated imported removal failure")
                self.entries.pop(entry_id)
                return {"require_restart": False}

        entries = FailOnceConfigEntries([imported])
        hass = FakeHass(self.root, entries)
        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(
            json.loads(yaml_path.read_text(encoding="utf-8")),
            [
                {
                    "name": "Imported Camera",
                    "port": 22001,
                    "mode": "accessory",
                    "filter": {"include_entities": ["camera.imported"]},
                }
            ],
        )
        self.assertEqual(len(raised.exception.yaml_backup_paths), 1)
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"imported-camera"}
        )
        self.assertEqual(raised.exception.removed_entry_ids, set())
        self.assertIsNotNone(entries.async_get_entry("imported-camera"))

        result = await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates,
            owned_entry_ids=["imported-camera"],
            prunable_entry_ids=["imported-camera"],
        )

        self.assertEqual(result.removed_entry_ids, {"imported-camera"})
        self.assertIsNone(entries.async_get_entry("imported-camera"))
        self.assertEqual(entries.remove_calls, ["imported-camera", "imported-camera"])
        self.assertEqual(len(self.yaml_save_calls), 2)
        self.assertEqual(
            len(list(self.root.glob("*.platform-sync-homekit-*.bak"))), 2
        )

    async def test_remove_exception_after_memory_delete_is_uncertain_and_restores_yaml(
        self,
    ) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        original = [
            {
                "name": "Imported Camera",
                "port": 22001,
                "mode": "accessory",
                "filter": {"include_entities": ["camera.imported"]},
            }
        ]
        yaml_path = self.root / "homekit.yaml"
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)

        class PopThenRaiseConfigEntries(FakeConfigEntries):
            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                self.entries.pop(entry_id)
                raise RuntimeError("hook/save failed after in-memory deletion")

        entries = PopThenRaiseConfigEntries([imported])
        hass = FakeHass(self.root, entries)
        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(raised.exception.removed_entry_ids, set())
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"imported-camera"}
        )
        self.assertEqual(entries.remove_calls, ["imported-camera"])
        self.assertIsNone(entries.async_get_entry("imported-camera"))
        self.assertEqual(yaml_path.read_bytes(), original_bytes)

    async def test_remove_cancellation_after_memory_delete_is_uncertain_and_restores_yaml(
        self,
    ) -> None:
        imported = FakeEntry(
            "imported-camera",
            "camera.imported",
            source="import",
            name="Imported Camera",
            port=22001,
        )
        candidates = plan(
            [imported],
            owned=["imported-camera"],
            prunable=["imported-camera"],
            yaml_paths={"imported-camera": "homekit.yaml"},
        )
        original = [
            {
                "name": "Imported Camera",
                "port": 22001,
                "mode": "accessory",
                "filter": {"include_entities": ["camera.imported"]},
            }
        ]
        yaml_path = self.root / "homekit.yaml"
        original_bytes = json.dumps(original).encode("utf-8")
        yaml_path.write_bytes(original_bytes)

        class PopThenCancelConfigEntries(FakeConfigEntries):
            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                self.entries.pop(entry_id)
                raise asyncio.CancelledError

        entries = PopThenCancelConfigEntries([imported])
        hass = FakeHass(self.root, entries)
        with self.assertRaises(lifecycle.HomeKitLifecycleCancelled) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["imported-camera"],
                prunable_entry_ids=["imported-camera"],
            )

        self.assertEqual(raised.exception.removed_entry_ids, set())
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"imported-camera"}
        )
        self.assertEqual(entries.remove_calls, ["imported-camera"])
        self.assertIsNone(entries.async_get_entry("imported-camera"))
        self.assertEqual(yaml_path.read_bytes(), original_bytes)

    async def test_multi_import_second_failure_restores_only_uncommitted_block(
        self,
    ) -> None:
        first = FakeEntry(
            "first-import",
            "camera.first",
            source="import",
            name="First Camera",
            port=22001,
        )
        second = FakeEntry(
            "second-import",
            "lock.second",
            source="import",
            name="Second Lock",
            port=22002,
        )
        candidates = plan(
            [first, second],
            owned=["first-import", "second-import"],
            prunable=["first-import", "second-import"],
            yaml_paths={
                "first-import": "homekit.yaml",
                "second-import": "homekit.yaml",
            },
        )
        first_block = {
            "name": "First Camera",
            "port": 22001,
            "mode": "accessory",
            "filter": {"include_entities": ["camera.first"]},
        }
        second_block = {
            "name": "Second Lock",
            "port": 22002,
            "mode": "accessory",
            "filter": {"include_entities": ["lock.second"]},
        }
        keep_block = {
            "name": "Keep Bridge",
            "port": 22003,
            "mode": "bridge",
            "filter": {"include_entities": ["light.keep"]},
        }
        yaml_path = self.root / "homekit.yaml"
        yaml_path.write_text(
            json.dumps([first_block, second_block, keep_block]), encoding="utf-8"
        )

        class FailSecondConfigEntries(FakeConfigEntries):
            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                if entry_id == "second-import":
                    raise RuntimeError("second removal failed")
                self.entries.pop(entry_id)
                return {"require_restart": True}

        entries = FailSecondConfigEntries([first, second])
        hass = FakeHass(self.root, entries)
        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["first-import", "second-import"],
                prunable_entry_ids=["first-import", "second-import"],
            )

        self.assertEqual(raised.exception.removed_entry_ids, {"first-import"})
        self.assertEqual(
            raised.exception.restart_required_entry_ids, {"first-import"}
        )
        self.assertEqual(
            raised.exception.uncertain_entry_ids, {"second-import"}
        )
        self.assertIsNone(entries.async_get_entry("first-import"))
        self.assertIs(entries.async_get_entry("second-import"), second)
        self.assertEqual(
            json.loads(yaml_path.read_text(encoding="utf-8")),
            [second_block, keep_block],
        )
        self.assertEqual(len(raised.exception.yaml_backup_paths), 2)

    async def test_partial_failure_reports_progress_and_retry_is_idempotent(
        self,
    ) -> None:
        first = FakeEntry("first", "camera.first", port=21064)
        second = FakeEntry("second", "lock.second", port=21065)
        candidates = plan(
            [first, second],
            owned=["first", "second"],
            prunable=["first", "second"],
        )

        class FailOnceConfigEntries(FakeConfigEntries):
            def __init__(self, entries: list[FakeEntry]) -> None:
                super().__init__(entries)
                self.failed = False

            async def async_remove(self, entry_id: str) -> dict[str, bool]:
                self.remove_calls.append(entry_id)
                if entry_id == "second" and not self.failed:
                    self.failed = True
                    raise RuntimeError("simulated removal failure")
                self.entries.pop(entry_id)
                return {"require_restart": entry_id == "first"}

        entries = FailOnceConfigEntries([first, second])
        hass = FakeHass(self.root, entries)
        with self.assertRaises(lifecycle.HomeKitLifecycleError) as raised:
            await lifecycle.async_remove_homekit_accessory_candidates(
                hass,
                candidates,
                owned_entry_ids=["first", "second"],
                prunable_entry_ids=["first", "second"],
            )
        self.assertEqual(raised.exception.removed_entry_ids, {"first"})
        self.assertEqual(
            raised.exception.restart_required_entry_ids, {"first"}
        )
        self.assertIsNone(entries.async_get_entry("first"))
        self.assertIsNotNone(entries.async_get_entry("second"))

        retry = await lifecycle.async_remove_homekit_accessory_candidates(
            hass,
            candidates[1:],
            owned_entry_ids=["first", "second"],
            prunable_entry_ids=["first", "second"],
        )
        self.assertEqual(retry.removed_entry_ids, {"second"})
        self.assertEqual(retry.already_absent_entry_ids, set())
        self.assertEqual(entries.remove_calls, ["first", "second", "second"])


if __name__ == "__main__":
    unittest.main()
