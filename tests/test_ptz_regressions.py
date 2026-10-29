"""Release-blocker tests for uncertain cloud PTZ START and STOP."""
import asyncio
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components" / "luxe_ezviz" / "ptz_core.py"
spec = importlib.util.spec_from_file_location("luxe_ptz_regression_core", PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class UncertainMovementTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_timeout_and_failed_compensation_remains_guarded(self):
        events = []
        stop_failures = 2

        async def send(action, direction):
            nonlocal stop_failures
            events.append((action, direction))
            if action == "start":
                raise TimeoutError("acknowledgement lost")
            if action == "stop" and stop_failures:
                stop_failures -= 1
                raise OSError("temporary stop failure")

        ctrl = core.PtzController(send, watchdog_seconds=.025)
        with self.assertRaises(TimeoutError):
            await ctrl.start("up")
        self.assertTrue(ctrl.active, "uncertain START must retain movement state")
        with self.assertRaises(RuntimeError):
            await ctrl.start("right")
        await asyncio.sleep(.67)
        self.assertFalse(ctrl.active, "watchdog must eventually confirm STOP")
        self.assertEqual(events, [
            ("start", 0), ("stop", 0), ("stop", 0), ("stop", 0)
        ])
        await ctrl.close()

    async def test_start_timeout_successful_compensation_clears_state(self):
        events = []

        async def send(action, direction):
            events.append((action, direction))
            if action == "start":
                raise TimeoutError("ack lost")

        ctrl = core.PtzController(send, watchdog_seconds=.025)
        with self.assertRaises(TimeoutError):
            await ctrl.start("left")
        self.assertFalse(ctrl.active)
        await asyncio.sleep(.05)
        self.assertEqual(events, [("start", 2), ("stop", 2)])
        await ctrl.close()

    async def test_close_stop_failure_preserves_retry_guard(self):
        events = []
        stop_failures = 1

        async def send(action, direction):
            nonlocal stop_failures
            events.append((action, direction))
            if action == "stop" and stop_failures:
                stop_failures -= 1
                raise OSError("cloud STOP unavailable")

        ctrl = core.PtzController(send, watchdog_seconds=.035)
        await ctrl.start("down")
        with self.assertRaises(OSError):
            await ctrl.close()
        self.assertTrue(ctrl.active, "close cannot discard unconfirmed STOP")
        await asyncio.sleep(.14)
        self.assertFalse(ctrl.active)
        self.assertEqual(events, [("start", 1), ("stop", 1), ("stop", 1)])
        await ctrl.close()

    async def test_start_cancellation_still_compensates(self):
        events = []
        entered = asyncio.Event()

        async def send(action, direction):
            events.append((action, direction))
            if action == "start":
                entered.set()
                await asyncio.Future()

        ctrl = core.PtzController(send, watchdog_seconds=.035)
        job = asyncio.create_task(ctrl.start("right"))
        await entered.wait()
        job.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await job
        self.assertFalse(ctrl.active)
        self.assertEqual(events, [("start", 3), ("stop", 3)])
        await ctrl.close()


class SourceGuardTests(unittest.TestCase):
    def test_pointer_cancel_does_not_erase_hold_stop(self):
        src = (ROOT / "custom_components/luxe_ezviz/frontend/player.html").read_text()
        self.assertIn("release(event,true)", src)
        self.assertNotIn(
            "if(ptzPress?.id===event.pointerId)ptzPress.mode='cancelled'", src
        )
        self.assertIn("press.mode==='hold'&&stop", src)
        self.assertIn("void ptzStop();", src)

    def test_navigation_has_no_hardcoded_dashboard_route(self):
        src = (ROOT / "custom_components/luxe_ezviz/frontend/luxe-ezviz-card.js").read_text()
        self.assertNotIn("cameras-2", src)
        self.assertIn("this._attachedRoute", src)
        self.assertIn("route!==activeRoute", src)

    def test_unload_refuses_unconfirmed_stop(self):
        src = (ROOT / "custom_components/luxe_ezviz/__init__.py").read_text()
        self.assertIn("refusing entry unload", src)
        self.assertIn("return False", src)


if __name__ == "__main__":
    unittest.main()
