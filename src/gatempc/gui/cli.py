"""The command line of the results explorer.

It lives inside the package so that ``main.py`` at the repository root, the
``gatempc-gui`` console script and ``python -m gatempc.gui`` are three doors into one
implementation rather than three copies of it.

PyQt6 is imported only when a window is actually wanted, so ``--list-pages`` works on a
machine that has no GUI toolkit at all.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import data as gdata
from . import i18n, pages

INSTALL_HINT = """\
The results explorer needs PyQt6, which is deliberately not part of the reproducibility
requirements: every number can be recomputed without it.

    python -m pip install PyQt6

or, for everything the explorer needs:

    python -m pip install -r requirements-gui.txt

On Linux a desktop session is also required. On a bare Linux server, run the scripts
in scripts/ directly, or render a page without a display:

    QT_QPA_PLATFORM=offscreen python main.py --screenshot page.png

That variable is for Linux only. On Windows the offscreen plugin ships no fonts and
renders every character as an empty box; --screenshot there needs the native plugin,
which draws the window without putting it on the desktop anyway.
"""


def build_parser(program: str = "main.py") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program,
        description="Open the GateMPC results explorer.",
    )
    parser.add_argument(
        "--language",
        "-l",
        default=os.environ.get("GATEMPC_LANGUAGE", i18n.DEFAULT_LANGUAGE),
        choices=list(i18n.LANGUAGES),
        help="uz (Uzbek, Cyrillic) or en (English). Default: uz.",
    )
    parser.add_argument(
        "--page",
        "-p",
        default=None,
        choices=list(pages.PAGE_KEYS),
        help="Open on this page.",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        help="Write the chosen page to this PNG and exit, instead of opening a window. "
             "The window is rendered without appearing on the desktop. Do not set "
             "QT_QPA_PLATFORM=offscreen on Windows: it has no fonts there.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root to read results from. Default: the repository this file is in.",
    )
    parser.add_argument(
        "--list-pages",
        action="store_true",
        help="Print the page keys and exit.",
    )
    return parser


def main(argv: list[str] | None = None, program: str = "main.py") -> int:
    arguments = build_parser(program).parse_args(argv)

    if arguments.list_pages:
        for key in pages.PAGE_KEYS:
            print(f"{key:<12} {pages.nav_label(key, arguments.language)}")
        return 0

    root = Path(arguments.root) if arguments.root else gdata.ProjectPaths.discover().root

    try:
        from .app import launch
    except ModuleNotFoundError as error:  # pragma: no cover - depends on the machine
        if error.name and error.name.split(".")[0] == "PyQt6":
            print(INSTALL_HINT, file=sys.stderr)
            return 3
        raise

    return launch(
        root=root,
        language=arguments.language,
        page=arguments.page,
        screenshot=Path(arguments.screenshot) if arguments.screenshot else None,
    )
