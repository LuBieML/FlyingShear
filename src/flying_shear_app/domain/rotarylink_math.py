"""Pure ROTARYLINK profile calculations and validation."""

from dataclasses import dataclass
import math

from .link_options import format_rotarylink
from .rotary_math import (
    compute_rotary_drum_circumference_mm,
    compute_rotary_units_per_mm,
)


@dataclass(frozen=True)
class RotaryLinkValueSource:
    """Human-readable source for one generated ROTARYLINK parameter."""

    title: str
    formula: str
    substitution: str
    result: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class RotaryLinkParameter:
    """One rendered ROTARYLINK argument and its calculation source."""

    name: str
    text: str
    source: RotaryLinkValueSource


@dataclass(frozen=True)
class RotaryLinkCommand:
    """One ROTARYLINK command row for the rotary knife profile."""

    phase: str
    purpose: str
    parameters: tuple[RotaryLinkParameter, ...]

    @property
    def text(self):
        return format_rotarylink(
            self.parameters[0].text,
            self.parameters[1].text,
            self.parameters[2].text,
            self.parameters[3].text,
            self.parameters[4].text,
            self.parameters[5].text,
            self.parameters[6].text,
        )


def _finite_float(value, label):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _fmt3(value):
    return f"{float(value):.3f}"


def _format_rotarylink_value(value):
    return _fmt3(value)


def _param(name, text, title, formula, substitution, result=None, details=()):
    return RotaryLinkParameter(
        name=name,
        text=text,
        source=RotaryLinkValueSource(
            title=title,
            formula=formula,
            substitution=substitution,
            result=text if result is None else result,
            details=tuple(details),
        ),
    )


def derive_rotarylink_geometry(
    drum_diameter,
    encoder_counts_per_rev,
    knives_on_drum,
    cut_length,
):
    """Return geometry inputs for a ROTARYLINK cut.

    ``cut_length`` is the product pitch in line-axis units. The ROTARYLINK
    ``linkdist`` argument is not product pitch; for matched surface speed it
    is the derived gear-ratio distance and equals ``distance``.
    """
    drum_diameter_value = _finite_float(drum_diameter, "drum_diameter")
    encoder_counts_value = _finite_float(encoder_counts_per_rev, "encoder_counts_per_rev")
    knives_value = _finite_float(knives_on_drum, "knives_on_drum")
    if knives_value < 1 or not knives_value.is_integer():
        raise ValueError("knives_on_drum must be a whole number >= 1")

    cut_length_value = _finite_float(cut_length, "cut_length")
    if cut_length_value <= 0:
        raise ValueError("cut_length must be > 0")

    circumference = compute_rotary_drum_circumference_mm(drum_diameter_value)
    units = compute_rotary_units_per_mm(encoder_counts_value, drum_diameter_value)
    knives_count = int(knives_value)
    distance = circumference / knives_count

    return {
        "drum_diameter": drum_diameter_value,
        "encoder_counts_per_rev": encoder_counts_value,
        "knives_on_drum": knives_count,
        "cut_length": cut_length_value,
        "circumference": circumference,
        "distance": distance,
        "units": units,
    }


def calculate_rotarylink_profile(
    distance,
    cut_length,
    acc,
    sync,
    sync_pos=None,
    previous_sync_end=None,
):
    """Return the Trio firmware ROTARYLINK model for matched 1:1 sync."""
    distance = float(distance)
    cut_length = float(cut_length)
    acc = float(acc)
    sync = float(sync)
    sync_pos_value = None if sync_pos is None else float(sync_pos)
    previous_sync_end_value = (
        None if previous_sync_end is None else float(previous_sync_end)
    )

    if distance <= 0:
        raise ValueError("distance must be > 0")
    if cut_length <= 0:
        raise ValueError("cut_length must be > 0")

    base_acc = acc
    base_sync = sync
    base_decel = distance - base_acc - base_sync
    link_dist = distance
    sync_gear_ratio = distance / link_dist
    line_per_cut = link_dist
    line_idle = cut_length - link_dist
    base_total = base_acc + base_sync + base_decel

    if sync_pos_value is not None:
        if sync_pos_value < 0:
            raise ValueError("sync_pos must be >= 0")
        if previous_sync_end_value is not None and sync_pos_value <= previous_sync_end_value:
            raise ValueError("sync_pos must be greater than the previous sync phase end")

    sync_start = None if sync_pos_value is None else sync_pos_value + base_acc
    sync_end = None if sync_start is None else sync_start + base_sync
    cycle_end = None if sync_pos_value is None else sync_pos_value + distance

    return {
        "distance": distance,
        "cut_length": cut_length,
        "link_dist": link_dist,
        "linkdist": link_dist,
        "acc": base_acc,
        "base_acc": base_acc,
        "sync": base_sync,
        "base_sync": base_sync,
        "decel": base_decel,
        "base_decel": base_decel,
        "base_total": base_total,
        "sync_gear_ratio": sync_gear_ratio,
        "line_per_cut_in_command": line_per_cut,
        "line_idle_between_cuts": line_idle,
        "line_idle": line_idle,
        "line_per_idle": line_idle,
        "sync_pos": sync_pos_value,
        "start_link_pos": sync_pos_value,
        "sync_start": sync_start,
        "sync_end": sync_end,
        "cycle_end": cycle_end,
        "phase_segments": [
            {"name": "acc", "base": base_acc},
            {"name": "sync", "base": base_sync},
            {"name": "decel", "base": base_decel},
        ],
    }


