"""Argument page — the pre-registration record, failures included.

The page's number is not written here. It comes from this module's position in
``pages.PAGES``, so a reordering cannot leave a stale number behind in a docstring.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QWidget

from .. import preregistration as record
from .. import widgets as w
from ..theme import COLORS, VERDICT_STYLE
from . import Context


def build(context: Context) -> QWidget:
    body = w.column(16)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Ўлчашдан олдин нима ёзилган эди, ва нима чиқди",
                "What was written before each measurement, and what came out",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Ҳар бир сўров ишга туширилишидан олдин кутилаётган натижа ва қарор "
                "қоидаси ёзилади; натижани кўргандан кейин улар ўзгартирилмайди. "
                "Қуйидаги ёзувларда: иккита катталик умуман баҳоланмади (A<sub>s</sub> ва "
                "z<sub>0</sub>), иккита кутиш ўлчов билан рад этилди, ва мезони "
                "бажарилган иккита фараз кейин қайтариб олинди. Улар ҳам шу ерда, чунки "
                "уларни олиб ташлаш қолганларининг қийматини йўқотади.",
                "Before a query is run, the expected result and the decision rule are "
                "written down; once the result is seen they are not edited. Among the "
                "entries below: two quantities could not be estimated at all (A<sub>s</sub> "
                "and z<sub>0</sub>), two expectations were contradicted by the measurement, "
                "and two hypotheses whose criteria were met were later withdrawn. They are "
                "here because removing them would destroy the value of the rest.",
            )
        )
    )

    layout.addWidget(_summary(context))
    for entry in record.RECORD:
        layout.addWidget(_entry_card(context, entry))
    return w.wrap_scroll(body)


# ----------------------------------------------------------------------- summary


def _summary(context: Context) -> QWidget:
    counts = record.counts()
    cards = []
    for verdict, count in counts.items():
        foreground, background, uzbek, english = VERDICT_STYLE[verdict.value]
        card = w.NumberCard(
            str(count),
            context.pick(uzbek, english),
            "src/gatempc/gui/preregistration.py",
        )
        card.setStyleSheet(
            f"QFrame#NumberCard {{ background: {background}; "
            f"border: 1px solid {foreground}; border-radius: 10px; }}"
            f"QLabel#NumberValue {{ color: {foreground}; }}"
        )
        cards.append(card)
    holder = w.Card(
        context.pick("Ўнта ёзувнинг ҳисоби", "The ten entries, counted"),
        context.pick(
            "Ҳар бир ёзувнинг тагида уни ёпган натижа файли турибди, шунинг учун "
            "даъвони журналга ишонмасдан текшириш мумкин.",
            "Each entry names the result file that closes it, so the claim can be checked "
            "without taking the log on trust.",
        ),
    )
    holder.add(w.card_row(cards, columns=4))
    return holder


# ------------------------------------------------------------------------ entry


def _entry_card(context: Context, entry: record.Entry) -> QWidget:
    foreground, background, uzbek_label, english_label = VERDICT_STYLE[entry.verdict.value]
    card = w.Card()

    heading = QHBoxLayout()
    heading.setSpacing(10)
    title = w.section_title(
        f"{entry.key} — {context.pick(entry.question_uz, entry.question_en)}"
    )
    heading.addWidget(title, 1)
    heading.addWidget(
        w.chip(context.pick(uzbek_label, english_label), foreground, background), 0
    )
    card.add_layout(heading)

    card.add(
        w.paragraph(
            "<b>"
            + context.pick("Олдиндан ёзилган", "Written in advance")
            + ".</b> "
            + context.pick(entry.expected_uz, entry.expected_en)
        )
    )
    measured = w.paragraph(
        "<b>"
        + context.pick("Ўлчанди", "Measured")
        + ".</b> "
        + context.pick(entry.measured_uz, entry.measured_en)
    )
    measured.setStyleSheet(f"color: {COLORS['ink']};")
    card.add(measured)

    footer = []
    if entry.script:
        footer.append(f"scripts/{entry.script}")
    footer.extend(_evidence_paths(entry))
    if footer:
        origin = w.paragraph("  ·  ".join(footer))
        origin.setObjectName("NumberSource")
        card.add(origin)
    return card


def _evidence_paths(entry: record.Entry) -> list[str]:
    paths = []
    for reference in entry.evidence:
        file_name, _, dotted = reference.partition(":")
        paths.append(f"results/{file_name}.json" + (f" -> {dotted}" if dotted else ""))
    return paths
