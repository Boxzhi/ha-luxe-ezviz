"""Admin-only connection diagnostics; does not return stream credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.helpers.http import KEY_HASS
from homeassistant.helpers import device_registry as dr

from .api import (
    EzvizApiError,
    EzvizAuthError,
    EzvizConnectionError,
    EzvizDeviceError,
    EzvizDeviceNotFoundError,
    EzvizInvalidChannelError,
    EzvizInvalidSerialError,
)
from .encryption import parse_encryption_state
from .image_manager import async_image_url
from .const import CONF_CHANNEL, CONF_DEVICE_SERIAL, DOMAIN


def _serial_mask(value: str) -> str:
    """Do not expose complete serial numbers in diagnostics."""
    return "***" + value[-4:] if len(value) >= 4 else "***"


def _response(view: HomeAssistantView, data: dict, status: int = 200) -> web.Response:
    return view.json(data, status_code=status, headers={"Cache-Control": "no-store"})


def _get_runtime(hass, device_serial: str | None):
    """Resolve by physical serial; never silently select the first entry."""
    if not isinstance(device_serial, str) or not device_serial.strip():
        return None, None, "device_serial_required"
    serial = device_serial.strip().upper()
    if not 4 <= len(serial) <= 64 or not all(
        char.isascii() and (char.isalnum() or char in "_-") for char in serial
    ):
        return None, None, "invalid_device_serial"
    entry = next((item for item in hass.config_entries.async_entries(DOMAIN)
                  if str(item.data.get(CONF_DEVICE_SERIAL, "")).strip().upper() == serial), None)
    if entry is None:
        return None, None, "device_serial_not_found"
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is None:
        return None, None, "camera_not_loaded"
    return entry, runtime, None


def _display_name(hass, entry) -> str:
    """Use HA's user-assigned name first, without using it for selection."""
    serial = entry.data[CONF_DEVICE_SERIAL]
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, serial)})
    if device:
        return device.name_by_user or device.name or entry.title
    return entry.title


def _selection_error(view: HomeAssistantView, reason: str) -> web.Response:
    """Return a stable, non-sensitive response for camera selection errors."""
    status = {
        "device_serial_required": 400,
        "invalid_device_serial": 400,
        "device_serial_not_found": 404,
        "camera_not_loaded": 503,
    }.get(reason, 503)
    return _response(view, {"ok": False, "reason": reason}, status)


class LuxeEzvizMetadataView(HomeAssistantView):
    """Cached device metadata for card labels; never returns credentials."""

    url = "/api/luxe_ezviz/metadata"
    name = "api:luxe_ezviz:metadata"
    requires_auth = True

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry, runtime, error = _get_runtime(hass, request.query.get("device_serial"))
        if error:
            return _selection_error(self, error)
        model = runtime.device_info.get("model")
        picture = await async_image_url(hass, entry.data[CONF_DEVICE_SERIAL])
        return _response(self, {
            "ok": True,
            "display_name": _display_name(hass, entry),
            "model": model if isinstance(model, str) else None,
            "image_url": picture,
            "device_serial_masked": _serial_mask(entry.data[CONF_DEVICE_SERIAL]),
        })


class LuxeEzvizStatusView(HomeAssistantView):
    """Status without credentials, not even the device verification code."""

    url = "/api/luxe_ezviz/status"
    name = "api:luxe_ezviz:status"
    requires_auth = True

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry, runtime, error = _get_runtime(hass, request.query.get("device_serial"))
        if error:
            return _selection_error(self, error)
        try:
            data = await runtime.async_device_info(entry.data[CONF_DEVICE_SERIAL])
            if not await runtime.async_channel_exists(
                entry.data[CONF_DEVICE_SERIAL], entry.data[CONF_CHANNEL]
            ):
                return _response(self, {"ok": False, "reason": "invalid_channel"}, 422)
        except EzvizAuthError:
            return _response(self, {"ok": False, "reason": "invalid_auth"}, 401)
        except EzvizInvalidSerialError:
            return _response(self, {"ok": False, "reason": "invalid_serial"}, 400)
        except EzvizDeviceNotFoundError:
            return _response(self, {"ok": False, "reason": "device_not_found"}, 404)
        except EzvizInvalidChannelError:
            return _response(self, {"ok": False, "reason": "invalid_channel"}, 422)
        except EzvizDeviceError:
            return _response(self, {"ok": False, "reason": "device_permission"}, 403)
        except (EzvizConnectionError, EzvizApiError):
            return _response(self, {"ok": False, "reason": "cloud_unavailable"}, 503)
        expiration = runtime.token_manager.expires_ms
        iso_expiry = (
            datetime.fromtimestamp(expiration / 1000, tz=timezone.utc).isoformat()
            if expiration else None
        )
        return _response(self, {
            "ok": True,
            "display_name": _display_name(request.app[KEY_HASS], entry),
            "device_serial_masked": _serial_mask(entry.data[CONF_DEVICE_SERIAL]),
            "channel": entry.data[CONF_CHANNEL],
            "token_expires_at_utc": iso_expiry,
            "device_checked_at_utc": runtime.device_checked_at.isoformat(),
            "device_name": data.get("deviceName"),
            "device_online": str(data.get("status")) == "1",
            "encrypted": parse_encryption_state(data),
            "note": "Device verification code not validated until actual video playback",
        })


class LuxeEzvizCheckView(HomeAssistantView):
    """Explicit action to check device API access."""

    url = "/api/luxe_ezviz/check"
    name = "api:luxe_ezviz:check"
    requires_auth = True

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            payload = None
        serial = payload.get("device_serial") if isinstance(payload, dict) else None
        entry, runtime, error = _get_runtime(request.app[KEY_HASS], serial)
        if error:
            return _selection_error(self, error)
        try:
            data = await runtime.async_device_info(
                entry.data[CONF_DEVICE_SERIAL], force=True
            )
            if not await runtime.async_channel_exists(
                entry.data[CONF_DEVICE_SERIAL], entry.data[CONF_CHANNEL], force=True
            ):
                return _response(self, {"ok": False, "reason": "invalid_channel"}, 422)
        except EzvizAuthError:
            return _response(self, {"ok": False, "reason": "invalid_auth"}, 401)
        except EzvizInvalidSerialError:
            return _response(self, {"ok": False, "reason": "invalid_serial"}, 400)
        except EzvizDeviceNotFoundError:
            return _response(self, {"ok": False, "reason": "device_not_found"}, 404)
        except EzvizInvalidChannelError:
            return _response(self, {"ok": False, "reason": "invalid_channel"}, 422)
        except EzvizDeviceError:
            return _response(self, {"ok": False, "reason": "device_permission"}, 403)
        except (EzvizConnectionError, EzvizApiError):
            return _response(self, {"ok": False, "reason": "cloud_unavailable"}, 503)
        return _response(self, {
            "ok": True,
            "display_name": _display_name(request.app[KEY_HASS], entry),
            "device_serial_masked": _serial_mask(entry.data[CONF_DEVICE_SERIAL]),
            "device_name": data.get("deviceName"),
            "device_checked_at_utc": runtime.device_checked_at.isoformat(),
            "online": str(data.get("status")) == "1",
            "encrypted": parse_encryption_state(data),
            "note": "API authorization verified; video decryption is not tested",
        })