def _describe_rotarylink_option_bits(
    start_mode,
    profile_mode,
    link_source,
    merge,
    options,
):
    options = int(options)
    start_labels = {
        "immediate": "bits 0..1 = 0 for immediate / absolute start",
        "absolute": "bits 0..1 = 0 for absolute sync position",
        "mark": "bits 0..1 = 1 for MARK start",
        "markb": "bits 0..1 = 2 for MARKB start",
        "rmark": "bits 0..1 = 3 for R_MARK channel",
    }
    profile_labels = {
        "trapezoid": "bits 2..4 = 0 for trapezoidal profile",
        "sine": "bits 2..4 = 1 for sine speed profile",
        "power9": "bits 2..4 = 2 for power 9 polynomial speed profile",
        "power7": "bits 2..4 = 3 for power 7 polynomial speed profile",
        "power5": "bits 2..4 = 4 for power 5 polynomial speed profile",
    }
    set_bits = [str(bit) for bit in range(15) if options & (1 << bit)]
    return (
        f"Decimal link_options = {options}",
        f"Set bits: {', '.join(set_bits) if set_bits else 'none'}",
        f"Start: {start_labels.get(start_mode, start_mode)}",
        f"Profile: {profile_labels.get(profile_mode, profile_mode)}",
        (
            "Merge: bit 5 ON because cut_length is shorter than distance"
            if merge
            else "Merge: bit 5 OFF because cut_length is at least distance"
        ),
        (
            "Source: bit 6 ON, follow master DPOS"
            if link_source == "dpos"
            else "Source: bit 6 OFF, follow master MPOS"
        ),
    )


def build_rotarylink_commands(
    profile,
    geometry,
    link_axis="link_ax",
    link_options=0,
    start_pos=0.0,
    start_mode="absolute",
    profile_mode="trapezoid",
    link_source="mpos",
    merge=False,
):
    """Build ROTARYLINK-only command metadata with parameter provenance."""
    distance = float(profile["distance"])
    link_dist = float(profile["link_dist"])
    base_acc = float(profile["base_acc"])
    base_sync = float(profile["base_sync"])
    cut_length = float(profile["cut_length"])
    line_idle = float(profile["line_per_idle"])
    start_pos = float(start_pos)
    link_axis_text = str(int(link_axis)) if isinstance(link_axis, int) else str(link_axis)
    options = int(link_options)
    circumference = float(geometry["circumference"])
    drum_diameter = float(geometry["drum_diameter"])
    knives_on_drum = int(geometry["knives_on_drum"])

    command = RotaryLinkCommand(
        phase="Profile",
        purpose="Run one rotary/base-axis cycle linked to one knife segment.",
        parameters=(
            _param(
                "distance",
                _fmt3(distance),
                "distance",
                "distance = circumference / knives_on_drum",
                f"{_fmt3(circumference)} / {knives_on_drum} = {_fmt3(distance)}",
                details=(
                    f"circumference = pi * drum_diameter = pi * {_fmt3(drum_diameter)} = {_fmt3(circumference)}.",
                    "This is the base-axis travel for one knife segment.",
                ),
            ),
            _param(
                "linkdist",
                _fmt3(link_dist),
                "linkdist",
                "linkdist = distance",
                f"{_fmt3(distance)} = {_fmt3(link_dist)}",
                details=(
                    "For matched 1:1 surface speed, ROTARYLINK uses the same distance on the link axis.",
                ),
            ),
            _param(
                "base_acc",
                _fmt3(base_acc),
                "base_acc",
                "base_acc = Base accel input",
                f"{_fmt3(base_acc)} = {_fmt3(base_acc)}",
                details=(
                    "ROTARYLINK expects a base-axis accel distance here, not an acceleration rate.",
                ),
            ),
            _param(
                "base_sync",
                _fmt3(base_sync),
                "base_sync",
                "base_sync = Sync distance input",
                f"{_fmt3(base_sync)} = {_fmt3(base_sync)}",
                details=(
                    "This is the base-axis distance over which the knife is synchronized with the material.",
                ),
            ),
            _param(
                "link_axis",
                link_axis_text,
                "link_axis",
                "Material axis selector",
                f"ROTARYLINK follows material/link axis {link_axis_text}",
            ),
            _param(
                "moveoptions",
                str(options),
                "moveoptions",
                "moveoptions = build_rotarylink_options(start, profile, source, merge)",
                (
                    f"start={start_mode}, profile={profile_mode}, source={link_source}, "
                    f"merge={bool(merge)}"
                ),
                result=str(options),
                details=_describe_rotarylink_option_bits(
                    start_mode,
                    profile_mode,
                    link_source,
                    merge,
                    options,
                ),
            ),
            _param(
                "start_pos",
                _fmt3(start_pos),
                "start_pos",
                "start_pos = base_acc",
                f"{_fmt3(base_acc)} = {_fmt3(start_pos)}",
                details=(
                    "The generated loop increments start_pos by cut_length after each ROTARYLINK call.",
                    f"line_idle_between_cuts = cut_length - distance = {_fmt3(cut_length)} - {_fmt3(distance)} = {_fmt3(line_idle)}.",
                ),
            ),
        ),
    )
    return (command,)


