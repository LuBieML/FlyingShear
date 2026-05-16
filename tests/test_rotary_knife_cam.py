import math
import unittest

from src.flying_shear_app.codegen.cambox_basic import emit_cam_basic_program
from src.flying_shear_app.domain.cambox_math import generate_rotary_knife_cam_table
from src.flying_shear_app.domain.rotary_math import compute_rotary_cutting_radius_px


class RotaryKnifeCamTests(unittest.TestCase):
    def test_cam_diagnostics_include_drum_units_from_circumference(self):
        encoder_counts_per_rev = 8_388_608
        table, diag = generate_rotary_knife_cam_table(
            cut_length_mm=100,
            drum_diameter_mm=20,
            n_knives=1,
            cut_window_deg=30,
            encoder_counts_per_rev=encoder_counts_per_rev,
            n_points=720,
            blend_fraction=0.4,
            line_speed_mm_s=500,
        )

        circumference = math.pi * 20
        self.assertEqual(table[-1], encoder_counts_per_rev)
        self.assertAlmostEqual(diag["drum_circumference"], circumference)
        self.assertAlmostEqual(
            diag["drum_axis_units_per_mm"],
            encoder_counts_per_rev / circumference,
        )

    def test_cam_basic_comments_report_calculated_units(self):
        table, diag = generate_rotary_knife_cam_table(
            cut_length_mm=100,
            drum_diameter_mm=20,
            n_knives=1,
            cut_window_deg=30,
            encoder_counts_per_rev=8_388_608,
            n_points=720,
            blend_fraction=0.4,
            line_speed_mm_s=500,
        )

        program = emit_cam_basic_program(
            table,
            diag,
            cut_length=100,
            link_axis=0,
            drum_axis=1,
            table_start=1000,
            cutter_op=8,
        )

        self.assertIn(
            "' Drum axis UNITS for mm: 133508.843 counts/mm",
            program,
        )

    def test_rotary_visual_cutting_radius_uses_conveyor_scale(self):
        self.assertAlmostEqual(
            compute_rotary_cutting_radius_px(
                drum_diameter_mm=20,
                scale_px_per_unit=2,
                link_units_to_mm=1,
            ),
            20.0,
        )
        self.assertAlmostEqual(
            compute_rotary_cutting_radius_px(
                drum_diameter_mm=20,
                scale_px_per_unit=45,
                link_units_to_mm=10,
            ),
            45.0,
        )


if __name__ == "__main__":
    unittest.main()
