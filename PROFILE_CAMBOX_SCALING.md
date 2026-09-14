# Profile CAMBOX scaling

The generator takes time in seconds, Y in millimetres, and C in radians.
The output TABLE values are relative encoder counts; CAMBOX uses multiplier 1.
The drive and any external controller-connected model must agree with the
effective counts used by the generator.

## Reza's 10:1 blade gearbox and 10 mm screw

If the controller sees exactly 65,535 counts per motor revolution, enter:

| Field | Value |
| --- | --- |
| Y counts/rev | 65535 |
| Y screw lead | 10 mm/rev |
| Y gear motor:output | 1:1 (direct motor-to-screw connection) |
| C counts/rev | 65535 |
| C gear motor:output | 10:1 |
| C user unit | 1 degree, or 0.1 degree if desired |
| C wrap ± | 360 degrees, or a larger boundary containing the whole profile |

This gives 6,553.5 counts/mm on Y and 1,820.416666667 counts/degree on C.
A relative 10 mm Y move uses 65,535 counts. A relative 180 degree blade
move uses 327,675 counts. With 0.1 degree C user units, C UNITS becomes
182.041666667, but the TABLE counts and physical rotation remain the same.

Confirm that 65,535 is a revolution count, not the maximum value of an encoder
whose range is 0–65,535 (65,536 counts). Include drive electronic gearing in
the effective controller counts per motor revolution.

Gear ratios use two numeric fields with a fixed colon between them, e.g. `10 : 1`.
The left field is motor turns; the right field is output turns. `1:1` is direct drive;
`3:2` means 1.5 motor turns per output turn; `1:2` is a speed increase.
Enter the physical screw lead before gearing. For example, a 10 mm/rev screw
with Y gearing of `2:1` travels 5 mm per motor turn. The generator calculates
Y counts/mm as counts/rev × gear ratio ÷ screw lead, and C counts/degree as
counts/rev × gear ratio ÷ 360. Diagnostics show the resulting motor-turn travel.
Saved ratios are normalized to an equivalent motor-turn value with output turns
set to 1 when reopened (for example, `20 : 2` reopens as `10 : 1`).

Older saved C output/rev settings migrate to an equivalent gear ratio
(36 degrees becomes `10:1`). Older Y travel/rev settings retain a `1:1` ratio
so the existing scale is preserved. If that old travel already incorporated
gearing, replace it with the actual screw lead when entering an explicit ratio
to avoid applying the reduction twice.

The virtual master uses an independent software scale. It does not need to
match either motor. Link distance equals CSV duration multiplied by master
speed, so regenerating after a master speed change preserves CSV timing.
Slave preposition speed controls only the initial MOVEABS, not the CAM profile.

For a short visible preposition in Motion Perfect simulation, enable
**Demo start: 5 mm before target** in the Y panel and/or
**Demo start: 5° before target** in the C panel. Generated BASIC uses DEFPOS
to redefine each selected axis at its first CSV position minus that offset,
waits for OFFPOS to settle, then issues the normal MOVEABS to the first sample.
C's offset is five output degrees and is converted to the configured user units.
These options default off: DEFPOS replaces the coordinate datum without moving
the axis. The options affect generated BASIC, not the app's profile-only preview.

## Position wrap and preview

C gear motor:output describes the gearbox. C wrap ± describes the symmetric position
boundary in output degrees and is independent of the gearbox. Generated BASIC
sets REP_OPTION=0 and writes REP_DIST in exact counts with UNITS=1 before
restoring C engineering units. Generation rejects commanded samples reaching
the boundary; increase the boundary to contain an unwrapped multi-turn profile.

Charts, simulation, diagnostics and commanded CSV columns reconstruct sample
positions from rounded TABLE counts and the configured scale. Inversion reverses
displacement about the first source position, which remains the preposition
target. Source-position CSV columns remain available for comparison.
The preview covers the profile samples, not drive feedback, controller
interpolation between samples, or the initial preposition and master run-up.
It cannot detect a drive or external model configured with a different scale.

Edits mark displayed results as needing regeneration. Generate, Copy BASIC,
Export, and opening Simulation regenerate from current inputs. Export also
rechecks inputs after the directory picker closes. Invalid settings block output.

The points CSV now calls its configurable C displacement column
`c_relative_user_units` (previously `c_relative_0.1deg`) and appends
`y_commanded_mm` and `c_commanded_deg`.

## Verification

Run the profile regression suite:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_profile_cambox_domain tests.test_profile_cambox_codegen tests.test_profile_cambox_simulation tests.test_profile_cambox_scaling tests.test_profile_cambox_ui
```

Coverage includes the customer mechanics, alternate encoder resolutions,
master timing, C user units, wrap boundaries, quantized inverted preview,
navigation, and copy/export freshness through the UI callbacks.
