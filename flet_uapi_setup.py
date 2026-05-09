import flet as ft
import flet.canvas as cv
import collections
import sys
import os
import json
import math
import time
import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor

# Windows default timer resolution is ~15.6ms which caps asyncio.sleep() precision.
# Set to 1ms for smooth 60 FPS updates.
if sys.platform == "win32":
    ctypes.windll.winmm.timeBeginPeriod(1)

# Add the current directory to sys.path to allow importing from src
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- Persistent settings via JSON file ---
SETTINGS_FILE = os.path.join(current_dir, "setup_settings.json")

def load_settings():
    """Load settings from the JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_settings(settings):
    """Save settings to the JSON file."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save settings: {e}")

def compute_rotary_mpos_counts_per_physical_rev(encoder_counts_per_rev, drum_axis_units):
    """Convert drive encoder CPR and Trio UNITS into MPOS units per drum turn."""
    cpr = float(encoder_counts_per_rev)
    units = float(drum_axis_units)
    if cpr <= 0:
        raise ValueError("Encoder counts/rev must be > 0")
    if units <= 0:
        raise ValueError("Drum axis UNITS must be > 0")
    return cpr / units

def compute_rotary_drum_angle_rad(drum_mpos, mpos_counts_per_physical_rev):
    divisor = float(mpos_counts_per_physical_rev)
    if divisor <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    return ((float(drum_mpos) % divisor) / divisor) * 2.0 * math.pi

def shortest_angle_distance_rad(angle, target):
    return abs(((float(angle) - float(target) + math.pi) % (2.0 * math.pi)) - math.pi)

def rotary_blade_direction_for_angle(drum_angle):
    angle = float(drum_angle)
    return math.sin(angle), -math.cos(angle)

def compute_rotary_drum_tangential_mm_s(
    drum_mspeed,
    mpos_counts_per_physical_rev,
    drum_diameter_mm,
):
    divisor = float(mpos_counts_per_physical_rev)
    diameter = float(drum_diameter_mm)
    if divisor <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")
    drum_rps = float(drum_mspeed) / divisor
    return drum_rps * math.pi * diameter

def compute_rotary_drum_kinematics(
    drum_mpos,
    drum_mspeed,
    mpos_counts_per_physical_rev,
    drum_diameter_mm,
    drum_direction_reversed=False,
):
    """Return shared rotary drum unit conversions for live diagnostics and drawing."""
    mpos_per_rev = float(mpos_counts_per_physical_rev)
    diameter = float(drum_diameter_mm)
    if mpos_per_rev <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")

    direction_sign = -1.0 if drum_direction_reversed else 1.0
    circumference = math.pi * diameter
    raw_mpos = None if drum_mpos is None else float(drum_mpos)
    raw_mspeed = None if drum_mspeed is None else float(drum_mspeed)
    effective_mspeed = None if raw_mspeed is None else raw_mspeed * direction_sign

    drum_angle_rad = None
    if raw_mpos is not None:
        drum_fraction_of_rev = (raw_mpos % mpos_per_rev) / mpos_per_rev
        drum_angle_rad = (drum_fraction_of_rev * 2.0 * math.pi * direction_sign) % (2.0 * math.pi)

    drum_rps = None
    drum_tangential_mm_s = None
    if effective_mspeed is not None:
        drum_rps = effective_mspeed / mpos_per_rev
        drum_tangential_mm_s = drum_rps * circumference

    return {
        "drum_mpos": raw_mpos,
        "drum_mspeed": raw_mspeed,
        "effective_drum_mspeed": effective_mspeed,
        "mpos_per_rev": mpos_per_rev,
        "drum_rps": drum_rps,
        "drum_circumference_mm": circumference,
        "drum_tangential_mm_s": drum_tangential_mm_s,
        "drum_angle_rad": drum_angle_rad,
    }

try:
    # Standalone mode: trio_connection.py sits next to this script
    from trio_connection import TrioConnection
except ImportError:
    try:
        # Full project mode: running from the gcode_interpretter root
        from src.core.trio_connection import TrioConnection
    except ImportError as e:
        print(f"Error importing TrioConnection: {e}")
        print("Make sure trio_connection.py is next to this script, or run from the gcode_interpretter project root.")
        sys.exit(1)

