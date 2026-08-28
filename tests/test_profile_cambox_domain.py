import math
from pathlib import Path
import tempfile
import unittest

from src.profile_cambox_app.domain import ProfileConfig, ProfileError, convert_profile, load_profile_csv


CSV_TEXT = """temps,Y,C
0.000,10.0,1.5707963267948966
0.004,10.5,1.5533430342749532
0.008,11.0,1.53588974175501
"""


class ProfileCamboxDomainTests(unittest.TestCase):
    def _load(self, text=CSV_TEXT):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "profile.csv"
        path.write_text(text, encoding="utf-8")
        raw = load_profile_csv(path)
        self.addCleanup(directory.cleanup)
        return raw

    def test_default_scaling_and_relative_counts(self):
        profile = convert_profile(self._load(), ProfileConfig())

        self.assertEqual(profile.config.master_units_counts_per_mm, 2_097_152)
        self.assertAlmostEqual(profile.config.c_units_counts_per_user_unit, 2330.1688888889)
        self.assertEqual(profile.points[1].master_mm, 0.32)
        self.assertEqual(profile.points[1].y_counts, 1_048_576)
        self.assertEqual(profile.points[1].c_counts, -23_302)
        self.assertEqual(profile.diagnostics.link_distance_mm, 0.64)

    def test_nonuniform_time_is_rejected(self):
        raw = self._load("temps,Y,C\n0,0,0\n0.004,1,0.1\n0.010,2,0.2\n")
        with self.assertRaisesRegex(ProfileError, "not uniformly spaced"):
            convert_profile(raw)

    def test_table_overlap_is_rejected(self):
        raw = self._load()
        config = ProfileConfig(y_table_start=100, c_table_start=102)
        with self.assertRaisesRegex(ProfileError, "overlaps"):
            convert_profile(raw, config)

    def test_rotary_unwrap_uses_short_continuous_path(self):
        raw = self._load("temps,Y,C\n0,0,3.13\n0.004,0,-3.13\n0.008,0,-3.12\n")
        profile = convert_profile(raw)
        self.assertLess(abs(profile.points[1].c_relative_deg), 2.0)


if __name__ == "__main__":
    unittest.main()
