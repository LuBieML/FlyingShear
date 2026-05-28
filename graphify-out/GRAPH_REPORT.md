# Graph Report - E:\SynologySynchro\Projects\FlyingShear  (2026-05-28)

## Corpus Check
- 59 files · ~87,782 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 603 nodes · 994 edges · 46 communities (33 shown, 13 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 16 edges (avg confidence: 0.72)
- Token cost: 15,600 input · 2,800 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Trio Controller Axis Control Commands|Trio Controller Axis Control Commands]]
- [[_COMMUNITY_Rotary Cam Sizing Parameters|Rotary Cam Sizing Parameters]]
- [[_COMMUNITY_Trio BASIC Profile Code Generation|Trio BASIC Profile Code Generation]]
- [[_COMMUNITY_Axis Startup Sizing & Formatting|Axis Startup Sizing & Formatting]]
- [[_COMMUNITY_Flet Jog Panel UI Component|Flet Jog Panel UI Component]]
- [[_COMMUNITY_Trio Controller Connection Actions|Trio Controller Connection Actions]]
- [[_COMMUNITY_ROTARYLINK Calculation Settings|ROTARYLINK Calculation Settings]]
- [[_COMMUNITY_FLEXLINK Sizing Parameters|FLEXLINK Sizing Parameters]]
- [[_COMMUNITY_OWASP Dependency Vulnerability Checker|OWASP Dependency Vulnerability Checker]]
- [[_COMMUNITY_Windows Asyncio & Timer Bootstrap|Windows Asyncio & Timer Bootstrap]]
- [[_COMMUNITY_Rotary Drum Kinematics & Conversion|Rotary Drum Kinematics & Conversion]]
- [[_COMMUNITY_Rotary-Knife Profile Sizing Calculations|Rotary-Knife Profile Sizing Calculations]]
- [[_COMMUNITY_CAMBOX Sizing & Table Profile Generation|CAMBOX Sizing & Table Profile Generation]]
- [[_COMMUNITY_OWASP Mobile Network Security Audit|OWASP Mobile Network Security Audit]]
- [[_COMMUNITY_Point-to-Point Motion Configuration|Point-to-Point Motion Configuration]]
- [[_COMMUNITY_Linear Flying Shear Sizing Parameters|Linear Flying Shear Sizing Parameters]]
- [[_COMMUNITY_OWASP Android Mobile Storage Audit|OWASP Android Mobile Storage Audit]]
- [[_COMMUNITY_Windows Asyncio Proactor Compatibility|Windows Asyncio Proactor Compatibility]]
- [[_COMMUNITY_Sizing Math Specifications & App Entry|Sizing Math Specifications & App Entry]]
- [[_COMMUNITY_Axis Controller Drive Parameter Limits 0|Axis Controller Drive Parameter Limits 0]]
- [[_COMMUNITY_Axis Controller Drive Parameter Limits 1|Axis Controller Drive Parameter Limits 1]]
- [[_COMMUNITY_Axis Controller Drive Parameter Limits 2|Axis Controller Drive Parameter Limits 2]]
- [[_COMMUNITY_Axis Controller Drive Parameter Limits 3|Axis Controller Drive Parameter Limits 3]]
- [[_COMMUNITY_Axis Controller Drive Parameter Limits 4|Axis Controller Drive Parameter Limits 4]]
- [[_COMMUNITY_FLEXLINK Profile Acceleration Progress Curves|FLEXLINK Profile Acceleration Progress Curves]]
- [[_COMMUNITY_Persistent Application Settings Sizing|Persistent Application Settings Sizing]]
- [[_COMMUNITY_Target Axis Control Configuration|Target Axis Control Configuration]]
- [[_COMMUNITY_Trio Unified API Communication Manager|Trio Unified API Communication Manager]]
- [[_COMMUNITY_Matplotlib Flet Chart Life Cycle Patch|Matplotlib Flet Chart Life Cycle Patch]]
- [[_COMMUNITY_Local Ide Claude Settings|Local Ide Claude Settings]]
- [[_COMMUNITY_Linear Flying Shear Solution Axis Config|Linear Flying Shear Solution Axis Config]]
- [[_COMMUNITY_Rotary Knife Solution Axis Config|Rotary Knife Solution Axis Config]]
- [[_COMMUNITY_ROTARYLINK Solution Axis Config|ROTARYLINK Solution Axis Config]]
- [[_COMMUNITY_Flying Shear Sizing App Launcher|Flying Shear Sizing App Launcher]]
- [[_COMMUNITY_Trio BASIC Code Generation Root|Trio BASIC Code Generation Root]]
- [[_COMMUNITY_App Configuration Initialization|App Configuration Initialization]]
- [[_COMMUNITY_Runtime Bootstrap Initialization|Runtime Bootstrap Initialization]]
- [[_COMMUNITY_Controller Integration Root|Controller Integration Root]]
- [[_COMMUNITY_Pure Motion-Domain Calculations Root|Pure Motion-Domain Calculations Root]]
- [[_COMMUNITY_Flying Shear Flet Application Package|Flying Shear Flet Application Package]]
- [[_COMMUNITY_Source Package Root|Source Package Root]]
- [[_COMMUNITY_Flet Reusable UI Solution Components|Flet Reusable UI Solution Components]]
- [[_COMMUNITY_Presenter Notes Documentation|Presenter Notes Documentation]]
- [[_COMMUNITY_Flutter Testing Skill Reference|Flutter Testing Skill Reference]]
- [[_COMMUNITY_OWASP Mobile Security Skill Reference|OWASP Mobile Security Skill Reference]]

