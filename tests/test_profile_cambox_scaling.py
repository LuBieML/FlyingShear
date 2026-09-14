"""Mechanical scaling, commanded preview, and wrap boundary regressions."""
from dataclasses import replace
import math
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch

from src.profile_cambox_app.domain import ProfileConfig, ProfileError, RawProfile, convert_profile, parse_gear_ratio
from src.profile_cambox_app import settings
from src.profile_cambox_app.codegen import emit_trio_basic
from src.profile_cambox_app.simulation import build_simulation_series


class MechanicalScalingTests(unittest.TestCase):
    def setUp(self):
        self.raw = RawProfile(Path("synthetic.csv"), ("temps", "Y", "C"),
                              (0., .5, 1.), (10., 15., 20.),
                              (0., math.pi / 2, math.pi))
        self.cfg = ProfileConfig(y_encoder_counts_per_rev=65535,
                                 y_travel_per_rev_mm=10,
                                 c_encoder_counts_per_rev=65535,
                                 c_degrees_per_rev=36, c_user_unit_deg=1)

    def test_customer_counts_and_wrap_are_independent(self):
        p = convert_profile(self.raw, self.cfg)
        self.assertEqual(p.y_table_values[-1], 65535)
        self.assertEqual(p.c_table_values[-1], 327675)
        self.assertEqual(self.cfg.y_units_counts_per_mm, 6553.5)
        self.assertAlmostEqual(self.cfg.c_units_counts_per_user_unit, 1820.4166666667)
        basic = emit_trio_basic(p)
        self.assertIn("UNITS = 1\nREP_OPTION = 0\nREP_DIST = 655350\nUNITS = 1820.416666667", basic)
        self.assertEqual(self.cfg.c_full_revolution_user_units, 360)

    def test_user_units_do_not_change_physical_rotation_or_table_counts(self):
        p = convert_profile(self.raw, self.cfg)
        tenths = convert_profile(self.raw, replace(self.cfg, c_user_unit_deg=.1))
        self.assertEqual(p.c_table_values, tenths.c_table_values)
        self.assertEqual(build_simulation_series(p), build_simulation_series(tenths))
        self.assertAlmostEqual(tenths.config.c_units_counts_per_user_unit, 182.0416666667)

    def test_resolution_and_master_changes_preserve_duration_and_motion(self):
        for counts in (65535, 65536, 131072, 8388608):
            with self.subTest(counts=counts):
                cfg = replace(self.cfg, master_encoder_counts_per_rev=counts,
                              master_speed_mm_s=37, y_encoder_counts_per_rev=counts,
                              c_encoder_counts_per_rev=counts)
                p = convert_profile(self.raw, cfg)
                self.assertEqual(p.diagnostics.link_distance_mm / cfg.master_speed_mm_s, 1)
                self.assertAlmostEqual(p.points[-1].y_commanded_mm, 20)
                self.assertAlmostEqual(p.points[-1].c_commanded_deg, 180)

    def test_preview_reconstructs_inverted_quantized_commands(self):
        cfg = replace(self.cfg, invert_y=True, invert_c=True,
                      y_encoder_counts_per_rev=7, c_encoder_counts_per_rev=7)
        p = convert_profile(self.raw, cfg)
        series = build_simulation_series(p)
        for i, point in enumerate(p.points):
            self.assertEqual(series.y_mm[i], 10 + point.y_counts / cfg.y_units_counts_per_mm)
            self.assertEqual(series.c_deg[i], point.c_counts / cfg.c_counts_per_degree)
        self.assertEqual(series.y_mm[-1], 0)
        self.assertEqual(series.c_deg[-1], -180)
        self.assertEqual(p.diagnostics.y_end_mm, series.y_mm[-1])

    def test_wrap_rejects_crossing_and_allows_larger_unwrapped_range(self):
        with self.assertRaisesRegex(ProfileError, "wrap boundary"):
            convert_profile(self.raw, replace(self.cfg, c_wrap_distance_deg=180))
        raw = replace(self.raw, c_rad=(0., math.pi, 2 * math.pi))
        with self.assertRaisesRegex(ProfileError, "wrap boundary"):
            convert_profile(raw, self.cfg)
        p = convert_profile(raw, replace(self.cfg, c_wrap_distance_deg=720))
        self.assertEqual(p.points[-1].c_commanded_deg, 360)

    def test_wrap_setting_is_validated(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ProfileError):
                convert_profile(self.raw, replace(self.cfg, c_wrap_distance_deg=value))

    def test_explicit_gearing_matches_legacy_and_scales_screw(self):
        cfg = ProfileConfig(y_encoder_counts_per_rev=65535, y_travel_per_rev_mm=10,
                            y_gear_ratio=2, c_encoder_counts_per_rev=65535,
                            c_gear_ratio=10, c_user_unit_deg=1)
        p = convert_profile(self.raw, cfg)
        self.assertEqual(p.c_table_values, convert_profile(self.raw, self.cfg).c_table_values)
        self.assertEqual(p.y_table_values[-1], 131070)
        self.assertEqual(p.points[-1].y_commanded_mm, 20)
        self.assertEqual(cfg.c_degrees_per_rev, 36)
        self.assertEqual(cfg.c_wrap_counts, 655350)

    def test_ratio_syntax_and_validation(self):
        for text, expected in (("10", 10), ("10:1", 10), ("3 : 2", 1.5), ("1:2", .5)):
            self.assertEqual(parse_gear_ratio(text), expected)
        for text in ("0", "-1", "1:0", "-1:-1", "nan", "inf:1", "1:inf", "1:2:3", ""):
            with self.subTest(text=text), self.assertRaises(ProfileError):
                parse_gear_ratio(text)
        for key in ("y_gear_ratio", "c_gear_ratio"):
            for value in (0, -1, float("nan"), float("inf")):
                with self.subTest(key=key, value=value), self.assertRaises(ProfileError):
                    convert_profile(self.raw, replace(self.cfg, **{key: value}))

    def test_legacy_settings_migrate_and_roundtrip_without_double_gearing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"c_degrees_per_rev": 36, "y_travel_per_rev_mm": 5}))
            with patch.object(settings, "SETTINGS_FILE", path):
                legacy = settings.load_config()
                self.assertEqual(legacy.c_gear_ratio, 10)
                self.assertEqual(legacy.y_gear_ratio, 1)
                settings.save_config(legacy)
                reloaded = settings.load_config()
                self.assertEqual(reloaded.to_dict(), legacy.to_dict())
                self.assertEqual(reloaded.c_counts_per_degree, legacy.c_counts_per_degree)


if __name__ == "__main__":
    unittest.main()
