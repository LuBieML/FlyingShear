import unittest

from src.flying_shear_app.domain.link_options import build_rotarylink_options
from src.flying_shear_app.domain.rotarylink_math import (
    build_rotarylink_commands,
    calculate_rotarylink_profile,
    derive_rotarylink_geometry,
    emit_rotarylink_only,
)


class RotaryLinkCommandTests(unittest.TestCase):
    def test_rotarylink_only_command_uses_derived_geometry_values(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 100)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
            sync_pos=10,
        )
        commands = build_rotarylink_commands(
            profile,
            geometry,
            link_axis=0,
            link_options=0,
            start_pos=10,
            start_mode="absolute",
            profile_mode="trapezoid",
            link_source="mpos",
            merge=False,
        )

        self.assertEqual(
            emit_rotarylink_only(commands),
            "ROTARYLINK(62.832, 62.832, 10.000, 3.000, 0, 0, 10.000)",
        )

    def test_rotarylink_distance_provenance_shows_circumference_formula(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 2, 100)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            5,
            10,
            sync_pos=5,
        )
        commands = build_rotarylink_commands(
            profile,
            geometry,
            link_axis=1,
            link_options=0,
            start_pos=5,
        )

        distance = commands[0].parameters[0]
        self.assertEqual(distance.name, "distance")
        self.assertEqual(distance.text, "31.416")
        self.assertEqual(distance.source.formula, "distance = circumference / knives_on_drum")
        self.assertEqual(distance.source.substitution, "62.832 / 2 = 31.416")
        self.assertIn("circumference = pi * drum_diameter", distance.source.details[0])

    def test_rotarylink_options_provenance_describes_merge_and_source_bits(self):
        geometry = derive_rotarylink_geometry(20, 8_388_608, 1, 30)
        profile = calculate_rotarylink_profile(
            geometry["distance"],
            geometry["cut_length"],
            10,
            3,
            sync_pos=10,
        )
        options = build_rotarylink_options("absolute", "power7", "dpos", True)
        commands = build_rotarylink_commands(
            profile,
            geometry,
            link_axis=2,
            link_options=options,
            start_pos=10,
            start_mode="absolute",
            profile_mode="power7",
            link_source="dpos",
            merge=True,
        )

        self.assertEqual(
            emit_rotarylink_only(commands),
            "ROTARYLINK(62.832, 62.832, 10.000, 3.000, 2, 108, 10.000)",
        )
        moveoptions = commands[0].parameters[5]
        self.assertEqual(moveoptions.name, "moveoptions")
        self.assertEqual(moveoptions.text, "108")
        self.assertIn("Set bits: 2, 3, 5, 6", moveoptions.source.details)
        self.assertIn(
            "Merge: bit 5 ON because cut_length is shorter than distance",
            moveoptions.source.details,
        )
        self.assertIn("Source: bit 6 ON, follow master DPOS", moveoptions.source.details)


if __name__ == "__main__":
    unittest.main()