## God Nodes (most connected - your core abstractions)
1. `main()` - 43 edges
2. `TrioConnection` - 29 edges
3. `TrioConnection` - 28 edges
4. `SlaveJogPanel` - 27 edges
5. `RotaryLinkTests` - 24 edges
6. `rotarylink_calc` - 22 edges
7. `flexlink_calc` - 21 edges
8. `1` - 16 edges
9. `0` - 16 edges
10. `2` - 15 edges

## Surprising Connections (you probably didn't know these)
- `FLEXLINK Flow-Wrapper Math` --implements--> `FLEXLINK Axis Command Specification`  [INFERRED]
  src/flying_shear_app/domain/flexlink_math.py → FLEXLINK.md
- `Flet UAPI Sizing App UI Setup` --implements--> `Flying Shear Synchronization`  [INFERRED]
  flet_uapi_setup.py → Calc.md
- `CAMBOX Math Engine` --implements--> `CAMBOX Electronic Cam Profile`  [INFERRED]
  src/flying_shear_app/domain/cambox_math.py → CAMBOX.md
- `Trio Connection Axis Controller` --implements--> `Trio Unified API Communication Protocol`  [INFERRED]
  src/flying_shear_app/controller/trio_connection.py → Trio_UnifiedApi_CPP.pdf
- `Legacy Trio Connection Manager` --implements--> `Trio Unified API Communication Protocol`  [INFERRED]
  trio_connection.py → Trio_UnifiedApi_CPP.pdf

## Hyperedges (group relationships)
- **Linked Axis Control Commands** — movelink_spec, cambox_spec, flexlink_spec [INFERRED 0.85]

## Communities (46 total, 13 thin omitted)

### Community 0 - "Trio Controller Axis Control Commands"
Cohesion: 0.07
Nodes (15): Exception, Read WDOG and SERVO state for the supplied axes., Set WDOG and SERVO for the supplied axes as one UI action., Enable the controller watchdog and SERVO for the supplied axes., Read the state of one controller digital output., TrioConnection, _EventType, FakeUapiConnection (+7 more)

### Community 1 - "Rotary Cam Sizing Parameters"
Cohesion: 0.04
Nodes (48): cam_calc, blend, cpr, cut, cut_window, drum_circumference, drum_dia, n_knives (+40 more)

### Community 2 - "Trio BASIC Profile Code Generation"
Cohesion: 0.09
Nodes (19): describe_rotarylink_options(), emit_rotarylink_basic_program(), Trio BASIC generation for ROTARYLINK profiles., build_flexlink_options(), build_movelink_options(), build_rotarylink_options(), _format_motion_arg(), format_rotarylink() (+11 more)

### Community 3 - "Axis Startup Sizing & Formatting"
Cohesion: 0.10
Nodes (23): axis_param_lines(), _axis_params_for(), _coerce_axis_param_number(), emit_axis_startup_basic_program(), format_axis_param_value(), _format_number(), Shared Trio BASIC startup axis configuration generation., Emit Trio BASIC startup code for a solution's configured axes. (+15 more)

### Community 4 - "Flet Jog Panel UI Component"
Cohesion: 0.14
Nodes (14): object, bool, float, str, SlaveJogPanelTests, _theme(), JogEdgeEvent, JogPanelTheme (+6 more)

### Community 5 - "Trio Controller Connection Actions"
Cohesion: 0.11
Nodes (10): Read WDOG and SERVO state for the supplied axes., Set WDOG and SERVO for the supplied axes as one UI action., Enable the controller watchdog and SERVO for the supplied axes., Read the state of one controller digital output., TrioConnection, bool, FileType, float (+2 more)

### Community 6 - "ROTARYLINK Calculation Settings"
Cohesion: 0.09
Nodes (22): rotarylink_calc, acc, buffered_commands, cut_length, decel, distance, link_dist, link_source (+14 more)

