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
    estimate_rotarylink_slave_decel,
    validate_rotarylink_profile,
)


class RotaryLinkTests(unittest.TestCase):
    def assert_rotarylink_totals(self, profile):
        self.assertAlmostEqual(
            (
                profile["base_acc"]
                + profile["base_sync"]
                + profile["base_decel"]
                + profile["base_idle"]
            ),
            profile["distance"],
        )
        self.assertAlmostEqual(
            profile["link_acc"] + profile["link_sync"] + profile["link_decel"],
            profile["link_dist"],
        )
        self.assertAlmostEqual(
            profile["cut_length"] - profile["link_dist"],
            profile["line_per_idle"],
        )
        self.assertAlmostEqual(profile["line_idle"], profile["line_per_idle"])

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

    def test_rotarylink_has_three_linked_phases_plus_base_idle(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=10)

        self.assertAlmostEqual(profile["base_decel"], 30)
        self.assertAlmostEqual(profile["base_idle"], 0)
        self.assertAlmostEqual(profile["link_acc"], 20)
        self.assertAlmostEqual(profile["link_sync"], 60)
        self.assertAlmostEqual(profile["link_decel"], 60)
        self.assertAlmostEqual(profile["link_dist"], 140)
        self.assertAlmostEqual(profile["line_per_idle"], 110)
        self.assertAlmostEqual(profile["start_link_pos"], 10)
        self.assertAlmostEqual(profile["sync_start"], 30)
        self.assertAlmostEqual(profile["sync_end"], 90)
        self.assertAlmostEqual(profile["cycle_end"], 150)
        self.assertEqual(
            [phase["name"] for phase in profile["phase_segments"]],
            ["acc", "sync", "decel", "idle"],
        )
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_sync_phase_is_one_to_one_by_construction(self):
        profile = calculate_rotarylink_profile(62.832, 330, 10, 8, 10)

        self.assertAlmostEqual(profile["base_sync"], 8)
        self.assertAlmostEqual(profile["link_sync"], 8)
        self.assertAlmostEqual(calculate_rotarylink_base_sync_speed(500, profile), 500)

    def test_rotarylink_worked_example_has_drum_and_line_idle(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 100)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
            10,
        )
        base_sync_speed = calculate_rotarylink_base_sync_speed(50, profile)
        est_slave_accel = estimate_rotarylink_slave_accel(50, profile)
        est_slave_decel = estimate_rotarylink_slave_decel(50, profile)
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(geometry["circumference"], math.pi * 20)
        self.assertAlmostEqual(geometry["distance"], math.pi * 20)
        self.assertAlmostEqual(profile["base_decel"], 10)
        self.assertAlmostEqual(profile["base_idle"], math.pi * 20 - 10 - 3 - 10)
        self.assertAlmostEqual(profile["link_dist"], 43)
        self.assertAlmostEqual(profile["link_acc"], 20)
        self.assertAlmostEqual(profile["link_sync"], 3)
        self.assertAlmostEqual(profile["link_decel"], 20)
        self.assertAlmostEqual(profile["line_idle"], 57)
        self.assertAlmostEqual(base_sync_speed, 50)
        self.assertAlmostEqual(est_slave_accel, 125)
        self.assertAlmostEqual(est_slave_decel, 125)
        self.assertEqual(status["severity"], "ok")
        self.assertFalse(status["requires_merge"])
        self.assertIn("idle between cuts = 57.000", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_no_overlap_has_external_idle(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 200)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
            10,
        )
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(profile["link_dist"], 43)
        self.assertAlmostEqual(profile["line_per_idle"], 157)
        self.assertEqual(status["severity"], "ok")
        self.assertFalse(status["requires_merge"])
        self.assertIn("idle between cuts = 157.000", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_back_to_back_cuts_are_green(self):
        profile = calculate_rotarylink_profile(100, 140, 10, 60, 30)
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(profile["line_per_idle"], 0)
        self.assertEqual(status["severity"], "ok")
        self.assertIn("back-to-back cuts", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_line_overlap_is_warning_and_requires_merge(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 30)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
            10,
        )
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(profile["line_idle"], -13)
        self.assertEqual(status["severity"], "warning")
        self.assertTrue(status["requires_merge"])
        self.assertIn("cuts overlap", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_base_phases_cannot_exceed_derived_distance(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 200)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            30,
            3,
            30,
        )
        status = validate_rotarylink_profile(profile)

        self.assertLess(profile["base_idle"], 0)
        self.assertEqual(status["severity"], "error")
        self.assertIn("base phases exceed one drum cycle", status["message"])
        self.assert_rotarylink_totals(profile)

    def test_rotarylink_sync_distance_must_be_positive(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 0, 10)
        status = validate_rotarylink_profile(profile)

        self.assertEqual(status["severity"], "error")
        self.assertIn("sync_distance must be > 0", status["message"])

    def test_rotarylink_accel_and_decel_must_be_positive(self):
        profile = calculate_rotarylink_profile(100, 250, 0, 10, 0)
        status = validate_rotarylink_profile(profile)

        self.assertEqual(status["severity"], "error")
        self.assertIn("base_acc must be > 0", status["message"])
        self.assertIn("base_decel must be > 0", status["message"])

    def test_rotarylink_geometry_derives_distance_but_not_linkdist(self):
        single_knife = derive_rotarylink_geometry(20, 8_388_608, 1, 40)
        larger_drum = derive_rotarylink_geometry(40, 8_388_608, 1, 40)
        two_knife = derive_rotarylink_geometry(20, 8_388_608, 2, 40)
        different_cut = derive_rotarylink_geometry(20, 8_388_608, 2, 31.416)

        self.assertAlmostEqual(single_knife["distance"], math.pi * 20)
        self.assertAlmostEqual(larger_drum["distance"], math.pi * 40)
        self.assertAlmostEqual(two_knife["distance"], math.pi * 10)
        self.assertAlmostEqual(single_knife["cut_length"], 40)
        self.assertAlmostEqual(two_knife["cut_length"], 40)
        self.assertAlmostEqual(different_cut["distance"], two_knife["distance"])
        self.assertAlmostEqual(different_cut["cut_length"], 31.416)
        self.assertNotIn("link_dist", single_knife)

    def test_rotarylink_linkdist_is_not_cut_length_in_general(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 60, 30)

        self.assertAlmostEqual(profile["link_dist"], 140)
        self.assertNotAlmostEqual(profile["link_dist"], profile["cut_length"])

    def test_rotarylink_base_acc_and_decel_are_independent_inputs(self):
        base_profile = calculate_rotarylink_profile(100, 250, 10, 20, 30)
        changed_acc = calculate_rotarylink_profile(100, 250, 15, 20, 30)
        changed_decel = calculate_rotarylink_profile(100, 250, 10, 20, 35)

        self.assertAlmostEqual(changed_acc["base_decel"], base_profile["base_decel"])
        self.assertNotAlmostEqual(changed_acc["base_acc"], base_profile["base_acc"])
        self.assertAlmostEqual(changed_decel["base_acc"], base_profile["base_acc"])
        self.assertNotAlmostEqual(changed_decel["base_decel"], base_profile["base_decel"])

    def test_rotarylink_sync_window_uses_per_knife_segment(self):
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 25, 2), 45.0)
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 25, 1), 90.0)

    def test_rotarylink_sync_window_is_clamped_to_segment(self):
        self.assertAlmostEqual(compute_rotarylink_sync_window_deg(100, 125, 2), 180.0)

    def test_rotarylink_units_are_counts_per_circumference_mm(self):
        circumference = compute_rotary_drum_circumference_mm(20)
        self.assertAlmostEqual(circumference, 20 * math.pi)
        self.assertAlmostEqual(
            compute_rotary_units_per_mm(8_388_608, 20),
            8_388_608 / circumference,
        )

    def test_rotarylink_rejects_bad_start_positions(self):
        with self.assertRaisesRegex(ValueError, "sync_pos must be >= 0"):
            calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=-1)

        with self.assertRaisesRegex(ValueError, "previous sync phase end"):
            calculate_rotarylink_profile(100, 250, 10, 60, 30, sync_pos=200, previous_sync_end=210)

    def test_rotarylink_basic_loop_sets_required_merge_for_overlap(self):
        program = emit_rotarylink_basic_program(
            62.832,
            43,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=30,
            base_decel=10,
            base_idle=39.832,
            line_per_idle=-13,
            required_merge=True,
            start_pos=10,
        )

        self.assertIn("moveoptions.5 = TRUE", program)
        self.assertIn("WHILE (1)", program)
        self.assertIn("    TRIGGER", program)
        self.assertIn(
            "ROTARYLINK(62.832, 43.000, 10.000, 3.000, link_ax, 32, start_pos)",
            program,
        )
        self.assertIn("start_pos = start_pos + cut_length", program)
        self.assertIn("WAIT UNTIL MOVES_BUFFERED < 2", program)

    def test_rotarylink_basic_no_overlap_leaves_merge_off(self):
        program = emit_rotarylink_basic_program(
            62.832,
            43,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=100,
            base_decel=10,
            base_idle=39.832,
            line_per_idle=57,
            required_merge=False,
            start_pos=10,
        )

        self.assertIn("moveoptions.5 = FALSE", program)
        self.assertIn(
            "ROTARYLINK(62.832, 43.000, 10.000, 3.000, link_ax, 0, start_pos)",
            program,
        )

    def test_rotarylink_basic_flags_external_idle_bookkeeping(self):
        program = emit_rotarylink_basic_program(
            62.832,
            43,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=100,
            base_decel=10,
            base_idle=39.832,
            line_per_idle=57,
            start_pos=10,
        )

        self.assertIn("' sync is 1:1 by construction", program)
        self.assertIn("base_decel   = 10.000", program)
        self.assertIn("' base_idle drum dwell = 39.832", program)
        self.assertIn("' line_idle between ROTARYLINK calls = 57.000", program)
        self.assertIn("ROTARYLINK has no idle phase", program)

    def test_rotarylink_basic_includes_option_bit_breakdown(self):
        program = emit_rotarylink_basic_program(
            360,
            660,
            50,
            60,
            link_axis=0,
            base_axis=1,
            link_options=108,
            cut_length=500,
            required_merge=True,
            start_pos=50,
        )

        self.assertIn("' link_options bit breakdown:", program)
        self.assertIn("'   decimal value = 108", program)
        self.assertIn("'   set bits = 2, 3, 5, 6", program)
        self.assertIn("'   bits 0..1 = 0: absolute sync position", program)
        self.assertIn("'   bits 2..4 = 3: power 7 polynomial speed profile", program)
        self.assertIn("'   bit 5 = ON: merge consecutive ROTARYLINK commands", program)
        self.assertIn("'   bit 6 = ON: follow master DPOS", program)

    def test_rotarylink_basic_defines_base_axis_before_loop(self):
        program = emit_rotarylink_basic_program(
            360,
            660,
            50,
            60,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=800,
        )

        base_setup = "BASE(base_ax)\nSERVO = ON\nDEFPOS(0)"
        self.assertIn(base_setup, program)
        self.assertLess(program.index(base_setup), program.index("WHILE (1)"))
        self.assertIn("FORWARD AXIS(link_ax)", program)

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
