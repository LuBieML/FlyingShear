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
    base_decel=None,
    base_idle=None,
    link_idle=None,
    cut_length=None,
    line_per_idle=None,
    required_merge=None,
    start_pos=None,
):
    cut_length_value = float(link_dist if cut_length is None else cut_length)
    required_merge_value = (
        cut_length_value < float(link_dist)
        if required_merge is None
        else bool(required_merge)
    )
    base_options = int(link_options) & ~32
    command_options = base_options | (32 if required_merge_value else 0)
    start_pos_value = float(acc if start_pos is None else start_pos)

    lines = [
        "' ROTARYLINK generated setup",
        "' distance is circumference/knives; linkdist is the master travel inside one ROTARYLINK command.",
        "' cut_length is the product pitch; any idle travel happens between loop iterations.",
        "' sync is 1:1 by construction: base_sync speed equals link speed during the cut.",
        f"base_ax      = {int(base_axis)}",
        f"link_ax      = {int(link_axis)}",
        f"distance     = {float(distance):.3f}",
        f"linkdist     = {float(link_dist):.3f}",
        f"cut_length   = {cut_length_value:.3f}",
        f"base_acc     = {float(acc):.3f}",
        f"base_sync    = {float(sync):.3f}",
        f"base_decel   = {float(base_decel):.3f}" if base_decel is not None else "' base_decel not supplied",
        f"moveoptions  = {base_options}",
        f"moveoptions.5 = {'TRUE' if required_merge_value else 'FALSE'}",
        f"start_pos    = {start_pos_value:.3f}",
    ]
    if base_idle is not None:
        lines.append(f"' base_idle drum dwell = {float(base_idle):.3f}")
    if line_per_idle is None:
        line_per_idle = link_idle
    if line_per_idle is not None:
        lines.append(f"' line_idle between ROTARYLINK calls = {float(line_per_idle):.3f}")
    if line_per_idle is not None and abs(float(line_per_idle)) > 1e-9:
        lines.append(
            "' NOTE: ROTARYLINK has no idle phase; this value is handled by start_pos += cut_length."
        )
    lines.extend(describe_rotarylink_options(command_options))

    lines.extend([
        "",
        "BASE(base_ax)",
        "SERVO = ON",
        "DEFPOS(0)",
        "' Add controller-specific axis setup here.",
        "FORWARD AXIS(link_ax)",
        "",
    ])

    command = format_rotarylink(
        distance,
        link_dist,
        acc,
        sync,
        "link_ax",
        command_options,
        "start_pos",
    )

    lines.extend([
        "WHILE (1)",
        "    TRIGGER",
        f"    {command}",
        "    start_pos = start_pos + cut_length",
        "    WA(10)",
        "    WAIT UNTIL MOVES_BUFFERED < 2",
        "WEND",
    ])

    return "\n".join(lines)
