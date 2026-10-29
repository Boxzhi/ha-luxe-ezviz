"""Luxe EZVIZ integration -- cloud authentication and browser playback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import device_registry as dr

from .api import (
    EzvizApiError,
    EzvizAuthError,
    EzvizClient,
    EzvizConnectionError,
    EzvizDeviceError,
    EzvizDeviceNotFoundError,
    EzvizInvalidChannelError,
    EzvizInvalidSerialError,
)
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_DEVICE_SERIAL,
    DOMAIN,
    DEVICE_INFO_CACHE_SECONDS,
    REFRESH_INTERVAL_HOURS,
)
from .http import LuxeEzvizCheckView, LuxeEzvizMetadataView, LuxeEzvizStatusView
from .token_manager import EzvizTokenManager
from .playback import LuxeEzvizPlaybackView
from .image_manager import async_delete_image
from .frontend_setup import async_setup_frontend
from .sdk import async_prepare_sdk
from .ptz import LuxeEzvizPtzCapabilityView, LuxeEzvizPtzControlView

_LOGGER = logging.getLogger(__name__)


@dataclass
class LuxeEzvizRuntime:
    """Per-entry cloud state."""

    token_manager: EzvizTokenManager
    device_info: dict
    device_checked_at: datetime
    device_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    channels: list[dict] | None = None
    channels_checked_at: datetime | None = None
    channel_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def async_device_info(self, serial: str, *, force: bool = False) -> dict:
        """Refresh device information once when its cache has expired."""
        async with self.device_lock:
            age = datetime.now(timezone.utc) - self.device_checked_at
            if not force and age.total_seconds() < DEVICE_INFO_CACHE_SECONDS:
                return self.device_info
            self.device_info = await self.token_manager.async_device_info(serial)
            self.device_checked_at = datetime.now(timezone.utc)
            return self.device_info

    async def async_channel_exists(
        self, serial: str, channel: int, *, force: bool = False
    ) -> bool:
        """Check the configured channel with the same short cache as device info."""
        async with self.channel_lock:
            now = datetime.now(timezone.utc)
            if (
                force
                or self.channels is None
                or self.channels_checked_at is None
                or (now - self.channels_checked_at).total_seconds()
                >= DEVICE_INFO_CACHE_SECONDS
            ):
                self.channels = await self.token_manager.async_device_channels(serial)
                self.channels_checked_at = datetime.now(timezone.utc)
            return any(
                str(item.get("channelNo")) == str(channel)
                for item in self.channels or []
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register authentication-protected, admin-only diagnostic views."""
    hass.data.setdefault(DOMAIN, {})
    # HACS ships only Luxe source; download official SDK to the local HA host.
    if not await async_prepare_sdk(hass):
        return False
    await async_setup_frontend(hass)
    hass.http.register_view(LuxeEzvizMetadataView())
    hass.http.register_view(LuxeEzvizStatusView())
    hass.http.register_view(LuxeEzvizCheckView())
    hass.http.register_view(LuxeEzvizPlaybackView())
    hass.http.register_view(LuxeEzvizPtzCapabilityView())
    hass.http.register_view(LuxeEzvizPtzControlView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Validate cloud account and device without creating a video session."""
    client = EzvizClient(async_get_clientsession(hass))
    manager = EzvizTokenManager(
        hass,
        entry.entry_id,
        client,
        entry.data[CONF_APP_KEY],
        entry.data[CONF_APP_SECRET],
    )
    await manager.async_load()
    try:
        device_info = await manager.async_device_info(entry.data[CONF_DEVICE_SERIAL])
    except EzvizAuthError as err:
        raise ConfigEntryAuthFailed("EZVIZ credentials are no longer valid") from err
    except EzvizInvalidSerialError as err:
        raise ConfigEntryError("EZVIZ device serial is invalid") from err
    except EzvizDeviceNotFoundError as err:
        raise ConfigEntryError("EZVIZ device was not found") from err
    except EzvizInvalidChannelError as err:
        raise ConfigEntryError("EZVIZ device channel was not found") from err
    except EzvizDeviceError as err:
        raise ConfigEntryError("EZVIZ developer application is not authorized for this device") from err
    except (EzvizConnectionError, EzvizApiError) as err:
        raise ConfigEntryNotReady("Unable to check EZVIZ device") from err

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_DEVICE_SERIAL])},
        manufacturer="EZVIZ",
        model=str(device_info.get("model") or "未知型号"),
        name=entry.title,
    )
    runtime = LuxeEzvizRuntime(manager, device_info, datetime.now(timezone.utc))
    hass.data[DOMAIN][entry.entry_id] = runtime

    async def _refresh_if_needed(_now: datetime) -> None:
        try:
            await manager.async_get_token()
        except EzvizAuthError:
            _LOGGER.warning("EZVIZ credentials need reauthentication")
            entry.async_start_reauth(hass)
        except (EzvizConnectionError, EzvizApiError):
            _LOGGER.warning("EZVIZ token refresh failed; will retry at next interval")

    entry.async_on_unload(
        async_track_time_interval(
            hass, _refresh_if_needed, timedelta(hours=REFRESH_INTERVAL_HOURS)
        )
    )
    _LOGGER.info("Luxe EZVIZ backend ready (device credentials kept private)")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload without touching existing go2rtc or other integrations."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime and getattr(runtime, "ptz_controller", None):
        try:
            await runtime.ptz_controller.close()
        except Exception:
            _LOGGER.error("PTZ STOP not confirmed; refusing entry unload to retain retry protection")
            return False
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove cached token when deleting the integration."""
    client = EzvizClient(async_get_clientsession(hass))
    manager = EzvizTokenManager(
        hass, entry.entry_id, client, entry.data[CONF_APP_KEY], entry.data[CONF_APP_SECRET]
    )
    await manager.async_delete()
    # Removal is explicit; do not retain an orphaned publicly served image.
    await async_delete_image(hass, entry.data[CONF_DEVICE_SERIAL])
