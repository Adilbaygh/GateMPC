"""Add a USGS station of your own to the detector's list.

Three things happen here, in this order, and the order is the point.

*Look up.* One request to the time-series-metadata collection returns every series
the station publishes. Nothing is downloaded and nothing is written.

*Assign.* The four roles the detector needs — gate opening, headwater, tailwater,
discharge — are proposed by ``download_usgs.propose_roles`` and then confirmed by
the person. The proposal is never taken on trust, because the two stages share
parameter code 00065 and are told apart only by ``sublocation_identifier``, a
free-text field the operating office writes. Both published sites say
"H1 (Headwater)"; nothing obliges a third to say anything at all. Swapping them
inverts the head difference, and nothing anywhere would complain.

*Remember.* The assignment goes to ``build/lab/stations.json`` with the moment it
was made, so the fetch can be repeated and a surprising result can be traced back
to the decision that produced it.

The dialog cannot reach the published data package: everything it leads to is
written under ``build/lab``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import lab
from . import widgets as w
from .pages import Context
from .theme import COLORS
from .workers import FunctionRunner

ROLE_LABELS = {
    "gate_opening": ("Затвор очилиши", "Gate opening"),
    "headwater": ("Юқори бьеф H₁", "Headwater H₁"),
    "tailwater": ("Қуйи бьеф H₂", "Tailwater H₂"),
    "discharge": ("Сарф Q", "Discharge Q"),
}
ROLES = ("gate_opening", "headwater", "tailwater", "discharge")


def series_label(record: dict) -> str:
    """One line describing a series, as the chooser shows it."""
    identifier = str(record.get("id") or "")
    code = str(record.get("parameter_code") or "")
    name = str(record.get("parameter_name") or "")
    where = str(record.get("sublocation_identifier") or "")
    extent = f"{str(record.get('begin') or '')[:4]}–{str(record.get('end') or '')[:4]}"
    parts = [code, name]
    if where:
        parts.append(where)
    parts.append(extent)
    parts.append(identifier[:8] + "…")
    return "  ·  ".join(part for part in parts if part.strip(" ·–"))


class AddStationDialog(QDialog):
    def __init__(self, context: Context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.records: list[dict] = []
        self.runner: FunctionRunner | None = None
        self.setWindowTitle(context.pick("Станция қўшиш", "Add a station"))
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(w.paragraph(context.pick(
            "USGS сайт рақамини киритинг. Ойна архивдан ўша станциянинг барча "
            "қаторларини сўрайди — битта сўров, ҳеч нарса юкланмайди — ва "
            "детекторга керак бўлган тўрттасини таклиф қилади. Таклифни "
            "<b>сиз тасдиқлайсиз</b>: иккала бьеф сатҳи бир хил параметр коди "
            "остида берилади ва фақат эркин матнли белги билан ажралади, шунинг "
            "учун уларни алмаштириб юбориш Δh ишорасини жимгина ағдаради.",
            "Type a USGS site number. The window asks the archive what series that "
            "station publishes — one request, nothing downloaded — and proposes the "
            "four the detector needs. <b>You confirm the proposal</b>: the two "
            "stages are published under one parameter code and are told apart only "
            "by a free-text label, so getting them the wrong way round inverts Δh "
            "and nothing complains.",
        )))

        self.site = QLineEdit()
        self.site.setPlaceholderText(context.pick("USGS сайт рақами",
                                                  "a USGS site number"))
        self.site.setMinimumWidth(180)
        self.site.returnPressed.connect(self.look_up)
        self.look_button = QPushButton(context.pick("Қидириш", "Look up"))
        self.look_button.setObjectName("Primary")
        self.look_button.clicked.connect(self.look_up)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(context.pick("Сайт рақами", "Site number")))
        row.addWidget(self.site, 1)
        row.addWidget(self.look_button, 0)
        layout.addLayout(row)

        self.table = QPlainTextEdit()
        self.table.setObjectName("Console")
        self.table.setReadOnly(True)
        self.table.setMinimumHeight(150)
        self.table.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.table.setFont(QFont("Consolas", 9))
        self.table.setVisible(False)
        layout.addWidget(self.table)

        self.problems = w.paragraph("")
        self.problems.setStyleSheet(f"color: {COLORS['warn']};")
        self.problems.setVisible(False)
        layout.addWidget(self.problems)

        self.role_boxes = {role: w.combo([]) for role in ROLES}
        self.name = QLineEdit()
        self.name.setPlaceholderText(context.pick("станциянинг номи",
                                                  "the station's name"))
        self.first_year = QSpinBox()
        self.last_year = QSpinBox()
        for box in (self.first_year, self.last_year):
            box.setRange(1900, 2100)
            box.setEnabled(False)

        years_row = QWidget()
        years_row.setObjectName("Page")
        years_layout = QHBoxLayout(years_row)
        years_layout.setContentsMargins(0, 0, 0, 0)
        years_layout.setSpacing(8)
        years_layout.addWidget(self.first_year)
        years_layout.addWidget(QLabel("–"))
        years_layout.addWidget(self.last_year)
        years_layout.addStretch(1)

        self.form = w.form(
            [(context.pick(*ROLE_LABELS[role]), self.role_boxes[role])
             for role in ROLES]
            + [
                (context.pick("Номи", "Name"), self.name),
                (context.pick("Йиллар", "Years"), years_row),
            ],
            columns=1,
        )
        self.form.setVisible(False)
        layout.addWidget(self.form)

        self.years_note = w.paragraph("")
        self.years_note.setVisible(False)
        layout.addWidget(self.years_note)

        self.status = w.paragraph("")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert self.ok_button is not None
        self.ok_button.setText(context.pick("Қўшиш", "Add"))
        self.ok_button.setEnabled(False)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setText(context.pick("Бекор қилиш", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Connected once, here, rather than each time a lookup finishes: a second
        # look-up would otherwise leave two handlers on every box and the year
        # bounds would be recomputed twice for one click.
        for box in self.role_boxes.values():
            box.currentIndexChanged.connect(self._roles_changed)

    # -- looking up ----------------------------------------------------------------

    def look_up(self) -> None:
        context = self.context
        site = self.site.text().strip()
        if not site or self.runner is not None:
            return
        # Refused before the request, not after: the downloader will not accept
        # --series for a site it already carries, so an assignment made here would
        # be saved, ignored, and quietly disagree with the published one.
        if site in lab.registered_sites(context.paths):
            self.form.setVisible(False)
            self.ok_button.setEnabled(False)
            self._say(
                context.pick(
                    f"{site} рўйхатда аллақачон бор — унинг тўртта қатори "
                    f"тадқиқот томонидан аниқланган. Уни бу ердан қайта "
                    f"таърифлаб бўлмайди.",
                    f"{site} is already in the list; its four series were resolved "
                    f"by the study. It cannot be redefined here.",
                ),
                COLORS["warn"],
            )
            return
        self.look_button.setEnabled(False)
        self._say(context.pick("Сўралмоқда…", "Asking the archive…"),
                  COLORS["ink_soft"])
        runner = FunctionRunner(lab.lookup_station, context.paths, site)
        runner.done.connect(self._found)
        runner.failed.connect(self._not_found)
        self.runner = runner
        runner.start()

    def _not_found(self, message: str) -> None:
        self._finish_lookup()
        self._say(message, COLORS["fail"])

    def _finish_lookup(self) -> None:
        runner = self.runner
        self.runner = None
        if runner is not None:
            runner.wait()
            runner.deleteLater()
        self.look_button.setEnabled(True)

    def _found(self, answer) -> None:
        context = self.context
        self._finish_lookup()
        records, proposal, problems, _url, from_cache = answer
        self.records = list(records)

        header = (f"{'time_series_id':34}  {'pcode':6}  {'parameter':24}  "
                  f"{'sublocation':22}  {'unit':7}  {'primary':8}  begin       end")
        lines = [header]
        for record in sorted(self.records, key=lambda r: (
                str(r.get("parameter_code") or ""),
                str(r.get("sublocation_identifier") or ""))):
            lines.append(
                f"{str(record.get('id') or '')[:34]:34}  "
                f"{str(record.get('parameter_code') or ''):6}  "
                f"{str(record.get('parameter_name') or '')[:24]:24}  "
                f"{str(record.get('sublocation_identifier') or '')[:22]:22}  "
                f"{str(record.get('unit_of_measure') or ''):7}  "
                f"{str(record.get('primary') or '')[:8]:8}  "
                f"{str(record.get('begin') or '')[:10]:10}  "
                f"{str(record.get('end') or '')[:10]:10}"
            )
        self.table.setPlainText("\n".join(lines))
        self.table.setVisible(True)

        if not self.records:
            self.form.setVisible(False)
            self.problems.setVisible(False)
            self.ok_button.setEnabled(False)
            self._say(context.pick("Бу рақамда қатор топилмади.",
                                   "No time series at that number."), COLORS["fail"])
            return

        items = [(series_label(record), str(record.get("id") or ""))
                 for record in self.records]
        for role, box in self.role_boxes.items():
            box.clear()
            for label, value in items:
                box.addItem(label, value)
            wanted = proposal.get(role)
            index = box.findData(wanted) if wanted else -1
            box.setCurrentIndex(index if index >= 0 else 0)

        self.problems.setText("<br>".join("• " + problem for problem in problems))
        self.problems.setVisible(bool(problems))
        if not self.name.text().strip():
            self.name.setText(f"USGS {self.site.text().strip()}")
        self.form.setVisible(True)
        self.years_note.setVisible(True)
        self._roles_changed()
        self._say(
            context.pick(
                "Кэшдан ўқилди." if from_cache else "Архивдан олинди.",
                "Read from the cache." if from_cache else "Read from the archive.",
            ),
            COLORS["ink_soft"],
        )

    # -- the assignment ------------------------------------------------------------

    def chosen(self) -> dict[str, str]:
        return {role: str(box.currentData() or "")
                for role, box in self.role_boxes.items()}

    def _roles_changed(self, *_ignored) -> None:
        context = self.context
        chosen = self.chosen()
        distinct = len(set(chosen.values())) == len(ROLES) and all(chosen.values())
        years = lab.advertised_years(self.records, chosen) if distinct else ()
        for box in (self.first_year, self.last_year):
            box.setEnabled(bool(years))
        if years:
            for box, value in ((self.first_year, years[0]), (self.last_year, years[-1])):
                box.setRange(years[0], years[-1])
                box.setValue(value)
        self.ok_button.setEnabled(bool(years))
        if not distinct:
            self.years_note.setText(context.pick(
                "Тўртта рол тўртта <b>ҳар хил</b> қаторга тегишли бўлиши керак.",
                "The four roles must point at four <b>different</b> series.",
            ))
            return
        if not years:
            self.years_note.setText(context.pick(
                "Танланган тўртта қаторнинг эълон қилинган оралиқлари кесишмайди — "
                "бу станцияда улар бир вақтда мавжуд бўлмаган.",
                "The advertised extents of the four chosen series do not overlap: "
                "they were never all present at the same time here.",
            ))
            return
        self.years_note.setText(context.pick(
            f"Оралиқ {years[0]}–{years[-1]} — қаторларнинг <b>эълон қилинган</b> "
            f"бошланиш ва тугаш саналаридан. Бу юқори чегара, кафолат эмас: асосий "
            f"иншоотда затвор қатори 2007 йилдан бошланади деб ёзилган, аслида "
            f"сатҳлар 2017 гача йўқ. Юклаш ҳар йил учун нечта ўлчов ҳақиқатан "
            f"тўрттала қаторга эга бўлганини ёзиб боради.",
            f"The range {years[0]}–{years[-1]} comes from the <b>advertised</b> begin "
            f"and end of the chosen series. It is an upper bound, not a promise: at "
            f"the primary structure the gate series claims to begin in 2007 while "
            f"stage is absent until 2017. The fetch reports, year by year, how many "
            f"readings really carried all four.",
        ))

    def result_station(self) -> tuple[str, str, list[int], dict[str, str]]:
        site = self.site.text().strip()
        name = self.name.text().strip() or f"USGS {site}"
        years = list(range(self.first_year.value(), self.last_year.value() + 1))
        return site, name, years, self.chosen()

    def _say(self, text: str, colour: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {colour};")

    # -- lifecycle -----------------------------------------------------------------

    def accept(self) -> None:
        site, name, years, chosen = self.result_station()
        try:
            lab.write_station(self.context.paths, site, name, years, chosen)
        except OSError as error:
            self._say(f"{type(error).__name__}: {error}", COLORS["fail"])
            return
        super().accept()

    def done(self, code: int) -> None:
        runner = self.runner
        if runner is not None:
            runner.wait(3000)
            self.runner = None
        super().done(code)


def ask_for_a_station(context: Context, parent: QWidget | None = None) -> str:
    """Run the dialog. Returns the site number that was added, or ``""``."""
    dialog = AddStationDialog(context, parent)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_station()[0]
    return ""
