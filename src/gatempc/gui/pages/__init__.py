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

**This module imports no Qt.** The registry below is plain data, so the page list, the
nav labels and the section names can be read on a machine that has never installed a
GUI toolkit — which is what makes ``python main.py --list-pages`` work there. Only
:func:`module_of` reaches for a page module, and only that pulls PyQt6 in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .. import data as gdata

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at run time
    from PyQt6.QtWidgets import QWidget


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


@dataclass(frozen=True)
class Page:
    """One page, described without loading it."""

    key: str
    module: str
    section: str
    uzbek: str
    english: str


#: Section captions for the sidebar and the View menu.
SECTIONS: dict[str, tuple[str, str]] = {
    "argument": ("МАҚОЛАНИНГ ЙЎЛИ", "THE ARGUMENT"),
    "laboratory": ("ЛАБОРАТОРИЯ", "THE LABORATORY"),
    "apparatus": ("АППАРАТ", "THE APPARATUS"),
}

#: The pages, in nav order. The number in each label is its position in this tuple;
#: ``test_nav_numbers_follow_the_page_order`` keeps the two from drifting apart.
PAGES: tuple[Page, ...] = (
    Page("claim", "claim", "argument",
         "1 · Даъво", "1 · The claim"),
    Page("circularity", "circularity", "argument",
         "2 · Доиравийлик", "2 · Circularity"),
    Page("independent", "independent", "argument",
         "3 · Мустақил текширув", "3 · Independent check"),
    Page("archive", "archive", "argument",
         "4 · Архивнинг чегаралари", "4 · Limits of the archive"),
    Page("control", "control", "argument",
         "5 · Бошқарув", "5 · Control"),
    Page("prereg", "prereg", "argument",
         "6 · Пре-регистрация", "6 · Pre-registration"),
    Page("calculator", "calculator", "laboratory",
         "7 · Затвор калькулятори", "7 · Gate calculator"),
    Page("detector", "detector_page", "laboratory",
         "8 · Доиравийлик детектори", "8 · Circularity detector"),
    Page("experiment", "experiment", "laboratory",
         "9 · Бошқарув тажрибаси", "9 · Control experiment"),
    Page("gallery", "gallery", "apparatus",
         "10 · Расм ва жадваллар", "10 · Figures and tables"),
    Page("reproduce", "reproduce", "apparatus",
         "11 · Қайта юритиш", "11 · Reproduce"),
    Page("help", "help", "apparatus",
         "12 · Ёрдам", "12 · Help"),
)

PAGE_KEYS: tuple[str, ...] = tuple(page.key for page in PAGES)

_BY_KEY: dict[str, Page] = {page.key: page for page in PAGES}


def page_of(key: str) -> Page:
    return _BY_KEY[key]


def module_of(key: str):
    """Import one page module. This is the only call here that needs PyQt6."""
    return __import__(f"{__name__}.{_BY_KEY[key].module}", fromlist=["build"])


def build_page(key: str, context: Context) -> "QWidget":
    return module_of(key).build(context)


def nav_label(key: str, language: str) -> str:
    from .. import i18n

    page = _BY_KEY[key]
    return i18n.pick(language, page.uzbek, page.english)


def section_of(key: str) -> str:
    return _BY_KEY[key].section


def section_label(section: str, language: str) -> str:
    from .. import i18n

    uzbek, english = SECTIONS[section]
    return i18n.pick(language, uzbek, english)
