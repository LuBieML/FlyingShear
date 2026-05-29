# Plan-Prompt: Splitting `app.py` into LLM-Friendly Modules

> **This is an executable prompt for a coding agent.** Read it top to bottom,
> then perform the migration **one step at a time**, committing after each
> verified step. Do **not** attempt the whole split in a single pass.

---

## 0. Mission

`src/flying_shear_app/app.py` is a **12,333-line file** consisting of a single
`main(page)` function that nests **~291 inner functions**. Everything shares
state through closures over `main`'s locals. This is unreadable for humans and
forces an LLM to load the entire file to change anything.

**Goal:** decompose `app.py` into small, self-contained **feature modules**
(target **≤ 800 lines each**, ideally 300–600) under a new
`src/flying_shear_app/features/` package, wired together by a thin shell.

**Hard rule — behavior must not change.** This is a *pure structural refactor*.
No feature, label, calculation, code-generation output, layout, or timing may
change. If you are tempted to "improve" something, **stop and leave it also**.

---

## 1. Non-negotiable constraints

1. **Behavior-preserving only.** Same UI, same generated TRIO BASIC text, same
   math, same defaults, same log strings. If output differs, the step is wrong.
2. **Incremental & reversible.** Migrate one feature per commit. The app must
   import and launch after every commit.
3. **Symbol navigation uses LSP**, per `CLAUDE.md` / `.claude/rules/prefer_lsp.md`.
   Use `goToDefinition` / `findReferences` to trace where a nested function or
   variable is used before moving it. Only fall back to `grep`/`rg` for literal
   text (log messages, comments, JSON keys) — and document the fallback reason.
4. **No new dependencies.** Use only what `requirements.txt` already provides.
5. **Windows-first runtime.** The app runs via `venv\Scripts\python.exe main.py`.
   Keep the `bootstrap/` Windows-timer/asyncio patches wired exactly as they are.
6. **Keep the entrypoint stable.** `main.py` imports `from
   src.flying_shear_app.app import main`. That import must keep working
   unchanged — `app.py` becomes a thin shell that still exposes `main(page)`.

---

## 2. Why this file is hard (read before touching anything)

The blocker is **closure-shared state**, not line count. Inner functions read
and mutate `main`'s locals directly:

- Shared services used *everywhere*: `page`, `trio_conn` (a `TrioConnection`),
  `settings` (from `load_settings()`), `uapi_executor`, `show_snack(...)`,
  `section_header(...)`, `control_cluster(...)`, `ui_loop_holder`,
  `current_solution`, `active_solution_key()`, `get_solution_involved_axes()`.
- Mutable state is deliberately held in **dict/list holders** (e.g.
  `current_solution = {"value": None}`, `position_zero_m = [None]`,
  `wdog_state = {...}`) precisely so closures can mutate without `nonlocal`.
  Only a few real `nonlocal`s exist: `monitor_running`, `flexlink_sim_running`,
  `rotary_sim_settings`, `rotary_sim_state`, `valid`.
- **Cross-feature coupling points** (these decide the architecture):
  - `on_page_resize` calls `resize_shear_visual`, `resize_rotary_sim_visual`,
    `resize_rotary_profile_view_visual`, `resize_flexlink_sim_visual`.
  - `on_window_event` (close) flips `monitor_running` / `flexlink_sim_running`
    and disconnects on the pinned UAPI executor thread.
  - `monitor_async_loop` / `_batch_read` feed telemetry into the rotary and
    flexlink sims via `update_rotary_sim_from_reads`,
    `update_flexlink_sim_from_reads`, `update_*_diagnostics`, etc.
  - `on_connect_click` triggers `apply_saved_params_after_connection`.

**Chosen pattern:** introduce a shared **`AppContext`** plus a lightweight
**callback registry**, then turn each feature into a class that *receives* the
context and *registers* its lifecycle hooks. This severs the closures cleanly
without changing behavior.

---

## 3. Target architecture

