"""The GateMPC results explorer.

``preregistration``, ``i18n``, ``lab`` and the page registry are free of Qt, as is
``gatempc.results``, which reads the published result files. Everything that needs
PyQt6 is reached through the lazy attribute below, which means

    from gatempc.gui import preregistration

costs nothing, while

    from gatempc.gui import launch

is what pulls PyQt6 in.
"""

from __future__ import annotations

from typing import Any

__all__ = ["launch", "MainWindow", "i18n", "lab", "preregistration"]


def __getattr__(name: str) -> Any:
    if name == "launch":
        from .app import launch

        return launch
    if name == "MainWindow":
        from .window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
