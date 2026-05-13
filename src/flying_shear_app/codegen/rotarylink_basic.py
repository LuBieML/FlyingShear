"""Trio BASIC generation for ROTARYLINK profiles."""

from ..domain.link_options import format_rotarylink


ROTARYLINK_START_MODE_LABELS = {
    0: "absolute sync position",
    1: "MARK start",
    2: "MARKB start",
    3: "R_MARK channel",
}

ROTARYLINK_PROFILE_LABELS = {
    0: "trapezoidal profile",
    1: "sine speed profile",
    2: "power 9 polynomial speed profile",
    3: "power 7 polynomial speed profile",
    4: "power 5 polynomial speed profile",
}


def describe_rotarylink_options(link_options):
    options = int(link_options)
    start_mode = options & 0b11
    profile_mode = (options >> 2) & 0b111
    set_bits = [str(bit) for bit in range(15) if options & (1 << bit)]

    lines = [
        "' link_options bit breakdown:",
        f"'   decimal value = {options}",
        f"'   set bits = {', '.join(set_bits) if set_bits else 'none'}",
        (
            f"'   bits 0..1 = {start_mode}: "
            f"{ROTARYLINK_START_MODE_LABELS.get(start_mode, 'reserved start mode')}"
        ),
        (
            f"'   bits 2..4 = {profile_mode}: "
            f"{ROTARYLINK_PROFILE_LABELS.get(profile_mode, 'reserved profile mode')}"
        ),
    ]

    if options & 32:
        lines.append("'   bit 5 = ON: merge consecutive ROTARYLINK commands")
    else:
        lines.append("'   bit 5 = OFF: no ROTARYLINK merge")

    if options & 64:
        lines.append("'   bit 6 = ON: follow master DPOS")
    else:
        lines.append("'   bit 6 = OFF: follow master MPOS")

    return lines


def emit_rotarylink_basic_program(
    distance,
    link_dist,
    acc,
    sync,
    link_axis,
    base_axis,
    link_options,
    sync_pos=None,
    include_optional_args=False,
    repeat_mode="single",
    merge=False,
    repeat_step=None,
    buffered_commands=4,
):
    command_options = link_options if include_optional_args else None
    command_sync_pos = sync_pos if include_optional_args and sync_pos is not None else None

    lines = [
        "' ROTARYLINK generated setup",
        "' distance/link_dist are total base/link travel; acc/sync are base-axis phase distances.",
        f"base_ax      = {int(base_axis)}",
        f"link_ax      = {int(link_axis)}",
        f"link_options = {int(link_options)}",
    ]
    lines.extend(describe_rotarylink_options(link_options))
    if sync_pos is not None:
        lines.append(f"sync_pos     = {float(sync_pos):.3f}")
    if repeat_step is not None:
        lines.append(f"repeat_dist  = {float(repeat_step):.3f}")

    lines.extend([
        "",
        "BASE(base_ax)",
        "SERVO = ON",
        "DEFPOS(0)",
        "",
    ])

    command = format_rotarylink(
        distance,
        link_dist,
        acc,
        sync,
        "link_ax",
        command_options,
        command_sync_pos,
    )

    if repeat_mode == "program_loop":
        lines.extend([
            "WHILE TRUE",
            f"    {command}",
            "    WAIT IDLE",
            "WEND",
        ])
    elif repeat_mode == "buffered_merge":
        start_pos = float(sync_pos or 0.0)
        step = float(repeat_step if repeat_step is not None else link_dist)
        count = max(1, int(buffered_commands))
        lines.extend([
            "' Buffered merged loop keeps loading future sync positions.",
            "MERGE = 0",
            "WHILE TRUE",
        ])
        for idx in range(count):
            pos_expr = "sync_pos" if idx == 0 else f"sync_pos + repeat_dist * {idx}"
            pos_value = start_pos + step * idx
            lines.append(f"    ' buffered command {idx + 1}: sync_pos {pos_value:.3f}")
            lines.append(
                "    "
                + format_rotarylink(
                    distance,
                    link_dist,
                    acc,
                    sync,
                    "link_ax",
                    link_options,
                    pos_expr,
                )
            )
        lines.extend([
            "    sync_pos = sync_pos + repeat_dist * " + str(count),
            "    WAIT UNTIL MOVES_BUFFERED < 2",
            "WEND",
        ])
    else:
        if merge:
            lines.append("' Merge bit is set; load another ROTARYLINK before this one decelerates.")
        lines.append(command)

    return "\n".join(lines)
