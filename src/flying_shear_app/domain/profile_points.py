"""Pure helpers for rotary profile plotting and viewport ranges."""

import math


def interpolate_profile_table_value(table_values, u):
    if not table_values:
        return 0.0
    n = len(table_values)
    idx_f = max(0.0, min(1.0, float(u))) * (n - 1)
    idx_lo = int(idx_f)
    idx_hi = min(idx_lo + 1, n - 1)
    frac = idx_f - idx_lo
    return table_values[idx_lo] * (1.0 - frac) + table_values[idx_hi] * frac


def build_rotary_speed_profile_points(
    table_values,
    diag,
    cut_length_mm,
    drum_diameter_mm,
    n_knives,
    line_speed_mm_s,
    metric,
):
    n = len(table_values)
    if n < 2:
        return []

    segment_counts = float(diag.get("cut_segment_counts", 0.0))
    if segment_counts <= 0 or cut_length_mm <= 0 or n_knives < 1:
        return []

    cpr = segment_counts * n_knives
    segment_angle = 360.0 / n_knives
    du = 1.0 / (n - 1)
    circumference = math.pi * drum_diameter_mm
    points = []

    for i, table_value in enumerate(table_values):
        if i == 0:
            counts_per_u = (table_values[1] - table_values[0]) / du
        elif i == n - 1:
            counts_per_u = (table_values[-1] - table_values[-2]) / du
        else:
            counts_per_u = (table_values[i + 1] - table_values[i - 1]) / (2.0 * du)

        segment_ratio = counts_per_u / segment_counts
        drum_rps = (counts_per_u / cpr) * (line_speed_mm_s / cut_length_mm)
        if metric == "rpm":
            y_value = drum_rps * 60.0
        elif metric == "surface":
            y_value = drum_rps * circumference
        elif metric == "ratio":
            y_value = segment_ratio
        else:
            y_value = drum_rps

        angle_in_segment = (float(table_value) / segment_counts) * segment_angle
        angle_in_segment = max(0.0, min(segment_angle, angle_in_segment))
        for segment_index in range(n_knives):
            angle = segment_index * segment_angle + angle_in_segment
            if 0.0 <= angle <= 360.0:
                points.append((angle, y_value))

    points.sort(key=lambda item: item[0])
    return points


def visible_profile_points(points, start_deg, end_deg):
    return [(angle, value) for angle, value in points if start_deg <= angle <= end_deg]


def normalize_profile_angle_range(start_deg, end_deg):
    start_deg = max(0.0, min(360.0, float(start_deg)))
    end_deg = max(0.0, min(360.0, float(end_deg)))
    if end_deg - start_deg < 1.0:
        midpoint = (start_deg + end_deg) / 2.0
        start_deg = max(0.0, midpoint - 0.5)
        end_deg = min(360.0, start_deg + 1.0)
        start_deg = max(0.0, end_deg - 1.0)
    return start_deg, end_deg
