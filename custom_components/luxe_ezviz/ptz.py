"""HA-authenticated PTZ endpoints. Device identity stays server-side."""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.helpers.http import KEY_HASS

from .api import EzvizAuthError, EzvizApiError, EzvizConnectionError
from .const import CONF_CHANNEL, CONF_DEVICE_SERIAL, DOMAIN
from .http import _get_runtime, _selection_error, _response
from .ptz_core import PtzController, parse_ptz_capability, DIRECTIONS

_LOGGER = logging.getLogger(__name__)


def _controller(hass, entry, runtime) -> PtzController:
    if not hasattr(runtime, 'ptz_controller') or runtime.ptz_controller is None:
        serial = entry.data[CONF_DEVICE_SERIAL]
        channel = int(entry.data[CONF_CHANNEL])
        async def send(action: str, direction: int) -> None:
            await runtime.token_manager.async_ptz_control(serial, channel, action, direction)
        runtime.ptz_controller = PtzController(send)
    return runtime.ptz_controller


async def _capability(runtime, serial: str) -> dict:
    loop = asyncio.get_running_loop()
    when = getattr(runtime, 'ptz_capacity_at', 0.0)
    if when and loop.time()-when < 900:
        return runtime.ptz_capacity
    if not hasattr(runtime, 'ptz_capacity_lock'):
        runtime.ptz_capacity_lock = asyncio.Lock()
    async with runtime.ptz_capacity_lock:
        when = getattr(runtime, 'ptz_capacity_at', 0.0)
        if when and loop.time()-when < 900:
            return runtime.ptz_capacity
        raw = await runtime.token_manager.async_ptz_capability(serial)
        capacity = parse_ptz_capability(raw)
        # Do not cache unknown capabilities; retry next opening.
        if capacity['known']:
            runtime.ptz_capacity = capacity
            runtime.ptz_capacity_at = loop.time()
        return capacity


class LuxeEzvizPtzCapabilityView(HomeAssistantView):
    url = '/api/luxe_ezviz/ptz/capability'
    name = 'api:luxe_ezviz:ptz:capability'
    requires_auth = True

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry, runtime, error = _get_runtime(hass, request.query.get('device_serial'))
        if error:
            return _selection_error(self,error)
        try:
            capability = await _capability(runtime,entry.data[CONF_DEVICE_SERIAL])
            return _response(self,{'ok': True, **capability})
        except (EzvizAuthError, EzvizApiError, EzvizConnectionError):
            return _response(self,{'ok':False,'supported':False,'known':False,'directions':[], 'reason':'ptz_capability_unavailable'},503)


class LuxeEzvizPtzControlView(HomeAssistantView):
    url = '/api/luxe_ezviz/ptz/control'
    name = 'api:luxe_ezviz:ptz:control'
    requires_auth = True

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except (ValueError, TypeError):
            data = None
        if not isinstance(data,dict) or data.get('action') not in {'pulse','start','stop','heartbeat'}:
            return _response(self,{'ok':False,'reason':'invalid_ptz_request'},400)
        hass = request.app[KEY_HASS]
        entry, runtime, error = _get_runtime(hass,data.get('device_serial'))
        if error:
            return _selection_error(self,error)
        action = data['action']
        direction = data.get('direction')
        if action in {'start','pulse'} and direction not in DIRECTIONS:
            return _response(self,{'ok':False,'reason':'invalid_ptz_direction'},400)
        controller = _controller(hass,entry,runtime)
        # Stop and heartbeat must remain usable if a subsequent capability
        # request fails. Never block an emergency STOP on cloud checks.
        if action in {'start','pulse'}:
            try:
                capability = await _capability(runtime,entry.data[CONF_DEVICE_SERIAL])
            except (EzvizAuthError, EzvizApiError, EzvizConnectionError):
                return _response(self,{'ok':False,'reason':'ptz_capability_unavailable'},503)
            if not capability['supported'] or direction not in capability['directions']:
                return _response(self,{'ok':False,'reason':'ptz_not_supported'},403)
        try:
            if action == 'start':
                await controller.start(direction)
            elif action == 'pulse':
                await controller.pulse(direction)
            elif action == 'heartbeat':
                await controller.heartbeat()
            elif action == 'stop':
                await controller.stop()
        except RuntimeError:
            return _response(self,{'ok':False,'reason':'ptz_busy'},409)
        except (EzvizAuthError, EzvizConnectionError, EzvizApiError):
            return _response(self,{'ok':False,'reason':'ptz_cloud_error'},503)
        except Exception:
            _LOGGER.exception('PTZ operation failed without exposing device credentials')
            return _response(self,{'ok':False,'reason':'ptz_operation_failed'},503)
        return _response(self,{'ok':True})
