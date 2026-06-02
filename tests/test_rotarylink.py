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
    def assert_rotarylink_firmware_model(self, profile):
        self.assertAlmostEqual(profile["link_dist"], profile["distance"])
        self.assertAlmostEqual(profile["linkdist"], profile["distance"])
        self.assertAlmostEqual(
            profile["base_decel"],
            profile["distance"] - profile["base_acc"] - profile["base_sync"],
        )
        self.assertAlmostEqual(profile["sync_gear_ratio"], 1.0)
        self.assertAlmostEqual(profile["line_per_cut_in_command"], profile["distance"])
        self.assertAlmostEqual(
            profile["line_idle_between_cuts"],
            profile["cut_length"] - profile["distance"],
        )
        self.assertAlmostEqual(profile["line_idle"], profile["line_idle_between_cuts"])
        self.assertAlmostEqual(profile["line_per_idle"], profile["line_idle_between_cuts"])
        for removed_key in (
            "base_idle",
            "link_acc",
            "link_sync",
            "link_decel",
            "link_idle",
            "link_total",
            "entered_base_decel",
        ):
            self.assertNotIn(removed_key, profile)

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
        self.assertEqual(
            format_rotarylink(
                "distance",
                "linkdist",
                "base_acc",
                "base_sync",
                "link_ax",
                "moveoptions",
                "start_pos",
            ),
            "ROTARYLINK(distance, linkdist, base_acc, base_sync, link_ax, moveoptions, start_pos)",
        )

    def test_rotarylink_has_three_base_phases_and_derived_decel(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 60, sync_pos=10)

        self.assertAlmostEqual(profile["base_decel"], 30)
        self.assertAlmostEqual(profile["line_per_idle"], 150)
        self.assertAlmostEqual(profile["start_link_pos"], 10)
        self.assertAlmostEqual(profile["sync_start"], 20)
        self.assertAlmostEqual(profile["sync_end"], 80)
        self.assertAlmostEqual(profile["cycle_end"], 110)
        self.assertEqual(
            [phase["name"] for phase in profile["phase_segments"]],
            ["acc", "sync", "decel"],
        )
        self.assertEqual(
            [phase["base"] for phase in profile["phase_segments"]],
            [10, 60, 30],
        )
        self.assert_rotarylink_firmware_model(profile)

    def test_worked_example_a_matched_one_to_one_no_overlap(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 100)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
        )
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(geometry["circumference"], math.pi * 20)
        self.assertAlmostEqual(geometry["distance"], math.pi * 20)
        self.assertAlmostEqual(profile["base_decel"], math.pi * 20 - 10 - 3)
        self.assertAlmostEqual(profile["link_dist"], geometry["distance"])
        self.assertAlmostEqual(profile["sync_gear_ratio"], 1.0)
        self.assertAlmostEqual(calculate_rotarylink_base_sync_speed(50, profile), 50)
        self.assertAlmostEqual(estimate_rotarylink_slave_accel(50, profile), 125)
        self.assertAlmostEqual(profile["line_idle_between_cuts"], 100 - math.pi * 20)
        self.assertEqual(status["severity"], "ok")
        self.assertFalse(status["requires_merge"])
        self.assertIn("idle between cuts = 37.168", status["message"])
        self.assert_rotarylink_firmware_model(profile)

    def test_worked_example_b_short_cut_requires_merge(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 30)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
        )
        status = validate_rotarylink_profile(profile)

        self.assertAlmostEqual(profile["line_idle_between_cuts"], 30 - math.pi * 20)
        self.assertEqual(status["severity"], "warning")
        self.assertTrue(status["requires_merge"])
        self.assertIn("Cut length (30.000) < distance (62.832)", status["message"])
        self.assertIn("Cuts overlap by 32.832 mm", status["message"])
        self.assert_rotarylink_firmware_model(profile)

        program = emit_rotarylink_basic_program(
            geometry["distance"],
            profile["link_dist"],
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=30,
            base_decel=profile["base_decel"],
            line_per_idle=profile["line_per_idle"],
            required_merge=status["requires_merge"],
            start_pos=10,
        )
        self.assertIn("moveoptions.5 = TRUE", program)
        self.assertIn(
            "ROTARYLINK(distance, linkdist, base_acc, base_sync, link_ax, moveoptions, start_pos)",
            program,
        )

    def test_worked_example_c_invalid_geometry_is_red(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 100)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            60,
            3,
        )
        status = validate_rotarylink_profile(profile)

        self.assertLess(profile["base_decel"], 0)
        self.assertEqual(status["severity"], "error")
        self.assertFalse(status["requires_merge"])
        self.assertIn("Acc + sync exceeds one drum cycle", status["message"])
        self.assertIn("firmware would silently rescale accel internally", status["message"])

    def test_rotarylink_cut_length_at_or_above_distance_is_green(self):
        back_to_back = calculate_rotarylink_profile(100, 100, 10, 60)
        with_idle = calculate_rotarylink_profile(100, 140, 10, 60)

        back_to_back_status = validate_rotarylink_profile(back_to_back)
        with_idle_status = validate_rotarylink_profile(with_idle)

        self.assertEqual(back_to_back_status["severity"], "ok")
        self.assertFalse(back_to_back_status["requires_merge"])
        self.assertIn("cut_length == distance", back_to_back_status["message"])
        self.assertEqual(with_idle_status["severity"], "ok")
        self.assertFalse(with_idle_status["requires_merge"])
        self.assertIn("idle between cuts = 40.000", with_idle_status["message"])

    def test_rotarylink_acc_and_sync_must_be_positive(self):
        acc_profile = calculate_rotarylink_profile(100, 250, 0, 10)
        sync_profile = calculate_rotarylink_profile(100, 250, 10, 0)

        acc_status = validate_rotarylink_profile(acc_profile)
        sync_status = validate_rotarylink_profile(sync_profile)

        self.assertEqual(acc_status["severity"], "error")
        self.assertIn("base_acc must be > 0", acc_status["message"])
        self.assertEqual(sync_status["severity"], "error")
        self.assertIn("sync_distance must be > 0", sync_status["message"])

    def test_rotarylink_geometry_derives_distance_not_pitch(self):
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

    def test_rotarylink_linkdist_is_distance_not_cut_length(self):
        profile = calculate_rotarylink_profile(100, 250, 10, 60)

        self.assertAlmostEqual(profile["link_dist"], 100)
        self.assertNotAlmostEqual(profile["link_dist"], profile["cut_length"])
        self.assert_rotarylink_firmware_model(profile)

    def test_rotarylink_base_decel_is_derived_from_acc_and_sync(self):
        base_profile = calculate_rotarylink_profile(100, 250, 10, 20)
        changed_acc = calculate_rotarylink_profile(100, 250, 15, 20)
        changed_sync = calculate_rotarylink_profile(100, 250, 10, 25)

        self.assertAlmostEqual(base_profile["base_decel"], 70)
        self.assertAlmostEqual(changed_acc["base_decel"], 65)
        self.assertAlmostEqual(changed_sync["base_decel"], 65)

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
            calculate_rotarylink_profile(100, 250, 10, 60, sync_pos=-1)

        with self.assertRaisesRegex(ValueError, "previous sync phase end"):
            calculate_rotarylink_profile(
                100,
                250,
                10,
                60,
                sync_pos=200,
                previous_sync_end=210,
            )

    def test_observed_scope_ratio_matches_old_linkdist_and_new_ratio_is_one(self):
        observed_old_ratio = 62.832 / 43
        profile = calculate_rotarylink_profile(62.832, 100, 10, 3)

        self.assertAlmostEqual(observed_old_ratio, 1.461, places=3)
        self.assertAlmostEqual(profile["sync_gear_ratio"], 1.0)

    def test_rotarylink_basic_loop_sets_required_merge_for_overlap(self):
        program = emit_rotarylink_basic_program(
            62.832,
            62.832,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=30,
            base_decel=49.832,
            line_per_idle=-32.832,
            required_merge=True,
            start_pos=10,
        )

        self.assertIn("moveoptions.5 = TRUE", program)
        self.assertIn(
            "\n".join(
                [
                    "WHILE (1)",
                    "    TRIGGER",
                    "    IF MOVES_BUFFERED< LIMIT_BUFFERED-1 THEN",
                    (
                        "        ROTARYLINK(distance, linkdist, base_acc, base_sync, "
                        "link_ax, moveoptions, start_pos)"
                    ),
                    "        start_pos = start_pos + cut_length",
                    "    ENDIF",
                    "    WA(1)",
                    "WEND",
                ]
            ),
            program,
        )
        self.assertNotIn("WAIT UNTIL MOVES_BUFFERED < 2", program)

    def test_rotarylink_basic_no_overlap_leaves_merge_off(self):
        program = emit_rotarylink_basic_program(
            62.832,
            62.832,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=100,
            base_decel=49.832,
            line_per_idle=37.168,
            required_merge=False,
            start_pos=10,
        )

        self.assertIn("moveoptions.5 = FALSE", program)
        self.assertIn(
            "ROTARYLINK(distance, linkdist, base_acc, base_sync, link_ax, moveoptions, start_pos)",
            program,
        )

    def test_rotarylink_basic_keeps_derived_values_without_header_comments(self):
        program = emit_rotarylink_basic_program(
            62.832,
            62.832,
            10,
            3,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=100,
            base_decel=49.832,
            line_per_idle=37.168,
            start_pos=10,
        )

        self.assertNotIn("' ROTARYLINK generated setup", program)
        self.assertNotIn("' sync gear ratio = distance / linkdist (firmware rule)", program)
        self.assertNotIn("' linkdist = distance for matched surface speed during the cut", program)
        self.assertNotIn("' cut_length controls line spacing between cuts via start_pos increment", program)
        self.assertNotIn("' Both axes must be calibrated so 1 user unit = 1 mm of product travel.", program)
        self.assertNotIn("' distance and linkdist are interpreted", program)
        self.assertIn("' base_decel derived = 49.832", program)
        self.assertIn("' line_idle_between_cuts = 37.168", program)
        self.assertNotIn("base_idle", program)
        self.assertNotIn("link_acc", program)
        self.assertNotIn("link_sync", program)
        self.assertNotIn("link_decel", program)

    def test_rotarylink_basic_includes_option_bit_breakdown(self):
        program = emit_rotarylink_basic_program(
            360,
            360,
            50,
            60,
            link_axis=0,
            base_axis=1,
            link_options=108,
            cut_length=300,
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

    def test_rotarylink_basic_defines_axes_before_loop(self):
        program = emit_rotarylink_basic_program(
            360,
            360,
            50,
            60,
            link_axis=0,
            base_axis=1,
            link_options=0,
            cut_length=800,
        )

        self.assertTrue(program.startswith("CANCEL(2)\nWA(100)\n\n"))
        startup_setup = (
            "BASE(link_ax)\n"
            "SERVO = ON\n"
            "DEFPOS(0)\n"
            "\n"
            "BASE(base_ax)\n"
            "SERVO = ON\n"
            "DEFPOS(0)\n"
            "WA(100)"
        )
        base_setup = "BASE(base_ax)\nSERVO = ON\nDEFPOS(0)"
        self.assertIn(startup_setup, program)
        self.assertIn(base_setup, program)
        self.assertLess(program.index(startup_setup), program.index("WHILE (1)"))
        self.assertNotIn("WA(200)", program)
        self.assertNotIn("' Add controller-specific axis setup here.", program)
        self.assertNotIn("FORWARD AXIS(link_ax)", program)

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
