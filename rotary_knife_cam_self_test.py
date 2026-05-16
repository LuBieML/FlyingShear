"""Focused regression check for rotary knife motion math."""

import math

from src.flying_shear_app.domain.cambox_math import generate_rotary_knife_cam_table
from src.flying_shear_app.domain.rotary_math import (
    compute_rotary_drum_angle_rad,
    compute_rotary_drum_kinematics,
    compute_rotary_drum_tangential_mm_s,
    compute_rotary_units_per_mm,
    compute_rotary_mpos_counts_per_physical_rev,
    rotary_blade_direction_for_angle,
    shortest_angle_distance_rad,
)


def slope_counts_per_mm(table, index, cut_length_mm):
    mm_per_sample = cut_length_mm / (len(table) - 1)
    return (table[index + 1] - table[index - 1]) / 2.0 / mm_per_sample


def assert_close(name, actual, expected, relative_tolerance):
    relative_error = abs(actual - expected) / expected
    assert relative_error < relative_tolerance, (
        f"{name} {actual} should match {expected} "
        f"(relative error {relative_error:.6g})"
    )


def assert_near(name, actual, expected, tolerance):
    error = abs(actual - expected)
    assert error < tolerance, (
        f"{name} {actual} should match {expected} "
        f"(absolute error {error:.6g})"
    )


