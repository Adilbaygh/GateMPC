"""The GateMPC results explorer.

``data``, ``preregistration`` and ``i18n`` are free of Qt, so they can be imported on a
machine that has never installed a GUI toolkit — the tests rely on that. Everything
that needs PyQt6 is reached through the lazy attribute below, which means

    from gatempc.gui import data

costs nothing, while

    from gatempc.gui import launch

is what pulls PyQt6 in.
"""

from __future__ import annotations

from typing import Any

__all__ = ["launch", "MainWindow", "data", "i18n", "preregistration"]


def __getattr__(name: str) -> Any:
    if name == "launch":
        from .app import launch

        return launch
    if name == "MainWindow":
        from .window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
