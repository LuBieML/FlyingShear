"""Pure parsing, conversion, and validation for profile CAMBOX generation."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import math
from pathlib import Path
from statistics import median
from typing import Iterable


DEFAULT_ENCODER_COUNTS = 2**23


class ProfileError(ValueError):
    """Raised when source data or configuration cannot produce a safe profile."""


@dataclass(frozen=True)
class RawProfile:
    source_path: Path
    headers: tuple[str, ...]
    time_s: tuple[float, ...]
    y_mm: tuple[float, ...]
    c_rad: tuple[float, ...]

    @property
    def count(self) -> int:
        return len(self.time_s)


@dataclass
class ProfileConfig:
    time_column: str = "temps"
    y_column: str = "Y"
    c_column: str = "C"
    y_axis: int = 0
    c_axis: int = 1
    master_axis: int = 10
    master_encoder_counts_per_rev: float = DEFAULT_ENCODER_COUNTS
    master_travel_per_rev_mm: float = 4.0
    y_encoder_counts_per_rev: float = DEFAULT_ENCODER_COUNTS
    y_travel_per_rev_mm: float = 4.0
    c_encoder_counts_per_rev: float = DEFAULT_ENCODER_COUNTS
    c_degrees_per_rev: float = 360.0
    c_user_unit_deg: float = 0.1
    master_speed_mm_s: float = 80.0
    master_accel_mm_s2: float = 1000.0
    master_decel_mm_s2: float = 1000.0
    lead_margin_mm: float = 1.0
    y_preposition_speed_mm_s: float = 40.0
    y_preposition_accel_mm_s2: float = 1000.0
    y_preposition_decel_mm_s2: float = 1000.0
    c_preposition_speed_deg_s: float = 45.0
    c_preposition_accel_deg_s2: float = 1000.0
    c_preposition_decel_deg_s2: float = 1000.0
    y_table_start: int = 1000
    c_table_start: int = 3000
    table_size: int = 500000
    values_per_table_line: int = 8
    time_uniformity_tolerance_pct: float = 0.1
    unwrap_c_axis: bool = True
    invert_y: bool = False
    invert_c: bool = False
    program_name: str = "PROFILE_CAMBOX_ONE_SHOT"

    @property
    def master_units_counts_per_mm(self) -> float:
        return self.master_encoder_counts_per_rev / self.master_travel_per_rev_mm

    @property
    def y_units_counts_per_mm(self) -> float:
        return self.y_encoder_counts_per_rev / self.y_travel_per_rev_mm

    @property
    def c_counts_per_degree(self) -> float:
        return self.c_encoder_counts_per_rev / self.c_degrees_per_rev

    @property
    def c_units_counts_per_user_unit(self) -> float:
        return self.c_counts_per_degree * self.c_user_unit_deg

    @property
    def c_full_revolution_user_units(self) -> float:
        return self.c_degrees_per_rev / self.c_user_unit_deg

    @property
    def master_acceleration_distance_mm(self) -> float:
        if self.master_accel_mm_s2 <= 0:
            return math.inf
        return self.master_speed_mm_s**2 / (2.0 * self.master_accel_mm_s2)

    @property
    def profile_start_master_mm(self) -> float:
        return self.master_acceleration_distance_mm + self.lead_margin_mm

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CamPoint:
    index: int
    time_s: float
    master_mm: float
    y_absolute_mm: float
    y_relative_mm: float
    y_counts: int
    c_absolute_rad: float
    c_absolute_deg: float
    c_relative_deg: float
    c_relative_user_units: float
    c_counts: int


@dataclass(frozen=True)
class ProfileDiagnostics:
    sample_count: int
    sample_interval_s: float
    duration_s: float
    link_distance_mm: float
    master_step_mm: float
    y_start_mm: float
    y_end_mm: float
    c_start_deg: float
    c_end_deg: float
    y_peak_speed_mm_s: float
    y_peak_accel_mm_s2: float
    c_peak_speed_deg_s: float
    c_peak_accel_deg_s2: float
    y_min_counts: int
    y_max_counts: int
    c_min_counts: int
    c_max_counts: int
    y_table_end: int
    c_table_end: int
    profile_start_master_mm: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvertedProfile:
    source: RawProfile
    config: ProfileConfig
    points: tuple[CamPoint, ...]
    diagnostics: ProfileDiagnostics

    @property
    def y_table_values(self) -> tuple[int, ...]:
        return tuple(point.y_counts for point in self.points)

    @property
    def c_table_values(self) -> tuple[int, ...]:
        return tuple(point.c_counts for point in self.points)


def _finite_float(text: str, *, row: int, column: str) -> float:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"Row {row}: {column!r} is not numeric.") from exc
    if not math.isfinite(value):
        raise ProfileError(f"Row {row}: {column!r} must be finite.")
    return value


def _resolve_header(headers: Iterable[str], requested: str) -> str:
    lookup = {header.strip().casefold(): header for header in headers}
    match = lookup.get(requested.strip().casefold())
    if match is None:
        raise ProfileError(f"Column {requested!r} was not found. Available columns: " + ", ".join(headers))
    return match


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def load_profile_csv(path: str | Path, config: ProfileConfig | None = None) -> RawProfile:
    """Load a three-column time/Y/C profile with strict numeric validation."""
    cfg = config or ProfileConfig()
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise ProfileError(f"CSV file does not exist: {source_path}")

    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        sample = source.read(4096)
        source.seek(0)
        reader = csv.DictReader(source, delimiter=_detect_delimiter(sample))
        if not reader.fieldnames:
            raise ProfileError("CSV file has no header row.")
        headers = tuple(header.strip() for header in reader.fieldnames if header is not None)
        time_header = _resolve_header(headers, cfg.time_column)
        y_header = _resolve_header(headers, cfg.y_column)
        c_header = _resolve_header(headers, cfg.c_column)

        time_values: list[float] = []
        y_values: list[float] = []
        c_values: list[float] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or all(not str(value or "").strip() for value in row.values()):
                continue
            time_values.append(_finite_float(row.get(time_header), row=row_number, column=time_header))
            y_values.append(_finite_float(row.get(y_header), row=row_number, column=y_header))
            c_values.append(_finite_float(row.get(c_header), row=row_number, column=c_header))

    if len(time_values) < 3:
        raise ProfileError("CAMBOX requires at least three profile points.")
    for index in range(1, len(time_values)):
        if time_values[index] <= time_values[index - 1]:
            raise ProfileError(f"Time must increase strictly; rows {index + 1} and {index + 2} are not increasing.")

    return RawProfile(source_path, headers, tuple(time_values), tuple(y_values), tuple(c_values))


def _round_count(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _unwrap_radians(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values:
        return values
    unwrapped = [values[0]]
    for value in values[1:]:
        adjusted = value
        previous = unwrapped[-1]
        while adjusted - previous > math.pi:
            adjusted -= 2.0 * math.pi
        while adjusted - previous < -math.pi:
            adjusted += 2.0 * math.pi
        unwrapped.append(adjusted)
    return tuple(unwrapped)


def _peak_kinematics(values: list[float], times: tuple[float, ...]) -> tuple[float, float]:
    speeds = [(values[i] - values[i - 1]) / (times[i] - times[i - 1]) for i in range(1, len(values))]
    accelerations = [
        (speeds[i] - speeds[i - 1]) / ((times[i + 1] - times[i - 1]) / 2.0)
        for i in range(1, len(speeds))
    ]
    return max((abs(v) for v in speeds), default=0.0), max((abs(v) for v in accelerations), default=0.0)


def _validate_config(config: ProfileConfig) -> None:
    if len({config.y_axis, config.c_axis, config.master_axis}) != 3:
        raise ProfileError("Y, C, and master axes must be different.")
    if min(config.y_axis, config.c_axis, config.master_axis) < 0:
        raise ProfileError("Axis numbers cannot be negative.")
    positive = {
        "master encoder counts/rev": config.master_encoder_counts_per_rev,
        "master travel/rev": config.master_travel_per_rev_mm,
        "Y encoder counts/rev": config.y_encoder_counts_per_rev,
        "Y travel/rev": config.y_travel_per_rev_mm,
        "C encoder counts/rev": config.c_encoder_counts_per_rev,
        "C degrees/rev": config.c_degrees_per_rev,
        "C user unit": config.c_user_unit_deg,
        "master speed": config.master_speed_mm_s,
        "master acceleration": config.master_accel_mm_s2,
        "master deceleration": config.master_decel_mm_s2,
    }
    invalid = [name for name, value in positive.items() if not math.isfinite(value) or value <= 0]
    if invalid:
        raise ProfileError("These settings must be positive: " + ", ".join(invalid))
    if config.lead_margin_mm < 0:
        raise ProfileError("Master lead margin cannot be negative.")
    if config.table_size < 3:
        raise ProfileError("TABLE size must be at least three.")
    if config.y_table_start < 0 or config.c_table_start < 0:
        raise ProfileError("TABLE start indexes cannot be negative.")
    if not 1 <= config.values_per_table_line <= 16:
        raise ProfileError("Values per TABLE line must be between 1 and 16.")


def convert_profile(raw: RawProfile, config: ProfileConfig | None = None) -> ConvertedProfile:
    """Convert absolute time/Y/C samples into two raw-count CAMBOX tables."""
    cfg = config or ProfileConfig()
    _validate_config(cfg)
    intervals = [raw.time_s[i] - raw.time_s[i - 1] for i in range(1, raw.count)]
    interval = median(intervals)
    tolerance = interval * cfg.time_uniformity_tolerance_pct / 100.0
    if max(abs(value - interval) for value in intervals) > tolerance + 1e-12:
        raise ProfileError("Time samples are not uniformly spaced. Resample the source before generating CAMBOX data.")

    c_values = _unwrap_radians(raw.c_rad) if cfg.unwrap_c_axis else raw.c_rad
    y_direction = -1.0 if cfg.invert_y else 1.0
    c_direction = -1.0 if cfg.invert_c else 1.0
    points: list[CamPoint] = []
    for index, (time_value, y_value, c_value) in enumerate(zip(raw.time_s, raw.y_mm, c_values)):
        time_rel = time_value - raw.time_s[0]
        y_relative = (y_value - raw.y_mm[0]) * y_direction
        c_absolute_deg = math.degrees(c_value)
        c_relative_deg = math.degrees(c_value - c_values[0]) * c_direction
        points.append(CamPoint(
            index=index,
            time_s=time_rel,
            master_mm=time_rel * cfg.master_speed_mm_s,
            y_absolute_mm=y_value,
            y_relative_mm=y_relative,
            y_counts=_round_count(y_relative * cfg.y_units_counts_per_mm),
            c_absolute_rad=c_value,
            c_absolute_deg=c_absolute_deg,
            c_relative_deg=c_relative_deg,
            c_relative_user_units=c_relative_deg / cfg.c_user_unit_deg,
            c_counts=_round_count(c_relative_deg * cfg.c_counts_per_degree),
        ))

    y_table_end = cfg.y_table_start + raw.count - 1
    c_table_end = cfg.c_table_start + raw.count - 1
    if y_table_end >= cfg.table_size or c_table_end >= cfg.table_size:
        raise ProfileError(f"TABLE allocation exceeds TSIZE={cfg.table_size}: Y ends at {y_table_end}, C ends at {c_table_end}.")
    if max(cfg.y_table_start, cfg.c_table_start) <= min(y_table_end, c_table_end):
        raise ProfileError(f"Y TABLE({cfg.y_table_start}..{y_table_end}) overlaps C TABLE({cfg.c_table_start}..{c_table_end}).")

    y_peak_speed, y_peak_accel = _peak_kinematics([p.y_absolute_mm for p in points], raw.time_s)
    c_peak_speed, c_peak_accel = _peak_kinematics([p.c_absolute_deg for p in points], raw.time_s)
    warnings: list[str] = []
    if abs(points[-1].y_relative_mm) > 1e-9 or abs(points[-1].c_relative_deg) > 1e-9:
        warnings.append("One-shot endpoints do not close; continuous repeat remains disabled.")
    if not cfg.unwrap_c_axis and any(abs(raw.c_rad[i] - raw.c_rad[i - 1]) > math.pi for i in range(1, raw.count)):
        warnings.append("C contains a jump greater than PI while angle unwrapping is disabled.")

    diagnostics = ProfileDiagnostics(
        sample_count=raw.count,
        sample_interval_s=interval,
        duration_s=points[-1].time_s,
        link_distance_mm=points[-1].master_mm,
        master_step_mm=cfg.master_speed_mm_s * interval,
        y_start_mm=raw.y_mm[0],
        y_end_mm=raw.y_mm[-1],
        c_start_deg=points[0].c_absolute_deg,
        c_end_deg=points[-1].c_absolute_deg,
        y_peak_speed_mm_s=y_peak_speed,
        y_peak_accel_mm_s2=y_peak_accel,
        c_peak_speed_deg_s=c_peak_speed,
        c_peak_accel_deg_s2=c_peak_accel,
        y_min_counts=min(p.y_counts for p in points),
        y_max_counts=max(p.y_counts for p in points),
        c_min_counts=min(p.c_counts for p in points),
        c_max_counts=max(p.c_counts for p in points),
        y_table_end=y_table_end,
        c_table_end=c_table_end,
        profile_start_master_mm=cfg.profile_start_master_mm,
        warnings=tuple(warnings),
    )
    return ConvertedProfile(raw, cfg, tuple(points), diagnostics)
