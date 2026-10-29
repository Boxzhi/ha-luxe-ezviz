"""EZVIZ Open Platform API with endpoint-aware, credential-safe errors."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import CHANNEL_LIST_URL, DEVICE_INFO_URL, TOKEN_URL, PTZ_CAPACITY_URL, PTZ_START_URL, PTZ_STOP_URL

_TIMEOUT = ClientTimeout(total=15)


class EzvizError(Exception):
    """Safe-to-log EZVIZ failure with a machine-readable code and endpoint."""

    def __init__(self, code: str = "unknown", *, endpoint: str = "unknown") -> None:
        self.code = code if code.isdigit() and len(code) <= 12 else "unknown"
        self.endpoint = endpoint
        super().__init__(f"EZVIZ {type(self).__name__} ({self.code}; {endpoint})")


class EzvizConnectionError(EzvizError):
    """Network or malformed response."""


class EzvizAuthError(EzvizError):
    """App credentials invalid, or access token rejected/expired."""


class EzvizDeviceError(EzvizError):
    """Device exists but is not accessible to this app."""


class EzvizDeviceNotFoundError(EzvizError):
    """Device is not found."""


class EzvizInvalidSerialError(EzvizError):
    """Invalid serial number."""


class EzvizInvalidChannelError(EzvizError):
    """Configured channel does not exist under the device."""


class EzvizApiError(EzvizError):
    """Other cloud API error."""


class EzvizClient:
    """Fixed-host, POST-form-only client; do not log response bodies."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _post(self, url: str, payload: dict[str, str]) -> dict[str, Any]:
        endpoint = {
            TOKEN_URL: "token",
            DEVICE_INFO_URL: "device_info",
            CHANNEL_LIST_URL: "device_channels",
            PTZ_CAPACITY_URL: "ptz_capacity",
            PTZ_START_URL: "ptz_start",
            PTZ_STOP_URL: "ptz_stop",
        }.get(url)
        if endpoint is None:
            raise ValueError("Unexpected EZVIZ API endpoint")
        try:
            async with self._session.post(
                url, data=payload, timeout=(ClientTimeout(total=4) if endpoint.startswith("ptz_") else _TIMEOUT), allow_redirects=False
            ) as response:
                if response.status != 200:
                    raise EzvizConnectionError(endpoint=endpoint)
                result = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError, ValueError, TypeError) as err:
            raise EzvizConnectionError(endpoint=endpoint) from err

        if not isinstance(result, dict):
            raise EzvizConnectionError(endpoint=endpoint)
        code = str(result.get("code", ""))
        if code == "200":
            return result
        if code in {"10002", "10003", "10005", "10017", "10018", "10030"}:
            raise EzvizAuthError(code, endpoint=endpoint)
        if endpoint in {"device_info", "device_channels"}:
            if code == "20014":
                raise EzvizInvalidSerialError(code, endpoint=endpoint)
            if code == "20002":
                raise EzvizDeviceNotFoundError(code, endpoint=endpoint)
            if code == "20018":
                raise EzvizDeviceError(code, endpoint=endpoint)
            if endpoint == "device_channels" and code in {"20001", "20032"}:
                raise EzvizInvalidChannelError(code, endpoint=endpoint)
        raise EzvizApiError(code, endpoint=endpoint)

    async def async_get_token(self, app_key: str, app_secret: str) -> tuple[str, int]:
        """Get access token with an absolute expiry in milliseconds."""
        result = await self._post(TOKEN_URL, {"appKey": app_key, "appSecret": app_secret})
        data = result.get("data")
        if not isinstance(data, dict):
            raise EzvizConnectionError(endpoint="token")
        token = data.get("accessToken")
        expiration = data.get("expireTime")
        if not isinstance(token, str) or not token or not isinstance(expiration, (int, float, str)):
            raise EzvizConnectionError(endpoint="token")
        try:
            expires_ms = int(expiration)
        except (ValueError, TypeError) as err:
            raise EzvizConnectionError(endpoint="token") from err
        if expires_ms <= 0:
            raise EzvizConnectionError(endpoint="token")
        return token, expires_ms

    async def async_device_info(self, token: str, serial: str) -> dict[str, Any]:
        """Verify app access to a device, but NOT its video decryption code."""
        result = await self._post(
            DEVICE_INFO_URL, {"accessToken": token, "deviceSerial": serial}
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise EzvizConnectionError(endpoint="device_info")
        return data

    async def async_device_channels(self, token: str, serial: str) -> list[dict[str, Any]]:
        """List the channels reported for this device."""
        result = await self._post(
            CHANNEL_LIST_URL, {"accessToken": token, "deviceSerial": serial}
        )
        data = result.get("data")
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise EzvizConnectionError(endpoint="device_channels")
        return data

    async def async_ptz_capability(self, token: str, serial: str) -> dict[str, Any]:
        """Read the device's official capability set, not a model-based guess."""
        result = await self._post(PTZ_CAPACITY_URL, {"accessToken": token, "deviceSerial": serial})
        data = result.get("data")
        if not isinstance(data, dict):
            raise EzvizConnectionError(endpoint="ptz_capacity")
        return data

    async def async_ptz_control(self, token: str, serial: str, channel: int, action: str, direction: int) -> None:
        """Use server-side credentials for PTZ start and stop."""
        if action not in ("start", "stop") or direction not in (0, 1, 2, 3):
            raise ValueError("Invalid PTZ operation")
        payload = {"accessToken": token, "deviceSerial": serial, "channelNo": str(channel), "direction": str(direction)}
        if action == "start":
            payload["speed"] = "1"
        await self._post(PTZ_START_URL if action == "start" else PTZ_STOP_URL, payload)
