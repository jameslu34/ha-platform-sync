"""Native-only user notification delivery for Platform Sync.

All user-visible runtime notices from this integration must pass through this
module.  The gateway intentionally uses Home Assistant's built-in persistent
notification component directly; it does not call a ``notify`` service, send a
mobile push, emit a webhook, or write to a Lovelace dashboard.
"""

from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)
USER_NOTIFICATION_CHANNEL = "home_assistant_persistent_notification"


def _persistent_notification_backend() -> ModuleType:
    """Load HA's native persistent-notification component lazily."""
    from homeassistant.components import persistent_notification

    return persistent_notification


def async_create_native_notification(
    hass: HomeAssistant,
    message: str,
    *,
    title: str,
    notification_id: str,
) -> bool:
    """Create or replace one HA-native persistent notification.

    Returning ``False`` keeps the caller fail-closed when the native component
    is unavailable.  No alternate or external delivery channel is attempted.
    """
    try:
        backend = _persistent_notification_backend()
    except ImportError:
        _LOGGER.warning(
            "HA native persistent notifications are unavailable; "
            "Platform Sync will not use a fallback notification channel"
        )
        return False

    backend.async_create(
        hass,
        message,
        title=title,
        notification_id=notification_id,
    )
    return True


def async_dismiss_native_notification(
    hass: HomeAssistant,
    notification_id: str,
) -> bool:
    """Dismiss one HA-native persistent notification without a fallback."""
    try:
        backend = _persistent_notification_backend()
    except ImportError:
        _LOGGER.warning(
            "HA native persistent notifications are unavailable; "
            "Platform Sync will not use a fallback notification channel"
        )
        return False

    backend.async_dismiss(hass, notification_id)
    return True
