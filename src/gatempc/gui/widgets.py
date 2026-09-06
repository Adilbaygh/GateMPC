"""The small set of widgets every page is built from.

The one that matters is :class:`NumberCard`. It cannot be constructed without a source
string, which is how the promise made in ``data.py`` — no number on screen without the
file it came from — is kept structurally rather than by discipline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QLocale, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import data as gdata
from . import i18n
from .theme import COLORS

CONTENT_WIDTH = 1000


# ----------------------------------------------------------------------- helpers


def open_in_file_manager(path: Path) -> None:
    """Reveal a file or folder using whatever the platform provides.

    ``QDesktopServices`` maps to Explorer, Finder and the freedesktop handler, so this
    is the one call that works on all three systems.
    """
    target = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def open_file(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def copy_to_clipboard(text: str) -> None:
    clipboard = QGuiApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def wrap_scroll(inner: QWidget) -> QScrollArea:
    """Put a page inside a scroll area that keeps a comfortable reading width."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    holder = QWidget()
    holder.setObjectName("Page")
    outer = QHBoxLayout(holder)
    outer.setContentsMargins(28, 24, 28, 32)
    outer.addStretch(1)
    inner.setMaximumWidth(CONTENT_WIDTH)
    outer.addWidget(inner, 20)
    outer.addStretch(1)
    area.setWidget(holder)
    return area


