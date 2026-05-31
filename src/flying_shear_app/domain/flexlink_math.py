"""Pure FLEXLINK curve, profile, and command helpers."""

from dataclasses import dataclass
import math

from .link_options import build_flexlink_options


@dataclass(frozen=True)
class FlexLinkValueSource:
    """Human-readable source for one generated FLEXLINK parameter."""

    title: str
    formula: str
    substitution: str
    result: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlexLinkParameter:
    """One rendered FLEXLINK argument and its calculation source."""

    name: str
    text: str
    source: FlexLinkValueSource


@dataclass(frozen=True)
class FlexLinkCommand:
    """One FLEXLINK command row for the VFFS profile."""

    phase: str
    purpose: str
    parameters: tuple[FlexLinkParameter, ...]

    @property
    def text(self):
        return f"FLEXLINK({', '.join(param.text for param in self.parameters)})"


@dataclass(frozen=True)
class VffsFlexLinkProfile:
    """Calculated VFFS cross-seal profile values."""

    cycle_pitch: float
    jaw_period: float
    reg_trim: float
    line_speed: float
    base_in_mm: float
    base_out_mm: float
    excite_acc_mm: float
    excite_dec_mm: float
    seal_dwell_min_ms: float
    base_dist: float
    excite_dist: float
    link_dist: float
    excite_window_mm: float
    flat_mm: float
    base_in_pct: float
    base_out_pct: float
    excite_acc_pct: float
    excite_dec_pct: float
    mech_seal_advance: float
    bump_denom_mm: float
    peak_extra_speed: float
    peak_speed: float
    cycle_time_ms: float
    seal_dwell_mm: float
    seal_dwell_ms: float
    required_contact_mm: float
    dwell_margin_ms: float


def _fmt3(value):
    return f"{float(value):.3f}"


def _fmt2(value):
    return f"{float(value):.2f}"


def _number_param(name, text, title, formula, substitution, result=None, details=()):
    return FlexLinkParameter(
        name=name,
        text=text,
        source=FlexLinkValueSource(
            title=title,
            formula=formula,
            substitution=substitution,
            result=text if result is None else result,
            details=tuple(details),
        ),
    )


def _link_axis_param(link_axis):
    text = str(int(link_axis)) if isinstance(link_axis, int) else str(link_axis)
    return FlexLinkParameter(
        name="link_axis",
        text=text,
        source=FlexLinkValueSource(
            title="link_axis",
            formula="Film pull axis selector",
            substitution=f"FLEXLINK follows material/link axis {text}",
            result=text,
        ),
    )


def calculate_vffs_flexlink_profile(
    cycle_pitch,
    jaw_period,
    reg_trim,
    line_speed,
    base_in_mm,
    base_out_mm,
    excite_acc_mm,
    excite_dec_mm,
    seal_dwell_min_ms=0.0,
):
    """Calculate the VFFS cross-seal FLEXLINK profile."""
    cycle_pitch = float(cycle_pitch)
    jaw_period = float(jaw_period)
    reg_trim = float(reg_trim)
    line_speed = float(line_speed)
    base_in_mm = float(base_in_mm)
    base_out_mm = float(base_out_mm)
    excite_acc_mm = float(excite_acc_mm)
    excite_dec_mm = float(excite_dec_mm)
    seal_dwell_min_ms = float(seal_dwell_min_ms)

    excite_dist = (jaw_period - cycle_pitch) + reg_trim
    excite_window_mm = max(0.0, cycle_pitch - base_in_mm - base_out_mm)
    flat_mm = max(0.0, excite_window_mm - excite_acc_mm - excite_dec_mm)

    if cycle_pitch > 0:
        base_in_pct = base_in_mm / cycle_pitch * 100.0
        base_out_pct = base_out_mm / cycle_pitch * 100.0
    else:
        base_in_pct = 0.0
        base_out_pct = 0.0

    if excite_window_mm > 0:
        excite_acc_pct = excite_acc_mm / excite_window_mm * 100.0
        excite_dec_pct = excite_dec_mm / excite_window_mm * 100.0
    else:
        excite_acc_pct = 0.0
        excite_dec_pct = 0.0

    base_dist = cycle_pitch
    link_dist = cycle_pitch
    mech_seal_advance = jaw_period - cycle_pitch
    bump_denom_mm = 0.5 * excite_acc_mm + flat_mm + 0.5 * excite_dec_mm
    if bump_denom_mm > 0 and line_speed > 0:
        peak_extra_speed = abs(excite_dist) * line_speed / bump_denom_mm
    else:
        peak_extra_speed = 0.0
    peak_speed = line_speed + peak_extra_speed if line_speed > 0 else 0.0
    cycle_time_ms = cycle_pitch / line_speed * 1000.0 if line_speed > 0 else 0.0
    seal_dwell_mm = base_in_mm + base_out_mm
    seal_dwell_ms = seal_dwell_mm / line_speed * 1000.0 if line_speed > 0 else 0.0
    required_contact_mm = (
        seal_dwell_min_ms * line_speed / 1000.0
        if seal_dwell_min_ms > 0 and line_speed > 0
        else 0.0
    )
    dwell_margin_ms = seal_dwell_ms - seal_dwell_min_ms

    return VffsFlexLinkProfile(
        cycle_pitch=cycle_pitch,
        jaw_period=jaw_period,
        reg_trim=reg_trim,
        line_speed=line_speed,
        base_in_mm=base_in_mm,
        base_out_mm=base_out_mm,
        excite_acc_mm=excite_acc_mm,
        excite_dec_mm=excite_dec_mm,
        seal_dwell_min_ms=seal_dwell_min_ms,
        base_dist=base_dist,
        excite_dist=excite_dist,
        link_dist=link_dist,
        excite_window_mm=excite_window_mm,
        flat_mm=flat_mm,
        base_in_pct=base_in_pct,
        base_out_pct=base_out_pct,
        excite_acc_pct=excite_acc_pct,
        excite_dec_pct=excite_dec_pct,
        mech_seal_advance=mech_seal_advance,
        bump_denom_mm=bump_denom_mm,
        peak_extra_speed=peak_extra_speed,
        peak_speed=peak_speed,
        cycle_time_ms=cycle_time_ms,
        seal_dwell_mm=seal_dwell_mm,
        seal_dwell_ms=seal_dwell_ms,
        required_contact_mm=required_contact_mm,
        dwell_margin_ms=dwell_margin_ms,
    )


