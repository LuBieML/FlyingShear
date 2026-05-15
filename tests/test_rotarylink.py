import math
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
from src.flying_shear_app.domain.rotarylink_math import (
    calculate_rotarylink_base_sync_speed,
    calculate_rotarylink_profile,
    derive_rotarylink_geometry,
    estimate_rotarylink_slave_accel,
    validate_rotarylink_profile,
)


class RotaryLinkTests(unittest.TestCase):
    def assert_rotarylink_totals(self, profile):
        self.assertAlmostEqual(
            profile["acc"] + profile["sync"] + profile["base_decel"] + profile["base_idle"],
            profile["distance"],
        )
        self.assertAlmostEqual(
            profile["link_acc"] + profile["link_sync"] + profile["link_decel"] + profile["link_idle"],
            profile["link_dist"],
        )

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
        profile = calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=80)

        self.assertAlmostEqual(profile["base_decel"], 30)
        self.assertAlmostEqual(profile["base_idle"], 0)
        self.assertAlmostEqual(profile["link_acc"], 20)
        self.assertAlmostEqual(profile["link_sync"], 60)
        self.assertAlmostEqual(profile["link_decel"], 60)
        self.assertAlmostEqual(profile["link_idle"], 110)
        self.assertAlmostEqual(profile["start_link_pos"], 80 - profile["link_acc"])
        self.assertAlmostEqual(profile["sync_end"], 80 + profile["link_sync"])
        self.assertEqual(
            [phase["name"] for phase in profile["phase_segments"]],
            ["acc", "sync", "decel", "idle"],
        )
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_sync_phase_is_always_one_to_one(self):
        profile = calculate_rotarylink_profile(62.832, 330, 10, 8, 10)

        self.assertAlmostEqual(profile["base_sync"], 8)
        self.assertAlmostEqual(profile["link_sync"], 8)
        self.assertAlmostEqual(calculate_rotarylink_base_sync_speed(500, profile), 500)

    def test_rotarylink_worked_example_regression(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 330)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["link_dist"],
            10,
            8,
            10,
        )
        base_sync_speed = calculate_rotarylink_base_sync_speed(500, profile)
        est_slave_accel = estimate_rotarylink_slave_accel(500, profile)
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(geometry["circumference"], math.pi * 20)
        self.assertAlmostEqual(geometry["distance"], math.pi * 20)
        self.assertAlmostEqual(geometry["link_dist"], 330)
        self.assertAlmostEqual(profile["base_idle"], math.pi * 20 - 10 - 8 - 10)
        self.assertAlmostEqual(profile["link_acc"], 20)
        self.assertAlmostEqual(profile["link_sync"], 8)
        self.assertAlmostEqual(profile["link_decel"], 20)
        self.assertAlmostEqual(profile["link_idle"], 282)
        self.assertAlmostEqual(base_sync_speed, 500)
        self.assertAlmostEqual(est_slave_accel, 12500)
        self.assertEqual(status["severity"], "ok")
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_locked_cut_geometry_passes(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 62.832)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["link_dist"],
            10,
            8,
            10,
        )
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(geometry["circumference"], math.pi * 20)
        self.assertAlmostEqual(geometry["distance"], geometry["circumference"])
        self.assertAlmostEqual(geometry["link_dist"], 62.832)
        self.assertEqual(status["severity"], "ok")

    def test_rotarylink_cut_length_different_from_drum_pitch_still_passes(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 330)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["link_dist"],
            10,
            8,
            10,
        )
        status = validate_rotarylink_profile(profile)

        self.assertNotAlmostEqual(geometry["link_dist"], geometry["distance"])
        self.assertEqual(status["severity"], "ok")
        self.assertEqual(status["messages"], [])

    def test_rotarylink_base_phases_cannot_exceed_derived_distance(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 330)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["link_dist"],
            30,
            8,
            30,
        )
        status = validate_rotarylink_profile(profile)

        self.assertLess(profile["base_idle"], 0)
        self.assertEqual(status["severity"], "error")
        self.assertIn("base phases exceed one drum cycle", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_link_idle_negative_is_red(self):
        profile = calculate_rotarylink_profile(100, 30, 10, 8, 10)
        status = validate_rotarylink_profile(profile)

        self.assertLess(profile["link_idle"], 0)
        self.assertEqual(status["severity"], "error")
        self.assertIn("cut_length too short", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_sync_distance_must_be_positive(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 0, 10)
        status = validate_rotarylink_profile(profile)

        self.assertEqual(status["severity"], "error")
        self.assertIn("sync_distance must be > 0", status["message"])

    def test_rotarylink_geometry_derives_distance_and_link_dist_from_real_inputs(self):
        single_knife = derive_rotarylink_geometry(20, 8_388_608, 1, 40)
        larger_drum = derive_rotarylink_geometry(40, 8_388_608, 1, 40)
        two_knife = derive_rotarylink_geometry(20, 8_388_608, 2, 40)
        different_cut = derive_rotarylink_geometry(20, 8_388_608, 2, 31.416)

        self.assertAlmostEqual(single_knife["distance"], math.pi * 20)
        self.assertAlmostEqual(larger_drum["distance"], math.pi * 40)
        self.assertAlmostEqual(two_knife["distance"], math.pi * 10)
        self.assertAlmostEqual(single_knife["link_dist"], 40)
        self.assertAlmostEqual(two_knife["link_dist"], 40)
        self.assertAlmostEqual(different_cut["distance"], two_knife["distance"])
        self.assertAlmostEqual(different_cut["link_dist"], 31.416)

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
            calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=15)

        with self.assertRaisesRegex(ValueError, "previous sync phase end"):
            calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=200, previous_sync_end=210)

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

    def test_rotarylink_basic_flags_idle_bookkeeping(self):
        program = emit_rotarylink_basic_program(
            62.832,
            330,
            10,
            8,
            link_axis=0,
            base_axis=1,
            link_options=0,
            base_decel=10,
            base_idle=34.832,
            link_idle=282,
        )

        self.assertIn("' sync is 1:1: base_sync = link_sync = sync distance during the cut.", program)
        self.assertIn("' computed base_decel = 10.000", program)
        self.assertIn("' computed base_idle  = 34.832", program)
        self.assertIn("' computed link_idle  = 282.000", program)
        self.assertIn("ROTARYLINK has no separate idle argument", program)

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
