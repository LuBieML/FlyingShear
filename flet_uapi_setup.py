import flet as ft
import collections
import sys
import os
import json
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
    page.title = "Trio UAPI Setup App"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.window_width = 1920
    page.window_height = 1050

    # Aesthetics to match the GCode interpreter dark mode
    DARK_BG = "#1e1e1e"
    DARKER_BG = "#121212"
    ACCENT_COLOR = "#007acc"
    TEXT_COLOR = "#d4d4d4"

    page.bgcolor = DARK_BG

    # Load persisted settings
    settings = load_settings()

    # Initialize the TrioConnection
    trio_conn = TrioConnection(status_callback=lambda msg, type_: print(f"[{type_}] {msg}"))

    # status_callback may be invoked from the pinned UAPI worker thread (e.g. during
    # connect()), so UI mutations must be marshalled back to the Flet event loop.
    ui_loop_holder = {"loop": None}

    def status_callback(msg, type_):
        def update_status():
            status_text.value = msg
            status_text.color = ft.Colors.RED if type_ == "error" else (ft.Colors.ORANGE if type_ == "warning" else ft.Colors.WHITE)
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
            status_text.color = ft.Colors.RED
            connect_btn.disabled = False
            ip_input.disabled = False
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

    # Axis Selectors
    def on_axis_m_change(e):
        settings["master_axis"] = e.control.value
        save_settings(settings)
        try:
            recalc()
        except NameError:
            pass

    def on_axis_s_change(e):
        settings["slave_axis"] = e.control.value
        save_settings(settings)
        try:
            recalc()
        except NameError:
            pass

    axis_m_dropdown = ft.Dropdown(
        label="Master Axis", width=110, height=45,
        options=[ft.dropdown.Option(str(i), f"Axis {i}") for i in range(16)],
        value=settings.get("master_axis", "0"),
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=ft.Colors.GREY_800,
        text_size=12, on_select=on_axis_m_change
    )

    axis_s_dropdown = ft.Dropdown(
        label="Slave Axis", width=110, height=45,
        options=[ft.dropdown.Option(str(i), f"Axis {i}") for i in range(16)],
        value=settings.get("slave_axis", "1"),
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=ft.Colors.GREY_800,
        text_size=12, on_select=on_axis_s_change
    )

    def on_master_speed_change(e):
        settings["master_speed"] = e.control.value
        save_settings(settings)

    master_speed_input = ft.TextField(
        label="Speed", value=settings.get("master_speed", "10.0"),
        width=100, height=45,
        bgcolor=DARKER_BG, color=TEXT_COLOR, border_color=ft.Colors.GREY_800,
        text_size=12, on_change=on_master_speed_change,
        tooltip="Master axis SPEED set before Forward/Reverse",
    )

    # --- Master axis Forward / Reverse / Cancel buttons ---
    # Mirrors the gcode parser's jog commands (machine_controller.start_jog / stop_jog):
    #   Forward(axis), Reverse(axis), Cancel(2, axis)
    # Cancel mode 2 stops both buffered and current move. All UAPI calls dispatched
    # via uapi_executor to preserve COM thread-affinity.
    def _send_master_cmd(cmd):
        try:
            axis_m_val = int(axis_m_dropdown.value or "0")
        except ValueError:
            return

        try:
            speed_val = float(master_speed_input.value or "10.0")
        except ValueError:
            speed_val = 10.0

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

    master_fwd_btn = ft.FilledButton(
        "Start ▶", on_click=lambda e: _send_master_cmd("forward"),
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
        height=38, tooltip="Forward(master) — continuous move forward",
    )
    master_rev_btn = ft.FilledButton(
        "◀ Reverse", on_click=lambda e: _send_master_cmd("reverse"),
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_700, color=ft.Colors.WHITE),
        height=38, tooltip="Reverse(master) — continuous move reverse",
    )
    master_stop_btn = ft.FilledButton(
        "Stop ■", on_click=lambda e: _send_master_cmd("cancel"),
        style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE),
        height=38, tooltip="Cancel(2, master) — stop buffered + current move",
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
    TRACK_WIDTH = 1540
    TRACK_HEIGHT = 24
    BELT_HEIGHT = 24
    CLEAT_HEIGHT = 18
    BELT_SPACING = 70
    CLEAT_WIDTH = 10
    NUM_BELT_ITEMS = (TRACK_WIDTH // BELT_SPACING) + 1
    WRAP_WIDTH = NUM_BELT_ITEMS * BELT_SPACING
    RAIL_HEIGHT = 4
    PULLEY_SIZE = 36
    CONVEYOR_HEIGHT = PULLEY_SIZE + 2 * (RAIL_HEIGHT + 1)

    # --- Shear/cutter graphic (Slave axis) ---
    SHEAR_WIDTH = 24
    SHEAR_HEIGHT = 52
    MOUNT_HEIGHT = 12
    BLADE_TIP_H = 12
    SHEAR_TRACK_HEIGHT = 90
    SHEAR_TOP_IDLE = 6
    CENTER_LEFT_S = TRACK_WIDTH / 2 - SHEAR_WIDTH / 2
    SHEAR_START_LEFT = 38  # ~1 cm from left; position-zero reference for slave visualizer

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
        blade_body_h = SHEAR_HEIGHT - MOUNT_HEIGHT - BLADE_TIP_H
        mount = ft.Container(
            width=SHEAR_WIDTH, height=MOUNT_HEIGHT,
            bgcolor="#2a2a2a",
            border=ft.Border.all(1, "#505050"),
            border_radius=ft.BorderRadius.only(top_left=3, top_right=3),
            top=0, left=0,
        )
        blade_body = ft.Container(
            width=SHEAR_WIDTH, height=blade_body_h,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                colors=["#5a5a5a", "#b4b4b4", "#ececec", "#b4b4b4", "#5a5a5a"],
                stops=[0.0, 0.25, 0.5, 0.75, 1.0],
            ),
            border=ft.Border.only(
                left=ft.BorderSide(1, "#404040"),
                right=ft.BorderSide(1, "#404040"),
            ),
            top=MOUNT_HEIGHT, left=0,
        )
        blade_tip = ft.Container(
            width=SHEAR_WIDTH, height=BLADE_TIP_H,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                colors=["#909090", "#383838", "#080808"],
                stops=[0.0, 0.55, 1.0],
            ),
            border_radius=ft.BorderRadius.only(bottom_left=2, bottom_right=2),
            top=SHEAR_HEIGHT - BLADE_TIP_H, left=0,
        )
        groove = ft.Container(
            width=2, height=blade_body_h - 6,
            bgcolor="#585858",
            border_radius=1,
            left=(SHEAR_WIDTH - 2) / 2,
            top=MOUNT_HEIGHT + 3,
        )

        indicator = ft.Container(
            content=ft.Stack(
                [blade_body, blade_tip, mount, groove],
                width=SHEAR_WIDTH, height=SHEAR_HEIGHT,
            ),
            width=SHEAR_WIDTH, height=SHEAR_HEIGHT,
            left=SHEAR_START_LEFT,
            top=SHEAR_TOP_IDLE,
        )

        track = ft.Stack(
            [
                ft.Container(width=TRACK_WIDTH, height=SHEAR_TRACK_HEIGHT,
                             bgcolor=DARKER_BG,
                             border=ft.Border.all(1, ft.Colors.GREY_800), border_radius=4),
                ft.Container(width=TRACK_WIDTH, height=2,
                             bgcolor=ft.Colors.with_opacity(0.35, color),
                             top=SHEAR_TRACK_HEIGHT - 10),
                indicator,
            ],
            width=TRACK_WIDTH, height=SHEAR_TRACK_HEIGHT,
        )
        return indicator, track

    belt_items_m, track_m = create_conveyor_track(ft.Colors.CYAN_300)
    indicator_s, track_s = create_shear_track(ft.Colors.ORANGE_300)

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
        settings["scale_px_per_unit"] = new_val
        save_settings(settings)
        scale_value_label.update()

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

        def _batch_read(axis_m, axis_s, read_slow_params):
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
                dirty = False
                fps_timestamps.append(frame_start)
                frame_counter += 1
                read_slow = (frame_counter % 3 == 0)

                # Single thread-crossing call for ALL reads
                results, mpos_t = await loop.run_in_executor(
                    uapi_executor, _batch_read, axis_m_val, axis_s_val, read_slow
                )

                if results is None:
                    await asyncio.sleep(0.1)
                    continue

                if mpos_t is not None:
                    comms_lag_samples.append(mpos_t)

                mpos_val_m = None
                mpos_val_s = None

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
                        txt = mon_vals[pn]
                        if txt.value != new_val:
                            txt.value = new_val
                            dirty = True

                # Update comms lag (rolling average of MPOS read)
                if comms_lag_samples:
                    avg_ms = sum(comms_lag_samples) / len(comms_lag_samples)
                    lag_str = f"MPOS read: {avg_ms:.1f} ms (avg {len(comms_lag_samples)})"
                    if comms_lag_label.value != lag_str:
                        comms_lag_label.value = lag_str
                        dirty = True

                # Update Master visualizer
                if mpos_val_m is not None:
                    if position_zero_m[0] is None:
                        position_zero_m[0] = mpos_val_m
                    delta = mpos_val_m - position_zero_m[0]
                    offset_px = delta * scale_px_per_unit[0]
                    for i, item in enumerate(belt_items_m):
                        new_left = (offset_px + i * BELT_SPACING) % WRAP_WIDTH - CLEAT_WIDTH
                        if abs((item.left or 0) - new_left) > 0.1:
                            item.left = new_left
                            dirty = True

                # Update Slave visualizer — absolute MPOS maps directly to pixel position
                if mpos_val_s is not None:
                    new_left = SHEAR_START_LEFT + mpos_val_s * scale_px_per_unit[0]
                    new_left = max(0, min(TRACK_WIDTH - SHEAR_WIDTH, new_left))
                    if abs((indicator_s.left or 0) - new_left) > 0.1:
                        indicator_s.left = new_left
                        dirty = True

                # Update FPS display
                if len(fps_timestamps) >= 2:
                    span = fps_timestamps[-1] - fps_timestamps[0]
                    if span > 0:
                        current_fps = (len(fps_timestamps) - 1) / span
                        fps_str = f"{current_fps:.0f} FPS"
                        if fps_label.value != fps_str:
                            fps_label.value = fps_str
                            dirty = True

                if dirty and frame_counter % ui_update_every == 0:
                    monitor_container.update()
                    # params_panel lives outside monitor_container (in the
                    # connection header row), so it needs its own update.
                    params_panel.update()
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
        bgcolor=DARKER_BG,
        border_radius=10,
        padding=15,
        border=ft.Border.all(1, ft.Colors.GREY_800),
    )

    monitor_container = ft.Container(
        content=ft.Column([
            ft.Row(
                [
                    ft.Text("Flying Shear Live Monitor", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    axis_m_dropdown,
                    axis_s_dropdown,
                    master_rev_btn,
                    master_fwd_btn,
                    master_stop_btn,
                    master_speed_input,
                    ft.Container(expand=True),  # push stats right
                    comms_lag_label,
                    ft.Text("|", size=10, color=ft.Colors.GREY_700),
                    fps_label,
                ],
                spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            ft.Container(height=14),
            ft.Row(
                [recenter_btn,
                 ft.Text("Scale:", size=12, color=ft.Colors.GREY_400),
                 scale_minus10_btn, scale_minus_btn,
                 scale_plus_btn, scale_plus10_btn,
                 scale_value_label],
                vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
            ),
            track_s,
            ft.Container(height=10),
            track_m,
        ]),
        bgcolor=DARKER_BG,
        border_radius=10,
        padding=20,
        border=ft.Border.all(1, ft.Colors.GREY_800),
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
        border_color=ft.Colors.GREY_800,
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
        page.update()

        loop = asyncio.get_running_loop()
        try:
            success = await loop.run_in_executor(uapi_executor, trio_conn.connect, ip_input.value)
        except Exception as ex:
            print(f"Connect error: {ex}")
            success = False

        if success:
            status_text.value = "Connected Successfully!"
            status_text.color = ft.Colors.GREEN
            connect_btn.disabled = True
            ip_input.disabled = True
            page.update()

            # Apply saved JSON parameters before starting the live monitor so
            # UAPI writes and reads do not compete during startup.
            await apply_saved_params_after_connection()

            start_monitor()
        else:
            status_text.value = "Connection Failed."
            status_text.color = ft.Colors.RED
            connect_btn.disabled = False
            ip_input.disabled = False
            page.update()

    connect_btn = ft.FilledButton("Connect", on_click=on_connect_click,
                                  style=ft.ButtonStyle(bgcolor=ACCENT_COLOR, color=ft.Colors.WHITE))
    status_text = ft.Text("", size=14, color=TEXT_COLOR, width=300)

    conn_row = ft.Row([ip_input, connect_btn, status_text], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # --- UI Elements: Setup Phase ---
    axis_dropdown = ft.Dropdown(
        label="Target Axis",
        width=150,
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
        border_color=ft.Colors.GREY_800
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
            border_color=ft.Colors.GREY_800,
            on_change=create_param_change_handler(param)
        )
        param_inputs[param] = txt
        param_controls.append(txt)

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
        border_color=ft.Colors.GREY_800,
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
        page.update()

    copy_btn = ft.FilledButton(
        "Copy", on_click=on_copy_click,
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
            status_text.color = ft.Colors.ORANGE
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
            status_text.color = ft.Colors.ORANGE
        else:
            applied_text = ", ".join(str(a) for a in applied_axes)
            status_text.value = f"Connected. Saved parameters applied to Axis {applied_text}."
            status_text.color = ft.Colors.GREEN
        page.update()

    async def on_apply_click(e):
        if not trio_conn.connection:
            status_text.value = "Not connected!"
            status_text.color = ft.Colors.RED
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
        try:
            await loop.run_in_executor(uapi_executor, _apply_params_blocking, axis, param_values)
            status_text.value = f"Parameters applied successfully to Axis {axis}!"
            status_text.color = ft.Colors.GREEN
        except Exception as ex:
            status_text.value = f"Error applying: {ex}"
            status_text.color = ft.Colors.RED
        page.update()

    apply_btn = ft.FilledButton("Apply Parameters", on_click=on_apply_click,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE))

    # Arrange parameters in a grid/wrap
    params_row = ft.Row(param_controls, wrap=True, alignment=ft.MainAxisAlignment.START, spacing=15, run_spacing=15)

    setup_container = ft.Column([
        ft.Container(height=10),
        ft.Row(
            [
                axis_dropdown,
                ft.Container(width=30),
                ft.Text("Copy from:", size=13, color=ft.Colors.GREY_400),
                copy_from_dropdown,
                copy_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        ft.Container(height=10),
        params_row,
        ft.Container(height=20),
        apply_btn
    ])

    # === Flying Shear Calculator ===
    calc_settings = settings.setdefault("shear_calc", {})

    def cs_set(k, v):
        calc_settings[k] = v
        save_settings(settings)

    def save_calc_settings(e=None):
        save_settings(settings)

    def make_input(label, key, default, width=160):
        tf = ft.TextField(
            label=label, value=str(calc_settings.get(key, default)),
            width=width, bgcolor=DARKER_BG, color=TEXT_COLOR,
            border_color=ft.Colors.GREY_800, text_size=13,
        )
        return tf

    cut_input    = make_input("Cut length (mm)",         "cut",    100)
    vline_input  = make_input("Line speed (mm/s)",       "vline",  500)
    amax_input   = make_input("Shear max accel (mm/s²)", "amax",   5000, width=180)
    tsync_input  = make_input("Sync time (ms)",          "tsync",  30,   width=140)
    safety_input = make_input("Safety factor",           "safety", 1.5,  width=120)

    result_labels = {
        k: ft.Text("---", size=18, color=ft.Colors.CYAN_200, weight=ft.FontWeight.BOLD)
        for k in ("stroke", "acc", "track", "dec", "ret")
    }
    warning_text = ft.Text("", size=13, color=ft.Colors.AMBER_300)

    code_output = ft.TextField(
        value="", read_only=True, multiline=True, min_lines=24, max_lines=30,
        bgcolor=DARKER_BG, color=ft.Colors.GREEN_200,
        border_color=ft.Colors.GREY_800,
        text_style=ft.TextStyle(font_family="Consolas", size=12),
        expand=True,
    )

    def result_card(label, key):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=12, color=ft.Colors.GREY_400),
                result_labels[key],
            ], spacing=4),
            bgcolor=DARKER_BG, border_radius=8, padding=12,
            border=ft.Border.all(1, ft.Colors.GREY_800), width=150,
        )

    def recalc(e=None):
        try:
            L     = float(cut_input.value)
            v     = float(vline_input.value)
            a     = float(amax_input.value)
            tsync = float(tsync_input.value)
            sf    = float(safety_input.value)
        except (TypeError, ValueError):
            return

        if L <= 0 or v < 0 or a <= 0 or tsync < 0 or sf <= 0:
            warning_text.value = "Invalid inputs: cut, accel, and safety must be > 0; speed and sync time must be >= 0"
            warning_text.color = ft.Colors.RED_300
            code_output.value = ""
            page.update()
            return

        for k, val in [("cut", L), ("vline", v), ("amax", a),
                       ("tsync", tsync), ("safety", sf)]:
            calc_settings[k] = val

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

        result_labels["stroke"].value = f"{stroke:.2f} mm"
        result_labels["acc"].value    = f"{accel_link:.2f} mm"
        result_labels["dec"].value    = f"{decel_link:.2f} mm"
        result_labels["track"].value  = f"{sync_link:.2f} mm"
        result_labels["ret"].value    = f"{ret_link:.2f} mm"

        if ret_link < 0:
            warning_text.value = "✗ Cut length too short — accel+sync+decel exceeds cut length"
            warning_text.color = ft.Colors.RED_300
        elif ret_link < accel_link * 0.5:
            warning_text.value = "⚠ Tight retract — shear must return during short dwell"
            warning_text.color = ft.Colors.AMBER_300
        else:
            warning_text.value = "✓ OK"
            warning_text.color = ft.Colors.GREEN_300

        try:
            link_ax  = int(axis_m_dropdown.value or "0")
            shear_ax = int(axis_s_dropdown.value or "1")
        except ValueError:
            link_ax, shear_ax = 0, 1

        code_output.value = (
            f"shear_ax  = {shear_ax}\n"
            f"link_ax   = {link_ax}\n"
            f"cutter_op = 8\n"
            f"\n"
            f"BASE(shear_ax)\n"
            f"SERVO = ON\n"
            f"DEFPOS(0)\n"
            f"\n"
            f"WHILE TRUE\n"
            f"    ' Accel to line speed\n"
            f"    MOVELINK({accel_dist:.3f}, {accel_link:.3f}, {accel_link:.3f}, 0, link_ax)\n"
            f"    WAIT LOADED\n"
            f"    OP(cutter_op, ON)\n"
            f"\n"
            f"    ' Sync at matched speed (cut happens here)\n"
            f"    MOVELINK({sync_dist:.3f}, {sync_link:.3f}, 0, 0, link_ax)\n"
            f"    WAIT LOADED\n"
            f"    OP(cutter_op, OFF)\n"
            f"\n"
            f"    ' Decel to stop (cutter is now clear)\n"
            f"    MOVELINK({decel_dist:.3f}, {decel_link:.3f}, 0, {decel_link:.3f}, link_ax)\n"
            f"    WAIT LOADED\n"
            f"\n"
            f"    ' Retract carriage to home\n"
            f"    MOVELINK({-stroke:.3f}, {ret_link:.3f}, "
            f"{ret_ad:.3f}, {ret_ad:.3f}, link_ax)\n"
            f"    WAIT LOADED\n"
            f"WEND\n"
        )
        page.update()

    for inp in (cut_input, vline_input, amax_input, tsync_input, safety_input):
        inp.on_change = recalc
        inp.on_blur = save_calc_settings

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
        status_text.color = ft.Colors.GREEN
        page.update()

    copy_btn_shear = ft.FilledButton(
        "Copy program", icon=ft.Icons.CONTENT_COPY, on_click=copy_code,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
        height=38,
    )

    shear_calc_container = ft.Column([
        ft.Container(height=20),
        ft.Text("Flying Shear MOVELINK Calculator", size=20,
                weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        ft.Container(height=10),
        ft.Row([cut_input, vline_input, amax_input, tsync_input, safety_input],
               wrap=True, spacing=15),
        ft.Container(height=15),
        ft.Row([
            result_card("Stroke needed", "stroke"),
            result_card("Accel link",    "acc"),
            result_card("Track link",    "track"),
            result_card("Decel link",    "dec"),
            result_card("Retract dwell", "ret"),
        ], spacing=10),
        ft.Container(height=10),
        warning_text,
        ft.Container(height=15),
        ft.Row([
            ft.Text("Master = link axis, Slave = shear axis (from Connection tab)",
                    size=12, color=ft.Colors.GREY_400),
            ft.Container(expand=True),
            copy_btn_shear,
        ]),
        code_output,
    ], expand=True)

    recalc()

    tabs = ft.Tabs(
        length=3,
        selected_index=0,
        content=ft.Column([
            ft.TabBar(
                tabs=[
                    ft.Tab(label="Connection"),
                    ft.Tab(label="Axis Settings"),
                    ft.Tab(label="Flying Shear"),
                ]
            ),
            ft.TabBarView(
                controls=[
                    ft.Container(
                        content=ft.Column([
                            ft.Container(height=20),
                            ft.Row(
                                [
                                    ft.Column(
                                        [
                                            ft.Text("Controller Connection", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                            conn_row,
                                        ],
                                        spacing=10,
                                        expand=True,
                                    ),
                                    params_panel,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                spacing=20,
                            ),
                            ft.Container(height=20),
                            monitor_container
                        ]),
                        padding=20
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Container(height=20),
                            ft.Text("Axis Parameter Setup", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            setup_container
                        ]),
                        padding=20
                    ),
                    ft.Container(content=shear_calc_container, padding=20),
                ],
                expand=1
            )
        ], expand=1),
        expand=1
    )

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

    # Assemble the main page
    page.add(
        ft.Text("Trio Motion Controller - UAPI Setup", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        tabs
    )

if __name__ == "__main__":
    ft.run(main)
