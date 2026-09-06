"""Page 7 — every published figure and table, each with the files it came from."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QStackedWidget, QWidget

from .. import data as gdata
from .. import widgets as w
from . import Context

NAV = ("10 · Расм ва жадваллар", "10 · Figures and tables")


def build(context: Context) -> QWidget:
    body = w.column(16)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Ҳамма расм ва жадвал — ҳар бири ўз манбаси билан",
                "Every figure and table, each with its own provenance",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Манба рўйхати қўлда ёзилмаган: `make_figures.py` чизиш пайтида очган "
                "ҳар бир файлни қайд қилади ва уларни "
                "<code>results/figure_provenance.json</code> га ёзади. Илова A ўша "
                "файлдан ҳосил бўлади.",
                "The source lists are not typed by hand: `make_figures.py` records every "
                "file it opens while drawing and writes them to "
                "<code>results/figure_provenance.json</code>. Appendix A is derived from "
                "that file.",
            )
        )
    )

    layout.addWidget(_picker(context))
    return w.wrap_scroll(body)


def _picker(context: Context) -> QWidget:
    """One selector over three groups, so the page opens fast and stays navigable."""
    holder = w.column(14)
    inner = w.body_of(holder)

    chooser = QComboBox()
    stack = QStackedWidget()

    groups: list[tuple[str, QWidget]] = [
        (
            context.pick("Расмлар (10 та)", "Figures (10)"),
            _figures(context),
        ),
        (
            context.pick("Мақоланинг жадваллари", "Manuscript tables"),
            _tables(context, gdata.manuscript_tables(context.paths), 420),
        ),
        (
            context.pick("Ёрдамчи жадваллар", "Supporting tables"),
            _tables(context, gdata.supporting_tables(context.paths), 300),
        ),
    ]
    for label, widget in groups:
        chooser.addItem(label)
        stack.addWidget(widget)
    chooser.currentIndexChanged.connect(stack.setCurrentIndex)

    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(chooser, 0)
    row.addStretch(1)
    inner.addLayout(row)
    inner.addWidget(stack)
    return holder


def _figures(context: Context) -> QWidget:
    holder = w.column(14)
    inner = w.body_of(holder)
    found = gdata.figures(context.paths, context.results)
    if not found:
        inner.addWidget(
            w.Card(
                "",
                context.pick(
                    "Расмлар ҳали чизилмаган. «Қайта юритиш» саҳифасидан "
                    "`make_figures.py` ни юритинг.",
                    "The figures have not been drawn yet. Run `make_figures.py` from the "
                    "“Reproduce” page.",
                ),
            )
        )
        return holder
    for figure in found:
        inner.addWidget(w.FigureCard(figure, context.paths, context.language))
    return holder


def _tables(context: Context, paths, max_height: int) -> QWidget:
    holder = w.column(14)
    inner = w.body_of(holder)
    if not paths:
        inner.addWidget(
            w.Card(
                "",
                context.pick(
                    "Жадваллар ҳали тузилмаган. `make_tables.py` ни юритинг.",
                    "The tables have not been assembled yet. Run `make_tables.py`.",
                ),
            )
        )
        return holder
    for path in paths:
        inner.addWidget(
            w.TableCard(path, context.paths, context.language, max_height=max_height)
        )
    return holder
