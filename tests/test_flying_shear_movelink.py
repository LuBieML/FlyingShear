import unittest

from src.flying_shear_app.domain.flying_shear_math import (
    build_flying_shear_movelink_commands,
    calculate_flying_shear_profile,
    emit_flying_shear_movelink_only,
)


class FlyingShearMoveLinkTests(unittest.TestCase):
    def test_movelink_only_commands_use_calculated_phase_distances(self):
        profile = calculate_flying_shear_profile(
            cut_length=160,
            line_speed=500,
            shear_max_speed=1500,
            shear_accel=5000,
            sync_time_ms=40,
            safety_factor=1.5,
        )
        commands = build_flying_shear_movelink_commands(
            profile,
            movelink_profile="trapezoid",
            start_mode="immediate",
            link_pos=0,
            link_source="mpos",
            direction_mode="any",
            repeat_mode="program_loop",
            link_axis=7,
        )

        self.assertEqual(
            emit_flying_shear_movelink_only(commands),
            "\n".join(
                [
                    "MOVELINK(37.500, 75.000, 75.000, 0.000, 7)",
                    "MOVELINK(20.000, 20.000, 0.000, 0.000, 7)",
                    "MOVELINK(37.500, 75.000, 0.000, 75.000, 7)",
                    "MOVELINK(-95.000, -10.000, 0.000, 0.000, 7)",
                ]
            ),
        )

    def test_movelink_only_includes_optional_args_when_options_are_set(self):
        profile = calculate_flying_shear_profile(
            cut_length=250,
            line_speed=400,
            shear_max_speed=1500,
            shear_accel=8000,
            sync_time_ms=30,
            safety_factor=1.2,
        )
        commands = build_flying_shear_movelink_commands(
            profile,
            movelink_profile="sine",
            start_mode="absolute",
            link_pos=12.5,
            link_source="dpos",
            direction_mode="positive",
            repeat_mode="movelink_repeat",
            use_base_dist=True,
            base_dist=4,
            link_axis=2,
        )

        lines = emit_flying_shear_movelink_only(commands).splitlines()
        self.assertIn("8246, 12.500, 4.000", lines[0])
        self.assertIn("8244, 0.000, 4.000", lines[1])
        self.assertIn("MOVELINK(-36.000, 190.000, 47.500, 47.500, 2, 8244, 0.000, 4.000)", lines)

    def test_parameter_provenance_describes_accel_link_source(self):
        profile = calculate_flying_shear_profile(
            cut_length=200,
            line_speed=300,
            shear_max_speed=1500,
            shear_accel=6000,
            sync_time_ms=20,
            safety_factor=1.5,
        )
        commands = build_flying_shear_movelink_commands(
            profile,
            movelink_profile="trapezoid",
            start_mode="immediate",
            link_pos=0,
            link_source="mpos",
            direction_mode="any",
            repeat_mode="program_loop",
            link_axis=0,
        )

        accel_link = commands[0].parameters[1]
        self.assertEqual(accel_link.name, "link_dist")
        self.assertEqual(accel_link.text, "22.500")
        self.assertEqual(accel_link.source.formula, "accel_link = 2 * accel_dist")
        self.assertEqual(accel_link.source.substitution, "2 * 11.250 = 22.500")
        self.assertIn("twice the slave travel", accel_link.source.details[0])
        self.assertIn("accel_dist = 300.000^2 / (2 * 6000.000) * 1.500 = 11.250", accel_link.source.details[1])


if __name__ == "__main__":
    unittest.main()