def column(spacing: int = 16, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QWidget:
    holder = QWidget()
    holder.setObjectName("Page")
    layout = QVBoxLayout(holder)
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    return holder


def body_of(holder: QWidget) -> QVBoxLayout:
    layout = holder.layout()
    assert isinstance(layout, QVBoxLayout)
    return layout


# ------------------------------------------------------------------------ labels


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageTitle")
    label.setWordWrap(True)
    return label


def page_lead(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageLead")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    label.setWordWrap(True)
    # Explicit rather than auto-detected, so subscripts such as A<sub>s</sub> render
    # instead of being shown as markup.
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


def paragraph(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("CardBody")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    label.setOpenExternalLinks(False)
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def chip(text: str, foreground: str, background: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Chip")
    label.setStyleSheet(f"color: {foreground}; background: {background};")
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


# ------------------------------------------------------------------------- cards


class Card(QFrame):
    """A white panel with an optional title. Everything else goes inside it."""

    def __init__(self, title: str = "", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 18)
        self._layout.setSpacing(10)
        if title:
            heading = QLabel(title)
            heading.setObjectName("CardTitle")
            heading.setWordWrap(True)
            self._layout.addWidget(heading)
        if subtitle:
            self._layout.addWidget(paragraph(subtitle))

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_text(self, text: str) -> QLabel:
        return self.add(paragraph(text))  # type: ignore[return-value]


class NumberCard(QFrame):
    """One measured quantity: the value, what it is, and where it was read from.

    ``source`` is required. A caller that has no source has no business putting a
    number on screen.
    """

    def __init__(
        self,
        value: str,
        caption: str,
        source: str,
        tone: str = "ink",
        note: str = "",
    ) -> None:
        super().__init__()
        self.setObjectName("NumberCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        shown = QLabel(value)
        shown.setObjectName("NumberValue")
        shown.setStyleSheet(f"color: {COLORS.get(tone, COLORS['ink'])};")
        shown.setWordWrap(False)
        layout.addWidget(shown)

        text = QLabel(caption)
        text.setObjectName("NumberCaption")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(text)

        if note:
            extra = QLabel(note)
            extra.setObjectName("NumberCaption")
            extra.setStyleSheet(f"color: {COLORS['ink_faint']};")
            extra.setWordWrap(True)
            extra.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(extra)

        layout.addSpacing(2)
        origin = QLabel(source)
        origin.setObjectName("NumberSource")
        origin.setWordWrap(True)
        origin.setToolTip(source)
        layout.addWidget(origin)


def number_card(
    results: gdata.Results,
    reference: str,
    caption: str,
    *,
    formatter=gdata.as_number,
    tone: str = "ink",
    note: str = "",
    fallback: str = "—",
) -> NumberCard:
    """Build a :class:`NumberCard` straight from a ``file:key`` reference."""
    found = results.value(reference)
    if not found.ok:
        return NumberCard(fallback, caption, f"{found.source}  ({found.problem})", "ink_faint")
    return NumberCard(formatter(found.value), caption, found.source, tone, note)


def card_row(cards: Iterable[QWidget], columns: int = 3) -> QWidget:
    """Lay number cards out in a grid that stays readable when the window narrows."""
    holder = QWidget()
    holder.setObjectName("Page")
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(12)
    for index, widget in enumerate(cards):
        grid.addWidget(widget, index // columns, index % columns)
    for position in range(columns):
        grid.setColumnStretch(position, 1)
    return holder


# ----------------------------------------------------------------------- figures


class FigureCard(Card):
    """A published figure with its caption and the files it was drawn from."""

    MAX_WIDTH = 940

    def __init__(self, figure: gdata.Figure, paths: gdata.ProjectPaths, language: str) -> None:
        caption = figure.what or figure.name
        title = f"{_figure_word(language)} {figure.number}. {caption}"
        super().__init__(title)
        if figure.section:
            self.add(paragraph(figure.section))

        if not figure.exists:
            self.add(paragraph(i18n.ui(language, "no_figure")))
            return

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(figure.path))
        if not pixmap.isNull():
            if pixmap.width() > self.MAX_WIDTH:
                pixmap = pixmap.scaledToWidth(
                    self.MAX_WIDTH, Qt.TransformationMode.SmoothTransformation
                )
            image.setPixmap(pixmap)
        self.add(image)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        origin = QLabel(paths.relative(figure.path))
        origin.setObjectName("NumberSource")
        footer.addWidget(origin)
        footer.addStretch(1)
        if figure.sources:
            drawn_from = QPushButton(
                i18n.pick(language, "Қайси файллардан чизилган", "Files it was drawn from")
            )
            drawn_from.setObjectName("Link")
            drawn_from.setToolTip("\n".join(figure.sources))
            drawn_from.clicked.connect(lambda: copy_to_clipboard("\n".join(figure.sources)))
            footer.addWidget(drawn_from)
        full_size = QPushButton(i18n.pick(language, "Тўлиқ ҳажмда очиш", "Open full size"))
        full_size.setObjectName("Link")
        full_size.clicked.connect(lambda: open_file(figure.path))
        footer.addWidget(full_size)
        self.add_layout(footer)


def _figure_word(language: str) -> str:
    return i18n.pick(language, "Расм", "Figure")


# ------------------------------------------------------------------------ tables


def table_widget(table: gdata.Table, max_height: int = 320) -> QTableWidget:
    widget = QTableWidget(len(table.rows), len(table.header))
    widget.setHorizontalHeaderLabels(table.header)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setAlternatingRowColors(False)
    widget.setWordWrap(False)
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row):
            if column_index >= len(table.header):
                continue
            item = QTableWidgetItem(cell)
            if _looks_numeric(cell):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            widget.setItem(row_index, column_index, item)
    header = widget.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(True)
    widget.resizeRowsToContents()
    widget.setMaximumHeight(max_height)
    widget.setMinimumHeight(min(max_height, 90 + 24 * min(len(table.rows), 6)))
    return widget


def _looks_numeric(text: str) -> bool:
    stripped = text.strip().replace("−", "-").replace(" ", "").replace(",", "")
    if not stripped:
        return False
    if stripped.endswith("%"):
        stripped = stripped[:-1]
    try:
        float(stripped)
    except ValueError:
        return False
    return True


class TableCard(Card):
    """One results CSV, with its path and a button that opens it."""

    def __init__(
        self,
        path: Path,
        paths: gdata.ProjectPaths,
        language: str,
        title: str = "",
        note: str = "",
        max_height: int = 320,
    ) -> None:
        super().__init__(title or path.name)
        table = gdata.read_table(path)
        if table is None:
            self.add(
                paragraph(
                    i18n.pick(
                        language,
                        f"`{paths.relative(path)}` топилмади.",
                        f"`{paths.relative(path)}` was not found.",
                    )
                )
            )
            return
        if note:
            self.add(paragraph(note))
        self.add(table_widget(table, max_height))

        footer = QHBoxLayout()
        footer.setSpacing(8)
        shown = len(table.rows)
        label = paths.relative(path)
        if table.truncated:
            label += i18n.pick(
                language,
                f"  ·  биринчи {shown} сатр кўрсатилди",
                f"  ·  first {shown} rows shown",
            )
        origin = QLabel(label)
        origin.setObjectName("NumberSource")
        footer.addWidget(origin)
        footer.addStretch(1)
        open_button = QPushButton(i18n.pick(language, "CSV ни очиш", "Open the CSV"))
        open_button.setObjectName("Link")
        open_button.clicked.connect(lambda: open_file(path))
        footer.addWidget(open_button)
        self.add_layout(footer)


# ----------------------------------------------------------------- key/value grid


def key_values(pairs: Iterable[tuple[str, str]], columns: int = 2) -> QWidget:
    holder = QWidget()
    holder.setObjectName("Page")
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(7)
    for index, (key, value) in enumerate(pairs):
        row = index // columns
        base = (index % columns) * 2
        name = QLabel(key)
        name.setObjectName("CardBody")
        shown = QLabel(value)
        shown.setWordWrap(True)
        shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(name, row, base)
        grid.addWidget(shown, row, base + 1)
    for position in range(columns):
        grid.setColumnStretch(position * 2 + 1, 1)
    return holder


def icon_size() -> QSize:  # pragma: no cover - trivial
    return QSize(16, 16)


# -------------------------------------------------------------------- form input


#: Numbers are entered and shown the way the manuscript writes them: a dot for the
#: decimal, no group separator. Without this a Windows machine set to Uzbek or Russian
#: would offer "1,3000" in the input field while every computed value on the same
#: screen reads "25.5580" — two conventions in one window, and an invitation to
#: mistype a coefficient.
SCIENTIFIC_LOCALE = QLocale.c()


def spin(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1e9,
    decimals: int = 4,
    step: float = 0.01,
    suffix: str = "",
    tooltip: str = "",
) -> QDoubleSpinBox:
    """A number field. Wide enough that four decimals are not cut off."""
    box = QDoubleSpinBox()
    box.setLocale(SCIENTIFIC_LOCALE)
    box.setDecimals(decimals)
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setValue(value)
    box.setMinimumWidth(150)
    box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    box.setKeyboardTracking(False)
    if suffix:
        box.setSuffix(" " + suffix)
    if tooltip:
        box.setToolTip(tooltip)
    return box


def integer_spin(
    value: int,
    minimum: int = 0,
    maximum: int = 1_000_000,
    step: int = 1,
    suffix: str = "",
    tooltip: str = "",
) -> QSpinBox:
    box = QSpinBox()
    box.setLocale(SCIENTIFIC_LOCALE)
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setValue(value)
    box.setMinimumWidth(150)
    box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    box.setKeyboardTracking(False)
    if suffix:
        box.setSuffix(" " + suffix)
    if tooltip:
        box.setToolTip(tooltip)
    return box


def combo(items: Iterable[tuple[str, object]], tooltip: str = "") -> QComboBox:
    """A chooser whose entries carry a value alongside their label."""
    box = QComboBox()
    for label, value in items:
        box.addItem(label, value)
    box.setMinimumWidth(150)
    if tooltip:
        box.setToolTip(tooltip)
    return box


def form(rows: Iterable[tuple[str, QWidget]], columns: int = 2) -> QWidget:
    """A label/field grid. Two columns by default so a long form stays on screen."""
    holder = QWidget()
    holder.setObjectName("Page")
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(20)
    grid.setVerticalSpacing(9)
    for index, (label, field) in enumerate(rows):
        row = index // columns
        base = (index % columns) * 2
        name = QLabel(label)
        name.setObjectName("CardBody")
        name.setWordWrap(True)
        grid.addWidget(name, row, base)
        grid.addWidget(field, row, base + 1)
    for position in range(columns):
        grid.setColumnStretch(position * 2, 3)
        grid.setColumnStretch(position * 2 + 1, 2)
    return holder


# ------------------------------------------------------------------------ charts


class Chart(QWidget):
    """A matplotlib figure inside the window, or an honest note if it is absent.

    matplotlib is already required to draw the manuscript's figures, so embedding
    it adds no dependency; but the window still has to open on a machine where the
    import fails rather than crashing at start-up.
    """

    def __init__(self, height: int = 300) -> None:
        super().__init__()
        self.setObjectName("Page")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.canvas = None
        self.figure = None
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except Exception as error:  # pragma: no cover - depends on the machine
            note = paragraph(f"matplotlib is not available: {error}")
            self._layout.addWidget(note)
            return
        self.figure = Figure(figsize=(7.4, height / 100), dpi=100,
                             facecolor=COLORS["card"])
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(height)
        self._layout.addWidget(self.canvas)

    def axes(self):
        """A cleared single axis, styled like the rest of the window."""
        if self.figure is None:
            return None
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(COLORS["card"])
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(COLORS["border_strong"])
        ax.tick_params(colors=COLORS["ink_soft"], labelsize=9)
        ax.grid(True, color=COLORS["border"], linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)
        return ax

    def draw(self) -> None:
        if self.canvas is not None:
            self.figure.tight_layout()
            self.canvas.draw_idle()
