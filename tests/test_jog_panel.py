import unittest

from src.flying_shear_app.ui.jog_panel import JogPanelTheme, SlaveJogPanel


def _theme():
    return JogPanelTheme(
        panel_bg="#20242a",
        field_bg="#111316",
        border_color="#343a40",
        text_color="#d4d4d4",
        muted_text="#888888",
        accent_color="#007acc",
        status_bg="#111316",
    )


class SlaveJogPanelTests(unittest.TestCase):
    def test_jog_buttons_emit_rising_and_falling_edges_with_press_speed(self):
        events = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="12.5",
            on_jog_edge=events.append,
        )

        self.assertTrue(panel.begin_jog("fwd"))
        panel.speed_input.value = "bad value"
        self.assertTrue(panel.end_jog("fwd"))

        self.assertEqual([event.edge for event in events], ["rising", "falling"])
        self.assertEqual([event.direction for event in events], ["fwd", "fwd"])
        self.assertEqual([event.speed for event in events], [12.5, 12.5])

    def test_invalid_speed_blocks_rising_edge(self):
        events = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="0",
            on_jog_edge=events.append,
        )

        self.assertFalse(panel.begin_jog("rev"))
        self.assertEqual(events, [])
        self.assertEqual(panel.speed_input.error_text, "Must be > 0")

    def test_disabling_panel_does_not_emit_falling_edge(self):
        events = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="4",
            on_jog_edge=events.append,
        )

        self.assertTrue(panel.begin_jog("rev"))
        panel.set_enabled(False)

        self.assertEqual([event.edge for event in events], ["rising"])

    def test_opposite_direction_is_blocked_while_jog_is_active(self):
        events = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="4",
            on_jog_edge=events.append,
        )

        self.assertTrue(panel.begin_jog("fwd"))
        self.assertFalse(panel.begin_jog("rev"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "fwd")

    def test_reset_callback_receives_current_speed_when_valid(self):
        resets = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="3.25",
            on_reset_position=resets.append,
        )

        panel._handle_reset(None)

        self.assertEqual(len(resets), 1)
        self.assertEqual(resets[0].speed, 3.25)
        self.assertEqual(resets[0].speed_text, "3.25")

    def test_speed_commit_callback_receives_normalized_speed(self):
        commits = []
        panel = SlaveJogPanel(
            theme=_theme(),
            speed_value="2.500",
            on_speed_commit=lambda speed, speed_text: commits.append((speed, speed_text)),
        )

        panel._handle_speed_commit(None)

        self.assertEqual(commits, [(2.5, "2.5")])
        self.assertEqual(panel.speed_input.value, "2.5")


if __name__ == "__main__":
    unittest.main()
