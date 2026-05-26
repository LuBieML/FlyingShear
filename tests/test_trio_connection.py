import sys
import types
import unittest


if "Trio_UnifiedApi" not in sys.modules:
    fake_uapi = types.ModuleType("Trio_UnifiedApi")

    class _EventType:
        Error = "error"
        Warning = "warning"
        Message = "message"

    class _TrioConnectionError(Exception):
        pass

    fake_uapi.EventType = _EventType
    fake_uapi.TrioConnectionError = _TrioConnectionError
    fake_uapi.TrioConnection = object
    fake_uapi.FileType = types.SimpleNamespace(BASIC="basic")
    fake_uapi.FileTransferOption = lambda value: value
    sys.modules["Trio_UnifiedApi"] = fake_uapi

from src.flying_shear_app.controller.trio_connection import TrioConnection


class FakeUapiConnection:
    def __init__(self):
        self.calls = []
        self.wdog = False
        self.servo = {}

    def SetSystemParameter_WDOG(self, value):
        self.calls.append(("SetSystemParameter_WDOG", bool(value)))
        self.wdog = bool(value)

    def GetSystemParameter_WDOG(self):
        return self.wdog

    def SetAxisParameter_SERVO(self, axis, value):
        self.calls.append(("SetAxisParameter_SERVO", axis, bool(value)))
        self.servo[axis] = bool(value)

    def GetAxisParameter_SERVO(self, axis):
        return self.servo.get(axis, False)


class TrioConnectionEnableTests(unittest.TestCase):
    def make_connected_trio(self):
        trio = TrioConnection(lambda msg, kind: None)
        trio.connection = FakeUapiConnection()
        trio._is_open = True
        return trio

    def test_enable_wdog_and_servo_sets_unique_axes_on(self):
        trio = self.make_connected_trio()

        result = trio.enable_wdog_and_servo([2, "1", 2])

        self.assertEqual(
            trio.connection.calls,
            [
                ("SetAxisParameter_SERVO", 2, True),
                ("SetAxisParameter_SERVO", 1, True),
                ("SetSystemParameter_WDOG", True),
            ],
        )
        self.assertEqual(result["enabled"], True)
        self.assertEqual(result["wdog_enabled"], True)
        self.assertEqual(result["servo_axes"], [2, 1])
        self.assertEqual(result["servo_states"], {2: True, 1: True})

    def test_set_axis_enable_turns_unique_axes_off(self):
        trio = self.make_connected_trio()
        trio.connection.wdog = True
        trio.connection.servo = {2: True, 1: True}

        result = trio.set_axis_enable([2, "1", 2], False)

        self.assertEqual(
            trio.connection.calls,
            [
                ("SetSystemParameter_WDOG", False),
                ("SetAxisParameter_SERVO", 2, False),
                ("SetAxisParameter_SERVO", 1, False),
            ],
        )
        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["wdog_enabled"], False)
        self.assertEqual(result["servo_states"], {2: False, 1: False})

    def test_read_axis_enable_requires_wdog_and_all_servos(self):
        trio = self.make_connected_trio()
        trio.connection.wdog = True
        trio.connection.servo = {2: True, 1: False}

        result = trio.read_axis_enable_state([2, 1])

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["wdog_enabled"], True)
        self.assertEqual(result["servo_states"], {2: True, 1: False})

    def test_enable_wdog_and_servo_rejects_invalid_axes(self):
        trio = self.make_connected_trio()

        with self.assertRaises(ValueError):
            trio.enable_wdog_and_servo(["bad"])

        with self.assertRaises(ValueError):
            trio.enable_wdog_and_servo([-1])

    def test_enable_wdog_and_servo_requires_connection(self):
        trio = TrioConnection(lambda msg, kind: None)

        with self.assertRaises(RuntimeError):
            trio.enable_wdog_and_servo([0])


if __name__ == "__main__":
    unittest.main()