### Community 7 - "FLEXLINK Sizing Parameters"
Cohesion: 0.10
Nodes (21): flexlink_calc, base_in, base_in_mm, base_out, base_out_mm, curve_type, cycle_pitch, direction_mode (+13 more)

### Community 8 - "OWASP Dependency Vulnerability Checker"
Cohesion: 0.15
Nodes (19): bool, int, str, analyze_outdated_results(), check_dangerous_packages(), check_outdated_packages(), check_version_constraints(), load_pubspec() (+11 more)

### Community 9 - "Windows Asyncio & Timer Bootstrap"
Cohesion: 0.20
Nodes (15): begin_windows_timer_resolution(), end_windows_timer_resolution(), Windows timer-resolution helpers used by animation loops., emit_square_startup_basic_program(), Emit square example axis setup code intended to run at startup., Save settings to the project JSON file., save_settings(), format_movelink() (+7 more)

### Community 10 - "Rotary Drum Kinematics & Conversion"
Cohesion: 0.20
Nodes (15): compute_rotary_drum_angle_rad(), compute_rotary_drum_kinematics(), compute_rotary_drum_tangential_mm_s(), compute_rotary_mpos_counts_per_physical_rev(), Pure rotary-knife unit conversion and kinematics helpers., Return shared rotary drum unit conversions for live diagnostics and drawing., Convert drive encoder CPR and Trio UNITS into MPOS units per drum turn., rotary_blade_direction_for_angle() (+7 more)

### Community 11 - "Rotary-Knife Profile Sizing Calculations"
Cohesion: 0.18
Nodes (13): CAMBOX rotary-knife profile calculations., compute_rotary_drum_circumference_mm(), compute_rotary_units_per_mm(), Return drum circumference in millimetres from diameter., Return Trio UNITS when one user unit is one millimetre of drum surface., calculate_rotarylink_base_sync_speed(), derive_rotarylink_geometry(), estimate_rotarylink_slave_accel() (+5 more)

### Community 12 - "CAMBOX Sizing & Table Profile Generation"
Cohesion: 0.20
Nodes (10): emit_cam_basic_program(), emit_cam_quicktest_basic_program(), _format_axis_units(), Trio BASIC generation for rotary-knife CAMBOX profiles., generate_rotary_knife_cam_table(), advance_rotary_drum_angle_rad(), compute_rotary_cutting_radius_px(), Return the visual cutting radius in pixels for the current conveyor scale. (+2 more)

### Community 13 - "OWASP Mobile Network Security Audit"
Cohesion: 0.21
Nodes (16): Path, str, check_android_network_security(), check_bad_cert_callback(), check_http_client_pinning(), check_ios_ats_configuration(), main(), Check Android network security configuration. (+8 more)

### Community 14 - "Point-to-Point Motion Configuration"
Cohesion: 0.13
Nodes (15): point_to_point, accel, axis, decel, example, move_mode, origin_x, origin_y (+7 more)

### Community 15 - "Linear Flying Shear Sizing Parameters"
Cohesion: 0.13
Nodes (15): shear_calc, amax, base_dist, cut, direction_mode, link_pos, link_source, profile (+7 more)

### Community 16 - "OWASP Android Mobile Storage Audit"
Cohesion: 0.23
Nodes (14): Path, str, main(), Check Android backup configuration., Scan entire Flutter project for storage security issues., Scan for insecure SharedPreferences usage., Main execution function., Scan for insecure file storage patterns. (+6 more)

### Community 17 - "Windows Asyncio Proactor Compatibility"
Cohesion: 0.20
Nodes (10): Any, _callback_name(), install_asyncio_windows_pipe_reset_filter(), is_windows_proactor_pipe_reset(), Windows asyncio compatibility helpers., Return true for benign proactor pipe resets during Windows shutdown., Suppress one noisy Windows proactor shutdown callback in the active loop., bool (+2 more)

### Community 18 - "Sizing Math Specifications & App Entry"
Cohesion: 0.18
Nodes (13): Flying Shear Math Specification, CAMBOX Axis Command Specification, CAMBOX Math Engine, Flet UAPI Sizing App UI Setup, FLEXLINK Flow-Wrapper Math, Rotary Link Math Calculation, CAMBOX Electronic Cam Profile, Flying Shear Synchronization (+5 more)

### Community 19 - "Axis Controller Drive Parameter Limits 0"
Cohesion: 0.17
Nodes (12): ACCEL, DECEL, DRIVE_FE_LIMIT, FASTDEC, FE_LIMIT, FE_RANGE, FS_LIMIT, JERK (+4 more)

