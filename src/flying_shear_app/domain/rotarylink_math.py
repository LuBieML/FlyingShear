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
    """Return geometry inputs for a ROTARYLINK cut.

    ``cut_length`` is the product pitch in line-axis units. It is not the
    ROTARYLINK ``link_dist`` argument; that command distance is derived from
    the in-command phases once ``base_acc``, ``sync_distance``, and
    ``base_decel`` are known.
    """
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
        "units": units,
    }


def calculate_rotarylink_profile(
    distance,
    cut_length,
    acc,
    sync,
    base_decel,
    sync_pos=None,
    previous_sync_end=None,
):
    """Return derived ROTARYLINK phase distances.

    ROTARYLINK has three linked phases inside one command: acceleration,
    synchronized cut, and deceleration. ``base_idle`` is the unlinked slack
    left in the drum cycle after those phases. The product pitch lives outside
    the command in the loop that increments the next command start position.
    """
    distance = float(distance)
    cut_length = float(cut_length)
    acc = float(acc)
    sync = float(sync)
    base_decel = float(base_decel)
    sync_pos_value = None if sync_pos is None else float(sync_pos)
    previous_sync_end_value = (
        None if previous_sync_end is None else float(previous_sync_end)
    )

    if distance <= 0:
        raise ValueError("distance must be > 0")
    if cut_length <= 0:
        raise ValueError("cut_length must be > 0")

    base_sync = sync
    base_idle = distance - acc - base_sync - base_decel
    link_acc = 2.0 * acc
    link_sync = base_sync
    link_decel = 2.0 * base_decel
    link_dist = link_acc + link_sync + link_decel
    line_idle = cut_length - link_dist
    base_total = acc + base_sync + base_decel + base_idle
    link_total = link_acc + link_sync + link_decel

    if sync_pos_value is not None:
        if sync_pos_value < 0:
            raise ValueError("sync_pos must be >= 0")
        if previous_sync_end_value is not None and sync_pos_value <= previous_sync_end_value:
            raise ValueError("sync_pos must be greater than the previous sync phase end")

    sync_start = None if sync_pos_value is None else sync_pos_value + link_acc
    sync_end = None if sync_start is None else sync_start + link_sync
    cycle_end = None if sync_pos_value is None else sync_pos_value + link_dist

    return {
        "distance": distance,
        "cut_length": cut_length,
        "link_dist": link_dist,
        "linkdist": link_dist,
        "acc": acc,
        "base_acc": acc,
        "sync": base_sync,
        "base_sync": base_sync,
        "entered_base_decel": base_decel,
        "decel": base_decel,
        "base_decel": base_decel,
        "base_idle": base_idle,
        "base_total": base_total,
        "link_acc": link_acc,
        "link_sync": link_sync,
        "link_decel": link_decel,
        "line_idle": line_idle,
        "line_per_idle": line_idle,
        "link_idle": line_idle,
        "link_total": link_total,
        "sync_pos": sync_pos_value,
        "start_link_pos": sync_pos_value,
        "sync_start": sync_start,
        "sync_end": sync_end,
        "cycle_end": cycle_end,
        "phase_segments": [
            {"name": "acc", "base": acc, "link": link_acc},
            {"name": "sync", "base": base_sync, "link": link_sync},
            {"name": "decel", "base": base_decel, "link": link_decel},
            {"name": "idle", "base": base_idle, "link": 0.0},
        ],
    }


def validate_rotarylink_profile(profile, abs_tol=1e-6, rel_tol=1e-9):
    """Validate the three-phase ROTARYLINK model and external cut spacing."""
    distance = _finite_float(profile["distance"], "distance")
    cut_length = _finite_float(
        profile.get("cut_length", profile.get("link_dist")),
        "cut_length",
    )
    link_dist = _finite_float(profile["link_dist"], "link_dist")
    acc = _finite_float(profile["acc"], "acc")
    sync = _finite_float(profile["sync"], "sync")
    base_sync = _finite_float(profile.get("base_sync", sync), "base_sync")
    base_decel = _finite_float(profile["base_decel"], "base_decel")
    base_idle = _finite_float(profile["base_idle"], "base_idle")
    link_acc = _finite_float(profile["link_acc"], "link_acc")
    link_sync = _finite_float(profile["link_sync"], "link_sync")
    link_decel = _finite_float(profile["link_decel"], "link_decel")
    line_idle = _finite_float(
        profile.get("line_idle", profile.get("line_per_idle", cut_length - link_dist)),
        "line_idle",
    )

    errors = []
    warnings = []
    info = []
    if sync <= 0:
        errors.append("sync_distance must be > 0")
    if acc <= 0:
        errors.append("base_acc must be > 0")
    if base_decel <= 0:
        errors.append("base_decel must be > 0")
    if base_idle < -abs_tol:
        errors.append(
            "base phases exceed one drum cycle - reduce base_acc, base_decel, "
            "or sync_distance, OR increase drum_diameter / knives"
        )
    if link_dist <= 0:
        errors.append(
            f"linkdist must be > 0; computed {_format_rotarylink_value(link_dist)}"
        )

    base_total = acc + base_sync + base_decel + base_idle
    link_total = link_acc + link_sync + link_decel
    if not math.isclose(base_total, distance, rel_tol=rel_tol, abs_tol=abs_tol):
        errors.append(
            "base_acc + base_sync + base_decel + base_idle does not sum to distance"
        )
    if not math.isclose(link_total, link_dist, rel_tol=rel_tol, abs_tol=abs_tol):
        errors.append("link_acc + link_sync + link_decel does not sum to linkdist")
    if (
        not math.isclose(sync, base_sync, rel_tol=rel_tol, abs_tol=abs_tol)
        or not math.isclose(sync, link_sync, rel_tol=rel_tol, abs_tol=abs_tol)
    ):
        errors.append("base_sync and link_sync must equal sync_distance")

    if not errors:
        if line_idle < 0 and not math.isclose(
            cut_length, link_dist, rel_tol=rel_tol, abs_tol=abs_tol
        ):
            warnings.append(
                "cuts overlap; generated program sets moveoptions.5 merge"
            )
        elif math.isclose(cut_length, link_dist, rel_tol=rel_tol, abs_tol=abs_tol):
            info.append("cut_length == linkdist: no idle, back-to-back cuts")
        else:
            info.append(
                "normal case: idle between cuts = "
                f"{_format_rotarylink_value(line_idle)}"
            )

    messages = errors + warnings + info
    severity = "error" if errors else "warning" if warnings else "ok"
    return {
        "severity": severity,
        "messages": messages,
        "message": "  |  ".join(messages) if messages else "All checks pass",
        "requires_merge": bool(warnings),
        "line_idle": line_idle,
        "line_per_idle": line_idle,
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


def estimate_rotarylink_slave_decel(line_speed, profile):
    """Estimate deceleration needed for the base/slave axis after sync."""
    decel = float(profile["base_decel"])
    if decel <= 0:
        return None
    base_sync_speed = calculate_rotarylink_base_sync_speed(line_speed, profile)
    return (base_sync_speed ** 2) / (2.0 * decel)
