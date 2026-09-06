"""Laboratory page — run the circularity detector on a structure of your own.

This is the paper's method rather than the paper's result: point it at a site-year in
the data package, or at your own file of readings, and it answers the same question by
the same rule — is this published discharge a measurement, or the output of a rating?

The thresholds are on screen and editable, because a verdict is only meaningful next
to the numbers it was judged by. They start at the values fixed before the study's own
measurement; changing them is allowed and is recorded in the saved result.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from .. import data as gdata
from .. import lab
from .. import widgets as w
from ..theme import COLORS
from ..workers import FunctionRunner
from . import Context

#: How each branch of the pre-registered rule is coloured and named.
BRANCH_STYLE = {
    "same_form": ("circular", "Доиравийлик — айнан ўша шаклда",
                  "Circular — in the same form"),
    "different_form": ("circular", "Доиравийлик — бошқа шаклда",
                       "Circular — in a different form"),
    "not_a_rating": ("measured", "Рейтингга ўхшамайди",
                     "Does not look like a rating"),
}
H5B_STYLE = {
    "structured": ("circular", "Қолдиқ тузилган", "The residual is structured"),
    "unstructured": ("measured", "Қолдиқ шовқин", "The residual is scatter"),
    "ambiguous": ("warn", "Аниқ эмас", "Inconclusive"),
}


def build(context: Context) -> QWidget:
    panel = DetectorPanel(context)
    area = w.wrap_scroll(panel)
    area.shutdown = panel.shutdown  # type: ignore[attr-defined]
    area.controller = panel  # type: ignore[attr-defined]
    return area


class DetectorPanel(QWidget):
    def __init__(self, context: Context) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.context = context
        self.runner: FunctionRunner | None = None
        self.result: dict | None = None
        self.source_label = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(
            w.page_title(
                context.pick(
                    "Ўз иншоотингизда доиравийликни текширинг",
                    "Test your own structure for the circularity",
                )
            )
        )
        layout.addWidget(
            w.page_lead(
                context.pick(
                    "Керак бўладиган нарса: битта иншоотда бир вақтда ўлчанган тўртта "
                    "қатор — затвор очилиши, юқори ва қуйи бьеф сатҳлари, ва эълон "
                    "қилинган сарф. Ҳисоблашни <code>gatempc.detector</code> бажаради — "
                    "мақоладаги натижани чиқарган айнан ўша код.",
                    "What it needs: four series measured together at one structure — the "
                    "gate opening, the two stages and the published discharge. The "
                    "computation is done by <code>gatempc.detector</code>, the same code "
                    "that produced the study's own result.",
                )
            )
        )

        layout.addWidget(self._source_card())
        layout.addWidget(self._thresholds_card())
        layout.addWidget(self._run_card())
        self.verdict_card = self._verdict_card()
        layout.addWidget(self.verdict_card)
        self.detail_card = w.Card(context.pick("Тафсилот", "Detail"))
        self.detail_body = QVBoxLayout()
        self.detail_body.setSpacing(12)
        self.detail_card.add_layout(self.detail_body)
        layout.addWidget(self.detail_card)
        self.chart = w.Chart(280)
        chart_card = w.Card(
            context.pick(
                "Қолдиқ предикторлар бўйича — тузилиш кўзга кўринадими?",
                "The residual against the predictors — is the structure visible?",
            )
        )
        chart_card.add(self.chart)
        layout.addWidget(chart_card)
        self._mode_changed()

    # -- source ------------------------------------------------------------------

    def _source_card(self) -> QWidget:
        context = self.context
        card = w.Card(context.pick("Маълумот манбаи", "Where the readings come from"))

        row = QHBoxLayout()
        row.setSpacing(16)
        self.from_package = QRadioButton(
            context.pick("Маълумот тўпламидан", "From the data package")
        )
        self.from_file = QRadioButton(context.pick("Ўз файлимдан", "From my own file"))
        self.from_package.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.from_package)
        group.addButton(self.from_file)
        self.from_package.toggled.connect(self._mode_changed)
        row.addWidget(self.from_package)
        row.addWidget(self.from_file)
        row.addStretch(1)
        card.add_layout(row)

        # -- package
        available = lab.package_site_years(context.paths)
        self.site_year = w.combo(
            [(f"{site}  ·  {year}", (site, year)) for site, year in available]
        )
        self.package_note = w.paragraph("")
        if not available:
            self.package_note.setText(
                context.pick(
                    "Маълумот тўплами топилмади. «Қайта юритиш» саҳифасидан "
                    "`download_usgs.py` ни юритинг, ёки бошқа сайтни олиш учун "
                    "қуйидаги майдонга сайт рақамини ёзинг.",
                    "No data package was found. Run `download_usgs.py` from the "
                    "“Reproduce” page, or type a site number below to fetch another one.",
                )
            )

        self.new_site = QLineEdit()
        self.new_site.setPlaceholderText(
            context.pick(
                "бошқа USGS сайт рақами, масалан 09429000",
                "another USGS site number, for example 09429000",
            )
        )
        self.new_site.setMinimumWidth(150)
        fetch = QPushButton(context.pick("Юклаб олиш…", "Fetch…"))
        fetch.clicked.connect(self._explain_fetch)

        fetch_row = QWidget()
        fetch_row.setObjectName("Page")
        fetch_layout = QHBoxLayout(fetch_row)
        fetch_layout.setContentsMargins(0, 0, 0, 0)
        fetch_layout.setSpacing(8)
        fetch_layout.addWidget(self.new_site, 1)
        fetch_layout.addWidget(fetch, 0)

        # -- own file
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText(
            context.pick("CSV файл танланмаган", "no CSV chosen")
        )
        self.file_path.setReadOnly(True)
        browse = QPushButton(context.pick("Танлаш…", "Choose…"))
        browse.clicked.connect(self.choose_file)
        file_row = QWidget()
        file_row.setObjectName("Page")
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(8)
        file_layout.addWidget(self.file_path, 1)
        file_layout.addWidget(browse, 0)

        self.column_time = w.combo([])
        self.column_a = w.combo([])
        self.column_h1 = w.combo([])
        self.column_h2 = w.combo([])
        self.column_q = w.combo([])
        self.file_length_unit = w.combo(
            [(label, factor) for _k, label, factor in lab.LENGTH_UNITS]
        )
        self.file_flow_unit = w.combo(
            [(label, factor) for _k, label, factor in lab.FLOW_UNITS]
        )

        self.package_form = w.form(
            [
                (context.pick("Сайт ва йил", "Site and year"), self.site_year),
                (context.pick("Тўпламда йўқ сайт", "A site not in the package"), fetch_row),
            ],
            columns=1,
        )
        self.file_form = w.form(
            [
                (context.pick("Файл", "File"), file_row),
                (context.pick("Вақт устуни", "Time column"), self.column_time),
                (context.pick("Затвор очилиши a", "Gate opening a"), self.column_a),
                (context.pick("Юқори бьеф H₁", "Headwater H₁"), self.column_h1),
                (context.pick("Қуйи бьеф H₂", "Tailwater H₂"), self.column_h2),
                (context.pick("Сарф Q", "Discharge Q"), self.column_q),
                (context.pick("Узунлик бирлиги", "Length unit"), self.file_length_unit),
                (context.pick("Сарф бирлиги", "Discharge unit"), self.file_flow_unit),
            ],
            columns=2,
        )
        card.add(self.package_form)
        card.add(self.package_note)
        card.add(self.file_form)
        card.add(
            w.paragraph(
                context.pick(
                    "Файл 15 дақиқалик тўрда бўлиши шарт эмас, лекин вақт устуни "
                    "<code>ГГГГ-ОО-КК</code> билан бошланиши керак — кунлик "
                    "гуруҳлаш шунга таянади.",
                    "The file need not be on a 15-minute grid, but the time column has to "
                    "start with <code>YYYY-MM-DD</code>: the daily grouping relies on it.",
                )
            )
        )
        return card

    def _mode_changed(self) -> None:
        from_package = self.from_package.isChecked()
        self.package_form.setVisible(from_package)
        self.package_note.setVisible(from_package and bool(self.package_note.text()))
        self.file_form.setVisible(not from_package)

    def choose_file(self) -> None:
        context = self.context
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            context.pick("Ўлчовлар файлини танланг", "Choose a file of readings"),
            str(context.paths.root),
            "CSV (*.csv);;All files (*)",
        )
        if not chosen:
            return
        self.file_path.setText(chosen)
        try:
            header = lab.csv_header(Path(chosen))
        except OSError as error:
            QMessageBox.warning(self, context.pick("Ўқилмади", "Could not read"), str(error))
            return
        guesses = {
            self.column_time: ("time", "date", "вақт", "timestamp"),
            self.column_a: ("gate", "opening", "a"),
            self.column_h1: ("head", "upstream", "h1"),
            self.column_h2: ("tail", "downstream", "h2"),
            self.column_q: ("discharge", "flow", "q"),
        }
        for box, hints in guesses.items():
            box.clear()
            for name in header:
                box.addItem(name, name)
            for index, name in enumerate(header):
                if any(hint in name.lower() for hint in hints):
                    box.setCurrentIndex(index)
                    break

    def _explain_fetch(self) -> None:
        context = self.context
        site = self.new_site.text().strip()
        if not site:
            return
        command = (f"python scripts/download_usgs.py --sites {site} "
                   f"--out build/lab/package_{site}")
        QMessageBox.information(
            self,
            context.pick("Сайтни юклаб олиш", "Fetching a site"),
            context.pick(
                "Янги сайтни юклаш тармоққа мурожаат қилади ва USGS квотасини "
                "сарфлайди, шунинг учун у ойнадан жимгина бажарилмайди. Қуйидаги "
                "буйруқни юритинг, кейин тўплам папкаси сифатида ўша йўлни "
                "кўрсатинг:\n\n"
                f"{command}\n\n"
                "Юклаб бўлингач, бу саҳифани қайта очинг.",
                "Fetching a new site goes to the network and spends USGS quota, so the "
                "window does not do it silently. Run this command, then point the package "
                "directory at that path:\n\n"
                f"{command}\n\n"
                "Reopen this page once it has finished.",
            ),
        )

    # -- thresholds --------------------------------------------------------------

    def _thresholds_card(self) -> QWidget:
        context = self.context
        from ...detector import BINS, KAPPA_TIGHT, RATING_TIGHT

        card = w.Card(
            context.pick("Ҳукм чиқарувчи остоналар", "The thresholds the verdict uses"),
            context.pick(
                "Бошланғич қийматлар — тадқиқотнинг ўз ўлчовидан ОЛДИН ёзилганлари. "
                "Ўзгартирсангиз, сақланган натижа айнан сиз қўйган қийматларни "
                "кўрсатади.",
                "The starting values are the ones written down BEFORE the study's own "
                "measurement. If you change them, the saved result carries the values you "
                "actually used.",
            ),
        )
        self.kappa_tight = w.spin(KAPPA_TIGHT * 100, 0.0001, 100.0, 4, 0.01, "%")
        self.rating_tight = w.spin(RATING_TIGHT * 100, 0.0001, 100.0, 4, 0.1, "%")
        self.bins = w.integer_spin(BINS, 2, 50, 1)
        card.add(
            w.form(
                [
                    (
                        context.pick(
                            "κ тарқалиши бундан кичик бўлса — «айнан ўша шакл»",
                            "κ spread below this means “the same form”",
                        ),
                        self.kappa_tight,
                    ),
                    (
                        context.pick(
                            "рейтинг қолдиғи бундан кичик бўлса — «бошқа шакл»",
                            "rating residual below this means “a different form”",
                        ),
                        self.rating_tight,
                    ),
                    (
                        context.pick("тузилиш тести учун бинлар", "bins for the structure test"),
                        self.bins,
                    ),
                ],
                columns=1,
            )
        )
        return card

    # -- run ---------------------------------------------------------------------

    def _run_card(self) -> QWidget:
        context = self.context
        card = w.Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        self.run_button = QPushButton(context.pick("Текширишни бошлаш", "Run the detector"))
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run)
        row.addWidget(self.run_button)

        self.save_button = QPushButton(context.pick("Натижани сақлаш…", "Save the result…"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)

        self.status = w.paragraph("")
        row.addWidget(self.status, 1)
        card.add_layout(row)
        return card

    def run(self) -> None:
        context = self.context
        from ...detector import Thresholds, analyse

        thresholds = Thresholds(
            kappa_tight=self.kappa_tight.value() / 100.0,
            rating_tight=self.rating_tight.value() / 100.0,
            bins=self.bins.value(),
        )
        try:
            samples, approved, label, note = self._samples()
        except Exception as error:
            self._say(f"{type(error).__name__}: {error}", COLORS["fail"])
            return
        self.source_label = label
        self._say(
            note or context.pick("Ҳисобланмоқда…", "Computing…"), COLORS["ink_soft"]
        )
        self.run_button.setEnabled(False)
        runner = FunctionRunner(analyse, samples, approved, thresholds)
        runner.done.connect(self._finished)
        runner.failed.connect(self._failed)
        self.runner = runner
        runner.start()

    def _samples(self):
        context = self.context
        if self.from_package.isChecked():
            chosen = self.site_year.currentData()
            if not chosen:
                raise RuntimeError(
                    context.pick(
                        "Маълумот тўпламида сайт-йил файли йўқ.",
                        "The data package holds no site-year file.",
                    )
                )
            from ...archive import load_fold

            site, year = chosen
            samples, approvals = load_fold(str(context.paths.data_package), site, year,
                                           with_approval=True)
            approved = [s for s, flag in zip(samples, approvals) if flag]
            return samples, approved, f"{site} {year}", ""

        path = self.file_path.text().strip()
        if not path:
            raise RuntimeError(
                context.pick("Аввал файл танланг.", "Choose a file first.")
            )
        mapping = {
            "time": self.column_time.currentText(),
            "a": self.column_a.currentText(),
            "h1": self.column_h1.currentText(),
            "h2": self.column_h2.currentText(),
            "q": self.column_q.currentText(),
        }
        samples, skipped = lab.samples_from_csv(
            Path(path), mapping,
            float(self.file_length_unit.currentData()),
            float(self.file_flow_unit.currentData()),
        )
        note = ""
        if skipped:
            note = context.pick(
                f"{skipped} сатр тўлиқ эмаслиги учун ташланди.",
                f"{skipped} rows were skipped as incomplete.",
            )
        return samples, [], Path(path).name, note

    def _failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self._say(message, COLORS["fail"])

    def _finished(self, result: dict) -> None:
        self.run_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.result = result
        self._say(
            self.context.pick(
                f"Тайёр — {self.source_label}, "
                f"{result['n_four_series']:,} нуқта".replace(",", " "),
                f"Done — {self.source_label}, "
                f"{result['n_four_series']:,} points".replace(",", " "),
            ),
            COLORS["measured"],
        )
        self._show_verdict(result)
        self._show_detail(result)
        self._show_chart(result)

    def _say(self, text: str, colour: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {colour};")

    # -- output ------------------------------------------------------------------

    def _verdict_card(self) -> QWidget:
        card = w.Card(self.context.pick("Ҳукм", "Verdict"))
        self.verdict_body = QVBoxLayout()
        self.verdict_body.setSpacing(10)
        card.add_layout(self.verdict_body)
        self.verdict_body.addWidget(
            w.paragraph(
                self.context.pick(
                    "Ҳали текширилмади.",
                    "Nothing has been tested yet.",
                )
            )
        )
        return card

    def _show_verdict(self, result: dict) -> None:
        context = self.context
        while self.verdict_body.count():
            item = self.verdict_body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        branch = str(result.get("branch", ""))
        tone, uzbek, english = BRANCH_STYLE.get(branch, ("ink", branch, branch))
        heading = w.section_title(context.pick(uzbek, english))
        heading.setStyleSheet(f"color: {COLORS[tone]};")
        self.verdict_body.addWidget(heading)
        self.verdict_body.addWidget(w.paragraph(str(result.get("verdict", ""))))

        h5b = result.get("h5b", {})
        b_tone, b_uz, b_en = H5B_STYLE.get(str(h5b.get("branch", "")),
                                           ("ink", "", ""))
        if b_uz:
            second = w.section_title(context.pick(b_uz, b_en))
            second.setStyleSheet(f"color: {COLORS[b_tone]};")
            self.verdict_body.addWidget(second)
            self.verdict_body.addWidget(w.paragraph(str(h5b.get("verdict", ""))))

    def _show_detail(self, result: dict) -> None:
        context = self.context
        while self.detail_body.count():
            item = self.detail_body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        kappa = result.get("kappa_all") or {}
        rating = result.get("rating_fit") or {}
        structure = (result.get("h5b") or {}).get("structure") or {}
        cards = [
            w.NumberCard(
                gdata.as_percent(kappa.get("spread_iqr_over_median"), 3),
                context.pick("κ нинг тарқалиши (IQR ⁄ медиана)", "κ spread (IQR ⁄ median)"),
                context.pick("ҳисобланди", "computed"),
                tone="circular",
            ),
            w.NumberCard(
                gdata.as_percent(kappa.get("typical_complete_day_deviation"), 4),
                context.pick(
                    f"типик тўлиқ куннинг четланиши ({kappa.get('complete_days', 0)} кун)",
                    f"typical complete day deviates ({kappa.get('complete_days', 0)} days)",
                ),
                context.pick("ҳисобланди", "computed"),
            ),
            w.NumberCard(
                gdata.as_percent(rating.get("median_abs_relative_residual"), 3),
                context.pick(
                    "рейтинг мослигининг медиана |қолдиқ| и",
                    "median |residual| of the rating fit",
                ),
                context.pick("ҳисобланди", "computed"),
                tone="circular",
            ),
            w.NumberCard(
                f"{structure.get('a', {}).get('ratio_to_median_abs_residual', float('nan')):.2f}",
                context.pick("a бўйича тузилиш нисбати", "structure ratio across a"),
                context.pick("мезон: >1.0 — тузилган", "criterion: above 1.0 is structured"),
            ),
            w.NumberCard(
                f"{structure.get('dh', {}).get('ratio_to_median_abs_residual', float('nan')):.2f}",
                context.pick("Δh бўйича тузилиш нисбати", "structure ratio across Δh"),
                context.pick("мезон: >1.0 — тузилган", "criterion: above 1.0 is structured"),
            ),
            w.NumberCard(
                f"{rating.get('c0', 0):+.4f} / {rating.get('c1_dh', 0):+.4f} / "
                f"{rating.get('c2_a', 0):+.4f}",
                context.pick(
                    "мосликнинг коэффициентлари c₀ / c₁(log Δh) / c₂(log a)",
                    "fit coefficients c₀ / c₁(log Δh) / c₂(log a)",
                ),
                context.pick("ҳисобланди", "computed"),
            ),
        ]
        self.detail_body.addWidget(w.card_row(cards, columns=3))

    def _show_chart(self, result: dict) -> None:
        axes = self.chart.axes()
        if axes is None:
            return
        structure = (result.get("h5b") or {}).get("structure") or {}
        colours = {"a": COLORS["accent"], "dh": COLORS["circular"]}
        for name in ("a", "dh"):
            bins = (structure.get(name) or {}).get("bins") or []
            if not bins:
                continue
            centres = [(b["x_lo"] + b["x_hi"]) / 2 for b in bins]
            medians = [100 * b["median_residual"] for b in bins]
            # Bin centres of the two predictors are on different scales, so each is
            # drawn against its own position in the bin order rather than its value.
            axes.plot(range(1, len(centres) + 1), medians, marker="o",
                      color=colours[name], linewidth=1.8,
                      label=f"binned by {name}")
        axes.axhline(0.0, color=COLORS["ink_faint"], linewidth=1.0)
        axes.set_xlabel(self.context.pick("бин (тенг сонли)", "bin (equal count)"),
                        fontsize=9, color=COLORS["ink_soft"])
        axes.set_ylabel(self.context.pick("медиана қолдиқ, %", "median residual, %"),
                        fontsize=9, color=COLORS["ink_soft"])
        axes.legend(frameon=False, fontsize=9)
        self.chart.draw()

    # -- saving ------------------------------------------------------------------

    def save(self) -> None:
        import json

        context = self.context
        if self.result is None:
            return
        stem = self.source_label.replace(" ", "_").replace(".", "_") or "detector"
        default = lab.lab_directory(context.paths) / lab.stamped(f"detector_{stem}", ".json")
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            context.pick("Натижани сақлаш", "Save the result"),
            str(default),
            "JSON (*.json)",
        )
        if not chosen:
            return
        payload = dict(self.result)
        payload["source"] = self.source_label
        with open(chosen, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
            handle.write("\n")
        QMessageBox.information(
            self,
            context.pick("Сақланди", "Saved"),
            context.pick(f"Ёзилди: {chosen}", f"Written to {chosen}"),
        )

    # -- teardown ----------------------------------------------------------------

    def shutdown(self) -> None:
        runner = self.runner
        if runner is not None:
            runner.wait(3000)
            self.runner = None