### Community 20 - "Axis Controller Drive Parameter Limits 1"
Cohesion: 0.17
Nodes (12): ACCEL, DECEL, DRIVE_FE_LIMIT, FASTDEC, FE_LIMIT, FE_RANGE, FS_LIMIT, JERK (+4 more)

### Community 21 - "Axis Controller Drive Parameter Limits 2"
Cohesion: 0.17
Nodes (12): ACCEL, DECEL, DRIVE_FE_LIMIT, FASTDEC, FE_LIMIT, FE_RANGE, FS_LIMIT, JERK (+4 more)

### Community 22 - "Axis Controller Drive Parameter Limits 3"
Cohesion: 0.17
Nodes (12): ACCEL, DECEL, DRIVE_FE_LIMIT, FASTDEC, FE_LIMIT, FE_RANGE, FS_LIMIT, JERK (+4 more)

### Community 23 - "Axis Controller Drive Parameter Limits 4"
Cohesion: 0.17
Nodes (12): ACCEL, DECEL, DRIVE_FE_LIMIT, FASTDEC, FE_LIMIT, FE_RANGE, FS_LIMIT, JERK (+4 more)

### Community 24 - "FLEXLINK Profile Acceleration Progress Curves"
Cohesion: 0.29
Nodes (7): flexlink_curve_progress(), flexlink_curve_progress_integral(), flexlink_excitation_progress(), Pure FLEXLINK curve and excitation progress helpers., Integral of `flexlink_curve_progress` from 0 to t.      Used to compute the *pos, Return (progress, in_excite) for normalized phase u in [0, 1].      Models a tra, Velocity-shape function for one accel (or, mirrored, decel) ramp.      Returns a

### Community 25 - "Persistent Application Settings Sizing"
Cohesion: 0.38
Nodes (6): _bundled_settings_file(), load_settings(), _project_root(), Persistent JSON settings for the Flying Shear setup app., Load settings from the project JSON file., Path

### Community 26 - "Target Axis Control Configuration"
Cohesion: 0.29
Nodes (7): axis_params, target_axis, axis_params, target_axis, solution_axis_params, flow_wrapper, point_to_point

### Community 27 - "Trio Unified API Communication Manager"
Cohesion: 0.67
Nodes (4): Trio Connection Axis Controller, Legacy Trio Connection Manager, Trio Unified API Communication Protocol, Trio Unified API C++ Reference (PDF)

### Community 28 - "Matplotlib Flet Chart Life Cycle Patch"
Cohesion: 0.50
Nodes (3): patch_flet_charts_matplotlib_lifecycle(), Compatibility patches for flet_charts inside rebuilt Flet tabs., Make flet_charts' Matplotlib control safe across tab/page rebuilds.

### Community 30 - "Linear Flying Shear Solution Axis Config"
Cohesion: 0.67
Nodes (3): axis_params, target_axis, flying_shear

### Community 31 - "Rotary Knife Solution Axis Config"
Cohesion: 0.67
Nodes (3): axis_params, target_axis, rotary_knife

### Community 32 - "ROTARYLINK Solution Axis Config"
Cohesion: 0.67
Nodes (3): axis_params, target_axis, rotarylink

## Knowledge Gaps
- **187 isolated node(s):** `controller_ip`, `param_UNITS`, `target_axis`, `param_SPEED`, `param_ACCEL` (+182 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TrioConnection` connect `Trio Controller Connection Actions` to `Trio Controller Axis Control Commands`, `Windows Asyncio & Timer Bootstrap`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `main()` connect `Windows Asyncio & Timer Bootstrap` to `Flying Shear Sizing App Launcher`, `Trio BASIC Profile Code Generation`, `Axis Startup Sizing & Formatting`, `Flet Jog Panel UI Component`, `Trio Controller Connection Actions`, `Rotary Drum Kinematics & Conversion`, `Rotary-Knife Profile Sizing Calculations`, `CAMBOX Sizing & Table Profile Generation`, `Windows Asyncio Proactor Compatibility`, `FLEXLINK Profile Acceleration Progress Curves`, `Persistent Application Settings Sizing`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `TrioConnection` (e.g. with `_EventType` and `FakeUapiConnection`) actually correct?**
  _`TrioConnection` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Compatibility launcher for the split Flying Shear application package.`, `Primary entrypoint for the split Flying Shear Flet application.`, `Focused regression check for rotary knife motion math.` to the rest of the system?**
  _273 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Trio Controller Axis Control Commands` be split into smaller, more focused modules?**
  _Cohesion score 0.06711915535444947 - nodes in this community are weakly interconnected._
- **Should `Rotary Cam Sizing Parameters` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._
- **Should `Trio BASIC Profile Code Generation` be split into smaller, more focused modules?**
  _Cohesion score 0.08748615725359911 - nodes in this community are weakly interconnected._