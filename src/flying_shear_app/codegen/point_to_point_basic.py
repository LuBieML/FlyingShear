"""Trio BASIC generation for point-to-point MOVE examples."""


def _format_number(value):
    return f"{float(value):.3f}"


AXIS_PARAMETER_DEFAULTS = {
    "UNITS": "1.0",
    "SPEED": "10.0",
    "ACCEL": "1.0",
    "DECEL": "1.0",
    "FASTDEC": "200.0",
    "JERK": "100000.0",
    "DRIVE_FE_LIMIT": "1",
    "FE_LIMIT": "1",
    "FE_RANGE": "1",
    "RS_LIMIT": "0.0",
    "FS_LIMIT": "0.0",
}
AXIS_PARAMETER_ORDER = list(AXIS_PARAMETER_DEFAULTS)
AXIS_PARAMETER_INT_VALUES = {"DRIVE_FE_LIMIT", "FE_LIMIT", "FE_RANGE"}


def _format_axis_param_value(param_name, value):
    if param_name in AXIS_PARAMETER_INT_VALUES:
        return str(int(float(value)))
    return _format_number(value)


def _axis_param_lines(axis, axis_params=None, servo_on=True):
    params = dict(AXIS_PARAMETER_DEFAULTS)
    if axis_params:
        params.update(axis_params)

    lines = [f"BASE({int(axis)})"]
    if servo_on:
        lines.append("SERVO = ON")
    for param_name in AXIS_PARAMETER_ORDER:
        lines.append(f"{param_name} = {_format_axis_param_value(param_name, params[param_name])}")
    return lines


def emit_point_to_point_basic_program(
    axis,
    move_mode,
    target,
    speed,
    accel,
    decel,
    servo_on=True,
    wait_idle=True,
    axis_params=None,
):
    """Emit a small Trio BASIC point-to-point move program.

    ``move_mode`` accepts ``relative`` for MOVE(distance) and ``absolute`` for
    MOVEABS(target_pos).
    """
    if move_mode not in ("relative", "absolute"):
        raise ValueError("move_mode must be 'relative' or 'absolute'")

    startup = emit_point_to_point_startup_program(axis, speed, accel, decel, servo_on, axis_params)
    motion = emit_point_to_point_motion_program(axis, move_mode, target, speed, accel, decel, wait_idle)
    return f"{startup}\n\n{motion}"


def emit_point_to_point_startup_program(axis, speed, accel, decel, servo_on=True, axis_params=None):
    """Emit axis setup code intended to run at controller startup."""
    axis_value = int(axis)
    startup_params = dict(axis_params or {})
    startup_params.setdefault("SPEED", speed)
    startup_params.setdefault("ACCEL", accel)
    startup_params.setdefault("DECEL", decel)

    lines = [
        "' Point To Point STARTUP axis configuration",
        "' Run this code on startup to configure axes before running motion code.",
    ]
    lines.extend(_axis_param_lines(axis_value, startup_params, servo_on))
    return "\n".join(lines)


def emit_point_to_point_motion_program(
    axis,
    move_mode,
    target,
    speed=None,
    accel=None,
    decel=None,
    wait_idle=True,
):
    """Emit single-axis point-to-point motion code."""
    if move_mode not in ("relative", "absolute"):
        raise ValueError("move_mode must be 'relative' or 'absolute'")

    axis_value = int(axis)
    target_value = _format_number(target)

    lines = [
        "' Point To Point motion code",
        "' Run STARTUP first so the selected axis is configured.",
        f"axis_no = {axis_value}",
    ]
    if speed is not None:
        lines.append(f"move_speed = {_format_number(speed)}")
    if accel is not None:
        lines.append(f"move_accel = {_format_number(accel)}")
    if decel is not None:
        lines.append(f"move_decel = {_format_number(decel)}")

    if move_mode == "relative":
        lines.append(f"distance = {target_value}")
        command = "MOVE(distance)"
    else:
        lines.append(f"target_pos = {target_value}")
        command = "MOVEABS(target_pos)"

    lines.extend(["", "BASE(axis_no)", command])
    if wait_idle:
        lines.append("WAIT IDLE")

    return "\n".join(lines)


