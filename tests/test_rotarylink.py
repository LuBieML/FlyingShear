import unittest

from src.flying_shear_app.codegen.rotarylink_basic import (
    describe_rotarylink_options,
    emit_rotarylink_basic_program,
)
from src.flying_shear_app.domain.link_options import (
    build_rotarylink_options,
    format_rotarylink,
)
from src.flying_shear_app.domain.rotary_math import (
    compute_rotary_drum_circumference_mm,
    compute_rotary_units_per_mm,
    compute_rotarylink_sync_window_deg,
)
from src.flying_shear_app.domain.rotarylink_math import calculate_rotarylink_profile


class RotaryLinkTests(unittest.TestCase):
    def test_rotarylink_option_encoding(self):
        self.assertEqual(build_rotarylink_options("immediate", "trapezoid", "mpos", False), 0)
        self.assertEqual(build_rotarylink_options("mark", "trapezoid", "mpos", False), 1)
        self.assertEqual(build_rotarylink_options("markb", "trapezoid", "mpos", False), 2)
        self.assertEqual(build_rotarylink_options("rmark", "trapezoid", "mpos", False), 3)
        self.assertEqual(build_rotarylink_options("absolute", "sine", "mpos", False), 4)
        self.assertEqual(build_rotarylink_options("absolute", "power7", "dpos", True), 108)

    def test_rotarylink_format_optional_arguments(self):
        self.assertEqual(
            format_rotarylink(100, 250, 10, 60, "link_ax"),
            "ROTARYLINK(100.000, 250.000, 10.000, 60.000, link_ax)",
        )
        self.assertEqual(
            format_rotarylink(100, 250, 10, 60, "link_ax", 4, 60),
            "ROTARYLINK(100.000, 250.000, 10.000, 60.000, link_ax, 4, 60.000)",
        )

    def test_rotarylink_phase_distances_are_base_axis_phases(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 60, sync_pos=60)

        self.assertAlmostEqual(profile["decel"], 30)
        self.assertAlmostEqual(profile["link_acc"], 25)
        self.assertAlmostEqual(profile["link_sync"], 150)
        self.assertAlmostEqual(profile["link_decel"], 75)
        self.assertAlmostEqual(profile["start_link_pos"], 35)
        self.assertAlmostEqual(profile["sync_end"], 210)

    def test_rotarylink_sync_window_uses_per_knife_segment(self):
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 25, 2), 45.0)
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 25, 1), 90.0)

    def test_rotarylink_sync_window_is_clamped_to_segment(self):
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 125, 2), 180.0)

    def test_rotarylink_units_are_counts_per_circumference_mm(self):
        circumference = compute_rotary_drum_circumference_mm(20)
        self.assertAlmostEqual(circumference, 20 * 3.141592653589793)
        self.assertAlmostEqual(
            compute_rotary_units_per_mm(8_388_608, 20),
            8_388_608 / circumference,
        )

    def test_rotarylink_rejects_bad_sync_positions(self):
        with self.assertRaisesRegex(ValueError, "sync_pos must be greater"):
            calculate_rotarylink_profile(100, 250, 10, 60, sync_pos=25)

        with self.assertRaisesRegex(ValueError, "previous sync phase end"):
            calculate_rotarylink_profile(100, 250, 10, 60, sync_pos=200, previous_sync_end=210)

    def test_rotarylink_basic_buffered_merge_generation(self):
        program = emit_rotarylink_basic_program(
            360,
            360,
            50,
            100,
            link_axis=0,
            base_axis=1,
            link_options=36,
            sync_pos=50,
            include_optional_args=True,
            repeat_mode="buffered_merge",
            merge=True,
            repeat_step=330,
            buffered_commands=2,
        )

        self.assertIn(
            "ROTARYLINK(360.000, 360.000, 50.000, 100.000, link_ax, 36, sync_pos)",
            program,
        )
        self.assertIn(
            "ROTARYLINK(360.000, 360.000, 50.000, 100.000, link_ax, 36, sync_pos + repeat_dist * 1)",
            program,
        )
        self.assertIn("WAIT UNTIL MOVES_BUFFERED < 2", program)

    def test_rotarylink_basic_includes_option_bit_breakdown(self):
        program = emit_rotarylink_basic_program(
            360,
            360,
            50,
            100,
            link_axis=0,
            base_axis=1,
            link_options=108,
            sync_pos=60,
            include_optional_args=True,
        )

        self.assertIn("' link_options bit breakdown:", program)
        self.assertIn("'   decimal value = 108", program)
        self.assertIn("'   set bits = 2, 3, 5, 6", program)
        self.assertIn("'   bits 0..1 = 0: absolute sync position", program)
        self.assertIn("'   bits 2..4 = 3: power 7 polynomial speed profile", program)
        self.assertIn("'   bit 5 = ON: merge consecutive ROTARYLINK commands", program)
        self.assertIn("'   bit 6 = ON: follow master DPOS", program)

    def test_rotarylink_basic_defines_link_axis_before_base_axis_setup(self):
        program = emit_rotarylink_basic_program(
            360,
            360,
            50,
            100,
            link_axis=0,
            base_axis=1,
            link_options=0,
        )

        link_setup = "BASE(link_ax)\nDEFPOS(0)"
        base_setup = "BASE(base_ax)\nSERVO = ON\nDEFPOS(0)"
        self.assertIn(link_setup, program)
        self.assertLess(program.index(link_setup), program.index(base_setup))

    def test_rotarylink_option_breakdown_reports_no_bits(self):
        self.assertEqual(
            describe_rotarylink_options(0),
            [
                "' link_options bit breakdown:",
                "'   decimal value = 0",
                "'   set bits = none",
                "'   bits 0..1 = 0: absolute sync position",
                "'   bits 2..4 = 0: trapezoidal profile",
                "'   bit 5 = OFF: no ROTARYLINK merge",
                "'   bit 6 = OFF: follow master MPOS",
            ],
        )


if __name__ == "__main__":
    unittest.main()
