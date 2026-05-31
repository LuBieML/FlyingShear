import unittest

from src.flying_shear_app.domain.cambox_math import (
    build_rotary_knife_cambox_commands,
    emit_rotary_knife_cambox_only,
    generate_rotary_knife_cam_table,
)


class RotaryKnifeCamBoxCommandTests(unittest.TestCase):
    def test_cambox_only_command_uses_table_range_and_cut_length(self):
        table, diag = generate_rotary_knife_cam_table(
            cut_length_mm=100,
            drum_diameter_mm=20,
            n_knives=1,
            cut_window_deg=30,
            encoder_counts_per_rev=10000,
            n_points=36,
            blend_fraction=0.4,
            line_speed_mm_s=500,
        )
        commands = build_rotary_knife_cambox_commands(
            table,
            diag,
            cut_length=100,
            link_axis=0,
            table_start=1000,
        )

        self.assertEqual(
            emit_rotary_knife_cambox_only(commands),
            "CAMBOX(1000, 1036, 1, 100.000, 0, 4)",
        )
        self.assertIn("TABLE(1000..1036)", commands[0].table_summary)

    def test_cambox_end_point_provenance_describes_table_count(self):
        table, diag = generate_rotary_knife_cam_table(
            cut_length_mm=120,
            drum_diameter_mm=25,
            n_knives=2,
            cut_window_deg=20,
            encoder_counts_per_rev=20000,
            n_points=40,
            blend_fraction=0.35,
            line_speed_mm_s=400,
        )
        commands = build_rotary_knife_cambox_commands(
            table,
            diag,
            cut_length=120,
            link_axis=3,
            table_start=250,
        )

        end_point = commands[0].parameters[1]
        self.assertEqual(end_point.name, "end_point")
        self.assertEqual(end_point.text, "290")
        self.assertEqual(end_point.source.formula, "end_point = table_start + generated_table_count - 1")
        self.assertEqual(end_point.source.substitution, "250 + 41 - 1 = 290")
        self.assertIn("count = table_points + 1", end_point.source.details[1])


if __name__ == "__main__":
    unittest.main()
