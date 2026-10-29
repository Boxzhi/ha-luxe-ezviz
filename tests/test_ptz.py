"""Offline contract tests: official PTZ capability and cloud movement safety."""
import asyncio
import importlib.util
from pathlib import Path
import unittest

PATH=Path(__file__).resolve().parents[1]/'custom_components'/'luxe_ezviz'/'ptz_core.py'
spec=importlib.util.spec_from_file_location('ptz_core',PATH)
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class CapabilityTests(unittest.TestCase):
    def test_unknown_never_claims_support(self):
        for data in (None, {}, {'support_ptz': 3}, {'support_ptz': 'unknown'}, []) :
            self.assertEqual(core.parse_ptz_capability(data)['known'],False)
            self.assertFalse(core.parse_ptz_capability(data)['supported'])
    def test_explicit_zero_is_hidden(self):
        self.assertEqual(core.parse_ptz_capability({'support_ptz': 0}),
                         {'supported': False,'known': True,'directions': []})
    def test_supported_legacy_and_axes(self):
        self.assertEqual(core.parse_ptz_capability({'support_ptz':1})['directions'],
                         ['up','down','left','right'])
        self.assertEqual(core.parse_ptz_capability({'support_ptz':'1','ptz_top_bottom':0,'ptz_left_right':1})['directions'],
                         ['left','right'])
        self.assertEqual(core.parse_ptz_capability({'support_ptz':1,'ptz_top_bottom':1,'ptz_left_right':0})['directions'],
                         ['up','down'])

class MovementTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_tap_starts_then_stops(self):
        calls=[]
        async def sender(action,direction): calls.append((action,direction))
        ctrl=core.PtzController(sender,watchdog_seconds=0.15)
        # Shorten test-only pulse duration, preserving start/stop ordering.
        old=core.TAP_SECONDS
        core.TAP_SECONDS=0.015
        try: await ctrl.pulse('up')
        finally: core.TAP_SECONDS=old
        self.assertEqual(calls,[('start',0),('stop',0)])
        self.assertFalse(ctrl.active)
        await ctrl.close()
    async def test_long_hold_heartbeat_and_stop(self):
        calls=[]
        async def sender(action,direction):calls.append((action,direction))
        ctrl=core.PtzController(sender,watchdog_seconds=0.12)
        await ctrl.start('right')
        await asyncio.sleep(0.065)
        await ctrl.heartbeat()
        await asyncio.sleep(0.07)
        self.assertTrue(ctrl.active)
        await ctrl.stop()
        self.assertEqual(calls,[('start',3),('stop',3)])
        await ctrl.close()
    async def test_disconnect_watchdog_forces_stop(self):
        calls=[]
        async def sender(action,direction):calls.append((action,direction))
        ctrl=core.PtzController(sender,watchdog_seconds=0.035)
        await ctrl.start('down')
        await asyncio.sleep(0.09)
        self.assertEqual(calls,[('start',1),('stop',1)])
        self.assertFalse(ctrl.active)
        await ctrl.close()
    async def test_failed_start_attempts_emergency_stop(self):
        calls=[]
        async def sender(action,direction):
            calls.append((action,direction))
            if action=='start':raise OSError('timeout')
        ctrl=core.PtzController(sender)
        with self.assertRaises(OSError):await ctrl.start('left')
        self.assertEqual(calls,[('start',2),('stop',2)])
        await ctrl.close()
    async def test_watchdog_retries_stop_after_transient_cloud_error(self):
        calls=[]
        stop_failures=1
        async def sender(action,direction):
            nonlocal stop_failures
            calls.append((action,direction))
            if action=='stop' and stop_failures:
                stop_failures-=1
                raise OSError('temporary cloud disconnect')
        ctrl=core.PtzController(sender,watchdog_seconds=0.025)
        await ctrl.start('left')
        await asyncio.sleep(0.6)
        self.assertFalse(ctrl.active)
        self.assertEqual(calls,[('start',2),('stop',2),('stop',2)])
        await ctrl.close()
    async def test_two_cameras_are_isolated(self):
        calls=[]
        async def a(action,direction):calls.append(('a',action,direction))
        async def b(action,direction):calls.append(('b',action,direction))
        ca=core.PtzController(a);cb=core.PtzController(b)
        await ca.start('up');await cb.start('left');await ca.stop()
        self.assertTrue(cb.active)
        await cb.stop()
        self.assertEqual(calls,[('a','start',0),('b','start',2),('a','stop',0),('b','stop',2)])
        await ca.close();await cb.close()
    async def test_blocks_second_start_until_stopped(self):
        calls=[]
        async def send(action,direction):calls.append((action,direction))
        ctrl=core.PtzController(send)
        await ctrl.start('up')
        with self.assertRaises(RuntimeError):await ctrl.start('down')
        await ctrl.stop();await ctrl.close()
        self.assertEqual(calls,[('start',0),('stop',0)])

if __name__=='__main__':unittest.main()
