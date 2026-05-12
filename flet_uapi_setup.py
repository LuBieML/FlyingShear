"""Compatibility launcher for the split Flying Shear application package."""

import flet as ft

from src.flying_shear_app.app import main
from src.flying_shear_app.domain.cambox_math import generate_rotary_knife_cam_table
from src.flying_shear_app.domain.rotary_math import (
    compute_rotary_drum_angle_rad,
    compute_rotary_drum_kinematics,
    compute_rotary_drum_tangential_mm_s,
    compute_rotary_mpos_counts_per_physical_rev,
    rotary_blade_direction_for_angle,
    shortest_angle_distance_rad,
)

__all__ = [
    "main",
    "generate_rotary_knife_cam_table",
    "compute_rotary_drum_angle_rad",
    "compute_rotary_drum_kinematics",
    "compute_rotary_drum_tangential_mm_s",
    "compute_rotary_mpos_counts_per_physical_rev",
    "rotary_blade_direction_for_angle",
    "shortest_angle_distance_rad",
]


if __name__ == "__main__":
    ft.run(main)
