"""Pure ROTARYLINK profile calculations and validation."""

import math

from .rotary_math import (
    compute_rotary_drum_circumference_mm,
    compute_rotary_units_per_mm,
)


def _finite_float(value, label):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _format_rotarylink_value(value):
    return f"{float(value):.3f}"


def derive_rotarylink_geometry(
    drum_diameter,
    encoder_counts_per_rev,
    knives_on_drum,
    cut_length,
):
    """Return ROTARYLINK distance/link_dist from machine geometry and cut length."""
    drum_diameter_value = _finite_float(drum_diameter, "drum_diameter")
    encoder_counts_value = _finite_float(encoder_counts_per_rev, "encoder_counts_per_rev")
    knives_value = _finite_float(knives_on_drum, "knives_on_drum")
    if knives_value < 1 or not knives_value.is_integer():
        raise ValueError("knives_on_drum must be a whole number >= 1")

    cut_length_value = _finite_float(cut_length, "cut_length")
    if cut_length_value <= 0:
        raise ValueError("cut_length must be > 0")

    circumference = compute_rotary_drum_circumference_mm(drum_diameter_value)
    units = compute_rotary_units_per_mm(encoder_counts_value, drum_diameter_value)
    knives_count = int(knives_value)
    distance = circumference / knives_count

    return {
        "drum_diameter": drum_diameter_value,
        "encoder_counts_per_rev": encoder_counts_value,
        "knives_on_drum": knives_count,
        "cut_length": cut_length_value,
        "circumference": circumference,
        "distance": distance,
        "link_dist": cut_length_value,
        "units": units,
    }


def calculate_rotarylink_profile(
    distance,
    link_dist,
    acc,
    sync,
    base_decel=None,
    sync_pos=None,
    previous_sync_end=None,
):
    """Return derived ROTARYLINK phase distances.

    ROTARYLINK phase arguments are base-axis distances. Sync is a 1:1 phase:
    base_sync and link_sync are both the entered sync distance. The link axis
    continues at line speed during base-axis ramps, so link ramp distances are
    twice their corresponding base ramp distances.
    """
    distance = float(distance)
    link_dist = float(link_dist)
    acc = float(acc)
    sync = float(sync)
    if base_decel is None:
        base_decel = distance - acc - sync
    base_decel = float(base_decel)
    sync_pos_value = None if sync_pos is None else float(sync_pos)
    previous_sync_end_value = (
        None if previous_sync_end is None else float(previous_sync_end)
    )

    if distance <= 0:
        raise ValueError("distance must be > 0")
    if link_dist <= 0:
        raise ValueError("link_dist must be > 0")
    if acc < 0:
        raise ValueError("acc must be >= 0")
    if base_decel < 0:
        raise ValueError("base_decel must be >= 0")

    base_sync = sync
    link_acc = 2.0 * acc
    link_sync = base_sync
    link_decel = 2.0 * base_decel
    base_idle = distance - acc - base_sync - base_decel
    link_idle = link_dist - link_acc - link_sync - link_decel
    base_total = acc + base_sync + base_decel + base_idle
    link_total = link_acc + link_sync + link_decel + link_idle

    if sync_pos_value is not None:
        if sync_pos_value < 0:
            raise ValueError("sync_pos must be >= 0")
        if sync_pos_value <= link_acc:
            raise ValueError("sync_pos must be greater than the link-axis acceleration distance")
        if previous_sync_end_value is not None and sync_pos_value <= previous_sync_end_value:
            raise ValueError("sync_pos must be greater than the previous sync phase end")

    sync_end = None if sync_pos_value is None else sync_pos_value + link_sync
    cycle_end = None if sync_pos_value is None else sync_end + link_decel + link_idle
    start_link_pos = None if sync_pos_value is None else sync_pos_value - link_acc

    return {
        "distance": distance,
        "link_dist": link_dist,
        "acc": acc,
        "base_acc": acc,
        "sync": base_sync,
        "base_sync": base_sync,
        "decel": base_decel,
        "base_decel": base_decel,
        "base_idle": base_idle,
        "base_total": base_total,
        "link_acc": link_acc,
        "link_sync": link_sync,
        "link_decel": link_decel,
        "link_idle": link_idle,
        "link_total": link_total,
        "sync_pos": sync_pos_value,
        "start_link_pos": start_link_pos,
        "sync_end": sync_end,
        "cycle_end": cycle_end,
        "phase_segments": [
            {"name": "acc", "base": acc, "link": link_acc},
            {"name": "sync", "base": base_sync, "link": link_sync},
            {"name": "decel", "base": base_decel, "link": link_decel},
            {"name": "idle", "base": base_idle, "link": link_idle},
        ],
    }