def main(page: ft.Page):
    page.title = "Trio Motion Setup"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    default_window_width = 1728
    default_window_height = 1200
    page.window_width = default_window_width
    page.window_height = default_window_height
    page.window.width = default_window_width
    page.window.height = default_window_height
    page.window.min_width = 1120
    page.window.min_height = 760

    # Industrial dark theme tokens. The palette keeps the tool calm and
    # readable while giving machine-state colors clear priority.
    DARK_BG = "#17191c"
    DARKER_BG = "#111316"
    PANEL_BG = "#20242a"
    PANEL_ALT_BG = "#181b20"
    BORDER_COLOR = "#343a40"
    ACCENT_COLOR = "#007acc"
    TEXT_COLOR = "#d4d4d4"
    MUTED_TEXT = ft.Colors.GREY_500
    SUCCESS_COLOR = ft.Colors.GREEN_300
    WARNING_COLOR = ft.Colors.AMBER_300
    ERROR_COLOR = ft.Colors.RED_300

    page.bgcolor = DARK_BG
    page.theme = ft.Theme(color_scheme_seed=ACCENT_COLOR, use_material3=True)
    page.dark_theme = ft.Theme(color_scheme_seed=ACCENT_COLOR, use_material3=True)

    # Load persisted settings
    settings = load_settings()

    def _update_if_mounted(control):
        try:
            control.update()
            return True
        except AssertionError:
            return False
        except RuntimeError as ex:
            if "must be added to the page first" in str(ex):
                return False
            raise

    def show_snack(message, type_="info"):
        palette = {
            "success": ("#133a25", ft.Icons.CHECK_CIRCLE, SUCCESS_COLOR),
            "warning": ("#3a2a0d", ft.Icons.WARNING_AMBER, WARNING_COLOR),
            "error": ("#3a1515", ft.Icons.ERROR, ERROR_COLOR),
            "info": ("#102d3f", ft.Icons.INFO, ft.Colors.CYAN_200),
        }
        bg, icon, icon_color = palette.get(type_, palette["info"])
        snack = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color=icon_color),
                    ft.Text(message, color=ft.Colors.WHITE, size=13),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=bg,
            behavior=ft.SnackBarBehavior.FLOATING,
            show_close_icon=True,
            close_icon_color=ft.Colors.WHITE,
            duration=4200,
        )
        if hasattr(page, "show_dialog"):
            page.show_dialog(snack)
        else:
            page.snack_bar = snack
            snack.open = True
            page.update()

    def section_header(title, subtitle=None, icon=None):
        leading = []
        if icon:
            leading.append(ft.Icon(icon, size=18, color=ft.Colors.CYAN_200))
        return ft.Row(
            leading + [
                ft.Column(
                    [
                        ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ft.Text(subtitle, size=12, color=MUTED_TEXT) if subtitle else ft.Container(height=0),
                    ],
                    spacing=2,
                    tight=True,
                )
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def control_cluster(title, controls, icon=None, col=None, height=None):
        heading = [ft.Text(title.upper(), size=10, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)]
        if icon:
            heading.insert(0, ft.Icon(icon, size=14, color=MUTED_TEXT))
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(heading, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row(
                        controls,
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=PANEL_ALT_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=12,
            height=height,
            col=col or {"xs": 12, "md": 6, "xl": 3},
        )

    # Initialize the TrioConnection
    trio_conn = TrioConnection(status_callback=lambda msg, type_: print(f"[{type_}] {msg}"))

    # status_callback may be invoked from the pinned UAPI worker thread (e.g. during
    # connect()), so UI mutations must be marshalled back to the Flet event loop.
    ui_loop_holder = {"loop": None}

    def status_callback(msg, type_):
        def update_status():
            status_text.value = msg
            status_text.color = ERROR_COLOR if type_ == "error" else (WARNING_COLOR if type_ == "warning" else ft.Colors.WHITE)
            page.update()

        loop = ui_loop_holder.get("loop")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(update_status)
        else:
            print(f"[{type_}] {msg}")

    trio_conn.status_callback = status_callback

    def handle_connection_lost():
        def update_ui():
            nonlocal monitor_running
            monitor_running = False
            status_text.value = "Connection lost. Reconnect when controller is available."
            status_text.color = ERROR_COLOR
            connect_btn.disabled = False
            ip_input.disabled = False
            try:
                _set_motion_controls_enabled(False)
            except NameError:
                pass
            try:
                _set_wdog_button_state(None)
            except NameError:
                pass
            show_snack("Connection lost. Motion controls disabled.", "error")
            page.update()

        loop = ui_loop_holder.get("loop")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(update_ui)
        else:
            print("[error] Connection lost")

    trio_conn.set_connection_lost_callback(handle_connection_lost)

    # --- Live Axis Monitor (Flying Shear / 2 Axes) ---
    monitor_running = False

    read_params = [
        ("MPOS", "Measured Position"),
        ("MSPEED", "Measured Speed"),
        ("DRIVE_FE", "Following Error"),
    ]

    LABEL_STYLE = {"size": 12, "color": ft.Colors.GREY_400, "width": 130}
    VALUE_STYLE_M = {"size": 14, "color": ft.Colors.CYAN_200, "weight": ft.FontWeight.BOLD, "width": 120}
    VALUE_STYLE_S = {"size": 14, "color": ft.Colors.ORANGE_200, "weight": ft.FontWeight.BOLD, "width": 120}

    # Axis Selectors. Duplicate controls in other tabs are registered in these
    # lists so Flet never has to mount the same control in two parents.
    axis_m_bound_controls = []
    axis_s_bound_controls = []
    master_speed_inputs = []
    master_speed_sliders = []
    cutter_output_inputs = []
    rotary_motion_buttons = []

    def _sync_bound_value(controls, value, source=None):
        for ctl in controls:
            if ctl is source:
                continue
            if getattr(ctl, "value", None) == value:
                continue
            ctl.value = value
            _update_if_mounted(ctl)

    def on_axis_m_change(e):
        settings["master_axis"] = e.control.value
        _sync_bound_value(axis_m_bound_controls, e.control.value, e.control)
        save_settings(settings)
        try:
            recalc()
        except NameError:
            pass

    def on_axis_s_change(e):
        settings["slave_axis"] = e.control.value
        _sync_bound_value(axis_s_bound_controls, e.control.value, e.control)
        save_settings(settings)
        try:
            request_rotary_units_refresh()
        except NameError:
            pass
        try:
            recalc()
        except NameError:
            pass

    axis_m_dropdown = ft.Dropdown(
        label="Material / encoder axis", width=165, height=45,
        options=[ft.dropdown.Option(str(i), f"Axis {i}") for i in range(16)],
        value=settings.get("master_axis", "0"),
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        text_size=12, on_select=on_axis_m_change
    )
    axis_m_bound_controls.append(axis_m_dropdown)

    axis_s_dropdown = ft.Dropdown(
        label="Shear carriage axis", width=155, height=45,
        options=[ft.dropdown.Option(str(i), f"Axis {i}") for i in range(16)],
        value=settings.get("slave_axis", "1"),
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        text_size=12, on_select=on_axis_s_change
    )
    axis_s_bound_controls.append(axis_s_dropdown)

    def get_conveyor_speed_max(default=10.0):
        try:
            return max(0.0, float(settings.get("shear_calc", {}).get("vline", default)))
        except (TypeError, ValueError):
            return default

    def format_conveyor_speed(value):
        if value >= 100:
            return f"{value:.0f}"
        if value >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"

    def clamp_conveyor_speed(value, max_speed=None):
        limit = get_conveyor_speed_max() if max_speed is None else max(0.0, max_speed)
        return max(0.0, min(value, limit))

    def get_saved_conveyor_speed():
        try:
            return float(settings.get("master_speed", "10.0") or 0)
        except (TypeError, ValueError):
            return 10.0

    def _sync_master_speed_controls(text_value=None, numeric_value=None, source=None):
        if text_value is not None:
            for inp in master_speed_inputs:
                if inp is source:
                    continue
                if inp.value != text_value:
                    inp.value = text_value
                    _update_if_mounted(inp)
        if numeric_value is not None:
            for slider in master_speed_sliders:
                if slider is source:
                    continue
                slider.value = clamp_conveyor_speed(float(numeric_value), slider.max)
                _update_if_mounted(slider)

    def on_master_speed_change(e):
        settings["master_speed"] = e.control.value
        save_settings(settings)
        _sync_master_speed_controls(text_value=e.control.value, source=e.control)
        try:
            _sync_master_speed_controls(
                numeric_value=float(e.control.value or "0"),
                source=e.control,
            )
        except (NameError, TypeError, ValueError):
            pass

    def on_master_speed_slider_change(e):
        speed = float(e.control.value or 0)
        speed_text = format_conveyor_speed(speed)
        master_speed_input.value = speed_text
        settings["master_speed"] = speed_text
        save_settings(settings)
        _sync_master_speed_controls(text_value=speed_text, numeric_value=speed, source=e.control)

    def refresh_conveyor_speed_limit(max_speed):
        max_speed = max(0.0, max_speed)
        current = clamp_conveyor_speed(get_saved_conveyor_speed(), max_speed)
        for slider in master_speed_sliders:
            old_max = slider.max or 0
            if max_speed >= old_max:
                slider.max = max_speed
                slider.value = current
            else:
                slider.value = current
                slider.max = max_speed
        for inp in master_speed_inputs:
            inp.value = format_conveyor_speed(current)
        settings["master_speed"] = format_conveyor_speed(current)

    def on_cutter_output_change(e):
        settings["cutter_output"] = e.control.value
        _sync_bound_value(cutter_output_inputs, e.control.value, e.control)
        save_settings(settings)
        try:
            recalc()
        except NameError:
            pass

    def _send_master_speed():
        try:
            axis_m_val = int(axis_m_dropdown.value or "0")
        except ValueError:
            return

        try:
            speed_val = float(master_speed_input.value or "10.0")
        except ValueError:
            status_text.value = "Invalid conveyor speed"
            status_text.color = ERROR_COLOR
            show_snack("Conveyor speed must be a number.", "error")
            page.update()
            return
        speed_val = clamp_conveyor_speed(speed_val, master_speed_slider.max)
        speed_text = format_conveyor_speed(speed_val)
        master_speed_input.value = speed_text
        master_speed_slider.value = speed_val
        settings["master_speed"] = speed_text
        save_settings(settings)
        _sync_master_speed_controls(text_value=speed_text, numeric_value=speed_val)
        _update_if_mounted(master_speed_input)
        _update_if_mounted(master_speed_slider)

        def _do():
            conn = trio_conn.connection
            if not conn or not trio_conn.is_connected():
                return
            try:
                set_speed = getattr(conn, "SetAxisParameter_SPEED", None)
                if set_speed:
                    set_speed(axis_m_val, speed_val)
            except Exception as ex:
                print(f"Master speed update error on axis {axis_m_val}: {ex}")

        uapi_executor.submit(_do)

    master_speed_input = ft.TextField(
        label="Conveyor speed",
        value=format_conveyor_speed(clamp_conveyor_speed(get_saved_conveyor_speed())),
        width=140, height=45,
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        suffix="u/s",
        text_size=12, on_change=on_master_speed_change,
        on_blur=lambda e: normalize_conveyor_speed_input(),
        on_submit=lambda e: _send_master_speed(),
        tooltip="Conveyor axis SPEED set before Forward/Reverse",
    )
    master_speed_inputs.append(master_speed_input)
    master_speed_slider = ft.Slider(
        min=0,
        max=get_conveyor_speed_max(),
        value=clamp_conveyor_speed(float(master_speed_input.value or 0)),
        width=230,
        label="{value} u/s",
        round=1,
        active_color=ft.Colors.CYAN_300,
        inactive_color=ft.Colors.GREY_700,
        thumb_color=ft.Colors.CYAN_200,
        on_change=on_master_speed_slider_change,
        on_change_end=lambda e: _send_master_speed(),
        tooltip="Limited by the calculator MAX line speed",
    )
    master_speed_sliders.append(master_speed_slider)

    def normalize_conveyor_speed_input(source=None):
        try:
            speed = float((source or master_speed_input).value or "0")
        except (TypeError, ValueError):
            return
        speed = clamp_conveyor_speed(speed, master_speed_slider.max)
        speed_text = format_conveyor_speed(speed)
        master_speed_input.value = speed_text
        if source is not None:
            source.value = speed_text
        master_speed_slider.value = speed
        settings["master_speed"] = speed_text
        save_settings(settings)
        _sync_master_speed_controls(text_value=speed_text, numeric_value=speed, source=source)
        _update_if_mounted(master_speed_input)
        _update_if_mounted(master_speed_slider)

    cutter_output_input = ft.TextField(
        label="Knife OP", value=str(settings.get("cutter_output", "8")),
        width=140, height=45,
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13, on_change=on_cutter_output_change,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        tooltip="Controller digital output number used for knife OP() and live output-state read",
    )
    cutter_output_inputs.append(cutter_output_input)

    cutter_lamp_op_text = ft.Text(
        "OP --",
        size=11,
        color=MUTED_TEXT,
        weight=ft.FontWeight.BOLD,
    )
    cutter_lamp_caption_text = ft.Text(
        "LIVE OUTPUT",
        size=10,
        color=MUTED_TEXT,
        weight=ft.FontWeight.BOLD,
    )
    cutter_lamp_bulb = ft.Container(
        width=36,
        height=36,
        border_radius=18,
        gradient=ft.RadialGradient(
            center=ft.Alignment(-0.38, -0.42),
            radius=0.9,
            colors=["#174729", "#0b2f1a", "#05160c"],
            stops=[0.0, 0.58, 1.0],
        ),
        border=ft.Border.all(1, "#123f24"),
        shadow=[
            ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#33092616",
                offset=ft.Offset(0, 0),
            )
        ],
    )
    cutter_lamp = ft.Container(
        width=54,
        height=54,
        padding=5,
        bgcolor="#0b1110",
        border_radius=27,
        border=ft.Border.all(1, "#2c3a34"),
        content=cutter_lamp_bulb,
        alignment=ft.Alignment(0, 0),
        tooltip="Knife output state unavailable",
    )
    cutter_output_lamp_panel = ft.Container(
        content=ft.Row(
            [
                cutter_lamp,
                ft.Column(
                    [
                        cutter_lamp_op_text,
                        cutter_lamp_caption_text,
                    ],
                    spacing=1,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(8, 6, 10, 6),
        border_radius=8,
        bgcolor="#121a16",
        border=ft.Border.all(1, "#263b2f"),
    )
    cutter_lamp_state = {"output": None, "state": None}
    extra_cutter_lamp_widgets = []

    def _set_cutter_output_lamp(output, state):
        if cutter_lamp_state["output"] == output and cutter_lamp_state["state"] == state:
            return False

        cutter_lamp_state["output"] = output
        cutter_lamp_state["state"] = state
        cutter_lamp_op_text.value = f"OP {output}"

        if state == "ON":
            label = "ON"
            caption = "LIVE OUTPUT"
            caption_color = ft.Colors.GREEN_200
            bulb_colors = ["#e8fff0", "#35e873", "#05843b"]
            bulb_border = "#77f29b"
            glow = "#9935e873"
            housing_border = "#2f8d52"
        elif state == "OFF":
            label = "OFF"
            caption = "LIVE OUTPUT"
            caption_color = "#79a98a"
            bulb_colors = ["#1b5b31", "#0b331d", "#031108"]
            bulb_border = "#174d2b"
            glow = "#330b331d"
            housing_border = "#263b2f"
        elif state == "ERR":
            label = "ERR"
            caption = "READ ERROR"
            caption_color = ERROR_COLOR
            bulb_colors = ["#ffd6d6", "#e04747", "#671515"]
            bulb_border = "#ff7d7d"
            glow = "#88e04747"
            housing_border = "#8a3434"
        else:
            label = "---"
            caption = "NO DATA"
            caption_color = ft.Colors.GREY_300
            bulb_colors = ["#515a55", "#26302b", "#111615"]
            bulb_border = "#48534e"
            glow = "#30323a36"
            housing_border = "#2c3a34"

        cutter_lamp_caption_text.value = caption
        cutter_lamp_caption_text.color = caption_color
        cutter_lamp_bulb.gradient = ft.RadialGradient(
            center=ft.Alignment(-0.38, -0.42),
            radius=0.9,
            colors=bulb_colors,
            stops=[0.0, 0.58, 1.0],
        )
        cutter_lamp_bulb.border = ft.Border.all(1, bulb_border)
        cutter_lamp_bulb.shadow = [
            ft.BoxShadow(
                spread_radius=1 if state == "ON" else 0,
                blur_radius=20 if state == "ON" else 8,
                color=glow,
                offset=ft.Offset(0, 0),
            )
        ]
        cutter_lamp.border = ft.Border.all(1, housing_border)
        cutter_lamp.tooltip = f"Knife output OP {output}: {label}"
        for widgets in extra_cutter_lamp_widgets:
            widgets["op_text"].value = f"OP {output}"
            widgets["caption_text"].value = caption
            widgets["caption_text"].color = caption_color
            widgets["bulb"].gradient = ft.RadialGradient(
                center=ft.Alignment(-0.38, -0.42),
                radius=0.9,
                colors=bulb_colors,
                stops=[0.0, 0.58, 1.0],
            )
            widgets["bulb"].border = ft.Border.all(1, bulb_border)
            widgets["bulb"].shadow = [
                ft.BoxShadow(
                    spread_radius=1 if state == "ON" else 0,
                    blur_radius=20 if state == "ON" else 8,
                    color=glow,
                    offset=ft.Offset(0, 0),
                )
            ]
            widgets["lamp"].border = ft.Border.all(1, housing_border)
            widgets["lamp"].tooltip = f"Knife output OP {output}: {label}"
        return True

    wdog_state = {"enabled": None, "busy": False}

    def _set_wdog_button_state(enabled=None, busy=False, error=False):
        wdog_state["enabled"] = enabled
        wdog_state["busy"] = busy
        wdog_btn.disabled = busy or not trio_conn.is_connected()

        if busy:
            wdog_btn.text = "WDOG ..."
            bg_color = ft.Colors.AMBER_700
        elif error:
            wdog_btn.text = "WDOG ERR"
            bg_color = ft.Colors.RED_700
        elif enabled is True:
            wdog_btn.text = "WDOG ON"
            bg_color = ft.Colors.GREEN_700
        elif enabled is False:
            wdog_btn.text = "WDOG OFF"
            bg_color = ft.Colors.BLUE_GREY_700
        else:
            wdog_btn.text = "WDOG --"
            bg_color = ft.Colors.GREY_700

        wdog_btn.style = ft.ButtonStyle(bgcolor=bg_color, color=ft.Colors.WHITE)

    async def refresh_wdog_state():
        if not trio_conn.is_connected():
            _set_wdog_button_state(None)
            page.update()
            return

        loop = asyncio.get_running_loop()

        def _read():
            conn = trio_conn.connection
            if not conn or not trio_conn.is_connected():
                return None
            return bool(conn.GetSystemParameter_WDOG())

        try:
            enabled = await loop.run_in_executor(uapi_executor, _read)
            _set_wdog_button_state(enabled)
        except Exception as ex:
            print(f"WDOG read error: {ex}")
            _set_wdog_button_state(None, error=True)
        page.update()

    async def on_wdog_click(e):
        if wdog_state["busy"] or not trio_conn.is_connected():
            return

        target_enabled = not bool(wdog_state["enabled"])
        _set_wdog_button_state(wdog_state["enabled"], busy=True)
        page.update()

        loop = asyncio.get_running_loop()

        def _write():
            conn = trio_conn.connection
            if not conn or not trio_conn.is_connected():
                return None
            conn.SetSystemParameter_WDOG(target_enabled)
            return bool(conn.GetSystemParameter_WDOG())

        try:
            enabled = await loop.run_in_executor(uapi_executor, _write)
            _set_wdog_button_state(enabled)
        except Exception as ex:
            print(f"WDOG write error: {ex}")
            _set_wdog_button_state(None, error=True)
            status_text.value = f"WDOG control failed: {ex}"
            status_text.color = ERROR_COLOR
            show_snack(f"WDOG control failed: {ex}", "error")
        page.update()

    wdog_btn = ft.FilledButton(
        "WDOG --",
        icon=ft.Icons.POWER_SETTINGS_NEW,
        on_click=on_wdog_click,
        disabled=True,
        height=38,
        tooltip="Toggle controller WDOG master enable",
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_700, color=ft.Colors.WHITE),
    )

    # --- Master axis Forward / Reverse / Cancel buttons ---
    # Mirrors the gcode parser's jog commands (machine_controller.start_jog / stop_jog):
    #   Forward(axis), Reverse(axis), Cancel(2, axis)
    # Cancel mode 2 stops both buffered and current move. All UAPI calls dispatched
    # via uapi_executor to preserve COM thread-affinity.
    def _send_master_cmd(cmd):
        if not trio_conn.is_connected():
            show_snack("Connect to the controller before moving the conveyor axis.", "warning")
            return

        try:
            axis_m_val = int(axis_m_dropdown.value or "0")
        except ValueError:
            return

        try:
            speed_val = float(master_speed_input.value or "10.0")
        except ValueError:
            speed_val = 10.0
        speed_val = clamp_conveyor_speed(speed_val, master_speed_slider.max)
        speed_text = format_conveyor_speed(speed_val)
        master_speed_input.value = speed_text
        master_speed_slider.value = speed_val
        settings["master_speed"] = speed_text
        save_settings(settings)
        _sync_master_speed_controls(text_value=speed_text, numeric_value=speed_val)
        _update_if_mounted(master_speed_input)
        _update_if_mounted(master_speed_slider)

        def _do():
            conn = trio_conn.connection
            if not conn:
                return
            try:
                if cmd in ("forward", "reverse"):
                    set_speed = getattr(conn, "SetAxisParameter_SPEED", None)
                    if set_speed:
                        set_speed(axis_m_val, speed_val)
                if cmd == "forward":
                    conn.Forward(axis_m_val)
                elif cmd == "reverse":
                    conn.Reverse(axis_m_val)
                elif cmd == "cancel":
                    conn.Cancel(2, axis_m_val)
            except Exception as ex:
                print(f"Master {cmd} error on axis {axis_m_val}: {ex}")

        uapi_executor.submit(_do)

    def _set_motion_controls_enabled(enabled):
        for btn in (master_fwd_btn, master_rev_btn, master_stop_btn, *rotary_motion_buttons):
            btn.disabled = not enabled

    master_fwd_btn = ft.FilledButton(
        "Forward", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: _send_master_cmd("forward"),
        disabled=True,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
        height=38, tooltip="Forward(master) - continuous move forward",
    )
    master_rev_btn = ft.FilledButton(
        "Reverse", icon=ft.Icons.ARROW_BACK, on_click=lambda e: _send_master_cmd("reverse"),
        disabled=True,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_700, color=ft.Colors.WHITE),
        height=38, tooltip="Reverse(master) - continuous move reverse",
    )
    master_stop_btn = ft.FilledButton(
        "Stop", icon=ft.Icons.STOP, on_click=lambda e: _send_master_cmd("cancel"),
        disabled=True,
        style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
        height=38, tooltip="Cancel(2, master) - stop buffered + current move",
    )

    # Build monitor rows
    monitor_values_m = {}  # param_name -> ft.Text
    monitor_values_s = {}  # param_name -> ft.Text
    monitor_rows = []
    
    # Header
    monitor_rows.append(
        ft.Row([
            ft.Text("Parameter", **LABEL_STYLE),
            ft.Text("Master Axis", width=120, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.Text("Slave Axis", width=120, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        ], spacing=5)
    )

    for param_name, param_label in read_params:
        val_text_m = ft.Text("---", **VALUE_STYLE_M)
        val_text_s = ft.Text("---", **VALUE_STYLE_S)
        monitor_values_m[param_name] = val_text_m
        monitor_values_s[param_name] = val_text_s
        monitor_rows.append(
            ft.Row([
                ft.Text(f"{param_label}:", **LABEL_STYLE),
                val_text_m,
                val_text_s
            ], spacing=5)
        )

    # --- Infinite Conveyor Belt visualizer (Master) ---
    TRACK_WIDTH = 2400
    TRACK_HEIGHT = 24
    BELT_HEIGHT = 24
    CLEAT_HEIGHT = 18
    BELT_SPACING = 70
    CLEAT_WIDTH = 10
    NUM_BELT_ITEMS = (TRACK_WIDTH // BELT_SPACING) + 1
    WRAP_WIDTH = NUM_BELT_ITEMS * BELT_SPACING
    CONVEYOR_VISUAL_DIRECTION = 1
    RAIL_HEIGHT = 4
    PULLEY_SIZE = 36
    CONVEYOR_HEIGHT = PULLEY_SIZE + 2 * (RAIL_HEIGHT + 1)
    BELT_TOP_IN_CONVEYOR = (CONVEYOR_HEIGHT - BELT_HEIGHT) / 2

    # --- Shear/cutter graphic (Slave axis) ---
    SHEAR_WIDTH = 46
    SHEAR_HEIGHT = 68
    MOUNT_HEIGHT = 14
    BLADE_TIP_H = 22
    SHEAR_TRACK_HEIGHT = 118
    SHEAR_TO_CONVEYOR_GAP = 8
    SHEAR_CUT_OVERTRAVEL = 6
    SHEAR_TOP_IDLE = 6
    BLADE_IDLE_EXTENSION = 30
    BLADE_CUT_EXTENSION = 78
    CENTER_LEFT_S = TRACK_WIDTH / 2 - SHEAR_WIDTH / 2
    SHEAR_ZERO_FROM_BELT_LEFT_PX = 38  # ~1 cm from the rubber belt's left edge.
    SHEAR_VISUAL_DIRECTION = 1  # Positive slave MPOS moves right from the left-side zero.

    # Mutable holders so closures can mutate without `nonlocal` boilerplate.
    position_zero_m = [None]
    scale_px_per_unit = [float(settings.get("scale_px_per_unit", 100.0))]

    def create_conveyor_track(accent_color):
        """Industrial conveyor: dark rubber belt with raised cleats, drive pulleys at each end, and side frame rails."""
        # Raised cleats (treads) — gradient gives them a 3D extruded look
        belt_items = []
        for i in range(NUM_BELT_ITEMS):
            cleat = ft.Container(
                width=CLEAT_WIDTH, height=CLEAT_HEIGHT,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                    colors=[ft.Colors.GREY_400, ft.Colors.GREY_700, "#050505"],
                    stops=[0.0, 0.45, 1.0],
                ),
                border_radius=2,
                top=(BELT_HEIGHT - CLEAT_HEIGHT) / 2,
                left=(i * BELT_SPACING) - CLEAT_WIDTH,
            )
            belt_items.append(cleat)

        # Belt rubber surface — dark with subtle top/bottom highlight for cylindrical curvature
        belt_surface = ft.Container(
            width=TRACK_WIDTH, height=BELT_HEIGHT,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                colors=["#262626", "#0a0a0a", "#262626"],
                stops=[0.0, 0.5, 1.0],
            ),
        )

        belt_stack = ft.Stack(
            [belt_surface] + belt_items,
            width=TRACK_WIDTH, height=BELT_HEIGHT,
        )

        belt_clipped = ft.Container(
            content=belt_stack,
            width=TRACK_WIDTH, height=BELT_HEIGHT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border_radius=BELT_HEIGHT / 2,
        )

        # Drive pulley (metallic roller) — outer disk with a darker hub
        def make_pulley():
            return ft.Stack(
                [
                    ft.Container(
                        width=PULLEY_SIZE, height=PULLEY_SIZE,
                        gradient=ft.RadialGradient(
                            center=ft.Alignment(-0.4, -0.4), radius=0.95,
                            colors=[ft.Colors.GREY_300, ft.Colors.GREY_700, "#050505"],
                            stops=[0.0, 0.55, 1.0],
                        ),
                        border_radius=PULLEY_SIZE / 2,
                        border=ft.Border.all(1, "#000000"),
                    ),
                    ft.Container(
                        width=PULLEY_SIZE * 0.32, height=PULLEY_SIZE * 0.32,
                        bgcolor="#1a1a1a",
                        border_radius=PULLEY_SIZE * 0.16,
                        left=PULLEY_SIZE * 0.34, top=PULLEY_SIZE * 0.34,
                        border=ft.Border.all(1, "#000000"),
                    ),
                ],
                width=PULLEY_SIZE, height=PULLEY_SIZE,
            )

        # Frame rails (industrial chassis above and below the belt)
        def make_rail():
            return ft.Container(
                width=TRACK_WIDTH, height=RAIL_HEIGHT,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                    colors=[ft.Colors.GREY_500, ft.Colors.GREY_900],
                ),
                border_radius=1,
            )

        pulley_y = (CONVEYOR_HEIGHT - PULLEY_SIZE) / 2
        belt_y = (CONVEYOR_HEIGHT - BELT_HEIGHT) / 2

        track = ft.Stack(
            [
                ft.Container(content=make_rail(), top=pulley_y - RAIL_HEIGHT - 1, left=0),
                ft.Container(content=belt_clipped, top=belt_y, left=0),
                ft.Container(content=make_pulley(), top=pulley_y, left=0),
                ft.Container(content=make_pulley(), top=pulley_y, left=TRACK_WIDTH - PULLEY_SIZE),
                ft.Container(content=make_rail(), top=pulley_y + PULLEY_SIZE + 1, left=0),
            ],
            width=TRACK_WIDTH, height=CONVEYOR_HEIGHT,
        )
        return belt_items, track

    def create_shear_track(color):
        """Shear blade for slave axis. Moves horizontally to track belt speed;
        top position (indicator.top) will be animated vertically to show cuts."""
        blade_body_w = 18
        blade_anchor_top = MOUNT_HEIGHT + 8
        blade_left = (SHEAR_WIDTH - blade_body_w) / 2
        guide_h = SHEAR_HEIGHT - 8

        mount = ft.Container(
            width=SHEAR_WIDTH, height=MOUNT_HEIGHT,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                colors=["#4d4d4d", "#1c1c1c"],
            ),
            border=ft.Border.all(1, "#707070"),
            border_radius=3,
            top=0, left=0,
        )

        blade_body = ft.Container(
            width=blade_body_w,
            height=BLADE_IDLE_EXTENSION,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                colors=["#8f8f8f", "#f2f2f2", "#ffffff", "#c8c8c8", "#6f6f6f"],
                stops=[0.0, 0.28, 0.5, 0.75, 1.0],
            ),
            border=ft.Border.all(1, "#3c3c3c"),
            border_radius=ft.BorderRadius.only(top_left=2, top_right=2),
            top=blade_anchor_top,
            left=blade_left,
        )
        blade_edge = ft.Container(
            width=2,
            height=BLADE_IDLE_EXTENSION - 6,
            bgcolor="#ffffff",
            border_radius=1,
            top=blade_anchor_top + 3,
            left=blade_left + blade_body_w * 0.36,
        )
        blade_tip = ft.Text(
            "▼",
            size=32,
            color="#f4f4f4",
            weight=ft.FontWeight.BOLD,
            width=SHEAR_WIDTH,
            text_align=ft.TextAlign.CENTER,
            top=blade_anchor_top + BLADE_IDLE_EXTENSION - 9,
            left=0,
        )
        left_guide = ft.Container(
            width=4, height=guide_h,
            bgcolor="#2e2e2e",
            border_radius=1,
            top=4, left=4,
            border=ft.Border.all(1, "#5c5c5c"),
        )
        right_guide = ft.Container(
            width=4, height=guide_h,
            bgcolor="#2e2e2e",
            border_radius=1,
            top=4, left=SHEAR_WIDTH - 8,
            border=ft.Border.all(1, "#5c5c5c"),
        )
        crosshead = ft.Container(
            width=SHEAR_WIDTH - 10,
            height=6,
            bgcolor="#3b3b3b",
            border=ft.Border.all(1, "#666666"),
            border_radius=2,
            top=MOUNT_HEIGHT + 6,
            left=5,
        )
        indicator = ft.Container(
            content=ft.Stack(
                [left_guide, right_guide, blade_body, blade_edge, blade_tip, crosshead, mount],
                width=SHEAR_WIDTH, height=SHEAR_HEIGHT,
                clip_behavior=ft.ClipBehavior.NONE,
            ),
            width=SHEAR_WIDTH, height=SHEAR_HEIGHT,
            left=CENTER_LEFT_S,
            top=SHEAR_TOP_IDLE,
        )

        track = ft.Stack(
            [
                ft.Container(width=TRACK_WIDTH, height=SHEAR_TRACK_HEIGHT,
                             bgcolor=DARKER_BG,
                             border=ft.Border.all(1, BORDER_COLOR), border_radius=4),
                ft.Container(width=TRACK_WIDTH, height=2,
                             bgcolor=ft.Colors.with_opacity(0.35, color),
                             top=SHEAR_TRACK_HEIGHT - 10),
                ft.Container(width=TRACK_WIDTH, height=2,
                             bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.WHITE),
                             top=SHEAR_TRACK_HEIGHT - 4),
                indicator,
            ],
            width=TRACK_WIDTH, height=SHEAR_TRACK_HEIGHT,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        return indicator, track, blade_body, blade_edge, blade_tip, blade_anchor_top

    def _available_visual_width():
        return max(720, (page.width or default_window_width) - 112)

    visual_width = _available_visual_width()
    visual_inner_width = visual_width - 20
    visual_inner_width_current = [visual_inner_width]
    visual_slave_mpos = [0.0]
    belt_width = visual_inner_width - (2 * PULLEY_SIZE)
    shear_conveyor_height = SHEAR_TRACK_HEIGHT + SHEAR_TO_CONVEYOR_GAP + CONVEYOR_HEIGHT

    def _clamp_shear_left(left, inner_width):
        return max(0, min(inner_width - SHEAR_WIDTH, left))

    def _shear_zero_left(inner_width):
        belt_left_edge = PULLEY_SIZE
        blade_center = belt_left_edge + SHEAR_ZERO_FROM_BELT_LEFT_PX
        return _clamp_shear_left(blade_center - (SHEAR_WIDTH / 2), inner_width)

    def _slave_mpos_to_shear_left(mpos, inner_width):
        return _clamp_shear_left(
            _shear_zero_left(inner_width) + SHEAR_VISUAL_DIRECTION * mpos * scale_px_per_unit[0],
            inner_width,
        )

    blade_body_w = 14
    rail_w = 5
    rail_gap = 3
    blade_body_s = ft.Container(
        width=blade_body_w,
        height=BLADE_IDLE_EXTENSION,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
            colors=["#7a7a7a", "#e8e8e8", "#ffffff", "#e8e8e8", "#7a7a7a"],
            stops=[0.0, 0.3, 0.5, 0.7, 1.0],
        ),
        border=ft.Border.all(1, "#5a5a5a"),
    )
    blade_tip_s = ft.Text(
        "▼",
        size=18,
        color="#f4f4f4",
        weight=ft.FontWeight.BOLD,
        text_align=ft.TextAlign.CENTER,
        width=SHEAR_WIDTH,
        margin=ft.Margin.only(top=-6),
    )
    SCREW_TOP = 15
    screw_shaft = ft.Container(
        width=visual_inner_width,
        height=9,
        border_radius=5,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=["#8b949c", "#454d55", "#14191f"],
            stops=[0.0, 0.48, 1.0],
        ),
        border=ft.Border.all(1, "#0f1215"),
        top=6,
        left=0,
    )
    screw_highlight = ft.Container(
        width=visual_inner_width,
        height=2,
        bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.WHITE),
        border_radius=1,
        top=7,
        left=0,
    )
    screw_support = ft.Stack(
        [screw_shaft, screw_highlight],
        width=visual_inner_width,
        height=24,
    )
    shear_position_spacer = ft.Container(width=_shear_zero_left(visual_inner_width))
    shear_lane_tail_spacer = ft.Container(width=visual_inner_width)
    belt_offset_spacer = ft.Container(width=0)
    belt_cleats = [
        ft.Container(width=CLEAT_WIDTH, height=CLEAT_HEIGHT, bgcolor="#8c8c8c", border_radius=2)
        for _ in range(NUM_BELT_ITEMS + 2)
    ]
    belt_cleats_row = ft.Row(
        belt_cleats,
        spacing=BELT_SPACING - CLEAT_WIDTH,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
    )

    shear_carriage = ft.Container(
        width=SHEAR_WIDTH,
        content=ft.Column(
            [
                # Top carriage frame (yoke holding the actuator)
                ft.Container(
                    width=SHEAR_WIDTH, height=MOUNT_HEIGHT,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                        colors=["#6a6a6a", "#3a3a3a"],
                    ),
                    border=ft.Border.all(1, "#8a8a8a"),
                    border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                    content=ft.Row(
                        [
                            ft.Container(width=3, height=3, bgcolor="#1a1a1a", border_radius=2),
                            ft.Container(expand=True),
                            ft.Container(width=3, height=3, bgcolor="#1a1a1a", border_radius=2),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=4),
                ),
                # Actuator / piston connector
                ft.Container(
                    width=SHEAR_WIDTH - 14, height=4,
                    bgcolor="#222222",
                    border=ft.Border.all(1, "#4a4a4a"),
                ),
                # Blade body flanked by guide rails
                ft.Row(
                    [
                        ft.Container(width=rail_w, height=BLADE_IDLE_EXTENSION,
                                     bgcolor="#2a2a2a",
                                     border=ft.Border.all(1, "#5a5a5a"),
                                     border_radius=1),
                        ft.Container(width=rail_gap),
                        blade_body_s,
                        ft.Container(width=rail_gap),
                        ft.Container(width=rail_w, height=BLADE_IDLE_EXTENSION,
                                     bgcolor="#2a2a2a",
                                     border=ft.Border.all(1, "#5a5a5a"),
                                     border_radius=1),
                    ],
                    spacing=0,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    tight=True,
                ),
                # Sharp cutting tip - centered under the blade body
                blade_tip_s,
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
    )

    shear_carriage_row = ft.Row(
        [shear_position_spacer, shear_carriage, shear_lane_tail_spacer],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    shear_lane_stack = ft.Stack(
        [
            ft.Container(content=screw_support, top=SCREW_TOP, left=0),
            ft.Container(content=shear_carriage_row, top=SHEAR_TOP_IDLE, left=0),
        ],
        width=visual_inner_width,
        height=SHEAR_TRACK_HEIGHT,
    )

    shear_lane = ft.Container(
        width=visual_inner_width,
        height=SHEAR_TRACK_HEIGHT,
        bgcolor="#15181c",
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=shear_lane_stack,
    )

    belt_surface = ft.Container(
        width=belt_width,
        height=BELT_HEIGHT,
        bgcolor="#080808",
        border_radius=BELT_HEIGHT / 2,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Row(
            [belt_offset_spacer, belt_cleats_row],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
    )
    pulley = lambda: ft.Container(
        width=PULLEY_SIZE,
        height=PULLEY_SIZE,
        bgcolor="#6f7478",
        border_radius=PULLEY_SIZE / 2,
        border=ft.Border.all(1, "#111111"),
        content=ft.Container(width=PULLEY_SIZE * 0.32, height=PULLEY_SIZE * 0.32,
                             bgcolor="#151515", border_radius=PULLEY_SIZE * 0.16),
        alignment=ft.Alignment.CENTER,
    )
    conveyor_top_rail = ft.Container(width=visual_inner_width, height=RAIL_HEIGHT, bgcolor="#4a4f55")
    conveyor_bottom_rail = ft.Container(width=visual_inner_width, height=RAIL_HEIGHT, bgcolor="#4a4f55")

    conveyor_lane = ft.Container(
        width=visual_inner_width,
        height=CONVEYOR_HEIGHT,
        content=ft.Column(
            [
                conveyor_top_rail,
                ft.Row([pulley(), belt_surface, pulley()], spacing=0,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                conveyor_bottom_rail,
            ],
            spacing=1,
        ),
    )

    shear_conveyor_view = ft.Container(
        width=visual_width,
        height=shear_conveyor_height,
        bgcolor=DARKER_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10),
        content=ft.Column([shear_lane, ft.Container(height=SHEAR_TO_CONVEYOR_GAP), conveyor_lane], spacing=0),
    )

    def resize_shear_visual(update=False):
        new_visual_width = _available_visual_width()
        new_inner_width = new_visual_width - 20
        new_belt_width = new_inner_width - (2 * PULLEY_SIZE)

        visual_inner_width_current[0] = new_inner_width
        shear_conveyor_view.width = new_visual_width
        shear_lane.width = new_inner_width
        shear_lane_stack.width = new_inner_width
        screw_support.width = new_inner_width
        screw_shaft.width = new_inner_width
        screw_highlight.width = new_inner_width
        shear_lane_tail_spacer.width = new_inner_width
        conveyor_lane.width = new_inner_width
        conveyor_top_rail.width = new_inner_width
        conveyor_bottom_rail.width = new_inner_width
        belt_surface.width = new_belt_width

        shear_position_spacer.width = _slave_mpos_to_shear_left(
            visual_slave_mpos[0],
            new_inner_width,
        )

        if update:
            _update_if_mounted(shear_conveyor_view)

    def on_recenter(e):
        position_zero_m[0] = None

    SCALE_MIN = 1.0
    SCALE_MAX = 2000.0

    scale_value_label = ft.Text(f"{scale_px_per_unit[0]:g} px/unit", size=12,
                                color=ft.Colors.CYAN_200,
                                weight=ft.FontWeight.BOLD, width=90)

    def _apply_scale(new_val):
        new_val = max(SCALE_MIN, min(SCALE_MAX, float(new_val)))
        scale_px_per_unit[0] = new_val
        scale_value_label.value = f"{new_val:g} px/unit"
        try:
            rotary_scale_value_label.value = scale_value_label.value
            _update_if_mounted(rotary_scale_value_label)
        except NameError:
            pass
        settings["scale_px_per_unit"] = new_val
        save_settings(settings)
        _update_if_mounted(scale_value_label)

    def on_scale_step(delta):
        def handler(e):
            _apply_scale(scale_px_per_unit[0] + delta)
        return handler

    recenter_btn = ft.IconButton(icon=ft.Icons.CENTER_FOCUS_STRONG,
                                 tooltip="Re-center on current position",
                                 on_click=on_recenter)
    scale_minus_btn = ft.IconButton(icon=ft.Icons.REMOVE, icon_size=18,
                                    tooltip="Decrease scale by 1",
                                    on_click=on_scale_step(-1))
    scale_plus_btn = ft.IconButton(icon=ft.Icons.ADD, icon_size=18,
                                   tooltip="Increase scale by 1",
                                   on_click=on_scale_step(1))
    scale_minus10_btn = ft.IconButton(icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT, icon_size=18,
                                      tooltip="Decrease scale by 10",
                                      on_click=on_scale_step(-10))
    scale_plus10_btn = ft.IconButton(icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT, icon_size=18,
                                     tooltip="Increase scale by 10",
                                     on_click=on_scale_step(10))

    # Trio UAPI is thread-affine (COM/STA): all calls — connect AND polling — must
    # happen on the same thread, otherwise we deadlock the .NET marshaller.
    # A 1-worker executor pins everything to one Python thread.
    uapi_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uapi")

    # Comms lag label – rolling average of MPOS read on master axis (last 100 samples)
    comms_lag_label = ft.Text("MPOS read: -- ms (avg 100)", size=10, color=ft.Colors.GREY_500)
    comms_lag_samples = collections.deque(maxlen=100)

    # FPS counter
    TARGET_FPS = 60
    FRAME_BUDGET = 1.0 / TARGET_FPS
    fps_label = ft.Text("0 FPS", size=10, color=ft.Colors.GREY_500)
    fps_timestamps = collections.deque(maxlen=60)  # last N frame timestamps

    async def monitor_async_loop():
        """Runs on Flet's main asyncio loop. UAPI reads dispatched to the pinned executor.
        
        All UAPI reads are batched into a single executor call to minimize
        thread-crossing overhead. MPOS is read every frame; MSPEED and
        DRIVE_FE are refreshed every 3rd frame.
        """
        loop = asyncio.get_running_loop()
        frame_counter = 0
        # Update UI every Nth frame to cap render cost; text values are still
        # refreshed every frame and flushed on the next .update() tick.
        ui_update_every = 2

        def _batch_read(axis_m, axis_s, cutter_output, read_slow_params):
            """Runs on the pinned UAPI thread. Returns (results, mpos_t) or
            (None, None) if there's no connection.

            Method lookup happens here (not on the UI thread) so the COM object
            is only ever touched from the pinned worker, and reconnects don't
            leave behind stale bound methods.
            """
            conn = trio_conn.connection
            if not conn or not trio_conn.is_connected():
                return None, None

            results = {}
            mpos_t = None
            mpos_errors = 0
            try:
                results[("CUTTER_OUTPUT", "state")] = trio_conn.read_digital_output(cutter_output)
            except Exception:
                results[("CUTTER_OUTPUT", "state")] = "ERR"
            if read_slow_params:
                try:
                    results[("WDOG", "state")] = bool(conn.GetSystemParameter_WDOG())
                except Exception:
                    results[("WDOG", "state")] = "ERR"
                method = getattr(conn, "GetAxisParameter_DEMAND_SPEED", None)
                if method is None:
                    results[("DEMAND_SPEED", "s")] = None
                else:
                    try:
                        results[("DEMAND_SPEED", "s")] = method(axis_s)
                    except Exception:
                        results[("DEMAND_SPEED", "s")] = "ERR"
            for pn, _ in read_params:
                if pn != "MPOS" and not read_slow_params:
                    continue
                method = getattr(conn, f"GetAxisParameter_{pn}", None)
                if method is None:
                    results[(pn, "m")] = None
                    results[(pn, "s")] = None
                    continue
                # Master
                try:
                    if pn == "MPOS":
                        t0 = time.perf_counter()
                    val_m = method(axis_m)
                    if pn == "MPOS":
                        mpos_t = (time.perf_counter() - t0) * 1000.0
                    results[(pn, "m")] = val_m
                except Exception:
                    results[(pn, "m")] = "ERR"
                    if pn == "MPOS":
                        mpos_errors += 1
                # Slave
                try:
                    val_s = method(axis_s)
                    results[(pn, "s")] = val_s
                except Exception:
                    results[(pn, "s")] = "ERR"
                    if pn == "MPOS":
                        mpos_errors += 1
            if mpos_errors >= 2:
                trio_conn.mark_connection_lost()
            return results, mpos_t

        while monitor_running:
            # Outside the try so it's always defined for the frame-pacing math
            # at the bottom of the loop, even if the body raises.
            frame_start = time.perf_counter()

            try:
                axis_m_val = int(axis_m_dropdown.value or "0")
                axis_s_val = int(axis_s_dropdown.value or "1")
                cutter_output_val = int(cutter_output_input.value or "8")
                dirty = False
                fps_timestamps.append(frame_start)
                frame_counter += 1
                read_slow = (frame_counter % 3 == 0)

                # Single thread-crossing call for ALL reads
                results, mpos_t = await loop.run_in_executor(
                    uapi_executor, _batch_read, axis_m_val, axis_s_val, cutter_output_val, read_slow
                )

                if results is None:
                    await asyncio.sleep(0.1)
                    continue

                if mpos_t is not None:
                    comms_lag_samples.append(mpos_t)

                cutter_raw = results.get(("CUTTER_OUTPUT", "state"))
                if cutter_raw == "ERR":
                    cutter_state = "ERR"
                elif cutter_raw is True:
                    cutter_state = "ON"
                elif cutter_raw is False:
                    cutter_state = "OFF"
                else:
                    cutter_state = "---"

                if _set_cutter_output_lamp(cutter_output_val, cutter_state):
                    dirty = True

                wdog_raw = results.get(("WDOG", "state"))
                if wdog_raw == "ERR":
                    _set_wdog_button_state(None, error=True)
                    _update_if_mounted(wdog_btn)
                elif isinstance(wdog_raw, bool) and not wdog_state["busy"]:
                    if wdog_state["enabled"] != wdog_raw or wdog_btn.disabled:
                        _set_wdog_button_state(wdog_raw)
                        _update_if_mounted(wdog_btn)

                target_blade_extension = BLADE_CUT_EXTENSION if cutter_raw is True else BLADE_IDLE_EXTENSION
                if abs((blade_body_s.height or 0) - target_blade_extension) > 0.1:
                    blade_body_s.height = target_blade_extension
                    dirty = True

                mpos_val_m = None
                mpos_val_s = None
                mspeed_val_m = None
                mspeed_val_s = None
                demand_speed_val_s = None

                # Apply results to UI texts
                for pn, _ in read_params:
                    for side, vals_dict, mon_vals in [
                        ("m", results, monitor_values_m),
                        ("s", results, monitor_values_s),
                    ]:
                        key = (pn, side)
                        if key not in vals_dict:
                            continue
                        raw = vals_dict[key]
                        if raw is None:
                            new_val = "N/A"
                        elif raw == "ERR":
                            new_val = "ERR"
                        else:
                            new_val = f"{raw:.4f}"
                            if pn == "MPOS":
                                if side == "m":
                                    mpos_val_m = raw
                                else:
                                    mpos_val_s = raw
                            elif pn == "MSPEED":
                                if side == "m":
                                    mspeed_val_m = raw
                                else:
                                    mspeed_val_s = raw
                        txt = mon_vals[pn]
                        if txt.value != new_val:
                            txt.value = new_val
                            dirty = True

                if ("DEMAND_SPEED", "s") in results:
                    demand_speed_raw_s = results.get(("DEMAND_SPEED", "s"))
                    if demand_speed_raw_s in (None, "ERR"):
                        demand_speed_val_s = "ERR"
                    else:
                        try:
                            demand_speed_val_s = float(demand_speed_raw_s)
                        except (TypeError, ValueError):
                            demand_speed_val_s = "ERR"

                # Update comms lag (rolling average of MPOS read)
                if comms_lag_samples:
                    avg_ms = sum(comms_lag_samples) / len(comms_lag_samples)
                    lag_str = f"MPOS read: {avg_ms:.1f} ms (avg {len(comms_lag_samples)})"
                    if comms_lag_label.value != lag_str:
                        comms_lag_label.value = lag_str
                        dirty = True
                    try:
                        if rotary_comms_lag_label.value != lag_str:
                            rotary_comms_lag_label.value = lag_str
                            dirty = True
                    except NameError:
                        pass

                # Update Master visualizer
                if mpos_val_m is not None:
                    if position_zero_m[0] is None:
                        position_zero_m[0] = mpos_val_m
                    delta = mpos_val_m - position_zero_m[0]
                    offset_px = CONVEYOR_VISUAL_DIRECTION * delta * scale_px_per_unit[0]
                    new_offset = offset_px % BELT_SPACING
                    if abs((belt_offset_spacer.width or 0) - new_offset) > 0.1:
                        belt_offset_spacer.width = new_offset
                        dirty = True

                # Update Slave visualizer — absolute MPOS maps directly to pixel position
                if mpos_val_s is not None:
                    visual_slave_mpos[0] = mpos_val_s
                    new_left = _slave_mpos_to_shear_left(mpos_val_s, visual_inner_width_current[0])
                    if abs((shear_position_spacer.width or 0) - new_left) > 0.1:
                        shear_position_spacer.width = new_left
                        dirty = True

                try:
                    if update_rotary_sim_from_reads(
                        mpos_val_m,
                        mpos_val_s,
                        mspeed_val_m,
                        mspeed_val_s,
                        demand_speed_val_s,
                        frame_start,
                    ):
                        dirty = True
                except NameError:
                    pass

                # Update FPS display
                if len(fps_timestamps) >= 2:
                    span = fps_timestamps[-1] - fps_timestamps[0]
                    if span > 0:
                        current_fps = (len(fps_timestamps) - 1) / span
                        fps_str = f"{current_fps:.0f} FPS"
                        if fps_label.value != fps_str:
                            fps_label.value = fps_str
                            dirty = True
                        try:
                            if rotary_fps_label.value != fps_str:
                                rotary_fps_label.value = fps_str
                                dirty = True
                        except NameError:
                            pass

                if dirty and frame_counter % ui_update_every == 0:
                    _update_if_mounted(monitor_container)
                    # params_panel lives outside monitor_container (in the
                    # connection header row), so it needs its own update.
                    _update_if_mounted(params_panel)
                    try:
                        _update_if_mounted(rotary_sim_container)
                    except NameError:
                        pass
            except Exception as ex:
                print(f"Monitor error: {ex}")

            # Sleep only the remaining frame budget to target 60 FPS
            elapsed = time.perf_counter() - frame_start
            remaining = FRAME_BUDGET - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            else:
                await asyncio.sleep(0)  # yield to event loop

    def start_monitor():
        nonlocal monitor_running
        if monitor_running:
            return
        monitor_running = True
        asyncio.create_task(monitor_async_loop())

    # Parameter readout table — lifted out so it can sit next to the Connection panel.
    params_panel = ft.Container(
        content=ft.Column(monitor_rows, spacing=6),
        bgcolor=PANEL_BG,
        border_radius=8,
        padding=15,
        border=ft.Border.all(1, BORDER_COLOR),
        col={"xs": 12, "lg": 5},
    )

    monitor_control_cluster_height = 116

    monitor_controls_grid = ft.ResponsiveRow(
        [
            control_cluster(
                "Conveyor control",
                [master_rev_btn, master_fwd_btn, master_stop_btn, master_speed_input, master_speed_slider],
                icon=ft.Icons.PLAY_ARROW,
                height=monitor_control_cluster_height,
                col={"xs": 12, "md": 8, "xl": 8},
            ),
            control_cluster(
                "Knife output state",
                [cutter_output_lamp_panel],
                icon=ft.Icons.POWER,
                height=monitor_control_cluster_height,
                col={"xs": 12, "md": 4, "xl": 4},
            ),
        ],
        columns=12,
        spacing=10,
        run_spacing=10,
    )

    monitor_container = ft.Container(
        content=ft.Column([
            ft.Row(
                [
                    section_header("Flying Shear Live Monitor", "Live axes, conveyor controls and knife state", ft.Icons.ANALYTICS),
                    ft.Row(
                        [comms_lag_label, ft.Text("|", size=10, color=ft.Colors.GREY_700), fps_label],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            monitor_controls_grid,
            ft.Row(
                [recenter_btn,
                 ft.Text("Scale:", size=12, color=ft.Colors.GREY_400),
                 scale_minus10_btn, scale_minus_btn,
                 scale_plus_btn, scale_plus10_btn,
                 scale_value_label],
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
            ),
            shear_conveyor_view,
        ], spacing=14),
        bgcolor=PANEL_BG,
        border_radius=8,
        padding=20,
        border=ft.Border.all(1, BORDER_COLOR),
    )

    # --- UI Elements: Connection Phase ---
    def on_ip_change(e):
        settings["controller_ip"] = e.control.value
        save_settings(settings)

    ip_input = ft.TextField(
        label="Controller IP", 
        value=settings.get("controller_ip", "192.168.1.250"), 
        width=200, 
        bgcolor=DARKER_BG, 
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        prefix_icon=ft.Icons.LAN,
        on_change=on_ip_change
    )
    
    async def on_connect_click(e):
        # Capture the Flet event loop so background-thread status_callback()
        # invocations can marshal UI updates back via call_soon_threadsafe.
        ui_loop_holder["loop"] = asyncio.get_running_loop()
        status_text.value = "Connecting..."
        status_text.color = ft.Colors.WHITE
        connect_btn.disabled = True
        ip_input.disabled = True
        connect_progress.visible = True
        _set_wdog_button_state(None, busy=True)
        page.update()

        loop = asyncio.get_running_loop()
        try:
            success = await loop.run_in_executor(uapi_executor, trio_conn.connect, ip_input.value)
        except Exception as ex:
            print(f"Connect error: {ex}")
            success = False

        if success:
            status_text.value = "Connected Successfully!"
            status_text.color = SUCCESS_COLOR
            connect_btn.disabled = True
            ip_input.disabled = True
            connect_progress.visible = False
            try:
                _set_motion_controls_enabled(True)
            except NameError:
                pass
            page.update()
            show_snack("Controller connected. Live monitor is starting.", "success")

            await refresh_wdog_state()
            try:
                await refresh_rotary_drum_units()
            except NameError:
                pass
            start_monitor()
            saved_sets = get_saved_axis_param_sets()
            if saved_sets:
                status_text.value = "Connected. Review saved axis parameters before applying."
                status_text.color = WARNING_COLOR
                show_saved_params_dialog(saved_sets)
            else:
                status_text.value = "Connected. No saved axis parameters found."
                status_text.color = SUCCESS_COLOR
                page.update()
        else:
            status_text.value = "Connection Failed."
            status_text.color = ERROR_COLOR
            connect_btn.disabled = False
            ip_input.disabled = False
            connect_progress.visible = False
            try:
                _set_motion_controls_enabled(False)
            except NameError:
                pass
            _set_wdog_button_state(None)
            show_snack("Connection failed. Check controller IP and network state.", "error")
            page.update()

    connect_progress = ft.ProgressRing(width=18, height=18, stroke_width=2, color=ft.Colors.CYAN_200, visible=False)
    connect_btn = ft.FilledButton("Connect", icon=ft.Icons.LAN, on_click=on_connect_click,
                                  style=ft.ButtonStyle(bgcolor=ACCENT_COLOR, color=ft.Colors.WHITE))
    status_text = ft.Text("", size=14, color=TEXT_COLOR, width=300)

    conn_row = ft.Row([ip_input, connect_btn, connect_progress, wdog_btn, status_text],
                      wrap=True, spacing=10, run_spacing=10,
                      alignment=ft.MainAxisAlignment.START,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # --- UI Elements: Setup Phase ---
    axis_dropdown = ft.Dropdown(
        label="Axis being tuned",
        width=170,
        options=[
            ft.dropdown.Option(
                str(i),
                f"Axis {i} ✓" if settings.get("axis_params", {}).get(str(i)) else f"Axis {i}"
            )
            for i in range(16)
        ],
        value=settings.get("target_axis", "0"),
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
    )

    # Dictionary to hold the parameter inputs
    param_inputs = {}
    parameters = [
        ("UNITS", "1.0"),
        ("SPEED", "10.0"),
        ("ACCEL", "1.0"),
        ("DECEL", "1.0"),
        ("FASTDEC", "200.0"),
        ("JERK", "100000.0"),
        ("DRIVE_FE_LIMIT", "1"),
        ("FE_LIMIT", "1"),
        ("FE_RANGE", "1"),
        ("RS_LIMIT", "0.0"),
        ("FS_LIMIT", "0.0"),
    ]
    parameter_defaults = dict(parameters)
    parameter_groups = [
        ("Units", ["UNITS"]),
        ("Motion", ["SPEED", "ACCEL", "DECEL", "FASTDEC", "JERK"]),
        ("Following Error", ["DRIVE_FE_LIMIT", "FE_LIMIT", "FE_RANGE"]),
        ("Travel Limits", ["RS_LIMIT", "FS_LIMIT"]),
    ]
    parameter_tooltips = {
        "UNITS": "User units conversion for this axis.",
        "SPEED": "Default speed used by the axis.",
        "ACCEL": "Default acceleration.",
        "DECEL": "Default deceleration.",
        "FASTDEC": "Emergency or fast deceleration.",
        "JERK": "Jerk limit used for ramp shaping.",
        "DRIVE_FE_LIMIT": "Drive following-error limit.",
        "FE_LIMIT": "Controller following-error limit.",
        "FE_RANGE": "Following-error warning range.",
        "RS_LIMIT": "Reverse software travel limit.",
        "FS_LIMIT": "Forward software travel limit.",
    }

    def get_axis_param_settings(axis):
        axis_key = str(axis)
        axis_params = settings.setdefault("axis_params", {})
        return axis_params.setdefault(axis_key, {})

    def get_saved_param_value(axis, param_name, default):
        axis_settings = get_axis_param_settings(axis)
        return axis_settings.get(param_name, default)

    def save_axis_param_value(axis, param_name, value):
        axis_settings = get_axis_param_settings(axis)
        axis_settings[param_name] = value
        save_settings(settings)

    def refresh_axis_dropdown():
        axis_params = settings.get("axis_params", {})
        axis_dropdown.options = [
            ft.dropdown.Option(
                str(i),
                f"Axis {i} ✓" if axis_params.get(str(i)) else f"Axis {i}"
            )
            for i in range(16)
        ]
        refresh_copy_dropdown()

    param_controls = []

    def create_param_change_handler(p_name):
        def handler(e):
            axis = axis_dropdown.value or "0"
            save_axis_param_value(axis, p_name, e.control.value)
            validate_axis_param_inputs(show_errors=False)
        return handler

    for param, default in parameters:
        initial_axis = settings.get("target_axis", "0")
        initial_val = get_saved_param_value(initial_axis, param, default)

        txt = ft.TextField(
            label=param, 
            value=initial_val, 
            width=160, 
            bgcolor=DARKER_BG, 
            color=TEXT_COLOR,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_COLOR,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT,
            on_change=create_param_change_handler(param),
            tooltip=parameter_tooltips.get(param),
        )
        param_inputs[param] = txt
        param_controls.append(txt)

    def validate_axis_param_inputs(show_errors=True):
        valid = True
        values = {}
        for param_name, _ in parameters:
            control = param_inputs[param_name]
            raw = (control.value or "").strip()
            try:
                value = float(raw)
                values[param_name] = value
                control.error_text = None
            except ValueError:
                valid = False
                if show_errors:
                    control.error_text = "Number required"

        positive_params = ["UNITS", "SPEED", "ACCEL", "DECEL", "FASTDEC", "JERK",
                           "DRIVE_FE_LIMIT", "FE_LIMIT", "FE_RANGE"]
        for param_name in positive_params:
            if param_name in values and values[param_name] <= 0:
                valid = False
                if show_errors:
                    param_inputs[param_name].error_text = "Must be > 0"

        limits_disabled = (
            "RS_LIMIT" in values and "FS_LIMIT" in values
            and values["RS_LIMIT"] == 0 and values["FS_LIMIT"] == 0
        )
        if (
            "RS_LIMIT" in values and "FS_LIMIT" in values
            and not limits_disabled
            and values["RS_LIMIT"] >= values["FS_LIMIT"]
        ):
            valid = False
            if show_errors:
                param_inputs["RS_LIMIT"].error_text = "Below FS_LIMIT"
                param_inputs["FS_LIMIT"].error_text = "Above RS_LIMIT"

        if show_errors:
            page.update()
        return valid

    def on_target_axis_change(e):
        axis = e.control.value or "0"
        settings["target_axis"] = axis

        axis_has_params = bool(settings.get("axis_params", {}).get(str(axis), {}))
        for param_name, _ in parameters:
            param_inputs[param_name].value = (
                get_saved_param_value(axis, param_name, parameter_defaults[param_name])
                if axis_has_params
                else parameter_defaults[param_name]
            )

        save_settings(settings)
        refresh_axis_dropdown()
        page.update()

    axis_dropdown.on_select = on_target_axis_change

    copy_from_dropdown = ft.Dropdown(
        label="Copy from",
        width=150,
        options=[
            ft.dropdown.Option(str(i), f"Axis {i} ✓")
            for i in range(16)
            if settings.get("axis_params", {}).get(str(i))
        ],
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
    )

    def refresh_copy_dropdown():
        axis_params = settings.get("axis_params", {})
        copy_from_dropdown.options = [
            ft.dropdown.Option(str(i), f"Axis {i} ✓")
            for i in range(16)
            if axis_params.get(str(i))
        ]

    def on_copy_click(e):
        src = copy_from_dropdown.value
        if not src:
            return
        src_params = settings.get("axis_params", {}).get(str(src), {})
        if not src_params:
            return
        dst = axis_dropdown.value or "0"
        dst_settings = get_axis_param_settings(dst)
        for param_name, _ in parameters:
            val = src_params.get(param_name, parameter_defaults[param_name])
            dst_settings[param_name] = val
            param_inputs[param_name].value = val
        save_settings(settings)
        refresh_axis_dropdown()
        show_snack(f"Copied saved parameters from Axis {src} to Axis {dst}.", "success")
        page.update()

    copy_btn = ft.FilledButton(
        "Copy", icon=ft.Icons.CONTENT_COPY, on_click=on_copy_click,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        height=38,
    )

    def _apply_params_blocking(axis, param_values):
        """Runs on the pinned UAPI thread. `param_values` is a plain dict
        snapshotted from the UI controls on the UI thread."""
        conn = trio_conn.connection
        if not conn:
            raise Exception("No Trio connection")

        for param_name, val_str in param_values.items():
            method = getattr(conn, f"SetAxisParameter_{param_name}", None)
            if not method:
                print(f"Warning: SetAxisParameter_{param_name} not found.")
                continue
            if param_name in ["DRIVE_FE_LIMIT", "FE_LIMIT", "FE_RANGE"]:
                val = int(float(val_str))
            else:
                val = float(val_str)
            try:
                method(axis, val)
            except Exception as e:
                raise Exception(f"{param_name} ({val}): {e}")
        if hasattr(conn, "SetSystemParameter_LIMIT_BUFFERED"):
            try:
                conn.SetSystemParameter_LIMIT_BUFFERED(50)
            except Exception as e:
                print(f"Warning: Failed to set LIMIT_BUFFERED: {e}")

    def get_saved_axis_param_sets():
        """Returns a list of (axis, param_values) tuples from the saved settings.

        Supports three formats (checked in priority order):
          1. "axes": {"0": {"SPEED": "10.0", ...}, ...}  — recommended new format
          2. "axis_params": {"0": {"SPEED": "10.0", ...}, ...}  — current code format
          3. Legacy flat: target_axis + param_SPEED, param_ACCEL, ...
        """
        saved_sets = []

        axes_config = settings.get("axes")
        if isinstance(axes_config, dict):
            for axis_key, axis_params in axes_config.items():
                try:
                    axis = int(axis_key)
                except ValueError:
                    continue
                if not isinstance(axis_params, dict):
                    continue
                param_values = {
                    pn: str(axis_params[pn])
                    for pn, _ in parameters
                    if pn in axis_params
                }
                if param_values:
                    saved_sets.append((axis, param_values))
            return saved_sets

        axis_params_config = settings.get("axis_params")
        if isinstance(axis_params_config, dict):
            for axis_key, axis_params in axis_params_config.items():
                try:
                    axis = int(axis_key)
                except ValueError:
                    continue
                if not isinstance(axis_params, dict):
                    continue
                param_values = {
                    pn: str(axis_params[pn])
                    for pn, _ in parameters
                    if pn in axis_params
                }
                if param_values:
                    saved_sets.append((axis, param_values))
            return saved_sets

        # Legacy flat format
        target_axis = settings.get("target_axis")
        if target_axis is not None:
            try:
                axis = int(target_axis)
            except ValueError:
                axis = 0
            param_values = {
                pn: str(settings[f"param_{pn}"])
                for pn, _ in parameters
                if f"param_{pn}" in settings
            }
            if param_values:
                saved_sets.append((axis, param_values))

        return saved_sets

    async def apply_saved_params_after_connection():
        saved_sets = get_saved_axis_param_sets()

        if not saved_sets:
            status_text.value = "Connected. No saved axis parameters found."
            status_text.color = WARNING_COLOR
            page.update()
            return

        loop = asyncio.get_running_loop()
        applied_axes = []
        failed_axes = []

        for axis, param_values in saved_sets:
            try:
                status_text.value = f"Applying saved parameters to Axis {axis}..."
                status_text.color = ft.Colors.WHITE
                page.update()

                await loop.run_in_executor(
                    uapi_executor,
                    _apply_params_blocking,
                    axis,
                    param_values,
                )
                applied_axes.append(axis)
            except Exception as ex:
                print(f"Failed to apply saved params to Axis {axis}: {ex}")
                failed_axes.append((axis, ex))

        if failed_axes:
            failed_text = ", ".join(str(a) for a, _ in failed_axes)
            status_text.value = f"Connected. Some saved params failed. Failed axes: {failed_text}"
            status_text.color = WARNING_COLOR
            show_snack(f"Some saved parameter sets failed: Axis {failed_text}.", "warning")
        else:
            applied_text = ", ".join(str(a) for a in applied_axes)
            status_text.value = f"Connected. Saved parameters applied to Axis {applied_text}."
            status_text.color = SUCCESS_COLOR
            show_snack(f"Saved parameters applied to Axis {applied_text}.", "success")
        page.update()

    saved_params_dialog = ft.AlertDialog(modal=True)

    def show_saved_params_dialog(saved_sets):
        axis_list = ", ".join(f"Axis {axis}" for axis, _ in saved_sets)

        async def apply_saved_from_dialog(e):
            saved_params_dialog.open = False
            page.update()
            await apply_saved_params_after_connection()

        def skip_saved_from_dialog(e):
            saved_params_dialog.open = False
            status_text.value = "Connected. Saved parameters were not applied."
            status_text.color = WARNING_COLOR
            page.update()

        saved_params_dialog.title = ft.Text("Apply saved axis parameters?")
        saved_params_dialog.content = ft.Text(
            f"Saved parameter sets were found for {axis_list}. "
            "Apply them only if this controller and machine are the intended demo setup.",
            color=TEXT_COLOR,
        )
        saved_params_dialog.actions = [
            ft.OutlinedButton("Skip", on_click=skip_saved_from_dialog),
            ft.FilledButton("Apply now", on_click=apply_saved_from_dialog,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)),
        ]
        saved_params_dialog.actions_alignment = ft.MainAxisAlignment.END
        if hasattr(page, "show_dialog"):
            page.show_dialog(saved_params_dialog)
        else:
            page.dialog = saved_params_dialog
            saved_params_dialog.open = True
            page.update()

    apply_progress = ft.ProgressRing(width=18, height=18, stroke_width=2, color=ft.Colors.CYAN_200, visible=False)

    async def on_apply_click(e):
        if not trio_conn.connection:
            status_text.value = "Not connected!"
            status_text.color = ERROR_COLOR
            show_snack("Connect to the controller before applying axis parameters.", "warning")
            page.update()
            return

        if not validate_axis_param_inputs(show_errors=True):
            status_text.value = "Fix highlighted axis parameters before applying."
            status_text.color = ERROR_COLOR
            show_snack("Fix highlighted axis parameters before applying.", "error")
            page.update()
            return

        axis = int(axis_dropdown.value)
        # Snapshot UI control values on the UI thread, then pass plain data to
        # the worker so the executor never reads Flet controls directly.
        param_values = {pn: tc.value for pn, tc in param_inputs.items()}

        settings["target_axis"] = axis_dropdown.value

        axis_settings = get_axis_param_settings(axis_dropdown.value)
        for pn, val in param_values.items():
            axis_settings[pn] = val

        save_settings(settings)
        refresh_axis_dropdown()

        loop = asyncio.get_running_loop()
        apply_btn.disabled = True
        apply_progress.visible = True
        status_text.value = f"Applying parameters to Axis {axis}..."
        status_text.color = ft.Colors.WHITE
        page.update()
        try:
            await loop.run_in_executor(uapi_executor, _apply_params_blocking, axis, param_values)
            status_text.value = f"Parameters applied successfully to Axis {axis}!"
            status_text.color = SUCCESS_COLOR
            show_snack(f"Parameters applied to Axis {axis}.", "success")
        except Exception as ex:
            status_text.value = f"Error applying: {ex}"
            status_text.color = ERROR_COLOR
            show_snack(f"Parameter apply failed: {ex}", "error")
        finally:
            apply_btn.disabled = False
            apply_progress.visible = False
        page.update()

    apply_btn = ft.FilledButton("Apply Parameters", on_click=on_apply_click,
                                icon=ft.Icons.CHECK_CIRCLE,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE))

    def build_param_group(title, names):
        controls = [param_inputs[name] for name in names]
        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Row(controls, wrap=True, alignment=ft.MainAxisAlignment.START,
                       spacing=15, run_spacing=15),
            ], spacing=10),
            bgcolor=PANEL_BG,
            border_radius=8,
            padding=14,
            border=ft.Border.all(1, BORDER_COLOR),
        )

    params_sections = [build_param_group(title, names) for title, names in parameter_groups]

    setup_container = ft.Column([
        ft.Container(height=10),
        ft.Row(
            [
                axis_dropdown,
                ft.Container(width=30),
                ft.Text("Copy saved axis:", size=13, color=ft.Colors.GREY_400),
                copy_from_dropdown,
                copy_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            run_spacing=10,
            spacing=10,
        ),
        ft.Container(height=10),
        *params_sections,
        ft.Container(height=20),
        ft.Row([apply_btn, apply_progress], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    ], spacing=10)

    # === Flying Shear Calculator ===
    calc_settings = settings.setdefault("shear_calc", {})

    def cs_set(k, v):
        calc_settings[k] = v
        save_settings(settings)

    def save_calc_settings(e=None):
        save_settings(settings)

    CALC_TOOLTIPS = {
        "cut": "Master/link distance between cuts. In MOVELINK this becomes the available link-axis distance for accel, sync, decel, and retract dwell.",
        "vline": "Maximum material line speed on the link axis. The shear must match this speed during the synchronized cut section.",
        "vmax": "Maximum allowed shear/slave speed. Used to flag impossible line-speed matching and retract moves.",
        "amax": "Maximum shear/slave acceleration. Accel distance is estimated from v^2/(2a), then multiplied by the safety factor.",
        "tsync": "Time the shear should remain synchronized with the material while the cut output is active.",
        "safety": "Multiplier applied to the calculated accel/decel distance to leave practical margin.",
        "profile": "Selects how MOVELINK shapes acceleration/deceleration: trapezoidal, sinusoidal S-curve, polynomial S-curves, or linear ramp mode.",
        "start_mode": "MOVELINK can start immediately, on MARK, at an absolute link-axis position, on MARKB, or on an R_MARK channel.",
        "link_pos": "Absolute start position on the link axis when using Absolute position start, or registration channel number when using R_MARK channel start.",
        "link_source": "MOVELINK normally follows the master's measured position (MPOS). DPOS mode follows the master's demanded position instead.",
        "direction_mode": "Chooses whether the link is active for any master movement, only while the master moves positive, or only after a positive movement threshold is reached.",
        "repeat_mode": "Program loop repeats the whole shear sequence. MOVELINK repeat asks the controller to repeat the linked move bi-directionally.",
        "base_dist": "Firmware V2.0253+: base distance is part of the total MOVELINK distance and lets the profile start/end at a nonzero base ratio.",
        "stroke": "Total slave/shear travel for accel, synchronized cut, and decel before retract.",
        "acc": "Master/link-axis distance used during acceleration. Rule from MOVELINK.md: to match speed, link distance is twice the shear travel.",
        "track": "Master/link-axis synchronized distance. At matched speed, shear distance equals link distance.",
        "dec": "Master/link-axis distance used during deceleration. Mirrored from the acceleration phase.",
        "ret": "Remaining master/link-axis distance before the next cut, available for retracting the shear carriage.",
        "vpeak": "Estimated peak shear speed needed during retract. This is checked against the shear max speed.",
        "profile_graph": "Velocity profile drawn from the calculated MOVELINK link-axis distances.",
        "options": "Decimal MOVELINK link_options value created from the selected profile, start trigger, position source, direction, and repeat settings.",
        "profile_result": "Active MOVELINK acceleration/deceleration profile used in generated commands.",
        "start_result": "Start condition applied to the first acceleration MOVELINK in the generated shear cycle.",
        "base_result": "Base distance included as MOVELINK parameter 8 when enabled. Parameters 6 and 7 are required when using base distance.",
        "warnings": "Validation messages for impossible speed, short cut length, ramp scaling, trigger setup, and repeat/base-distance caveats.",
        "code": "Generated Trio BASIC program. Copy this into the controller after checking axes, output number, and safety conditions.",
        "copy": "Copy the generated Trio BASIC MOVELINK program to the Windows clipboard.",
    }

    def make_input(label, key, default, width=160, suffix=None):
        tf = ft.TextField(
            label=label, value=str(calc_settings.get(key, default)),
            width=width, bgcolor=DARKER_BG, color=TEXT_COLOR,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_COLOR,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT,
            suffix=suffix,
            text_size=13,
            tooltip=CALC_TOOLTIPS.get(key),
        )
        return tf

    def make_dropdown(label, key, default, options, width=180):
        return ft.Dropdown(
            label=label, value=str(calc_settings.get(key, default)),
            width=width, bgcolor=DARKER_BG, color=TEXT_COLOR,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_COLOR,
            text_size=13,
            options=[ft.dropdown.Option(value, text) for value, text in options],
            tooltip=CALC_TOOLTIPS.get(key),
        )

    cut_input    = make_input("Cut length",      "cut",    100, suffix="mm")
    vline_input  = make_input("MAX line speed",  "vline",  500, suffix="mm/s")
    vmax_input   = make_input("Shear max speed", "vmax",   1500, width=180, suffix="mm/s")
    amax_input   = make_input("Shear max accel", "amax",   5000, width=180, suffix="mm/s2")
    tsync_input  = make_input("Sync time",       "tsync",  30,   width=140, suffix="ms")
    safety_input = make_input("Safety factor",           "safety", 1.5,  width=120)

    profile_dropdown = make_dropdown(
        "MOVELINK profile", "profile", "trapezoid",
        [
            ("trapezoid", "Trapezoidal"),
            ("sine", "Sine S-curve"),
            ("power9", "Power 9 S-curve"),
            ("power7", "Power 7 S-curve"),
            ("power5", "Power 5 S-curve"),
            ("linear_s", "Linear ramp mode"),
        ],
        width=190,
    )
    start_dropdown = make_dropdown(
        "Start trigger", "start_mode", "immediate",
        [
            ("immediate", "Immediate"),
            ("mark", "MARK"),
            ("absolute", "Absolute position"),
            ("markb", "MARKB"),
            ("rmark", "R_MARK channel"),
        ],
        width=190,
    )
    link_pos_input = make_input("Link pos / channel", "link_pos", 0, width=150)
    source_dropdown = make_dropdown(
        "Link source", "link_source", "mpos",
        [("mpos", "Master MPOS"), ("dpos", "Master DPOS")],
        width=160,
    )
    direction_dropdown = make_dropdown(
        "Direction", "direction_mode", "any",
        [
            ("any", "Any direction"),
            ("positive", "Positive only"),
            ("positive_threshold", "Positive threshold"),
        ],
        width=185,
    )
    repeat_dropdown = make_dropdown(
        "Repeat style", "repeat_mode", "program_loop",
        [
            ("program_loop", "Program WHILE loop"),
            ("movelink_repeat", "MOVELINK repeat bit"),
        ],
        width=190,
    )
    base_dist_checkbox = ft.Checkbox(
        label="Use base distance",
        value=bool(calc_settings.get("use_base_dist", False)),
        fill_color=ft.Colors.BLUE_700,
        check_color=ft.Colors.WHITE,
        tooltip=CALC_TOOLTIPS["base_dist"],
    )
    base_dist_input = make_input("Base distance", "base_dist", 0, width=140, suffix="mm")

    result_labels = {
        k: ft.Text("---", size=18, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD)
        for k in ("stroke", "acc", "track", "dec", "ret", "vpeak", "options", "profile", "start", "base")
    }
    warning_text = ft.Text(
        "", size=13, color=ft.Colors.AMBER_300,
        tooltip=CALC_TOOLTIPS["warnings"],
        selectable=True,
        expand=True,
    )
    warning_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.GREY_400)
    warning_banner = ft.Container(
        content=ft.Row(
            [warning_icon, warning_text],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        bgcolor=PANEL_ALT_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        visible=False,
    )

    _WARNING_PALETTE = {
        "ok":      ("#0f2517", "#1f4d2e", ft.Icons.CHECK_CIRCLE,    ft.Colors.GREEN_300),
        "error":   ("#2a1313", "#5a2222", ft.Icons.ERROR_OUTLINE,   ft.Colors.RED_300),
        "warning": ("#2a200c", "#5a4014", ft.Icons.WARNING_AMBER,   ft.Colors.AMBER_300),
    }

    def _apply_warning_severity(severity):
        if severity not in _WARNING_PALETTE:
            warning_banner.visible = False
            return
        bg, border, icon_name, fg = _WARNING_PALETTE[severity]
        warning_banner.bgcolor = bg
        warning_banner.border = ft.Border.all(1, border)
        warning_icon.name = icon_name
        warning_icon.color = fg
        warning_text.color = fg
        warning_banner.visible = True

    review_text = ft.Text("", size=12, color=ft.Colors.GREY_300)
    profile_canvas = cv.Canvas(width=660, height=218, shapes=[])

    def fmt_distance(value):
        abs_value = abs(value)
        if abs_value >= 100:
            return f"{value:.0f}"
        if abs_value >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"

    def canvas_paint(color, width=1, dash=None, style=ft.PaintingStyle.STROKE):
        return ft.Paint(
            color=color,
            stroke_width=width,
            stroke_cap=ft.StrokeCap.ROUND,
            stroke_dash_pattern=dash,
            style=style,
        )

    def add_profile_text(shapes, x, y, value, size=11, color=ft.Colors.GREY_300,
                         weight=None, align=ft.Alignment.CENTER, max_width=None, rotate=0):
        shapes.append(
            cv.Text(
                x=x,
                y=y,
                value=value,
                style=ft.TextStyle(size=size, color=color, weight=weight),
                alignment=align,
                text_align=ft.TextAlign.CENTER,
                max_width=max_width,
                rotate=rotate,
            )
        )

    def scaled_segment_widths(values, plot_width):
        positive_values = [max(v, 0) for v in values]
        total = sum(positive_values)
        if total <= 0:
            return [plot_width / len(values) for _ in values]

        minimums = [62, 92, 62, 86]
        minimums = [minimums[i] if positive_values[i] > 0 else 0 for i in range(len(values))]
        minimum_total = sum(minimums)
        if minimum_total >= plot_width:
            return [plot_width * value / total if value > 0 else 0 for value in positive_values]

        remaining = plot_width - minimum_total
        return [
            minimums[i] + (remaining * positive_values[i] / total if positive_values[i] > 0 else 0)
            for i in range(len(values))
        ]

    def build_velocity_profile_shapes(accel_link, sync_link, decel_link, ret_link, profile):
        width = 660
        height = 218
        left = 70
        right = 34
        top = 22
        baseline = 150
        peak = 50
        plot_end = width - right
        plot_width = plot_end - left
        axis_color = "#b8a80f"
        profile_color = "#b9250f"
        return_color = "#90a4ae"
        grid_color = "#46505a"
        label_color = ft.Colors.GREY_300

        values = [accel_link, sync_link, decel_link, max(ret_link, 0)]
        widths = scaled_segment_widths(values, plot_width)
        x0 = left
        x1 = x0 + widths[0]
        x2 = x1 + widths[1]
        x3 = x2 + widths[2]
        x4 = x3 + widths[3]

        axis_paint = canvas_paint(axis_color, 3)
        grid_paint = canvas_paint(grid_color, 1, dash=[4, 5])
        profile_paint = canvas_paint(profile_color, 4.5)
        return_paint = canvas_paint(return_color, 3, dash=[6, 5])
        thin_return_paint = canvas_paint(return_color, 1.4)

        shapes = [
            cv.Rect(
                0, 0, width, height,
                border_radius=ft.BorderRadius.all(8),
                paint=ft.Paint(color=DARKER_BG, style=ft.PaintingStyle.FILL),
            ),
            cv.Line(left, baseline, plot_end + 12, baseline, paint=axis_paint),
            cv.Line(left, baseline, left, top, paint=axis_paint),
            cv.Line(plot_end + 12, baseline, plot_end + 2, baseline - 6, paint=axis_paint),
            cv.Line(plot_end + 12, baseline, plot_end + 2, baseline + 6, paint=axis_paint),
            cv.Line(left, top, left - 6, top + 10, paint=axis_paint),
            cv.Line(left, top, left + 6, top + 10, paint=axis_paint),
        ]

        for marker_x in (x1, x2, x3):
            if left + 8 < marker_x < plot_end - 8:
                shapes.append(cv.Line(marker_x, top + 8, marker_x, baseline + 8, paint=grid_paint))

        if profile in ("sine", "power9", "power7", "power5"):
            ramp_in = max(widths[0], 1)
            ramp_out = max(widths[2], 1)
            elements = [
                cv.Path.MoveTo(x0, baseline),
                cv.Path.CubicTo(x0 + ramp_in * 0.30, baseline, x1 - ramp_in * 0.30, peak, x1, peak),
                cv.Path.LineTo(x2, peak),
                cv.Path.CubicTo(x2 + ramp_out * 0.30, peak, x3 - ramp_out * 0.30, baseline, x3, baseline),
            ]
        else:
            elements = [
                cv.Path.MoveTo(x0, baseline),
                cv.Path.LineTo(x1, peak),
                cv.Path.LineTo(x2, peak),
                cv.Path.LineTo(x3, baseline),
            ]
        shapes.append(cv.Path(elements=elements, paint=profile_paint))

        if ret_link > 0:
            return_y = baseline - 17
            shapes.append(cv.Line(x3 + 6, return_y, min(x4, plot_end), return_y, paint=return_paint))
            shapes.append(cv.Line(min(x4, plot_end), return_y, min(x4, plot_end) - 8, return_y - 5, paint=thin_return_paint))
            shapes.append(cv.Line(min(x4, plot_end), return_y, min(x4, plot_end) - 8, return_y + 5, paint=thin_return_paint))
            add_profile_text(
                shapes, (x3 + min(x4, plot_end)) / 2, peak + 38,
                "Return", size=17, color=ft.Colors.WHITE,
                max_width=max(80, min(x4, plot_end) - x3),
            )

        if sync_link > 0:
            add_profile_text(
                shapes, (x1 + x2) / 2, peak - 22,
                "Synchronized", size=18, color=ft.Colors.WHITE,
                max_width=max(120, x2 - x1),
            )

        add_profile_text(
            shapes, 24, (top + baseline) / 2, "Velocity",
            size=15, color=ft.Colors.WHITE, rotate=-1.5708,
        )
        add_profile_text(
            shapes, plot_end - 46, baseline + 45, "Distance",
            size=13, color=ft.Colors.WHITE, max_width=130,
        )

        label_y = baseline + 18
        segment_specs = [
            (x0, x1, accel_link),
            (x1, x2, sync_link),
            (x2, x3, decel_link),
        ]
        if ret_link > 0:
            segment_specs.append((x3, min(x4, plot_end), ret_link))

        for start_x, end_x, value in segment_specs:
            if end_x - start_x < 10:
                continue
            add_profile_text(
                shapes, (start_x + end_x) / 2, label_y,
                f"{fmt_distance(value)} mm",
                size=12, color=label_color, max_width=max(54, end_x - start_x - 4),
            )

        if ret_link < 0:
            add_profile_text(
                shapes, plot_end - 92, peak + 38,
                "No return distance", size=13, color=ft.Colors.RED_200, max_width=150,
            )

        return shapes

    phase_bar = ft.Column([
        ft.Text("Generated MOVELINK velocity profile", size=12, color=ft.Colors.GREY_400),
        ft.Container(
            content=profile_canvas,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            tooltip=CALC_TOOLTIPS["profile_graph"],
        ),
    ], spacing=6)

    code_output = ft.TextField(
        value="", read_only=True, multiline=True, min_lines=29, max_lines=45,
        bgcolor=DARKER_BG, color=ft.Colors.GREEN_200,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        text_style=ft.TextStyle(font_family="Consolas", size=12),
        expand=True,
        tooltip=CALC_TOOLTIPS["code"],
    )

    def result_card(label, key, tooltip_key=None):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=12, color=ft.Colors.GREY_400),
                result_labels[key],
            ], spacing=4),
            bgcolor=PANEL_BG, border_radius=8, padding=12,
            border=ft.Border.all(1, BORDER_COLOR), width=150,
            tooltip=CALC_TOOLTIPS.get(tooltip_key or key),
        )

    def fmt_speed(value):
        if value >= 100:
            return f"{value:.0f}"
        if value >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"

    def option_bit(index):
        return 1 << index

    def build_link_options(profile, start_mode, link_source, direction_mode, repeat_mode):
        options = 0

        profile_modes = {
            "sine": 0,
            "power9": 1,
            "power7": 2,
            "power5": 3,
            "linear_s": 4,
        }
        if profile in profile_modes:
            options |= option_bit(4)
            options |= profile_modes[profile] << 10

        start_bits = {
            "mark": 0,
            "absolute": 1,
            "markb": 8,
            "rmark": 9,
        }
        if start_mode in start_bits:
            options |= option_bit(start_bits[start_mode])

        if link_source == "dpos":
            options |= option_bit(13)

        if direction_mode == "positive":
            options |= option_bit(5)
        elif direction_mode == "positive_threshold":
            options |= option_bit(14)

        if repeat_mode == "movelink_repeat":
            options |= option_bit(2)

        return options

    def format_movelink(distance, link_dist, link_acc, link_dec, options, link_pos, base_dist=None):
        args = [
            f"{distance:.3f}",
            f"{link_dist:.3f}",
            f"{link_acc:.3f}",
            f"{link_dec:.3f}",
            "link_ax",
        ]

        if base_dist is not None:
            args.extend([str(options), f"{link_pos:.3f}", f"{base_dist:.3f}"])
        elif options or link_pos:
            args.extend([str(options), f"{link_pos:.3f}"])

        return f"MOVELINK({', '.join(args)})"

    def recalc(e=None):
        try:
            L     = float(cut_input.value)
            v     = float(vline_input.value)
            vmax  = float(vmax_input.value)
            a     = float(amax_input.value)
            tsync = float(tsync_input.value)
            sf    = float(safety_input.value)
            link_pos = float(link_pos_input.value or 0)
            base_dist = float(base_dist_input.value or 0)
        except (TypeError, ValueError):
            warning_text.value = "Invalid inputs: enter numeric values for the shear calculator."
            _apply_warning_severity("error")
            code_output.value = ""
            page.update()
            return

        if L <= 0 or v < 0 or vmax <= 0 or a <= 0 or tsync < 0 or sf <= 0:
            warning_text.value = "Invalid inputs: cut, max speed, accel, and safety must be > 0; MAX line speed and sync time must be >= 0"
            _apply_warning_severity("error")
            code_output.value = ""
            page.update()
            return

        for k, val in [("cut", L), ("vline", v), ("vmax", vmax), ("amax", a),
                       ("tsync", tsync), ("safety", sf), ("link_pos", link_pos),
                       ("base_dist", base_dist)]:
            calc_settings[k] = val
        calc_settings["profile"] = profile_dropdown.value
        calc_settings["start_mode"] = start_dropdown.value
        calc_settings["link_source"] = source_dropdown.value
        calc_settings["direction_mode"] = direction_dropdown.value
        calc_settings["repeat_mode"] = repeat_dropdown.value
        calc_settings["use_base_dist"] = bool(base_dist_checkbox.value)
        refresh_conveyor_speed_limit(v)

        # Shear (slave) distances
        accel_dist = (v * v) / (2 * a) * sf
        decel_dist = accel_dist
        sync_dist  = v * (tsync / 1000.0)
        stroke     = accel_dist + sync_dist + decel_dist

        # Link (master) distances
        accel_link = 2 * accel_dist     # Rule 1: accel ramp uses 2x shear travel
        decel_link = 2 * decel_dist     # Rule 1 mirror
        sync_link  = sync_dist          # Rule 2: matched speed = equal distances
        ret_link   = L - (accel_link + sync_link + decel_link)
        ret_ad     = ret_link / 4 if ret_link > 0 else 0
        if ret_link > 0:
            v_retract_peak = (4.0 / 3.0) * v * (stroke / ret_link)
        else:
            v_retract_peak = float("inf")

        result_labels["stroke"].value = f"{stroke:.2f} mm"
        result_labels["acc"].value    = f"{accel_link:.2f} mm"
        result_labels["dec"].value    = f"{decel_link:.2f} mm"
        result_labels["track"].value  = f"{sync_link:.2f} mm"
        result_labels["ret"].value    = f"{ret_link:.2f} mm"
        if ret_link > 0:
            result_labels["vpeak"].value = f"{fmt_speed(v_retract_peak)} mm/s"
            result_labels["vpeak"].color = ERROR_COLOR if v_retract_peak > vmax else SUCCESS_COLOR
        else:
            result_labels["vpeak"].value = "—"
            result_labels["vpeak"].color = ERROR_COLOR

        profile = profile_dropdown.value or "trapezoid"
        profile_canvas.shapes = build_velocity_profile_shapes(
            accel_link, sync_link, decel_link, ret_link, profile
        )

        start_mode = start_dropdown.value or "immediate"
        link_source = source_dropdown.value or "mpos"
        direction_mode = direction_dropdown.value or "any"
        repeat_mode = repeat_dropdown.value or "program_loop"
        use_base_dist = bool(base_dist_checkbox.value)
        link_options = build_link_options(profile, start_mode, link_source, direction_mode, repeat_mode)
        follow_options = build_link_options(profile, "immediate", link_source, direction_mode, repeat_mode)

        profile_labels = {
            "trapezoid": "Trapezoidal",
            "sine": "Sine S",
            "power9": "Power 9",
            "power7": "Power 7",
            "power5": "Power 5",
            "linear_s": "Linear",
        }
        start_labels = {
            "immediate": "Immediate",
            "mark": "MARK",
            "absolute": f"Abs {link_pos:g}",
            "markb": "MARKB",
            "rmark": f"R_MARK {link_pos:g}",
        }
        result_labels["options"].value = str(link_options)
        result_labels["profile"].value = profile_labels.get(profile, profile)
        result_labels["start"].value = start_labels.get(start_mode, start_mode)
        result_labels["base"].value = f"{base_dist:.2f} mm" if use_base_dist else "Off"

        warnings = []
        if v > vmax:
            warnings.append(f"✗ MAX line speed ({v:g}) exceeds shear max speed ({vmax:g}) — cannot match")
        if ret_link < 0:
            warnings.append("✗ Cut length too short — accel+sync+decel exceeds cut length")
        elif v_retract_peak > vmax:
            warnings.append(f"✗ Retract peak speed {fmt_speed(v_retract_peak)} mm/s exceeds shear max {vmax:g}")
        elif ret_link < accel_link * 0.5:
            warnings.append("⚠ Tight retract — shear must return during short dwell")
        for label, l_dist, l_acc, l_dec in [
            ("Accel", accel_link, accel_link, 0),
            ("Track", sync_link, 0, 0),
            ("Decel", decel_link, 0, decel_link),
            ("Retract", ret_link, ret_ad, ret_ad),
        ]:
            if l_dist > 0 and l_acc + l_dec > l_dist:
                warnings.append(f"⚠ {label} accel+decel exceeds link distance; controller will scale ramps")
        if start_mode in ("absolute", "rmark") and link_pos < 0:
            warnings.append("✗ Link position/channel must be >= 0 for selected start trigger")
        if start_mode == "rmark" and int(link_pos) != link_pos:
            warnings.append("✗ R_MARK channel must be a whole number")
        if use_base_dist and base_dist < 0:
            warnings.append("✗ Base distance must be >= 0")
        if start_mode != "immediate":
            warnings.append("⚠ Start trigger is applied to the first acceleration MOVELINK only")
        if repeat_mode == "movelink_repeat":
            warnings.append("⚠ MOVELINK repeat bit is intended for simple repeating links; verify multi-phase shear behavior")

        if not warnings:
            warning_text.value = "All checks pass"
            _apply_warning_severity("ok")
        elif any(w.startswith("✗") for w in warnings):
            warning_text.value = "  |  ".join(warnings)
            _apply_warning_severity("error")
        else:
            warning_text.value = "  |  ".join(warnings)
            _apply_warning_severity("warning")

        try:
            link_ax  = int(axis_m_dropdown.value or "0")
            shear_ax = int(axis_s_dropdown.value or "1")
            cutter_output = int(cutter_output_input.value or "8")
        except ValueError:
            link_ax, shear_ax, cutter_output = 0, 1, 8

        review_text.value = (
            f"Review before running: material/encoder Axis {link_ax}, shear carriage Axis {shear_ax}, "
            f"knife OP {cutter_output}, profile {profile_labels.get(profile, profile)}, "
            f"start {start_labels.get(start_mode, start_mode)}."
        )

        base_arg = base_dist if use_base_dist else None
        loop_start = "" if repeat_mode == "movelink_repeat" else "WHILE TRUE\n"
        line_prefix = "" if repeat_mode == "movelink_repeat" else "    "
        loop_end = "" if repeat_mode == "movelink_repeat" else "WEND\n"

        code_output.value = (
            f"shear_ax  = {shear_ax}\n"
            f"link_ax   = {link_ax}\n"
            f"cutter_op = {cutter_output}\n"
            f"link_options = {link_options}\n"
            f"link_pos = {link_pos:.3f}\n"
            f"\n"
            f"BASE(shear_ax)\n"
            f"SERVO = ON\n"
            f"SPEED=100\n"
            f"MOVEABS(0)\n"
            f"WAIT IDLE\n"
            f"DEFPOS(0)\n"
            f"\n"
            f"{loop_start}"
            f"{line_prefix}' Accel to MAX line speed\n"
            f"{line_prefix}{format_movelink(accel_dist, accel_link, accel_link, 0, link_options, link_pos, base_arg)}\n"
            f"{line_prefix}WAIT LOADED\n"
            f"\n"
            f"{line_prefix}' Sync at matched speed (cut happens here)\n"
            f"{line_prefix}{format_movelink(sync_dist, sync_link, 0, 0, follow_options, 0, base_arg)}\n"
            f"{line_prefix}WAIT LOADED\n"
            f"{line_prefix}OP(cutter_op, ON)\n"
            f"\n"
            f"{line_prefix}' Decel to stop (cutter is now clear)\n"
            f"{line_prefix}{format_movelink(decel_dist, decel_link, 0, decel_link, follow_options, 0, base_arg)}\n"
            f"{line_prefix}WAIT LOADED\n"
            f"{line_prefix}OP(cutter_op, OFF)\n"
            f"\n"
            f"{line_prefix}' Retract carriage to home\n"
            f"{line_prefix}{format_movelink(-stroke, ret_link, ret_ad, ret_ad, follow_options, 0, base_arg)}\n"
            f"{line_prefix}WAIT LOADED\n"
            f"{loop_end}"
        )
        page.update()

    for inp in (cut_input, vline_input, vmax_input, amax_input, tsync_input, safety_input):
        inp.on_change = recalc
        inp.on_blur = save_calc_settings

    for inp in (link_pos_input, base_dist_input):
        inp.on_change = recalc
        inp.on_blur = save_calc_settings

    def recalc_and_save(e=None):
        recalc(e)
        save_calc_settings(e)

    for dd in (profile_dropdown, start_dropdown, source_dropdown, direction_dropdown, repeat_dropdown):
        dd.on_change = recalc_and_save
        dd.on_select = recalc_and_save

    base_dist_checkbox.on_change = recalc_and_save

    def copy_code(e):
        text = code_output.value
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 2
        raw = text.encode("utf-16-le") + b"\x00\x00"
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        k32.GlobalAlloc.restype  = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype   = ctypes.c_void_p
        k32.GlobalLock.argtypes  = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype  = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        u32.OpenClipboard(0)
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, raw, len(raw))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
        u32.CloseClipboard()
        status_text.value = "Program copied to clipboard"
        status_text.color = SUCCESS_COLOR
        show_snack("Program copied to clipboard.", "success")
        page.update()

    copy_btn_shear = ft.FilledButton(
        "Copy program", icon=ft.Icons.CONTENT_COPY, on_click=copy_code,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        height=38,
        tooltip=CALC_TOOLTIPS["copy"],
    )

    axis_assignment_cluster = control_cluster(
        "Axis & knife assignment",
        [axis_m_dropdown, axis_s_dropdown, cutter_output_input],
        icon=ft.Icons.ACCOUNT_TREE,
        col={"xs": 12},
    )

    shear_calc_panel_height = 1000

    shear_params_panel = ft.Container(
        content=ft.Column([
            section_header("Flying Shear MOVELINK Calculator", "Shape the linked move and validate machine limits", ft.Icons.CALCULATE),
            axis_assignment_cluster,
            ft.Row([cut_input, vline_input, vmax_input, amax_input, tsync_input, safety_input],
                   wrap=True, spacing=15, run_spacing=12),
            ft.Row([
                profile_dropdown,
                start_dropdown,
                link_pos_input,
                source_dropdown,
                direction_dropdown,
                repeat_dropdown,
                base_dist_checkbox,
                base_dist_input,
            ], wrap=True, spacing=15, run_spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INSIGHTS, size=14, color=MUTED_TEXT),
                            ft.Text(
                                "COMPUTED METRICS",
                                size=10,
                                color=MUTED_TEXT,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            result_card("Stroke needed", "stroke"),
                            result_card("Retract peak speed", "vpeak"),
                        ],
                        wrap=True,
                        spacing=10,
                        run_spacing=10,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            phase_bar,
            warning_banner,
            review_text,
            ft.Text("Material axis = MOVELINK link axis. Shear axis = generated BASIC BASE axis.",
                    size=12, color=ft.Colors.GREY_400),
        ], spacing=14, scroll=ft.ScrollMode.AUTO),
        bgcolor=PANEL_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=16,
        height=shear_calc_panel_height,
        col={"xs": 12, "xl": 6},
    )

    trio_basic_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                section_header("Trio BASIC Program", "Generated controller code", ft.Icons.CODE),
                ft.Container(expand=True),
                copy_btn_shear,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            code_output,
        ], expand=True, spacing=12),
        bgcolor=PANEL_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=16,
        height=shear_calc_panel_height,
        col={"xs": 12, "xl": 6},
    )

    shear_calc_container = ft.ResponsiveRow(
        [shear_params_panel, trio_basic_panel],
        columns=12,
        spacing=18,
        run_spacing=18,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    # === MOVELINK Math Help ===
    def help_text(value, size=13, color=TEXT_COLOR, weight=None, selectable=True):
        return ft.Text(
            value,
            size=size,
            color=color,
            weight=weight,
            selectable=selectable,
        )

    def help_card(title, controls, icon=None, col=None):
        heading = [
            ft.Row(
                [
                    ft.Icon(icon, size=18, color=ft.Colors.CYAN_200) if icon else ft.Container(width=0),
                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        return ft.Container(
            content=ft.Column(heading + controls, spacing=10),
            bgcolor=PANEL_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=16,
            col=col or {"xs": 12},
        )

    def formula_block(lines):
        return ft.Container(
            content=ft.Column(
                [ft.Text(line, size=13, color=ft.Colors.GREEN_200, font_family="Consolas", selectable=True) for line in lines],
                spacing=5,
            ),
            bgcolor=DARKER_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=12,
        )

    def mini_table(headers, rows, widths):
        table_rows = [
            ft.Row(
                [
                    ft.Text(headers[i], width=widths[i], size=12, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD)
                    for i in range(len(headers))
                ],
                spacing=8,
            )
        ]
        for row in rows:
            table_rows.append(
                ft.Row(
                    [
                        ft.Text(str(row[i]), width=widths[i], size=12, color=TEXT_COLOR, selectable=True)
                        for i in range(len(row))
                    ],
                    spacing=8,
                )
            )
        return ft.Container(
            content=ft.Column(table_rows, spacing=6),
            bgcolor=DARKER_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=12,
        )

    def build_help_phase_shapes():
        width = 700
        height = 260
        left = 70
        right = 28
        top = 26
        baseline = 182
        peak = 58
        plot_end = width - right
        axis_paint = canvas_paint("#b8a80f", 3)
        grid_paint = canvas_paint("#46505a", 1, dash=[4, 5])
        red_paint = canvas_paint("#d24a35", 4.5)
        blue_paint = canvas_paint("#4fc3f7", 4)
        green_paint = canvas_paint("#81c784", 4)
        amber_paint = canvas_paint("#ffb74d", 4)
        label_color = ft.Colors.GREY_300

        x0 = left
        x1 = 200
        x2 = 390
        x3 = 520
        x4 = plot_end
        shapes = [
            cv.Rect(0, 0, width, height, border_radius=ft.BorderRadius.all(8), paint=ft.Paint(color=DARKER_BG, style=ft.PaintingStyle.FILL)),
            cv.Line(left, baseline, plot_end + 10, baseline, paint=axis_paint),
            cv.Line(left, baseline, left, top, paint=axis_paint),
            cv.Line(plot_end + 10, baseline, plot_end, baseline - 6, paint=axis_paint),
            cv.Line(plot_end + 10, baseline, plot_end, baseline + 6, paint=axis_paint),
            cv.Line(left, top, left - 6, top + 10, paint=axis_paint),
            cv.Line(left, top, left + 6, top + 10, paint=axis_paint),
        ]
        for x in (x1, x2, x3):
            shapes.append(cv.Line(x, top + 8, x, baseline + 10, paint=grid_paint))
        shapes.extend(
            [
                cv.Path(
                    elements=[
                        cv.Path.MoveTo(x0, baseline),
                        cv.Path.LineTo(x1, peak),
                        cv.Path.LineTo(x2, peak),
                        cv.Path.LineTo(x3, baseline),
                    ],
                    paint=red_paint,
                ),
                cv.Line(x3 + 8, baseline - 22, x4 - 8, baseline - 22, paint=blue_paint),
                cv.Line(x4 - 8, baseline - 22, x4 - 20, baseline - 30, paint=blue_paint),
                cv.Line(x4 - 8, baseline - 22, x4 - 20, baseline - 14, paint=blue_paint),
                cv.Line(x0, baseline + 34, x1, baseline + 34, paint=green_paint),
                cv.Line(x1, baseline + 45, x2, baseline + 45, paint=green_paint),
                cv.Line(x2, baseline + 56, x3, baseline + 56, paint=green_paint),
                cv.Line(x3, baseline + 67, x4, baseline + 67, paint=amber_paint),
            ]
        )
        add_profile_text(shapes, 26, 104, "slave velocity", size=14, color=ft.Colors.WHITE, rotate=-1.5708)
        add_profile_text(shapes, plot_end - 54, baseline + 45, "master distance", size=13, color=ft.Colors.WHITE, max_width=150)
        add_profile_text(shapes, (x0 + x1) / 2, peak - 28, "Accel", size=16, color=ft.Colors.WHITE)
        add_profile_text(shapes, (x1 + x2) / 2, peak - 28, "Sync / cut", size=16, color=ft.Colors.WHITE)
        add_profile_text(shapes, (x2 + x3) / 2, peak - 28, "Decel", size=16, color=ft.Colors.WHITE)
        add_profile_text(shapes, (x3 + x4) / 2, baseline - 56, "Retract dwell", size=16, color=ft.Colors.WHITE)
        add_profile_text(shapes, (x0 + x1) / 2, baseline + 22, "link_acc = 2 x accel_dist", size=11, color=label_color, max_width=145)
        add_profile_text(shapes, (x1 + x2) / 2, baseline + 22, "link_dist = sync_dist", size=11, color=label_color, max_width=160)
        add_profile_text(shapes, (x2 + x3) / 2, baseline + 22, "link_dec = 2 x decel_dist", size=11, color=label_color, max_width=140)
        add_profile_text(shapes, (x3 + x4) / 2, baseline + 22, "remaining cut length", size=11, color=label_color, max_width=140)
        return shapes

    def build_help_scurve_shapes():
        width = 700
        height = 230
        left = 64
        right = 30
        top = 26
        baseline = 168
        peak = 52
        plot_end = width - right
        axis_paint = canvas_paint("#b8a80f", 3)
        trap_paint = canvas_paint("#ef5350", 3.5)
        s_paint = canvas_paint("#4fc3f7", 4)
        grid_paint = canvas_paint("#46505a", 1, dash=[4, 5])
        shapes = [
            cv.Rect(0, 0, width, height, border_radius=ft.BorderRadius.all(8), paint=ft.Paint(color=DARKER_BG, style=ft.PaintingStyle.FILL)),
            cv.Line(left, baseline, plot_end + 10, baseline, paint=axis_paint),
            cv.Line(left, baseline, left, top, paint=axis_paint),
            cv.Line(plot_end + 10, baseline, plot_end, baseline - 6, paint=axis_paint),
            cv.Line(plot_end + 10, baseline, plot_end, baseline + 6, paint=axis_paint),
            cv.Line(left, peak, plot_end - 4, peak, paint=grid_paint),
        ]
        x0 = left + 12
        x1 = 224
        x2 = 472
        x3 = plot_end - 14
        shapes.append(cv.Path(elements=[cv.Path.MoveTo(x0, baseline), cv.Path.LineTo(x1, peak), cv.Path.LineTo(x2, peak), cv.Path.LineTo(x3, baseline)], paint=trap_paint))
        shapes.append(
            cv.Path(
                elements=[
                    cv.Path.MoveTo(x0, baseline),
                    cv.Path.CubicTo(x0 + 55, baseline, x1 - 55, peak, x1, peak),
                    cv.Path.LineTo(x2, peak),
                    cv.Path.CubicTo(x2 + 55, peak, x3 - 55, baseline, x3, baseline),
                ],
                paint=s_paint,
            )
        )
        add_profile_text(shapes, 28, 98, "velocity", size=14, color=ft.Colors.WHITE, rotate=-1.5708)
        add_profile_text(shapes, plot_end - 54, baseline + 32, "link distance", size=13, color=ft.Colors.WHITE, max_width=140)
        add_profile_text(shapes, 178, 30, "Trapezoid: constant acceleration", size=13, color=ft.Colors.RED_200, max_width=220)
        add_profile_text(shapes, 494, 30, "S-curve: smoother jerk, higher peak accel", size=13, color=ft.Colors.CYAN_200, max_width=250)
        return shapes

    phase_help_canvas = cv.Canvas(width=700, height=260, shapes=build_help_phase_shapes())
    scurve_help_canvas = cv.Canvas(width=700, height=230, shapes=build_help_scurve_shapes())

    example_inputs = {
        "cut": 160.0,
        "v": 500.0,
        "a": 5000.0,
        "sf": 1.5,
        "tsync": 40.0,
    }
    ex_accel_dist = (example_inputs["v"] * example_inputs["v"]) / (2 * example_inputs["a"]) * example_inputs["sf"]
    ex_sync_dist = example_inputs["v"] * (example_inputs["tsync"] / 1000.0)
    ex_stroke = ex_accel_dist + ex_sync_dist + ex_accel_dist
    ex_accel_link = 2 * ex_accel_dist
    ex_decel_link = ex_accel_link
    ex_ret_link = example_inputs["cut"] - (ex_accel_link + ex_sync_dist + ex_decel_link)
    ex_retract_peak = (4.0 / 3.0) * example_inputs["v"] * (ex_stroke / ex_ret_link)

    movelink_help_list = ft.ListView(
        controls=[
                section_header("MOVELINK Math Help", "The equations behind the generated flying-shear program", ft.Icons.FUNCTIONS),
                ft.ResponsiveRow(
                    [
                        help_card(
                            "Command Shape",
                            [
                                help_text("MOVELINK(distance, link_dist, link_acc, link_dec, link_axis[, link_options[, link_pos[, base_dist]]])"),
                                help_text("distance is the slave/base-axis travel. link_dist is the positive measured master-axis travel that drives it."),
                                help_text("link_acc and link_dec are master-axis distances over which the slave accelerates and decelerates. If link_acc + link_dec is larger than link_dist, the controller scales them down proportionally."),
                                formula_block(
                                    [
                                        "instantaneous ratio = slave_velocity / master_velocity",
                                        "slave distance = area under ratio curve over master distance",
                                        "matched speed for a flying shear means ratio = 1 during the cut",
                                    ]
                                ),
                            ],
                            icon=ft.Icons.CODE,
                            col={"xs": 12, "xl": 6},
                        ),
                        help_card(
                            "Flying Shear Core Rules",
                            [
                                help_text("The app follows the same two practical rules shown in MOVELINK.md example 1."),
                                formula_block(
                                    [
                                        "accel_dist = v_line^2 / (2 * a_shear) * safety_factor",
                                        "decel_dist = accel_dist",
                                        "sync_dist = v_line * sync_time_seconds",
                                        "stroke = accel_dist + sync_dist + decel_dist",
                                        "accel_link = 2 * accel_dist",
                                        "sync_link = sync_dist",
                                        "decel_link = 2 * decel_dist",
                                        "return_link = cut_length - accel_link - sync_link - decel_link",
                                    ]
                                ),
                                help_text("Why 2x? During a linear ramp from zero to matched speed, average shear speed is half line speed. To travel X on the shear while the master runs at line speed, the master must travel 2X."),
                            ],
                            icon=ft.Icons.CALCULATE,
                            col={"xs": 12, "xl": 6},
                        ),
                    ],
                    columns=12,
                    spacing=18,
                    run_spacing=18,
                ),
                ft.ResponsiveRow(
                    [
                        help_card(
                            "Phase Graph",
                            [
                                ft.Container(
                                    content=phase_help_canvas,
                                    border=ft.Border.all(1, BORDER_COLOR),
                                    border_radius=8,
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                ),
                                help_text("The red line is shear velocity against master distance. The colored bars under the axis show the link distances consumed by each generated MOVELINK command."),
                            ],
                            icon=ft.Icons.SHOW_CHART,
                            col={"xs": 12, "xl": 6},
                        ),
                        help_card(
                            "Worked Example",
                            [
                                help_text("Example inputs: cut length 160 mm, line speed 500 mm/s, shear accel 5000 mm/s2, safety 1.5, sync time 40 ms."),
                                formula_block(
                                    [
                                        f"accel_dist = 500^2 / (2 * 5000) * 1.5 = {ex_accel_dist:.2f} mm",
                                        f"sync_dist = 500 * 0.040 = {ex_sync_dist:.2f} mm",
                                        f"stroke = {ex_accel_dist:.2f} + {ex_sync_dist:.2f} + {ex_accel_dist:.2f} = {ex_stroke:.2f} mm",
                                        f"accel_link = decel_link = 2 * {ex_accel_dist:.2f} = {ex_accel_link:.2f} mm",
                                        f"return_link = 160 - {ex_accel_link:.2f} - {ex_sync_dist:.2f} - {ex_decel_link:.2f} = {ex_ret_link:.2f} mm",
                                        f"estimated retract peak = 4/3 * 500 * ({ex_stroke:.2f} / {ex_ret_link:.2f}) = {ex_retract_peak:.1f} mm/s",
                                    ]
                                ),
                                mini_table(
                                    ["Phase", "MOVELINK distance", "link_dist", "link_acc", "link_dec"],
                                    [
                                        ("Accel", f"{ex_accel_dist:.2f}", f"{ex_accel_link:.2f}", f"{ex_accel_link:.2f}", "0"),
                                        ("Sync", f"{ex_sync_dist:.2f}", f"{ex_sync_dist:.2f}", "0", "0"),
                                        ("Decel", f"{ex_accel_dist:.2f}", f"{ex_decel_link:.2f}", "0", f"{ex_decel_link:.2f}"),
                                        ("Retract", f"{-ex_stroke:.2f}", f"{ex_ret_link:.2f}", f"{ex_ret_link / 4:.2f}", f"{ex_ret_link / 4:.2f}"),
                                    ],
                                    [88, 132, 92, 92, 92],
                                ),
                            ],
                            icon=ft.Icons.ARTICLE,
                            col={"xs": 12, "xl": 6},
                        ),
                    ],
                    columns=12,
                    spacing=18,
                    run_spacing=18,
                ),
                ft.ResponsiveRow(
                    [
                        help_card(
                            "Profiles And Jerk",
                            [
                                ft.Container(
                                    content=scurve_help_canvas,
                                    border=ft.Border.all(1, BORDER_COLOR),
                                    border_radius=8,
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                ),
                                help_text("Bit 4 changes accel/decel from a trapezoidal speed profile to an S-ramp profile. Bits 10..12 select the S-ramp type."),
                                mini_table(
                                    ["Profile", "Bits 10..12", "Peak accel note"],
                                    [
                                        ("Sine", "0", "about 1.55x trapezoid"),
                                        ("Power 9", "1", "about 2.42x trapezoid"),
                                        ("Power 7", "2", "about 2.16x trapezoid"),
                                        ("Power 5", "3", "about 1.86x trapezoid"),
                                        ("Linear ramp", "4", "linear ramp mode"),
                                    ],
                                    [110, 92, 190],
                                ),
                                help_text("S-curves reduce jerk at the transitions, but the peak acceleration is higher for the same link_acc/link_dec distance. Keep that in mind when comparing the calculator's acceleration setting to servo limits."),
                            ],
                            icon=ft.Icons.TIMELINE,
                            col={"xs": 12, "xl": 6},
                        ),
                        help_card(
                            "link_options Bits",
                            [
                                help_text("The calculator builds one decimal link_options value by adding the selected bit values."),
                                mini_table(
                                    ["Bit", "Value", "Meaning used by this app"],
                                    [
                                        ("0", "1", "start on MARK"),
                                        ("1", "2", "start at absolute link_pos"),
                                        ("2", "4", "automatic bi-directional MOVELINK repeat"),
                                        ("4", "16", "enable S-ramp / curved profile"),
                                        ("5", "32", "active only for positive master movement"),
                                        ("8", "256", "start on MARKB"),
                                        ("9", "512", "start on R_MARK channel in link_pos"),
                                        ("10..12", "1024..4096", "S-ramp mode number shifted left by 10"),
                                        ("13", "8192", "follow master DPOS instead of MPOS"),
                                        ("14", "16384", "positive threshold mode"),
                                    ],
                                    [70, 90, 320],
                                ),
                                formula_block(
                                    [
                                        "Power 5 profile only: 16 + (3 << 10) = 3088",
                                        "Power 5 + MARK start + DPOS = 3088 + 1 + 8192 = 11281",
                                    ]
                                ),
                            ],
                            icon=ft.Icons.TOGGLE_ON,
                            col={"xs": 12, "xl": 6},
                        ),
                    ],
                    columns=12,
                    spacing=18,
                    run_spacing=18,
                ),
                ft.ResponsiveRow(
                    [
                        help_card(
                            "Base Distance",
                            [
                                help_text("Firmware V2.0253 and newer allow an eighth MOVELINK parameter: base_dist."),
                                help_text("base_dist is part of the total distance parameter. It represents travel at the base ratio before/after the shaped profile contribution, so the profile can start and end at a nonzero ratio."),
                                formula_block(
                                    [
                                        "MOVELINK(total_slave_distance, link_dist, link_acc, link_dec, link_axis, options, link_pos, base_dist)",
                                        "profile_extra_distance = total_slave_distance - base_dist",
                                    ]
                                ),
                                help_text("MOVELINK.md notes that parameters 6 and 7 must be present when base_dist is used, even when they are zero. MOVELINK_MODIFY cannot be used with base distance."),
                            ],
                            icon=ft.Icons.LAYERS,
                            col={"xs": 12, "xl": 6},
                        ),
                        help_card(
                            "Practical Checks",
                            [
                                help_text("The calculator warns when the shear cannot match the requested line speed, when the phase distances are longer than the cut length, or when retract speed is too high."),
                                formula_block(
                                    [
                                        "must have: v_line <= shear_max_speed",
                                        "must have: return_link > 0",
                                        "approx retract_peak = 4/3 * v_line * stroke / return_link",
                                        "controller scaling risk: link_acc + link_dec > link_dist",
                                    ]
                                ),
                                help_text("The retract estimate assumes a symmetric triangular/trapezoid style return over the remaining master distance. Treat it as a sizing warning, then validate on the actual machine."),
                            ],
                            icon=ft.Icons.WARNING_AMBER,
                            col={"xs": 12, "xl": 6},
                        ),
                    ],
                    columns=12,
                    spacing=18,
                    run_spacing=18,
                ),
                help_card(
                    "Notes From MOVELINK.md",
                    [
                        help_text("MOVELINK links slave motion to the measured position of another axis by default. The app exposes DPOS mode with option bit 13."),
                        help_text("link_dist is always positive, even if the link axis is moving in the opposite direction. The generated retract command uses a negative slave distance but keeps link_dist positive."),
                        help_text("The original flying-shear example splits acceleration and synchronized motion so the program can switch the cutter output at a known point in the move buffer. This app keeps the same idea: accel, sync/cut, decel, then retract."),
                        help_text("For a pure exact-ratio gearbox, MOVELINK can also be used with zero accel/decel and repeat bit 2. The flying-shear program loop is usually easier to reason about for multi-phase cutting."),
                    ],
                    icon=ft.Icons.MENU_BOOK,
                ),
        ],
        spacing=18,
        padding=20,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    recalc()

    # ============================================================
    # === Rotary Knife Cam Table Generator =======================
    # ============================================================
    cam_settings = settings.setdefault("cam_calc", {})

    def cam_set(k, v):
        cam_settings[k] = v
        save_settings(settings)

    CAM_TOOLTIPS = {
        "cut":        "Material distance per cut (mm of master). The cam cycle repeats every cut_length of link travel.",
        "drum_dia":   "Knife drum outside diameter. Used to compute drum circumference and tangential velocity.",
        "n_knives":   "Number of knives evenly spaced around the drum. Each cut consumes 360°/n_knives of drum rotation.",
        "cut_window": "Angular width of the constant-tangential-match zone (the 'pure cut' window) on the drum.",
        "cpr":        "Drum axis encoder counts per full revolution. CAMBOX TABLE values are in encoder counts, not user units.",
        "n_points":   "Number of points in the cam table. Resolution = (360°/n_knives) / n_points.",
        "blend":      "Fraction of the outside zone used for sinusoidal accel/decel blends. 0.0 = step (rough), 1.0 = pure sinusoid (smooth).",
        "vline":      "Line speed for diagnostic peak-RPS and peak-angular-accel calculations. Does not affect the table itself.",
        "table_start":"Starting TABLE() index where the cam profile is loaded into controller memory.",
        "R":          "Natural ratio = (drum_segment_per_cut) / cut_length. R=1 → constant 1:1, R<1 → slow cut/fast outside, R>1 → fast cut/slow outside.",
        "cut_zone":   "Master/material distance during the cut window. This is the knife's horizontal chord travel, not drum arc length.",
        "rps_cut":    "Drum revolutions per second at cut center. Cut-window edges are higher by the cosine correction.",
        "rps_out":    "Drum revolutions per second in the slow/fast zone outside the cut window. Check against drum motor max RPM.",
        "cosine_corr":"Velocity boost at the cut-window edges. The drum speeds up by 1/cos(alpha) so the knife's horizontal speed still matches the material.",
        "peak_accel": "Peak drum angular acceleration from the corrected cut profile or sinusoidal blend transitions. Check against drum motor torque/inertia limits.",
        "table_res":  "Angular resolution of the cam table on the drum.",
        "code":       "Generated Trio BASIC TABLE() loader and CAMBOX() call. Copy this into the controller.",
    }

    def make_cam_input(label, key, default, width=160, suffix=None):
        return ft.TextField(
            label=label, value=str(cam_settings.get(key, default)),
            width=width, bgcolor=DARKER_BG, color=TEXT_COLOR,
            border_color=BORDER_COLOR, focused_border_color=ACCENT_COLOR,
            keyboard_type=ft.KeyboardType.NUMBER, text_align=ft.TextAlign.RIGHT,
            suffix=suffix, text_size=13,
            tooltip=CAM_TOOLTIPS.get(key),
        )

    cam_cut_input        = make_cam_input("Cut length",        "cut",         100,   suffix="mm")
    cam_drum_dia_input   = make_cam_input("Drum diameter",     "drum_dia",    200,   suffix="mm")
    cam_n_knives_input   = make_cam_input("Number of knives",  "n_knives",    1,     width=140)
    cam_cut_window_input = make_cam_input("Cut window",        "cut_window",  30,    width=140, suffix="°")
    cam_cpr_input        = make_cam_input("Encoder cnts/rev",  "cpr",         10000, width=160)
    cam_n_points_input   = make_cam_input("Table points",      "n_points",    720,   width=140)
    cam_blend_input      = make_cam_input("Blend fraction",    "blend",       0.4,   width=140)
    cam_vline_input      = make_cam_input("Line speed (diag.)", "vline",      500,   width=170, suffix="mm/s")
    cam_table_start_input = make_cam_input("TABLE start idx",  "table_start", 1000,  width=160)

    cam_result_labels = {
        k: ft.Text("---", size=18, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD)
        for k in ("R", "cut_zone", "rps_cut", "rps_out", "cosine_corr", "peak_accel", "table_res")
    }
    cam_warning_text = ft.Text("", size=13, color=ft.Colors.AMBER_300)
    cam_review_text  = ft.Text("", size=12, color=ft.Colors.GREY_300)

    def cam_result_card(label, key):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=12, color=ft.Colors.GREY_400),
                cam_result_labels[key],
            ], spacing=4),
            bgcolor=PANEL_BG, border_radius=8, padding=12,
            border=ft.Border.all(1, BORDER_COLOR), width=180,
            tooltip=CAM_TOOLTIPS.get(key),
        )

    cam_profile_canvas = cv.Canvas(width=660, height=240, shapes=[])
    cam_code_output = ft.TextField(
        value="", read_only=True, multiline=True, min_lines=29, max_lines=45,
        bgcolor=DARKER_BG, color=ft.Colors.GREEN_200,
        border_color=BORDER_COLOR, focused_border_color=ACCENT_COLOR,
        text_style=ft.TextStyle(font_family="Consolas", size=12),
        expand=True, tooltip=CAM_TOOLTIPS["code"],
    )

    # --- Cam table math (1/cos cut correction + sinusoidal blend) ---
    def generate_rotary_knife_cam_table(cut_length_mm, drum_diameter_mm, n_knives,
                                         cut_window_deg, encoder_counts_per_rev,
                                         n_points=720, blend_fraction=0.4,
                                         line_speed_mm_s=500):
        drum_radius = drum_diameter_mm / 2.0
        drum_circumference = math.pi * drum_diameter_mm
        cut_segment_counts = encoder_counts_per_rev / n_knives
        alpha_max = math.radians(cut_window_deg / 2.0)

        if cut_window_deg >= 360.0 / n_knives:
            raise ValueError(f"Cut window {cut_window_deg}° too large; must be < {360.0/n_knives:.1f}° for {n_knives}-knife drum")
        if alpha_max >= math.pi / 2:
            raise ValueError("Cut window too wide: half-window angle must be < 90° for cosine correction")

        cut_zone_master_mm = 2.0 * drum_radius * math.sin(alpha_max)
        w_cut = cut_zone_master_mm / cut_length_mm
        if w_cut >= 1.0:
            raise ValueError(f"Cut zone ({cut_zone_master_mm:.2f} mm) exceeds cut length ({cut_length_mm} mm)")
        max_x_offset = (cut_length_mm * w_cut) / 2.0
        if max_x_offset >= drum_radius:
            raise ValueError(
                f"Cut window too wide for drum radius: would require "
                f"knife horizontal travel of {max_x_offset:.2f} mm exceeding "
                f"drum radius {drum_radius:.2f} mm. Reduce cut_window_deg or "
                f"increase drum_diameter."
            )

        w_blend = blend_fraction * (1.0 - w_cut) / 2.0
        w_outside = 1.0 - w_cut - 2.0 * w_blend
        if w_outside < 0:
            raise ValueError(f"Blend fraction {blend_fraction} too large; reduce or increase cut length")

        R = n_knives * cut_length_mm / drum_circumference
        v_cut = R
        v_cut_at_edge = v_cut / math.cos(alpha_max)
        f_slave_cut = n_knives * cut_window_deg / 360.0
        v_out = (1.0 - f_slave_cut - v_cut_at_edge * w_blend) / (w_outside + w_blend)
        if v_out < 0:
            raise ValueError(f"Outside velocity would be negative ({v_out:.3f}); drum cannot reverse — increase cut_length or reduce drum dia")

        u1 = w_outside / 2.0
        u2 = u1 + w_blend
        u3 = u2 + w_cut
        u4 = u3 + w_blend
        u_cut_center = (u2 + u3) / 2.0

        def velocity(u):
            if u < u1: return v_out
            if u < u2:
                t = (u - u1) / w_blend
                return v_out + (v_cut_at_edge - v_out) * 0.5 * (1.0 - math.cos(math.pi * t))
            if u < u3:
                # Compensate for the knife's circular path so its horizontal
                # velocity component matches the line speed across the cut.
                x = (u - u_cut_center) * cut_length_mm
                raw_ratio = x / drum_radius
                if abs(raw_ratio) > 1.0 + 1e-12:
                    raise ValueError("Cut-window geometry produced an invalid arcsin argument")
                ratio = max(-1.0, min(1.0, raw_ratio))
                alpha = math.asin(ratio)
                return v_cut / math.cos(alpha)
            if u < u4:
                t = (u - u3) / w_blend
                return v_cut_at_edge + (v_out - v_cut_at_edge) * 0.5 * (1.0 - math.cos(math.pi * t))
            return v_out

        n_fine = max(n_points * 8, 8000)
        du_fine = 1.0 / n_fine
        theta_fine = [0.0]
        v_prev = velocity(0.0)
        for i in range(1, n_fine + 1):
            v_curr = velocity(i * du_fine)
            theta_fine.append(theta_fine[-1] + 0.5 * (v_prev + v_curr) * du_fine)
            v_prev = v_curr
        theta_total = theta_fine[-1]
        integration_error = abs(theta_total - 1.0)
        scale = 1.0 / theta_total
        theta_fine = [t * scale for t in theta_fine]

        table_int = []
        for i in range(n_points + 1):
            idx_f = (i / n_points) * n_fine
            idx_lo = int(idx_f)
            idx_hi = min(idx_lo + 1, n_fine)
            frac = idx_f - idx_lo
            theta_norm = theta_fine[idx_lo] * (1 - frac) + theta_fine[idx_hi] * frac
            table_int.append(int(round(theta_norm * cut_segment_counts)))

        line_period_s = cut_length_mm / line_speed_mm_s if line_speed_mm_s > 0 else 1.0
        drum_rps_cut = line_speed_mm_s / drum_circumference if drum_circumference > 0 else 0
        drum_rps_out = v_out / n_knives * line_speed_mm_s / cut_length_mm if cut_length_mm > 0 else 0
        blend_peak_dv_du = abs(v_cut_at_edge - v_out) * math.pi / (2 * w_blend) if w_blend > 0 else 0.0
        cut_peak_dv_du = v_cut * math.sin(alpha_max) / (math.cos(alpha_max) ** 3) * cut_length_mm / drum_radius
        peak_ang_accel = max(blend_peak_dv_du, cut_peak_dv_du) / n_knives / line_period_s ** 2

        diag = {
            "R": R, "cut_zone_master_mm": cut_zone_master_mm,
            "w_cut": w_cut, "w_blend": w_blend, "w_outside": w_outside,
            "v_cut": v_cut, "v_out": v_out,
            "alpha_max_deg": math.degrees(alpha_max),
            "v_cut_at_edge_normalized": v_cut_at_edge,
            "cosine_correction_at_edge": 1.0 / math.cos(alpha_max),
            "drum_radius": drum_radius,
            "drum_circumference": drum_circumference, "cut_segment_counts": cut_segment_counts,
            "drum_rps_cut": drum_rps_cut, "drum_rps_out": drum_rps_out,
            "peak_drum_rps": max(drum_rps_cut, drum_rps_out),
            "peak_ang_accel_rev_s2": peak_ang_accel,
            "table_resolution_deg": (360.0 / n_knives) / n_points,
            "integration_error": integration_error,
        }
        return table_int, diag

    def build_cam_profile_shapes(table_values, diag):
        """Velocity profile: dθ/du vs u, with cut window shaded."""
        width, height = 660, 240
        left, right = 60, 30
        top, bottom = 30, 200
        plot_end = width - right
        plot_w = plot_end - left
        plot_h = bottom - top

        n = len(table_values)
        # Numerical derivative of position in normalized counts/u
        du = 1.0 / (n - 1)
        velocities = []
        for i in range(n):
            if i == 0:
                v = (table_values[1] - table_values[0]) / du
            elif i == n - 1:
                v = (table_values[-1] - table_values[-2]) / du
            else:
                v = (table_values[i+1] - table_values[i-1]) / (2 * du)
            velocities.append(v)
        v_min = min(velocities)
        v_max = max(velocities)
        v_pad = max((v_max - v_min) * 0.1, 1.0)
        v_lo = v_min - v_pad
        v_hi = v_max + v_pad

        def map_x(u): return left + u * plot_w
        def map_y(v): return bottom - (v - v_lo) / (v_hi - v_lo) * plot_h

        axis_paint = canvas_paint("#b8a80f", 2.5)
        grid_paint = canvas_paint("#46505a", 1, dash=[4, 5])
        vel_paint  = canvas_paint("#4fc3f7", 2.5)
        ref_paint  = canvas_paint("#90a4ae", 1.4, dash=[5, 4])
        cut_band_paint = ft.Paint(color="#33d24a35", style=ft.PaintingStyle.FILL)

        shapes = [
            cv.Rect(0, 0, width, height, border_radius=ft.BorderRadius.all(8),
                    paint=ft.Paint(color=DARKER_BG, style=ft.PaintingStyle.FILL)),
        ]

        # Cut window band
        u_cut_start = 0.5 - diag["w_cut"] / 2
        u_cut_end   = 0.5 + diag["w_cut"] / 2
        x_cs = map_x(u_cut_start)
        x_ce = map_x(u_cut_end)
        shapes.append(cv.Rect(x_cs, top, x_ce - x_cs, plot_h, paint=cut_band_paint))

        # Axes
        shapes.extend([
            cv.Line(left, bottom, plot_end, bottom, paint=axis_paint),
            cv.Line(left, bottom, left, top, paint=axis_paint),
        ])

        # Reference lines for v_cut and v_out (in counts/u space)
        v_cut_counts = diag["v_cut"] * diag["cut_segment_counts"]
        v_out_counts = diag["v_out"] * diag["cut_segment_counts"]
        for v_ref, label, label_color in [(v_cut_counts, "v_cut", "#d24a35"),
                                            (v_out_counts, "v_out", "#ffb74d")]:
            y_ref = map_y(v_ref)
            if top <= y_ref <= bottom:
                shapes.append(cv.Line(left, y_ref, plot_end, y_ref, paint=ref_paint))
                add_profile_text(shapes, plot_end - 12, y_ref - 9, label,
                                 size=10, color=label_color, align=ft.Alignment.CENTER_RIGHT)

        # Velocity curve
        elements = [cv.Path.MoveTo(map_x(0), map_y(velocities[0]))]
        for i in range(1, n):
            elements.append(cv.Path.LineTo(map_x(i / (n - 1)), map_y(velocities[i])))
        shapes.append(cv.Path(elements=elements, paint=vel_paint))

        # Labels
        add_profile_text(shapes, 22, (top + bottom) / 2, "drum velocity",
                         size=13, color=ft.Colors.WHITE, rotate=-1.5708)
        add_profile_text(shapes, plot_end - 30, bottom + 18, "master fraction",
                         size=12, color=ft.Colors.WHITE, max_width=120)
        add_profile_text(shapes, (x_cs + x_ce) / 2, top + 12, "cut window",
                         size=12, color="#ffd1c2", max_width=max(60, x_ce - x_cs - 4))
        add_profile_text(shapes, left - 4, bottom + 14, "0", size=10,
                         color=ft.Colors.GREY_300, align=ft.Alignment.CENTER_RIGHT)
        add_profile_text(shapes, plot_end + 4, bottom + 14, "1", size=10,
                         color=ft.Colors.GREY_300, align=ft.Alignment.CENTER_LEFT)
        return shapes

    def emit_cam_basic_program(table_values, diag, cut_length, link_axis,
                                drum_axis, table_start, cutter_op,
                                values_per_line=10):
        n_pts = len(table_values)
        table_end = table_start + n_pts - 1
        lines = []
        lines.append(f"' Rotary knife cam table — {n_pts} pts, "
                     f"{diag['table_resolution_deg']:.4f}°/point on drum")
        lines.append(f"' Drum: {diag['drum_circumference']:.2f} mm circumference, "
                     f"{int(diag['cut_segment_counts'])} counts per cut segment")
        lines.append("' Drum zero: blade at top. Material contact/cut is 180 deg from zero.")
        lines.append(f"' Cut zone: {diag['cut_zone_master_mm']:.2f} mm of material "
                     f"(R={diag['R']:.4f})")
        lines.append(f"' Inside cut window: ratio={diag['v_cut']:.4f} center, "
                     f"{diag['v_cut_at_edge_normalized']:.4f} at edges "
                     f"({diag['cosine_correction_at_edge']:.4f}x cosine correction)")
        lines.append(f"' Outside cut window: ratio={diag['v_out']:.4f}")
        lines.append("")
        lines.append(f"link_ax    = {link_axis}")
        lines.append(f"drum_ax    = {drum_axis}")
        lines.append(f"cut_length = {cut_length:g}")
        lines.append(f"cutter_op  = {cutter_op}")
        lines.append("")
        lines.append("' Load cam table (encoder counts on drum axis)")
        for chunk_start in range(0, n_pts, values_per_line):
            chunk = table_values[chunk_start:chunk_start + values_per_line]
            idx = table_start + chunk_start
            lines.append(f"TABLE({idx}, {', '.join(str(v) for v in chunk)})")
        lines.append("")
        lines.append("BASE(drum_ax)")
        lines.append("SERVO = ON")
        lines.append("' Jog/home the blade to the top before this line; that is drum position 0.")
        lines.append("DEFPOS(0)")
        lines.append("")
        lines.append("' Bit 2 = repeat continuously")
        lines.append(f"CAMBOX({table_start}, {table_end}, 1, cut_length, link_ax, 4)")
        return "\n".join(lines)

    def cam_recalc(e=None):
        try:
            cut_len   = float(cam_cut_input.value)
            drum_dia  = float(cam_drum_dia_input.value)
            n_knives  = int(float(cam_n_knives_input.value))
            cut_win   = float(cam_cut_window_input.value)
            cpr       = int(float(cam_cpr_input.value))
            n_points  = int(float(cam_n_points_input.value))
            blend     = float(cam_blend_input.value)
            vline     = float(cam_vline_input.value)
            table_start = int(float(cam_table_start_input.value))
        except (TypeError, ValueError):
            cam_warning_text.value = "✗ Invalid input — enter numeric values"
            cam_warning_text.color = ERROR_COLOR
            cam_code_output.value = ""
            page.update()
            return

        # Persist
        for k, v in [("cut", cut_len), ("drum_dia", drum_dia), ("n_knives", n_knives),
                     ("cut_window", cut_win), ("cpr", cpr), ("n_points", n_points),
                     ("blend", blend), ("vline", vline), ("table_start", table_start)]:
            cam_settings[k] = v
        save_settings(settings)

        # Bounds
        if cut_len <= 0 or drum_dia <= 0 or n_knives < 1 or cut_win <= 0 \
                or cpr < 100 or n_points < 10 or vline <= 0 or table_start < 0 \
                or blend < 0 or blend > 1:
            cam_warning_text.value = ("✗ Inputs out of range — "
                                       "cut/drum/cpr/vline must be > 0; "
                                       "n_knives ≥ 1; n_points ≥ 10; blend ∈ [0,1]")
            cam_warning_text.color = ERROR_COLOR
            cam_code_output.value = ""
            page.update()
            return

        try:
            table, diag = generate_rotary_knife_cam_table(
                cut_length_mm=cut_len, drum_diameter_mm=drum_dia,
                n_knives=n_knives, cut_window_deg=cut_win,
                encoder_counts_per_rev=cpr, n_points=n_points,
                blend_fraction=blend, line_speed_mm_s=vline,
            )
        except ValueError as ex:
            cam_warning_text.value = f"✗ {ex}"
            cam_warning_text.color = ERROR_COLOR
            cam_code_output.value = ""
            cam_profile_canvas.shapes = []
            for k in cam_result_labels:
                cam_result_labels[k].value = "—"
            page.update()
            return

        # Result cards
        cam_result_labels["R"].value           = f"{diag['R']:.4f}"
        cam_result_labels["cut_zone"].value    = f"{diag['cut_zone_master_mm']:.2f} mm"
        cam_result_labels["rps_cut"].value     = f"{diag['drum_rps_cut']:.3f} rps"
        cam_result_labels["rps_out"].value     = f"{diag['drum_rps_out']:.3f} rps"
        cam_result_labels["cosine_corr"].value = f"{diag['cosine_correction_at_edge']:.3f}× boost"
        cam_result_labels["peak_accel"].value  = f"{diag['peak_ang_accel_rev_s2']:.1f} rev/s²"
        cam_result_labels["table_res"].value   = f"{diag['table_resolution_deg']:.4f} °/pt"

        # Color-code R against sane band
        R = diag["R"]
        cam_result_labels["R"].color = (SUCCESS_COLOR if 0.5 <= R <= 2.0
                                          else WARNING_COLOR)

        # Profile graph
        cam_profile_canvas.shapes = build_cam_profile_shapes(table, diag)

        # Warnings
        warnings = []
        if R < 0.3 or R > 3.0:
            warnings.append(f"⚠ R={R:.2f} far from 1 — drum must spin {diag['v_out']/diag['v_cut']:.1f}× cut speed in outside zone")
        if diag["drum_rps_out"] > 20:
            warnings.append(f"⚠ Outside-zone drum {diag['drum_rps_out']:.1f} rps = {diag['drum_rps_out']*60:.0f} RPM — verify drum motor max speed")
        if diag["peak_ang_accel_rev_s2"] > 500:
            warnings.append(f"⚠ Peak angular accel {diag['peak_ang_accel_rev_s2']:.0f} rev/s² — verify drum drive torque/inertia")
        if diag["table_resolution_deg"] > 1.5:
            warnings.append(f"⚠ Coarse table resolution ({diag['table_resolution_deg']:.2f}°/pt) — increase n_points for smoother motion")
        if blend < 0.1:
            warnings.append("⚠ Very small blend — sharp velocity transitions, high jerk at cut-window edges")
        if cam_settings.get("cpr", 0) < 1000:
            warnings.append(f"⚠ Low encoder resolution ({cpr} counts/rev) — table will quantize visibly")

        if not warnings:
            cam_warning_text.value = "✓ OK"
            cam_warning_text.color = SUCCESS_COLOR
        else:
            cam_warning_text.value = "  |  ".join(warnings)
            cam_warning_text.color = WARNING_COLOR

        # Review line + code
        try:
            link_ax  = int(axis_m_dropdown.value or "0")
            drum_ax  = int(axis_s_dropdown.value or "1")
            cutter_op = int(cutter_output_input.value or "8")
        except ValueError:
            link_ax, drum_ax, cutter_op = 0, 1, 8

        cam_review_text.value = (
            f"Review before running: material/encoder Axis {link_ax}, "
            f"drum Axis {drum_ax}, knife OP {cutter_op}, "
            f"{len(table)} table points starting at TABLE({table_start})."
        )

        cam_code_output.value = emit_cam_basic_program(
            table_values=table, diag=diag, cut_length=cut_len,
            link_axis=link_ax, drum_axis=drum_ax,
            table_start=table_start, cutter_op=cutter_op,
        )
        try:
            update_rotary_units_label()
            redraw_rotary_sim()
        except NameError:
            pass
        page.update()

    # Hook up handlers
    for inp in (cam_cut_input, cam_drum_dia_input, cam_n_knives_input,
                cam_cut_window_input, cam_cpr_input, cam_n_points_input,
                cam_blend_input, cam_vline_input, cam_table_start_input):
        inp.on_change = cam_recalc
        inp.on_blur = save_calc_settings

    def copy_cam_code(e):
        text = cam_code_output.value
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 2
        raw = text.encode("utf-16-le") + b"\x00\x00"
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        k32.GlobalAlloc.restype  = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype   = ctypes.c_void_p
        k32.GlobalLock.argtypes  = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype  = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        u32.OpenClipboard(0)
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, raw, len(raw))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
        u32.CloseClipboard()
        show_snack("Cam program copied to clipboard.", "success")

    copy_cam_btn = ft.FilledButton(
        "Copy program", icon=ft.Icons.CONTENT_COPY, on_click=copy_cam_code,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        height=38, tooltip="Copy generated TABLE/CAMBOX program to clipboard",
    )

    cam_panel_height = 1000

    cam_params_panel = ft.Container(
        content=ft.Column([
            section_header("Rotary Knife Cam Generator",
                            "Generate a CAMBOX position table from drum geometry",
                            ft.Icons.AUTORENEW),
            ft.Row([cam_cut_input, cam_drum_dia_input, cam_n_knives_input,
                    cam_cut_window_input, cam_cpr_input],
                   wrap=True, spacing=15, run_spacing=12),
            ft.Row([cam_n_points_input, cam_blend_input, cam_vline_input,
                    cam_table_start_input],
                   wrap=True, spacing=15, run_spacing=12),
            ft.Row([
                cam_result_card("Natural ratio R",       "R"),
                cam_result_card("Cut zone (master)",     "cut_zone"),
                cam_result_card("Drum RPS cut center",   "rps_cut"),
                cam_result_card("Drum RPS outside",      "rps_out"),
                cam_result_card("Cosine correction",     "cosine_corr"),
                cam_result_card("Peak ang. accel",       "peak_accel"),
                cam_result_card("Table resolution",      "table_res"),
            ], wrap=True, spacing=10, run_spacing=10),
            ft.Column([
                ft.Text("Drum velocity profile (cut window shaded)",
                        size=12, color=ft.Colors.GREY_400),
                ft.Container(
                    content=cam_profile_canvas,
                    border=ft.Border.all(1, BORDER_COLOR),
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=6),
            cam_warning_text,
            cam_review_text,
            ft.Text("Material axis (above) → CAMBOX link_ax. Shear axis → CAMBOX BASE drum_ax.",
                    size=12, color=ft.Colors.GREY_400),
        ], spacing=14, scroll=ft.ScrollMode.AUTO),
        bgcolor=PANEL_BG, border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8, padding=16, height=cam_panel_height,
        col={"xs": 12, "xl": 6},
    )

    cam_basic_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                section_header("Trio BASIC Program", "Generated TABLE + CAMBOX", ft.Icons.CODE),
                ft.Container(expand=True),
                copy_cam_btn,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            cam_code_output,
        ], expand=True, spacing=12),
        bgcolor=PANEL_BG, border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8, padding=16, height=cam_panel_height,
        col={"xs": 12, "xl": 6},
    )

    cam_calc_container = ft.ResponsiveRow(
        [cam_params_panel, cam_basic_panel],
        columns=12, spacing=18, run_spacing=18,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    cam_recalc()

    rotary_cam_math_help_list = ft.ListView(
        controls=[
            section_header(
                "Rotary Knife Cam Math",
                "How the generated CAMBOX profile is calculated and scaled",
                ft.Icons.FUNCTIONS,
            ),
            ft.ResponsiveRow(
                [
                    help_card(
                        "What CAMBOX Uses",
                        [
                            help_text(
                                "CAMBOX links drum-axis position to the measured motion of the material axis. "
                                "The app writes a TABLE profile, then calls CAMBOX with the material cut length as link_distance."
                            ),
                            formula_block(
                                [
                                    "CAMBOX(start_point, end_point, table_multiplier, link_distance, link_axis, link_options)",
                                    "this app: CAMBOX(table_start, table_end, 1, cut_length, material_axis, 4)",
                                    "bit 2 / value 4 = repeat continuously",
                                ]
                            ),
                            help_text(
                                "CAMBOX subtracts the first TABLE value, multiplies the remaining values by table_multiplier, "
                                "and treats the result as absolute slave-axis positions over one link_distance."
                            ),
                        ],
                        icon=ft.Icons.CODE,
                        col={"xs": 12, "xl": 6},
                    ),
                    help_card(
                        "Count Scale Requirement",
                        [
                            help_text(
                                "The drum encoder counts field must be the raw encoder counts for one physical drum revolution. "
                                "Do not enter Trio UNITS, MPOS/rev, mm, degrees, or a gearbox ratio-adjusted user unit."
                            ),
                            formula_block(
                                [
                                    "drum_counts_per_cut = drum_encoder_counts_per_rev / number_of_knives",
                                    "table_value[i] = round(normalized_drum_angle[i] * drum_counts_per_cut)",
                                    "final table value must equal drum_counts_per_cut",
                                ]
                            ),
                            help_text(
                                "This matters because CAMBOX TABLE values do not use UNITS. "
                                "If the count value is wrong, the controller receives a correctly shaped profile at the wrong scale."
                            ),
                        ],
                        icon=ft.Icons.WARNING_AMBER,
                        col={"xs": 12, "xl": 6},
                    ),
                ],
                columns=12,
                spacing=18,
                run_spacing=18,
            ),
            ft.ResponsiveRow(
                [
                    help_card(
                        "Normalized Profile",
                        [
                            help_text(
                                "The calculator works in normalized master distance u from 0 to 1, where one full cam cycle "
                                "corresponds to one requested cut length of material travel."
                            ),
                            formula_block(
                                [
                                    "u = material_distance / cut_length",
                                    "drum_radius = drum_diameter / 2",
                                    "drum_circumference = pi * drum_diameter",
                                    "R = number_of_knives * cut_length / drum_circumference",
                                ]
                            ),
                            help_text(
                                "R is the cut-center velocity ratio. R = 1 means a constant one-to-one surface speed is natural. "
                                "Values far from 1 mean the drum must slow down or speed up outside the cut window."
                            ),
                        ],
                        icon=ft.Icons.CALCULATE,
                        col={"xs": 12, "xl": 6},
                    ),
                    help_card(
                        "Cut Window Geometry",
                        [
                            help_text(
                                "Inside the cut window, the blade moves on a circle. The table boosts angular velocity at the window edges "
                                "so the blade horizontal velocity still matches the material."
                            ),
                            formula_block(
                                [
                                    "alpha_max = cut_window_deg / 2",
                                    "cut_zone_master = 2 * drum_radius * sin(alpha_max)",
                                    "x = (u - cut_center_u) * cut_length",
                                    "alpha = asin(x / drum_radius)",
                                    "v_cut(u) = R / cos(alpha)",
                                ]
                            ),
                            help_text(
                                "The generated diagnostics show the cosine correction at the edge of the cut window. "
                                "A wider cut window increases that correction and the required drum acceleration."
                            ),
                        ],
                        icon=ft.Icons.SHOW_CHART,
                        col={"xs": 12, "xl": 6},
                    ),
                ],
                columns=12,
                spacing=18,
                run_spacing=18,
            ),
            ft.ResponsiveRow(
                [
                    help_card(
                        "Blend And Integration",
                        [
                            help_text(
                                "Outside the cut window, the calculator solves the remaining drum travel and inserts sinusoidal blends "
                                "between outside speed and corrected cut-window speed."
                            ),
                            formula_block(
                                [
                                    "w_cut = cut_zone_master / cut_length",
                                    "w_blend = blend_fraction * (1 - w_cut) / 2",
                                    "w_outside = 1 - w_cut - 2 * w_blend",
                                    "integrate v(u) over 0..1, then scale total area back to exactly 1.0",
                                ]
                            ),
                            help_text(
                                "After integration, the normalized drum position is converted to integer encoder counts for the TABLE data."
                            ),
                        ],
                        icon=ft.Icons.TIMELINE,
                        col={"xs": 12, "xl": 6},
                    ),
                    help_card(
                        "CAMBOX Reference",
                        [
                            help_text(
                                "From CAMBOX.md: TABLE values define the slave motion profile, while link_distance is the positive "
                                "distance the linked material axis must travel to complete that profile."
                            ),
                            mini_table(
                                ["CAMBOX parameter", "Rotary knife value"],
                                [
                                    ("start_point", "TABLE start index"),
                                    ("end_point", "TABLE end index"),
                                    ("table_multiplier", "1, because table is already in counts"),
                                    ("link_distance", "cut length in material-axis units"),
                                    ("link_axis", "material encoder axis"),
                                    ("link_options", "4 for continuous repeat"),
                                ],
                                [150, 330],
                            ),
                            help_text(
                                "The drum axis is selected with BASE before CAMBOX. The material axis is the CAMBOX link axis."
                            ),
                        ],
                        icon=ft.Icons.MENU_BOOK,
                        col={"xs": 12, "xl": 6},
                    ),
                ],
                columns=12,
                spacing=18,
                run_spacing=18,
            ),
            help_card(
                "Practical Checks Before Running",
                [
                    help_text(
                        "Confirm the drum encoder counts per revolution against the real drive/encoder setup. "
                        "For a one-knife drum, the generated table should end at one full revolution of raw counts. "
                        "For an N-knife drum, it should end at one Nth of a revolution."
                    ),
                    formula_block(
                        [
                            "one knife: table[-1] = encoder_counts_per_rev",
                            "two knives: table[-1] = encoder_counts_per_rev / 2",
                            "N knives: table[-1] = encoder_counts_per_rev / N",
                        ]
                    ),
                    help_text(
                        "Also check table resolution, outside-zone RPS, and peak angular acceleration against the real drive limits."
                    ),
                ],
                icon=ft.Icons.TUNE,
            ),
        ],
        spacing=18,
        padding=20,
        expand=True,
    )

    # ============================================================
    # === Rotary Knife Live Simulation ===========================
    # ============================================================
    rotary_sim_settings = settings.setdefault("rotary_sim", {})
    ROTARY_MPOS_OVERRIDE_KEY = "mpos_counts_per_rev_override"
    ROTARY_LEGACY_MPOS_OVERRIDE_KEY = "drum_mpos_units_override"
    if ROTARY_MPOS_OVERRIDE_KEY not in rotary_sim_settings:
        rotary_sim_settings[ROTARY_MPOS_OVERRIDE_KEY] = rotary_sim_settings.pop(
            ROTARY_LEGACY_MPOS_OVERRIDE_KEY,
            None,
        )
    else:
        rotary_sim_settings.pop(ROTARY_LEGACY_MPOS_OVERRIDE_KEY, None)
    rotary_sim_settings.setdefault("drum_direction_reversed", False)
    rotary_sim_settings.setdefault("link_units_to_mm", 1.0)
    rotary_sim_settings.setdefault(ROTARY_MPOS_OVERRIDE_KEY, None)
    rotary_sim_settings.setdefault("match_tolerance_pct", 2.0)
    rotary_sim_settings.setdefault("show_debug", False)

    ROTARY_SIM_HEIGHT = 390
    ROTARY_DEFAULT_AXIS_CPR = 8_388_608.0
    ROTARY_DRUM_RADIUS_PX = 118
    ROTARY_KNIFE_LENGTH_PX = 38
    ROTARY_ACTIVE_KNIFE_EXTENSION_PX = 9
    ROTARY_GUIDE_GAP_PX = ROTARY_KNIFE_LENGTH_PX + ROTARY_ACTIVE_KNIFE_EXTENSION_PX + 2
    ROTARY_MATERIAL_CONTACT_ANGLE_RAD = math.pi
    ROTARY_TANGENTIAL_WARNING_LIMIT_MM_S = 10000.0

    rotary_sim_state = {
        "line_mpos": None,
        "drum_mpos": None,
        "line_mspeed": None,
        "drum_mspeed": None,
        "drum_demand_speed": None,
        "drum_tangential_mm_s": None,
        "belt_offset_px": 0.0,
        "drum_angle": 0.0,
        "axis_cpr": None,
        "cpr_axis": None,
        "cpr_source": "not read",
        "axis_units": None,
        "units_axis": None,
        "mpos_per_rev": None,
        "units_source": "not read",
        "units_error": None,
        "units_warning": None,
        "last_diag_update": 0.0,
        "speed_samples": collections.deque(maxlen=8),
        "last_kinematics": None,
        "drum_speed_warning": None,
    }

    def rotary_setting_float(key, default):
        try:
            return float(rotary_sim_settings.get(key, default))
        except (TypeError, ValueError):
            return default

    def cam_setting_float(key, default):
        try:
            return float(cam_settings.get(key, default))
        except (TypeError, ValueError):
            return default

    def cam_setting_int(key, default):
        try:
            return max(1, int(float(cam_settings.get(key, default))))
        except (TypeError, ValueError):
            return default

    def format_rotary_count(value):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return "--"
        if abs(val - round(val)) < 1e-9:
            return f"{int(round(val)):,}"
        return f"{val:,.6g}"

    def format_rotary_mpos_rev(value):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return "--"
        if abs(val - round(val)) < 1e-9 and abs(val) < 1000:
            return f"{val:.1f}"
        return format_rotary_count(val)

    def format_rotary_debug_float(value, digits=4):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return "--"
        return f"{val:.{digits}f}"

    def rotary_drum_direction_reversed():
        try:
            return bool(rotary_reverse_checkbox.value)
        except NameError:
            return bool(rotary_sim_settings.get("drum_direction_reversed", False))

    def rotary_override_value():
        raw = rotary_sim_settings.get(ROTARY_MPOS_OVERRIDE_KEY)
        try:
            val = float(raw)
            return val if val > 0 else None
        except (TypeError, ValueError):
            return None

    def rotary_recompute_mpos_per_rev():
        override = rotary_override_value()
        if override is not None:
            rotary_sim_state["mpos_per_rev"] = override
            rotary_sim_state["units_source"] = "manual override"
            rotary_sim_state["units_error"] = None
            rotary_sim_state["units_warning"] = None
            return override

        cpr = rotary_sim_state.get("axis_cpr")
        units = rotary_sim_state.get("axis_units")
        if cpr is None:
            rotary_sim_state["mpos_per_rev"] = None
            rotary_sim_state["units_error"] = "Drum axis CPR not read"
            return None
        if units is None:
            rotary_sim_state["mpos_per_rev"] = None
            rotary_sim_state["units_error"] = "Drum UNITS not read"
            return None

        try:
            rotary_sim_state["mpos_per_rev"] = compute_rotary_mpos_counts_per_physical_rev(cpr, units)
        except ValueError as ex:
            rotary_sim_state["mpos_per_rev"] = None
            rotary_sim_state["units_error"] = str(ex)
            return None

        rotary_sim_state["units_error"] = None
        return rotary_sim_state["mpos_per_rev"]

    def update_rotary_units_label():
        cpr = rotary_sim_state.get("axis_cpr")
        units = rotary_sim_state.get("axis_units")
        mpos_per_rev = rotary_recompute_mpos_per_rev()

        if cpr is None:
            rotary_encoder_cpr_label.value = "--"
            rotary_encoder_cpr_label.color = WARNING_COLOR
        else:
            rotary_encoder_cpr_label.value = format_rotary_count(cpr)
            rotary_encoder_cpr_label.color = SUCCESS_COLOR if cpr > 0 else ERROR_COLOR

        if units is None:
            rotary_drum_units_label.value = "--"
            rotary_drum_units_label.color = WARNING_COLOR
        else:
            rotary_drum_units_label.value = format_rotary_count(units)
            rotary_drum_units_label.color = SUCCESS_COLOR

        if mpos_per_rev:
            rotary_mpos_per_rev_label.value = format_rotary_mpos_rev(mpos_per_rev)
            rotary_mpos_per_rev_label.color = SUCCESS_COLOR
        else:
            rotary_mpos_per_rev_label.value = "--"
            rotary_mpos_per_rev_label.color = ERROR_COLOR

        if rotary_sim_state.get("units_error"):
            rotary_units_source_label.value = rotary_sim_state["units_error"]
            rotary_units_source_label.color = ERROR_COLOR
        elif rotary_sim_state.get("units_warning"):
            rotary_units_source_label.value = rotary_sim_state["units_warning"]
            rotary_units_source_label.color = WARNING_COLOR
        elif rotary_override_value() is not None:
            rotary_units_source_label.value = "manual override"
            rotary_units_source_label.color = WARNING_COLOR
        else:
            cpr_source = rotary_sim_state.get("cpr_source", "CPR not read")
            units_source = rotary_sim_state.get("units_source", "UNITS not read")
            rotary_units_source_label.value = f"{cpr_source}; {units_source}"
            rotary_units_source_label.color = MUTED_TEXT

    def saved_drum_units_for_axis(axis):
        axis_params = settings.get("axis_params", {}).get(str(axis), {})
        try:
            return float(axis_params.get("UNITS"))
        except (TypeError, ValueError):
            return None

    def apply_saved_rotary_units_fallback(axis):
        units = saved_drum_units_for_axis(axis)
        rotary_sim_state["units_warning"] = None
        rotary_sim_state["axis_cpr"] = ROTARY_DEFAULT_AXIS_CPR
        rotary_sim_state["cpr_axis"] = axis
        rotary_sim_state["cpr_source"] = f"default CPR {format_rotary_count(ROTARY_DEFAULT_AXIS_CPR)}"

        if units is None:
            rotary_sim_state["axis_units"] = None
            rotary_sim_state["units_axis"] = axis
            rotary_sim_state["units_source"] = "not connected"
        else:
            rotary_sim_state["axis_units"] = units
            rotary_sim_state["units_axis"] = axis
            rotary_sim_state["units_source"] = f"saved UNITS {units:g}"
        rotary_sim_state["units_error"] = None
        rotary_sim_state["speed_samples"].clear()
        update_rotary_units_label()

    def request_rotary_units_refresh():
        try:
            axis = int(axis_s_dropdown.value or "1")
        except ValueError:
            axis = 1

        if rotary_override_value() is not None:
            rotary_sim_state["cpr_axis"] = axis
            rotary_sim_state["units_axis"] = axis
            update_rotary_units_label()
            redraw_rotary_sim()
            try:
                _update_if_mounted(rotary_sim_container)
            except NameError:
                pass
            return

        if not trio_conn.is_connected():
            apply_saved_rotary_units_fallback(axis)
            redraw_rotary_sim()
            try:
                _update_if_mounted(rotary_sim_container)
            except NameError:
                pass
            return

        try:
            asyncio.create_task(refresh_rotary_drum_units())
        except RuntimeError:
            pass

    async def refresh_rotary_drum_units(e=None):
        try:
            axis = int(axis_s_dropdown.value or "1")
        except ValueError:
            axis = 1

        if rotary_override_value() is not None:
            rotary_sim_state["cpr_axis"] = axis
            rotary_sim_state["units_axis"] = axis
            update_rotary_units_label()
            rotary_status_text.value = "Using manual drum MPOS/rev override."
            rotary_status_text.color = WARNING_COLOR
            redraw_rotary_sim()
            page.update()
            return

        if not trio_conn.is_connected():
            apply_saved_rotary_units_fallback(axis)
            rotary_status_text.value = "Controller not connected; using saved axis UNITS if available."
            rotary_status_text.color = MUTED_TEXT
            redraw_rotary_sim()
            page.update()
            return

        loop = asyncio.get_running_loop()

        def _read_axis_geometry():
            conn = trio_conn.connection
            if not conn or not trio_conn.is_connected():
                return {}, {"CPR": "not connected", "UNITS": "not connected"}
            values = {}
            errors = {}
            for param_name in ("CPR", "UNITS"):
                method = getattr(conn, f"GetAxisParameter_{param_name}", None)
                if method is None:
                    errors[param_name] = f"GetAxisParameter_{param_name} unavailable"
                    continue
                try:
                    values[param_name] = float(method(axis))
                except Exception as ex:
                    errors[param_name] = str(ex)
            return values, errors

        try:
            live_values, read_errors = await loop.run_in_executor(uapi_executor, _read_axis_geometry)
            cpr = live_values.get("CPR")
            units = live_values.get("UNITS")
            warnings = []

            if cpr is None:
                cpr = ROTARY_DEFAULT_AXIS_CPR
                rotary_sim_state["cpr_source"] = f"default CPR {format_rotary_count(cpr)}"
                cpr_error = read_errors.get("CPR", "")
                if cpr_error and "unavailable" not in cpr_error:
                    warnings.append(
                        f"CPR read failed ({read_errors.get('CPR', 'unknown')}); using default axis CPR."
                    )
            else:
                rotary_sim_state["cpr_source"] = f"axis {axis} CPR {format_rotary_count(cpr)}"

            if units is None:
                units = saved_drum_units_for_axis(axis)
                if units is None:
                    units = 1.0
                    rotary_sim_state["units_source"] = "fallback UNITS 1"
                    warnings.append(
                        f"UNITS read failed ({read_errors.get('UNITS', 'unknown')}); using fallback UNITS 1."
                    )
                else:
                    rotary_sim_state["units_source"] = f"saved UNITS {format_rotary_count(units)}"
                    warnings.append(
                        f"UNITS read failed ({read_errors.get('UNITS', 'unknown')}); using saved UNITS."
                    )
            else:
                rotary_sim_state["units_source"] = f"axis {axis} UNITS {units:g}"

            rotary_sim_state["axis_cpr"] = cpr
            rotary_sim_state["cpr_axis"] = axis
            rotary_sim_state["axis_units"] = units
            rotary_sim_state["units_axis"] = axis
            rotary_sim_state["units_error"] = None
            rotary_sim_state["units_warning"] = " ".join(warnings) if warnings else None
            rotary_sim_state["speed_samples"].clear()
            if warnings:
                rotary_status_text.value = rotary_sim_state["units_warning"]
                rotary_status_text.color = WARNING_COLOR
            else:
                rotary_status_text.value = (
                    f"Drum axis {axis} CPR/UNITS read: "
                    f"{format_rotary_count(cpr)} / {format_rotary_count(units)}"
                )
                rotary_status_text.color = SUCCESS_COLOR
        except Exception as ex:
            fallback_cpr = ROTARY_DEFAULT_AXIS_CPR
            cpr_text = f"default CPR {format_rotary_count(fallback_cpr)}"
            fallback_units = saved_drum_units_for_axis(axis)
            if fallback_units is None:
                fallback_units = 1.0
                fallback_text = "fallback UNITS 1"
            else:
                fallback_text = f"saved UNITS {format_rotary_count(fallback_units)}"
            rotary_sim_state["axis_cpr"] = fallback_cpr
            rotary_sim_state["cpr_axis"] = axis
            rotary_sim_state["cpr_source"] = cpr_text
            rotary_sim_state["axis_units"] = fallback_units
            rotary_sim_state["units_axis"] = axis
            rotary_sim_state["units_source"] = fallback_text
            rotary_sim_state["units_error"] = None
            rotary_sim_state["units_warning"] = f"CPR/UNITS read failed; using {cpr_text} and {fallback_text}"
            rotary_sim_state["speed_samples"].clear()
            rotary_status_text.value = f"Drum CPR/UNITS read failed: {ex}; using {cpr_text} and {fallback_text}."
            rotary_status_text.color = WARNING_COLOR

        update_rotary_units_label()
        redraw_rotary_sim()
        page.update()

    def rotary_draw_conveyor(shapes, width, belt_offset_px):
        rail_color = "#4a4f55"
        belt_left = PULLEY_SIZE
        belt_right = width - PULLEY_SIZE
        belt_width_px = max(120, belt_right - belt_left)
        pulley_y = ROTARY_SIM_HEIGHT - 58
        belt_y = pulley_y + (PULLEY_SIZE - BELT_HEIGHT) / 2
        belt_center_y = belt_y + BELT_HEIGHT / 2

        shapes.extend([
            cv.Rect(0, 0, width, ROTARY_SIM_HEIGHT,
                    paint=ft.Paint(color=DARKER_BG, style=ft.PaintingStyle.FILL)),
            cv.Rect(0, belt_y - RAIL_HEIGHT - 2, width, RAIL_HEIGHT,
                    paint=ft.Paint(color=rail_color, style=ft.PaintingStyle.FILL)),
            cv.Rect(0, belt_y + BELT_HEIGHT + 2, width, RAIL_HEIGHT,
                    paint=ft.Paint(color=rail_color, style=ft.PaintingStyle.FILL)),
            cv.Rect(belt_left, belt_y, belt_width_px, BELT_HEIGHT,
                    border_radius=ft.BorderRadius.all(BELT_HEIGHT / 2),
                    paint=ft.Paint(
                        gradient=ft.PaintLinearGradient(
                            begin=ft.Offset(belt_left, belt_y),
                            end=ft.Offset(belt_left, belt_y + BELT_HEIGHT),
                            colors=["#262626", "#070707", "#262626"],
                            color_stops=[0.0, 0.5, 1.0],
                        ),
                        style=ft.PaintingStyle.FILL,
                    )),
            cv.Circle(PULLEY_SIZE / 2, belt_center_y, PULLEY_SIZE / 2,
                      paint=ft.Paint(color="#6f7478", style=ft.PaintingStyle.FILL)),
            cv.Circle(width - PULLEY_SIZE / 2, belt_center_y, PULLEY_SIZE / 2,
                      paint=ft.Paint(color="#6f7478", style=ft.PaintingStyle.FILL)),
            cv.Circle(PULLEY_SIZE / 2, belt_center_y, PULLEY_SIZE * 0.16,
                      paint=ft.Paint(color="#151515", style=ft.PaintingStyle.FILL)),
            cv.Circle(width - PULLEY_SIZE / 2, belt_center_y, PULLEY_SIZE * 0.16,
                      paint=ft.Paint(color="#151515", style=ft.PaintingStyle.FILL)),
        ])

        x = belt_left - BELT_SPACING + (belt_offset_px % BELT_SPACING)
        cleat_paint = ft.Paint(
            gradient=ft.PaintLinearGradient(
                begin=ft.Offset(0, belt_y),
                end=ft.Offset(0, belt_y + BELT_HEIGHT),
                colors=[ft.Colors.GREY_400, ft.Colors.GREY_700, "#050505"],
                color_stops=[0.0, 0.45, 1.0],
            ),
            style=ft.PaintingStyle.FILL,
        )
        while x < belt_right + BELT_SPACING:
            if belt_left - CLEAT_WIDTH <= x <= belt_right:
                shapes.append(
                    cv.Rect(x, belt_y + (BELT_HEIGHT - CLEAT_HEIGHT) / 2,
                            CLEAT_WIDTH, CLEAT_HEIGHT,
                            border_radius=ft.BorderRadius.all(2),
                            paint=cleat_paint)
                )
            x += BELT_SPACING
        return belt_y

    def rotary_cut_state_for_angle(drum_angle, n_knives, cut_window_deg):
        spacing = 2 * math.pi / max(1, n_knives)
        knife_angles = [(drum_angle + i * spacing) % (2 * math.pi) for i in range(n_knives)]
        distances = [
            shortest_angle_distance_rad(a, ROTARY_MATERIAL_CONTACT_ANGLE_RAD)
            for a in knife_angles
        ]
        closest = min(distances) if distances else 0.0
        closest_index = distances.index(closest) if distances else 0
        half_window = math.radians(cut_window_deg / 2.0)
        in_cut = closest <= half_window
        approach_band = max(half_window * 2.0, half_window + math.radians(10))
        approaching = not in_cut and closest <= approach_band
        return knife_angles, closest_index, closest, in_cut, approaching

    def draw_rotary_drum(shapes, width, belt_y, drum_angle):
        n_knives = cam_setting_int("n_knives", 1)
        cut_window = max(0.1, cam_setting_float("cut_window", 30.0))
        r = ROTARY_DRUM_RADIUS_PX
        horizontal_margin = r + ROTARY_KNIFE_LENGTH_PX + ROTARY_ACTIVE_KNIFE_EXTENSION_PX + 42
        if width >= horizontal_margin * 2:
            cx = max(horizontal_margin, min(width - horizontal_margin, width * 0.32))
        else:
            cx = width / 2
        cy = belt_y - ROTARY_GUIDE_GAP_PX - r
        half_window = math.radians(cut_window / 2.0)
        knife_angles, closest_index, closest, in_cut, approaching = rotary_cut_state_for_angle(
            drum_angle, n_knives, cut_window
        )

        def fill_paint(color):
            return ft.Paint(color=color, style=ft.PaintingStyle.FILL)

        def linear_paint(x0, y0, x1, y1, colors, stops=None):
            if stops is None:
                if len(colors) <= 1:
                    stops = [0.0]
                else:
                    stops = [i / (len(colors) - 1) for i in range(len(colors))]
            return ft.Paint(
                gradient=ft.PaintLinearGradient(
                    begin=ft.Offset(x0, y0),
                    end=ft.Offset(x1, y1),
                    colors=colors,
                    color_stops=stops,
                ),
                style=ft.PaintingStyle.FILL,
            )

        def point_for(angle, radius):
            dx, dy = rotary_blade_direction_for_angle(angle)
            return cx + radius * dx, cy + radius * dy

        def add_polygon(points, fill, stroke="#111316", stroke_width=1.1):
            if not points:
                return
            elements = [cv.Path.MoveTo(*points[0])]
            elements.extend(cv.Path.LineTo(*point) for point in points[1:])
            elements.append(cv.Path.Close())
            shapes.append(cv.Path(elements=elements, paint=fill_paint(fill)))
            if stroke:
                shapes.append(
                    cv.Path(
                        elements=elements,
                        paint=canvas_paint(stroke, stroke_width),
                    )
                )

        def oriented_box(angle, radius_inner, radius_outer, width_px, fill, stroke="#111316", stroke_width=1.0):
            dx, dy = rotary_blade_direction_for_angle(angle)
            tx = math.cos(angle)
            ty = math.sin(angle)
            inner_x, inner_y = cx + radius_inner * dx, cy + radius_inner * dy
            outer_x, outer_y = cx + radius_outer * dx, cy + radius_outer * dy
            points = [
                (inner_x - tx * width_px / 2, inner_y - ty * width_px / 2),
                (outer_x - tx * width_px / 2, outer_y - ty * width_px / 2),
                (outer_x + tx * width_px / 2, outer_y + ty * width_px / 2),
                (inner_x + tx * width_px / 2, inner_y + ty * width_px / 2),
            ]
            add_polygon(points, fill, stroke, stroke_width)

        contact_color = SUCCESS_COLOR if in_cut else WARNING_COLOR if approaching else "#7f8a94"
        guideline_paint = canvas_paint(ft.Colors.with_opacity(0.55, "#8fa1b3"), 1.2, dash=[6, 7])
        shapes.append(cv.Line(cx, cy - r - 26, cx, belt_y + BELT_HEIGHT + 10, paint=guideline_paint))

        bed_y = belt_y - 12
        block_w = 82
        block_h = 72
        left_block_x = max(12, cx - r - 112)
        right_block_x = min(width - block_w - 12, cx + r + 30)
        block_y = cy - block_h / 2
        shaft_left = left_block_x + block_w - 8
        shaft_right = right_block_x + 8

        # Fixed machine hardware behind the rotating drum.
        shapes.extend([
            cv.Rect(cx - r - 86, bed_y - 6, 2 * (r + 86), 8,
                    border_radius=ft.BorderRadius.all(3),
                    paint=linear_paint(cx, bed_y - 6, cx, bed_y + 2,
                                       ["#5f6871", "#262d33", "#101418"])),
            cv.Rect(left_block_x + 14, block_y + block_h - 2,
                    16, max(18, bed_y - block_y - block_h + 3),
                    border_radius=ft.BorderRadius.all(2),
                    paint=linear_paint(left_block_x, block_y, left_block_x, bed_y,
                                       ["#68727b", "#303840", "#13171b"])),
            cv.Rect(right_block_x + block_w - 30, block_y + block_h - 2,
                    16, max(18, bed_y - block_y - block_h + 3),
                    border_radius=ft.BorderRadius.all(2),
                    paint=linear_paint(right_block_x, block_y, right_block_x, bed_y,
                                       ["#68727b", "#303840", "#13171b"])),
            cv.Rect(left_block_x, block_y, block_w, block_h,
                    border_radius=ft.BorderRadius.all(7),
                    paint=linear_paint(left_block_x, block_y, left_block_x, block_y + block_h,
                                       ["#74808a", "#303942", "#151a1f"])),
            cv.Rect(right_block_x, block_y, block_w, block_h,
                    border_radius=ft.BorderRadius.all(7),
                    paint=linear_paint(right_block_x, block_y, right_block_x, block_y + block_h,
                                       ["#74808a", "#303942", "#151a1f"])),
            cv.Rect(shaft_left, cy - 7, max(0, shaft_right - shaft_left), 14,
                    border_radius=ft.BorderRadius.all(7),
                    paint=linear_paint(cx, cy - 7, cx, cy + 7,
                                       ["#b7c0c7", "#69737c", "#20272d"],
                                       [0.0, 0.46, 1.0])),
            cv.Circle(left_block_x + block_w / 2, cy, 23,
                      paint=fill_paint("#151b20")),
            cv.Circle(left_block_x + block_w / 2, cy, 15,
                      paint=fill_paint("#56616b")),
            cv.Circle(right_block_x + block_w / 2, cy, 23,
                      paint=fill_paint("#151b20")),
            cv.Circle(right_block_x + block_w / 2, cy, 15,
                      paint=fill_paint("#56616b")),
        ])

        for bolt_x in (left_block_x + 13, left_block_x + block_w - 13, right_block_x + 13, right_block_x + block_w - 13):
            for bolt_y in (block_y + 13, block_y + block_h - 13):
                shapes.append(cv.Circle(bolt_x, bolt_y, 3.3, paint=fill_paint("#111418")))
                shapes.append(cv.Circle(bolt_x - 0.9, bolt_y - 0.9, 1.0, paint=fill_paint("#aab2b9")))

        cut_window_color = SUCCESS_COLOR if in_cut else WARNING_COLOR if approaching else "#ccd24a"
        shapes.extend([
            cv.Arc(cx - r - 18, cy - r - 18, 2 * (r + 18), 2 * (r + 18),
                   start_angle=math.pi / 2 - half_window,
                   sweep_angle=2 * half_window,
                   paint=canvas_paint(ft.Colors.with_opacity(0.42, cut_window_color), 14)),
            cv.Arc(cx - r - 34, cy - r - 34, 2 * (r + 34), 2 * (r + 34),
                   start_angle=math.pi + math.radians(12),
                   sweep_angle=math.pi - math.radians(24),
                   paint=canvas_paint(ft.Colors.with_opacity(0.20, "#4fc3f7"), 11)),
            cv.Arc(cx - r - 34, cy - r - 34, 2 * (r + 34), 2 * (r + 34),
                   start_angle=math.pi + math.radians(12),
                   sweep_angle=math.pi - math.radians(24),
                   paint=canvas_paint(ft.Colors.with_opacity(0.58, "#8fb6c7"), 1.4, dash=[12, 7])),
            cv.Oval(cx - r - 22, cy + r - 14, 2 * (r + 22), 34,
                    paint=fill_paint(ft.Colors.with_opacity(0.22, "#000000"))),
        ])

        marker_count = 7
        for idx in range(marker_count):
            offset = -half_window + (2 * half_window * idx / max(1, marker_count - 1))
            mx, my = point_for(ROTARY_MATERIAL_CONTACT_ANGLE_RAD + offset, r + ROTARY_KNIFE_LENGTH_PX + 2)
            shapes.append(cv.Circle(mx, my, 2.2, paint=fill_paint(ft.Colors.with_opacity(0.72, cut_window_color))))

        shapes.extend([
            cv.Circle(cx, cy, r + 4,
                      paint=fill_paint("#0b0f13")),
            cv.Circle(cx, cy, r,
                      paint=ft.Paint(
                          gradient=ft.PaintSweepGradient(
                              center=ft.Offset(cx, cy),
                              colors=["#5d6871", "#d4dade", "#76808a", "#242b31", "#aab2b9", "#5d6871"],
                              color_stops=[0.0, 0.16, 0.32, 0.56, 0.78, 1.0],
                              rotation=drum_angle,
                          ),
                          style=ft.PaintingStyle.FILL,
                      )),
            cv.Circle(cx, cy, r - 8,
                      paint=ft.Paint(
                          gradient=ft.PaintRadialGradient(
                              center=ft.Offset(cx - r * 0.36, cy - r * 0.40),
                              radius=r * 1.28,
                              colors=[
                                  ft.Colors.with_opacity(0.40, ft.Colors.WHITE),
                                  ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                                  ft.Colors.with_opacity(0.28, ft.Colors.BLACK),
                              ],
                              color_stops=[0.0, 0.54, 1.0],
                          ),
                          style=ft.PaintingStyle.FILL,
                      )),
            cv.Circle(cx, cy, r,
                      paint=canvas_paint("#07090c", 2.2)),
            cv.Circle(cx, cy, r - 23,
                      paint=canvas_paint(ft.Colors.with_opacity(0.34, ft.Colors.WHITE), 0.9)),
        ])

        for slot_idx in range(24):
            theta = drum_angle + slot_idx * 2.0 * math.pi / 24.0
            sx0, sy0 = point_for(theta, r - 24)
            sx1, sy1 = point_for(theta, r - 9)
            line_color = ft.Colors.with_opacity(0.28 if slot_idx % 2 == 0 else 0.14, ft.Colors.WHITE)
            shapes.append(cv.Line(sx0, sy0, sx1, sy1, paint=canvas_paint(line_color, 1.0)))

        for spoke_idx in range(6):
            theta = drum_angle + spoke_idx * 2.0 * math.pi / 6.0
            oriented_box(theta, 36, r - 34, 15, ft.Colors.with_opacity(0.26, "#0d1116"),
                         stroke=ft.Colors.with_opacity(0.16, ft.Colors.WHITE), stroke_width=0.8)

        for bolt_idx in range(12):
            theta = drum_angle + bolt_idx * 2.0 * math.pi / 12.0
            bx, by = point_for(theta, 74)
            shapes.append(cv.Circle(bx, by, 4.6, paint=fill_paint("#12161a")))
            shapes.append(cv.Circle(bx - 1.2, by - 1.2, 1.3, paint=fill_paint("#b9c0c6")))

        shapes.extend([
            cv.Circle(cx, cy, 33,
                      paint=ft.Paint(
                          gradient=ft.PaintRadialGradient(
                              center=ft.Offset(cx - 11, cy - 13),
                              radius=46,
                              colors=["#d2d8dc", "#69747d", "#171d22"],
                              color_stops=[0.0, 0.55, 1.0],
                          ),
                          style=ft.PaintingStyle.FILL,
                      )),
            cv.Circle(cx, cy, 33, paint=canvas_paint("#090b0e", 1.2)),
            cv.Circle(cx, cy, 13, paint=fill_paint("#161c22")),
            cv.Circle(cx, cy, 5, paint=fill_paint("#050607")),
        ])

        blade_order = sorted(
            enumerate(knife_angles),
            key=lambda item: rotary_blade_direction_for_angle(item[1])[1],
        )
        for i, theta in blade_order:
            dx, dy = rotary_blade_direction_for_angle(theta)
            tx = math.cos(theta)
            ty = math.sin(theta)
            is_hot = i == closest_index and in_cut
            is_near = i == closest_index and (in_cut or approaching)
            active_extension = ROTARY_ACTIVE_KNIFE_EXTENSION_PX if is_hot else 0
            blade_tip_radius = r + ROTARY_KNIFE_LENGTH_PX + active_extension

            oriented_box(theta, r - 17, r + 8, 44, "#46515a", "#11161a", 1.0)
            oriented_box(theta, r - 8, r + 5, 34, "#85909a", "#263039", 0.8)

            base_radius = r + 4
            shoulder_radius = r + ROTARY_KNIFE_LENGTH_PX * 0.72
            tip_radius = blade_tip_radius
            root_w = 31 + (4 if is_hot else 0)
            shoulder_w = 17 + (3 if is_hot else 0)
            tip_w = 4
            root_l = (cx + base_radius * dx - tx * root_w / 2, cy + base_radius * dy - ty * root_w / 2)
            shoulder_l = (cx + shoulder_radius * dx - tx * shoulder_w / 2, cy + shoulder_radius * dy - ty * shoulder_w / 2)
            tip_l = (cx + (tip_radius - 3) * dx - tx * tip_w / 2, cy + (tip_radius - 3) * dy - ty * tip_w / 2)
            tip = (cx + tip_radius * dx, cy + tip_radius * dy)
            tip_r = (cx + (tip_radius - 3) * dx + tx * tip_w / 2, cy + (tip_radius - 3) * dy + ty * tip_w / 2)
            shoulder_r = (cx + shoulder_radius * dx + tx * shoulder_w / 2, cy + shoulder_radius * dy + ty * shoulder_w / 2)
            root_r = (cx + base_radius * dx + tx * root_w / 2, cy + base_radius * dy + ty * root_w / 2)
            blade_fill = "#ffe082" if is_hot else "#dfe7eb"
            blade_stroke = "#5f4d16" if is_hot else "#1e252b"
            add_polygon([root_l, shoulder_l, tip_l, tip, tip_r, shoulder_r, root_r],
                        blade_fill, blade_stroke, 1.25 if is_near else 1.0)

            bevel_mid = (cx + (base_radius + 12) * dx - tx * 5, cy + (base_radius + 12) * dy - ty * 5)
            bevel_tip = (cx + (tip_radius - 5) * dx - tx * 1.5, cy + (tip_radius - 5) * dy - ty * 1.5)
            shapes.append(cv.Line(bevel_mid[0], bevel_mid[1], bevel_tip[0], bevel_tip[1],
                                  paint=canvas_paint(ft.Colors.with_opacity(0.72, ft.Colors.WHITE), 1.1)))
            shapes.append(cv.Line(tip[0], tip[1], shoulder_r[0], shoulder_r[1],
                                  paint=canvas_paint("#7d858c", 0.9)))

            for bolt_offset in (-12, 12):
                bolt_x = cx + (r - 3) * dx + tx * bolt_offset
                bolt_y = cy + (r - 3) * dy + ty * bolt_offset
                shapes.append(cv.Circle(bolt_x, bolt_y, 2.6, paint=fill_paint("#111418")))
                shapes.append(cv.Circle(bolt_x - 0.7, bolt_y - 0.7, 0.8, paint=fill_paint("#d6dde2")))

            if is_hot:
                shapes.extend([
                    cv.Oval(tip[0] - 39, tip[1] - 10, 78, 20,
                            paint=fill_paint(ft.Colors.with_opacity(0.30, "#ffd54f"))),
                    cv.Line(tip[0] - 18, belt_y - 2, tip[0] - 5, belt_y + 8,
                            paint=canvas_paint("#ffecb3", 1.2)),
                    cv.Line(tip[0] + 12, belt_y - 3, tip[0] + 25, belt_y + 7,
                            paint=canvas_paint("#ffb74d", 1.1)),
                ])
            elif is_near:
                shapes.append(cv.Circle(tip[0], tip[1], 8,
                                        paint=fill_paint(ft.Colors.with_opacity(0.18, "#ffcc80"))))

        anvil_y = belt_y - 7
        shapes.extend([
            cv.Rect(cx - 62, anvil_y, 124, 7,
                    border_radius=ft.BorderRadius.all(2),
                    paint=linear_paint(cx, anvil_y, cx, anvil_y + 7,
                                       ["#c5ced5", "#68737d", "#222a31"])),
            cv.Rect(cx - 50, anvil_y - 4, 100, 3,
                    border_radius=ft.BorderRadius.all(1.5),
                    paint=fill_paint(ft.Colors.with_opacity(0.68, contact_color))),
        ])

        add_profile_text(
            shapes,
            cx + r + 42,
            cy - r + 14,
            f"{math.degrees(drum_angle) % 360.0:05.1f} deg",
            size=11,
            color=ft.Colors.GREY_400,
            align=ft.Alignment.TOP_LEFT,
            max_width=130,
        )

        return in_cut, approaching, closest

    def redraw_rotary_sim():
        width = float(rotary_sim_canvas.width or visual_width)
        shapes = []
        belt_y = rotary_draw_conveyor(shapes, width, rotary_sim_state["belt_offset_px"])
        in_cut, approaching, closest = draw_rotary_drum(
            shapes,
            width,
            belt_y,
            rotary_sim_state.get("drum_angle", 0.0),
        )
        rotary_sim_state["in_cut"] = in_cut
        rotary_sim_state["approaching"] = approaching
        rotary_sim_state["closest_knife_rad"] = closest
        rotary_sim_canvas.shapes = shapes
        return True

    def rotary_diag_card(label, value_control, width=185):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=11, color=ft.Colors.GREY_400),
                value_control,
            ], spacing=4, tight=True),
            bgcolor=PANEL_ALT_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=10,
            width=width,
        )

    def update_rotary_debug_overlay():
        try:
            show_debug = bool(rotary_debug_checkbox.value)
            rotary_debug_container.visible = show_debug
        except NameError:
            return
        if not show_debug:
            return

        kinematics = rotary_sim_state.get("last_kinematics") or {}
        drum_mpos = kinematics.get("drum_mpos", rotary_sim_state.get("drum_mpos"))
        drum_mspeed = kinematics.get("drum_mspeed", rotary_sim_state.get("drum_mspeed"))
        drum_demand_speed = rotary_sim_state.get("drum_demand_speed")
        effective_mspeed = kinematics.get("effective_drum_mspeed")
        axis_cpr = rotary_sim_state.get("axis_cpr")
        mpos_per_rev = kinematics.get("mpos_per_rev", rotary_sim_state.get("mpos_per_rev"))
        drum_rps = kinematics.get("drum_rps")
        circumference = kinematics.get("drum_circumference_mm")
        drum_tangential = rotary_sim_state.get("drum_tangential_mm_s")
        drum_angle = kinematics.get("drum_angle_rad", rotary_sim_state.get("drum_angle"))

        mspeed_text = format_rotary_debug_float(drum_mspeed)
        if (
            drum_mspeed is not None
            and effective_mspeed is not None
            and abs(float(drum_mspeed) - float(effective_mspeed)) > 1e-12
        ):
            mspeed_text = (
                f"{format_rotary_debug_float(drum_mspeed)} raw / "
                f"{format_rotary_debug_float(effective_mspeed)} effective"
            )

        rotary_debug_text.value = "\n".join([
            f"Drum MPOS:           {format_rotary_debug_float(drum_mpos)} user units",
            f"Drum MSPEED:         {mspeed_text} user units/s",
            f"Drum DEMAND_SPEED:   {format_rotary_debug_float(drum_demand_speed)}",
            f"Drum CPR:            {format_rotary_debug_float(axis_cpr, 0)} counts/rev",
            f"mpos per rev:        {format_rotary_debug_float(mpos_per_rev, 6)}",
            f"Drum RPS:            {format_rotary_debug_float(drum_rps)}",
            f"Drum circumference:  {format_rotary_debug_float(circumference, 2)} mm",
            f"Drum tangential:     {format_rotary_debug_float(drum_tangential, 2)} mm/s (DEMAND_SPEED x1000)",
            f"Drum angle:          {format_rotary_debug_float(drum_angle)} rad",
        ])

    def update_rotary_diagnostics(now):
        if now - rotary_sim_state["last_diag_update"] < 0.12:
            update_rotary_debug_overlay()
            return False
        rotary_sim_state["last_diag_update"] = now

        line_mspeed = rotary_sim_state.get("line_mspeed")
        drum_mspeed = rotary_sim_state.get("drum_mspeed")
        drum_mpos = rotary_sim_state.get("drum_mpos")
        link_units_to_mm = rotary_setting_float("link_units_to_mm", 1.0)
        drum_diameter = cam_setting_float("drum_dia", 200.0)
        mpos_per_rev = rotary_recompute_mpos_per_rev()
        in_cut = bool(rotary_sim_state.get("in_cut"))
        approaching = bool(rotary_sim_state.get("approaching"))

        line_mm_s = line_mspeed * link_units_to_mm if line_mspeed is not None else None
        drum_demand_speed = rotary_sim_state.get("drum_demand_speed")
        drum_mm_s = drum_demand_speed * 1000.0 if drum_demand_speed is not None else None
        rotary_sim_state["drum_tangential_mm_s"] = drum_mm_s
        kinematics = None
        if mpos_per_rev and (drum_mpos is not None or drum_mspeed is not None):
            try:
                kinematics = compute_rotary_drum_kinematics(
                    drum_mpos,
                    drum_mspeed,
                    mpos_per_rev,
                    drum_diameter,
                    rotary_drum_direction_reversed(),
                )
                rotary_sim_state["last_kinematics"] = kinematics
            except ValueError:
                rotary_sim_state["last_kinematics"] = None

        speed_warning = None
        if drum_mm_s is not None and abs(drum_mm_s) > ROTARY_TANGENTIAL_WARNING_LIMIT_MM_S:
            speed_warning = (
                "Drum tangential exceeds 10000 mm/s; check MPOS/rev, drum diameter, "
                "or selected drum axis."
            )
        rotary_sim_state["drum_speed_warning"] = speed_warning

        if line_mm_s is not None and drum_mm_s is not None and not speed_warning:
            rotary_sim_state["speed_samples"].append((line_mm_s, drum_mm_s))
        if rotary_sim_state["speed_samples"] and not speed_warning:
            line_mm_s = sum(s[0] for s in rotary_sim_state["speed_samples"]) / len(rotary_sim_state["speed_samples"])
            drum_mm_s = sum(s[1] for s in rotary_sim_state["speed_samples"]) / len(rotary_sim_state["speed_samples"])

        if line_mspeed is None:
            rotary_line_speed_label.value = "--"
        else:
            rotary_line_speed_label.value = f"{line_mspeed:.3f} u/s -> {line_mspeed * link_units_to_mm:.3f} mm/s"

        if drum_mm_s is None:
            rotary_drum_speed_label.value = "--"
            rotary_drum_speed_label.color = MUTED_TEXT
        elif speed_warning:
            rotary_drum_speed_label.value = f"WARN {drum_mm_s:.0f} mm/s"
            rotary_drum_speed_label.color = ERROR_COLOR
        else:
            rotary_drum_speed_label.value = f"{drum_mm_s:.3f} mm/s"
            rotary_drum_speed_label.color = ft.Colors.ORANGE_200

        if in_cut:
            rotary_cut_status_label.value = "In cut"
            rotary_cut_status_label.color = SUCCESS_COLOR
        elif approaching:
            rotary_cut_status_label.value = "Approaching"
            rotary_cut_status_label.color = WARNING_COLOR
        else:
            rotary_cut_status_label.value = "Outside"
            rotary_cut_status_label.color = MUTED_TEXT

        if in_cut and line_mm_s is not None and drum_mm_s is not None and not speed_warning:
            delta = line_mm_s - drum_mm_s
            denom = abs(line_mm_s) if abs(line_mm_s) > 1e-9 else 1.0
            pct = abs(delta) / denom * 100.0
            green_pct = max(0.1, rotary_setting_float("match_tolerance_pct", 2.0))
            amber_pct = max(5.0, green_pct * 2.5)
            rotary_match_delta_label.value = f"{delta:+.3f} mm/s ({pct:.1f}%)"
            if pct < green_pct:
                rotary_match_delta_label.color = SUCCESS_COLOR
            elif pct < amber_pct:
                rotary_match_delta_label.color = WARNING_COLOR
            else:
                rotary_match_delta_label.color = ERROR_COLOR
        else:
            rotary_match_delta_label.value = "--"
            rotary_match_delta_label.color = MUTED_TEXT

        if rotary_sim_state.get("units_error"):
            rotary_status_text.value = rotary_sim_state["units_error"]
            rotary_status_text.color = ERROR_COLOR
        elif speed_warning:
            rotary_status_text.value = speed_warning
            rotary_status_text.color = WARNING_COLOR
        elif rotary_sim_state.get("units_warning"):
            rotary_status_text.value = rotary_sim_state["units_warning"]
            rotary_status_text.color = WARNING_COLOR
        elif trio_conn.is_connected():
            rotary_status_text.value = "Live MPOS and DEMAND_SPEED from controller."
            rotary_status_text.color = SUCCESS_COLOR
        else:
            rotary_status_text.value = "Not connected; static schematic."
            rotary_status_text.color = MUTED_TEXT

        update_rotary_units_label()
        update_rotary_debug_overlay()
        return True

    def update_rotary_sim_from_reads(line_mpos, drum_mpos, line_mspeed, drum_mspeed, drum_demand_speed, now):
        dirty = False
        if line_mspeed is not None:
            rotary_sim_state["line_mspeed"] = line_mspeed
        if drum_mspeed is not None:
            rotary_sim_state["drum_mspeed"] = drum_mspeed
        if drum_demand_speed == "ERR":
            rotary_sim_state["drum_demand_speed"] = None
            rotary_sim_state["drum_tangential_mm_s"] = None
        elif drum_demand_speed is not None:
            rotary_sim_state["drum_demand_speed"] = drum_demand_speed

        if line_mpos is not None:
            rotary_sim_state["line_mpos"] = line_mpos
            if position_zero_m[0] is None:
                position_zero_m[0] = line_mpos
            delta = line_mpos - position_zero_m[0]
            rotary_sim_state["belt_offset_px"] = (
                CONVEYOR_VISUAL_DIRECTION * delta * scale_px_per_unit[0]
            ) % BELT_SPACING
            dirty = True

        mpos_per_rev = rotary_recompute_mpos_per_rev()
        if drum_mpos is not None:
            rotary_sim_state["drum_mpos"] = drum_mpos
            if mpos_per_rev and mpos_per_rev != 0:
                try:
                    kinematics = compute_rotary_drum_kinematics(
                        drum_mpos,
                        rotary_sim_state.get("drum_mspeed"),
                        mpos_per_rev,
                        cam_setting_float("drum_dia", 200.0),
                        rotary_drum_direction_reversed(),
                    )
                    rotary_sim_state["last_kinematics"] = kinematics
                    angle = kinematics.get("drum_angle_rad")
                    if angle is not None:
                        rotary_sim_state["drum_angle"] = angle
                except ValueError:
                    rotary_sim_state["last_kinematics"] = None
            dirty = True

        if dirty:
            redraw_rotary_sim()
        if update_rotary_diagnostics(now):
            dirty = True
        return dirty

    def on_rotary_reverse_change(e):
        rotary_sim_settings["drum_direction_reversed"] = bool(e.control.value)
        rotary_sim_state["speed_samples"].clear()
        save_settings(settings)
        drum_mpos = rotary_sim_state.get("drum_mpos")
        if drum_mpos is not None:
            update_rotary_sim_from_reads(None, drum_mpos, None, None, None, time.perf_counter())
        else:
            redraw_rotary_sim()
            update_rotary_diagnostics(time.perf_counter())
        page.update()

    def on_rotary_link_units_change(e):
        try:
            val = float(e.control.value or "1.0")
            if val <= 0:
                raise ValueError
            rotary_sim_settings["link_units_to_mm"] = val
            save_settings(settings)
        except ValueError:
            rotary_status_text.value = "Link units to mm must be > 0."
            rotary_status_text.color = ERROR_COLOR
        update_rotary_diagnostics(time.perf_counter())
        page.update()

    def on_rotary_override_change(e):
        text = (e.control.value or "").strip()
        if text == "":
            rotary_sim_settings[ROTARY_MPOS_OVERRIDE_KEY] = None
            request_rotary_units_refresh()
        else:
            try:
                val = float(text)
                if val <= 0:
                    raise ValueError
                rotary_sim_settings[ROTARY_MPOS_OVERRIDE_KEY] = val
                rotary_recompute_mpos_per_rev()
                rotary_sim_state["speed_samples"].clear()
            except ValueError:
                rotary_status_text.value = "Drum MPOS/rev override must be blank or > 0."
                rotary_status_text.color = ERROR_COLOR
                page.update()
                return
        save_settings(settings)
        update_rotary_units_label()
        redraw_rotary_sim()
        page.update()

    def on_rotary_debug_change(e):
        rotary_sim_settings["show_debug"] = bool(e.control.value)
        save_settings(settings)
        update_rotary_debug_overlay()
        page.update()

    def on_rotary_tolerance_change(e):
        try:
            val = float(e.control.value or "2.0")
            if val <= 0:
                raise ValueError
            rotary_sim_settings["match_tolerance_pct"] = val
            save_settings(settings)
        except ValueError:
            rotary_status_text.value = "Match tolerance must be > 0%."
            rotary_status_text.color = ERROR_COLOR
        update_rotary_diagnostics(time.perf_counter())
        page.update()

    def make_rotary_axis_dropdown(label, value, handler, width):
        dd = ft.Dropdown(
            label=label, width=width, height=45,
            options=[ft.dropdown.Option(str(i), f"Axis {i}") for i in range(16)],
            value=value,
            bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=BORDER_COLOR,
            focused_border_color=ACCENT_COLOR,
            text_size=12, on_select=handler,
        )
        return dd

    def make_rotary_motion_button(text, icon, color, command, tooltip):
        return ft.FilledButton(
            text,
            icon=icon,
            on_click=lambda e: _send_master_cmd(command),
            disabled=not trio_conn.is_connected(),
            style=ft.ButtonStyle(bgcolor=color, color=ft.Colors.WHITE),
            height=38,
            tooltip=tooltip,
        )

    def make_cutter_lamp_panel_clone():
        op_text = ft.Text("OP --", size=11, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
        caption_text = ft.Text("NO DATA", size=10, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
        bulb = ft.Container(
            width=36,
            height=36,
            border_radius=18,
            gradient=ft.RadialGradient(
                center=ft.Alignment(-0.38, -0.42),
                radius=0.9,
                colors=["#515a55", "#26302b", "#111615"],
                stops=[0.0, 0.58, 1.0],
            ),
            border=ft.Border.all(1, "#48534e"),
            shadow=[ft.BoxShadow(spread_radius=0, blur_radius=8, color="#30323a36", offset=ft.Offset(0, 0))],
        )
        lamp = ft.Container(
            width=54,
            height=54,
            padding=5,
            bgcolor="#0b1110",
            border_radius=27,
            border=ft.Border.all(1, "#2c3a34"),
            content=bulb,
            alignment=ft.Alignment(0, 0),
            tooltip="Knife output state unavailable",
        )
        extra_cutter_lamp_widgets.append({
            "op_text": op_text,
            "caption_text": caption_text,
            "bulb": bulb,
            "lamp": lamp,
        })
        return ft.Container(
            content=ft.Row(
                [
                    lamp,
                    ft.Column([op_text, caption_text], spacing=1, tight=True,
                              alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            padding=ft.Padding(8, 6, 10, 6),
            border_radius=8,
            bgcolor="#121a16",
            border=ft.Border.all(1, "#263b2f"),
            width=170,
        )

    rotary_axis_m_dropdown = make_rotary_axis_dropdown(
        "Material / encoder axis",
        settings.get("master_axis", "0"),
        on_axis_m_change,
        150,
    )
    axis_m_bound_controls.append(rotary_axis_m_dropdown)

    rotary_axis_s_dropdown = make_rotary_axis_dropdown(
        "Drum axis",
        settings.get("slave_axis", "1"),
        on_axis_s_change,
        125,
    )
    axis_s_bound_controls.append(rotary_axis_s_dropdown)

    rotary_cutter_output_input = ft.TextField(
        label="Knife OP",
        value=str(settings.get("cutter_output", "8")),
        width=125,
        height=45,
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13,
        on_change=on_cutter_output_change,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        tooltip="Controller digital output number used for knife OP() and live output-state read",
    )
    cutter_output_inputs.append(rotary_cutter_output_input)

    rotary_master_speed_input = ft.TextField(
        label="Conveyor speed",
        value=format_conveyor_speed(clamp_conveyor_speed(get_saved_conveyor_speed())),
        width=140,
        height=45,
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        suffix="u/s",
        text_size=12,
        on_change=on_master_speed_change,
        on_blur=lambda e: normalize_conveyor_speed_input(e.control),
        on_submit=lambda e: _send_master_speed(),
        tooltip="Conveyor axis SPEED set before Forward/Reverse",
    )
    master_speed_inputs.append(rotary_master_speed_input)

    rotary_master_speed_slider = ft.Slider(
        min=0,
        max=get_conveyor_speed_max(),
        value=clamp_conveyor_speed(float(rotary_master_speed_input.value or 0)),
        width=230,
        label="{value} u/s",
        round=1,
        active_color=ft.Colors.CYAN_300,
        inactive_color=ft.Colors.GREY_700,
        thumb_color=ft.Colors.CYAN_200,
        on_change=on_master_speed_slider_change,
        on_change_end=lambda e: _send_master_speed(),
        tooltip="Limited by the calculator MAX line speed",
    )
    master_speed_sliders.append(rotary_master_speed_slider)

    rotary_master_fwd_btn = make_rotary_motion_button(
        "Forward", ft.Icons.PLAY_ARROW, ft.Colors.GREEN_700,
        "forward", "Forward(master) - continuous move forward",
    )
    rotary_master_rev_btn = make_rotary_motion_button(
        "Reverse", ft.Icons.ARROW_BACK, ft.Colors.BLUE_GREY_700,
        "reverse", "Reverse(master) - continuous move reverse",
    )
    rotary_master_stop_btn = make_rotary_motion_button(
        "Stop", ft.Icons.STOP, ft.Colors.RED_700,
        "cancel", "Cancel(2, master) - stop buffered + current move",
    )
    rotary_motion_buttons.extend([rotary_master_fwd_btn, rotary_master_rev_btn, rotary_master_stop_btn])

    rotary_scale_value_label = ft.Text(
        f"{scale_px_per_unit[0]:g} px/unit",
        size=12,
        color=ft.Colors.CYAN_200,
        weight=ft.FontWeight.BOLD,
        width=90,
    )
    rotary_recenter_btn = ft.IconButton(
        icon=ft.Icons.CENTER_FOCUS_STRONG,
        tooltip="Re-center on current position",
        on_click=on_recenter,
    )
    rotary_scale_minus_btn = ft.IconButton(
        icon=ft.Icons.REMOVE,
        icon_size=18,
        tooltip="Decrease scale by 1",
        on_click=on_scale_step(-1),
    )
    rotary_scale_plus_btn = ft.IconButton(
        icon=ft.Icons.ADD,
        icon_size=18,
        tooltip="Increase scale by 1",
        on_click=on_scale_step(1),
    )
    rotary_scale_minus10_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=18,
        tooltip="Decrease scale by 10",
        on_click=on_scale_step(-10),
    )
    rotary_scale_plus10_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT,
        icon_size=18,
        tooltip="Increase scale by 10",
        on_click=on_scale_step(10),
    )

    rotary_reverse_checkbox = ft.Checkbox(
        label="Reverse drum direction",
        value=bool(rotary_sim_settings.get("drum_direction_reversed", False)),
        fill_color=ft.Colors.BLUE_700,
        check_color=ft.Colors.WHITE,
        on_change=on_rotary_reverse_change,
        tooltip="Flip MPOS-to-angle sign if encoder polarity is opposite to the visual",
    )
    rotary_link_units_input = ft.TextField(
        label="Link units to mm",
        value=str(rotary_sim_settings.get("link_units_to_mm", 1.0)),
        width=145,
        height=45,
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        suffix="mm/u",
        text_size=12,
        on_blur=on_rotary_link_units_change,
        on_submit=on_rotary_link_units_change,
        tooltip="Multiplier from material-axis user units to millimeters",
    )
    rotary_mpos_override_input = ft.TextField(
        label="MPOS counts/rev override",
        value="" if rotary_sim_settings.get(ROTARY_MPOS_OVERRIDE_KEY) is None else str(rotary_sim_settings.get(ROTARY_MPOS_OVERRIDE_KEY)),
        width=190,
        height=45,
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        text_size=12,
        on_blur=on_rotary_override_change,
        on_submit=on_rotary_override_change,
        tooltip="Blank = auto from drum axis CPR / drum axis UNITS",
    )
    rotary_tolerance_input = ft.TextField(
        label="Match green tol",
        value=str(rotary_sim_settings.get("match_tolerance_pct", 2.0)),
        width=135,
        height=45,
        bgcolor=DARKER_BG,
        color=TEXT_COLOR,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_COLOR,
        keyboard_type=ft.KeyboardType.NUMBER,
        suffix="%",
        text_size=12,
        on_blur=on_rotary_tolerance_change,
        on_submit=on_rotary_tolerance_change,
        tooltip="Green tangential-speed match tolerance while knife is in the cut window",
    )
    rotary_refresh_units_btn = ft.OutlinedButton(
        "Refresh",
        icon=ft.Icons.REFRESH,
        height=38,
        on_click=refresh_rotary_drum_units,
        tooltip="Read drum axis CPR and UNITS, then recompute MPOS per revolution",
    )
    rotary_debug_checkbox = ft.Checkbox(
        label="Show debug",
        value=bool(rotary_sim_settings.get("show_debug", False)),
        fill_color=ft.Colors.BLUE_700,
        check_color=ft.Colors.WHITE,
        on_change=on_rotary_debug_change,
        tooltip="Show raw drum MPOS/MSPEED conversion values",
    )

    rotary_comms_lag_label = ft.Text("MPOS read: -- ms (avg 100)", size=10, color=ft.Colors.GREY_500)
    rotary_fps_label = ft.Text("0 FPS", size=10, color=ft.Colors.GREY_500)
    rotary_status_text = ft.Text("Not connected; static schematic.", size=13, color=MUTED_TEXT, width=520)
    rotary_line_speed_label = ft.Text("--", size=15, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD)
    rotary_drum_speed_label = ft.Text("--", size=15, color=ft.Colors.ORANGE_200, weight=ft.FontWeight.BOLD)
    rotary_match_delta_label = ft.Text("--", size=15, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
    rotary_cut_status_label = ft.Text("Outside", size=15, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
    rotary_encoder_cpr_label = ft.Text("--", size=15, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
    rotary_drum_units_label = ft.Text("--", size=15, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
    rotary_mpos_per_rev_label = ft.Text("--", size=15, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)
    rotary_units_source_label = ft.Text("not read", size=10, color=MUTED_TEXT)
    rotary_debug_text = ft.Text(
        "",
        size=12,
        color=ft.Colors.GREY_300,
        font_family="Consolas",
        selectable=True,
    )
    rotary_debug_container = ft.Container(
        content=rotary_debug_text,
        visible=bool(rotary_sim_settings.get("show_debug", False)),
        bgcolor=DARKER_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=12,
    )

    rotary_sim_canvas = cv.Canvas(
        width=visual_width,
        height=ROTARY_SIM_HEIGHT,
        shapes=[],
    )
    rotary_sim_canvas_holder = ft.Container(
        content=rotary_sim_canvas,
        width=visual_width,
        height=ROTARY_SIM_HEIGHT,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        bgcolor=DARKER_BG,
    )

    rotary_controls_grid = ft.ResponsiveRow(
        [
            control_cluster(
                "Axes & knife",
                [rotary_axis_m_dropdown, rotary_axis_s_dropdown,
                 rotary_cutter_output_input, make_cutter_lamp_panel_clone()],
                icon=ft.Icons.ACCOUNT_TREE,
                col={"xs": 12, "lg": 5},
            ),
            control_cluster(
                "Conveyor jog",
                [rotary_master_rev_btn, rotary_master_fwd_btn, rotary_master_stop_btn,
                 rotary_master_speed_input, rotary_master_speed_slider],
                icon=ft.Icons.PLAY_ARROW,
                col={"xs": 12, "lg": 7},
            ),
            control_cluster(
                "Visual scale",
                [rotary_recenter_btn,
                 ft.Text("Scale:", size=12, color=ft.Colors.GREY_400),
                 rotary_scale_minus10_btn, rotary_scale_minus_btn,
                 rotary_scale_plus_btn, rotary_scale_plus10_btn,
                 rotary_scale_value_label],
                icon=ft.Icons.ZOOM_OUT_MAP,
                col={"xs": 12, "lg": 5},
            ),
            control_cluster(
                "Simulation setup",
                [rotary_reverse_checkbox, rotary_link_units_input,
                 rotary_mpos_override_input, rotary_tolerance_input,
                 rotary_refresh_units_btn, rotary_debug_checkbox],
                icon=ft.Icons.SETTINGS,
                col={"xs": 12, "lg": 7},
            ),
        ],
        columns=12,
        spacing=10,
        run_spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    rotary_diag_strip = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.SHOW_CHART, size=14, color=MUTED_TEXT),
                    ft.Text(
                        "LIVE READINGS",
                        size=10,
                        color=MUTED_TEXT,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    rotary_diag_card("Line speed", rotary_line_speed_label, 230),
                    rotary_diag_card("Cut zone", rotary_cut_status_label, 150),
                    rotary_diag_card(
                        "MPOS cnts per physical rev",
                        rotary_mpos_per_rev_label,
                        245,
                    ),
                ],
                wrap=True,
                spacing=10,
                run_spacing=10,
            ),
        ],
        spacing=8,
        tight=True,
    )

    rotary_sim_container = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        section_header("Rotary Knife Simulation",
                                       "Live drum geometry from CAMBOX axes",
                                       ft.Icons.AUTORENEW),
                        ft.Row(
                            [rotary_status_text,
                             ft.Text("|", size=10, color=ft.Colors.GREY_700),
                             rotary_comms_lag_label,
                             ft.Text("|", size=10, color=ft.Colors.GREY_700),
                             rotary_fps_label],
                            wrap=True,
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                rotary_sim_canvas_holder,
                rotary_controls_grid,
                rotary_diag_strip,
                rotary_debug_container,
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
        ),
        bgcolor=PANEL_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=20,
    )

    def resize_rotary_sim_visual(update=False):
        new_visual_width = _available_visual_width()
        rotary_sim_canvas.width = new_visual_width
        rotary_sim_canvas_holder.width = new_visual_width
        redraw_rotary_sim()
        if update:
            _update_if_mounted(rotary_sim_canvas_holder)

    apply_saved_rotary_units_fallback(int(axis_s_dropdown.value or "1"))
    redraw_rotary_sim()
    update_rotary_debug_overlay()

    connection_panel = ft.Container(
        content=ft.Column(
            [
                section_header("Controller Connection", "Connect first, then verify watchdog and saved parameters", ft.Icons.LAN),
                conn_row,
            ],
            spacing=12,
        ),
        bgcolor=PANEL_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=16,
        col={"xs": 12, "lg": 7},
    )

    axis_connection_page = ft.Container(
        content=ft.Column(
            [
                ft.ResponsiveRow(
                    [connection_panel, params_panel],
                    columns=12,
                    spacing=14,
                    run_spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                section_header("Axis Configuration", "Tune and save controller parameters per axis", ft.Icons.TUNE),
                setup_container,
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=20,
        expand=True,
    )

    flying_shear_monitor_page = ft.Container(
        content=ft.Column([monitor_container], spacing=14, scroll=ft.ScrollMode.AUTO),
        padding=20,
        expand=True,
    )

    def build_solution_tabs(solution):
        if solution == "rotary_knife":
            tab_specs = [
                (
                    ft.Tab(label="Rotary Knife Sim", icon=ft.Icons.AUTORENEW),
                    ft.Container(content=rotary_sim_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="Rotary Knife Cam", icon=ft.Icons.AUTORENEW),
                    ft.Container(content=cam_calc_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="Cam Math Help", icon=ft.Icons.FUNCTIONS),
                    rotary_cam_math_help_list,
                ),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    axis_connection_page,
                ),
            ]
        else:
            tab_specs = [
                (
                    ft.Tab(label="Configure Shear", icon=ft.Icons.CALCULATE),
                    ft.Container(
                        content=ft.Column([shear_calc_container], spacing=14, scroll=ft.ScrollMode.AUTO),
                        padding=20,
                        expand=True,
                    ),
                ),
                (ft.Tab(label="MoveLink Help", icon=ft.Icons.FUNCTIONS), movelink_help_list),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    axis_connection_page,
                ),
                (ft.Tab(label="Live Monitor", icon=ft.Icons.ANALYTICS), flying_shear_monitor_page),
            ]

        return ft.Tabs(
            length=len(tab_specs),
            selected_index=0,
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[tab for tab, _ in tab_specs],
                        label_color=ft.Colors.CYAN_200,
                        unselected_label_color=MUTED_TEXT,
                        indicator_color=ACCENT_COLOR,
                        divider_color=BORDER_COLOR,
                    ),
                    ft.TabBarView(
                        controls=[content for _, content in tab_specs],
                        expand=1,
                    ),
                ],
                expand=1,
            ),
            expand=1,
        )

    app_root = ft.Container(expand=True)

    def set_workspace_appbar(solution_name):
        page.appbar = ft.AppBar(
            title=ft.Text(f"Trio {solution_name} Setup", size=18, weight=ft.FontWeight.BOLD),
            bgcolor=PANEL_BG,
            color=ft.Colors.WHITE,
            elevation=0,
            actions=[
                ft.TextButton(
                    "Change solution",
                    icon=ft.Icons.SWAP_HORIZ,
                    on_click=lambda e: show_solution_picker(),
                    style=ft.ButtonStyle(color=ft.Colors.CYAN_200),
                ),
                ft.Container(
                    content=ft.Text(solution_name, size=12, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD),
                    padding=ft.Padding.only(right=16),
                    alignment=ft.Alignment.CENTER,
                ),
            ],
        )

    def show_solution_workspace(solution):
        solution_name = "Rotary Knife" if solution == "rotary_knife" else "Flying Shear"
        page.title = f"Trio {solution_name} Setup"
        set_workspace_appbar(solution_name)
        app_root.content = build_solution_tabs(solution)
        page.update()

    def solution_card(label, subtitle, icon, solution):
        base_bg = PANEL_BG
        base_border = BORDER_COLOR
        hover_bg = "#262b32"
        hover_border = ACCENT_COLOR

        icon_badge = ft.Container(
            content=ft.Icon(icon, size=30, color=ft.Colors.CYAN_200),
            width=58,
            height=58,
            bgcolor=PANEL_ALT_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=14,
            alignment=ft.Alignment.CENTER,
        )

        cta = ft.Row(
            [
                ft.Text("Configure", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_200),
                ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=ft.Colors.CYAN_200),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        card = ft.Container(
            content=ft.Column(
                [
                    icon_badge,
                    ft.Container(height=2),
                    ft.Text(label, size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text(subtitle, size=13, color=MUTED_TEXT, max_lines=3),
                    ft.Container(expand=True),
                    cta,
                ],
                spacing=8,
                expand=True,
            ),
            width=320,
            height=270,
            padding=ft.Padding.all(22),
            bgcolor=base_bg,
            border=ft.Border.all(1, base_border),
            border_radius=14,
            on_click=lambda e: show_solution_workspace(solution),
            ink=True,
            animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
        )

        def _on_hover(e):
            hovered = e.data == "true"
            card.bgcolor = hover_bg if hovered else base_bg
            card.border = ft.Border.all(1, hover_border if hovered else base_border)
            card.update()

        card.on_hover = _on_hover
        return card

    def show_solution_picker():
        page.title = "Trio Motion Setup"
        page.appbar = None

        hero = ft.Column(
            [
                ft.Text(
                    "Trio Motion Setup",
                    size=34,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                ft.Text(
                    "Choose a motion solution to begin configuring the controller.",
                    size=14,
                    color=MUTED_TEXT,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

        cards = ft.Row(
            [
                solution_card(
                    "Flying Shear",
                    "Linear cut-on-the-fly with a matched-speed shear axis driven by a MOVELINK profile.",
                    ft.Icons.CONTENT_CUT,
                    "flying_shear",
                ),
                solution_card(
                    "Rotary Knife",
                    "Continuous rotary drum knife synchronised to the line via CAMBOX.",
                    ft.Icons.AUTORENEW,
                    "rotary_knife",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            wrap=True,
            run_spacing=20,
        )

        app_root.content = ft.Container(
            content=ft.Column(
                [hero, cards],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=32,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=24, vertical=24),
        )
        page.update()

    # Clean up monitor on window close
    async def on_window_event(e):
        nonlocal monitor_running

        if e.type != ft.WindowEventType.CLOSE:
            return

        monitor_running = False

        loop = asyncio.get_running_loop()

        # Trio UAPI is COM/STA-thread-affine — disconnect must run on the
        # same pinned worker that opened the connection, not the UI thread.
        try:
            if trio_conn.connection:
                await asyncio.wait_for(
                    loop.run_in_executor(uapi_executor, trio_conn.disconnect),
                    timeout=5,
                )
        except Exception as ex:
            print(f"Error disconnecting on close: {ex}")

        try:
            uapi_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        await page.window.destroy()

    page.window.prevent_close = True
    page.window.on_event = on_window_event

    def on_page_resize(e):
        resize_shear_visual(update=True)
        resize_rotary_sim_visual(update=True)

    page.on_resize = on_page_resize

    page.add(
        ft.SafeArea(
            content=app_root,
            minimum_padding=ft.Padding.only(left=16, right=16, bottom=16),
            expand=True,
        )
    )
    show_solution_picker()

if __name__ == "__main__":
    ft.run(main)
