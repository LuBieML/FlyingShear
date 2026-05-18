"""Trio BASIC generation for point-to-point MOVE examples."""


def _format_number(value):
    return f"{float(value):.3f}"


def emit_point_to_point_basic_program(
    axis,
    move_mode,
    target,
    speed,
    accel,
    decel,
    servo_on=True,
    wait_idle=True,
):
    """Emit a small Trio BASIC point-to-point move program.

    ``move_mode`` accepts ``relative`` for MOVE(distance) and ``absolute`` for
    MOVEABS(target_pos).
    """
    if move_mode not in ("relative", "absolute"):
        raise ValueError("move_mode must be 'relative' or 'absolute'")

    startup = emit_point_to_point_startup_program(axis, speed, accel, decel, servo_on)
    motion = emit_point_to_point_motion_program(axis, move_mode, target, speed, accel, decel, wait_idle)
    return f"{startup}\n\n{motion}"


def emit_point_to_point_startup_program(axis, speed, accel, decel, servo_on=True):
    """Emit axis setup code intended to run at controller startup."""
    axis_value = int(axis)
    speed_value = _format_number(speed)
    accel_value = _format_number(accel)
    decel_value = _format_number(decel)

    lines = [
        "' Point To Point STARTUP axis configuration",
        "' Run this code on startup to configure axes before running motion code.",
        f"BASE({axis_value})",
    ]
    if servo_on:
        lines.append("SERVO = ON")
    lines.extend(
        [
            f"SPEED = {speed_value}",
            f"ACCEL = {accel_value}",
            f"DECEL = {decel_value}",
        ]
    )
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
):
    """Emit square example axis setup code intended to run at startup."""
    x_axis_value = int(x_axis)
    y_axis_value = int(y_axis)
    speed_value = _format_number(speed)
    accel_value = _format_number(accel)
    decel_value = _format_number(decel)

    lines = [
        "' Point To Point STARTUP axis configuration",
        "' Run this code on startup to configure axes before running motion code.",
    ]

    lines.append("")
    for axis_value in (x_axis_value, y_axis_value):
        lines.append(f"BASE({axis_value})")
        if servo_on:
            lines.append("SERVO = ON")
        lines.extend(
            [
                f"SPEED = {speed_value}",
                f"ACCEL = {accel_value}",
                f"DECEL = {decel_value}",
                "",
            ]
        )

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
