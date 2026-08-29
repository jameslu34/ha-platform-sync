"""Constants for Platform Sync."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "platform_sync"
PLATFORMS: tuple[str, ...] = ()

CONF_ENABLED = "enabled"
CONF_SOURCE_KIND = "source_kind"
CONF_SOURCE_DASHBOARD = "source_dashboard"
CONF_SOURCE_VIEW = "source_view"
CONF_SOURCE_PAGES = "source_pages"
CONF_SOURCE_ENTITIES = "source_entities"
CONF_TARGET_PLATFORMS = "target_platforms"
CONF_MATTER_HOST = "matter_host"
CONF_MATTER_PORT = "matter_port"
CONF_GOOGLE_CONFIG_PATH = "google_config_path"
CONF_HOMEKIT_SOURCE_ENTRY_IDS = "homekit_source_entry_ids"
CONF_HOMEKIT_MANAGED_ENTRY_IDS = "homekit_managed_entry_ids"
CONF_USER_RULES = "user_rules"
CONF_LOCKED_RULES = "locked_rules"
CONF_LOCKED_HOMEKIT_APPLE_TV_EXCLUSION = "locked_homekit_apple_tv_exclusion"

DEFAULT_ENTRY_TITLE_EN = "Cross-Platform Device Sync"
DEFAULT_ENTRY_TITLE_ZH_HANT = "裝置平台同步"
DEFAULT_ENABLED = False
DEFAULT_SOURCE_DASHBOARD = "lovelace"
DEFAULT_SOURCE_VIEW = "default-view"
DEFAULT_MATTER_HOST = ""
DEFAULT_MATTER_PORT = 8283
DEFAULT_GOOGLE_CONFIG_PATH = "google_assistant_entity_config.yaml"

# Internal timing is intentionally not user configurable.  Prefer push events
# when a source provides them and poll only platform-backed sources that do not.
INTERNAL_DEBOUNCE_SECONDS = 2
INTERNAL_POLL_SECONDS = 15
INTERNAL_RETRY_SECONDS = 15
INTERNAL_RETRY_MAX_SECONDS = 300
INTERNAL_RETRY_DELAYS_SECONDS = (15, 30, 60, 120, 300)

# Version 2.2 migration removes these former user-facing keys from existing
# config entries.  They are never read by runtime configuration.
LEGACY_CONF_DEBOUNCE_SECONDS = "debounce_seconds"
LEGACY_CONF_POLL_SECONDS = "poll_seconds"
LEGACY_CONF_AUTO_APPLY = "auto_apply"
LEGACY_CONF_HOME_PRESENCE_PROTECTION = "home_presence_protection"
LEGACY_CONF_PROFILE_NAME = "profile_name"

SERVICE_PREVIEW = "preview"
SERVICE_SYNC_NOW = "sync_now"

EVENT_SYNC_COMPLETED = f"{DOMAIN}_sync_completed"
EVENT_SYNC_FAILED = f"{DOMAIN}_sync_failed"


class SourceKind(StrEnum):
    """Supported source kinds."""

    DASHBOARD = "dashboard"
    MANUAL = "manual"
    GOOGLE = "google"
    HOMEKIT = "homekit"
    MATTER = "matter"


class TargetPlatform(StrEnum):
    """Supported target platforms."""

    GOOGLE = "google"
    HOMEKIT = "homekit"
    MATTER = "matter"


ALL_TARGETS = tuple(TargetPlatform)
