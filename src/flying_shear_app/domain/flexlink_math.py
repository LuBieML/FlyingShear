"""Pure FLEXLINK curve and excitation progress helpers."""

import math


def flexlink_curve_progress(t, curve_type):
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


def flexlink_excitation_progress(
    u,
    base_in,
    base_out,
    excite_acc,
    excite_dec,
    curve_type,
):
    start_u = base_in / 100.0
    end_u = 1.0 - base_out / 100.0
    if end_u <= start_u:
        return 0.0, False
    if u <= start_u:
        return 0.0, False
    if u >= end_u:
        return 1.0, False

    phase = (u - start_u) / (end_u - start_u)
    acc = max(0.0, min(1.0, excite_acc / 100.0))
    dec = max(0.0, min(1.0, excite_dec / 100.0))
    if acc + dec > 1.0:
        scale = 1.0 / (acc + dec)
        acc *= scale
        dec *= scale
    flat = max(0.0, 1.0 - acc - dec)
    area_total = max(0.001, 0.5 * acc + flat + 0.5 * dec)

    if acc > 0 and phase < acc:
        local = phase / acc
        area = 0.5 * acc * flexlink_curve_progress(local, curve_type)
    elif phase < acc + flat:
        area = 0.5 * acc + (phase - acc)
    elif dec > 0:
        local = (phase - acc - flat) / dec
        area = (
            0.5 * acc
            + flat
            + dec * (
                local - 0.5 * flexlink_curve_progress(local, curve_type)
            )
        )
    else:
        area = area_total
    return max(0.0, min(1.0, area / area_total)), True
