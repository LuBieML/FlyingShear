"""Flying-shear MOVELINK calculations with parameter provenance."""

from dataclasses import dataclass
import math

from .link_options import build_movelink_options


@dataclass(frozen=True)
class ValueSource:
    """Human-readable source for one generated command parameter."""

    title: str
    formula: str
    substitution: str
    result: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class MoveLinkParameter:
    """One rendered MOVELINK argument and its calculation source."""

    name: str
    text: str
    source: ValueSource


@dataclass(frozen=True)
class MoveLinkCommand:
    """One MOVELINK command row for the flying-shear profile."""

    phase: str
    purpose: str
    parameters: tuple[MoveLinkParameter, ...]

    @property
    def text(self):
        return f"MOVELINK({', '.join(param.text for param in self.parameters)})"


@dataclass(frozen=True)
class FlyingShearProfile:
    cut_length: float
    line_speed: float
    shear_max_speed: float
    shear_accel: float
    sync_time_ms: float
    safety_factor: float
    accel_dist: float
    decel_dist: float
    sync_dist: float
    stroke: float
    accel_link: float
    decel_link: float
    sync_link: float
    ret_link: float
    ret_ad: float
    v_retract_peak: float

    @property
    def sync_time_s(self):
        return self.sync_time_ms / 1000.0


def _fmt(value):
    return f"{float(value):.3f}"


def _number_source(title, value, formula, substitution, details=()):
    return ValueSource(
        title=title,
        formula=formula,
        substitution=substitution,
        result=_fmt(value),
        details=tuple(details),
    )


def _number_param(name, value, title, formula, substitution, details=()):
    return MoveLinkParameter(
        name=name,
        text=_fmt(value),
        source=_number_source(title, value, formula, substitution, details),
    )


def _constant_param(name, value, title, reason):
    return MoveLinkParameter(
        name=name,
        text=_fmt(value),
        source=ValueSource(
            title=title,
            formula="Constant for this MOVELINK phase",
            substitution=reason,
            result=_fmt(value),
        ),
    )


def calculate_flying_shear_profile(
    cut_length,
    line_speed,
    shear_max_speed,
    shear_accel,
    sync_time_ms,
    safety_factor,
):
    """Calculate the four-phase flying-shear MOVELINK profile."""
    cut_length = float(cut_length)
    line_speed = float(line_speed)
    shear_max_speed = float(shear_max_speed)
    shear_accel = float(shear_accel)
    sync_time_ms = float(sync_time_ms)
    safety_factor = float(safety_factor)

    if (
        cut_length <= 0
        or line_speed < 0
        or shear_max_speed <= 0
        or shear_accel <= 0
        or sync_time_ms < 0
        or safety_factor <= 0
    ):
        raise ValueError(
            "cut, max speed, accel, and safety must be > 0; "
            "line speed and sync time must be >= 0"
        )

    accel_dist = (line_speed * line_speed) / (2.0 * shear_accel) * safety_factor
    decel_dist = accel_dist
    sync_dist = line_speed * (sync_time_ms / 1000.0)
    stroke = accel_dist + sync_dist + decel_dist

    accel_link = 2.0 * accel_dist
    decel_link = 2.0 * decel_dist
    sync_link = sync_dist
    ret_link = cut_length - (accel_link + sync_link + decel_link)
    ret_ad = ret_link / 4.0 if ret_link > 0 else 0.0
    v_retract_peak = (
        (4.0 / 3.0) * line_speed * (stroke / ret_link)
        if ret_link > 0
        else math.inf
    )

    return FlyingShearProfile(
        cut_length=cut_length,
        line_speed=line_speed,
        shear_max_speed=shear_max_speed,
        shear_accel=shear_accel,
        sync_time_ms=sync_time_ms,
        safety_factor=safety_factor,
        accel_dist=accel_dist,
        decel_dist=decel_dist,
        sync_dist=sync_dist,
        stroke=stroke,
        accel_link=accel_link,
        decel_link=decel_link,
        sync_link=sync_link,
        ret_link=ret_link,
        ret_ad=ret_ad,
        v_retract_peak=v_retract_peak,
    )


