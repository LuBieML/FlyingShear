"""Pure FLEXLINK curve and excitation progress helpers."""

import math


def flexlink_curve_progress(t, curve_type):
    """Velocity-shape function for one accel (or, mirrored, decel) ramp.

    Returns a value in [0, 1] that ramps from 0 at t=0 to 1 at t=1 with a
    smooth profile selected by curve_type. Used as the *velocity* shape during
    the accel ramp: instantaneous excitation velocity = peak * curve_progress.
    """
    t = max(0.0, min(1.0, float(t)))
    if curve_type == "linear":
        return t
    if curve_type == "poly5":
        return t ** 3 * (10 - 15 * t + 6 * t ** 2)
    if curve_type == "poly7":
        return t ** 4 * (35 - 84 * t + 70 * t ** 2 - 20 * t ** 3)
    if curve_type == "poly9":
        return t ** 5 * (
            126 - 420 * t + 540 * t ** 2
            - 315 * t ** 3 + 70 * t ** 4
        )
    return 0.5 - 0.5 * math.cos(math.pi * t)


def flexlink_curve_progress_integral(t, curve_type):
    """Integral of `flexlink_curve_progress` from 0 to t.

    Used to compute the *position* accumulated during a ramp whose velocity
    follows the chosen curve shape. Each integral satisfies I(1) = 0.5 (the
    triangle area of a unit-peak ramp of width 1).
    """
    t = max(0.0, min(1.0, float(t)))
    if curve_type == "linear":
        return 0.5 * t * t
    if curve_type == "poly5":
        # v_shape(t) = 10 t^3 - 15 t^4 + 6 t^5
        return t ** 4 * (2.5 - 3.0 * t + t ** 2)
    if curve_type == "poly7":
        # v_shape(t) = 35 t^4 - 84 t^5 + 70 t^6 - 20 t^7
        return 7.0 * t ** 5 - 14.0 * t ** 6 + 10.0 * t ** 7 - 2.5 * t ** 8
    if curve_type == "poly9":
        # v_shape(t) = 126 t^5 - 420 t^6 + 540 t^7 - 315 t^8 + 70 t^9
        return (
            21.0 * t ** 6
            - 60.0 * t ** 7
            + 67.5 * t ** 8
            - 35.0 * t ** 9
            + 7.0 * t ** 10
        )
    # default: sine
    return 0.5 * t - (0.5 / math.pi) * math.sin(math.pi * t)


def flexlink_excitation_progress(
    u,
    cycle_pitch,
    base_in,
    base_out,
    excite_acc,
    excite_dec,
    curve_type,
):
    """Return (progress, in_excite) for normalized phase u in [0, 1].

    Models a trapezoidal velocity bump above the 1:1 baseline:
        - Accel ramp: velocity rises from 0 to peak following the curve shape.
        - Flat: velocity at peak.
        - Decel ramp: velocity falls from peak back to 0 (mirror of accel).

    `progress` is the normalized *area* accumulated under that bump, i.e. the
    fraction of the slave excitation displacement covered at master phase u.

    cycle_pitch, base_in, base_out, excite_acc, excite_dec are all distances
    in the same units (mm). base_in/base_out are dwell distances at the base
    ratio; excite_acc/excite_dec are accel/decel ramp distances inside the
    excitation window.
    """
    if cycle_pitch <= 0:
        return 0.0, False
    start_u = base_in / cycle_pitch
    end_u = 1.0 - base_out / cycle_pitch
    if end_u <= start_u:
        return 0.0, False
    if u <= start_u:
        return 0.0, False
    if u >= end_u:
        return 1.0, False

    window = cycle_pitch - base_in - base_out
    if window <= 0:
        return 0.0, False
    phase = (u - start_u) / (end_u - start_u)
    acc = max(0.0, min(1.0, excite_acc / window))
    dec = max(0.0, min(1.0, excite_dec / window))
    if acc + dec > 1.0:
        scale = 1.0 / (acc + dec)
        acc *= scale
        dec *= scale
    flat = max(0.0, 1.0 - acc - dec)
    area_total = max(1e-9, 0.5 * acc + flat + 0.5 * dec)

    if acc > 0 and phase < acc:
        local = phase / acc
        area = acc * flexlink_curve_progress_integral(local, curve_type)
    elif phase < acc + flat:
        area = 0.5 * acc + (phase - acc)
    elif dec > 0:
        local = (phase - acc - flat) / dec
        # Decel velocity = peak * (1 - v_shape(local)). Integrating gives
        # dec * (local - I(local)), which adds to the accumulated area.
        area = (
            0.5 * acc
            + flat
            + dec * (local - flexlink_curve_progress_integral(local, curve_type))
        )
    else:
        area = area_total
    return max(0.0, min(1.0, area / area_total)), True
