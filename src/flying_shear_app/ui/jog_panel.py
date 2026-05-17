"""Reusable slave-axis jog panel with explicit press/release edge callbacks."""

from dataclasses import dataclass
from typing import Callable, Optional

import flet as ft


@dataclass(frozen=True)
class JogEdgeEvent:
    """Event raised by jog buttons on pointer press and release."""

    direction: str
    edge: str
    speed: float
    speed_text: str
    source: str
    reason: str = ""


@dataclass(frozen=True)
class JogResetEvent:
    """Event raised when Reset pos is clicked."""

    source: str
    speed: Optional[float]
    speed_text: str


@dataclass(frozen=True)
class JogPanelTheme:
    panel_bg: str
    field_bg: str
    border_color: str
    text_color: str
    muted_text: str
    accent_color: str
    status_bg: str
    fwd_bg: object = ft.Colors.GREEN_700
    rev_bg: object = ft.Colors.BLUE_GREY_700
    reset_color: object = ft.Colors.CYAN_200
    active_border: object = ft.Colors.CYAN_200
    error_color: object = ft.Colors.RED_300
    idle_color: object = ft.Colors.GREY_500
    active_color: object = ft.Colors.AMBER_200


class SlaveJogPanel:
    """Build a copyable slave/drum jog panel.

    The panel deliberately separates UI edge detection from controller IO.
    Wire real movement by supplying callbacks for ``on_jog_edge`` and
    ``on_reset_position``.
    """

    def __init__(
        self,
        *,
        title: str = "Slave / drum jog",
        subtitle: str = "Press and release edges are exposed for controller commands",
        source: str = "slave_jog",
        speed_value: object = "1.0",
        speed_suffix: str = "u/s",
        theme: JogPanelTheme,
        on_jog_edge: Optional[Callable[[JogEdgeEvent], None]] = None,
        on_reset_position: Optional[Callable[[JogResetEvent], None]] = None,
        on_speed_change: Optional[Callable[[float, str], None]] = None,
        enabled: bool = True,
        col=None,
    ):
        self.source = source
        self.speed_suffix = speed_suffix
        self.theme = theme
        self.on_jog_edge = on_jog_edge
        self.on_reset_position = on_reset_position
        self.on_speed_change = on_speed_change
        self.enabled = enabled
        self._active_speeds = {}
        self._button_surfaces = {}
        self._edge_detectors = []

        self.speed_input = ft.TextField(
            label="Jog speed",
            value=str(speed_value),
            width=135,
            height=45,
            bgcolor=theme.field_bg,
            color=theme.text_color,
            border_color=theme.border_color,
            focused_border_color=theme.accent_color,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix=speed_suffix,
            text_align=ft.TextAlign.RIGHT,
            text_size=12,
            on_change=self._handle_speed_change,
            on_blur=self._handle_speed_commit,
            on_submit=self._handle_speed_commit,
            tooltip="Positive slave-axis jog speed. Direction is selected by the jog button.",
        )

        self.status_text = ft.Text(
            "Framework ready. Controller jog commands are not wired yet.",
            size=11,
            color=theme.idle_color,
            max_lines=2,
        )
        self.status_box = ft.Container(
            content=self.status_text,
            bgcolor=theme.status_bg,
            border=ft.Border.all(1, theme.border_color),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            width=360,
        )

        self.rev_button = self._make_jog_button(
            "Jog REV",
            ft.Icons.FAST_REWIND,
            "rev",
            theme.rev_bg,
            "Rising edge on press, falling edge on release for reverse drum jog",
        )
        self.fwd_button = self._make_jog_button(
            "Jog FWD",
            ft.Icons.FAST_FORWARD,
            "fwd",
            theme.fwd_bg,
            "Rising edge on press, falling edge on release for forward drum jog",
        )
        self.reset_button = ft.OutlinedButton(
            "Reset pos",
            icon=ft.Icons.RESTART_ALT,
            height=38,
            on_click=self._handle_reset,
            style=ft.ButtonStyle(color=theme.reset_color),
            tooltip="Click edge for a future slave/drum position reset command",
        )

        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.TOUCH_APP, size=14, color=theme.muted_text),
                            ft.Column(
                                [
                                    ft.Text(title.upper(), size=10, color=theme.muted_text, weight=ft.FontWeight.BOLD),
                                    ft.Text(subtitle, size=11, color=theme.muted_text, max_lines=2),
                                ],
                                spacing=1,
                                tight=True,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [self.rev_button, self.fwd_button, self.reset_button, self.speed_input, self.status_box],
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=theme.panel_bg,
            border=ft.Border.all(1, theme.border_color),
            border_radius=8,
            padding=12,
            col=col or {"xs": 12, "lg": 7},
        )

        self.set_enabled(enabled)

    def set_status(self, message: str, kind: str = "idle") -> None:
        colors = {
            "active": self.theme.active_color,
            "error": self.theme.error_color,
            "idle": self.theme.idle_color,
        }
        self.status_text.value = message
        self.status_text.color = colors.get(kind, self.theme.idle_color)
        self._safe_update(self.status_box)

    def set_enabled(self, enabled: bool) -> None:
        if self.enabled and not enabled:
            for direction in tuple(self._active_speeds):
                self._active_speeds.pop(direction, None)
                self._set_button_pressed(direction, False)

        self.enabled = enabled
        for detector in self._edge_detectors:
            detector.disabled = not enabled
            detector.opacity = 1.0 if enabled else 0.45
        self.reset_button.disabled = not enabled
        self.speed_input.disabled = not enabled
        self.control.opacity = 1.0 if enabled else 0.7
        self._safe_update(self.control)

    def begin_jog(self, direction: str, reason: str = "tap_down") -> bool:
        if not self.enabled or direction in self._active_speeds:
            return False
        if self._active_speeds:
            self.set_status("Release the active jog before changing direction.", "error")
            return False

        speed = self._parse_speed(show_error=True)
        if speed is None:
            return False

        speed_text = self._normalized_speed_text(speed)
        self._active_speeds[direction] = speed
        self._set_button_pressed(direction, True)
        self.set_status(
            f"{self._direction_label(direction)} rising edge captured at {speed_text} {self.speed_suffix}.",
            "active",
        )
        self._emit_jog_edge(direction, "rising", speed, speed_text, reason)
        return True

    def end_jog(self, direction: str, reason: str = "tap_up") -> bool:
        if direction not in self._active_speeds:
            return False

        speed = self._active_speeds.pop(direction)
        speed_text = self._normalized_speed_text(speed)
        self._set_button_pressed(direction, False)
        self.set_status(
            f"{self._direction_label(direction)} falling edge captured. Jog stop hook pending.",
            "idle",
        )
        self._emit_jog_edge(direction, "falling", speed, speed_text, reason)
        return True

    def _make_jog_button(self, label, icon, direction, bgcolor, tooltip):
        surface = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=17, color=ft.Colors.WHITE),
                    ft.Text(label, size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=112,
            height=38,
            bgcolor=bgcolor,
            border=ft.Border.all(1, bgcolor),
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            animate=ft.Animation(90, ft.AnimationCurve.EASE_OUT),
            tooltip=tooltip,
        )
        self._button_surfaces[direction] = surface

        detector = ft.GestureDetector(
            content=surface,
            on_tap_down=lambda e, d=direction: self.begin_jog(d, "tap_down"),
            on_tap_up=lambda e, d=direction: self.end_jog(d, "tap_up"),
            on_long_press_up=lambda e, d=direction: self.end_jog(d, "long_press_up"),
            on_long_press_end=lambda e, d=direction: self.end_jog(d, "long_press_end"),
            on_pan_end=lambda e, d=direction: self.end_jog(d, "pan_end"),
            tooltip=tooltip,
        )
        self._edge_detectors.append(detector)
        return detector

    def _handle_reset(self, e) -> None:
        speed = self._parse_speed(show_error=False)
        speed_text = "" if speed is None else self._normalized_speed_text(speed)
        self.set_status("Reset pos click captured. Controller reset hook pending.", "idle")
        if self.on_reset_position:
            self.on_reset_position(
                JogResetEvent(
                    source=self.source,
                    speed=speed,
                    speed_text=speed_text,
                )
            )

    def _handle_speed_change(self, e) -> None:
        speed = self._parse_speed(show_error=False)
        if speed is None:
            return
        self.speed_input.error_text = None
        if self.on_speed_change:
            self.on_speed_change(speed, self._normalized_speed_text(speed))

    def _handle_speed_commit(self, e) -> None:
        speed = self._parse_speed(show_error=True)
        if speed is None:
            return
        speed_text = self._normalized_speed_text(speed)
        self.speed_input.value = speed_text
        self.speed_input.error_text = None
        if self.on_speed_change:
            self.on_speed_change(speed, speed_text)
        self.set_status(f"Jog speed set to {speed_text} {self.speed_suffix}.", "idle")
        self._safe_update(self.speed_input)

    def _parse_speed(self, show_error: bool) -> Optional[float]:
        text = (self.speed_input.value or "").strip().replace(",", ".")
        try:
            speed = float(text)
        except ValueError:
            speed = None
        if speed is None or speed <= 0:
            if show_error:
                self.speed_input.error_text = "Must be > 0"
                self.set_status("Enter a positive jog speed before jogging.", "error")
                self._safe_update(self.speed_input)
            return None
        return speed

    def _emit_jog_edge(self, direction, edge, speed, speed_text, reason) -> None:
        if not self.on_jog_edge:
            return
        self.on_jog_edge(
            JogEdgeEvent(
                direction=direction,
                edge=edge,
                speed=speed,
                speed_text=speed_text,
                source=self.source,
                reason=reason,
            )
        )

    def _set_button_pressed(self, direction, pressed):
        surface = self._button_surfaces.get(direction)
        if surface is None:
            return
        if pressed:
            surface.scale = 0.97
            surface.border = ft.Border.all(2, self.theme.active_border)
        else:
            surface.scale = 1.0
            surface.border = ft.Border.all(1, surface.bgcolor)
        self._safe_update(surface)

    def _normalized_speed_text(self, speed):
        return f"{speed:g}"

    def _direction_label(self, direction):
        return "Jog FWD" if direction == "fwd" else "Jog REV"

    def _safe_update(self, control) -> None:
        if getattr(control, "parent", None) is None:
            return
        try:
            control.update()
        except (AssertionError, RuntimeError):
            pass
