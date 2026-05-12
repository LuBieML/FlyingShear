# Flying Shear Math

This document explains the math used by the linear flying shear MOVELINK
calculator in `flet_uapi_setup.py`. It is scoped to the "Flying Shear
MOVELINK Calculator", not the rotary knife CAMBOX generator or the FLEXLINK
flow-wrapper calculator.

## Variables

The calculator sizes a shear carriage, also called the slave axis, from the
material or encoder axis, also called the master or link axis.

| Symbol | App input / result | Meaning | Units |
| --- | --- | --- | --- |
| `L` | Cut length | Master distance between cuts | mm |
| `v` | MAX line speed | Maximum material speed used for sizing | mm/s |
| `vmax` | Shear max speed | Maximum allowed shear carriage speed | mm/s |
| `a` | Shear max accel | Maximum allowed shear acceleration used for sizing | mm/s2 |
| `tsync_ms` | Sync time | Time the shear should stay matched to the material | ms |
| `sf` | Safety factor | Multiplier applied to calculated accel/decel distance | none |
| `d_acc` | internal | Shear distance used to accelerate to line speed | mm |
| `d_sync` | internal | Shear distance while matched to the material | mm |
| `d_dec` | internal | Shear distance used to decelerate back to zero | mm |
| `stroke` | Stroke needed | Total forward shear travel before retract | mm |
| `l_acc` | Accel link distance | Master distance consumed during acceleration | mm |
| `l_sync` | Track link distance | Master distance consumed during synchronized cutting | mm |
| `l_dec` | Decel link distance | Master distance consumed during deceleration | mm |
| `l_ret` | Return link distance | Remaining master distance available for retract | mm |
| `v_ret_peak` | Retract peak speed | Estimated peak shear speed during the retract command | mm/s |

MOVELINK links slave position to master position. If:

```text
r = slave_velocity / master_velocity
```

then `r` is also the slope of the slave-position curve against master
position:

```text
r = d(slave_position) / d(master_position)
```

The slave distance moved during any linked phase is the area under the `r`
curve across the master distance for that phase.

## Phase Model

The calculator breaks each cut cycle into four phases:

1. Accelerate the shear carriage from zero to line speed.
2. Track the material at line speed while the cut happens.
3. Decelerate the shear carriage from line speed to zero.
4. Retract the shear carriage back to home before the next cut.

The forward phases are sized first. The leftover master distance is then used
for retract.

## Acceleration Distance

The app uses the constant-acceleration kinematic equation:

```text
v^2 = u^2 + 2 * a * s
```

The shear starts the forward acceleration phase from rest, so `u = 0`:

```text
v^2 = 2 * a * d_acc
d_acc = v^2 / (2 * a)
```

The calculator then applies the safety factor:

```text
d_acc = v^2 / (2 * a) * sf
```

Deceleration is mirrored:

```text
d_dec = d_acc
```

The safety factor increases the distance reserved for acceleration and
deceleration. It does not increase the requested line speed.

## Why Accel Link Distance Is Twice The Shear Travel

During acceleration, the shear speed ramps from `0` to `v`. For a normalized
ramp, the average shear speed over the phase is:

```text
average_shear_speed = (0 + v) / 2 = v / 2
```

The material is moving at `v`, so over the same time the master axis travels
twice as far as the shear:

```text
master_distance = v * time
shear_distance = (v / 2) * time
master_distance = 2 * shear_distance
```

Therefore:

```text
l_acc = 2 * d_acc
l_dec = 2 * d_dec
```

This is the same practical MOVELINK rule shown in `MOVELINK.md`: to accelerate
to a matched speed, the link distance should be twice the slave movement.

## Synchronized Cut Distance

The sync time is entered in milliseconds, so it is first converted to seconds:

```text
tsync = tsync_ms / 1000
```

While synchronized, the shear speed equals material speed:

```text
d_sync = v * tsync
```

Because master and slave speeds match, the distance ratio is one-to-one:

```text
l_sync = d_sync
```

During this phase, the shear carriage should be moving at the same speed as
the material. This is why the forward peak shear speed is `v`.

## Forward Stroke

The total forward shear travel before retract is:

```text
stroke = d_acc + d_sync + d_dec
```

Since `d_dec = d_acc`, this is:

```text
stroke = 2 * d_acc + d_sync
```

The master distance consumed before retract is:

```text
l_used = l_acc + l_sync + l_dec
```

With symmetric accel/decel:

```text
l_used = 2 * d_acc + d_sync + 2 * d_acc
l_used = 4 * d_acc + d_sync
```

The remaining master distance available for return is:

```text
l_ret = L - l_used
l_ret = L - (l_acc + l_sync + l_dec)
```

