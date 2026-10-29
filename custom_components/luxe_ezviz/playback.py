"""Admin-only EZUIKit playback-session endpoint.

A session contains a cloud token and an encrypted EZOPEN URL, so it is delivered
only to an authenticated HA administrator on an explicit POST request. Never
put these values in logs, URLs, storage owned by the browser, or static assets.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from aiohttp import web

from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.helpers.http import KEY_HASS

from .api import (
    EzvizApiError,
    EzvizAuthError,
    EzvizConnectionError,
    EzvizDeviceError,
    EzvizDeviceNotFoundError,
    EzvizInvalidChannelError,
    EzvizInvalidSerialError,
)
from .const import (
    API_BASE,
    CONF_CHANNEL,
    CONF_DEVICE_SERIAL,
    CONF_VERIFY_CODE,
)
from .http import _get_runtime
from .encryption import parse_encryption_state

_SERIAL_PATTERN = re.compile(r"[A-Za-z0-9_-]{4,64}\Z")


def build_ezopen_url(serial: str, verify_code: str, channel: int, encrypted: bool = True) -> str:
    """Build an EZOPEN URL using the verified cloud encryption state."""
    if not isinstance(serial, str) or not _SERIAL_PATTERN.fullmatch(serial):
        raise ValueError("Invalid configured device serial")
    if not isinstance(channel, int) or not 1 <= channel <= 255:
        raise ValueError("Invalid configured channel")
    if not isinstance(verify_code, str) or not verify_code or len(verify_code) > 128:
        raise ValueError("Invalid configured verification code")
    if not isinstance(encrypted, bool):
        raise ValueError("Unknown device encryption state")
    # Never attach a stored code when the device explicitly reports clear video.
    prefix = f"{quote(verify_code, safe='')}@" if encrypted else ""
    return f"ezopen://{prefix}open.ys7.com/{serial}/{channel}.live"


class LuxeEzvizPlaybackView(HomeAssistantView):
    """Create an ephemeral browser playback session from HA-stored credentials."""

    url = "/api/luxe_ezviz/playback"
    name = "api:luxe_ezviz:playback"
    requires_auth = True

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict):
            return self._answer({"ok": False, "reason": "invalid_request"}, 400)
        entry, runtime, error = _get_runtime(hass, payload.get("device_serial"))
        if error:
            status = {
                "device_serial_required": 400,
                "invalid_device_serial": 400,
                "device_serial_not_found": 404,
            }.get(error, 503)
            return self._answer({"ok": False, "reason": error}, status)
        try:
            channel = int(entry.data[CONF_CHANNEL])
            info = await runtime.async_device_info(entry.data[CONF_DEVICE_SERIAL])
            encrypted = parse_encryption_state(info)
            if encrypted is None:
                return self._answer({"ok": False, "reason": "encryption_unknown"}, 422)
            url = build_ezopen_url(
                entry.data[CONF_DEVICE_SERIAL],
                entry.data[CONF_VERIFY_CODE],
                channel,
                encrypted=encrypted,
            )
            if not await runtime.async_channel_exists(
                entry.data[CONF_DEVICE_SERIAL], channel
            ):
                return self._answer({"ok": False, "reason": "invalid_channel"}, 422)
            token = await runtime.token_manager.async_get_token()
        except ValueError:
            return self._answer({"ok": False, "reason": "invalid_configuration"}, 422)
        except EzvizAuthError:
            return self._answer({"ok": False, "reason": "invalid_auth"}, 401)
        except EzvizInvalidSerialError:
            return self._answer({"ok": False, "reason": "invalid_serial"}, 400)
        except EzvizDeviceNotFoundError:
            return self._answer({"ok": False, "reason": "device_not_found"}, 404)
        except EzvizInvalidChannelError:
            return self._answer({"ok": False, "reason": "invalid_channel"}, 422)
        except EzvizDeviceError:
            return self._answer({"ok": False, "reason": "device_permission"}, 403)
        except (EzvizConnectionError, EzvizApiError):
            return self._answer({"ok": False, "reason": "cloud_unavailable"}, 503)

        return self._answer({
            "ok": True,
            "camera_name": entry.title,
            "accessToken": token,
            "url": url,
            "env": {"domain": API_BASE},
            "expires_at_ms": runtime.token_manager.expires_ms,
        })

    def _answer(self, result: dict, status: int = 200) -> web.Response:
        return self.json(result, status_code=status, headers={
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        })
