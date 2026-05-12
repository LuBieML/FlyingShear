"""Windows timer-resolution helpers used by animation loops."""

import ctypes
import sys


def begin_windows_timer_resolution(period_ms=1):
    if sys.platform == "win32":
        ctypes.windll.winmm.timeBeginPeriod(int(period_ms))


def end_windows_timer_resolution(period_ms=1):
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.timeEndPeriod(int(period_ms))
        except Exception:
            pass