```
src/flying_shear_app/
  app.py                      # SHRINKS to a thin shell (~150-250 lines):
                              #   builds AppContext, instantiates features,
                              #   wires the registry, defines main(page).
  context.py                  # NEW: AppContext dataclass + CallbackRegistry.
  ui/
    jog_panel.py              # (exists)
    shell.py                  # NEW: solution picker, workspace appbar,
                              #   solution_card, training cards, tab assembly,
                              #   show_solution_workspace / show_solution_picker.
    common.py                 # NEW: show_snack, section_header, control_cluster,
                              #   _update_if_mounted, shared LABEL/VALUE styles,
                              #   canvas_paint, color constants.
  features/
    __init__.py               # NEW
    connection.py             # IP field, on_connect_click, status_callback,
                              #   handle_connection_lost, watchdog, master cmds,
                              #   master-speed + cutter-output controls.
    monitor.py                # monitor_async_loop, _batch_read, start_monitor,
                              #   monitor_values_*, comms-lag / fps tracking.
    shear_visual.py           # conveyor + shear track canvas, scaling, recenter,
                              #   resize_shear_visual.
    axis_params.py            # param inputs/handlers, apply/copy, saved sets,
                              #   apply_saved_params_after_connection, dialogs.
    shear_basic.py            # shear-basic calculator: inputs, velocity-profile
                              #   shapes, recalc, copy_code, tab content.
    shear_help.py             # help cards, formula blocks, phase/s-curve shapes.
    cambox.py                 # Rotary Knife Cam Table generator + profile view.
    rotary_sim.py             # Rotary live simulation (drum visual, diagnostics,
                              #   kinematics, slave jog, cutter-lamp clone).
    flexlink_calc.py          # FLEXLINK (VFFS cross-seal) calculator + codegen.
    flexlink_sim.py           # FLEXLINK live sim (film tube, jaws, sim loop).
    rotarylink_calc.py        # ROTARYLINK calculator + codegen.
    point_to_point.py         # Point-to-point calculator + square visual.
```

> Split `flexlink` into `_calc` and `_sim` because the source already separates
> them (calculator near line 7273; live-sim block near 9365) and each is large.

---

## 4. Source-line map (current `app.py`)

Use this as the cut guide. **Verify every boundary with LSP `findReferences`
before moving a block** — line numbers drift as you edit, so re-check, don't
trust these blindly after the first commit.

| Feature / module            | Approx. source lines | Anchor symbols |
|-----------------------------|----------------------|----------------|
| Shell setup + state         | 73–118, 11915–12333  | `SOLUTION_LABELS`, `current_solution`, `build_solution_tabs`, `show_solution_picker`, `on_window_event`, `on_page_resize`, `page.add` |
| `ui/common.py`              | 199–294, 2816–2824   | `_update_if_mounted`, `show_snack`, `section_header`, `control_cluster`, `canvas_paint` |
| `connection.py`             | 288–344, 365–689, 774–868, 920–1051, 1932–2121 | `status_callback`, `handle_connection_lost`, watchdog `on_wdog_click`, `_send_master_cmd`, `on_connect_click`, master-speed / cutter-output |
| `monitor.py`                | 992–994, 1548–1931   | `monitor_async_loop`, `_batch_read`, `start_monitor` |
| `shear_visual.py`           | 1049–1530            | `create_conveyor_track`, `create_shear_track`, `resize_shear_visual`, `on_recenter`, `_apply_scale` |
| `axis_params.py`            | 2087–2598            | `param_inputs`, `create_param_change_handler`, `on_apply_click`, `apply_saved_params_after_connection`, `show_saved_params_dialog` |
| `shear_basic.py`            | 2599–3422            | `build_param_group`, `recalc`, `build_velocity_profile_shapes`, `copy_code`, `shear_basic_tab_content` |
| `shear_help.py`             | 3423–3836            | `help_card`, `formula_block`, `build_help_phase_shapes`, `build_help_scurve_shapes` |
| `cambox.py`                 | 3837–5342            | banner *"Rotary Knife Cam Table Generator"*; `cam_recalc`, profile-view `redraw_profile_figure`, `send_cam_quicktest_table` |
| `rotary_sim.py`             | 5343–7272            | banner *"Rotary Live Simulation Instances"*; `draw_rotary_drum`, `update_rotary_diagnostics`, slave-jog handlers, `make_cutter_lamp_panel_clone` |
| `flexlink_calc.py`          | 7273–8272            | banner *"Continuous VFFS Cross-Seal FLEXLINK Calculator"*; `flexlink_recalc`, `flexlink_copy_code`, `flexlink_basic_tab_content` |
| `rotarylink_calc.py`        | 8273–9364            | banner *"ROTARYLINK Calculator"*; `rotarylink_recalc`, `rotarylink_copy_code`, `rotarylink_basic_tab_content` |
| `flexlink_sim.py`           | 9365–11164           | `flexlink_profile_snapshot`, `redraw_flexlink_sim`, `flexlink_sim_loop`, `flexlink_build_help_anatomy_shapes` |
| `point_to_point.py`         | 11165–11914          | `point_to_point_update_code`, `point_to_point_update_square_visual`, `point_to_point_basic_tab_content` |

