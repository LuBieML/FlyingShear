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

    axis_value = int(axis)
    target_value = _format_number(target)
    speed_value = _format_number(speed)
    accel_value = _format_number(accel)
    decel_value = _format_number(decel)

    lines = [
        "' Point To Point Move generated setup",
        "' Relative mode uses MOVE(distance). Absolute mode uses MOVEABS(target_pos).",
        f"axis_no = {axis_value}",
        f"move_speed = {speed_value}",
        f"move_accel = {accel_value}",
        f"move_decel = {decel_value}",
    ]

    if move_mode == "relative":
        lines.append(f"distance = {target_value}")
        command = "MOVE(distance)"
    else:
        lines.append(f"target_pos = {target_value}")
        command = "MOVEABS(target_pos)"

    lines.extend(
        [
            "",
            "BASE(axis_no)",
        ]
    )
    if servo_on:
        lines.append("SERVO = ON")
    lines.extend(
        [
            "SPEED = move_speed",
            "ACCEL = move_accel",
            "DECEL = move_decel",
            command,
        ]
    )
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

    x_axis_value = int(x_axis)
    y_axis_value = int(y_axis)
    side_value = float(side)
    if side_value <= 0:
        raise ValueError("side must be > 0")

    origin_x_value = float(origin_x)
    origin_y_value = float(origin_y)
    speed_value = _format_number(speed)
    accel_value = _format_number(accel)
    decel_value = _format_number(decel)

    lines = [
        "' Point To Point square path example",
        "' Each edge is one single-axis point-to-point move.",
        f"x_axis = {x_axis_value}",
        f"y_axis = {y_axis_value}",
        f"side = {_format_number(side_value)}",
        f"move_speed = {speed_value}",
        f"move_accel = {accel_value}",
        f"move_decel = {decel_value}",
    ]

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
    for axis_name in ("x_axis", "y_axis"):
        lines.append(f"BASE({axis_name})")
        if servo_on:
            lines.append("SERVO = ON")
        lines.extend(
            [
                "SPEED = move_speed",
                "ACCEL = move_accel",
                "DECEL = move_decel",
                "",
            ]
        )

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
