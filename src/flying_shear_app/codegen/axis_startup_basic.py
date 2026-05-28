"""Shared Trio BASIC startup axis configuration generation."""

import math


BASIC_PROGRAM_PREAMBLE = ["CANCEL(2)", "WA(100)", ""]

AXIS_PARAMETER_DEFAULTS = {
    "UNITS": "1.0",
    "SPEED": "10.0",
    "ACCEL": "1.0",
    "DECEL": "1.0",
    "FASTDEC": "200.0",
    "JERK": "100000.0",
    "DRIVE_FE_LIMIT": "1",
    "FE_LIMIT": "1",
    "FE_RANGE": "1",
    "RS_LIMIT": "0.0",
    "FS_LIMIT": "0.0",
}
AXIS_PARAMETER_ORDER = list(AXIS_PARAMETER_DEFAULTS)
AXIS_PARAMETER_INT_VALUES = {"DRIVE_FE_LIMIT", "FE_LIMIT", "FE_RANGE"}


def _format_number(value):
    return f"{float(value):.3f}"


def _coerce_axis_param_number(param_name, value):
    default = AXIS_PARAMETER_DEFAULTS[param_name]
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return number


def format_axis_param_value(param_name, value):
    number = _coerce_axis_param_number(param_name, value)
    if param_name in AXIS_PARAMETER_INT_VALUES:
        return str(int(number))
    return _format_number(number)


def axis_param_lines(axis, axis_params=None, servo_on=True):
    params = dict(AXIS_PARAMETER_DEFAULTS)
    if axis_params:
        params.update(axis_params)

    lines = [f"BASE({int(axis)})"]
    if servo_on:
        lines.append("SERVO = ON")
    for param_name in AXIS_PARAMETER_ORDER:
        lines.append(f"{param_name} = {format_axis_param_value(param_name, params[param_name])}")
    return lines


def _unique_axes(axes):
    unique = []
    seen = set()
    for axis in axes or []:
        try:
            axis_value = int(axis)
        except (TypeError, ValueError):
            continue
        if axis_value in seen:
            continue
        seen.add(axis_value)
        unique.append(axis_value)
    return unique


def _axis_params_for(axis_params_by_axis, axis):
    if not axis_params_by_axis:
        return None
    return axis_params_by_axis.get(axis) or axis_params_by_axis.get(str(axis))


def emit_axis_startup_basic_program(
    title,
    axes,
    axis_params_by_axis=None,
    servo_on=True,
    include_preamble=False,
):
    """Emit Trio BASIC startup code for a solution's configured axes."""
    axis_values = _unique_axes(axes)
    lines = [
        *(BASIC_PROGRAM_PREAMBLE if include_preamble else []),
        f"' {title} STARTUP axis configuration",
        "' Run this code on startup to configure axes before running motion code.",
    ]

    if not axis_values:
        lines.append("' No axes selected.")
        return "\n".join(lines)

    for index, axis in enumerate(axis_values):
        if index:
            lines.append("")
        lines.extend(axis_param_lines(axis, _axis_params_for(axis_params_by_axis, axis), servo_on))

    return "\n".join(lines)
