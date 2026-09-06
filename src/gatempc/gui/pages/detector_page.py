"""Laboratory page — run the circularity detector on a structure of your own.

This is the paper's method rather than the paper's result: point it at a site-year in
the data package, or at your own file of readings, and it answers the same question by
the same rule — is this published discharge a measurement, or the output of a rating?

The thresholds are on screen and editable, because a verdict is only meaningful next
to the numbers it was judged by. They start at the values fixed before the study's own
measurement; changing them is allowed and is recorded in the saved result.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ... import results as gdata
from .. import lab
from .. import widgets as w
from ..theme import COLORS
from ..workers import FunctionRunner, ScriptRunner, describe
from . import Context

#: Where a reader looks a site number up. Opened and read on 2026-09-06: the page
#: titles itself "Explore - USGS Water Data for the Nation" and searches monitoring
#: locations by area and by type of data.
USGS_EXPLORE = "https://waterdata.usgs.gov/explore/"

#: One station's own page; the site number and a trailing slash complete it. Checked
#: on 2026-09-06 with 09522700, which answers "WELLTON-MOHAWK MAIN CANAL NEAR YUMA,
#: AZ". The number carries the agency prefix in this address, not in the field below.
USGS_LOCATION = "https://waterdata.usgs.gov/monitoring-location/USGS-"

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
        self.fetch_runner: ScriptRunner | None = None
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
        self.folds = lab.available_folds(context.paths)
        self.registry = lab.known_sites(context.paths)
        self.site_year = w.combo(self._fold_items())
        self.package_note = w.paragraph("")
        if not self.folds:
            self.package_note.setText(
                context.pick(
                    "Маълумот тўплами топилмади. «Қайта юритиш» саҳифасидан "
                    "`download_usgs.py` ни юритинг, ёки қуйидаги рўйхатдан "
                    "станция танлаб юклаб олинг.",
                    "No data package was found. Run `download_usgs.py` from the "
                    "“Reproduce” page, or pick a station below and fetch it.",
                )
            )

        # A site number is not something a reader can guess, and until this was
        # written the page asked for one behind a placeholder and nothing else. The
        # first link is where the numbers actually are. The second is a station that
        # carries what the detector needs, taken from the reader's own package rather
        # than named here, so the example cannot outlive the data it points at.
        example = self.folds[0][1] if self.folds else ""
        example_uz = example_en = ""
        if example:
            page = f"{USGS_LOCATION}{example}/"
            example_uz = (f" Станциянинг ўз саҳифаси қандай кўринишини кўринг: "
                          f"<a href=\"{page}\">{example}</a>.")
            example_en = (f" To see a station's own page, open "
                          f"<a href=\"{page}\">{example}</a>.")
        self.site_help = w.paragraph(
            context.pick(
                "Бу рақамлар — USGS станцияларининг рақамлари; станцияни "
                f"<a href=\"{USGS_EXPLORE}\">USGS Water Data — Explore</a> саҳифасида "
                "ҳудуд ва маълумот тури бўйича қидириб топасиз. Детектор учун "
                "станция тўртта узлуксиз қаторни эълон қилиши шарт: затвор очилиши, "
                "юқори бьеф сатҳи, қуйи бьеф сатҳи ва сарф. Камёби — затвор "
                "очилиши: аксарият станцияларда бундай қатор йўқ." + example_uz
                + " <b>Ўз иншоотингизни текшириш учун «Ўз файлимдан» режимига "
                  "ўтинг.</b>",
                "These are USGS station numbers; you can search for a station on "
                f"<a href=\"{USGS_EXPLORE}\">USGS Water Data — Explore</a>, by area "
                "and by type of data. A station is usable here only if it publishes "
                "four continuous series: the gate opening, the headwater stage, the "
                "tailwater stage and the discharge. The gate opening is the rare one; "
                "most stations do not have it." + example_en
                + " <b>To check a structure of your own, switch to “From my own "
                  "file”.</b>",
            )
        )
        self.site_help.linkActivated.connect(w.open_url)

        # Not a free-text field. The downloader refuses a site it has not been
        # taught, so a box that accepts any number promises what the project cannot
        # deliver: typing one produced "unknown site …" in a terminal the reader was
        # never told to open. The chooser offers exactly what the script accepts.
        self.fetchable = w.combo(self._fetchable_items())
        self.fetch_button = QPushButton(context.pick("Юклаб олиш", "Fetch"))
        self.fetch_button.clicked.connect(self.fetch)
        self.stop_fetch_button = QPushButton(context.pick("Тўхтатиш", "Stop"))
        self.stop_fetch_button.setEnabled(False)
        self.stop_fetch_button.clicked.connect(self.stop_fetch)
        self.add_button = QPushButton(context.pick("Станция қўшиш…", "Add a station…"))
        self.add_button.clicked.connect(self.add_station)

        self.fetch_row = QWidget()
        self.fetch_row.setObjectName("Page")
        fetch_layout = QHBoxLayout(self.fetch_row)
        fetch_layout.setContentsMargins(0, 0, 0, 0)
        fetch_layout.setSpacing(8)
        fetch_layout.addWidget(self.fetchable, 1)
        fetch_layout.addWidget(self.fetch_button, 0)
        fetch_layout.addWidget(self.stop_fetch_button, 0)
        fetch_layout.addWidget(self.add_button, 0)

        self.fetch_note = w.paragraph("")
        self.fetch_console = QPlainTextEdit()
        self.fetch_console.setObjectName("Console")
        self.fetch_console.setReadOnly(True)
        self.fetch_console.setMaximumBlockCount(2000)
        self.fetch_console.setMinimumHeight(130)
        self.fetch_console.setVisible(False)

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
                (context.pick("Станция юклаб олиш", "Fetch a station"),
                 self.fetch_row),
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
        # What the file has to look like, said BEFORE the dialog opens. Until this
        # was written the five column pickers only appeared after a file had been
        # chosen, so a reader learned what was wanted by being told his file was
        # wrong. The sample row is the shortest honest specification there is.
        self.file_intro = w.paragraph(
            context.pick(
                "Файл — оддий CSV, сарлавҳа қатори билан. <b>Ҳар бир қатор — битта "
                "вақт нуқтаси</b>, ва ўша қаторда бешта ўлчов ёнма-ён туради: вақт, "
                "затвор очилиши, юқори бьеф сатҳи, қуйи бьеф сатҳи, сарф. Устунлар "
                "қандай номланиши муҳим эмас — файл очилгач қайси устун қайси "
                "ўлчовлигини ўзингиз кўрсатасиз, ва бирликларни ҳам ўзингиз "
                "танлайсиз.<br><br>"
                "<code>time,gate_opening,headwater,tailwater,discharge</code><br>"
                "<code>2024-03-01 00:00,1.42,63.71,61.55,9.83</code>",
                "The file is a plain CSV with a header row. <b>One row is one instant "
                "in time</b>, carrying five readings side by side: the time, the gate "
                "opening, the headwater stage, the tailwater stage and the discharge. "
                "The column names do not matter — once the file is open you say which "
                "column is which, and you choose the units as well.<br><br>"
                "<code>time,gate_opening,headwater,tailwater,discharge</code><br>"
                "<code>2024-03-01 00:00,1.42,63.71,61.55,9.83</code>",
            )
        )
        self.file_note = w.paragraph(
            context.pick(
                "Файл 15 дақиқалик тўрда бўлиши шарт эмас, лекин вақт устуни "
                "<code>ГГГГ-ОО-КК</code> билан бошланиши керак — кунлик "
                "гуруҳлаш шунга таянади. Бешта ўлчовдан биттаси бўш бўлган қатор "
                "ташланади, ва нечтаси ташлангани натижа билан бирга кўрсатилади.",
                "The file need not be on a 15-minute grid, but the time column has to "
                "start with <code>YYYY-MM-DD</code>: the daily grouping relies on it. "
                "A row with a blank in any of the five is skipped, and how many were "
                "skipped is reported with the result.",
            )
        )

        card.add(self.site_help)
        card.add(self.package_form)
        card.add(self.package_note)
        card.add(self.fetch_note)
        card.add(self.fetch_console)
        card.add(self.file_intro)
        card.add(self.file_form)
        card.add(self.file_note)
        self._refresh_fetch()
        return card

    # -- the site list and what may still be fetched ------------------------------

    def _fold_items(self) -> list[tuple[str, object]]:
        """One entry per site-year, marked with the package it came from."""
        context = self.context
        items: list[tuple[str, object]] = []
        for package, site, year in self.folds:
            own = package != context.paths.data_package
            mark = context.pick("  ·  ўзингиз юклаган", "  ·  fetched by you") if own else ""
            items.append((f"{site}  ·  {year}{mark}", (package, site, year)))
        return items

    def _fetchable_items(self) -> list[tuple[str, object]]:
        """Every registered site, the ones the reader has not got listed first.

        Not only the missing ones. A run that was stopped, or that ended on the
        hourly quota, leaves part of a package behind; a chooser that then dropped
        the site would leave no way to finish it from the window — which is exactly
        the dead end the free-text field used to be. Choosing a site already held
        is cheap: the downloader keeps what it fetched in its cache and asks the
        API only for what is missing.
        """
        context = self.context
        have = {site for _package, site, _year in self.folds}
        items: list[tuple[str, object]] = []
        for site, entry in sorted(self.registry.items(),
                                  key=lambda pair: (pair[0] in have, pair[0])):
            label = f"{site}  ·  {entry['name']}" if entry["name"] else site
            # The years belong on the label. A fetch takes the registered years and
            # no others, and a reader who cannot see them has no way to know what a
            # station brings — or to tell that the choice was not left open.
            years = lab.years_as_text(entry["years"])
            if years:
                label += f"  ·  {years}"
            # A station the reader assigned is marked as such wherever it appears.
            # Its four roles are one person's reading of a free-text label, and
            # that is not the same standing as the two the study checked.
            if entry.get("source") == "you":
                label += context.pick("  ·  ўзингиз қўшган", "  ·  added by you")
            if site in have:
                label += context.pick("  ·  сизда бор", "  ·  you have it")
            items.append((label, site))
        return items

    def _refresh_fetch(self) -> None:
        """State the terms of a fetch, or say why none can be offered."""
        context = self.context
        offered = self.fetchable.count() > 0
        self.fetch_row.setVisible(offered)
        if offered:
            self.fetch_note.setText(
                context.pick(
                    "Рўйхатда `download_usgs.py` таниган станциялар турибди. "
                    "Янгисини қўшиш бир буйруқлик иш эмас: иккита бир хил сатҳ "
                    "қаторидан қайси бири юқори бьеф эканини скрипт аниқлай "
                    "олмайди, шунинг учун тўртта сериянинг роли қўлда белгиланади. "
                    "Юклаш USGS API'сига мурожаат қилади — 2026-09-05 да ўлчанганда "
                    "соатига тахминан 140 сўровга рухсат берилган — шунинг учун у "
                    "секин боради, ва натижа `build/lab/` га ёзилади, эълон "
                    "қилинган тўпламга эмас. «Сизда бор» деб белгиланганини "
                    "танласангиз юклаш қайтадан юритилади: кэшдагиси иккинчи марта "
                    "олинмайди, шунинг учун ярим қолган юриш шу йўл билан "
                    "тугалланади. Йиллар рўйхатда кўрсатилган — улар танланмайди, "
                    "чунки булар архивда тўртта қатор ҳам мавжуд бўлган йиллар; "
                    "қолган йилларда затвор очилиши ва бьеф сатҳлари умуман йўқ, "
                    "буни тўпламдаги `coverage_census.csv` йилма-йил кўрсатади.",
                    "The list holds the stations `download_usgs.py` has been taught. "
                    "Adding one is not a one-command job: the script cannot tell "
                    "which of two identical stage series is the headwater, so the "
                    "roles of the four series are fixed by hand. A fetch goes to the "
                    "USGS API — measured on 2026-09-05 at roughly 140 requests an "
                    "hour — so it is paced, and what it writes goes to `build/lab/`, "
                    "never into the published package. Choosing one marked “you have "
                    "it” runs the download again: nothing already cached is fetched "
                    "twice, so this is also how a run that stopped halfway is "
                    "finished. The years are shown in the list and are not a choice: "
                    "they are the years the archive carries all four series for. In "
                    "the others the gate opening and the two stages are absent "
                    "entirely, which `coverage_census.csv` in the package reports "
                    "year by year.",
                )
            )
        else:
            self.fetch_note.setText(
                context.pick(
                    "`scripts/download_usgs.py` топилмади, шунинг учун бу ердан "
                    "ҳеч нарса юклаб бўлмайди.",
                    "`scripts/download_usgs.py` was not found, so nothing can be "
                    "fetched from here.",
                )
            )
        self.fetch_note.setVisible(self.from_package.isChecked())

    def _reload_packages(self) -> None:
        """Rebuild both choosers after a fetch, keeping the reader's selection."""
        chosen = self.site_year.currentData()
        self.folds = lab.available_folds(self.context.paths)
        self.site_year.clear()
        for label, value in self._fold_items():
            self.site_year.addItem(label, value)
        if chosen is not None:
            index = self.site_year.findData(chosen)
            if index >= 0:
                self.site_year.setCurrentIndex(index)
        site = self.fetchable.currentData()
        self.fetchable.clear()
        for label, value in self._fetchable_items():
            self.fetchable.addItem(label, value)
        if site is not None:
            index = self.fetchable.findData(site)
            if index >= 0:
                self.fetchable.setCurrentIndex(index)
        if self.folds:
            self.package_note.setText("")
        self._refresh_fetch()
        self._mode_changed()

    def _mode_changed(self) -> None:
        from_package = self.from_package.isChecked()
        self.site_help.setVisible(from_package)
        self.package_form.setVisible(from_package)
        self.package_note.setVisible(from_package and bool(self.package_note.text()))
        self.fetch_note.setVisible(from_package)
        self.fetch_console.setVisible(
            from_package and bool(self.fetch_console.toPlainText())
        )
        self.file_intro.setVisible(not from_package)
        self.file_form.setVisible(not from_package)
        self.file_note.setVisible(not from_package)

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

    # -- fetching a registered site ------------------------------------------------

    def fetch(self) -> None:
        """Run the published downloader, in the window, with its output on screen.

        Not silently: the command line is printed before it runs, every line the
        script writes appears as it is written, and Stop is live throughout. That
        is what the reader is owed for a run that goes to the network — the earlier
        dialog handed over a command and told the reader to reopen the page, which
        answered neither *is it running* nor *how far has it got*.
        """
        context = self.context
        if self.fetch_runner is not None:
            return
        site = self.fetchable.currentData()
        if not site:
            return
        try:
            out = lab.lab_directory(context.paths) / f"package_{site}"
        except OSError as error:
            # A clone opened from a read-only location, most likely. Say so rather
            # than dying inside a signal handler with nothing on screen.
            self.fetch_console.setVisible(True)
            self.fetch_console.setPlainText(
                context.pick(
                    f"`build/lab` папкасини яратиб бўлмади: {error}\n"
                    f"Юклаб олинган нарса лойиҳа папкасининг ичига ёзилади, "
                    f"шунинг учун у ёзиладиган жойда бўлиши керак.",
                    f"`build/lab` could not be created: {error}\n"
                    f"A fetch is written inside the project folder, so that folder "
                    f"has to be writable.",
                )
            )
            return
        command = [sys.executable, str(context.paths.scripts / "download_usgs.py"),
                   "--sites", str(site), "--out", str(out)]
        # A station the reader added carries its own assignment; the script has no
        # entry for it and would refuse the site without one. The published sites
        # need nothing here, and must not be given anything: passing --series for
        # one of them is refused by the script itself.
        entry = self.registry.get(str(site), {})
        if entry.get("source") == "you":
            series = ",".join(f"{role}={entry['series'][role]}"
                              for role in ("gate_opening", "headwater",
                                           "tailwater", "discharge")
                              if role in entry.get("series", {}))
            command += ["--series", series,
                        "--years", lab.years_as_text(entry["years"]).replace("–", "-"),
                        "--site-name", entry.get("name", "") or f"USGS {site}"]
        self.fetch_console.setVisible(True)
        self.fetch_console.clear()
        self.fetch_console.appendPlainText("$ " + describe(command, context.paths.root))
        self.fetch_console.appendPlainText(
            context.pick(
                "Ҳар бир қатлам ва ҳар бир сайт-йил учун битта сатр чиқади. "
                "Тўхтатсангиз, юклаб бўлинганлари кэшда қолади ва қайта юритиш "
                "фақат етишмаётганини олади.",
                "One line appears per layer and per site-year. If you stop it, what "
                "was fetched stays in the cache and running it again takes only what "
                "is missing.",
            )
        )
        self.fetch_button.setEnabled(False)
        self.stop_fetch_button.setEnabled(True)
        runner = ScriptRunner(command, context.paths.root)
        runner.line.connect(self._fetch_line)
        runner.finished_with.connect(self._fetch_finished)
        self.fetch_runner = runner
        runner.start()

    def add_station(self) -> None:
        """Look a station up, confirm its four series, and remember the assignment."""
        from ..add_station import ask_for_a_station

        site = ask_for_a_station(self.context, self)
        if not site:
            return
        self.registry = lab.known_sites(self.context.paths)
        self._reload_packages()
        index = self.fetchable.findData(site)
        if index >= 0:
            self.fetchable.setCurrentIndex(index)

    def stop_fetch(self) -> None:
        if self.fetch_runner is not None:
            self.fetch_runner.cancel()

    def _fetch_line(self, line: str) -> None:
        self.fetch_console.appendPlainText(line)
        bar = self.fetch_console.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.maximum())

    def _fetch_finished(self, code: int) -> None:
        context = self.context
        runner = self.fetch_runner
        self.fetch_runner = None
        if runner is not None:
            runner.wait()
            runner.deleteLater()
        self.fetch_button.setEnabled(True)
        self.stop_fetch_button.setEnabled(False)
        if code == 0:
            self._reload_packages()
            self.fetch_console.appendPlainText(
                context.pick(
                    "--- юкланди; сайт-йил рўйхати янгиланди ---",
                    "--- fetched; the site-year list has been rebuilt ---",
                )
            )
            return
        # A failure keeps whatever arrived: the site list is rebuilt either way so
        # that a partial package is offered rather than silently ignored.
        self._reload_packages()
        self.fetch_console.appendPlainText(
            context.pick(
                f"--- тугамади (чиқиш коди {code}); юқоридаги сабабни ўқинг ---",
                f"--- did not finish (exit code {code}); the reason is above ---",
            )
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

            # The package travels with the site-year: a fold fetched from this page
            # lives under build/lab, not in the published package, and reading the
            # wrong directory would silently answer about the wrong data.
            package, site, year = chosen
            samples, approvals = load_fold(str(package), site, year,
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
        fetch = self.fetch_runner
        if fetch is not None:
            fetch.cancel()
            fetch.wait(3000)
            self.fetch_runner = None