def _describe_movelink_option_bits(profile, start_mode, link_source, direction_mode, repeat_mode, options):
    details = [f"Decimal link_options = {int(options)}"]
    set_bits = [str(bit) for bit in range(15) if int(options) & (1 << bit)]
    details.append(f"Set bits: {', '.join(set_bits) if set_bits else 'none'}")

    profile_labels = {
        "trapezoid": "trapezoidal profile, no curve option bits",
        "sine": "bit 4 enables curved profile; bits 10..12 = 0 for sine",
        "power9": "bit 4 enables curved profile; bits 10..12 = 1 for power 9",
        "power7": "bit 4 enables curved profile; bits 10..12 = 2 for power 7",
        "power5": "bit 4 enables curved profile; bits 10..12 = 3 for power 5",
        "linear_s": "bit 4 enables profile mode; bits 10..12 = 4 for linear ramp",
    }
    details.append(f"Profile: {profile_labels.get(profile, profile)}")

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
        "Repeat: bit 2 requests MOVELINK repeat"
        if repeat_mode == "movelink_repeat"
        else "Repeat: generated BASIC program loop"
    )
    return tuple(details)


def _options_param(profile, start_mode, link_source, direction_mode, repeat_mode, options, title):
    return MoveLinkParameter(
        name="link_options",
        text=str(int(options)),
        source=ValueSource(
            title=title,
            formula="build_movelink_options(profile, start, source, direction, repeat)",
            substitution=(
                f"profile={profile}, start={start_mode}, source={link_source}, "
                f"direction={direction_mode}, repeat={repeat_mode}"
            ),
            result=str(int(options)),
            details=_describe_movelink_option_bits(
                profile,
                start_mode,
                link_source,
                direction_mode,
                repeat_mode,
                options,
            ),
        ),
    )


def _link_pos_param(link_pos, start_mode, title):
    if start_mode == "absolute":
        formula = "Absolute start position from Link pos / channel input"
        substitution = f"link_pos = {_fmt(link_pos)}"
    elif start_mode == "rmark":
        formula = "R_MARK channel from Link pos / channel input"
        substitution = f"channel = {_fmt(link_pos)}"
    else:
        formula = "Optional MOVELINK parameter 7"
        substitution = (
            f"{_fmt(link_pos)} is included because link_options, link_pos, "
            "or base_dist is present"
        )
    return MoveLinkParameter(
        name="link_pos",
        text=_fmt(link_pos),
        source=ValueSource(
            title=title,
            formula=formula,
            substitution=substitution,
            result=_fmt(link_pos),
        ),
    )


def _base_dist_param(base_dist):
    return MoveLinkParameter(
        name="base_dist",
        text=_fmt(base_dist),
        source=ValueSource(
            title="base_dist",
            formula="Base distance input",
            substitution=f"use_base_dist is enabled; base_dist = {_fmt(base_dist)}",
            result=_fmt(base_dist),
            details=(
                "MOVELINK requires parameters 6 and 7 to be present when base_dist is used.",
            ),
        ),
    )


def _link_axis_param(link_axis):
    return MoveLinkParameter(
        name="link_axis",
        text=str(int(link_axis)) if isinstance(link_axis, int) else str(link_axis),
        source=ValueSource(
            title="link_axis",
            formula="Material axis selector",
            substitution=f"MOVELINK follows material/link axis {link_axis}",
            result=str(int(link_axis)) if isinstance(link_axis, int) else str(link_axis),
        ),
    )


def _command(phase, purpose, params, optional_options=None, optional_link_pos=None, optional_base_dist=None):
    final_params = list(params)
    if optional_base_dist is not None:
        final_params.extend([optional_options, optional_link_pos, optional_base_dist])
    elif optional_options is not None and optional_link_pos is not None:
        if int(optional_options.text) or float(optional_link_pos.text):
            final_params.extend([optional_options, optional_link_pos])
    return MoveLinkCommand(phase=phase, purpose=purpose, parameters=tuple(final_params))


