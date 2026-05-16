import unittest

from src.flying_shear_app.bootstrap.asyncio_windows import is_windows_proactor_pipe_reset


class AsyncioWindowsTests(unittest.TestCase):
    def test_detects_windows_proactor_pipe_reset_callback(self):
        def callback():
            pass

        callback.__qualname__ = "_ProactorBasePipeTransport._call_connection_lost"
        handle = type("Handle", (), {"_callback": callback})()
        exc = ConnectionResetError(10054, "forcibly closed by the remote host")
        exc.winerror = 10054

        self.assertTrue(
            is_windows_proactor_pipe_reset(
                {
                    "exception": exc,
                    "handle": handle,
                }
            )
        )

    def test_ignores_connection_reset_from_other_callbacks(self):
        def callback():
            pass

        handle = type("Handle", (), {"_callback": callback})()
        exc = ConnectionResetError(10054, "forcibly closed by the remote host")
        exc.winerror = 10054

        self.assertFalse(
            is_windows_proactor_pipe_reset(
                {
                    "exception": exc,
                    "handle": handle,
                }
            )
        )

    def test_ignores_other_proactor_callback_errors(self):
        def callback():
            pass

        callback.__qualname__ = "_ProactorBasePipeTransport._call_connection_lost"
        handle = type("Handle", (), {"_callback": callback})()

        self.assertFalse(
            is_windows_proactor_pipe_reset(
                {
                    "exception": RuntimeError("different failure"),
                    "handle": handle,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
