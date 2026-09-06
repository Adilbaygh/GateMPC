"""Colours, fonts and one stylesheet.

Two constraints shaped this. First, the window has to read the same on Windows, macOS
and Linux, so every font is given as a family list ending in a face that ships with the
platform and covers Cyrillic; nothing is hard-coded to one operating system. Second,
the study is about telling a measured number from a computed one, so the palette gives
those two states different colours and never uses colour alone to carry that meaning —
the wording says it too.
"""

from __future__ import annotations

#: Family lists, in the order Qt should try them. Every list ends in a face that
#: exists on the platform it targets and renders Cyrillic.
FONT_UI = (
    '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", '
    '"Noto Sans", "DejaVu Sans", sans-serif'
)
FONT_MONO = (
    '"Cascadia Mono", "SF Mono", Menlo, Consolas, '
    '"DejaVu Sans Mono", "Noto Sans Mono", monospace'
)

COLORS: dict[str, str] = {
    # surfaces
    "page": "#f4f6f7",
    "card": "#ffffff",
    "sidebar": "#12242e",
    "sidebar_hover": "#1c3542",
    "sidebar_active": "#0f7d8c",
    "header": "#0d1b23",
    "border": "#d8dee2",
    "border_strong": "#b7c2c8",
    # text
    "ink": "#12242e",
    "ink_soft": "#5a6b74",
    "ink_faint": "#8a99a1",
    "on_dark": "#e8eef1",
    "on_dark_soft": "#93a7b1",
    # meaning
    "accent": "#0f7d8c",       # the water/measurement accent
    "accent_soft": "#e2f1f3",
    "circular": "#b3541e",     # a number produced by a rating
    "circular_soft": "#fbeee5",
    "measured": "#1f7a4d",     # a number from an independent measurement
    "measured_soft": "#e6f3ec",
    "warn": "#a3601a",
    "warn_soft": "#fcf1de",
    "fail": "#a92f2f",
    "fail_soft": "#fbeaea",
    "neutral_soft": "#eef1f3",
}

#: How each pre-registration verdict is shown. The label is spelled out so the state
#: survives a black-and-white printout or a colour-blind reader.
VERDICT_STYLE: dict[str, tuple[str, str, str, str]] = {
    # key: (foreground, background, uzbek label, english label)
    "supported": (COLORS["measured"], COLORS["measured_soft"], "Тасдиқланди", "Supported"),
    "withdrawn": (COLORS["circular"], COLORS["circular_soft"], "Қайтариб олинди", "Withdrawn"),
    "not_identified": (COLORS["fail"], COLORS["fail_soft"], "Баҳоланмайди", "Not identified"),
    "expectation_wrong": (COLORS["warn"], COLORS["warn_soft"], "Кутиш нотўғри", "Expectation wrong"),
}