---

## 5. The `AppContext` + registry contract (build this FIRST, Step 1)

Create `src/flying_shear_app/context.py`. It carries the shared singletons and
the cross-feature hook registry. Keep it dumb — no business logic.

```python
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class CallbackRegistry:
    """Cross-feature lifecycle hooks, registered by features, fired by the shell."""
    resize_handlers: list[Callable[[], None]] = field(default_factory=list)
    stop_handlers:   list[Callable[[], None]] = field(default_factory=list)   # called on window close
    telemetry_sinks: list[Callable[..., None]] = field(default_factory=list)  # fed by monitor loop
    on_connected:    list[Callable[[], None]] = field(default_factory=list)   # after successful connect

    def register_resize(self, fn):    self.resize_handlers.append(fn)
    def register_stop(self, fn):      self.stop_handlers.append(fn)
    def register_telemetry(self, fn): self.telemetry_sinks.append(fn)
    def register_on_connected(self, fn): self.on_connected.append(fn)

@dataclass
class AppContext:
    page: Any                    # ft.Page
    settings: dict
    trio_conn: Any               # TrioConnection
    uapi_executor: Any           # ThreadPoolExecutor (pinned UAPI/STA worker)
    ui_loop_holder: dict         # {"loop": ...}
    current_solution: dict       # {"value": ...}
    registry: CallbackRegistry

    # Shared UI helpers (assigned by ui/common.py during shell build):
    show_snack: Callable = None
    section_header: Callable = None
    control_cluster: Callable = None

    # Shared solution helpers (assigned by shell):
    active_solution_key: Callable = None
    get_solution_involved_axes: Callable = None
    save_settings: Callable = None
```

**Wiring rules the agent must follow:**
- Anything used by 2+ features → put on `ctx` (or `ctx.registry`).
- `on_page_resize` → iterate `ctx.registry.resize_handlers`. Each visual
  feature calls `ctx.registry.register_resize(self.resize)` in its `__init__`.
- `on_window_event` (close) → iterate `ctx.registry.stop_handlers`. Monitor and
  flexlink-sim register a `stop()` that clears their run flag.
- Monitor loop → after a batch read, call each `ctx.registry.telemetry_sinks`
  entry. Rotary-sim and flexlink-sim register sinks that wrap their existing
  `update_*_from_reads` functions. **The data passed must be identical to
  today's call arguments** — copy the current call sites verbatim.
- `on_connect_click` → after success, fire `ctx.registry.on_connected`.
  Axis-params registers `apply_saved_params_after_connection`.

---

## 6. Feature module shape (mirror `ui/jog_panel.py` conventions)

Each feature is a class. Former nested functions become methods; former shared
locals become `self.` attributes. Pattern:

```python
class CamboxFeature:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        # ... build controls, restore from ctx.settings ...
        ctx.registry.register_resize(self.resize_profile_view)

    def tab_content(self) -> ft.Control:
        """Return the Control the shell mounts into the solution tab."""
        ...

    # former nested functions -> methods, calling self.ctx.show_snack(...), etc.
```

The shell asks each feature for its `tab_content()` and assembles tabs exactly
as `build_solution_tabs` does today — preserving tab order, titles, and which
solution shows which tabs.

---

## 7. Execution order (safest dependency-first sequence)

Do these as **separate commits**, verifying (Section 8) after each:

1. **`context.py`** — add `AppContext` + `CallbackRegistry`. No call sites yet.
   App still runs unchanged. *(Pure addition.)*
2. **`ui/common.py`** — move `show_snack`, `section_header`, `control_cluster`,
   `_update_if_mounted`, `canvas_paint`, shared style/color constants. In
   `app.py`, build `ctx` early and assign these onto it; replace inner defs with
   `ctx.*` references. Highest reuse → unlocks everything else.
3. **`ui/shell.py`** — move solution picker / workspace / appbar / `solution_card`
   / training cards / `build_solution_tabs`. Shell consumes feature
   `tab_content()`s (initially still inline; rewire as features migrate).
