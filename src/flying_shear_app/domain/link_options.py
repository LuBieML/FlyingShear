"""Link option bit helpers for Trio linked-motion commands."""


def option_bit(index):
    return 1 << index


def build_movelink_options(profile, start_mode, link_source, direction_mode, repeat_mode):
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


def build_flexlink_options(
    curve_type,
    start_mode,
    link_source,
    direction_mode,
    repeat_mode,
):
    options = 0
    curve_bits = {
        "sine": 0,
        "poly9": 1,
        "poly7": 2,
        "poly5": 3,
        "linear": 4,
    }
    options |= curve_bits.get(curve_type, 0) << 10

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
    if repeat_mode == "flexlink_repeat":
        options |= option_bit(2)

    return options


def build_rotarylink_options(start_mode, profile, link_source, merge):
    """Build ROTARYLINK link_options.

    ROTARYLINK encodes start mode in bits 0..1 and profile type in bits 2..4.
    This differs from MOVELINK/FLEXLINK, where start modes are separate bits.
    """
    start_modes = {
        "immediate": 0,
        "absolute": 0,
        "mark": 1,
        "markb": 2,
        "rmark": 3,
    }
    profile_modes = {
        "trapezoid": 0,
        "sine": 1,
        "power9": 2,
        "power7": 3,
        "power5": 4,
    }

    options = start_modes.get(start_mode, 0)
    options |= profile_modes.get(profile, 0) << 2

    if merge:
        options |= option_bit(5)
    if link_source == "dpos":
        options |= option_bit(6)

    return options


def format_rotarylink(distance, link_dist, acc, sync, link_axis, options=None, sync_pos=None):
    args = [
        f"{distance:.3f}",
        f"{link_dist:.3f}",
        f"{acc:.3f}",
        f"{sync:.3f}",
        str(link_axis),
    ]

    if options is not None:
        args.append(str(int(options)))
        if sync_pos is not None:
            if isinstance(sync_pos, str):
                args.append(sync_pos)
            else:
                args.append(f"{sync_pos:.3f}")

    return f"ROTARYLINK({', '.join(args)})"