The cycle is geometrically impossible if:

```text
l_ret <= 0
```

because there is no material travel left before the next cut to retract the
shear carriage.

## Retract Peak Speed

The result called "Retract peak speed" is the peak speed needed during the
return-to-home MOVELINK command.

The retract command must move the shear carriage back by the full forward
stroke:

```text
retract_slave_distance = -stroke
```

The calculator assigns the remaining link distance to retract:

```text
retract_link_dist = l_ret
```

It uses symmetric accel/decel link distances equal to one quarter of the return
window:

```text
ret_ad = l_ret / 4
```

That leaves one half of the return window at constant retract speed:

```text
constant_return_link = l_ret - ret_ad - ret_ad
constant_return_link = l_ret / 2
```

The retract speed ratio shape is therefore:

```text
0 -> peak over l_ret / 4
peak held over l_ret / 2
peak -> 0 over l_ret / 4
```

The slave distance is the area under this ratio curve:

```text
stroke = area
stroke = 0.5 * r_peak * (l_ret / 4)
       +       r_peak * (l_ret / 2)
       + 0.5 * r_peak * (l_ret / 4)
```

Collecting terms:

```text
stroke = r_peak * (l_ret / 8 + l_ret / 2 + l_ret / 8)
stroke = r_peak * (3 * l_ret / 4)
```

Solving for peak ratio:

```text
r_peak = stroke / (3 * l_ret / 4)
r_peak = (4 / 3) * stroke / l_ret
```

Master speed is `v`, so the peak retract speed magnitude is:

```text
v_ret_peak = r_peak * v
v_ret_peak = (4 / 3) * v * stroke / l_ret
```

This is the formula in the app:

```text
v_retract_peak = (4.0 / 3.0) * v * (stroke / ret_link)
```

If `l_ret <= 0`, the app treats the retract peak as impossible.

## Overall Peak Shear Speed

There are two useful peak-speed numbers:

```text
forward_peak_speed = v
retract_peak_speed = (4 / 3) * v * stroke / l_ret
```

The app displays the second number because retract is usually the hidden
limiting case. The actual maximum speed magnitude over the full cycle is:

```text
cycle_peak_speed = max(v, v_ret_peak)
```

The app separately warns if:

```text
v > vmax
```

because the shear cannot match the material during the cut. It also warns if:

```text
v_ret_peak > vmax
```

because the carriage cannot retract fast enough before the next cut.

## Minimum Cut Length

The forward phases alone require:

```text
L > l_used
```

Substituting the formulas:

```text
L > 4 * d_acc + d_sync
L > 4 * (v^2 / (2 * a) * sf) + v * tsync
L > (2 * v^2 / a) * sf + v * tsync
```

That only guarantees some positive return distance. It does not guarantee the
return speed is within the shear speed limit.

To also keep retract under `vmax`, require:

```text
v_ret_peak <= vmax
(4 / 3) * v * stroke / l_ret <= vmax
```

Solving for required return link distance:

```text
l_ret >= (4 / 3) * v * stroke / vmax
```

So a practical cut-length requirement is:

```text
L >= l_used + (4 / 3) * v * stroke / vmax
```

This is useful when choosing a cut length or deciding whether the requested
line speed is realistic.

## MOVELINK Parameters Generated By The Calculator

The generated program uses four MOVELINK commands.

Acceleration:

```text
MOVELINK(d_acc, l_acc, l_acc, 0, link_ax, ...)
```

Synchronized cut:

```text
MOVELINK(d_sync, l_sync, 0, 0, link_ax, ...)
```

Deceleration:

```text
MOVELINK(d_dec, l_dec, 0, l_dec, link_ax, ...)
```

Retract:

```text
MOVELINK(-stroke, l_ret, l_ret / 4, l_ret / 4, link_ax, ...)
```

Important MOVELINK details:

- `distance` is the slave/shear travel.
- `link_dist` is the positive master/material distance that drives the move.
- `link_acc` and `link_dec` are distances on the master axis, not time values.
- The retract command uses a negative slave distance but a positive link
  distance.
- If `link_acc + link_dec > link_dist`, the controller scales the ramps down.

## Base Distance Option

The Flying Shear calculator also exposes MOVELINK's optional eighth parameter,
`base_dist`.

```text
MOVELINK(distance, link_dist, link_acc, link_dec,
         link_axis, link_options, link_pos, base_dist)
```

`base_dist` is part of the total `distance` argument. It adds motion at the
base ratio so the shaped MOVELINK contribution can start and end at a nonzero
ratio instead of starting from zero. In Trio firmware, parameters 6 and 7 must
be present when parameter 8 is used, even when `link_options` and `link_pos`
are both zero.

