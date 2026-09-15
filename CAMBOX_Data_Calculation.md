# How CAMBOX data is calculated

The generator converts absolute CSV positions into **relative displacements in encoder counts**. The generated program first moves each axis to its starting position, then executes those displacements using CAMBOX.

## 1. Source data

| CSV column | Meaning | Unit |
| --- | --- | --- |
| `temps` | Sample time | Seconds |
| `Y` | Absolute linear position | Millimetres |
| `C` | Absolute rotary angle | Radians |

Time samples must be uniformly spaced. Profile time starts at zero by subtracting the first timestamp.

## 2. Mechanical scaling

Gear ratio means **motor revolutions per output revolution**: a 10:1 reduction has a ratio of 10.

```text
Y counts/mm = motor counts/rev × Y gear ratio ÷ screw lead (mm/rev)

C counts/degree = motor counts/rev × C gear ratio ÷ 360
```

For 65,535 effective controller counts per motor revolution:

| Axis | Mechanics | Scale |
| --- | --- | --- |
| Y | 10 mm screw lead, 1:1 gearing | 6,553.5 counts/mm |
| C | 10:1 reduction gearbox | 1,820.416666667 counts/degree |

Use the effective controller count scale, including drive electronic gearing. An encoder range of 0–65,535 contains 65,536 counts; confirm the actual counts per revolution.

## 3. Convert each sample into a TABLE value

With inversion disabled, for sample index `i`:

```text
Y displacement[i] = Y[i] − Y[0]
Y TABLE[i] = round(Y displacement[i] × Y counts/mm)

C displacement[i] = (C[i] − C[0]) × 180 / π
C TABLE[i] = round(C displacement[i] × C counts/degree)
```

The first TABLE value is therefore **zero**, regardless of the absolute starting position. Values are rounded to whole encoder counts.

If inversion is enabled, the corresponding displacement is multiplied by −1 before scaling. The starting position remains unchanged. If C unwrapping is enabled, angles are first adjusted by complete revolutions to remove jumps greater than π between successive samples.

## 4. Recover the commanded position

The generated program prepositions the axes at the first CSV sample. With CAMBOX's TABLE multiplier set to **1**:

```text
Y commanded position[i] = Y[0] + Y TABLE[i] / Y counts/mm

C commanded angle[i] = C[0] × 180 / π + C TABLE[i] / C counts/degree
```

TABLE values already contain encoder counts. **Do not multiply them by slave UNITS again.**

### Worked examples

Using the supplied BASIC's starting positions and second TABLE values:

| Axis | Starting position | TABLE value | Reconstructed position |
| --- | ---: | ---: | ---: |
| Y | 244.418973526 mm | 994 counts | 244.570648204 mm |
| C | 145.890752152° | −507 counts | 145.612244484° |

```text
Y = 244.418973526 + 994 / 6553.5
  ≈ 244.570648204 mm

C = 145.890752152 − 507 / 1820.416666667
  ≈ 145.612244484°
```

These reconstructed positions—not the raw TABLE numbers—correspond to the source positions, apart from rounding and any enabled inversion or unwrapping.

## 5. Convert CSV time into master distance

CAMBOX follows master position rather than CSV timestamps directly. The generator maps time to distance using the selected virtual master speed:

```text
Relative time[i] = time[i] − time[0]
Relative master distance[i] = relative time[i] × master speed
Link distance = profile duration × master speed
```

For **1,007 samples**, spaced **0.004 s** apart, at **80 mm/s**:

```text
Duration = (1007 − 1) × 0.004 = 4.024 s
Master distance per sample interval = 80 × 0.004 = 0.32 mm
CAMBOX link distance = 80 × 4.024 = 321.92 mm
```

The supplied program starts CAMBOX at master position **4.2 mm**:

```text
Absolute master position[i] = 4.2 + relative master distance[i]
```

For example, sample index 250 occurs at profile time **1 s** and master position **84.2 mm**. The final sample occurs at master position **326.12 mm**.

The exported `master_mm` column contains relative distance; add the configured profile start to compare it with absolute master DPOS. Prepositioning and master run-up occur before CSV profile time zero.

## 6. The CAMBOX commands used

CAMBOX defines slave position as a function of master travel. Its general syntax is:

```text
CAMBOX(start_point, end_point, table_multiplier, link_distance,
       link_axis [, link_options] [, link_pos] [, offset_start]) AXIS(slave)
```

