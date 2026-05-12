"""Compatibility patches for flet_charts inside rebuilt Flet tabs."""

import asyncio

import flet_charts as fc


def patch_flet_charts_matplotlib_lifecycle():
    """Make flet_charts' Matplotlib control safe across tab/page rebuilds."""
    chart_cls = getattr(fc, "MatplotlibChart", None)
    if chart_cls is None or getattr(chart_cls, "_flying_shear_lifecycle_patch", False):
        return

    original_build = chart_cls.build
    original_receive_loop = chart_cls._receive_loop

    def _manager_for(chart):
        figure = getattr(chart, "figure", None)
        canvas = getattr(figure, "canvas", None)
        return getattr(canvas, "manager", None)

    def _discard_web_socket(chart):
        manager = _manager_for(chart)
        sockets = getattr(manager, "web_sockets", None)
        if sockets is None:
            return
        try:
            sockets.discard(chart)
        except AttributeError:
            try:
                if chart in sockets:
                    sockets.remove(chart)
            except (KeyError, ValueError):
                pass

    def patched_build(self):
        self._flying_shear_unmounted = False
        self._flying_shear_receive_task = None
        return original_build(self)

    def patched_will_unmount(self):
        self._flying_shear_unmounted = True
        _discard_web_socket(self)
        task = getattr(self, "_flying_shear_receive_task", None)
        if task is not None and not task.done():
            task.cancel()
        self._flying_shear_receive_task = None
        setattr(self, "_MatplotlibChart__started", False)

    async def patched_receive_loop(self):
        try:
            await original_receive_loop(self)
        except asyncio.CancelledError:
            raise
        except RuntimeError as ex:
            if "Timeout waiting for invoke method listener" in str(ex):
                _discard_web_socket(self)
                self._flying_shear_unmounted = True
                self._flying_shear_receive_task = None
                setattr(self, "_MatplotlibChart__started", False)
                return
            raise

    async def patched_on_canvas_resize(self, e):
        self._flying_shear_unmounted = False
        manager = _manager_for(self)
        sockets = getattr(manager, "web_sockets", None)
        registered = sockets is not None and self in sockets
        task = getattr(self, "_flying_shear_receive_task", None)
        started = bool(getattr(self, "_MatplotlibChart__started", False))

        if not started or not registered or task is None or task.done():
            setattr(self, "_MatplotlibChart__started", True)
            self._flying_shear_receive_task = asyncio.create_task(self._receive_loop())
            if manager is not None and not registered:
                manager.add_web_socket(self)
            self.send_message({"type": "send_image_mode"})
            self.send_message(
                {
                    "type": "set_device_pixel_ratio",
                    "device_pixel_ratio": getattr(self, "_MatplotlibChart__dpr", 1),
                }
            )
            self.send_message({"type": "refresh"})

        self._width = e.width
        self._height = e.height
        self.send_message(
            {"type": "resize", "width": self._width, "height": self._height}
        )

    chart_cls.build = patched_build
    chart_cls.will_unmount = patched_will_unmount
    chart_cls._receive_loop = patched_receive_loop
    chart_cls._on_canvas_resize = patched_on_canvas_resize
    chart_cls._flying_shear_lifecycle_patch = True
