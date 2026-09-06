"""Laboratory page — the gate-law calculator.

Type an opening and two stages; get the discharge each of the two laws predicts, the
gap between them, and the detector statistic at that point. The inverse works too:
type the discharge you need and read off the opening each law asks for.

Two things this page refuses to do quietly. It will not pretend a number outside the
range the archive actually covers is a prediction — it says so. And it never invents
coefficients: if ``results/gate_law.json`` has not been built, the form stays empty
and says which file is missing.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from .. import lab
from .. import widgets as w
from ..theme import COLORS
from . import Context

NAV = ("7 · Затвор калькулятори", "7 · Gate calculator")

SWEEP_POINTS = 60


def build(context: Context) -> QWidget:
    return w.wrap_scroll(CalculatorPanel(context))


class CalculatorPanel(QWidget):
    def __init__(self, context: Context) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.context = context
        self.identified, self.ideal, problem = lab.laws_from_results(context.results)
        self.a_range, self.dh_range = lab.observed_range(context.results)
        self.sweep_rows: list[tuple] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(
            w.page_title(
                context.pick(
                    "Затвор қонуни калькулятори",
                    "Gate-law calculator",
                )
            )
        )
        layout.addWidget(
            w.page_lead(
                context.pick(
                    "Иккита қонун ёнма-ён: архивдан <b>идентификация қилинган</b> ва "
                    "эталоннинг <b>идеаллаштирилган</b> қонуни. Иккови бир хил "
                    "остонада, шунинг учун фарқ фақат кўрсаткичлардан келади.",
                    "Two laws side by side: the one <b>identified</b> from the archive and "
                    "the benchmark's <b>idealised</b> one. Both sit on the same sill, so "
                    "the gap between them comes only from the exponents.",
                )
            )
        )

        if problem:
            card = w.Card(context.pick("Қонунлар ўқилмади", "The laws could not be read"))
            card.add(w.paragraph(problem))
            card.add(
                w.paragraph(
                    context.pick(
                        "«Қайта юритиш» саҳифасидан `identify_gate_law.py` ни юритинг.",
                        "Run `identify_gate_law.py` from the “Reproduce” page.",
                    )
                )
            )
            layout.addWidget(card)
            return

        layout.addWidget(self._laws_card())
        layout.addWidget(self._input_card())
        layout.addWidget(self._output_card())
        layout.addWidget(self._sweep_card())
        self._recompute()

    # -- the two laws ------------------------------------------------------------

    def _laws_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick("Ишлатилаётган иккита қонун", "The two laws in use"),
            context.pick(
                "Q = Γ · a<sup>α</sup> · Δh<sup>β</sup>, бунда Δh = H₁ − H₂. "
                "Коэффициентлар қўлда киритилмаган — улар натижа файлидан ўқилади.",
                "Q = Γ · a<sup>α</sup> · Δh<sup>β</sup>, with Δh = H₁ − H₂. The "
                "coefficients are not typed in: they are read from the result file.",
            ),
        )
        card.add(
            w.key_values(
                [
                    (
                        context.pick("Идентификация қилинган", "Identified"),
                        f"Γ = {self.identified.gamma:.4f}   "
                        f"α = {self.identified.alpha:.6f}   "
                        f"β = {self.identified.beta:.6f}",
                    ),
                    (
                        context.pick("Идеал (ASCE)", "Ideal (ASCE)"),
                        f"Γ = {self.ideal.gamma:.4f}   α = 1   β = 0.5",
                    ),
                    (
                        context.pick("Манба", "Source"),
                        "results/gate_law.json → full_fit, ideal_law_same_sill",
                    ),
                ],
                columns=1,
            )
        )
        return card

    # -- input -------------------------------------------------------------------

    def _input_card(self) -> QWidget:
        context = self.context
        card = w.Card(context.pick("Киритиш", "Input"))

        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        self.forward = QRadioButton(
            context.pick("a, H₁, H₂ берилган → Q", "given a, H₁, H₂ → Q")
        )
        self.inverse = QRadioButton(
            context.pick("Q, H₁, H₂ берилган → a", "given Q, H₁, H₂ → a")
        )
        self.forward.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.forward)
        group.addButton(self.inverse)
        self.forward.toggled.connect(self._mode_changed)
        mode_row.addWidget(self.forward)
        mode_row.addWidget(self.inverse)
        mode_row.addStretch(1)
        card.add_layout(mode_row)

        self.length_unit = w.combo([(label, factor) for _k, label, factor in lab.LENGTH_UNITS])
        self.flow_unit = w.combo([(label, factor) for _k, label, factor in lab.FLOW_UNITS])
        self.length_unit.currentIndexChanged.connect(self._recompute)
        self.flow_unit.currentIndexChanged.connect(self._recompute)

        self.opening = w.spin(1.30, 0.0, 100.0, 4, 0.05)
        self.headwater = w.spin(2.10, 0.0, 1000.0, 4, 0.05)
        # Defaults sit inside the range the archive actually covers, so the page
        # does not open already warning about extrapolation.
        self.tailwater = w.spin(1.30, 0.0, 1000.0, 4, 0.05)
        self.target_q = w.spin(11.0, 0.0, 100000.0, 4, 0.5)
        self.target_q.setEnabled(False)
        for box in (self.opening, self.headwater, self.tailwater, self.target_q):
            box.valueChanged.connect(self._recompute)

        card.add(
            w.form(
                [
                    (context.pick("Узунлик бирлиги", "Length unit"), self.length_unit),
                    (context.pick("Сарф бирлиги", "Discharge unit"), self.flow_unit),
                    (context.pick("Затвор очилиши a", "Gate opening a"), self.opening),
                    (context.pick("Юқори бьеф H₁", "Headwater H₁"), self.headwater),
                    (context.pick("Қуйи бьеф H₂", "Tailwater H₂"), self.tailwater),
                    (context.pick("Керакли сарф Q", "Required discharge Q"), self.target_q),
                ],
                columns=2,
            )
        )
        return card

    def _mode_changed(self) -> None:
        forward = self.forward.isChecked()
        self.opening.setEnabled(forward)
        self.target_q.setEnabled(not forward)
        self._recompute()

    # -- output ------------------------------------------------------------------

    def _output_card(self) -> QWidget:
        context = self.context
        self.output_card = w.Card(context.pick("Натижа", "Result"))
        self.output_body = QVBoxLayout()
        self.output_body.setSpacing(12)
        self.output_card.add_layout(self.output_body)

        self.warning = w.paragraph("")
        self.warning.setStyleSheet(f"color: {COLORS['warn']}; font-weight: 600;")
        self.output_card.add(self.warning)
        return self.output_card

    def _clear_output(self) -> None:
        while self.output_body.count():
            item = self.output_body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    # -- sweep -------------------------------------------------------------------

    def _sweep_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick(
                "Бутун диапазон бўйича — иккита қонун қаерда ажралади",
                "Across the range — where the two laws part company",
            ),
            context.pick(
                "Ҳозирги Δh да, затвор очилиши бўйича. Соя — архивда кузатилган "
                "очилиш диапазони; ундан ташқарида иккала қонун ҳам экстраполяция.",
                "At the current Δh, against gate opening. The shaded band is the opening "
                "range the archive actually contains; outside it both laws extrapolate.",
            ),
        )
        self.chart = w.Chart(300)
        card.add(self.chart)

        self.sweep_table = w.QTableWidget(0, 4)
        self.sweep_table.setHorizontalHeaderLabels(["a", "Q identified", "Q ideal", "Δ %"])
        self.sweep_table.verticalHeader().setVisible(False)
        self.sweep_table.setMaximumHeight(220)
        card.add(self.sweep_table)

        row = QHBoxLayout()
        row.addStretch(1)
        save = QPushButton(context.pick("Жадвални CSV га сақлаш", "Save the table as CSV"))
        save.setObjectName("Link")
        save.clicked.connect(self.save_csv)
        row.addWidget(save)
        card.add_layout(row)
        return card

    # -- computation -------------------------------------------------------------

    def _recompute(self) -> None:
        context = self.context
        length_factor = float(self.length_unit.currentData())
        flow_factor = float(self.flow_unit.currentData())
        length_label = self.length_unit.currentText()
        flow_label = self.flow_unit.currentText()

        h1 = self.headwater.value() * length_factor
        h2 = self.tailwater.value() * length_factor
        dh = h1 - h2

        self._clear_output()
        if dh <= 0:
            self.output_body.addWidget(
                w.paragraph(
                    context.pick(
                        "Δh = H₁ − H₂ мусбат бўлиши керак. Тескари напорда бу қонун "
                        "ишламайди, ва архивда ҳам саккиз йилда атиги 38 марта учрайди.",
                        "Δh = H₁ − H₂ has to be positive. Neither law applies under a "
                        "reversed head, and the archive contains only 38 such readings in "
                        "eight years.",
                    )
                )
            )
            self.warning.setText("")
            self._clear_chart()
            return

        if self.forward.isChecked():
            a = self.opening.value() * length_factor
            q_identified = self.identified.discharge(a, dh)
            q_ideal = self.ideal.discharge(a, dh)
            cards = self._forward_cards(a, dh, q_identified, q_ideal,
                                        length_factor, flow_factor,
                                        length_label, flow_label)
        else:
            q = self.target_q.value() * flow_factor
            a_identified = self.identified.opening_for(q, dh)
            a_ideal = self.ideal.opening_for(q, dh)
            a = a_identified
            cards = self._inverse_cards(q, dh, a_identified, a_ideal,
                                        length_factor, length_label)

        self.output_body.addWidget(w.card_row(cards, columns=len(cards)))
        self._set_warning(a, dh, length_factor, length_label)
        self._refresh_sweep(dh, length_factor, flow_factor, length_label, flow_label)

    def _forward_cards(self, a, dh, q_identified, q_ideal,
                       length_factor, flow_factor, length_label, flow_label):
        context = self.context
        gap = ((q_identified - q_ideal) / q_ideal * 100.0) if q_ideal else float("nan")
        kappa = lab.kappa_of(q_identified, a, dh)
        return [
            w.NumberCard(
                f"{lab.from_si(q_identified, flow_factor):,.3f}".replace(",", " "),
                context.pick(
                    f"идентификация қилинган қонун бўйича Q, {flow_label}",
                    f"Q from the identified law, {flow_label}",
                ),
                "results/gate_law.json → full_fit",
                tone="accent",
            ),
            w.NumberCard(
                f"{lab.from_si(q_ideal, flow_factor):,.3f}".replace(",", " "),
                context.pick(
                    f"идеал қонун бўйича Q, {flow_label}",
                    f"Q from the ideal law, {flow_label}",
                ),
                "results/gate_law.json → ideal_law_same_sill",
                tone="measured",
            ),
            w.NumberCard(
                f"{gap:+.3f}%",
                context.pick(
                    "иккита қонуннинг фарқи шу нуқтада",
                    "the gap between the two laws at this point",
                ),
                context.pick(
                    "ҳисобланди: (Q_ид − Q_идеал) ⁄ Q_идеал",
                    "computed: (Q_identified − Q_ideal) ⁄ Q_ideal",
                ),
                tone="circular" if abs(gap) > 1.0 else "ink",
            ),
            w.NumberCard(
                f"{kappa:.4f}" if kappa else "—",
                context.pick(
                    "κ = Q ⁄ (a·√(2g·Δh)), м — детекторнинг статистикаси",
                    "κ = Q ⁄ (a·√(2g·Δh)) in metres — the detector statistic",
                ),
                context.pick("ҳисобланди", "computed"),
            ),
        ]

    def _inverse_cards(self, q, dh, a_identified, a_ideal, length_factor, length_label):
        context = self.context
        gap = ((a_identified - a_ideal) / a_ideal * 100.0) if a_ideal else float("nan")
        return [
            w.NumberCard(
                f"{lab.from_si(a_identified, length_factor):,.4f}".replace(",", " "),
                context.pick(
                    f"идентификация қилинган қонун сўраган очилиш, {length_label}",
                    f"opening the identified law asks for, {length_label}",
                ),
                "results/gate_law.json → full_fit",
                tone="accent",
            ),
            w.NumberCard(
                f"{lab.from_si(a_ideal, length_factor):,.4f}".replace(",", " "),
                context.pick(
                    f"идеал қонун сўраган очилиш, {length_label}",
                    f"opening the ideal law asks for, {length_label}",
                ),
                "results/gate_law.json → ideal_law_same_sill",
                tone="measured",
            ),
            w.NumberCard(
                f"{gap:+.3f}%",
                context.pick(
                    "иккита қонун сўраган очилишнинг фарқи — бошқарувчи кўтарадиган хато "
                    "айнан шу",
                    "the gap in the opening each law asks for — this is the error a "
                    "controller carries",
                ),
                context.pick(
                    "ҳисобланди: (a_ид − a_идеал) ⁄ a_идеал",
                    "computed: (a_identified − a_ideal) ⁄ a_ideal",
                ),
                tone="circular" if abs(gap) > 1.0 else "ink",
            ),
        ]

    def _set_warning(self, a, dh, length_factor, length_label) -> None:
        context = self.context
        outside = []
        if self.a_range and not (self.a_range[0] <= a <= self.a_range[1]):
            lo = lab.from_si(self.a_range[0], length_factor)
            hi = lab.from_si(self.a_range[1], length_factor)
            outside.append(
                context.pick(
                    f"очилиш архивдаги диапазондан ташқарида "
                    f"({lo:.3f} … {hi:.3f} {length_label})",
                    f"the opening is outside the range the archive contains "
                    f"({lo:.3f} … {hi:.3f} {length_label})",
                )
            )
        if self.dh_range and not (self.dh_range[0] <= dh <= self.dh_range[1]):
            lo = lab.from_si(self.dh_range[0], length_factor)
            hi = lab.from_si(self.dh_range[1], length_factor)
            outside.append(
                context.pick(
                    f"напор фарқи архивдаги диапазондан ташқарида "
                    f"({lo:.3f} … {hi:.3f} {length_label})",
                    f"the head difference is outside the range the archive contains "
                    f"({lo:.3f} … {hi:.3f} {length_label})",
                )
            )
        if outside:
            self.warning.setText(
                context.pick("Экстраполяция: ", "Extrapolating: ") + "; ".join(outside)
            )
        else:
            self.warning.setText("")

    # -- sweep -------------------------------------------------------------------

    def _clear_chart(self) -> None:
        axes = self.chart.axes()
        if axes is not None:
            self.chart.draw()
        self.sweep_table.setRowCount(0)
        self.sweep_rows = []

    def _refresh_sweep(self, dh, length_factor, flow_factor,
                       length_label, flow_label) -> None:
        lo, hi = (self.a_range if self.a_range else (0.05, 2.3))
        span = hi - lo
        start = max(1e-4, lo - 0.15 * span)
        stop = hi + 0.15 * span
        step = (stop - start) / (SWEEP_POINTS - 1)

        openings, identified, ideal, gaps = [], [], [], []
        for index in range(SWEEP_POINTS):
            a = start + index * step
            q_id = self.identified.discharge(a, dh)
            q_ideal = self.ideal.discharge(a, dh)
            openings.append(a)
            identified.append(q_id)
            ideal.append(q_ideal)
            gaps.append((q_id - q_ideal) / q_ideal * 100.0 if q_ideal else float("nan"))

        self.sweep_rows = [
            (
                lab.from_si(a, length_factor),
                lab.from_si(q_id, flow_factor),
                lab.from_si(q_ideal, flow_factor),
                gap,
            )
            for a, q_id, q_ideal, gap in zip(openings, identified, ideal, gaps)
        ]

        self.sweep_table.setHorizontalHeaderLabels(
            [
                f"a, {length_label}",
                f"Q identified, {flow_label}",
                f"Q ideal, {flow_label}",
                "Δ %",
            ]
        )
        shown = self.sweep_rows[:: max(1, SWEEP_POINTS // 12)]
        self.sweep_table.setRowCount(len(shown))
        for row_index, row in enumerate(shown):
            for column, value in enumerate(row):
                item = w.QTableWidgetItem(f"{value:,.4f}".replace(",", " "))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.sweep_table.setItem(row_index, column, item)
        self.sweep_table.resizeColumnsToContents()

        axes = self.chart.axes()
        if axes is None:
            return
        xs = [lab.from_si(a, length_factor) for a in openings]
        axes.plot(xs, [lab.from_si(q, flow_factor) for q in identified],
                  color=COLORS["accent"], linewidth=2.0,
                  label=self.context.pick("идентификация қилинган", "identified"))
        axes.plot(xs, [lab.from_si(q, flow_factor) for q in ideal],
                  color=COLORS["measured"], linewidth=1.6, linestyle="--",
                  label=self.context.pick("идеал (ASCE)", "ideal (ASCE)"))
        if self.a_range:
            axes.axvspan(lab.from_si(self.a_range[0], length_factor),
                         lab.from_si(self.a_range[1], length_factor),
                         color=COLORS["accent"], alpha=0.07)
        axes.set_xlabel(f"a, {length_label}", fontsize=9, color=COLORS["ink_soft"])
        axes.set_ylabel(f"Q, {flow_label}", fontsize=9, color=COLORS["ink_soft"])
        axes.legend(frameon=False, fontsize=9)
        self.chart.draw()

    # -- saving ------------------------------------------------------------------

    def save_csv(self) -> None:
        context = self.context
        if not self.sweep_rows:
            return
        default = lab.lab_directory(context.paths) / lab.stamped("gate_sweep", ".csv")
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            context.pick("Жадвални сақлаш", "Save the table"),
            str(default),
            "CSV (*.csv)",
        )
        if not chosen:
            return
        header = [
            self.sweep_table.horizontalHeaderItem(i).text()
            for i in range(self.sweep_table.columnCount())
        ]
        path = lab.write_csv(Path(chosen), header, self.sweep_rows)
        QMessageBox.information(
            self,
            context.pick("Сақланди", "Saved"),
            context.pick(f"Ёзилди: {path}", f"Written to {path}"),
        )
