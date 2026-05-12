"""CAMBOX rotary-knife profile calculations."""

import math


def generate_rotary_knife_cam_table(
    cut_length_mm,
    drum_diameter_mm,
    n_knives,
    cut_window_deg,
    encoder_counts_per_rev,
    n_points=720,
    blend_fraction=0.4,
    line_speed_mm_s=500,
):
    drum_radius = drum_diameter_mm / 2.0
    drum_circumference = math.pi * drum_diameter_mm
    cut_segment_counts = encoder_counts_per_rev / n_knives
    alpha_max = math.radians(cut_window_deg / 2.0)

    if cut_window_deg >= 360.0 / n_knives:
        raise ValueError(f"Cut window {cut_window_deg}° too large; must be < {360.0/n_knives:.1f}° for {n_knives}-knife drum")
    if alpha_max >= math.pi / 2:
        raise ValueError("Cut window too wide: half-window angle must be < 90° for cosine correction")

    cut_zone_master_mm = 2.0 * drum_radius * math.sin(alpha_max)
    w_cut = cut_zone_master_mm / cut_length_mm
    if w_cut >= 1.0:
        raise ValueError(f"Cut zone ({cut_zone_master_mm:.2f} mm) exceeds cut length ({cut_length_mm} mm)")
    max_x_offset = (cut_length_mm * w_cut) / 2.0
    if max_x_offset >= drum_radius:
        raise ValueError(
            f"Cut window too wide for drum radius: would require "
            f"knife horizontal travel of {max_x_offset:.2f} mm exceeding "
            f"drum radius {drum_radius:.2f} mm. Reduce cut_window_deg or "
            f"increase drum_diameter."
        )

    w_blend = blend_fraction * (1.0 - w_cut) / 2.0
    w_outside = 1.0 - w_cut - 2.0 * w_blend
    if w_outside < 0:
        raise ValueError(f"Blend fraction {blend_fraction} too large; reduce or increase cut length")

    r_ratio = n_knives * cut_length_mm / drum_circumference
    v_cut = r_ratio
    v_cut_at_edge = v_cut / math.cos(alpha_max)
    f_slave_cut = n_knives * cut_window_deg / 360.0
    v_out = (1.0 - f_slave_cut - v_cut_at_edge * w_blend) / (w_outside + w_blend)
    if v_out < 0:
        raise ValueError(f"Outside velocity would be negative ({v_out:.3f}); drum cannot reverse - increase cut_length or reduce drum dia")

    u1 = w_outside / 2.0
    u2 = u1 + w_blend
    u3 = u2 + w_cut
    u4 = u3 + w_blend
    u_cut_center = (u2 + u3) / 2.0

    def velocity(u):
        if u < u1:
            return v_out
        if u < u2:
            t = (u - u1) / w_blend
            return v_out + (v_cut_at_edge - v_out) * 0.5 * (1.0 - math.cos(math.pi * t))
        if u < u3:
            x = (u - u_cut_center) * cut_length_mm
            raw_ratio = x / drum_radius
            if abs(raw_ratio) > 1.0 + 1e-12:
                raise ValueError("Cut-window geometry produced an invalid arcsin argument")
            ratio = max(-1.0, min(1.0, raw_ratio))
            alpha = math.asin(ratio)
            return v_cut / math.cos(alpha)
        if u < u4:
            t = (u - u3) / w_blend
            return v_cut_at_edge + (v_out - v_cut_at_edge) * 0.5 * (1.0 - math.cos(math.pi * t))
        return v_out

    n_fine = max(n_points * 8, 8000)
    du_fine = 1.0 / n_fine
    theta_fine = [0.0]
    v_prev = velocity(0.0)
    for i in range(1, n_fine + 1):
        v_curr = velocity(i * du_fine)
        theta_fine.append(theta_fine[-1] + 0.5 * (v_prev + v_curr) * du_fine)
        v_prev = v_curr
    theta_total = theta_fine[-1]
    integration_error = abs(theta_total - 1.0)
    scale = 1.0 / theta_total
    theta_fine = [t * scale for t in theta_fine]

    table_int = []
    for i in range(n_points + 1):
        idx_f = (i / n_points) * n_fine
        idx_lo = int(idx_f)
        idx_hi = min(idx_lo + 1, n_fine)
        frac = idx_f - idx_lo
        theta_norm = theta_fine[idx_lo] * (1 - frac) + theta_fine[idx_hi] * frac
        table_int.append(int(round(theta_norm * cut_segment_counts)))

    line_period_s = cut_length_mm / line_speed_mm_s if line_speed_mm_s > 0 else 1.0
    drum_rps_cut = line_speed_mm_s / drum_circumference if drum_circumference > 0 else 0
    drum_rps_out = v_out / n_knives * line_speed_mm_s / cut_length_mm if cut_length_mm > 0 else 0
    blend_peak_dv_du = abs(v_cut_at_edge - v_out) * math.pi / (2 * w_blend) if w_blend > 0 else 0.0
    cut_peak_dv_du = v_cut * math.sin(alpha_max) / (math.cos(alpha_max) ** 3) * cut_length_mm / drum_radius
    peak_ang_accel = max(blend_peak_dv_du, cut_peak_dv_du) / n_knives / line_period_s ** 2

    diag = {
        "R": r_ratio,
        "cut_zone_master_mm": cut_zone_master_mm,
        "w_cut": w_cut,
        "w_blend": w_blend,
        "w_outside": w_outside,
        "v_cut": v_cut,
        "v_out": v_out,
        "alpha_max_deg": math.degrees(alpha_max),
        "v_cut_at_edge_normalized": v_cut_at_edge,
        "cosine_correction_at_edge": 1.0 / math.cos(alpha_max),
        "drum_radius": drum_radius,
        "drum_circumference": drum_circumference,
        "cut_segment_counts": cut_segment_counts,
        "drum_rps_cut": drum_rps_cut,
        "drum_rps_out": drum_rps_out,
        "peak_drum_rps": max(drum_rps_cut, drum_rps_out),
        "peak_ang_accel_rev_s2": peak_ang_accel,
        "table_resolution_deg": (360.0 / n_knives) / n_points,
        "integration_error": integration_error,
    }
    return table_int, diag
