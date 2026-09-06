"""The window: a menu bar, a sectioned sidebar, one page at a time, and a status line.

Pages are built the first time they are opened rather than all at startup, because the
figure page loads ten PNGs and a reviewer who only wants the pre-registration record
should not wait for them.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import results as gdata
from . import i18n, lab, pages
from . import widgets as w
from .theme import COLORS

SIDEBAR_WIDTH = 248


class MainWindow(QMainWindow):
    def __init__(self, root=None, language: str = i18n.DEFAULT_LANGUAGE) -> None:
        super().__init__()
        self.paths = gdata.ProjectPaths.discover(root) if root else gdata.ProjectPaths.discover()
        self.language = i18n.normalise(language)
        self.results = gdata.Results(self.paths)

        self.setWindowTitle(i18n.ui(self.language, "app_title"))
        self.resize(1320, 900)
        self.setMinimumSize(960, 640)

        central = QWidget()
        central.setObjectName("Page")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())

        lower = QHBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.setSpacing(0)
        self.sidebar = self._sidebar()
        lower.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        lower.addWidget(self.stack, 1)
        outer.addLayout(lower, 1)
        self.setCentralWidget(central)

        self._holders: dict[str, QWidget] = {}
        self._built: set[str] = set()
        for key in pages.PAGE_KEYS:
            holder = QWidget()
            holder.setObjectName("Page")
            layout = QVBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._holders[key] = holder
            self.stack.addWidget(holder)

        self._build_menus()
        self._build_status_bar()
        self._add_shortcuts()
        self.show_page(pages.PAGE_KEYS[0])

    # ------------------------------------------------------------------- chrome

    def _header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Header")
        bar.setFixedHeight(70)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 11, 18, 11)
        layout.setSpacing(14)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel(i18n.ui(self.language, "app_title"))
        self.title_label.setObjectName("HeaderTitle")
        text.addWidget(self.title_label)
        self.strip_label = QLabel(i18n.ui(self.language, "headline_strip"))
        self.strip_label.setObjectName("HeaderStrip")
        text.addWidget(self.strip_label)
        layout.addLayout(text, 1)

        self.language_button = QPushButton()
        self.language_button.setObjectName("LanguageButton")
        self.language_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_button.clicked.connect(self.toggle_language)
        self._refresh_language_button()
        layout.addWidget(self.language_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Sidebar")
        panel.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 6, 0, 12)
        layout.setSpacing(0)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.section_labels: dict[str, QLabel] = {}

        seen: set[str] = set()
        for index, key in enumerate(pages.PAGE_KEYS):
            section = pages.section_of(key)
            if section not in seen:
                seen.add(section)
                caption = QLabel(pages.section_label(section, self.language))
                caption.setObjectName("SidebarCaption")
                layout.addWidget(caption)
                self.section_labels[section] = caption
            button = QPushButton(pages.nav_label(key, self.language))
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, target=key: self.show_page(target))
            self.nav_group.addButton(button, index)
            self.nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.root_label = QLabel(self.paths.root.name)
        self.root_label.setObjectName("SidebarCaption")
        self.root_label.setToolTip(str(self.paths.root))
        self.root_label.setStyleSheet(f"color: {COLORS['on_dark_soft']}; font-weight: 400;")
        self.root_label.setWordWrap(True)
        layout.addWidget(self.root_label)
        return panel

    # -------------------------------------------------------------------- menus

    def _act(self, uzbek: str, english: str, slot, shortcut: str = "",
             tip: tuple[str, str] | None = None) -> QAction:
        action = QAction(self.pick(uzbek, english), self)
        action.setData((uzbek, english))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            # Both, because the two are read in different places: the status tip in
            # the bar at the foot of the window, the tool tip under the cursor. A
            # menu shows the second only when the menu is asked to.
            text = self.pick(*tip)
            action.setStatusTip(text)
            action.setToolTip(text)
            action.setData((uzbek, english, *tip))
        action.triggered.connect(slot)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.clear()
        self._menus: list[tuple[object, tuple[str, str]]] = []
        self._actions: list[QAction] = []

        # -- File
        #
        # Three folders, and their names alone do not tell a reader which one holds
        # the answer to the question being asked. Each item therefore says what is
        # inside, and the tip separates the two that are easy to confuse: results/
        # is what the published scripts wrote, build/lab/ is what this window
        # computed for the reader, and the second sits outside the public
        # repository precisely so that it can never be taken for the first.
        file_menu = bar.addMenu(self.pick("&Файл", "&File"))
        file_menu.setToolTipsVisible(True)
        self._menus.append((file_menu, ("&Файл", "&File")))
        for action in (
            self._act(
                "Лойиҳа папкаси — код, маълумот пакети ва мақола",
                "Project folder — the code, the data package and the manuscript",
                lambda: w.open_in_file_manager(self.paths.root),
                tip=("Лойиҳанинг илдиз папкаси: scripts/, results/, DATA/, tests/ "
                     "ва paper/ шу ерда.",
                     "The project root: scripts/, results/, DATA/, tests/ and "
                     "paper/ all live here."),
            ),
            self._act(
                "results/ — мақоладаги сонлар, расмлар ва жадваллар",
                "results/ — the numbers, figures and tables the paper prints",
                lambda: w.open_in_file_manager(self.paths.results),
                tip=("Скриптлар ёзган эълон қилинган натижалар. Мақоладаги ҳар бир "
                     "сон шу ердан ўқилади, ва формадан чиққан ҳеч нарса бу ерга "
                     "ёзилмайди.",
                     "The published results the scripts wrote. Every number in the "
                     "paper is read from here, and nothing produced from a form is "
                     "written into it."),
            ),
            self._act(
                "build/lab/ — шу ойнада ўзингиз ҳисоблаганлар",
                "build/lab/ — what you compute in this window",
                lambda: w.open_in_file_manager(lab.lab_directory(self.paths)),
                tip=("ЛАБОРАТОРИЯ саҳифаларидан (7–9) бошланган юришлар шу ерга "
                     "ёзилади. build/ оммавий репозиторийга кирмайди, шунинг учун "
                     "сизнинг юришингиз эълон қилинган натижа билан аралашмайди.",
                     "Runs started from the laboratory pages (7–9) are written "
                     "here. build/ is not part of the public repository, so your "
                     "own run can never be mistaken for a published result."),
            ),
        ):
            file_menu.addAction(action)
            self._actions.append(action)
        file_menu.addSeparator()
        quit_action = self._act("Чиқиш", "Quit", self.close, "Ctrl+Q")
        file_menu.addAction(quit_action)
        self._actions.append(quit_action)

        # -- Compute
        compute = bar.addMenu(self.pick("Ҳ&исоблаш", "&Compute"))
        self._menus.append((compute, ("Ҳ&исоблаш", "&Compute")))
        for key in ("calculator", "detector", "experiment"):
            page = pages.page_of(key)
            action = self._act(page.uzbek, page.english,
                               lambda _checked=False, target=key: self.show_page(target))
            compute.addAction(action)
            self._actions.append(action)
        compute.addSeparator()
        for action in (
            self._act("Тўлиқ юришни бошлаш", "Run the whole pipeline",
                      self.run_pipeline, "F5"),
            self._act("Тестларни юритиш", "Run the tests", self.run_tests, "Ctrl+T"),
            self._act("Тўхтатиш", "Stop", self.stop_running, "Esc"),
        ):
            compute.addAction(action)
            self._actions.append(action)

        # -- View
        view = bar.addMenu(self.pick("&Кўриниш", "&View"))
        self._menus.append((view, ("&Кўриниш", "&View")))
        self.page_actions: dict[str, QAction] = {}
        page_group = QActionGroup(self)
        page_group.setExclusive(True)
        seen: set[str] = set()
        self.section_actions: dict[str, QAction] = {}
        for index, key in enumerate(pages.PAGE_KEYS, start=1):
            section = pages.section_of(key)
            if section not in seen:
                seen.add(section)
                if len(seen) > 1:
                    view.addSeparator()
                heading = QAction(pages.section_label(section, self.language), self)
                heading.setEnabled(False)
                view.addAction(heading)
                self.section_actions[section] = heading
            page = pages.page_of(key)
            action = self._act(page.uzbek, page.english,
                               lambda _checked=False, target=key: self.show_page(target),
                               f"Ctrl+{index}" if index <= 9 else "")
            action.setCheckable(True)
            page_group.addAction(action)
            view.addAction(action)
            self.page_actions[key] = action
            self._actions.append(action)
        view.addSeparator()
        self.sidebar_action = self._act("Ёнбош панел", "Sidebar",
                                        self.toggle_sidebar, "Ctrl+B")
        self.sidebar_action.setCheckable(True)
        self.sidebar_action.setChecked(True)
        view.addAction(self.sidebar_action)
        self._actions.append(self.sidebar_action)

        # -- Language
        language_menu = bar.addMenu(self.pick("&Тил", "&Language"))
        self._menus.append((language_menu, ("&Тил", "&Language")))
        self.language_actions: dict[str, QAction] = {}
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        for code in i18n.LANGUAGES:
            action = QAction(i18n.ENDONYM[code], self)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            action.triggered.connect(lambda _checked=False, c=code: self.set_language(c))
            language_group.addAction(action)
            language_menu.addAction(action)
            self.language_actions[code] = action

        # -- Help
        help_menu = bar.addMenu(self.pick("&Ёрдам", "&Help"))
        self._menus.append((help_menu, ("&Ёрдам", "&Help")))
        for action in (
            self._act("Ёрдам", "Help", lambda: self.show_page("help"), "F1"),
            self._act("Тезкор тугмалар", "Keyboard shortcuts", self.show_shortcuts),
        ):
            help_menu.addAction(action)
            self._actions.append(action)
        help_menu.addSeparator()
        about = self._act("GateMPC ҳақида", "About GateMPC", self.show_about)
        help_menu.addAction(about)
        self._actions.append(about)

    # -------------------------------------------------------------- status bar

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.status_state = QLabel()
        bar.addPermanentWidget(self.status_state)
        self._refresh_status()

    def _refresh_status(self) -> None:
        missing = self.results.missing_files()
        stale = gdata.stale_results(self.paths)
        if missing:
            text = f"{len(missing)} / {len(gdata.RESULT_FILES)} " + self.pick(
                "натижа файли етишмайди", "result files missing")
            colour = COLORS["fail"]
        elif stale:
            text = self.pick("баъзи натижалар эскирган", "some results are stale")
            colour = COLORS["warn"]
        else:
            text = self.pick("натижалар тўлиқ", "results complete")
            colour = COLORS["measured"]
        self.status_state.setText(text)
        self.status_state.setStyleSheet(f"color: {colour}; padding-right: 8px;")
        self.statusBar().showMessage(str(self.paths.root))

    # -------------------------------------------------------------- behaviour

    def pick(self, uzbek: str, english: str) -> str:
        return i18n.pick(self.language, uzbek, english)

    def show_page(self, key: str) -> None:
        """Open a page, building it the first time it is asked for."""
        if key not in self._holders:
            return
        if key not in self._built:
            context = pages.Context(
                paths=self.paths,
                results=self.results,
                language=self.language,
                goto=self.show_page,
            )
            widget = pages.build_page(key, context)
            layout = self._holders[key].layout()
            assert layout is not None
            layout.addWidget(widget)
            self._built.add(key)
        self.stack.setCurrentWidget(self._holders[key])
        button = self.nav_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        action = self.page_actions.get(key)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        self._refresh_status()

    def current_key(self) -> str:
        index = self.stack.currentIndex()
        return pages.PAGE_KEYS[index] if 0 <= index < len(pages.PAGE_KEYS) else ""

    def _page_widget(self, key: str) -> QWidget | None:
        holder = self._holders.get(key)
        if holder is None:
            return None
        layout = holder.layout()
        if layout is None or not layout.count():
            return None
        item = layout.itemAt(0)
        return item.widget() if item is not None else None

    def toggle_sidebar(self) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.sidebar_action.setChecked(visible)

    # -- running from the menu ---------------------------------------------------

    def _reproduce_panel(self):
        self.show_page("reproduce")
        widget = self._page_widget("reproduce")
        return getattr(widget, "controller", None)

    def run_pipeline(self) -> None:
        panel = self._reproduce_panel()
        if panel is not None:
            panel.run_pipeline()

    def run_tests(self) -> None:
        panel = self._reproduce_panel()
        if panel is not None:
            panel.run_tests()

    def stop_running(self) -> None:
        """Stop whatever the page in front is running, if it is running anything."""
        widget = self._page_widget(self.current_key())
        controller = getattr(widget, "controller", None)
        stop = getattr(controller, "stop", None)
        if callable(stop):
            stop()

    # -- help --------------------------------------------------------------------

    def show_shortcuts(self) -> None:
        rows = [
            ("Ctrl+1 … Ctrl+9", self.pick("саҳифаларга ўтиш", "go to a page")),
            ("Ctrl+L", self.pick("тилни алмаштириш", "switch the language")),
            ("Ctrl+B", self.pick("ёнбош панелни яшириш", "hide the sidebar")),
            ("F1", self.pick("ёрдам саҳифаси", "the help page")),
            ("F5", self.pick("тўлиқ юришни бошлаш", "run the whole pipeline")),
            ("Ctrl+T", self.pick("тестларни юритиш", "run the tests")),
            ("Esc", self.pick("юритилаётган ишни тўхтатиш", "stop what is running")),
            ("Ctrl+Q", self.pick("чиқиш", "quit")),
        ]
        QMessageBox.information(
            self,
            self.pick("Тезкор тугмалар", "Keyboard shortcuts"),
            "\n".join(f"{keys:<16}{what}" for keys, what in rows),
        )

    def show_about(self) -> None:
        from .. import __version__

        environment = gdata.environment()
        QMessageBox.about(
            self,
            self.pick("GateMPC ҳақида", "About GateMPC"),
            self.pick(
                f"<b>GateMPC {__version__}</b><br><br>"
                "Реал затвор ўлчовлари бўйича идентификация қилинган канал модели ва "
                "предиктив бошқарув. Ойна натижаларни кўрсатади ва мақоланинг усулини "
                "сизнинг маълумотингизга қўллайди; ҳисоблашни "
                "<code>scripts/</code> даги скриптлар бажаради.<br><br>"
                f"Лойиҳа: {self.paths.root}<br>"
                f"Python {environment['python']} · {environment['platform']}",
                f"<b>GateMPC {__version__}</b><br><br>"
                "A canal model identified from real gate measurements, and predictive "
                "control. This window shows the results and applies the study's method to "
                "your own data; the computing is done by the scripts in "
                "<code>scripts/</code>.<br><br>"
                f"Project: {self.paths.root}<br>"
                f"Python {environment['python']} · {environment['platform']}",
            ),
        )

    # -- language ----------------------------------------------------------------

    def toggle_language(self) -> None:
        self.set_language("en" if self.language == "uz" else "uz")

    def set_language(self, language: str) -> None:
        language = i18n.normalise(language)
        if language == self.language:
            return
        current = self.current_key()
        self.language = language

        self.setWindowTitle(i18n.ui(language, "app_title"))
        self.title_label.setText(i18n.ui(language, "app_title"))
        self.strip_label.setText(i18n.ui(language, "headline_strip"))
        self._refresh_language_button()
        for key, button in self.nav_buttons.items():
            button.setText(pages.nav_label(key, language))
        for section, label in self.section_labels.items():
            label.setText(pages.section_label(section, language))
        for code, action in self.language_actions.items():
            action.setChecked(code == language)
        self._build_menus()
        self._refresh_status()

        # Pages carry their text inline, so the honest way to switch is to drop them
        # and rebuild the one being looked at.
        self._discard_pages()
        self.show_page(current or pages.PAGE_KEYS[0])

    def _refresh_language_button(self) -> None:
        other = "en" if self.language == "uz" else "uz"
        self.language_button.setText(i18n.ENDONYM[other])
        self.language_button.setToolTip(
            self.pick("Тилни алмаштириш (Ctrl+L)", "Switch language (Ctrl+L)")
        )

    # -- lifecycle ---------------------------------------------------------------

    def _add_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.toggle_language)

    def _discard_pages(self) -> None:
        for key in list(self._built):
            layout = self._holders[key].layout()
            assert layout is not None
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is None:
                    continue
                shutdown = getattr(widget, "shutdown", None)
                if callable(shutdown):
                    shutdown()
                widget.setParent(None)
                widget.deleteLater()
        self._built.clear()

    def closeEvent(self, event) -> None:  # pragma: no cover - window lifecycle
        self._discard_pages()
        super().closeEvent(event)