def emit_rotarylink_only(commands):
    return "\n".join(command.text for command in commands)


def validate_rotarylink_profile(profile, abs_tol=1e-6, rel_tol=1e-9):
    """Validate the Trio firmware ROTARYLINK model and external cut spacing."""
    distance = _finite_float(profile["distance"], "distance")
    cut_length = _finite_float(
        profile.get("cut_length", profile.get("link_dist")),
        "cut_length",
    )
    link_dist = _finite_float(profile["link_dist"], "link_dist")
    acc = _finite_float(profile["acc"], "acc")
    sync = _finite_float(profile["sync"], "sync")
    base_sync = _finite_float(profile.get("base_sync", sync), "base_sync")
    base_decel = _finite_float(profile["base_decel"], "base_decel")
    line_idle = _finite_float(
        profile.get(
            "line_idle_between_cuts",
            profile.get("line_idle", profile.get("line_per_idle", cut_length - link_dist)),
        ),
        "line_idle",
    )
    sync_gear_ratio = _finite_float(
        profile.get("sync_gear_ratio", distance / link_dist if link_dist else 0.0),
        "sync_gear_ratio",
    )

    errors = []
    warnings = []
    info = []
    if sync <= 0:
        errors.append("sync_distance must be > 0")
    if acc <= 0:
        errors.append("base_acc must be > 0")
    if acc + base_sync > distance + abs_tol:
        errors.append(
            "Acc + sync exceeds one drum cycle. The firmware would silently "
            "rescale accel internally - do not run this. Reduce base_acc, "
            "sync_distance, or increase drum_diameter / knives."
        )
    if link_dist <= 0:
        errors.append(
            f"linkdist must be > 0; computed {_format_rotarylink_value(link_dist)}"
        )

    if not math.isclose(base_decel, distance - acc - base_sync, rel_tol=rel_tol, abs_tol=abs_tol):
        errors.append(
            "base_decel must equal distance - base_acc - base_sync"
        )
    if not math.isclose(link_dist, distance, rel_tol=rel_tol, abs_tol=abs_tol):
        errors.append("linkdist must equal distance for matched 1:1 sync")
    if link_dist > 0 and not math.isclose(
        sync_gear_ratio,
        distance / link_dist,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    ):
        errors.append("sync_gear_ratio must equal distance / linkdist")
    if (
        not math.isclose(sync, base_sync, rel_tol=rel_tol, abs_tol=abs_tol)
    ):
        errors.append("base_sync must equal sync_distance")

    if not errors:
        if line_idle < -abs_tol:
            warnings.append(
                "Cut length "
                f"({_format_rotarylink_value(cut_length)}) < distance "
                f"({_format_rotarylink_value(distance)}). Cuts overlap by "
                f"{_format_rotarylink_value(distance - cut_length)} mm of line per cycle; "
                "generated program must set link_options.5 (merge) to chain "
                "commands continuously."
            )
        elif math.isclose(cut_length, distance, rel_tol=rel_tol, abs_tol=abs_tol):
            info.append("cut_length == distance: no idle between cuts")
        else:
            info.append(
                "normal case: idle between cuts = "
                f"{_format_rotarylink_value(line_idle)}"
            )

    messages = errors + warnings + info
    severity = "error" if errors else "warning" if warnings else "ok"
    return {
        "severity": severity,
        "messages": messages,
        "message": "  |  ".join(messages) if messages else "All checks pass",
        "requires_merge": bool(warnings),
        "line_idle": line_idle,
        "line_per_idle": line_idle,
        "line_idle_between_cuts": line_idle,
    }


def calculate_rotarylink_base_sync_speed(line_speed, profile):
    """Return the base-axis speed during ROTARYLINK sync for a line-axis speed."""
    line_speed = float(line_speed)
    if line_speed <= 0:
        raise ValueError("line_speed must be > 0")
    return line_speed * float(profile.get("sync_gear_ratio", 1.0))


def estimate_rotarylink_slave_accel(line_speed, profile):
    """Estimate acceleration needed for the base/slave axis to reach sync speed."""
    acc = float(profile["acc"])
    if acc <= 0:
        return None
    base_sync_speed = calculate_rotarylink_base_sync_speed(line_speed, profile)
    return (base_sync_speed ** 2) / (2.0 * acc)
