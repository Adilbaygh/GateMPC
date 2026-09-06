"""Laboratory page — run the closed-loop experiment with parameters of your own.

The form does not simulate anything itself. It builds a command line for
``scripts/control_comparison.py``, shows you that line, runs it, and reads the JSON it
writes. So an experiment started here is the same experiment a reader would start in a
terminal, and it can be repeated without the window.

Output goes to ``build/lab/``, never to ``results/``: a run with parameters other than
the registered ones is not the published result and must not be able to overwrite it.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import data as gdata
from .. import i18n, lab
from .. import widgets as w
from ..theme import COLORS
from ..workers import ScriptRunner, describe
from . import Context

NAV = ("9 · Бошқарув тажрибаси", "9 · Control experiment")

#: The values the published run used, so a departure can be named rather than guessed.
REGISTERED = {"replicates": 100, "pool_length": 7000.0, "min_gate_step": 0.0}


def build(context: Context) -> QWidget:
    panel = ExperimentPanel(context)
    area = w.wrap_scroll(panel)
    area.shutdown = panel.shutdown  # type: ignore[attr-defined]
    area.controller = panel  # type: ignore[attr-defined]
    return area


class ExperimentPanel(QWidget):
    def __init__(self, context: Context) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.context = context
        self.runner: ScriptRunner | None = None
        self.output_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(
            w.page_title(
                context.pick(
                    "Ёпиқ ҳалқа тажрибасини ўз параметрларингиз билан юритинг",
                    "Run the closed-loop experiment with your own parameters",
                )
            )
        )
        layout.addWidget(
            w.page_lead(
                context.pick(
                    "Ўлчанадиган нарса — <b>δ</b>: бир хил контроллер идентификация "
                    "қилинган қонунда созилганда, эталон қонунида созилганига нисбатан "
                    "нима ютади. Манфий δ — идентификация қилинган қонун фойдасига.",
                    "What is measured is <b>δ</b>: what the same controller gains when it "
                    "is tuned on the identified law instead of the benchmark law. A "
                    "negative δ favours the identified law.",
                )
            )
        )

        layout.addWidget(self._form_card())
        layout.addWidget(self._command_card())
        layout.addWidget(self._console_card())
        self.result_card = w.Card(context.pick("Натижа", "Result"))
        self.result_body = QVBoxLayout()
        self.result_body.setSpacing(12)
        self.result_card.add_layout(self.result_body)
        self.result_body.addWidget(
            w.paragraph(context.pick("Ҳали юритилмади.", "Nothing has been run yet."))
        )
        layout.addWidget(self.result_card)
        self._refresh_command()

    # -- form --------------------------------------------------------------------

    def _form_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick("Параметрлар", "Parameters"),
            context.pick(
                "Ҳар бир майдоннинг бошланғич қиймати — мақолада эълон қилинган "
                "юришнинг қиймати. Ўзгартирганингизни скриптнинг ўзи ҳам чиқишида "
                "огоҳлантириб ёзади.",
                "Every field starts at the value the published run used. If you change "
                "one, the script itself prints a warning saying so in its output.",
            ),
        )
        self.replicates = w.integer_spin(REGISTERED["replicates"], 2, 2000, 10)
        self.pool_length = w.spin(REGISTERED["pool_length"], 200.0, 100000.0, 1, 500.0, "m")
        self.min_step = w.spin(REGISTERED["min_gate_step"] * 1000, 0.0, 500.0, 2, 1.0, "mm")
        self.skip_sensitivity = QCheckBox(
            context.pick(
                "Сезгирлик сўровларини ўтказиб юбориш (тезроқ)",
                "Skip the sensitivity sweeps (faster)",
            )
        )
        for widget in (self.replicates, self.pool_length, self.min_step):
            widget.valueChanged.connect(self._refresh_command)
        self.skip_sensitivity.toggled.connect(self._refresh_command)

        card.add(
            w.form(
                [
                    (
                        context.pick("Жуфтланган такрорлар", "Paired replicates"),
                        self.replicates,
                    ),
                    (context.pick("Бьеф узунлиги", "Pool length"), self.pool_length),
                    (
                        context.pick(
                            "Минимал затвор қадами (бош юришда)",
                            "Minimum gate step (in the headline run)",
                        ),
                        self.min_step,
                    ),
                ],
                columns=2,
            )
        )
        card.add(self.skip_sensitivity)
        self.departure = w.paragraph("")
        self.departure.setStyleSheet(f"color: {COLORS['warn']}; font-weight: 600;")
        card.add(self.departure)
        return card

    # -- command -----------------------------------------------------------------

    def command(self) -> list[str]:
        context = self.context
        self.output_path = lab.lab_directory(context.paths) / lab.stamped(
            "control_comparison", ".json"
        )
        csv_path = self.output_path.with_suffix(".csv")
        arguments = [
            "--replicates", str(self.replicates.value()),
            "--pool-length", f"{self.pool_length.value():g}",
            "--min-gate-step", f"{self.min_step.value() / 1000.0:g}",
            "--out", str(self.output_path),
            "--out-csv", str(csv_path),
        ]
        if self.skip_sensitivity.isChecked():
            arguments.append("--skip-sensitivity")
        import sys

        return [sys.executable,
                str(context.paths.scripts / "control_comparison.py"), *arguments]

    def _command_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick("Юритиладиган буйруқ", "The command that will run"),
            context.pick(
                "Терминалда ҳам худди шу сатр ишлайди.",
                "The same line works in a terminal.",
            ),
        )
        self.command_label = QLabel()
        self.command_label.setObjectName("NumberSource")
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        card.add(self.command_label)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.run_button = QPushButton(context.pick("Юритиш", "Run"))
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run)
        row.addWidget(self.run_button)
        self.stop_button = QPushButton(i18n.ui(context.language, "stop"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        row.addWidget(self.stop_button)
        copy = QPushButton(i18n.ui(context.language, "copy"))
        copy.setObjectName("Link")
        copy.clicked.connect(lambda: w.copy_to_clipboard(self.command_label.text()))
        row.addWidget(copy)
        row.addStretch(1)
        self.status = w.paragraph("")
        row.addWidget(self.status, 1)
        card.add_layout(row)
        return card

    def _refresh_command(self) -> None:
        context = self.context
        self.command_label.setText(describe(self.command(), context.paths.root))
        departures = []
        if self.replicates.value() != REGISTERED["replicates"]:
            departures.append(
                context.pick(
                    f"такрорлар {self.replicates.value()} "
                    f"(эълон қилинганда {REGISTERED['replicates']})",
                    f"{self.replicates.value()} replicates "
                    f"(the published run used {REGISTERED['replicates']})",
                )
            )
        if abs(self.pool_length.value() - REGISTERED["pool_length"]) > 1e-9:
            departures.append(
                context.pick(
                    f"бьеф {self.pool_length.value():g} м "
                    f"(эълон қилинганда {REGISTERED['pool_length']:g} м)",
                    f"pool {self.pool_length.value():g} m "
                    f"(the published run used {REGISTERED['pool_length']:g} m)",
                )
            )
        if self.min_step.value() > 0:
            departures.append(
                context.pick(
                    f"бош юришда {self.min_step.value():g} мм лик ўлик зона "
                    f"(эълон қилинган протоколда йўқ)",
                    f"a {self.min_step.value():g} mm deadband in the headline run "
                    f"(the registered protocol has none)",
                )
            )
        self.departure.setText(
            context.pick(
                "Бу юриш эълон қилинган натижа ЭМАС: ", "This run is NOT the published result: "
            )
            + "; ".join(departures)
            if departures
            else ""
        )

    # -- console -----------------------------------------------------------------

    def _console_card(self) -> QWidget:
        card = w.Card(self.context.pick("Чиқиш", "Output"))
        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(4000)
        self.console.setMinimumHeight(180)
        card.add(self.console)
        return card

    # -- running -----------------------------------------------------------------

    def run(self) -> None:
        if self.runner is not None:
            return
        context = self.context
        command = self.command()
        self.console.clear()
        self.console.appendPlainText("$ " + describe(command, context.paths.root))
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._say(i18n.ui(context.language, "running"), COLORS["accent"])
        runner = ScriptRunner(command, context.paths.root)
        runner.line.connect(self._append)
        runner.finished_with.connect(self._finished)
        self.runner = runner
        runner.start()

    def stop(self) -> None:
        if self.runner is not None:
            self.runner.cancel()

    def _append(self, line: str) -> None:
        self.console.appendPlainText(line)
        bar = self.console.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.maximum())

    def _finished(self, code: int) -> None:
        context = self.context
        runner = self.runner
        self.runner = None
        if runner is not None:
            runner.wait()
            runner.deleteLater()
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if code != 0:
            self._say(f"{i18n.ui(context.language, 'failed')} · {code}", COLORS["fail"])
            return
        self._say(i18n.ui(context.language, "done"), COLORS["measured"])
        self._show_result()

    def _say(self, text: str, colour: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {colour};")

    # -- result ------------------------------------------------------------------

    def _show_result(self) -> None:
        context = self.context
        while self.result_body.count():
            item = self.result_body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if self.output_path is None or not self.output_path.is_file():
            self.result_body.addWidget(
                w.paragraph(
                    context.pick(
                        "Скрипт натижа файлини ёзмади.",
                        "The script wrote no result file.",
                    )
                )
            )
            return
        with self.output_path.open(encoding="utf-8") as handle:
            document = json.load(handle)

        cards = []
        for name in ("PI", "MPC"):
            block = ((document.get("controllers") or {}).get(name) or {}).get("delta") or {}
            interval = block.get("ci95") or []
            note = ""
            if len(interval) == 2:
                note = (f"[{100 * interval[0]:+.3f}, {100 * interval[1]:+.3f}] %, "
                        f"95% bootstrap")
            cards.append(
                w.NumberCard(
                    gdata.as_signed_percent(block.get("median"), 3),
                    context.pick(f"{name} — δ нинг медианаси", f"{name} — median δ"),
                    context.paths.relative(self.output_path)
                    + f" → controllers.{name}.delta.median",
                    tone="accent",
                    note=note,
                )
            )
        environment = document.get("environment") or {}
        cards.append(
            w.NumberCard(
                f"{environment.get('runtime_s', '—')} s",
                context.pick("бу юришнинг вақти", "runtime of this run"),
                context.paths.relative(self.output_path) + " → environment.runtime_s",
            )
        )
        self.result_body.addWidget(w.card_row(cards, columns=3))

        indicators = (
            ((document.get("controllers") or {}).get("MPC") or {}).get("indicators") or {}
        )
        rows = []
        for combination, block in sorted(indicators.items()):
            rows.append(
                [combination]
                + [
                    f"{(block.get(key) or {}).get('median', float('nan')):.6f}"
                    for key in ("MAE", "IAE", "StE", "IAQ", "IAW")
                ]
            )
        if rows:
            table = gdata.Table(self.output_path, ["MPC", "MAE", "IAE", "StE", "IAQ", "IAW"],
                                rows)
            self.result_body.addWidget(w.table_widget(table, 200))

        row = QHBoxLayout()
        row.addStretch(1)
        open_folder = QPushButton(
            context.pick("Натижа файлини очиш", "Open the result file")
        )
        open_folder.setObjectName("Link")
        open_folder.clicked.connect(lambda: w.open_in_file_manager(self.output_path))
        row.addWidget(open_folder)
        self.result_body.addLayout(row)

    # -- teardown ----------------------------------------------------------------

    def shutdown(self) -> None:
        if self.runner is not None:
            self.runner.cancel()
            self.runner.wait(3000)
            self.runner = None
