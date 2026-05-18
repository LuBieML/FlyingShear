import unittest

from src.flying_shear_app.codegen.point_to_point_basic import (
    emit_point_to_point_basic_program,
    emit_point_to_point_startup_program,
    emit_square_move_basic_program,
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

    def test_absolute_square_uses_moveabs_corner_coordinates(self):
        program = emit_square_move_basic_program(
            x_axis=0,
            y_axis=1,
            move_mode="absolute",
            origin_x=10,
            origin_y=20,
            side=50,
            speed=25,
            accel=100,
            decel=100,
        )

        self.assertIn("BASE(0)\nSERVO = ON\nUNITS = 1.000\nSPEED = 25.000", program)
        self.assertIn("BASE(1)\nSERVO = ON\nUNITS = 1.000\nSPEED = 25.000", program)
        self.assertNotIn("BASE(x_axis, y_axis)", program)
        self.assertIn("x0 = 10.000", program)
        self.assertIn("y0 = 20.000", program)
        self.assertIn("BASE(x_axis)\nMOVEABS(x0 + side)", program)
        self.assertIn("BASE(y_axis)\nMOVEABS(y0 + side)", program)
        self.assertIn("BASE(x_axis)\nMOVEABS(x0)", program)
        self.assertIn("BASE(y_axis)\nMOVEABS(y0)", program)

    def test_relative_square_uses_move_edges(self):
        program = emit_square_move_basic_program(
            x_axis=0,
            y_axis=1,
            move_mode="relative",
            origin_x=0,
            origin_y=0,
            side=50,
            speed=25,
            accel=100,
            decel=100,
        )

        self.assertIn("BASE(x_axis)\nMOVE(side)", program)
        self.assertIn("BASE(y_axis)\nMOVE(side)", program)
        self.assertIn("BASE(x_axis)\nMOVE(-side)", program)
        self.assertIn("BASE(y_axis)\nMOVE(-side)", program)
        self.assertNotIn("\nMOVEABS", program)

    def test_square_side_must_be_positive(self):
        with self.assertRaises(ValueError):
            emit_square_move_basic_program(0, 1, "absolute", 0, 0, 0, 1, 1, 1)

    def test_startup_program_falls_back_for_invalid_axis_params(self):
        program = emit_point_to_point_startup_program(
            axis=0,
            speed=25,
            accel=100,
            decel=100,
            axis_params={
                "SPEED": "-",
                "DRIVE_FE_LIMIT": "nan",
                "FS_LIMIT": "bad",
            },
        )

        self.assertIn("SPEED = 10.000", program)
        self.assertIn("DRIVE_FE_LIMIT = 1", program)
        self.assertIn("FS_LIMIT = 0.000", program)


if __name__ == "__main__":
    unittest.main()