def main():
    compute_mpos_counts = compute_rotary_mpos_counts_per_physical_rev
    compute_drum_angle = compute_rotary_drum_angle_rad
    compute_drum_tangential = compute_rotary_drum_tangential_mm_s
    compute_drum_kinematics = compute_rotary_drum_kinematics
    shortest_angle_distance = shortest_angle_distance_rad
    blade_direction = rotary_blade_direction_for_angle

    mpos_counts_per_rev = compute_mpos_counts(8_388_608, 2_097_152)
    assert_close("MPOS counts per physical rev", mpos_counts_per_rev, 4.0, 1e-12)
    assert_close("Quarter-turn angle", compute_drum_angle(1.0, mpos_counts_per_rev), math.pi / 2.0, 1e-12)
    assert_near("Zero-count angle", compute_drum_angle(0.0, mpos_counts_per_rev), 0.0, 1e-12)
    assert_close("Half-turn angle", compute_drum_angle(2.0, mpos_counts_per_rev), math.pi, 1e-12)
    zero_dx, zero_dy = blade_direction(0.0)
    half_dx, half_dy = blade_direction(math.pi)
    assert_near("Blade zero x", zero_dx, 0.0, 1e-12)
    assert_near("Blade zero y points top", zero_dy, -1.0, 1e-12)
    assert_near("Blade half-turn x", half_dx, 0.0, 1e-12)
    assert_near("Blade half-turn y points material", half_dy, 1.0, 1e-12)
    assert_close("Material contact distance at top", shortest_angle_distance(0.0, math.pi), math.pi, 1e-12)
    assert_near("Material contact distance at bottom", shortest_angle_distance(math.pi, math.pi), 0.0, 1e-12)
    assert_close(
        "One-rps drum tangential speed",
        compute_drum_tangential(4.0, mpos_counts_per_rev, 20.0),
        math.pi * 20.0,
        1e-12,
    )
    current_setup_mpos_per_rev = compute_mpos_counts(8_388_608, 8_388_608)
    assert_close("Current setup MPOS counts per physical rev", current_setup_mpos_per_rev, 1.0, 1e-12)
    assert_close(
        "Current setup quarter-turn angle",
        compute_drum_angle(2.25, current_setup_mpos_per_rev),
        math.pi / 2.0,
        1e-12,
    )
    user_setup_mspeed = 556.0 / (math.pi * 20.0)
    assert_close(
        "Current setup tangential speed",
        compute_drum_tangential(user_setup_mspeed, current_setup_mpos_per_rev, 20.0),
        556.0,
        1e-12,
    )
    kinematics = compute_drum_kinematics(
        drum_mpos=2.25,
        drum_mspeed=user_setup_mspeed,
        mpos_counts_per_physical_rev=current_setup_mpos_per_rev,
        drum_diameter_mm=20.0,
        drum_direction_reversed=False,
    )
    assert_close("Shared kinematics RPS", kinematics["drum_rps"], user_setup_mspeed, 1e-12)
    assert_close("Shared kinematics circumference", kinematics["drum_circumference_mm"], math.pi * 20.0, 1e-12)
    assert_close("Shared kinematics tangential", kinematics["drum_tangential_mm_s"], 556.0, 1e-12)
    assert_close("Shared kinematics angle", kinematics["drum_angle_rad"], math.pi / 2.0, 1e-12)
    reversed_kinematics = compute_drum_kinematics(
        drum_mpos=0.25,
        drum_mspeed=1.0,
        mpos_counts_per_physical_rev=current_setup_mpos_per_rev,
        drum_diameter_mm=20.0,
        drum_direction_reversed=True,
    )
    assert_near("Reversed kinematics angle", reversed_kinematics["drum_angle_rad"], 1.5 * math.pi, 1e-12)
    assert_near("Reversed kinematics tangential", reversed_kinematics["drum_tangential_mm_s"], -math.pi * 20.0, 1e-12)
    try:
        compute_drum_kinematics(
            drum_mpos=0.0,
            drum_mspeed=0.0,
            mpos_counts_per_physical_rev=0.0,
            drum_diameter_mm=20.0,
        )
    except ValueError as ex:
        assert "mpos_counts_per_physical_rev must be positive" in str(ex)
    else:
        raise AssertionError("Non-positive MPOS/rev should fail validation")

    cut_length_mm = 20.0
    drum_diameter_mm = 20.0
    encoder_counts_per_rev = 8_388_608
    n_points = 2000

    table, diag = generate_rotary_knife_cam_table(
        cut_length_mm=cut_length_mm,
        drum_diameter_mm=drum_diameter_mm,
        n_knives=1,
        cut_window_deg=30,
        encoder_counts_per_rev=encoder_counts_per_rev,
        n_points=n_points,
        blend_fraction=0.4,
        line_speed_mm_s=20,
    )

    expected_center_slope = encoder_counts_per_rev / (math.pi * drum_diameter_mm)
    assert_close(
        "Rotary knife drum UNITS",
        diag["drum_axis_units_per_mm"],
        compute_rotary_units_per_mm(encoder_counts_per_rev, drum_diameter_mm),
        1e-12,
    )
    mid = (len(table) - 1) // 2
    slope_center = slope_counts_per_mm(table, mid, cut_length_mm)
    assert_close("Cut center slope", slope_center, expected_center_slope, 0.001)

    u3 = 0.5 + diag["w_cut"] / 2.0
    edge_index = max(1, min(len(table) - 2, int(round(u3 * n_points)) - 1))
    edge_u = edge_index / n_points
    edge_alpha = math.asin(abs((edge_u - 0.5) * cut_length_mm / diag["drum_radius"]))
    expected_edge_slope = expected_center_slope / math.cos(edge_alpha)
    slope_edge = slope_counts_per_mm(table, edge_index, cut_length_mm)
    assert_close("Cut edge slope", slope_edge, expected_edge_slope, 0.003)

    expected_edge_boost = 1.0 / math.cos(math.radians(15.0))
    assert_close(
        "Cosine correction diagnostic",
        diag["cosine_correction_at_edge"],
        expected_edge_boost,
        1e-12,
    )

    assert table[-1] == int(round(encoder_counts_per_rev)), (
        f"Total cycle rotation {table[-1]} should equal "
        f"{encoder_counts_per_rev}"
    )
    assert diag["integration_error"] < 1e-6, (
        f"Integration error {diag['integration_error']} should be < 1e-6"
    )

    try:
        generate_rotary_knife_cam_table(
            cut_length_mm=20,
            drum_diameter_mm=20,
            n_knives=1,
            cut_window_deg=180,
            encoder_counts_per_rev=encoder_counts_per_rev,
            n_points=720,
            blend_fraction=0.4,
            line_speed_mm_s=20,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("180 degree cut window should fail geometry validation")

    print("rotary_knife_cam_self_test: OK")


if __name__ == "__main__":
    main()
