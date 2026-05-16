"""Windows asyncio compatibility helpers."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Mapping
from typing import Any


_PROACTOR_PIPE_LOST_CALLBACK = "_ProactorBasePipeTransport._call_connection_lost"
_CONNECTION_RESET_BY_REMOTE_HOST = 10054


def _callback_name(handle: Any) -> str:
    callback = getattr(handle, "_callback", None)
    if callback is None:
        return repr(handle)
    return getattr(callback, "__qualname__", repr(callback))


def is_windows_proactor_pipe_reset(context: Mapping[str, Any]) -> bool:
    """Return true for benign proactor pipe resets during Windows shutdown."""
    exc = context.get("exception")
    if not isinstance(exc, ConnectionResetError):
        return False

    winerror = getattr(exc, "winerror", None)
    errno = getattr(exc, "errno", None)
    if winerror != _CONNECTION_RESET_BY_REMOTE_HOST and errno != _CONNECTION_RESET_BY_REMOTE_HOST:
        return False

    handle = context.get("handle")
    handle_text = repr(handle)
    callback_name = _callback_name(handle)
    return (
        _PROACTOR_PIPE_LOST_CALLBACK in callback_name
        or _PROACTOR_PIPE_LOST_CALLBACK in handle_text
    )


def install_asyncio_windows_pipe_reset_filter() -> bool:
    """Suppress one noisy Windows proactor shutdown callback in the active loop."""
    if not sys.platform.startswith("win"):
        return False

    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if is_windows_proactor_pipe_reset(context):
            logging.debug(
                "Ignoring benign Windows asyncio pipe reset during shutdown",
                exc_info=context.get("exception"),
            )
            return

        if previous_handler is not None:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(exception_handler)
    return True
