import unittest

from src.flying_shear_app.codegen.axis_startup_basic import emit_axis_startup_basic_program


class AxisStartupBasicTests(unittest.TestCase):
    def test_startup_uses_per_axis_parameters_and_deduplicates_axes(self):
        program = emit_axis_startup_basic_program(
            "Flying Shear",
            [0, 1, "0"],
            axis_params_by_axis={
                0: {"UNITS": "2", "SPEED": "30"},
                "1": {"ACCEL": "40", "DRIVE_FE_LIMIT": "3.7"},
            },
        )

        self.assertFalse(program.startswith("CANCEL(2)\nWA(100)"))
        self.assertNotIn("CANCEL(2)", program)
        self.assertNotIn("WA(100)", program)
        self.assertTrue(program.startswith("' Flying Shear STARTUP axis configuration"))
        self.assertIn("' Flying Shear STARTUP axis configuration", program)
        self.assertEqual(program.count("BASE(0)"), 1)
        self.assertEqual(program.count("BASE(1)"), 1)
        self.assertIn("BASE(0)\nSERVO = ON\nUNITS = 2.000\nSPEED = 30.000", program)
        self.assertIn("BASE(1)\nSERVO = ON", program)
        self.assertIn("ACCEL = 40.000", program)
        self.assertIn("DRIVE_FE_LIMIT = 3", program)

    def test_startup_falls_back_for_invalid_axis_parameters(self):
        program = emit_axis_startup_basic_program(
            "Rotary Knife",
            [2],
            axis_params_by_axis={2: {"SPEED": "-", "FE_LIMIT": "nan"}},
        )

        self.assertIn("SPEED = 10.000", program)
        self.assertIn("FE_LIMIT = 1", program)


if __name__ == "__main__":
    unittest.main()