def _describe_flexlink_option_bits(curve_type, start_mode, link_source, direction_mode, repeat_mode, options):
    details = [f"Decimal link_options = {int(options)}"]
    set_bits = [str(bit) for bit in range(15) if int(options) & (1 << bit)]
    details.append(f"Set bits: {', '.join(set_bits) if set_bits else 'none'}")

    curve_labels = {
        "sine": "bits 10..12 = 0 for sine",
        "poly9": "bits 10..12 = 1 for polynomial power 9",
        "poly7": "bits 10..12 = 2 for polynomial power 7",
        "poly5": "bits 10..12 = 3 for polynomial power 5",
        "linear": "bits 10..12 = 4 for linear ramp",
    }
    details.append(f"Curve: {curve_labels.get(curve_type, curve_type)}")

    start_labels = {
        "immediate": "immediate start, no start bit",
        "mark": "bit 0 starts from MARK",
        "absolute": "bit 1 starts at an absolute link-axis position",
        "markb": "bit 8 starts from MARKB",
        "rmark": "bit 9 starts from an R_MARK channel",
    }
    details.append(f"Start: {start_labels.get(start_mode, start_mode)}")
    details.append(
        "Source: bit 13 follows master DPOS"
        if link_source == "dpos"
        else "Source: follows master MPOS"
    )

    if direction_mode == "positive":
        details.append("Direction: bit 5 only links on positive master movement")
    elif direction_mode == "positive_threshold":
        details.append("Direction: bit 14 waits for positive movement threshold")
    else:
        details.append("Direction: any master direction")

    details.append(
        "Repeat: bit 2 requests FLEXLINK repeat"
        if repeat_mode == "flexlink_repeat"
        else "Repeat: generated BASIC program loop"
    )
    return tuple(details)


def _options_param(curve_type, start_mode, link_source, direction_mode, repeat_mode, options):
    return FlexLinkParameter(
        name="link_options",
        text=str(int(options)),
        source=FlexLinkValueSource(
            title="link_options",
            formula="build_flexlink_options(curve, start, source, direction, repeat)",
            substitution=(
                f"curve={curve_type}, start={start_mode}, source={link_source}, "
                f"direction={direction_mode}, repeat={repeat_mode}"
            ),
            result=str(int(options)),
            details=_describe_flexlink_option_bits(
                curve_type,
                start_mode,
                link_source,
                direction_mode,
                repeat_mode,
                options,
            ),
        ),
    )


def _start_pos_param(link_pos, start_mode):
    if start_mode == "absolute":
        formula = "Absolute start position from Link pos / channel input"
        substitution = f"start_pos = {_fmt3(link_pos)}"
    elif start_mode == "rmark":
        formula = "R_MARK channel from Link pos / channel input"
        substitution = f"channel = {_fmt3(link_pos)}"
    else:
        formula = "Optional FLEXLINK start_pos parameter"
        substitution = (
            f"{_fmt3(link_pos)} is included because link_options or start_pos is present"
        )
    return FlexLinkParameter(
        name="start_pos",
        text=_fmt3(link_pos),
        source=FlexLinkValueSource(
            title="start_pos",
            formula=formula,
            substitution=substitution,
            result=_fmt3(link_pos),
        ),
    )


