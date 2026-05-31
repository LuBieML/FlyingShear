import unittest

from src.flying_shear_app.domain.flexlink_math import (
    build_vffs_flexlink_commands,
    calculate_vffs_flexlink_profile,
    emit_vffs_flexlink_only,
)


class VffsFlexLinkTests(unittest.TestCase):
    def test_vffs_flexlink_only_command_uses_calculated_percentages(self):
        profile = calculate_vffs_flexlink_profile(
            cycle_pitch=180,
            jaw_period=185,
            reg_trim=0,
            line_speed=400,
            base_in_mm=108,
            base_out_mm=9,
            excite_acc_mm=15,
            excite_dec_mm=15,
            seal_dwell_min_ms=80,
        )
        commands = build_vffs_flexlink_commands(
            profile,
            curve_type="sine",
            start_mode="immediate",
            link_pos=0,
            link_source="mpos",
            direction_mode="any",
            repeat_mode="program_loop",
            link_axis=1,
        )

        self.assertEqual(
            emit_vffs_flexlink_only(commands),
            "FLEXLINK(180.000, 5.000, 180.000, 60.00, 5.00, 23.81, 23.81, 1)",
        )

    def test_vffs_flexlink_only_includes_optional_args_when_options_are_set(self):
        profile = calculate_vffs_flexlink_profile(
            cycle_pitch=200,
            jaw_period=220,
            reg_trim=2.5,
            line_speed=500,
            base_in_mm=80,
            base_out_mm=20,
            excite_acc_mm=25,
            excite_dec_mm=25,
            seal_dwell_min_ms=75,
        )
        commands = build_vffs_flexlink_commands(
            profile,
            curve_type="poly7",
            start_mode="absolute",
            link_pos=12,
            link_source="dpos",
            direction_mode="positive",
            repeat_mode="flexlink_repeat",
            link_axis=2,
        )

        self.assertEqual(
            emit_vffs_flexlink_only(commands),
            "FLEXLINK(200.000, 22.500, 200.000, 40.00, 10.00, 25.00, 25.00, 2, 10278, 12.000)",
        )

    def test_vffs_flexlink_parameter_provenance_describes_percentage_source(self):
        profile = calculate_vffs_flexlink_profile(
            cycle_pitch=180,
            jaw_period=185,
            reg_trim=0,
            line_speed=400,
            base_in_mm=108,
            base_out_mm=9,
            excite_acc_mm=15,
            excite_dec_mm=15,
            seal_dwell_min_ms=80,
        )
        commands = build_vffs_flexlink_commands(
            profile,
            curve_type="sine",
            start_mode="immediate",
            link_pos=0,
            link_source="mpos",
            direction_mode="any",
            repeat_mode="program_loop",
            link_axis=1,
        )

        excite_acc = commands[0].parameters[5]
        self.assertEqual(excite_acc.name, "excite_acc")
        self.assertEqual(excite_acc.text, "23.81")
        self.assertEqual(excite_acc.source.formula, "excite_acc = advance_acc / open_window * 100")
        self.assertEqual(excite_acc.source.substitution, "15.000 / 63.000 * 100 = 23.81")
        self.assertIn(
            "Open window = bag_length - seal_contact_in - seal_contact_out = 180.000 - 108.000 - 9.000 = 63.000.",
            excite_acc.source.details[0],
        )


if __name__ == "__main__":
    unittest.main()