The supplied program uses two separate commands with the same master, start position, and link distance:

```basic
profile_link_dist = 321.92
profile_start = 4.2
master_ax = 10
link_options = 8194

CAMBOX(1000, 2006, 1, profile_link_dist, master_ax, link_options, profile_start) AXIS(0)
WAIT LOADED AXIS(0)
CAMBOX(3000, 4006, 1, profile_link_dist, master_ax, link_options, profile_start) AXIS(1)
WAIT LOADED AXIS(1)
```

### Argument meanings

| Argument | Value used | Meaning |
| --- | --- | --- |
| `start_point` | Y: 1000; C: 3000 | First TABLE address, not the axis's starting position |
| `end_point` | Y: 2006; C: 4006 | Last TABLE address, inclusive: each block contains 1,007 points |
| `table_multiplier` | 1 | TABLE displacements are already in encoder counts; no further scaling is needed |
| `link_distance` | 321.92 | Positive master travel required to traverse the complete profile, in master user units—virtual mm here |
| `link_axis` | 10 | Master axis whose position advances the profile |
| `link_options` | 8194 | Start at an absolute master position and follow master DPOS |
| `link_pos` | 4.2 | Absolute master position where this profile begins, in master user units |
| `offset_start` | Omitted | No forced entry partway through the profile |
| `AXIS(slave)` | Y: 0; C: 1 | Axis executing the corresponding TABLE movement |

### Why options equal 8194

`link_options` is a bit mask, not a speed or scale:

```text
8194 = 8192 + 2 = 2^13 + 2^1
```

- **Bit 1, value 2:** start at the absolute master position specified by `link_pos`.
- **Bit 13, value 8192:** follow the master's demanded position, **DPOS**, rather than its measured position, MPOS.
- **Bit 2, value 4, is not set:** automatic repetition is disabled. This is a one-shot profile.

The master is configured separately as a virtual axis. Both slave commands are loaded before the master starts, so they wait for the same future master DPOS of 4.2 mm. This synchronizes their start even though they are issued as separate commands. The generator does not use CAMBOX's alternative multi-axis loading syntax.

### How the TABLE is traversed

CAMBOX treats TABLE values as positions, not speeds. It subtracts the first TABLE value, applies the multiplier, and uses the result as displacement from the slave position at profile start:

```text
Slave displacement in counts = (TABLE value − first TABLE value) × multiplier
```

Here, each first TABLE value is zero and each multiplier is 1. The controller interpolates between successive TABLE points over equal increments of master distance. For this example:

```text
Master increment per TABLE interval = 321.92 / (2006 − 1000)
                                   = 0.32 mm
```

The TABLE slope and master velocity determine slave velocity. A constant TABLE value produces a dwell; increasing or decreasing values produce positive or negative displacement. These profiles describe displacement, not necessarily a return to the starting position.

### Execution and completion

1. `MOVEABS` prepositions Y and C at their first CSV positions; `WAIT IDLE` waits for arrival.
2. The two CAMBOX commands are armed; `WAIT LOADED` waits for loading, not completion of the profile.
3. `FORWARD AXIS(10)` starts the master. Its run-up allows it to reach the requested speed before the 4.2 mm start.
4. As master DPOS advances from **4.2 to 326.12 mm**, both TABLE profiles execute.
5. The program waits for both slaves to become idle, cancels master motion, and waits for the master to stop.

The Y and C `SPEED` settings govern their initial MOVEABS moves; they are not the speed commands for the linked CAMBOX trajectory. If actual master speed changes during the profile, slave timing changes with it. The stated 4.024-second duration assumes the master maintains 80 mm/s throughout the link distance.

## 7. Units and comparison

- **Y DPOS:** millimetres with the generated Y UNITS setting.
- **C DPOS:** configured C user units. Multiply by degrees per user unit to obtain degrees. For example, DPOS 900 with 0.1° units means 90°.
- Changing C user units changes UNITS and the numeric MOVEABS target, but does not change TABLE counts for the same physical rotation.
- Compare source positions with the exported `y_commanded_mm` and `c_commanded_deg` columns. These reconstruct position from the actual rounded TABLE values.
- Compare scope DPOS at matching master positions. MPOS represents measured position and may differ due to following error. Between TABLE samples, CAMBOX interpolates.

The examples above were reconstructed from generated BASIC; they are expected command values, not measured machine results.
