"""Focused regression check for the rotary knife cam profile math."""

import ast
import math
from pathlib import Path
import textwrap


APP_FILE = Path(__file__).with_name("flet_uapi_setup.py")


def load_generator():
    source = APP_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_rotary_knife_cam_table":
            function_source = ast.get_source_segment(source, node)
            namespace = {"math": math}
            exec(textwrap.dedent(function_source), namespace)
            return namespace["generate_rotary_knife_cam_table"]
    raise RuntimeError("generate_rotary_knife_cam_table not found")


def slope_counts_per_mm(table, index, cut_length_mm):
    mm_per_sample = cut_length_mm / (len(table) - 1)
    return (table[index + 1] - table[index - 1]) / 2.0 / mm_per_sample


def assert_close(name, actual, expected, relative_tolerance):
    relative_error = abs(actual - expected) / expected
    assert relative_error < relative_tolerance, (
        f"{name} {actual} should match {expected} "
        f"(relative error {relative_error:.6g})"
    )


def main():
    generate_rotary_knife_cam_table = load_generator()

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