def emit_square_move_basic_program(
    x_axis,
    y_axis,
    move_mode,
    origin_x,
    origin_y,
    side,
    speed,
    accel,
    decel,
    servo_on=True,
    wait_idle=True,
    axis_params_by_axis=None,
):
    """Emit a beginner-friendly two-axis square path example."""
    if move_mode not in ("relative", "absolute"):
        raise ValueError("move_mode must be 'relative' or 'absolute'")

    startup = emit_square_startup_basic_program(
        x_axis,
        y_axis,
        speed,
        accel,
        decel,
        servo_on,
        axis_params_by_axis,
    )
    motion = emit_square_motion_basic_program(
        x_axis,
        y_axis,
        move_mode,
        origin_x,
        origin_y,
        side,
        speed,
        accel,
        decel,
        wait_idle,
    )
    return f"{startup}\n\n{motion}"


def emit_square_startup_basic_program(
    x_axis,
    y_axis,
    speed,
    accel,
    decel,
    servo_on=True,
    axis_params_by_axis=None,
):
    """Emit square example axis setup code intended to run at startup."""
    x_axis_value = int(x_axis)
    y_axis_value = int(y_axis)

    lines = [
        "' Point To Point STARTUP axis configuration",
        "' Run this code on startup to configure axes before running motion code.",
    ]

    lines.append("")
    seen_axes = set()
    for axis_value in (x_axis_value, y_axis_value):
        if axis_value in seen_axes:
            continue
        seen_axes.add(axis_value)
        axis_params = None
        if axis_params_by_axis:
            axis_params = axis_params_by_axis.get(axis_value) or axis_params_by_axis.get(str(axis_value))
        startup_params = dict(axis_params or {})
        startup_params.setdefault("SPEED", speed)
        startup_params.setdefault("ACCEL", accel)
        startup_params.setdefault("DECEL", decel)
        lines.extend(_axis_param_lines(axis_value, startup_params, servo_on))
        lines.append("")

    return "\n".join(lines).rstrip()


def emit_square_motion_basic_program(
    x_axis,
    y_axis,
    move_mode,
    origin_x,
    origin_y,
    side,
    speed=None,
    accel=None,
    decel=None,
    wait_idle=True,
):
    """Emit square motion code using one BASE(axis) before each single-axis move."""
    if move_mode not in ("relative", "absolute"):
        raise ValueError("move_mode must be 'relative' or 'absolute'")

    x_axis_value = int(x_axis)
    y_axis_value = int(y_axis)
    side_value = float(side)
    if side_value <= 0:
        raise ValueError("side must be > 0")

    origin_x_value = float(origin_x)
    origin_y_value = float(origin_y)

    lines = [
        "' Point To Point square motion code",
        "' Run STARTUP first so both axes are configured.",
        "' Each edge is one single-axis point-to-point move.",
        f"x_axis = {x_axis_value}",
        f"y_axis = {y_axis_value}",
        f"side = {_format_number(side_value)}",
    ]
    if speed is not None:
        lines.append(f"move_speed = {_format_number(speed)}")
    if accel is not None:
        lines.append(f"move_accel = {_format_number(accel)}")
    if decel is not None:
        lines.append(f"move_decel = {_format_number(decel)}")

    if move_mode == "absolute":
        lines.extend(
            [
                f"x0 = {_format_number(origin_x_value)}",
                f"y0 = {_format_number(origin_y_value)}",
            ]
        )
    else:
        lines.append("' Relative square starts from the current X/Y position.")

    lines.append("")

    if move_mode == "absolute":
        moves = [
            ("Move X to start corner", "x_axis", "MOVEABS(x0)"),
            ("Move Y to start corner", "y_axis", "MOVEABS(y0)"),
            ("Bottom edge", "x_axis", "MOVEABS(x0 + side)"),
            ("Right edge", "y_axis", "MOVEABS(y0 + side)"),
            ("Top edge", "x_axis", "MOVEABS(x0)"),
            ("Left edge back home", "y_axis", "MOVEABS(y0)"),
        ]
    else:
        moves = [
            ("Bottom edge", "x_axis", "MOVE(side)"),
            ("Right edge", "y_axis", "MOVE(side)"),
            ("Top edge", "x_axis", "MOVE(-side)"),
            ("Left edge back home", "y_axis", "MOVE(-side)"),
        ]

    for label, axis_name, command in moves:
        lines.append(f"' {label}")
        lines.append(f"BASE({axis_name})")
        lines.append(command)
        if wait_idle:
            lines.append("WAIT IDLE")

    return "\n".join(lines)