4. **`connection.py`** — connection, status, watchdog, master commands,
   master-speed/cutter-output. Register `on_connected`.
5. **`monitor.py`** — monitor loop + batch read. Register telemetry dispatch
   (no sinks yet — equivalent to current direct calls).
6. **`shear_visual.py`** — conveyor/shear canvas; register resize.
7. **`axis_params.py`** — params; register `apply_saved_params_after_connection`
   on `on_connected`.
8. **`shear_basic.py`**, then **9. `shear_help.py`**.
10. **`cambox.py`** (large — go slowly; profile view is matplotlib-backed).
11. **`rotary_sim.py`** (large; register resize + telemetry sink).
12. **`flexlink_calc.py`**, **13. `rotarylink_calc.py`**,
    **14. `flexlink_sim.py`** (register resize + telemetry + stop),
    **15. `point_to_point.py`**.
16. **Final shrink of `app.py`** — it now only: runs bootstrap patches, builds
    `AppContext`, instantiates features, wires `on_page_resize` /
    `on_window_event` to the registry, mounts the shell, and defines `main`.

> Migrate the two big blocks (`cambox`, `rotary_sim`) in *sub-steps*: first move
> the block into the new module with an explicit parameter list, get it
> importing and running, then convert the parameter passing into the
> class/context shape. Don't refactor and relocate in the same edit.

---

## 8. Per-step verification (MANDATORY after every commit)

Run, in order. If any fails, fix before committing — do not stack changes.

1. **Imports cleanly:**
   `venv\Scripts\python.exe -c "from src.flying_shear_app.app import main"`
2. **App launches** and the solution picker renders:
   `venv\Scripts\python.exe main.py` — open each migrated solution's tabs,
   confirm controls render and no console exceptions.
3. **Unit tests pass:**
   `venv\Scripts\python.exe -m pytest tests/ -q`
   (covers `point_to_point_basic`, `rotary_knife_cam`, `rotarylink`,
   `jog_panel`, `trio_connection`, `asyncio_windows`, `axis_startup_basic`).
4. **Generated-code parity** for any calculator touched: before starting, save a
   reference copy of each tab's generated TRIO BASIC for a fixed set of inputs;
   after the step, regenerate with identical inputs and **diff — must be byte
   identical**. Also run `rotary_knife_cam_self_test.py` if the step touched
   cam/rotary.
5. **No leftover references** to a moved symbol remain in `app.py` (LSP
   `findReferences` on the moved name returns only the new module).

Commit message format: `refactor(app): extract <feature> into features/<file>`.

---

## 9. Guardrails / do-NOT list

- ❌ Don't change any computed value, default, label, tooltip, color, or
  generated-code string.
- ❌ Don't reorder tabs or solutions, or change which tabs a solution shows.
- ❌ Don't "fix" the dict/list holder pattern by inventing new state shapes —
  move the holders onto features/context as-is.
- ❌ Don't touch `domain/`, `codegen/`, `controller/`, `config/`, `bootstrap/`
  logic — they're already clean; only import from them.
- ❌ Don't change threading: UAPI calls must stay on `uapi_executor`
  (COM/STA-affine); UI updates stay on the page/UI loop.
- ❌ Don't introduce circular imports — features import `context` + `ui.common`,
  never each other. Cross-feature talk goes through `ctx.registry`.
- ❌ Don't combine "move" and "rename/refactor" in one commit.

---

## 10. Definition of done

- `app.py` ≤ ~250 lines and contains only shell wiring + `main(page)`.
- Every feature lives in its own `features/*.py`, each ≤ ~800 lines.
- Cross-feature interaction flows exclusively through `AppContext` /
  `CallbackRegistry` (no feature imports another feature).
- `pytest tests/` green; app launches; every calculator's generated code is
  byte-identical to a pre-refactor capture; resize, monitor telemetry, connect,
  and window-close all behave as before.
- `main.py`'s `from src.flying_shear_app.app import main` is unchanged.

---

## 11. Suggested first prompt to the implementing agent

> "Implement **Step 1 and Step 2 only** from `APP_SPLIT_PLAN.md`: create
> `context.py` (`AppContext` + `CallbackRegistry`), then extract the shared UI
> helpers into `ui/common.py` and route them through `ctx`. Do not touch any
> feature logic. Verify with Section 8 (import, launch, `pytest tests/`), then
> commit as `refactor(app): add AppContext + extract shared UI helpers`. Stop
> and report before starting Step 3."
