"""The pages, in the order the work is done.

Three sections, because the window serves three different visits.

*The argument* walks the same road the manuscript walks: here is the claim; here is
why the usual check is circular; here is the way out; here is what the archive can and
cannot give; here is what it costs a controller; here is what was written down before
any of it was measured.

*The laboratory* is where you put your own numbers in. A calculator for the two gate
laws, the circularity detector pointed at whatever structure you have, and the
closed-loop experiment with parameters you choose. Nothing here writes into
``results/``.

*The apparatus* is the machinery: every figure and table with its provenance, the
buttons that reproduce the lot, and the help.

Each page module exposes ``NAV`` (its two nav labels) and ``build(context)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtWidgets import QWidget

from .. import data as gdata


@dataclass
class Context:
    """What a page needs: where things are, what they say, and how to move on."""

    paths: gdata.ProjectPaths
    results: gdata.Results
    language: str
    goto: Callable[[str], None]

    def pick(self, uzbek: str, english: str) -> str:
        from .. import i18n

        return i18n.pick(self.language, uzbek, english)


#: Section captions for the sidebar and the View menu.
SECTIONS: dict[str, tuple[str, str]] = {
    "argument": ("МАҚОЛАНИНГ ЙЎЛИ", "THE ARGUMENT"),
    "laboratory": ("ЛАБОРАТОРИЯ", "THE LABORATORY"),
    "apparatus": ("АППАРАТ", "THE APPARATUS"),
}

#: (key, module name, section) in nav order.
PAGE_ORDER: tuple[tuple[str, str, str], ...] = (
    ("claim", "claim", "argument"),
    ("circularity", "circularity", "argument"),
    ("independent", "independent", "argument"),
    ("archive", "archive", "argument"),
    ("control", "control", "argument"),
    ("prereg", "prereg", "argument"),
    ("calculator", "calculator", "laboratory"),
    ("detector", "detector_page", "laboratory"),
    ("experiment", "experiment", "laboratory"),
    ("gallery", "gallery", "apparatus"),
    ("reproduce", "reproduce", "apparatus"),
    ("help", "help", "apparatus"),
)

PAGE_KEYS: tuple[str, ...] = tuple(key for key, _module, _section in PAGE_ORDER)

_MODULES: dict[str, str] = {key: module for key, module, _section in PAGE_ORDER}
_SECTION_OF: dict[str, str] = {key: section for key, _module, section in PAGE_ORDER}


def module_of(key: str):
    """Import one page module lazily. Pages pull in matplotlib and the package."""
    return __import__(f"{__name__}.{_MODULES[key]}", fromlist=["build", "NAV"])


def build_page(key: str, context: Context) -> QWidget:
    return module_of(key).build(context)


def nav_label(key: str, language: str) -> str:
    from .. import i18n

    uzbek, english = module_of(key).NAV
    return i18n.pick(language, uzbek, english)


def section_of(key: str) -> str:
    return _SECTION_OF[key]


def section_label(section: str, language: str) -> str:
    from .. import i18n

    uzbek, english = SECTIONS[section]
    return i18n.pick(language, uzbek, english)
