"""Interactive Flet view for inspecting a generated Y/C cam profile."""

from __future__ import annotations

import asyncio
import bisect
import time
from collections.abc import Callable

import flet as ft
import flet_charts as fc
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from .domain import ConvertedProfile, ProfileError
from .simulation import SimulationSeries, build_simulation_series


BG = "#202122"
PANEL = "#2D2E2F"
INPUT_BG = "#222427"
BORDER = "#484B4F"
TEXT = "#F1F2F3"
MUTED = "#A0A5AA"
MASTER = "#FFB000"
Y_COLOR = "#FFB000"
C_COLOR = "#37D67A"
ACCEL = "#EF4C4C"
PATH = "#D5D000"
CHART_BG = "#1E2022"
GRID = "#4A4D50"
BUTTON_INK = "#191A1B"


class SimulationView:
    """Animated, one-shot Y/C profile simulation embedded in the Flet app."""

    def __init__(self, page: ft.Page, on_message: Callable[[str, str], None]) -> None:
        self.page = page
        self.on_message = on_message
        self.profile: ConvertedProfile | None = None
        self.series: SimulationSeries | None = None
        self.index = 0
        self.playing = False
        self._play_generation = 0
        self._artists: dict[str, object] = {}

        self.radius = ft.TextField(
            label="C reference radius",
            value="50",
            suffix="mm",
            width=165,
            dense=True,
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=MASTER,
            border_radius=2,
            color=TEXT,
        )
        self.angle_offset = ft.TextField(
            label="C zero-angle offset",
            value="0",
            suffix="°",
            width=170,
            dense=True,
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=MASTER,
            border_radius=2,
            color=TEXT,
        )
        self.speed = ft.Dropdown(
            label="Playback",
            value="1",
            options=[ft.DropdownOption(key=value, text=f"{value}×") for value in ("0.25", "0.5", "1", "2", "4")],
            width=125,
            dense=True,
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=MASTER,
            border_radius=2,
            color=TEXT,
        )
        self.apply_button = ft.OutlinedButton(
            "Apply geometry",
            icon=ft.Icons.REFRESH,
            on_click=self._rebuild_geometry,
            style=ft.ButtonStyle(color=TEXT, side=ft.BorderSide(1, BORDER), shape=ft.RoundedRectangleBorder(radius=3)),
        )
        self.play_button = ft.FilledButton(
            "Play one-shot",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._toggle_play,
            bgcolor=MASTER,
            color=BUTTON_INK,
            disabled=True,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3)),
        )
        self.reset_button = ft.OutlinedButton(
            "Reset",
            icon=ft.Icons.REPLAY,
            on_click=self._reset,
            disabled=True,
            style=ft.ButtonStyle(color=TEXT, side=ft.BorderSide(1, BORDER), shape=ft.RoundedRectangleBorder(radius=3)),
        )

        self.figure = plt.figure(figsize=(13.2, 7.2), dpi=90, facecolor=PANEL)
        grid = self.figure.add_gridspec(2, 2, width_ratios=(1.18, 1.0), hspace=0.30, wspace=0.31)
        self.ax_motion = self.figure.add_subplot(grid[:, 0])
        self.ax_y = self.figure.add_subplot(grid[0, 1])
        self.ax_c = self.figure.add_subplot(grid[1, 1], sharex=self.ax_y)
        self.ax_y_acc = self.ax_y.twinx()
        self.ax_c_acc = self.ax_c.twinx()
        self.figure.subplots_adjust(left=0.065, right=0.935, top=0.93, bottom=0.10)
        self.chart = fc.MatplotlibChart(figure=self.figure, expand=True)

        self.slider = ft.Slider(
            min=0,
            max=1,
            value=0,
            divisions=1,
            disabled=True,
            active_color=MASTER,
            inactive_color=BORDER,
            on_change=self._scrub,
        )
        self.values = {
            name: ft.Text("—", size=15, color=color, weight=ft.FontWeight.BOLD, font_family="Consolas")
            for name, color in (
                ("point", TEXT),
                ("time", MASTER),
                ("master", MASTER),
                ("y", Y_COLOR),
                ("c", C_COLOR),
                ("yv", Y_COLOR),
                ("cv", C_COLOR),
            )
        }
        self.empty_label = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.MOVIE_FILTER, size=42, color=MUTED),
                    ft.Text("Generate a profile to activate simulation", size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                    ft.Text("The simulation uses the same validated cam points as the BASIC export.", size=11, color=MUTED),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=2,
        )
        self.chart_panel = ft.Container(
            content=self.empty_label,
            expand=True,
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=2,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Y + C MOVEMENT SIMULATION", size=17, color=TEXT, weight=ft.FontWeight.BOLD, font_family="Bahnschrift SemiCondensed"),
                                    ft.Text("Animated mechanism view with synchronized velocity and acceleration", size=10, color=MUTED),
                                ],
                                spacing=2,
                            ),
                            ft.Container(expand=True),
                            self.radius,
                            self.angle_offset,
                            self.apply_button,
                            self.speed,
                            self.reset_button,
                            self.play_button,
                        ],
                        spacing=9,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=15, color=MASTER),
                                ft.Text(
                                    "Schematic geometry: the C centre follows Y; the green point rotates at the configured radius. Use CAD geometry for collision validation.",
                                    size=10,
                                    color=MUTED,
                                    expand=True,
                                ),
                            ],
                            spacing=8,
                        ),
                        bgcolor="#292A2B",
                        border=ft.Border.only(left=ft.BorderSide(3, MASTER)),
                        border_radius=2,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    ),
                    self.chart_panel,
                    self.slider,
                    ft.Row(
                        [
                            self._metric("POINT", "point", 115),
                            self._metric("TIME", "time", 130),
                            self._metric("MASTER", "master", 155),
                            self._metric("Y POSITION", "y", 165),
                            self._metric("C POSITION", "c", 165),
                            self._metric("Y SPEED", "yv", 165),
                            self._metric("C SPEED", "cv", 165),
                        ],
                        spacing=9,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                spacing=8,
                expand=True,
            ),
            padding=10,
            expand=True,
        )

    def _metric(self, label: str, key: str, width: int) -> ft.Container:
        return ft.Container(
            content=ft.Column([ft.Text(label, size=9, color=MUTED), self.values[key]], spacing=2),
            bgcolor=INPUT_BG,
            border=ft.Border.all(1, BORDER),
            border_radius=2,
            padding=10,
            width=width,
        )

    @staticmethod
    def _style_axis(axis, *, ylabel: str, color: str) -> None:
        axis.set_facecolor(CHART_BG)
        axis.tick_params(colors=MUTED, labelsize=8)
        axis.set_ylabel(ylabel, color=color, fontsize=8.5, fontfamily="Bahnschrift")
        axis.grid(True, color=GRID, linewidth=0.55, alpha=0.72)
        for spine in axis.spines.values():
            spine.set_color(BORDER)

    @staticmethod
    def _style_twin(axis, *, ylabel: str) -> None:
        axis.tick_params(colors=ACCEL, labelsize=8)
        axis.set_ylabel(ylabel, color=ACCEL, fontsize=8.5, fontfamily="Bahnschrift")
        for spine in axis.spines.values():
            spine.set_color(BORDER)

    def set_profile(self, profile: ConvertedProfile) -> None:
        self.stop()
        self.profile = profile
        try:
            self.series = build_simulation_series(
                profile,
                radius_mm=float(str(self.radius.value).strip()),
                angle_offset_deg=float(str(self.angle_offset.value).strip()),
            )
        except (ValueError, ProfileError) as exc:
            self.on_message(str(exc), ACCEL)
            return
        self.index = 0
        self.slider.min = 0
        self.slider.max = self.series.count - 1
        self.slider.divisions = self.series.count - 1
        self.slider.value = 0
        self.slider.disabled = False
        self.play_button.disabled = False
        self.reset_button.disabled = False
        self.chart_panel.content = self.chart
        self._draw_profile()
        self.set_frame(0, refresh=False)

    def _draw_profile(self) -> None:
        series = self.series
        if series is None:
            return

        for axis in (self.ax_motion, self.ax_y, self.ax_c, self.ax_y_acc, self.ax_c_acc):
            axis.clear()
        self._style_axis(self.ax_motion, ylabel="Combined Y + C [mm]", color=PATH)
        self._style_axis(self.ax_y, ylabel="Y speed [mm/s]", color=Y_COLOR)
        self._style_axis(self.ax_c, ylabel="C speed [deg/s]", color=C_COLOR)
        self._style_twin(self.ax_y_acc, ylabel="Y accel [mm/s²]")
        self._style_twin(self.ax_c_acc, ylabel="C accel [deg/s²]")

        self.ax_motion.set_title("Schematic machine view", color=TEXT, fontsize=12, fontfamily="Bahnschrift", pad=10)
        self.ax_motion.set_xlabel("C reference-point X [mm]", color=MUTED, fontsize=8.5)
        self.ax_motion.axvline(0.0, color=MUTED, linewidth=1.0, linestyle="--", alpha=0.55)
        self.ax_motion.plot(series.path_x_mm, series.path_y_mm, color="#6A6C6E", linewidth=1.0, linestyle="--", label="Full locus")
        trail, = self.ax_motion.plot([], [], color=PATH, linewidth=2.2, label="Completed locus")
        arm, = self.ax_motion.plot([], [], color=C_COLOR, linewidth=3.0, solid_capstyle="round")
        centre, = self.ax_motion.plot([], [], marker="s", markersize=6, color=Y_COLOR)
        endpoint, = self.ax_motion.plot([], [], marker="o", markersize=7, color=PATH, markeredgecolor="#F3F1A8")
        circle = Circle((0.0, series.y_mm[0]), series.radius_mm, fill=False, edgecolor=C_COLOR, linewidth=1.2, alpha=0.62)
        self.ax_motion.add_patch(circle)
        info = self.ax_motion.text(
            0.025,
            0.975,
            "",
            transform=self.ax_motion.transAxes,
            va="top",
            color=TEXT,
            fontsize=8.5,
            fontfamily="Consolas",
            bbox=dict(boxstyle="square,pad=0.5", facecolor=CHART_BG, edgecolor=BORDER, alpha=0.94),
        )
        x_pad = max(8.0, series.radius_mm * 0.22)
        y_min = min(min(series.path_y_mm), min(series.y_mm) - series.radius_mm)
        y_max = max(max(series.path_y_mm), max(series.y_mm) + series.radius_mm)
        y_pad = max(8.0, (y_max - y_min) * 0.07)
        self.ax_motion.set_xlim(min(series.path_x_mm) - x_pad, max(series.path_x_mm) + x_pad)
        self.ax_motion.set_ylim(y_min - y_pad, y_max + y_pad)
        self.ax_motion.set_aspect("equal", adjustable="datalim")
        self.ax_motion.legend(loc="lower right", fontsize=7, facecolor=PANEL, edgecolor=BORDER, labelcolor=TEXT)

        self.ax_y.set_title("Y axis · velocity and acceleration", color=TEXT, fontsize=11, fontfamily="Bahnschrift", pad=8)
        self.ax_c.set_title("C axis · velocity and acceleration", color=TEXT, fontsize=11, fontfamily="Bahnschrift", pad=8)
        self.ax_y.plot(series.time_s, series.y_speed_mm_s, color=Y_COLOR, linewidth=1.6)
        self.ax_y_acc.plot(series.time_s, series.y_accel_mm_s2, color=ACCEL, linewidth=1.0, alpha=0.78)
        self.ax_c.plot(series.time_s, series.c_speed_deg_s, color=C_COLOR, linewidth=1.6)
        self.ax_c_acc.plot(series.time_s, series.c_accel_deg_s2, color=ACCEL, linewidth=1.0, alpha=0.78)
        self.ax_c.set_xlabel("Profile time [s]", color=MASTER, fontsize=8.5, fontfamily="Bahnschrift")
        y_cursor = self.ax_y.axvline(0.0, color=MASTER, linewidth=1.2, linestyle="--")
        c_cursor = self.ax_c.axvline(0.0, color=MASTER, linewidth=1.2, linestyle="--")
        y_marker, = self.ax_y.plot([], [], marker="o", markersize=5, color=Y_COLOR)
        ya_marker, = self.ax_y_acc.plot([], [], marker="o", markersize=4, color=ACCEL)
        c_marker, = self.ax_c.plot([], [], marker="o", markersize=5, color=C_COLOR)
        ca_marker, = self.ax_c_acc.plot([], [], marker="o", markersize=4, color=ACCEL)
        self._artists = {
            "trail": trail,
            "arm": arm,
            "centre": centre,
            "endpoint": endpoint,
            "circle": circle,
            "info": info,
            "y_cursor": y_cursor,
            "c_cursor": c_cursor,
            "y_marker": y_marker,
            "ya_marker": ya_marker,
            "c_marker": c_marker,
            "ca_marker": ca_marker,
        }
        self.figure.canvas.draw_idle()

    def set_frame(self, index: int, *, refresh: bool = True) -> None:
        series = self.series
        if series is None or not self._artists:
            return
        self.index = max(0, min(index, series.count - 1))
        i = self.index
        t = series.time_s[i]
        x = series.path_x_mm[i]
        path_y = series.path_y_mm[i]
        centre_y = series.y_mm[i]

        self._artists["trail"].set_data(series.path_x_mm[: i + 1], series.path_y_mm[: i + 1])
        self._artists["arm"].set_data([0.0, x], [centre_y, path_y])
        self._artists["centre"].set_data([0.0], [centre_y])
        self._artists["endpoint"].set_data([x], [path_y])
        self._artists["circle"].center = (0.0, centre_y)
        self._artists["info"].set_text(
            f"POINT  {i + 1:04d}/{series.count:04d}\n"
            f"TIME   {t:8.3f} s\n"
            f"Y      {centre_y:8.3f} mm\n"
            f"C      {series.c_deg[i]:8.3f} deg"
        )
        for key in ("y_cursor", "c_cursor"):
            self._artists[key].set_xdata([t, t])
        self._artists["y_marker"].set_data([t], [series.y_speed_mm_s[i]])
        self._artists["ya_marker"].set_data([t], [series.y_accel_mm_s2[i]])
        self._artists["c_marker"].set_data([t], [series.c_speed_deg_s[i]])
        self._artists["ca_marker"].set_data([t], [series.c_accel_deg_s2[i]])

        self.slider.value = i
        self.values["point"].value = f"{i + 1} / {series.count}"
        self.values["time"].value = f"{t:.3f} s"
        self.values["master"].value = f"{series.master_mm[i]:.3f} mm"
        self.values["y"].value = f"{centre_y:.3f} mm"
        self.values["c"].value = f"{series.c_deg[i]:.3f}°"
        self.values["yv"].value = f"{series.y_speed_mm_s[i]:.2f} mm/s"
        self.values["cv"].value = f"{series.c_speed_deg_s[i]:.2f}°/s"
        self.figure.canvas.draw_idle()
        if refresh:
            try:
                self.page.update()
            except RuntimeError:
                self.stop()

    def _scrub(self, event) -> None:
        self.stop()
        self.set_frame(int(round(float(event.control.value or 0))))

    def _rebuild_geometry(self, _=None) -> None:
        if self.profile is None:
            self.on_message("Generate a valid profile before configuring the simulation.", ACCEL)
            return
        self.set_profile(self.profile)
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _reset(self, _=None) -> None:
        self.stop()
        self.set_frame(0)

    def _toggle_play(self, _=None) -> None:
        if self.series is None:
            self.on_message("Generate a valid profile before starting the simulation.", ACCEL)
            return
        if self.playing:
            self.stop()
            self.page.update()
            return
        if self.index >= self.series.count - 1:
            self.set_frame(0, refresh=False)
        self.playing = True
        self._play_generation += 1
        generation = self._play_generation
        self.play_button.text = "Pause"
        self.play_button.icon = ft.Icons.PAUSE
        self.page.update()
        self.page.run_task(self._play_loop, generation)

    async def _play_loop(self, generation: int) -> None:
        series = self.series
        if series is None:
            return
        start_profile_time = series.time_s[self.index]
        start_clock = time.monotonic()
        while self.playing and generation == self._play_generation:
            multiplier = float(self.speed.value or "1")
            target_time = start_profile_time + (time.monotonic() - start_clock) * multiplier
            index = bisect.bisect_right(series.time_s, target_time) - 1
            if index >= series.count - 1:
                self.set_frame(series.count - 1)
                self.stop()
                try:
                    self.page.update()
                except RuntimeError:
                    pass
                return
            self.set_frame(max(0, index))
            await asyncio.sleep(1.0 / 30.0)

    def stop(self) -> None:
        self.playing = False
        self._play_generation += 1
        self.play_button.text = "Play one-shot"
        self.play_button.icon = ft.Icons.PLAY_ARROW


__all__ = ["SimulationView"]
