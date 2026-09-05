"""Platform Sync integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .config import SyncConfig, normalize_dashboard_pages
from .const import (
    CONF_ENABLED,
    CONF_HOMEKIT_MAIN_ENTRY_ID,
    CONF_HOMEKIT_MANAGED_ENTRY_IDS,
    CONF_HOMEKIT_SOURCE_ENTRY_IDS,
    CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION,
    CONF_LOCKED_RULES,
    CONF_SOURCE_DASHBOARD,
    CONF_SOURCE_KIND,
    CONF_SOURCE_PAGES,
    CONF_SOURCE_VIEW,
    CONF_TARGET_PLATFORMS,
    DEFAULT_SOURCE_DASHBOARD,
    DEFAULT_SOURCE_VIEW,
    DEFAULT_ENTRY_TITLE_EN,
    DEFAULT_ENTRY_TITLE_ZH_HANT,
    DOMAIN,
    LEGACY_CONF_AUTO_APPLY,
    LEGACY_CONF_DEBOUNCE_SECONDS,
    LEGACY_CONF_HOME_PRESENCE_PROTECTION,
    LEGACY_CONF_POLL_SECONDS,
    LEGACY_CONF_PROFILE_NAME,
    PLATFORMS,
    SERVICE_PREVIEW,
    SERVICE_SYNC_NOW,
    SourceKind,
    TargetPlatform,
)
from .manager import PlatformSyncManager
from .models import parse_rules, serialize_rules
from .targets import homekit_managed_main_entry_id

type PlatformSyncConfigEntry = ConfigEntry[PlatformSyncManager]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(
    hass: HomeAssistant, entry: PlatformSyncConfigEntry
) -> bool:
    """Migrate to one switch, exact sources, and durable HomeKit identity."""
    if entry.version > 4 or (entry.version == 4 and entry.minor_version > 4):
        return False
    if entry.version == 4 and entry.minor_version == 4:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    merged = {**data, **options}
    if entry.version < 2:
        targets = set(merged.get(CONF_TARGET_PLATFORMS, []))
        if (
            TargetPlatform.HOMEKIT.value in targets
            and not merged.get(CONF_HOMEKIT_MANAGED_ENTRY_IDS)
        ):
            # Snapshot only the entries present during this one-time migration.
            # Future HomeKit entries are never adopted implicitly.
            snapshot = [
                item.entry_id for item in hass.config_entries.async_entries("homekit")
            ]
            if CONF_HOMEKIT_MANAGED_ENTRY_IDS in options:
                options[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = snapshot
            else:
                data[CONF_HOMEKIT_MANAGED_ENTRY_IDS] = snapshot

    if entry.version < 3:
        # Keep any immutable rules already stored by a pre-release build, but
        # do not ship deployment-specific entity identifiers in public code.
        locked_rules = parse_rules(data.get(CONF_LOCKED_RULES))
        data[CONF_LOCKED_RULES] = serialize_rules(locked_rules)

        # Old preview mode must never turn into automatic writes. Only legacy
        # configurations whose two gates were both on become enabled.
        enabled = bool(merged.get(CONF_ENABLED, False))
        if entry.version < 2:
            enabled = False
        elif LEGACY_CONF_AUTO_APPLY in data or LEGACY_CONF_AUTO_APPLY in options:
            enabled = enabled and bool(merged.get(LEGACY_CONF_AUTO_APPLY, False))
        data.pop(CONF_ENABLED, None)
        options[CONF_ENABLED] = enabled

    # Remove every retired UI key from both storage layers.
    for key in (
        LEGACY_CONF_AUTO_APPLY,
        LEGACY_CONF_HOME_PRESENCE_PROTECTION,
        LEGACY_CONF_DEBOUNCE_SECONDS,
        LEGACY_CONF_POLL_SECONDS,
        LEGACY_CONF_PROFILE_NAME,
    ):
        data.pop(key, None)
        options.pop(key, None)

    merged = {**data, **options}
    if CONF_SOURCE_PAGES not in merged:
        pages = normalize_dashboard_pages(
            None,
            fallback_dashboard=str(
                merged.get(CONF_SOURCE_DASHBOARD, DEFAULT_SOURCE_DASHBOARD)
            ),
            fallback_view=str(merged.get(CONF_SOURCE_VIEW, DEFAULT_SOURCE_VIEW)),
        )
        options[CONF_SOURCE_PAGES] = [
            {"dashboard": dashboard, "view": view}
            for dashboard, view in pages
        ]

    # Schema 4.1 read every HomeKit Config Entry as one implicit source.  Take
    # one explicit snapshot during migration so later HomeKit additions are
    # never adopted without the user's selection.  Source ownership remains
    # separate from the managed target-entry list above.
    merged = {**data, **options}
    if (
        merged.get(CONF_SOURCE_KIND) == SourceKind.HOMEKIT.value
        and CONF_HOMEKIT_SOURCE_ENTRY_IDS not in merged
    ):
        source_snapshot = [
            item.entry_id for item in hass.config_entries.async_entries("homekit")
        ]
        options[CONF_HOMEKIT_SOURCE_ENTRY_IDS] = source_snapshot
        if bool(merged.get(CONF_ENABLED, False)) and not source_snapshot:
            # An enabled HomeKit source with no exact entry selection cannot be
            # evaluated safely.  Disable only the master switch and preserve
            # every other source, target, and exception setting.
            data.pop(CONF_ENABLED, None)
            options[CONF_ENABLED] = False

    # Keep Apple TV integration entities out of HomeKit targets. This is a
    # fail-safe provenance rule because re-exporting them can create duplicate
    # or recursive accessories; it also applies to new Config Flow entries.
    data.setdefault(CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION, True)

    # Schema 4.3 inferred the writable main Bridge from its current entity
    # count. That identity becomes ambiguous as soon as the main Bridge and a
    # side entry are both singletons. Resolve and durably store the identity
    # before setup can perform the first target mutation. If the live layout no
    # longer proves exactly one main Bridge, leave the Config Entry untouched
    # and require the user to select it explicitly in Options Flow.
    merged = {**data, **options}
    targets = set(merged.get(CONF_TARGET_PLATFORMS, []))
    managed_entry_ids = merged.get(CONF_HOMEKIT_MANAGED_ENTRY_IDS, [])
    if (
        TargetPlatform.HOMEKIT.value in targets
        and managed_entry_ids
    ):
        try:
            migrated_config = SyncConfig.from_entry(data, options)
            resolved_main_entry_id = homekit_managed_main_entry_id(
                hass, migrated_config
            )
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False
        if not merged.get(CONF_HOMEKIT_MAIN_ENTRY_ID):
            if CONF_HOMEKIT_MAIN_ENTRY_ID in options:
                options[CONF_HOMEKIT_MAIN_ENTRY_ID] = resolved_main_entry_id
            elif CONF_HOMEKIT_MAIN_ENTRY_ID in data:
                data[CONF_HOMEKIT_MAIN_ENTRY_ID] = resolved_main_entry_id
            else:
                options[CONF_HOMEKIT_MAIN_ENTRY_ID] = resolved_main_entry_id

    language = (
        str(getattr(hass.config, "language", "en"))
        .casefold()
        .replace("_", "-")
    )
    is_zh_hant = language in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"} or language.startswith(
        "zh-hant-"
    )
    title = DEFAULT_ENTRY_TITLE_ZH_HANT if is_zh_hant else DEFAULT_ENTRY_TITLE_EN

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        title=title,
        version=4,
        minor_version=4,
    )
    return True


def _remove_legacy_entities(hass: HomeAssistant, entry: PlatformSyncConfigEntry) -> None:
    """Remove the retired status and manual-action registry rows by unique ID."""
    registry = er.async_get(hass)
    for entity_domain, suffix in (("sensor", "status"), ("button", "sync_now")):
        entity_id = registry.async_get_entity_id(
            entity_domain, DOMAIN, f"{entry.entry_id}_{suffix}"
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up service actions."""
    async def handle(call: ServiceCall) -> dict:
        results = {}
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.runtime_data:
                apply = call.service == SERVICE_SYNC_NOW
                results[entry.title] = await entry.runtime_data.async_reconcile(
                    reason=f"service_{call.service}", apply=apply
                )
        return results

    hass.services.async_register(
        DOMAIN, SERVICE_PREVIEW, handle, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_NOW, handle, supports_response=SupportsResponse.OPTIONAL
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PlatformSyncConfigEntry) -> bool:
    """Set up the synchronization configuration."""
    _remove_legacy_entities(hass, entry)
    manager = PlatformSyncManager(
        hass, SyncConfig.from_entry(entry.data, entry.options), entry
    )
    entry.runtime_data = manager
    await manager.async_start()
    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlatformSyncConfigEntry) -> bool:
    """Unload without changing any platform exposure."""
    if not await entry.runtime_data.async_stop():
        return False
    if not PLATFORMS:
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