def build_flying_shear_movelink_commands(
    profile,
    movelink_profile,
    start_mode,
    link_pos,
    link_source,
    direction_mode,
    repeat_mode,
    use_base_dist=False,
    base_dist=0.0,
    link_axis="link_ax",
):
    """Build MOVELINK-only commands with clickable provenance data."""
    link_pos = float(link_pos or 0.0)
    base_dist = float(base_dist or 0.0)
    use_base_dist = bool(use_base_dist)

    link_options = build_movelink_options(
        movelink_profile,
        start_mode,
        link_source,
        direction_mode,
        repeat_mode,
    )
    follow_options = build_movelink_options(
        movelink_profile,
        "immediate",
        link_source,
        direction_mode,
        repeat_mode,
    )

    first_optional = (
        _options_param(
            movelink_profile,
            start_mode,
            link_source,
            direction_mode,
            repeat_mode,
            link_options,
            "First-command link_options",
        ),
        _link_pos_param(link_pos, start_mode, "First-command link_pos"),
        _base_dist_param(base_dist) if use_base_dist else None,
    )
    follow_optional = (
        _options_param(
            movelink_profile,
            "immediate",
            link_source,
            direction_mode,
            repeat_mode,
            follow_options,
            "Follow-command link_options",
        ),
        _link_pos_param(0.0, "immediate", "Follow-command link_pos"),
        _base_dist_param(base_dist) if use_base_dist else None,
    )
    axis_param = _link_axis_param(link_axis)

    accel_dist_sub = (
        f"{_fmt(profile.line_speed)}^2 / (2 * {_fmt(profile.shear_accel)}) "
        f"* {_fmt(profile.safety_factor)} = {_fmt(profile.accel_dist)}"
    )
    accel_dist_details = (
        "This uses the Shear max accel input as shear_accel in the denominator.",
        f"Upstream distance: accel_dist = {accel_dist_sub}",
    )
    sync_sub = (
        f"{_fmt(profile.line_speed)} * ({_fmt(profile.sync_time_ms)} / 1000) "
        f"= {_fmt(profile.sync_dist)}"
    )
    stroke_sub = (
        f"{_fmt(profile.accel_dist)} + {_fmt(profile.sync_dist)} + "
        f"{_fmt(profile.decel_dist)} = {_fmt(profile.stroke)}"
    )
    ret_link_sub = (
        f"{_fmt(profile.cut_length)} - ({_fmt(profile.accel_link)} + "
        f"{_fmt(profile.sync_link)} + {_fmt(profile.decel_link)}) = {_fmt(profile.ret_link)}"
    )

    commands = [
        _command(
            "Accel",
            "Accelerate shear to matched line speed",
            [
                _number_param(
                    "distance",
                    profile.accel_dist,
                    "Accel distance",
                    "accel_dist = v_line^2 / (2 * shear_accel) * safety_factor",
                    accel_dist_sub,
                    accel_dist_details,
                ),
                _number_param(
                    "link_dist",
                    profile.accel_link,
                    "Accel link distance",
                    "accel_link = 2 * accel_dist",
                    f"2 * {_fmt(profile.accel_dist)} = {_fmt(profile.accel_link)}",
                    (
                        "MOVELINK rule: an acceleration ramp to matched speed uses twice the slave travel on the link axis.",
                        f"Upstream distance: accel_dist = {accel_dist_sub}",
                        "This upstream accel_dist is calculated from the line speed, shear acceleration input, and safety factor.",
                    ),
                ),
                _number_param(
                    "link_acc",
                    profile.accel_link,
                    "Accel ramp distance",
                    "link_acc = accel_link",
                    f"{_fmt(profile.accel_link)} = {_fmt(profile.accel_link)}",
                    (
                        "The full first command is acceleration, so link_acc equals link_dist.",
                        f"Upstream distance: accel_dist = {accel_dist_sub}",
                        f"Then accel_link = 2 * {_fmt(profile.accel_dist)} = {_fmt(profile.accel_link)}.",
                    ),
                ),
                _constant_param("link_dec", 0.0, "Accel decel distance", "No deceleration in the acceleration command."),
                axis_param,
            ],
            *first_optional,
        ),
        _command(
            "Sync",
            "Track material at matched speed during the cut",
            [
                _number_param(
                    "distance",
                    profile.sync_dist,
                    "Synchronized distance",
                    "sync_dist = v_line * sync_time_seconds",
                    sync_sub,
                ),
                _number_param(
                    "link_dist",
                    profile.sync_link,
                    "Synchronized link distance",
                    "sync_link = sync_dist",
                    f"{_fmt(profile.sync_dist)} = {_fmt(profile.sync_link)}",
                    ("At matched speed, slave distance equals master/link distance.",),
                ),
                _constant_param("link_acc", 0.0, "Sync accel distance", "No acceleration in the synchronized command."),
                _constant_param("link_dec", 0.0, "Sync decel distance", "No deceleration in the synchronized command."),
                axis_param,
            ],
            *follow_optional,
        ),
        _command(
            "Decel",
            "Decelerate shear after the cut",
            [
                _number_param(
                    "distance",
                    profile.decel_dist,
                    "Decel distance",
                    "decel_dist = accel_dist",
                    f"{_fmt(profile.accel_dist)} = {_fmt(profile.decel_dist)}",
                    (
                        "The deceleration phase mirrors the acceleration phase.",
                        f"Upstream distance: accel_dist = {accel_dist_sub}",
                    ),
                ),
                _number_param(
                    "link_dist",
                    profile.decel_link,
                    "Decel link distance",
                    "decel_link = 2 * decel_dist",
                    f"2 * {_fmt(profile.decel_dist)} = {_fmt(profile.decel_link)}",
                    (
                        "MOVELINK rule mirrored from the acceleration phase.",
                        f"Upstream distance: accel_dist = {accel_dist_sub}",
                        f"Then decel_dist = accel_dist = {_fmt(profile.decel_dist)}.",
                    ),
                ),
                _constant_param("link_acc", 0.0, "Decel accel distance", "No acceleration in the deceleration command."),
                _number_param(
                    "link_dec",
                    profile.decel_link,
                    "Decel ramp distance",
                    "link_dec = decel_link",
                    f"{_fmt(profile.decel_link)} = {_fmt(profile.decel_link)}",
                    (
                        "The full third command is deceleration, so link_dec equals link_dist.",
                        f"Upstream distance: accel_dist = {accel_dist_sub}",
                        f"Then decel_link = 2 * {_fmt(profile.decel_dist)} = {_fmt(profile.decel_link)}.",
                    ),
                ),
                axis_param,
            ],
            *follow_optional,
        ),
        _command(
            "Retract",
            "Return shear carriage before the next cut",
            [
                _number_param(
                    "distance",
                    -profile.stroke,
                    "Retract distance",
                    "distance = -stroke",
                    f"-({stroke_sub}) = {_fmt(-profile.stroke)}",
                    ("Negative slave distance returns the carriage home.",),
                ),
                _number_param(
                    "link_dist",
                    profile.ret_link,
                    "Retract link distance",
                    "ret_link = cut_length - (accel_link + sync_link + decel_link)",
                    ret_link_sub,
                ),
                _number_param(
                    "link_acc",
                    profile.ret_ad,
                    "Retract accel distance",
                    "ret_ad = ret_link / 4 when ret_link > 0, else 0",
                    (
                        f"{_fmt(profile.ret_link)} / 4 = {_fmt(profile.ret_ad)}"
                        if profile.ret_link > 0
                        else f"ret_link <= 0, so ret_ad = {_fmt(profile.ret_ad)}"
                    ),
                ),
                _number_param(
                    "link_dec",
                    profile.ret_ad,
                    "Retract decel distance",
                    "ret_ad = ret_link / 4 when ret_link > 0, else 0",
                    (
                        f"{_fmt(profile.ret_link)} / 4 = {_fmt(profile.ret_ad)}"
                        if profile.ret_link > 0
                        else f"ret_link <= 0, so ret_ad = {_fmt(profile.ret_ad)}"
                    ),
                ),
                axis_param,
            ],
            *follow_optional,
        ),
    ]
    return tuple(commands)


def emit_flying_shear_movelink_only(commands):
    return "\n".join(command.text for command in commands)
