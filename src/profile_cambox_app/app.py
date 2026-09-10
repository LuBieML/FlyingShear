"""Flet UI for the standalone profile CAMBOX generator."""

from __future__ import annotations

from dataclasses import fields
import os
from pathlib import Path
import re

import flet as ft
import flet_charts as fc
import matplotlib.pyplot as plt

from .codegen import emit_points_csv, emit_trio_basic
from .domain import ConvertedProfile, ProfileConfig, ProfileError, convert_profile, load_profile_csv
from .settings import load_config, save_config
from .simulation_view import SimulationView
from .help_text import SETTING_HELP


BG = "#202122"
PANEL = "#2D2E2F"
PANEL_ALT = "#36383A"
INPUT_BG = "#222427"
BORDER = "#484B4F"
TEXT = "#F1F2F3"
MUTED = "#A0A5AA"
MASTER = "#FFB000"
Y_COLOR = "#FFB000"
C_COLOR = "#37D67A"
SUCCESS = "#29C866"
WARNING = "#FFB000"
ERROR = "#EF4C4C"
CHART_BG = "#1E2022"
GRID = "#4A4D50"
BUTTON_INK = "#191A1B"


def _clean_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "profile_cambox"


def main(page: ft.Page) -> None:
    page.title = os.environ.get("PROFILE_CAMBOX_WINDOW_TITLE", "Profile CAMBOX Generator")
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.window.width = 1500
    page.window.height = 980
    page.window.min_width = 1120
    page.window.min_height = 760
    page.theme = ft.Theme(font_family="Segoe UI", color_scheme_seed=MASTER)

    stored = load_config()
    file_picker = ft.FilePicker()
    page.services.append(file_picker)
    state: dict[str, ConvertedProfile | str | None] = {"profile": None, "basic": "", "csv": ""}
    controls: dict[str, ft.Control] = {}

    def show_message(message: str, color: str = PANEL_ALT) -> None:
        page.show_dialog(ft.SnackBar(message, bgcolor=color, show_close_icon=True))

    def section_title(title: str, subtitle: str) -> ft.Control:
        return ft.Column([
            ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=TEXT, font_family="Bahnschrift SemiCondensed"),
            ft.Text(subtitle, size=10, color=MUTED),
        ], spacing=2)

    def field_control(key: str, label: str, value, *, suffix: str | None = None, width: int = 160) -> ft.TextField:
        control = ft.TextField(
            label=label,
            tooltip=SETTING_HELP[key],
            value=str(value),
            suffix=suffix,
            width=width,
            dense=True,
            bgcolor=INPUT_BG,
            color=TEXT,
            border_color=BORDER,
            focused_border_color=MASTER,
            border_radius=2,
            text_size=12,
        )
        controls[key] = control
        return control

    def switch_control(key: str, label: str, value: bool) -> ft.Switch:
        control = ft.Switch(label=label, tooltip=SETTING_HELP[key], value=value, active_color=MASTER, label_text_style=ft.TextStyle(size=11, color=TEXT))
        controls[key] = control
        return control

    def config_card(title: str, subtitle: str, content: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Column([section_title(title, subtitle), *content], spacing=10),
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=2,
            padding=12,
        )

    source_path = ft.TextField(
        label="CSV profile",
        tooltip="The CSV file you are using. Click Import CSV to choose another file. Use the column settings below to tell the app where to find time, Y and C.",
        hint_text="Import a time / Y / C CSV file",
        read_only=True,
        expand=True,
        dense=True,
        bgcolor=INPUT_BG,
        border_color=BORDER,
        border_radius=2,
        color=TEXT,
        text_size=11,
    )

    # Configuration controls are deliberately compact: this is an engineering
    # commissioning surface, not a wizard.
    source_card = config_card("Source mapping", "Time in seconds, Y in millimetres, C in radians", [
        ft.Row([field_control("time_column", "Time column", stored.time_column, width=105), field_control("y_column", "Y column", stored.y_column, width=105), field_control("c_column", "C column", stored.c_column, width=105)], spacing=8),
        switch_control("unwrap_c_axis", "Unwrap C across ±π", stored.unwrap_c_axis),
    ])
    axes_card = config_card("Axes and direction", "Independent slaves linked to virtual master DPOS", [
        ft.Row([field_control("y_axis", "Y axis", stored.y_axis, width=100), field_control("c_axis", "C axis", stored.c_axis, width=100), field_control("master_axis", "Master", stored.master_axis, width=100)], spacing=8),
        ft.Row([switch_control("invert_y", "Invert Y", stored.invert_y), switch_control("invert_c", "Invert C", stored.invert_c)], spacing=14),
    ])
    scaling_card = config_card("Encoder scaling", "2²³ counts/rev with 4 mm linear pitch and 0.1° C units", [
        ft.Row([field_control("master_encoder_counts_per_rev", "Master counts/rev", stored.master_encoder_counts_per_rev, width=155), field_control("master_travel_per_rev_mm", "Travel/rev", stored.master_travel_per_rev_mm, suffix="mm", width=155)], spacing=8),
        ft.Row([field_control("y_encoder_counts_per_rev", "Y counts/rev", stored.y_encoder_counts_per_rev, width=155), field_control("y_travel_per_rev_mm", "Travel/rev", stored.y_travel_per_rev_mm, suffix="mm", width=155)], spacing=8),
        ft.Row([field_control("c_encoder_counts_per_rev", "C counts/rev", stored.c_encoder_counts_per_rev, width=155), field_control("c_user_unit_deg", "C user unit", stored.c_user_unit_deg, suffix="°", width=155)], spacing=8),
    ])
    master_card = config_card("Master motion", "Lead-in keeps the full CAM profile at constant line speed", [
        ft.Row([field_control("master_speed_mm_s", "Speed", stored.master_speed_mm_s, suffix="mm/s", width=155), field_control("master_accel_mm_s2", "Acceleration", stored.master_accel_mm_s2, suffix="mm/s²", width=155)], spacing=8),
        ft.Row([field_control("master_decel_mm_s2", "Deceleration", stored.master_decel_mm_s2, suffix="mm/s²", width=155), field_control("lead_margin_mm", "Lead margin", stored.lead_margin_mm, suffix="mm", width=155)], spacing=8),
    ])
    preposition_card = config_card("Slave preposition", "Independent absolute moves before CAMBOX is armed", [
        ft.Row([field_control("y_preposition_speed_mm_s", "Y speed", stored.y_preposition_speed_mm_s, suffix="mm/s", width=155), field_control("c_preposition_speed_deg_s", "C speed", stored.c_preposition_speed_deg_s, suffix="°/s", width=155)], spacing=8),
        ft.Row([field_control("y_preposition_accel_mm_s2", "Y accel", stored.y_preposition_accel_mm_s2, suffix="mm/s²", width=155), field_control("c_preposition_accel_deg_s2", "C accel", stored.c_preposition_accel_deg_s2, suffix="°/s²", width=155)], spacing=8),
        ft.Row([field_control("y_preposition_decel_mm_s2", "Y decel", stored.y_preposition_decel_mm_s2, suffix="mm/s²", width=155), field_control("c_preposition_decel_deg_s2", "C decel", stored.c_preposition_decel_deg_s2, suffix="°/s²", width=155)], spacing=8),
    ])
    table_card = config_card("Controller TABLE", "Non-overlapping raw-count blocks", [
        ft.Row([field_control("y_table_start", "Y start", stored.y_table_start, width=100), field_control("c_table_start", "C start", stored.c_table_start, width=100), field_control("table_size", "TSIZE", stored.table_size, width=110)], spacing=8),
        ft.Row([field_control("values_per_table_line", "Values/line", stored.values_per_table_line, width=120), field_control("time_uniformity_tolerance_pct", "Time tolerance", stored.time_uniformity_tolerance_pct, suffix="%", width=160)], spacing=8),
        field_control("program_name", "Program name", stored.program_name, width=320),
    ])

    int_keys = {"y_axis", "c_axis", "master_axis", "y_table_start", "c_table_start", "table_size", "values_per_table_line"}
    bool_keys = {"unwrap_c_axis", "invert_y", "invert_c"}
    string_keys = {"time_column", "y_column", "c_column", "program_name"}

    def read_config() -> ProfileConfig:
        values = {}
        for item in fields(ProfileConfig):
            key = item.name
            control = controls.get(key)
            if control is None:
                values[key] = getattr(stored, key)
            elif key in bool_keys:
                values[key] = bool(control.value)
            elif key in string_keys:
                values[key] = str(control.value or "").strip()
            elif key in int_keys:
                values[key] = int(float(str(control.value).strip()))
            else:
                values[key] = float(str(control.value).strip())
        return ProfileConfig(**values)

    # Profile chart and shared inspection cursor.
    figure, (y_axes, c_axes) = plt.subplots(2, 1, sharex=True, figsize=(10.5, 5.0), dpi=100)
    figure.patch.set_facecolor(PANEL)
    figure.subplots_adjust(left=0.085, right=0.985, top=0.94, bottom=0.12, hspace=0.14)
    for axes, label, color in ((y_axes, "Y position [mm]", Y_COLOR), (c_axes, "C position [deg]", C_COLOR)):
        axes.set_facecolor(CHART_BG)
        axes.tick_params(colors=MUTED, labelsize=8)
        axes.set_ylabel(label, color=color, fontsize=9, fontfamily="Bahnschrift")
        axes.grid(True, color=GRID, linewidth=0.55, alpha=0.75)
        for spine in axes.spines.values():
            spine.set_color(BORDER)
    c_axes.set_xlabel("Virtual master distance [mm]", color=MASTER, fontsize=9, fontfamily="Bahnschrift")
    chart = fc.MatplotlibChart(figure=figure, expand=True)
    cursor_artists: list = []

    cursor_slider = ft.Slider(min=0, max=1, value=0, divisions=1, active_color=MASTER, inactive_color=BORDER, disabled=True, tooltip="Drag to look at a different moment in the movement. The numbers below show the positions at that moment. Release to move the vertical lines on the graphs.")
    cursor_values = {
        key: ft.Text("—", size=16, color=color, weight=ft.FontWeight.BOLD, font_family="Consolas")
        for key, color in (("master", MASTER), ("time", TEXT), ("y", Y_COLOR), ("c", C_COLOR), ("counts", MUTED))
    }

    def metric(label: str, key: str, width: int = 160) -> ft.Container:
        return ft.Container(
            content=ft.Column([ft.Text(label, size=9, color=MUTED), cursor_values[key]], spacing=2),
            bgcolor=INPUT_BG,
            border=ft.Border.all(1, BORDER),
            border_radius=2,
            padding=10,
            width=width,
        )

    cursor_row = ft.Row([
        metric("MASTER", "master"), metric("TIME", "time", 130), metric("Y ABSOLUTE", "y"), metric("C ABSOLUTE", "c"), metric("RAW COUNTS Y / C", "counts", 230),
    ], spacing=9, scroll=ft.ScrollMode.AUTO)

    basic_preview = ft.TextField(
        value="Import a CSV profile to generate Trio BASIC.",
        multiline=True,
        read_only=True,
        min_lines=18,
        max_lines=18,
        expand=True,
        bgcolor=INPUT_BG,
        border_color=BORDER,
        border_radius=2,
        color=TEXT,
        text_size=11,
        text_style=ft.TextStyle(font_family="Consolas"),
    )
    points_preview = ft.Column([ft.Text("No profile points generated.", color=MUTED)], scroll=ft.ScrollMode.AUTO, expand=True)
    diagnostics_view = ft.Column([ft.Text("Import and generate a profile to run validation.", color=MUTED)], scroll=ft.ScrollMode.AUTO, expand=True)
    status_text = ft.Text("Ready — import a CSV profile", color=MUTED, size=11)
    status_dot = ft.Container(width=10, height=10, border_radius=2, bgcolor=MUTED)
    generate_button = ft.FilledButton("Generate", icon=ft.Icons.AUTO_GRAPH, bgcolor=MASTER, color=BUTTON_INK, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3)))
    export_button = ft.FilledButton("Export BASIC + points", icon=ft.Icons.SAVE_ALT, bgcolor=Y_COLOR, color=BUTTON_INK, disabled=True, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3)))

    def set_cursor(index: int, redraw: bool = False) -> None:
        profile = state.get("profile")
        if not isinstance(profile, ConvertedProfile):
            return
        index = max(0, min(index, len(profile.points) - 1))
        point = profile.points[index]
        cursor_values["master"].value = f"{point.master_mm:.3f} mm"
        cursor_values["time"].value = f"{point.time_s:.3f} s"
        cursor_values["y"].value = f"{point.y_absolute_mm:.4f} mm"
        cursor_values["c"].value = f"{point.c_absolute_deg:.4f}°"
        cursor_values["counts"].value = f"{point.y_counts:,}  /  {point.c_counts:,}"
        if redraw:
            for artist in cursor_artists:
                artist.set_xdata([point.master_mm, point.master_mm])
            figure.canvas.draw_idle()
            try:
                chart.update()
            except RuntimeError:
                pass
        for control in cursor_values.values():
            try:
                control.update()
            except RuntimeError:
                pass

    def on_cursor_change(event) -> None:
        set_cursor(int(round(float(event.control.value or 0))), redraw=False)

    def on_cursor_end(event) -> None:
        set_cursor(int(round(float(event.control.value or 0))), redraw=True)

    cursor_slider.on_change = on_cursor_change
    cursor_slider.on_change_end = on_cursor_end

    def update_chart(profile: ConvertedProfile) -> None:
        nonlocal cursor_artists
        masters = [point.master_mm for point in profile.points]
        y_values = [point.y_absolute_mm for point in profile.points]
        c_values = [point.c_absolute_deg for point in profile.points]
        y_axes.clear()
        c_axes.clear()
        for axes, label, color in ((y_axes, "Y position [mm]", Y_COLOR), (c_axes, "C position [deg]", C_COLOR)):
            axes.set_facecolor(CHART_BG)
            axes.tick_params(colors=MUTED, labelsize=8)
            axes.set_ylabel(label, color=color, fontsize=9, fontfamily="Bahnschrift")
            axes.grid(True, color=GRID, linewidth=0.55, alpha=0.75)
            for spine in axes.spines.values():
                spine.set_color(BORDER)
        y_axes.plot(masters, y_values, color=Y_COLOR, linewidth=1.8)
        c_axes.plot(masters, c_values, color=C_COLOR, linewidth=1.8)
        c_axes.set_xlabel("Virtual master distance [mm]", color=MASTER, fontsize=9, fontfamily="Bahnschrift")
        cursor_artists = [y_axes.axvline(0, color=MASTER, linewidth=1.1), c_axes.axvline(0, color=MASTER, linewidth=1.1)]
        figure.canvas.draw_idle()
        cursor_slider.disabled = False
        cursor_slider.min = 0
        cursor_slider.max = len(profile.points) - 1
        cursor_slider.divisions = len(profile.points) - 1
        cursor_slider.value = 0
        set_cursor(0)

    def update_points_preview(profile: ConvertedProfile) -> None:
        sample_indexes = list(range(min(8, len(profile.points))))
        if len(profile.points) > 12:
            sample_indexes.extend(range(len(profile.points) - 4, len(profile.points)))
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(label, size=10, color=MUTED)) for label in ("#", "Master mm", "Y mm", "Y counts", "C deg", "C counts")],
            rows=[
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(profile.points[index].index), size=10)),
                    ft.DataCell(ft.Text(f"{profile.points[index].master_mm:.3f}", size=10)),
                    ft.DataCell(ft.Text(f"{profile.points[index].y_absolute_mm:.4f}", size=10, color=Y_COLOR)),
                    ft.DataCell(ft.Text(f"{profile.points[index].y_counts:,}", size=10, font_family="Consolas")),
                    ft.DataCell(ft.Text(f"{profile.points[index].c_absolute_deg:.4f}", size=10, color=C_COLOR)),
                    ft.DataCell(ft.Text(f"{profile.points[index].c_counts:,}", size=10, font_family="Consolas")),
                ]) for index in sample_indexes
            ],
            column_spacing=24,
            heading_row_color=PANEL_ALT,
            data_row_min_height=34,
            data_row_max_height=34,
        )
        points_preview.controls = [
            ft.Text(f"Showing {len(sample_indexes)} representative rows of {len(profile.points)}. The export contains every point.", size=10, color=MUTED),
            ft.Row([table], scroll=ft.ScrollMode.AUTO),
        ]

    def diagnostic_row(label: str, value: str, color: str = TEXT) -> ft.Container:
        return ft.Container(
            content=ft.Row([ft.Text(label, size=11, color=MUTED), ft.Text(value, size=11, color=color, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.symmetric(vertical=8, horizontal=2),
        )

    def update_diagnostics(profile: ConvertedProfile) -> None:
        d = profile.diagnostics
        rows = [
            diagnostic_row("Source samples", f"{d.sample_count:,} at {d.sample_interval_s:.6f} s"),
            diagnostic_row("Master profile", f"{d.link_distance_mm:.3f} mm · {d.master_step_mm:.3f} mm/interval", MASTER),
            diagnostic_row("Master CAM start", f"{d.profile_start_master_mm:.3f} mm absolute DPOS", MASTER),
            diagnostic_row("Y preposition → end", f"{d.y_start_mm:.6f} → {d.y_end_mm:.6f} mm", Y_COLOR),
            diagnostic_row("C preposition → end", f"{d.c_start_deg:.6f}° → {d.c_end_deg:.6f}°", C_COLOR),
            diagnostic_row("Y peak speed / acceleration", f"{d.y_peak_speed_mm_s:.3f} mm/s · {d.y_peak_accel_mm_s2:.3f} mm/s²"),
            diagnostic_row("C peak speed / acceleration", f"{d.c_peak_speed_deg_s:.3f}°/s · {d.c_peak_accel_deg_s2:.3f}°/s²"),
            diagnostic_row("Y TABLE", f"{profile.config.y_table_start}..{d.y_table_end} · {d.y_min_counts:,}..{d.y_max_counts:,} counts"),
            diagnostic_row("C TABLE", f"{profile.config.c_table_start}..{d.c_table_end} · {d.c_min_counts:,}..{d.c_max_counts:,} counts"),
            diagnostic_row("CAMBOX mode", "Separate one-shot commands · options 8194", SUCCESS),
        ]
        for warning in d.warnings:
            rows.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.WARNING_AMBER, color=WARNING, size=17), ft.Text(warning, size=11, color=WARNING, expand=True)], spacing=8), bgcolor="#3A301B", border_radius=2, padding=10))
        diagnostics_view.controls = rows

    def generate_profile(_=None) -> None:
        if not source_path.value:
            show_message("Import a CSV profile first.", ERROR)
            return
        try:
            config = read_config()
            raw = load_profile_csv(source_path.value, config)
            profile = convert_profile(raw, config)
            basic = emit_trio_basic(profile)
            points_csv = emit_points_csv(profile)
            save_config(config)
        except (ProfileError, ValueError, OSError, RuntimeError) as exc:
            state.update(profile=None, basic="", csv="")
            basic_preview.value = f"Generation blocked:\n\n{exc}"
            export_button.disabled = True
            status_dot.bgcolor = ERROR
            status_text.value = f"Blocked — {exc}"
            status_text.color = ERROR
            page.update()
            return

        state.update(profile=profile, basic=basic, csv=points_csv)
        basic_preview.value = basic
        update_chart(profile)
        update_points_preview(profile)
        update_diagnostics(profile)
        simulation_view.set_profile(profile)
        export_button.disabled = False
        status_dot.bgcolor = SUCCESS
        status_text.value = f"Validated — {len(profile.points):,} points per axis · {profile.diagnostics.link_distance_mm:.3f} mm master profile"
        status_text.color = SUCCESS
        page.update()

    async def import_csv(_=None) -> None:
        selected = await file_picker.pick_files(
            dialog_title="Import time / Y / C profile",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["csv", "tsv", "txt"],
            allow_multiple=False,
        )
        if not selected:
            return
        source_path.value = selected[0].path
        generate_profile()

    async def export_files(_=None) -> None:
        profile = state.get("profile")
        if not isinstance(profile, ConvertedProfile):
            show_message("Generate a valid profile before exporting.", ERROR)
            return
        directory = await file_picker.get_directory_path(dialog_title="Export BASIC program and CAM points")
        if not directory:
            return
        stem = _clean_filename(profile.config.program_name.lower())
        bas_path = Path(directory) / f"{stem}.bas"
        csv_path = Path(directory) / f"{stem}_cam_points.csv"
        try:
            bas_path.write_text(str(state["basic"]), encoding="utf-8")
            csv_path.write_text(str(state["csv"]), encoding="utf-8", newline="")
        except OSError as exc:
            show_message(f"Export failed: {exc}", ERROR)
            return
        show_message(f"Exported {bas_path.name} and {csv_path.name}", SUCCESS)

    async def copy_basic(_=None) -> None:
        if not state.get("basic"):
            show_message("Generate a valid profile first.", ERROR)
            return
        await page.clipboard.set(str(state["basic"]))
        show_message("Trio BASIC copied to clipboard.", SUCCESS)

    generate_button.on_click = generate_profile
    export_button.on_click = export_files

    tabs = ft.Tabs(
        length=3,
        selected_index=0,
        content=ft.Column([
            ft.TabBar(
                tabs=[ft.Tab(label="Diagnostics", icon=ft.Icons.VERIFIED), ft.Tab(label="CAM points", icon=ft.Icons.TABLE_CHART), ft.Tab(label="Trio BASIC", icon=ft.Icons.CODE)],
                label_color=MASTER,
                unselected_label_color=MUTED,
                indicator_color=MASTER,
                divider_color=BORDER,
            ),
            ft.TabBarView(controls=[
                ft.Container(diagnostics_view, padding=12),
                ft.Container(points_preview, padding=12),
                ft.Container(ft.Column([
                    ft.Row([ft.Text("Generated one-shot program", size=11, color=MUTED), ft.Container(expand=True), ft.TextButton("Copy BASIC", icon=ft.Icons.CONTENT_COPY, on_click=copy_basic)], spacing=8),
                    basic_preview,
                ], expand=True), padding=12),
            ], expand=1),
        ], expand=True),
        expand=True,
    )

    generator_nav = ft.FilledButton(
        "Generator",
        icon=ft.Icons.TUNE,
        bgcolor=MASTER,
        color=BUTTON_INK,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3)),
    )
    simulation_nav = ft.FilledButton(
        "Simulation",
        icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
        bgcolor=PANEL_ALT,
        color=MUTED,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3)),
    )

    def show_view(name: str) -> None:
        is_simulation = name == "simulation"
        if not is_simulation:
            simulation_view.stop()
        # Keep chart canvases mounted: removing them disconnects their backend
        # stream, which is not restored when the same control is reinserted.
        generator_page.opacity = 0 if is_simulation else 1
        generator_page.ignore_interactions = is_simulation
        generator_page.disabled = is_simulation
        simulation_page.opacity = 1 if is_simulation else 0
        simulation_page.ignore_interactions = not is_simulation
        simulation_page.disabled = not is_simulation
        generator_nav.bgcolor = PANEL_ALT if is_simulation else MASTER
        generator_nav.color = MUTED if is_simulation else BUTTON_INK
        simulation_nav.bgcolor = MASTER if is_simulation else PANEL_ALT
        simulation_nav.color = BUTTON_INK if is_simulation else MUTED
        page.update()

    generator_nav.on_click = lambda _: show_view("generator")
    simulation_nav.on_click = lambda _: show_view("simulation")

    header = ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Column([
                    ft.Text("PROFILE CAMBOX", size=22, weight=ft.FontWeight.W_700, color=TEXT, font_family="Bahnschrift SemiCondensed"),
                    ft.Text("CSV trajectory → synchronized Y / C controller tables", size=10, color=MUTED),
                ], spacing=1),
                width=290,
            ),
            ft.Row([generator_nav, simulation_nav], spacing=6),
            source_path,
            ft.OutlinedButton("Import CSV", icon=ft.Icons.UPLOAD_FILE, on_click=import_csv, style=ft.ButtonStyle(color=TEXT, side=ft.BorderSide(1, BORDER), shape=ft.RoundedRectangleBorder(radius=3))),
            generate_button,
            export_button,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=PANEL,
        border=ft.Border.only(bottom=ft.BorderSide(2, MASTER)),
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
    )

    sidebar = ft.Container(
        content=ft.Column([source_card, axes_card, scaling_card, master_card, preposition_card, table_card], spacing=7, scroll=ft.ScrollMode.AUTO),
        width=365,
        padding=ft.Padding.only(left=14, right=8, top=14, bottom=14),
    )
    chart_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([ft.Text("Synchronized master-distance view", size=15, weight=ft.FontWeight.BOLD, color=TEXT), ft.Text("One cursor reads the same CAM interval on both slave axes", size=10, color=MUTED)], spacing=2),
                ft.Container(expand=True),
                ft.Row([ft.Container(width=8, height=8, border_radius=1, bgcolor=Y_COLOR), ft.Text("Y", color=Y_COLOR, size=10), ft.Container(width=8, height=8, border_radius=1, bgcolor=C_COLOR), ft.Text("C", color=C_COLOR, size=10)], spacing=6),
            ]),
            ft.Container(chart, height=420, bgcolor=PANEL, border_radius=2, clip_behavior=ft.ClipBehavior.HARD_EDGE),
            cursor_slider,
            cursor_row,
        ], spacing=8),
        bgcolor=PANEL,
        border=ft.Border.all(1, BORDER),
        border_radius=2,
        padding=12,
    )
    workspace = ft.Container(
        content=ft.Column([
            chart_panel,
            ft.Container(tabs, height=360, bgcolor=PANEL, border=ft.Border.all(1, BORDER), border_radius=2, clip_behavior=ft.ClipBehavior.HARD_EDGE),
        ], spacing=8, scroll=ft.ScrollMode.AUTO),
        expand=True,
        padding=ft.Padding.only(left=6, right=14, top=14, bottom=14),
    )
    simulation_view = SimulationView(page, show_message)
    generator_body = ft.Row([sidebar, workspace], expand=True, spacing=0)
    generator_page = ft.Container(content=generator_body, expand=True)
    simulation_page = ft.Container(
        content=simulation_view.control, expand=True,
        opacity=0, ignore_interactions=True, disabled=True,
    )
    body_holder = ft.Stack(
        controls=[generator_page, simulation_page],
        fit=ft.StackFit.EXPAND, expand=True,
    )
    footer = ft.Container(
        content=ft.Row([status_dot, status_text, ft.Container(expand=True), ft.Text("Offline generator · no controller writes", size=10, color=MUTED)], spacing=8),
        bgcolor="#262728",
        border=ft.Border.only(top=ft.BorderSide(1, BORDER)),
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
    )

    page.add(ft.Column([header, body_holder, footer], expand=True, spacing=0))

    automation_input = os.environ.get("PROFILE_CAMBOX_INPUT", "").strip()
    if automation_input and Path(automation_input).exists():
        source_path.value = str(Path(automation_input).resolve())
        generate_profile()


__all__ = ["main"]
