"""Start the window.

Kept apart from ``window.py`` so that the Qt application object, the style and the
offscreen screenshot mode all live in one place, and so that importing the window for
a test does not create an application.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from . import i18n
from .theme import APP_STYLE
from .window import MainWindow


def _application() -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    application = QApplication(sys.argv)
    application.setApplicationName("GateMPC")
    application.setApplicationDisplayName("GateMPC")
    application.setOrganizationName("GateMPC")
    # Fusion renders identically on Windows, macOS and Linux, so a screenshot taken on
    # one machine is the interface the reader sees on theirs.
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLE)
    return application


def warn_about_fonts() -> str:
    """Windows' ``offscreen`` plugin ships no fonts, and renders every glyph as a box.

    Qt says so itself, in a warning that is easy to lose in a loop of a hundred runs
    and impossible to see in the resulting image without opening it. So the check is
    made here, before the image is written, and the answer is a sentence the caller
    can print: on Windows a screenshot needs the native plugin, which
    ``WA_DontShowOnScreen`` below keeps from flashing a window on the desktop.
    """
    if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        return (
            "QT_QPA_PLATFORM=offscreen has no fonts on Windows, so every character in "
            "this image will be an empty box. Unset it and run the same command again: "
            "the window is rendered without appearing on the desktop either way."
        )
    return ""


def launch(
    root: Path | str | None = None,
    language: str = i18n.DEFAULT_LANGUAGE,
    page: str | None = None,
    screenshot: Path | str | None = None,
) -> int:
    """Open the window, or write a screenshot of one page and exit.

    The screenshot path renders the window without ever putting it on the desktop, so
    it needs no free screen and flashes nothing at the user. It does need a platform
    plugin that can find fonts: the native one everywhere, or ``offscreen`` on a Linux
    machine with fontconfig. On Windows ``offscreen`` has no fonts at all, and
    :func:`warn_about_fonts` says so rather than letting a page of empty boxes pass
    for a screenshot.
    """
    application = _application()
    window = MainWindow(root=root, language=language)
    if page:
        window.show_page(page)

    if screenshot is not None:
        complaint = warn_about_fonts()
        if complaint:
            print(complaint, file=sys.stderr)
        target = Path(screenshot)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Lay the window out and paint it without mapping it to the screen.
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        application.processEvents()
        pixmap = window.grab()
        window.close()
        saved = pixmap.save(str(target))
        if saved and complaint:
            return 4          # the file exists, but nobody should trust what is in it
        return 0 if saved else 1

    window.show()
    return application.exec()
