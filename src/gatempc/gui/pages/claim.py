"""Page 1 — the claim, in the fewest numbers that carry it."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from .. import data as gdata
from .. import widgets as w
from . import Context

NAV = ("1 · Даъво", "1 · The claim")

#: The widest of the four within-period spreads of kappa. Rounded, this is the 0.01%
#: the claim quotes; the exact figure is shown next to it.
KAPPA_REFERENCE = "discharge_coefficient:by_period.after.spread_by_relative_opening"
#: The accuracy USGS itself states for its best-rated discharge measurements.
LIMIT_REFERENCE = "gate_law_validation:by_rating.Good.stated_accuracy"


def build(context: Context) -> QWidget:
    results = context.results
    body = w.column(18)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Затворли иншоотда эълон қилинган сарф — ўлчов эмас",
                "At a gated structure, the published discharge is not a measurement",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "У затвор очилиши ва иккита сатҳдан рейтинг тенгламаси билан "
                "<b>ҳисобланади</b>. Шунинг учун затвор қонунини ўша қаторга қарши "
                "«текшириш» тавтология — у деярли мукаммал мослик кўрсатади. Қуйидаги "
                "иккита сон ўша тузоқнинг нархини ўлчайди.",
                "It is <b>computed</b> from the gate opening and two stages by a rating "
                "equation. Checking a gate law against that series is therefore a "
                "tautology: it returns a near-perfect fit. The two numbers below measure "
                "what the trap costs.",
            )
        )
    )

    layout.addWidget(_headline(context))
    layout.addWidget(_road(context))
    layout.addWidget(_what_it_rests_on(context, results))
    layout.addWidget(_scope(context))
    return w.wrap_scroll(body)


# ---------------------------------------------------------------------- headline


def _headline(context: Context) -> QWidget:
    results = context.results
    circular = results.number(KAPPA_REFERENCE)
    limit = results.number(LIMIT_REFERENCE)

    if circular and limit:
        exact = limit / circular
        ratio_value = f"≈{round(exact / 100) * 100:.0f}×"
        ratio_note = context.pick(
            f"юмалоқлаштирилган иккита сондан: 5% ÷ 0.01%. Аниқ нисбат — {exact:.0f}×",
            f"from the two rounded figures: 5% ÷ 0.01%. The exact ratio is {exact:.0f}×",
        )
    else:
        ratio_value = "—"
        ratio_note = context.pick("натижа файли етишмайди", "a result file is missing")

    card = w.Card(
        context.pick(
            "Тузоқнинг нархи — иккита ўлчанган сон ва улар орасидаги фарқ",
            "The cost of the trap — two measured figures and the gap between them",
        )
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    KAPPA_REFERENCE,
                    context.pick(
                        "Доиравий текширув: рейтинг даври ичида κ нинг тарқалиши. "
                        "Мослик шунчалик тор — чунки у ўзини ўзи текширмоқда.",
                        "The circular check: the spread of κ within a rating period. The "
                        "fit is this tight because it is checking itself.",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 4),
                    tone="circular",
                    note=context.pick(
                        "тўрттасининг энг кенгги; даъвода ≈0.01% деб келтирилади",
                        "the widest of the four; the claim quotes it as ≈0.01%",
                    ),
                ),
                w.number_card(
                    results,
                    LIMIT_REFERENCE,
                    context.pick(
                        "Ҳалол чегара: USGS нинг ўзи `Good` синфидаги дала ўлчови учун "
                        "эълон қилган аниқлиги. Мустақил ўлчов бундан нозикроқ ажрата "
                        "олмайди.",
                        "The honest limit: the accuracy USGS itself states for a `Good` "
                        "field measurement. No independent measurement resolves finer.",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 0),
                    tone="measured",
                ),
                w.NumberCard(
                    ratio_value,
                    context.pick(
                        "Икки чегара орасидаги фарқ. Доиравий текширув борлиқда "
                        "бўлмаган аниқликни кўрсатади.",
                        "The gap between the two limits. The circular check reports a "
                        "precision that does not exist.",
                    ),
                    context.pick(
                        f"ҳисобланди: {LIMIT_REFERENCE.split(':')[1]} ÷ "
                        f"{KAPPA_REFERENCE.split(':')[1]}",
                        f"computed: {LIMIT_REFERENCE.split(':')[1]} ÷ "
                        f"{KAPPA_REFERENCE.split(':')[1]}",
                    ),
                    tone="accent",
                    note=ratio_note,
                ),
            ],
            columns=3,
        )
    )
    return card


# -------------------------------------------------------------------------- road


def _road(context: Context) -> QWidget:
    card = w.Card(
        context.pick("Мақоланинг йўли — тўртта қадам", "The road the paper takes — four steps")
    )
    steps = (
        (
            "circularity",
            context.pick("1. Детектор", "1. The detector"),
            context.pick(
                "Доиравийликни қандай аниқлаш мумкин — датумсиз, фақат эълон қилинган "
                "қаторлардан. Иккита иншоотда текширилди.",
                "How to detect the circularity — datum-free, from the published series "
                "alone. Checked at two structures.",
            ),
        ),
        (
            "independent",
            context.pick("2. Қочиш йўли", "2. The way out"),
            context.pick(
                "Мустақил дала гаугинглари. Эталоннинг идеал қонуни улар билан "
                "текширилади — асбоб ўрнатмасдан.",
                "Independent field gaugings. The benchmark's ideal law is checked "
                "against them, with no instrument installed.",
            ),
        ),
        (
            "archive",
            context.pick("3. Чегаралар", "3. The limits"),
            context.pick(
                "Очиқ архив нимани беради ва нимани бермайди — иккита параметр умуман "
                "баҳоланмайди.",
                "What the open archive gives and what it does not — two parameters are "
                "not identifiable at all.",
            ),
        ),
        (
            "control",
            context.pick("4. Нархи", "4. What it costs"),
            context.pick(
                "Бошқарувчи эталон қонунини кўтарганда нима йўқотади — ёпиқ ҳалқада, "
                "100 жуфтланган такрорда ўлчанди.",
                "What a controller loses by carrying the benchmark law — measured in "
                "closed loop over 100 paired replicates.",
            ),
        ),
    )
    for key, title, text in steps:
        row = QHBoxLayout()
        row.setSpacing(12)
        button = QPushButton(title)
        button.setMinimumWidth(140)
        button.clicked.connect(lambda _checked=False, target=key: context.goto(target))
        row.addWidget(button)
        row.addWidget(w.paragraph(text), 1)
        card.add_layout(row)
    return card


# ------------------------------------------------------------- what it rests on


def _what_it_rests_on(context: Context, results: gdata.Results) -> QWidget:
    card = w.Card(
        context.pick(
            "Даъво нимага таянади — ҳар бир сон ўз файлидан",
            "What the claim rests on — every figure from its own file",
        ),
        context.pick(
            "Ҳеч бир сон бу ерга қўлда киритилмаган. Ҳар бирининг тагида уни ўқиган "
            "файл ва калит турибди.",
            "No figure here was typed in. Each one carries the file and the key it was "
            "read from.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "gate_law_validation:accepted",
                    context.pick(
                        "мустақил дала гаугинги қабул қилинди (жами 317 тадан)",
                        "independent field gaugings accepted (of 317)",
                    ),
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law_validation:relative_residual.median",
                    context.pick(
                        "эталоннинг идеал қонунининг силжиши — ўша 77 гаугингда",
                        "bias of the benchmark's ideal law across those 77 gaugings",
                    ),
                    formatter=lambda v: gdata.as_signed_percent(v, 2),
                    tone="measured",
                ),
                w.NumberCard(
                    _inside_stated(results, context),
                    context.pick(
                        "гаугинг ўлчовнинг ўз эълон қилинган аниқлиги ичида "
                        "(Good 5%, Fair 8%)",
                        "gaugings inside the measurement's own stated accuracy "
                        "(Good 5%, Fair 8%)",
                    ),
                    "results/gate_law_validation.json -> by_rating.*.n_outside_stated",
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "second_structure:rating_fit.median_abs_relative_residual",
                    context.pick(
                        "иккинчи иншоотда рейтинг мослигининг медиана қолдиғи — "
                        "доиравийлик такрорланади, шакли бошқа",
                        "median residual of the rating fit at the second structure — the "
                        "circularity repeats in a different form",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.step_relative",
                    context.pick(
                        "сув йили чегарасидаги белгиланмаган рейтинг сакраши",
                        "the undocumented rating step at the water-year boundary",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "control_comparison:controllers.MPC.delta.median",
                    context.pick(
                        "MPC да эталон қонунини кўтаришнинг нархи (δ, 100 такрор медианаси)",
                        "what carrying the benchmark law costs MPC (δ, median of 100 replicates)",
                    ),
                    formatter=lambda v: gdata.as_signed_percent(v, 3),
                    tone="accent",
                ),
            ],
            columns=3,
        )
    )
    return card


def _inside_stated(results: gdata.Results, context: Context) -> str:
    accepted = results.number("gate_law_validation:accepted")
    by_rating = results.value("gate_law_validation:by_rating")
    if accepted is None or not by_rating.ok or not isinstance(by_rating.value, dict):
        return "—"
    outside = 0
    for block in by_rating.value.values():
        if isinstance(block, dict):
            outside += int(block.get("n_outside_stated", 0) or 0)
    return f"{int(accepted) - outside} / {int(accepted)}"


# ------------------------------------------------------------------------- scope


def _scope(context: Context) -> QWidget:
    return w.Card(
        context.pick("Нима даъво қилинмайди", "What is not claimed"),
        context.pick(
            "Бу иш затвор гидравликасига янги тенглама таклиф қилмайди ва эталон "
            "масалаларни рад этмайди. Аксинча: <b>эталоннинг идеаллаштирилган ботирилган "
            "тешик қонуни реал иншоотда мустақил ўлчовлар билан текширилганда ишлайди.</b> "
            "Даъво — ўша қонунни <i>қандай</i> текшириш ҳақида: эълон қилинган узлуксиз "
            "сарф қаторига қарши текшириш ҳеч нарса кўрсатмайди, чунки қатор ўша "
            "тенгламанинг ўз чиқиши. Иккита иншоотда рейтингнинг шакли ҳар хил бўлди — "
            "демак детектор шаклга эмас, белгига таянади.",
            "This work proposes no new gate-hydraulics equation and does not reject the "
            "benchmark problems. The opposite: <b>the benchmark's idealised submerged-orifice "
            "law holds up at a real structure when it is checked against independent "
            "measurements.</b> The claim is about <i>how</i> to check it. Checking against "
            "the published continuous discharge shows nothing, because that series is the "
            "equation's own output. The two structures used different rating forms, so the "
            "detector rests on a signature rather than on a particular formula.",
        ),
    )
