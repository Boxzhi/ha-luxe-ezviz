"""PTZ capability parsing and fail-safe serialized controller (no HA dependencies).

This module deliberately does not control EZUIKit or any playback state.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Awaitable, Callable

DIRECTIONS = {"up": 0, "down": 1, "left": 2, "right": 3}
HORIZONTAL = frozenset({"left", "right"})
VERTICAL = frozenset({"up", "down"})
WATCHDOG_SECONDS = 2.5
TAP_SECONDS = 0.38


def _flag(value: object) -> bool | None:
    if value is True or value == 1 or value == "1":
        return True
    if value is False or value == 0 or value == "0":
        return False
    return None


def parse_ptz_capability(data: object) -> dict:
    """Fail closed on unknown responses; do not infer PTZ from a model name.

    EZVIZ capability APIs expose support_ptz and optional axis flags.
    When supported but neither axis is specified, normal four-way PTZ is
    assumed; explicit axis restrictions always take precedence.
    """
    if not isinstance(data, dict):
        return {"supported": False, "known": False, "directions": []}
    supported = _flag(data.get("support_ptz"))
    if supported is None:
        return {"supported": False, "known": False, "directions": []}
    if not supported:
        return {"supported": False, "known": True, "directions": []}
    vert = _flag(data.get("ptz_top_bottom"))
    horiz = _flag(data.get("ptz_left_right"))
    if vert is None and horiz is None:
        vert = horiz = True
    directions = (["up", "down"] if vert is True else []) + (["left", "right"] if horiz is True else [])
    return {"supported": bool(directions), "known": True, "directions": directions}


class PtzController:
    """Single active movement per camera; watchdog expires without browser heartbeats.

    The START/STOP implementation is injected, enabling isolated unit tests.
    Any uncertain START outcome triggers a best-effort STOP. A failed STOP
    keeps the active direction so later watchdog attempts may retry.
    """

    def __init__(self, send: Callable[[str, int], Awaitable[None]], *, watchdog_seconds: float = WATCHDOG_SECONDS):
        self._send = send
        self._lock = asyncio.Lock()
        self._active: int | None = None
        self._deadline = 0.0
        self._watchdog: asyncio.Task | None = None
        self._timeout = watchdog_seconds

    @property
    def active(self) -> bool:
        return self._active is not None

    def _arm(self) -> None:
        self._deadline = asyncio.get_running_loop().time() + self._timeout
        if self._watchdog is None or self._watchdog.done():
            self._watchdog = asyncio.create_task(self._guard())

    async def start(self, direction: str) -> None:
        if direction not in DIRECTIONS:
            raise ValueError("Invalid PTZ direction")
        async with self._lock:
            if self._active is not None:
                raise RuntimeError("PTZ movement already active")
            code = DIRECTIONS[direction]
            try:
                await self._send("start", code)
            except Exception:
                # Device may have started even if the acknowledgment was lost.
                with suppress(Exception):
                    await self._send("stop", code)
                raise
            self._active = code
            self._arm()

    async def heartbeat(self) -> None:
        async with self._lock:
            if self._active is None:
                raise RuntimeError("PTZ not active")
            self._arm()

    async def _stop_locked(self) -> None:
        if self._active is None:
            return
        code = self._active
        await self._send("stop", code)
        self._active = None
        self._deadline = 0.0

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def pulse(self, direction: str) -> None:
        await self.start(direction)
        try:
            await asyncio.sleep(TAP_SECONDS)
        finally:
            await self.stop()

    async def _guard(self) -> None:
        try:
            while True:
                async with self._lock:
                    if self._active is None:
                        return
                    delay = max(0.0, self._deadline - asyncio.get_running_loop().time())
                if delay:
                    await asyncio.sleep(delay)
                    continue
                # The final deadline check and STOP are serialized against
                # heartbeat updates; no late heartbeat can cause premature STOP.
                async with self._lock:
                    if self._active is None:
                        return
                    if self._deadline > asyncio.get_running_loop().time():
                        continue
                    try:
                        await self._stop_locked()
                    except Exception:
                        pass
                    else:
                        return
                # Retry periodically if the cloud STOP endpoint failed.
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise

    async def close(self) -> None:
        # Attempt cloud STOP first. Do not silently discard active movement.
        try:
            await self.stop()
        finally:
            task = self._watchdog
            if task and task is not asyncio.current_task():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
