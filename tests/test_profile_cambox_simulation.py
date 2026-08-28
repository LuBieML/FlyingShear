import math
from pathlib import Path
import tempfile
import unittest

from src.profile_cambox_app.domain import ProfileError, convert_profile, load_profile_csv
from src.profile_cambox_app.simulation import build_simulation_series, finite_difference


class ProfileCamboxSimulationTests(unittest.TestCase):
    def _profile(self):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "profile.csv"
        path.write_text(
            "temps,Y,C\n"
            "0.0,10.0,0.0\n"
            f"0.5,11.0,{math.pi / 2}\n"
            f"1.0,14.0,{math.pi}\n",
            encoding="utf-8",
        )
        self.addCleanup(directory.cleanup)
        return convert_profile(load_profile_csv(path))

    def test_finite_difference_uses_central_samples(self):
        result = finite_difference((0.0, 1.0, 4.0), (0.0, 1.0, 2.0))
        self.assertEqual(result, (1.0, 2.0, 3.0))

    def test_combined_path_translates_y_and_rotates_c(self):
        series = build_simulation_series(self._profile(), radius_mm=2.0)

        self.assertAlmostEqual(series.path_x_mm[0], 2.0)
        self.assertAlmostEqual(series.path_y_mm[0], 10.0)
        self.assertAlmostEqual(series.path_x_mm[1], 0.0, places=7)
        self.assertAlmostEqual(series.path_y_mm[1], 13.0)
        self.assertAlmostEqual(series.path_x_mm[2], -2.0)
        self.assertAlmostEqual(series.path_y_mm[2], 14.0, places=7)
        self.assertEqual(series.y_speed_mm_s, (2.0, 4.0, 6.0))
        self.assertEqual(series.c_speed_deg_s, (180.0, 180.0, 180.0))

    def test_angle_offset_rotates_the_reference_point(self):
        series = build_simulation_series(self._profile(), radius_mm=2.0, angle_offset_deg=90.0)
        self.assertAlmostEqual(series.path_x_mm[0], 0.0, places=7)
        self.assertAlmostEqual(series.path_y_mm[0], 12.0)

    def test_invalid_radius_is_rejected(self):
        with self.assertRaisesRegex(ProfileError, "radius"):
            build_simulation_series(self._profile(), radius_mm=0.0)


if __name__ == "__main__":
    unittest.main()
