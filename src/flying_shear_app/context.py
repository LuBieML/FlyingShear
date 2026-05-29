from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CallbackRegistry:
    """Cross-feature lifecycle hooks, registered by features, fired by the shell."""

    resize_handlers: list[Callable[[], None]] = field(default_factory=list)
    stop_handlers: list[Callable[[], None]] = field(default_factory=list)
    telemetry_sinks: list[Callable[..., None]] = field(default_factory=list)
    on_connected: list[Callable[[], None]] = field(default_factory=list)

    def register_resize(self, fn):
        self.resize_handlers.append(fn)

    def register_stop(self, fn):
        self.stop_handlers.append(fn)

    def register_telemetry(self, fn):
        self.telemetry_sinks.append(fn)

    def register_on_connected(self, fn):
        self.on_connected.append(fn)


@dataclass
class AppContext:
    page: Any
    settings: dict
    trio_conn: Any
    uapi_executor: Any
    ui_loop_holder: dict
    current_solution: dict
    registry: CallbackRegistry

    show_snack: Callable = None
    section_header: Callable = None
    control_cluster: Callable = None

    active_solution_key: Callable = None
    get_solution_involved_axes: Callable = None
    save_settings: Callable = None
