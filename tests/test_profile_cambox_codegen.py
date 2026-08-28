from pathlib import Path
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
        self.assertIn("c_relative_0.1deg", exported.splitlines()[0])
        self.assertEqual(len(exported.splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
