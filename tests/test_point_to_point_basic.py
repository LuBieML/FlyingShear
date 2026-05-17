import unittest

from src.flying_shear_app.codegen.point_to_point_basic import (
    emit_point_to_point_basic_program,
)


class PointToPointBasicTests(unittest.TestCase):
    def test_relative_mode_uses_move_distance(self):
        program = emit_point_to_point_basic_program(
            axis=2,
            move_mode="relative",
            target=25.5,
            speed=10,
            accel=100,
            decel=80,
        )

        self.assertIn("axis_no = 2", program)
        self.assertIn("distance = 25.500", program)
        self.assertIn("MOVE(distance)", program)
        self.assertNotIn("\nMOVEABS", program)

    def test_absolute_mode_uses_moveabs_target_position(self):
        program = emit_point_to_point_basic_program(
            axis=1,
            move_mode="absolute",
            target=150,
            speed=20,
            accel=200,
            decel=200,
            servo_on=False,
            wait_idle=False,
        )

        self.assertIn("target_pos = 150.000", program)
        self.assertIn("MOVEABS(target_pos)", program)
        self.assertNotIn("SERVO = ON", program)
        self.assertNotIn("WAIT IDLE", program)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            emit_point_to_point_basic_program(0, "indexed", 10, 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
