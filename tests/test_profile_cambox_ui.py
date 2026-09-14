"""Exercise actual UI callbacks to prevent exporting stale settings."""
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import flet as ft
import matplotlib.pyplot as plt

from src.profile_cambox_app import app
from src.profile_cambox_app.domain import ProfileConfig
from tests.test_profile_cambox_navigation import test_navigation_keeps_chart_pages_mounted_and_stops_playback


def walk(control, seen=None):
    seen = set() if seen is None else seen
    if not isinstance(control, ft.Control) or id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for value in (getattr(control, key, None) for key in ("controls", "content", "tabs")):
        for child in value if isinstance(value, (tuple, list)) else [value]:
            yield from walk(child, seen)


class ProfileUiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(plt.close, "all")
        self.csv = Path(self.directory.name) / "input.csv"
        self.csv.write_text("temps,Y,C\n0,0,0\n0.5,5,0.5\n1,10,1\n")
        self.roots = []
        self.page = SimpleNamespace(window=SimpleNamespace(), services=[],
                                    add=self.roots.append, update=lambda: None,
                                    show_dialog=lambda _: None,
                                    clipboard=SimpleNamespace(set=AsyncMock()))
        self.save = patch.object(app, "save_config").start()
        self.addCleanup(patch.stopall)
        with patch.dict(app.os.environ, {"PROFILE_CAMBOX_INPUT": str(self.csv)}), patch.object(
            app, "load_config", return_value=ProfileConfig()
        ):
            app.main(self.page)
        self.controls = list(walk(self.roots[0]))

    def find(self, label):
        return next(c for c in self.controls if getattr(c, "label", None) == label
                    or getattr(c, "content", None) == label)

    def change(self, label, value):
        control = self.find(label)
        control.value = value
        control.on_change(None)

    def test_copy_uses_current_mechanical_settings(self):
        self.change("Y counts/rev", "65535")
        self.change("Y screw lead", "10")
        self.change("Y motor turns", "4")
        self.change("Y output turns", "2")
        self.change("C counts/rev", "65535")
        self.change("C motor turns", "20")
        self.change("C output turns", "2")
        self.change("C user unit", "1")
        asyncio.run(self.find("Copy BASIC").on_click(None))
        basic = self.page.clipboard.set.call_args.args[0]
        self.assertIn("REP_DIST = 655350", basic)
        self.assertIn("UNITS = 1820.416666667", basic)
        self.assertIn("UNITS = 13107", basic)
        self.assertEqual(self.save.call_args.args[0].c_degrees_per_rev, 36)

    def test_export_rechecks_changes_made_during_picker(self):
        async def choose_directory(*args, **kwargs):
            self.change("Y counts/rev", "65535")
            return self.directory.name
        with patch.object(ft.FilePicker, "get_directory_path", side_effect=choose_directory):
            asyncio.run(self.find("Export BASIC + points").on_click(None))
        basic = (Path(self.directory.name) / "profile_cambox_one_shot.bas").read_text()
        self.assertIn("UNITS = 16383.75", basic)

    def test_invalid_edits_cannot_copy_old_basic(self):
        self.change("C output turns", "0")
        asyncio.run(self.find("Copy BASIC").on_click(None))
        self.page.clipboard.set.assert_not_called()

    def test_navigation_regression(self):
        test_navigation_keeps_chart_pages_mounted_and_stops_playback()


if __name__ == "__main__":
    unittest.main()
