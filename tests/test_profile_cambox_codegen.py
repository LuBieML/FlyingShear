from pathlib import Path
from dataclasses import replace
import tempfile
import unittest

from src.profile_cambox_app.codegen import emit_points_csv, emit_trio_basic
from src.profile_cambox_app.domain import ProfileConfig, convert_profile, load_profile_csv


class ProfileCamboxCodegenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "profile.csv"
        path.write_text("temps,Y,C\n0,244,2.5\n0.004,245,2.4\n0.008,246,2.3\n", encoding="utf-8")
        self.profile = convert_profile(load_profile_csv(path), ProfileConfig())

    def test_emits_two_separate_one_shot_cambox_commands(self):
        basic = emit_trio_basic(self.profile)
        self.assertIn("CAMBOX(1000, 1002, 1, profile_link_dist, master_ax, link_options, profile_start) AXIS(0)", basic)
        self.assertIn("CAMBOX(3000, 3002, 1, profile_link_dist, master_ax, link_options, profile_start) AXIS(1)", basic)
        self.assertIn("link_options = 8194", basic)
        self.assertNotIn("link_options = 4", basic)
        self.assertIn("FORWARD AXIS(10)", basic)

    def test_prepositions_absolute_source_values(self):
        basic = emit_trio_basic(self.profile)
        self.assertIn("MOVEABS(244) AXIS(0)", basic)
        self.assertIn("MOVEABS(1432.394487827) AXIS(1)", basic)

    def test_points_csv_is_auditable(self):
        exported = emit_points_csv(self.profile)
        self.assertIn("master_mm", exported.splitlines()[0])
        self.assertIn("c_relative_user_units", exported.splitlines()[0])
        self.assertEqual(len(exported.splitlines()), 4)

    def test_demo_start_precedes_absolute_moves_and_converts_c_units(self):
        for unit, expected_c in ((1, "138.239448783"), (.1, "1382.394487827")):
            cfg = replace(self.profile.config, c_user_unit_deg=unit,
                          demo_y_preposition=True, demo_c_preposition=True,
                          y_axis=3, c_axis=4)
            basic = emit_trio_basic(convert_profile(self.profile.source, cfg))
            self.assertIn("DEFPOS(239) AXIS(3)\nWAIT UNTIL OFFPOS AXIS(3) = 0", basic)
            self.assertIn(f"DEFPOS({expected_c}) AXIS(4)\nWAIT UNTIL OFFPOS AXIS(4) = 0", basic)
            self.assertLess(basic.index(f"DEFPOS({expected_c})"), basic.index("MOVEABS(244)"))

    def test_demo_defaults_off_and_axes_can_be_enabled_independently(self):
        basic = emit_trio_basic(self.profile)
        self.assertEqual(basic.count("DEFPOS("), 1)  # virtual master only
        for y, c in ((True, False), (False, True)):
            cfg = replace(self.profile.config, demo_y_preposition=y, demo_c_preposition=c)
            basic = emit_trio_basic(convert_profile(self.profile.source, cfg))
            self.assertEqual(basic.count("DEFPOS("), 2)
            self.assertEqual("DEFPOS(239) AXIS(0)" in basic, y)


if __name__ == "__main__":
    unittest.main()
