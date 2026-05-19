"""Pure rotary-knife unit conversion and kinematics helpers."""

import math


def compute_rotary_mpos_counts_per_physical_rev(encoder_counts_per_rev, drum_axis_units):
    """Convert drive encoder CPR and Trio UNITS into MPOS units per drum turn."""
    cpr = float(encoder_counts_per_rev)
    units = float(drum_axis_units)
    if cpr <= 0:
        raise ValueError("Encoder counts/rev must be > 0")
    if units <= 0:
        raise ValueError("Drum axis UNITS must be > 0")
    return cpr / units


def compute_rotary_drum_circumference_mm(drum_diameter_mm):
    """Return drum circumference in millimetres from diameter."""
    diameter = float(drum_diameter_mm)
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")
    return math.pi * diameter


def compute_rotary_units_per_mm(encoder_counts_per_rev, drum_diameter_mm):
    """Return Trio UNITS when one user unit is one millimetre of drum surface."""
    cpr = float(encoder_counts_per_rev)
    if cpr <= 0:
        raise ValueError("Encoder counts/rev must be > 0")
    return cpr / compute_rotary_drum_circumference_mm(drum_diameter_mm)


def compute_rotary_cutting_radius_px(drum_diameter_mm, scale_px_per_unit, link_units_to_mm=1.0):
    """Return the visual cutting radius in pixels for the current conveyor scale."""
    diameter = float(drum_diameter_mm)
    scale = float(scale_px_per_unit)
    units_to_mm = float(link_units_to_mm)
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")
    if scale <= 0:
        raise ValueError("Visual scale must be > 0")
    if units_to_mm <= 0:
        raise ValueError("Link units to mm must be > 0")
    return (diameter / units_to_mm) * scale / 2.0


def compute_rotary_drum_angle_rad(drum_mpos, mpos_counts_per_physical_rev):
    divisor = float(mpos_counts_per_physical_rev)
    if divisor <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    return ((float(drum_mpos) % divisor) / divisor) * 2.0 * math.pi


def advance_rotary_drum_angle_rad(
    current_angle_rad,
    drum_mspeed,
    mpos_counts_per_physical_rev,
    elapsed_s,
):
    """Dead-reckon a drum angle from live MSPEED between usable MPOS samples."""
    divisor = float(mpos_counts_per_physical_rev)
    if divisor <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    dt = float(elapsed_s)
    if dt <= 0:
        return float(current_angle_rad) % (2.0 * math.pi)
    revolutions = float(drum_mspeed) / divisor * dt
    return (float(current_angle_rad) + revolutions * 2.0 * math.pi) % (2.0 * math.pi)


def shortest_angle_distance_rad(angle, target):
    return abs(((float(angle) - float(target) + math.pi) % (2.0 * math.pi)) - math.pi)


def compute_rotarylink_sync_window_deg(distance, sync, n_knives, minimum_deg=0.1):
    """Convert ROTARYLINK base-axis sync distance into a per-knife drum angle."""
    n = max(1, int(float(n_knives)))
    segment_angle = 360.0 / n
    base_distance = float(distance)
    sync_distance = float(sync)
    min_angle = max(0.0, float(minimum_deg))
    if base_distance <= 0:
        raise ValueError("ROTARYLINK distance must be > 0")
    if sync_distance < 0:
        raise ValueError("ROTARYLINK sync distance must be >= 0")
    return min(segment_angle, max(min_angle, sync_distance / base_distance * segment_angle))


def rotary_blade_direction_for_angle(drum_angle):
    angle = float(drum_angle)
    return math.sin(angle), -math.cos(angle)


def compute_rotary_drum_tangential_mm_s(
    drum_mspeed,
    mpos_counts_per_physical_rev,
    drum_diameter_mm,
):
    divisor = float(mpos_counts_per_physical_rev)
    diameter = float(drum_diameter_mm)
    if divisor <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")
    drum_rps = float(drum_mspeed) / divisor
    return drum_rps * math.pi * diameter


def compute_rotary_drum_kinematics(
    drum_mpos,
    drum_mspeed,
    mpos_counts_per_physical_rev,
    drum_diameter_mm,
    drum_direction_reversed=False,
):
    """Return shared rotary drum unit conversions for live diagnostics and drawing."""
    mpos_per_rev = float(mpos_counts_per_physical_rev)
    diameter = float(drum_diameter_mm)
    if mpos_per_rev <= 0:
        raise ValueError("mpos_counts_per_physical_rev must be positive")
    if diameter <= 0:
        raise ValueError("Drum diameter must be > 0")

    direction_sign = -1.0 if drum_direction_reversed else 1.0
    circumference = math.pi * diameter
    raw_mpos = None if drum_mpos is None else float(drum_mpos)
    raw_mspeed = None if drum_mspeed is None else float(drum_mspeed)
    effective_mspeed = None if raw_mspeed is None else raw_mspeed * direction_sign

    drum_angle_rad = None
    if raw_mpos is not None:
        drum_fraction_of_rev = (raw_mpos % mpos_per_rev) / mpos_per_rev
        drum_angle_rad = (drum_fraction_of_rev * 2.0 * math.pi * direction_sign) % (2.0 * math.pi)

    drum_rps = None
    drum_tangential_mm_s = None
    if effective_mspeed is not None:
        drum_rps = effective_mspeed / mpos_per_rev
        drum_tangential_mm_s = drum_rps * circumference

    return {
        "drum_mpos": raw_mpos,
        "drum_mspeed": raw_mspeed,
        "effective_drum_mspeed": effective_mspeed,
        "mpos_per_rev": mpos_per_rev,
        "drum_rps": drum_rps,
        "drum_circumference_mm": circumference,
        "drum_tangential_mm_s": drum_tangential_mm_s,
        "drum_angle_rad": drum_angle_rad,
    }