def validate_rotarylink_profile(profile, abs_tol=1e-6, rel_tol=1e-9):
    """Validate the four-phase ROTARYLINK bookkeeping model."""
    distance = _finite_float(profile["distance"], "distance")
    link_dist = _finite_float(profile["link_dist"], "link_dist")
    acc = _finite_float(profile["acc"], "acc")
    sync = _finite_float(profile["sync"], "sync")
    base_sync = _finite_float(profile.get("base_sync", sync), "base_sync")
    base_decel = _finite_float(profile["base_decel"], "base_decel")
    base_idle = _finite_float(profile["base_idle"], "base_idle")
    link_acc = _finite_float(profile["link_acc"], "link_acc")
    link_sync = _finite_float(profile["link_sync"], "link_sync")
    link_decel = _finite_float(profile["link_decel"], "link_decel")
    link_idle = _finite_float(profile["link_idle"], "link_idle")

    messages = []
    if sync <= 0:
        messages.append("sync_distance must be > 0")
    if base_idle < -abs_tol:
        phase_sum = acc + base_sync + base_decel
        messages.append(
            "base phases exceed one drum cycle: "
            f"base_acc + base_sync + base_decel = {_format_rotarylink_value(phase_sum)} "
            f"> distance {_format_rotarylink_value(distance)}"
        )
    if link_idle < -abs_tol:
        used = link_acc + link_sync + link_decel
        messages.append(
            "cut_length too short: "
            f"link_acc + link_sync + link_decel = {_format_rotarylink_value(used)} "
            f"> cut_length {_format_rotarylink_value(link_dist)}"
        )

    base_total = acc + base_sync + base_decel + base_idle
    link_total = link_acc + link_sync + link_decel + link_idle
    if not math.isclose(base_total, distance, rel_tol=rel_tol, abs_tol=abs_tol):
        messages.append("base phase distances do not sum to distance")
    if not math.isclose(link_total, link_dist, rel_tol=rel_tol, abs_tol=abs_tol):
        messages.append("link phase distances do not sum to cut_length")
    if (
        not math.isclose(sync, base_sync, rel_tol=rel_tol, abs_tol=abs_tol)
        or not math.isclose(sync, link_sync, rel_tol=rel_tol, abs_tol=abs_tol)
    ):
        messages.append("base_sync and link_sync must equal sync_distance")

    severity = "error" if messages else "ok"
    return {
        "severity": severity,
        "messages": messages,
        "message": "  |  ".join(messages) if messages else "All checks pass",
    }


def calculate_rotarylink_base_sync_speed(line_speed, profile):
    """Return the base-axis speed during ROTARYLINK sync for a link-axis speed."""
    line_speed = float(line_speed)
    if line_speed <= 0:
        raise ValueError("line_speed must be > 0")
    return line_speed


def estimate_rotarylink_slave_accel(line_speed, profile):
    """Estimate acceleration needed for the base/slave axis to reach sync speed."""
    acc = float(profile["acc"])
    if acc <= 0:
        return None
    base_sync_speed = calculate_rotarylink_base_sync_speed(line_speed, profile)
    return (base_sync_speed ** 2) / (2.0 * acc)