APP_STYLE = f"""
* {{
    font-family: {FONT_UI};
}}

QWidget {{
    color: {COLORS['ink']};
}}

QMainWindow, QWidget#Page, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {COLORS['page']};
}}

/* ------------------------------------------------------------------ header */

QFrame#Header {{
    background: {COLORS['header']};
    border: none;
}}

QLabel#HeaderTitle {{
    color: #ffffff;
    font-size: 17px;
    font-weight: 600;
}}

QLabel#HeaderStrip {{
    color: {COLORS['on_dark_soft']};
    font-size: 12px;
    letter-spacing: 0.3px;
}}

QPushButton#LanguageButton {{
    background: rgba(255, 255, 255, 0.10);
    color: {COLORS['on_dark']};
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 13px;
    padding: 5px 14px;
    font-size: 12px;
}}

QPushButton#LanguageButton:hover {{
    background: rgba(255, 255, 255, 0.18);
}}

/* ----------------------------------------------------------------- sidebar */

QFrame#Sidebar {{
    background: {COLORS['sidebar']};
    border: none;
}}

QPushButton#NavButton {{
    background: transparent;
    color: {COLORS['on_dark_soft']};
    border: none;
    border-left: 3px solid transparent;
    padding: 11px 16px 11px 13px;
    text-align: left;
    font-size: 13px;
}}

QPushButton#NavButton:hover {{
    background: {COLORS['sidebar_hover']};
    color: {COLORS['on_dark']};
}}

QPushButton#NavButton:checked {{
    background: {COLORS['sidebar_hover']};
    color: #ffffff;
    border-left: 3px solid {COLORS['accent']};
    font-weight: 600;
}}

QLabel#SidebarCaption {{
    color: #6d838f;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 16px 16px 6px 16px;
}}

/* -------------------------------------------------------------------- card */

QFrame#Card {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}

QLabel#CardTitle {{
    font-size: 15px;
    font-weight: 600;
}}

QLabel#CardBody {{
    color: {COLORS['ink_soft']};
    font-size: 13px;
}}

QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 600;
}}

QLabel#PageLead {{
    color: {COLORS['ink_soft']};
    font-size: 14px;
}}

QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS['ink']};
}}

/* ------------------------------------------------------------ number cards */

QFrame#NumberCard {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}

QLabel#NumberValue {{
    font-size: 27px;
    font-weight: 600;
}}

QLabel#NumberCaption {{
    font-size: 12px;
    color: {COLORS['ink_soft']};
}}

QLabel#NumberSource {{
    font-family: {FONT_MONO};
    font-size: 10px;
    color: {COLORS['ink_faint']};
}}

QLabel#Chip {{
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}}

/* ------------------------------------------------------------------ tables */

QTableWidget {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: {COLORS['border']};
    font-size: 12px;
    selection-background-color: {COLORS['accent_soft']};
    selection-color: {COLORS['ink']};
}}

QHeaderView::section {{
    background: {COLORS['neutral_soft']};
    color: {COLORS['ink_soft']};
    border: none;
    border-right: 1px solid {COLORS['border']};
    border-bottom: 1px solid {COLORS['border']};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 700;
}}

QTableWidget::item {{
    padding: 4px 8px;
}}

/* ----------------------------------------------------------------- buttons */

QPushButton {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 7px;
    padding: 7px 15px;
    font-size: 13px;
}}

QPushButton:hover {{
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}

QPushButton:disabled {{
    color: {COLORS['ink_faint']};
    border-color: {COLORS['border']};
}}

QPushButton#Primary {{
    background: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#Primary:hover {{
    background: #0c6b78;
    color: #ffffff;
}}

QPushButton#Primary:disabled {{
    background: {COLORS['border_strong']};
    border-color: {COLORS['border_strong']};
    color: #ffffff;
}}

QPushButton#Link {{
    background: transparent;
    border: none;
    color: {COLORS['accent']};
    padding: 2px 4px;
    font-size: 12px;
    text-align: left;
}}

QPushButton#Link:hover {{
    text-decoration: underline;
}}

/* -------------------------------------------------------------- log output */

QPlainTextEdit#Console {{
    background: #0e1a21;
    color: #cfe3e8;
    border: 1px solid {COLORS['header']};
    border-radius: 8px;
    font-family: {FONT_MONO};
    font-size: 12px;
    padding: 8px;
}}

/* ------------------------------------------------------------ misc widgets */

QScrollArea {{
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border_strong']};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS['ink_faint']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS['border_strong']};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QFrame#Divider {{
    background: {COLORS['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QComboBox {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 13px;
}}

QComboBox:hover {{
    border-color: {COLORS['accent']};
}}

QToolTip {{
    background: {COLORS['header']};
    color: {COLORS['on_dark']};
    border: none;
    padding: 6px 8px;
    font-size: 12px;
}}

/* -------------------------------------------------------- menu and status bar */

QMenuBar {{
    background: {COLORS['header']};
    color: {COLORS['on_dark']};
    border: none;
    padding: 2px 6px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 5px;
}}

QMenuBar::item:selected {{
    background: rgba(255, 255, 255, 0.13);
}}

QMenu {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border_strong']};
    padding: 5px;
}}

QMenu::item {{
    padding: 6px 26px 6px 20px;
    border-radius: 5px;
}}

QMenu::item:selected {{
    background: {COLORS['accent_soft']};
    color: {COLORS['ink']};
}}

QMenu::item:disabled {{
    color: {COLORS['ink_faint']};
    font-size: 10px;
    font-weight: 700;
    padding-top: 8px;
}}

QMenu::separator {{
    height: 1px;
    background: {COLORS['border']};
    margin: 5px 8px;
}}

QStatusBar {{
    background: {COLORS['card']};
    border-top: 1px solid {COLORS['border']};
    color: {COLORS['ink_faint']};
    font-size: 11px;
}}

QStatusBar::item {{
    border: none;
}}

/* --------------------------------------------------------------- form inputs */

QLineEdit {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 13px;
}}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {COLORS['accent']};
}}

QLineEdit:read-only {{
    background: {COLORS['neutral_soft']};
    color: {COLORS['ink_soft']};
}}

QDoubleSpinBox, QSpinBox {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 7px;
    padding: 6px 8px;
    font-size: 13px;
}}

QDoubleSpinBox:disabled, QSpinBox:disabled {{
    background: {COLORS['neutral_soft']};
    color: {COLORS['ink_faint']};
}}

QRadioButton, QCheckBox {{
    font-size: 13px;
    spacing: 7px;
}}
"""
