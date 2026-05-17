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
