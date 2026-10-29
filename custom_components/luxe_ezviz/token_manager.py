"""Persistent and concurrent-safe EZVIZ access-token manager."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Awaitable, Callable, TypeVar

from homeassistant.helpers.storage import Store

from .api import EzvizApiError, EzvizAuthError, EzvizClient, EzvizConnectionError
from .const import DOMAIN, TOKEN_EARLY_REFRESH_MS

_STORAGE_VERSION = 1  # Retain persisted token cache compatibility with v1.0.0.
_T = TypeVar("_T")
_INVALID_ACCESS_TOKENS = frozenset({"10002", "10003"})


class EzvizTokenManager:
    """Manage tokens, merging concurrent forced renewals of a failed token."""

    def __init__(self, hass, entry_id: str, client: EzvizClient, app_key: str, app_secret: str) -> None:
        self._client = client
        self._key = app_key
        self._secret = app_secret
        self._credential_fingerprint = hashlib.sha256(
            (app_key + "\0" + app_secret).encode("utf-8")
        ).hexdigest()
        self._store = Store(hass, _STORAGE_VERSION, f"{DOMAIN}_token_{entry_id}")
        self._token: str | None = None
        self._expires_ms = 0
        self._lock = asyncio.Lock()
        self._last_refresh_ms = 0

    @property
    def expires_ms(self) -> int:
        return self._expires_ms

    async def async_load(self) -> None:
        cached = await self._store.async_load()
        if (
            not isinstance(cached, dict)
            or cached.get("credential_fingerprint") != self._credential_fingerprint
        ):
            return
        token = cached.get("token")
        expires = cached.get("expires_ms")
        if isinstance(token, str) and token and isinstance(expires, int):
            self._token, self._expires_ms = token, expires

    async def async_get_token(
        self, *, force_refresh: bool = False, failed_token: str | None = None
    ) -> str:
        """Return cached token or renew it under one lock.

        A failed_token identifies the token rejected by a *previous* API call.
        If another task already replaced it with a nonexpired token, reuse that
        replacement even if it's inside the proactive 24h refresh window.
        """
        async with self._lock:
            now = int(time.time() * 1000)
            if (
                failed_token is not None
                and self._token is not None
                and self._token != failed_token
                and self._expires_ms > now
            ):
                return self._token
            if (
                failed_token is None
                and not force_refresh
                and self._token
                and self._expires_ms > now
                and (
                    self._expires_ms - now > TOKEN_EARLY_REFRESH_MS
                    or now - self._last_refresh_ms < 60_000
                )
            ):
                return self._token
            try:
                token, expires_ms = await self._client.async_get_token(self._key, self._secret)
                if expires_ms <= int(time.time() * 1000):
                    raise EzvizConnectionError(endpoint="token")
            except (EzvizConnectionError, EzvizApiError):
                if (
                    failed_token is None
                    and not force_refresh
                    and self._token
                    and self._expires_ms > int(time.time() * 1000)
                ):
                    self._last_refresh_ms = int(time.time() * 1000)
                    return self._token
                raise
            self._token, self._expires_ms = token, expires_ms
            self._last_refresh_ms = int(time.time() * 1000)
            await self._store.async_save({
                "credential_fingerprint": self._credential_fingerprint,
                "token": token,
                "expires_ms": expires_ms,
            })
            return token

    async def _with_token(self, operation: Callable[[str], Awaitable[_T]]) -> _T:
        """Retry once on access-token failure; never retry invalid app credentials."""
        token = await self.async_get_token()
        try:
            return await operation(token)
        except EzvizAuthError as err:
            if err.code not in _INVALID_ACCESS_TOKENS:
                raise
            replacement = await self.async_get_token(
                force_refresh=True, failed_token=token
            )
            return await operation(replacement)

    async def async_device_info(self, serial: str) -> dict:
        return await self._with_token(lambda token: self._client.async_device_info(token, serial))

    async def async_device_channels(self, serial: str) -> list[dict]:
        return await self._with_token(
            lambda token: self._client.async_device_channels(token, serial)
        )

    async def async_delete(self) -> None:
        await self._store.async_remove()
