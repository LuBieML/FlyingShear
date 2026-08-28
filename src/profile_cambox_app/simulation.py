"""Pure kinematic calculations used by the profile simulation page."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .domain import ConvertedProfile, ProfileError


@dataclass(frozen=True)
class SimulationSeries:
    """Time-domain axis data and a schematic point attached to the C stage."""

    time_s: tuple[float, ...]
    master_mm: tuple[float, ...]
    y_mm: tuple[float, ...]
    c_deg: tuple[float, ...]
    y_speed_mm_s: tuple[float, ...]
    y_accel_mm_s2: tuple[float, ...]
    c_speed_deg_s: tuple[float, ...]
    c_accel_deg_s2: tuple[float, ...]
    path_x_mm: tuple[float, ...]
    path_y_mm: tuple[float, ...]
    radius_mm: float
    angle_offset_deg: float

    @property
    def count(self) -> int:
        return len(self.time_s)

    @property
    def duration_s(self) -> float:
        return self.time_s[-1] if self.time_s else 0.0


def finite_difference(values: tuple[float, ...], times: tuple[float, ...]) -> tuple[float, ...]:
    """Return a same-length derivative using central differences internally."""
    if len(values) != len(times):
        raise ProfileError("Simulation values and time arrays must have the same length.")
    if len(values) < 2:
        return tuple(0.0 for _ in values)

    derivative = [(values[1] - values[0]) / (times[1] - times[0])]
    for index in range(1, len(values) - 1):
        dt = times[index + 1] - times[index - 1]
        derivative.append((values[index + 1] - values[index - 1]) / dt)
    derivative.append((values[-1] - values[-2]) / (times[-1] - times[-2]))
    return tuple(derivative)


def build_simulation_series(
    profile: ConvertedProfile,
    *,
    radius_mm: float = 50.0,
    angle_offset_deg: float = 0.0,
) -> SimulationSeries:
    """Build axis kinematics and a combined Y+C path for an attached point.

    The C centre translates along Y. A reference point at ``radius_mm`` rotates
    around that centre, producing a useful schematic of the combined motion.
    """
    if not math.isfinite(radius_mm) or radius_mm <= 0:
        raise ProfileError("C reference radius must be a positive finite value.")
    if not math.isfinite(angle_offset_deg):
        raise ProfileError("C zero-angle offset must be finite.")

    times = tuple(point.time_s for point in profile.points)
    masters = tuple(point.master_mm for point in profile.points)
    y_values = tuple(point.y_absolute_mm for point in profile.points)
    c_values = tuple(point.c_absolute_deg for point in profile.points)
    y_speed = finite_difference(y_values, times)
    y_accel = finite_difference(y_speed, times)
    c_speed = finite_difference(c_values, times)
    c_accel = finite_difference(c_speed, times)

    angles = tuple(math.radians(value + angle_offset_deg) for value in c_values)
    path_x = tuple(radius_mm * math.cos(angle) for angle in angles)
    path_y = tuple(y + radius_mm * math.sin(angle) for y, angle in zip(y_values, angles))

    return SimulationSeries(
        time_s=times,
        master_mm=masters,
        y_mm=y_values,
        c_deg=c_values,
        y_speed_mm_s=y_speed,
        y_accel_mm_s2=y_accel,
        c_speed_deg_s=c_speed,
        c_accel_deg_s2=c_accel,
        path_x_mm=path_x,
        path_y_mm=path_y,
        radius_mm=radius_mm,
        angle_offset_deg=angle_offset_deg,
    )


__all__ = ["SimulationSeries", "build_simulation_series", "finite_difference"]