The calculator's displayed sizing values are still computed from the main
four-phase model:

```text
d_acc, d_sync, d_dec, stroke, l_ret, v_ret_peak
```

So `base_dist` should be treated as an advanced controller option layered onto
the generated MOVELINK commands. It is not used to recompute the stroke or the
retract peak speed. If a real machine needs a nonzero base ratio during the
flying-shear sequence, validate the resulting path on the controller because
the simple peak-speed estimate no longer describes the entire slave velocity
curve by itself.

## Profile Selection And S-Curves

The distance math above does not change when the profile dropdown changes.
Profile selection changes how MOVELINK shapes acceleration and deceleration.

The app options are:

| Profile | MOVELINK effect |
| --- | --- |
| Trapezoidal | Standard linear speed ramp |
| Sine S-curve | Curved accel/decel, option bit 4 plus mode 0 |
| Power 9 S-curve | Curved accel/decel, option bit 4 plus mode 1 |
| Power 7 S-curve | Curved accel/decel, option bit 4 plus mode 2 |
| Power 5 S-curve | Curved accel/decel, option bit 4 plus mode 3 |
| Linear ramp mode | MOVELINK S-ramp mode 4 |

S-curves reduce jerk at the transitions, but they can require higher peak
acceleration for the same link distance. `MOVELINK.md` lists approximate peak
acceleration multipliers compared with the standard linear ramp:

| S-curve | Approx peak acceleration multiplier |
| --- | --- |
| Sine | 1.55 |
| Power 9 | 2.42 |
| Power 7 | 2.16 |
| Power 5 | 1.86 |

The calculator uses `a` to size distance, then applies `sf`. When using an
S-curve, check the real drive torque and following error limits against the
profile's higher peak acceleration.

## Link Options

The kinematic formulas are independent of start trigger, MPOS/DPOS source, and
direction mode. Those settings only change the generated `link_options` value.

The calculator uses these bits:

| Bit | Value | Meaning |
| --- | --- | --- |
| 0 | 1 | Start on MARK |
| 1 | 2 | Start at absolute link position |
| 2 | 4 | MOVELINK automatic repeat |
| 4 | 16 | Enable MOVELINK curved/S-ramp profile |
| 5 | 32 | Link active only during positive master movement |
| 8 | 256 | Start on MARKB |
| 9 | 512 | Start on R_MARK channel |
| 10..12 | 1024..4096 | S-ramp mode number shifted left by 10 |
| 13 | 8192 | Follow master DPOS instead of MPOS |
| 14 | 16384 | Positive-threshold mode |

For example, Power 7 S-curve has mode number 2:

```text
link_options = bit_4 + (2 << 10)
link_options = 16 + 2048
link_options = 2064
```

## Current Saved-Settings Example

Using the values currently saved in `setup_settings.json`:

```text
L = 36 mm
v = 30 mm/s
a = 300 mm/s2
tsync_ms = 100 ms
sf = 1.5
vmax = 210 mm/s
```

Acceleration distance:

```text
d_acc = 30^2 / (2 * 300) * 1.5
d_acc = 900 / 600 * 1.5
d_acc = 2.25 mm
```

Sync distance:

```text
tsync = 100 / 1000 = 0.1 s
d_sync = 30 * 0.1 = 3.00 mm
```

Forward stroke:

```text
stroke = 2.25 + 3.00 + 2.25
stroke = 7.50 mm
```

Master distances:

```text
l_acc = 2 * 2.25 = 4.50 mm
l_sync = 3.00 mm
l_dec = 2 * 2.25 = 4.50 mm
l_used = 4.50 + 3.00 + 4.50 = 12.00 mm
l_ret = 36.00 - 12.00 = 24.00 mm
```

Retract peak:

```text
v_ret_peak = (4 / 3) * 30 * 7.50 / 24.00
v_ret_peak = 12.50 mm/s
```

Overall speed check:

```text
forward_peak_speed = 30.00 mm/s
retract_peak_speed = 12.50 mm/s
cycle_peak_speed = max(30.00, 12.50) = 30.00 mm/s
```

Both the forward match speed and retract peak speed are below the saved shear
max speed of `210 mm/s`.

## Practical Interpretation

The main tradeoffs are:

- Increasing line speed `v` increases acceleration distance with `v^2`, not
  linearly.
- Increasing sync time increases required stroke and used cut length linearly.
- Increasing safety factor increases accel/decel distance and reduces the
  return window.
- Shorter cut length reduces `l_ret`, which can make retract peak speed rise
  quickly.
- A retract peak below `vmax` does not by itself prove the machine is safe. The
  drive still needs enough acceleration, torque, following-error margin, and
  mechanical clearance.