def build_vffs_flexlink_commands(
    profile,
    curve_type,
    start_mode,
    link_pos,
    link_source,
    direction_mode,
    repeat_mode,
    link_axis="link_ax",
):
    """Build FLEXLINK-only commands with clickable provenance data."""
    link_pos = float(link_pos or 0.0)
    options = build_flexlink_options(
        curve_type,
        start_mode,
        link_source,
        direction_mode,
        repeat_mode,
    )
    open_window_sub = (
        f"{_fmt3(profile.cycle_pitch)} - {_fmt3(profile.base_in_mm)} - "
        f"{_fmt3(profile.base_out_mm)} = {_fmt3(profile.excite_window_mm)}"
    )
    excite_dist_sub = (
        f"({_fmt3(profile.jaw_period)} - {_fmt3(profile.cycle_pitch)}) "
        f"+ {_fmt3(profile.reg_trim)} = {_fmt3(profile.excite_dist)}"
    )

    params = [
        _number_param(
            "base_dist",
            _fmt3(profile.base_dist),
            "base_dist",
            "base_dist = bag_length",
            f"{_fmt3(profile.cycle_pitch)} = {_fmt3(profile.base_dist)}",
            details=(
                "VFFS convention: the jaw axis has a 1:1 base motion over one bag length.",
            ),
        ),
        _number_param(
            "excite_dist",
            _fmt3(profile.excite_dist),
            "excite_dist",
            "excite_dist = (jaw_period - bag_length) + reg_trim",
            excite_dist_sub,
            details=(
                f"Mechanical seal advance = jaw_period - bag_length = {_fmt3(profile.mech_seal_advance)}.",
                "Registration trim is added on top of the mechanical advance.",
            ),
        ),
        _number_param(
            "link_dist",
            _fmt3(profile.link_dist),
            "link_dist",
            "link_dist = bag_length",
            f"{_fmt3(profile.cycle_pitch)} = {_fmt3(profile.link_dist)}",
            details=(
                "This is the positive film-pull distance for one complete cross-seal cycle.",
            ),
        ),
        _number_param(
            "base_in",
            _fmt2(profile.base_in_pct),
            "base_in percentage",
            "base_in = seal_contact_in / bag_length * 100",
            (
                f"{_fmt3(profile.base_in_mm)} / {_fmt3(profile.cycle_pitch)} "
                f"* 100 = {_fmt2(profile.base_in_pct)}"
            ),
            details=(
                "FLEXLINK arguments 4-7 are percentages. The UI takes millimetres for readability.",
            ),
        ),
        _number_param(
            "base_out",
            _fmt2(profile.base_out_pct),
            "base_out percentage",
            "base_out = seal_contact_out / bag_length * 100",
            (
                f"{_fmt3(profile.base_out_mm)} / {_fmt3(profile.cycle_pitch)} "
                f"* 100 = {_fmt2(profile.base_out_pct)}"
            ),
            details=(
                "This is the locked 1:1 contact percentage after the excitation window.",
            ),
        ),
        _number_param(
            "excite_acc",
            _fmt2(profile.excite_acc_pct),
            "excite_acc percentage",
            "excite_acc = advance_acc / open_window * 100",
            (
                f"{_fmt3(profile.excite_acc_mm)} / {_fmt3(profile.excite_window_mm)} "
                f"* 100 = {_fmt2(profile.excite_acc_pct)}"
            ),
            details=(
                f"Open window = bag_length - seal_contact_in - seal_contact_out = {open_window_sub}.",
                "This percentage controls how much of the open window is used to ramp into the excitation move.",
            ),
        ),
        _number_param(
            "excite_dec",
            _fmt2(profile.excite_dec_pct),
            "excite_dec percentage",
            "excite_dec = advance_dec / open_window * 100",
            (
                f"{_fmt3(profile.excite_dec_mm)} / {_fmt3(profile.excite_window_mm)} "
                f"* 100 = {_fmt2(profile.excite_dec_pct)}"
            ),
            details=(
                f"Open window = bag_length - seal_contact_in - seal_contact_out = {open_window_sub}.",
                "This percentage controls how much of the open window is used to ramp out of the excitation move.",
            ),
        ),
        _link_axis_param(link_axis),
    ]

    if options or link_pos:
        params.extend(
            [
                _options_param(
                    curve_type,
                    start_mode,
                    link_source,
                    direction_mode,
                    repeat_mode,
                    options,
                ),
                _start_pos_param(link_pos, start_mode),
            ]
        )

    return (
        FlexLinkCommand(
            phase="Cycle",
            purpose="VFFS cross-seal profile for one bag pitch",
            parameters=tuple(params),
        ),
    )


def emit_vffs_flexlink_only(commands):
    return "\n".join(command.text for command in commands)


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
