"""Apparatus page — reproduce everything, from this window or from a terminal.

The page's number is not written here. It comes from this module's position in
``pages.PAGES``, so a reordering cannot leave a stale number behind in a docstring.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import data as gdata
from .. import i18n
from .. import widgets as w
from ..theme import COLORS
from ..workers import ScriptRunner, describe
from . import Context

MAX_CONSOLE_LINES = 4000


def build(context: Context) -> QWidget:
    panel = ReproducePanel(context)
    area = w.wrap_scroll(panel)
    # The window calls ``shutdown`` before it discards a page, so a script that is
    # still running is stopped rather than orphaned.
    area.shutdown = panel.shutdown  # type: ignore[attr-defined]
    # The window drives F5 / Ctrl+T / Esc through this handle.
    area.controller = panel  # type: ignore[attr-defined]
    return area


class ReproducePanel(QWidget):
    """The pipeline, the tests, and one console they all write into."""

    def __init__(self, context: Context) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.context = context
        self.runner: ScriptRunner | None = None
        self.queue: list[tuple[str, list[str]]] = []
        self.status_labels: dict[str, QLabel] = {}
        self.run_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(
            w.page_title(
                context.pick(
                    "Ҳамма рақамни ўзингиз қайта чиқаринг",
                    "Reproduce every number yourself",
                )
            )
        )
        layout.addWidget(
            w.page_lead(
                context.pick(
                    "Бу ердаги ҳар бир тугма терминалда ёзиладиган буйруқнинг айнан "
                    "ўзини юритади — тугманинг ёнида ўша сатр турибди. Ойна ҳисоблашнинг "
                    "иккинчи, яширин йўли эмас.",
                    "Every button here runs exactly the command you would type in a "
                    "terminal, and that command line is printed next to it. The window is "
                    "not a second, hidden way of producing the numbers.",
                )
            )
        )

        layout.addWidget(self._status_card())
        layout.addWidget(self._console_card())
        layout.addWidget(self._pipeline_card())
        layout.addWidget(self._tests_card())
        layout.addWidget(self._environment_card())

    # -- status ------------------------------------------------------------------

    def _status_card(self) -> QWidget:
        context = self.context
        paths = context.paths
        results = context.results
        missing = results.missing_files()
        stale = gdata.stale_results(paths)

        if missing:
            text = i18n.ui(context.language, "missing_results")
            tone = COLORS["fail"]
        elif stale:
            text = i18n.ui(context.language, "stale_results") + "  ·  " + ", ".join(stale)
            tone = COLORS["warn"]
        else:
            text = i18n.ui(context.language, "everything_current")
            tone = COLORS["measured"]

        card = w.Card(context.pick("Ҳозирги ҳолат", "Current state"))
        banner = w.paragraph(text)
        banner.setStyleSheet(f"color: {tone}; font-weight: 600;")
        card.add(banner)

        package = gdata.package_files(paths)
        card.add(
            w.card_row(
                [
                    w.NumberCard(
                        str(len(gdata.RESULT_FILES) - len(missing)) + f" / {len(gdata.RESULT_FILES)}",
                        context.pick("натижа файли жойида", "result files present"),
                        "results/*.json",
                        tone="measured" if not missing else "fail",
                    ),
                    w.NumberCard(
                        str(len(gdata.figures(paths, results))),
                        context.pick("расм чизилган", "figures drawn"),
                        "results/figures/",
                    ),
                    w.NumberCard(
                        str(len(package)),
                        context.pick(
                            "маълумот тўпламидаги файл  ·  "
                            f"{gdata.checksum_count(paths)} та SHA-256 йиғиндиси",
                            "files in the data package  ·  "
                            f"{gdata.checksum_count(paths)} SHA-256 checksums",
                        ),
                        paths.relative(paths.data_package) + "/",
                    ),
                ],
                columns=3,
            )
        )

        row = QHBoxLayout()
        row.setSpacing(10)
        run_all = QPushButton(
            context.pick("Тўлиқ юришни бошлаш", "Run the whole pipeline")
        )
        run_all.setObjectName("Primary")
        run_all.clicked.connect(self._run_everything)
        row.addWidget(run_all)
        self.run_buttons.append(run_all)

        self.stop_button = QPushButton(i18n.ui(context.language, "stop"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        row.addWidget(self.stop_button)

        open_results = QPushButton(
            context.pick("results папкасини очиш", "Open the results folder")
        )
        open_results.clicked.connect(lambda: w.open_in_file_manager(paths.results))
        row.addWidget(open_results)
        row.addStretch(1)
        card.add_layout(row)
        return card

    # -- console -----------------------------------------------------------------

    def _console_card(self) -> QWidget:
        context = self.context
        card = w.Card(context.pick("Чиқиш", "Output"))
        self.console = QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(MAX_CONSOLE_LINES)
        self.console.setMinimumHeight(220)
        self.console.setPlaceholderText(
            context.pick(
                "Ҳали ҳеч нарса юритилмади.",
                "Nothing has been run yet.",
            )
        )
        card.add(self.console)

        row = QHBoxLayout()
        row.addStretch(1)
        copy = QPushButton(i18n.ui(context.language, "copy"))
        copy.setObjectName("Link")
        copy.clicked.connect(lambda: w.copy_to_clipboard(self.console.toPlainText()))
        row.addWidget(copy)
        clear = QPushButton(context.pick("Тозалаш", "Clear"))
        clear.setObjectName("Link")
        clear.clicked.connect(self.console.clear)
        row.addWidget(clear)
        card.add_layout(row)
        return card

    # -- pipeline ----------------------------------------------------------------

    def _pipeline_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick("Юриш тартиби", "The pipeline, in order"),
            context.pick(
                "Тартиб муҳим: кейинги скрипт олдингисининг натижа файлини ўқийди.",
                "The order matters: each script reads the result file the previous one "
                "wrote.",
            ),
        )
        for step in gdata.PIPELINE:
            card.add(self._step_row(step))
        return card

    def _step_row(self, step: gdata.Step) -> QWidget:
        context = self.context
        holder = QWidget()
        holder.setObjectName("Page")
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(10)
        button = QPushButton(i18n.ui(context.language, "run"))
        button.setMinimumWidth(96)
        button.clicked.connect(
            lambda _checked=False, s=step: self._enqueue([(s.script, s.command(context.paths))])
        )
        self.run_buttons.append(button)
        top.addWidget(button, 0)

        title = QLabel(f"<b>{step.script}</b> — {context.pick(step.uzbek, step.english)}")
        title.setWordWrap(True)
        title.setObjectName("CardBody")
        title.setStyleSheet(f"color: {COLORS['ink']};")
        top.addWidget(title, 1)

        status = QLabel(i18n.ui(context.language, "not_run"))
        status.setObjectName("NumberSource")
        status.setMinimumWidth(90)
        status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_labels[step.script] = status
        top.addWidget(status, 0)
        outer.addLayout(top)

        detail = QLabel(
            describe(step.command(context.paths), context.paths.root)
            + (f"   ·   ≈ {step.minutes} min" if step.minutes else "")
            + "   ·   → "
            + ", ".join(step.writes)
        )
        detail.setObjectName("NumberSource")
        detail.setWordWrap(True)
        detail.setContentsMargins(106, 0, 0, 0)
        outer.addWidget(detail)
        return holder

    # -- tests -------------------------------------------------------------------

    def _tests_card(self) -> QWidget:
        context = self.context
        card = w.Card(
            context.pick("Тестлар", "Tests"),
            context.pick(
                "Тестлар маълумот тўпламининг назорат йиғиндиларини, затвор қонунининг "
                "хоссаларини, USGS мижозини ва репозиторийнинг ўз тартибини текширади — "
                "жумладан Илова A да номи келтирилган ҳар бир файлнинг мавжудлигини.",
                "The tests check the data package's checksums, the properties of the gate "
                "law, the USGS client, and the repository's own hygiene — including that "
                "every file named in Appendix A exists.",
            ),
        )
        row = QHBoxLayout()
        row.setSpacing(10)
        button = QPushButton(context.pick("Тестларни юритиш", "Run the tests"))
        button.setMinimumWidth(96)
        button.clicked.connect(
            lambda: self._enqueue([("pytest", gdata.test_command(context.paths))])
        )
        self.run_buttons.append(button)
        row.addWidget(button, 0)
        command = QLabel(describe(gdata.test_command(context.paths), context.paths.root))
        command.setObjectName("NumberSource")
        command.setWordWrap(True)
        row.addWidget(command, 1)
        status = QLabel(i18n.ui(context.language, "not_run"))
        status.setObjectName("NumberSource")
        status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_labels["pytest"] = status
        row.addWidget(status, 0)
        card.add_layout(row)
        return card

    # -- environment -------------------------------------------------------------

    def _environment_card(self) -> QWidget:
        context = self.context
        here = gdata.environment()
        there = gdata.recorded_environment(context.results)
        card = w.Card(
            context.pick(
                "Муҳит — бу машина ва натижалар ўлчанган машина",
                "Environment — this machine and the machine the results were measured on",
            ),
            context.pick(
                "Мақолада келтириладиган вақт ўлчовлари битта машинага тегишли. Бу ерда "
                "иккови ёнма-ён турибди, шунинг учун бошқа машинадаги вақт бошқача "
                "чиқиши кутилган нарса — рақамлар эса бир хил бўлиши шарт.",
                "The timings quoted in the manuscript belong to one machine. Both are shown "
                "side by side here, so a different runtime elsewhere is expected — while "
                "the numbers themselves must match.",
            ),
        )
        pairs = [
            (context.pick("Бу машина", "This machine"), here["platform"]),
            (
                context.pick("Натижалар ўлчанган машина", "Machine of record"),
                str(there.get("platform", "—")),
            ),
            (context.pick("Python (бу ерда)", "Python (here)"), here["python"]),
            (
                context.pick("Python (ёзилган)", "Python (recorded)"),
                str(there.get("python", "—")),
            ),
            (context.pick("Процессор", "Processor"), here["processor"]),
            (
                context.pick("Ёзилган иш вақти", "Recorded runtime"),
                f"{there.get('runtime_s', '—')} s",
            ),
        ]
        card.add(w.key_values(pairs, columns=2))
        if there.get("runtime_covers"):
            card.add(
                w.paragraph(
                    context.pick("Иш вақти нимани қамрайди: ", "The runtime covers: ")
                    + str(there["runtime_covers"])
                )
            )
        matches = gdata.same_machine(context.results)
        if matches is False:
            card.add(
                w.paragraph(
                    context.pick(
                        "Бу машина натижалар ўлчанган машина эмас — вақт ўлчовлари "
                        "таққосланмайди, натижа сонлари эса таққосланиши шарт.",
                        "This is not the machine of record, so the timings are not "
                        "comparable — but the result numbers must be.",
                    )
                )
            )
        return card

    # -- running -----------------------------------------------------------------

    def run_pipeline(self) -> None:
        """Every published script in order, then the tests. Bound to F5."""
        self._run_everything()

    def run_tests(self) -> None:
        """The test suite alone. Bound to Ctrl+T."""
        self._enqueue([("pytest", gdata.test_command(self.context.paths))])

    def stop(self) -> None:
        """Bound to Esc, and to the Stop button."""
        self._stop()

    def _run_everything(self) -> None:
        commands = [
            (step.script, step.command(self.context.paths)) for step in gdata.PIPELINE
        ]
        commands.append(("pytest", gdata.test_command(self.context.paths)))
        self._enqueue(commands)

    def _enqueue(self, commands: list[tuple[str, list[str]]]) -> None:
        if self.runner is not None:
            return
        self.queue = list(commands)
        self._start_next()

    def _start_next(self) -> None:
        if not self.queue:
            self._set_busy(False)
            return
        name, command = self.queue.pop(0)
        self._set_busy(True)
        self._mark(name, i18n.ui(self.context.language, "running"), COLORS["accent"])
        self._append("")
        self._append(f"$ {describe(command, self.context.paths.root)}")
        self.started_at = time.monotonic()
        self.current = name

        runner = ScriptRunner(command, self.context.paths.root)
        runner.line.connect(self._append)
        runner.finished_with.connect(self._finished)
        self.runner = runner
        runner.start()

    def _finished(self, code: int) -> None:
        elapsed = time.monotonic() - getattr(self, "started_at", time.monotonic())
        language = self.context.language
        if code == 0:
            self._mark(self.current, f"{i18n.ui(language, 'done')} · {elapsed:.1f}s", COLORS["measured"])
        else:
            self._mark(self.current, f"{i18n.ui(language, 'failed')} · {code}", COLORS["fail"])
            self.queue.clear()
        runner = self.runner
        self.runner = None
        if runner is not None:
            runner.wait()
            runner.deleteLater()
        self._start_next()

    def _stop(self) -> None:
        self.queue.clear()
        if self.runner is not None:
            self.runner.cancel()

    def _set_busy(self, busy: bool) -> None:
        for button in self.run_buttons:
            button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

    def _mark(self, name: str, text: str, colour: str) -> None:
        label = self.status_labels.get(name)
        if label is not None:
            label.setText(text)
            label.setStyleSheet(f"color: {colour};")

    def _append(self, line: str) -> None:
        self.console.appendPlainText(line)
        bar = self.console.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.maximum())

    # -- teardown ----------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop anything still running and wait for the thread to end."""
        self._stop()
        runner = self.runner
        if runner is not None:
            runner.wait(3000)
            self.runner = None

    def closeEvent(self, event) -> None:  # pragma: no cover - window lifecycle
        self.shutdown()
        super().closeEvent(event)
