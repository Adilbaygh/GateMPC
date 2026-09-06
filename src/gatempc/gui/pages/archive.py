"""Argument page — what the open archive gives, and what it refuses to give.

The page's number is not written here. It comes from this module's position in
``pages.PAGES``, so a reordering cannot leave a stale number behind in a docstring.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from .. import data as gdata
from .. import widgets as w
from . import Context


def build(context: Context) -> QWidget:
    body = w.column(18)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Очиқ архив нимани беради ва нимани бермайди",
                "What the open archive gives, and what it does not",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Иккита параметр умуман баҳоланмайди, ва бу — камчилик эмас, ўлчанган "
                "натижа. Иккаласи учун ҳам тушиб қолиш йўли <b>ўлчашдан олдин</b> "
                "ёзилган эди, шунинг учун натижадан кейин ҳеч нарса ўзгартирилмади.",
                "Two parameters cannot be estimated at all, and that is a measured result "
                "rather than a shortcoming. For both of them a fallback was written "
                "<b>before</b> the measurement, so nothing had to be changed afterwards.",
            )
        )
    )

    layout.addWidget(_not_identified(context))
    layout.addWidget(_defects(context))
    layout.addWidget(_coverage(context))
    layout.addWidget(_excitation(context))
    _add_figures(context, layout, (3, 4))
    for name, uz, en in (
        ("table_1_series.csv", "Жадвал 1 — қаторлар", "Table 1 — the series"),
        ("table_2_folds.csv", "Жадвал 2 — fold'лар", "Table 2 — the folds"),
        ("table_3_defects.csv", "Жадвал 3 — маълумот нуқсонлари", "Table 3 — data defects"),
        (
            "table_5_identifiability.csv",
            "Жадвал 5 — баҳоланувчанлик",
            "Table 5 — identifiability",
        ),
    ):
        layout.addWidget(
            w.TableCard(
                context.paths.tables / name,
                context.paths,
                context.language,
                title=context.pick(uz, en),
            )
        )
    return w.wrap_scroll(body)


# ---------------------------------------------------------------- not identified


def _not_identified(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Иккита параметр баҳоланмайди — H0c-1 ва H0c-2",
            "Two parameters are not identifiable — H0c-1 and H0c-2",
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>Бьефнинг сув юзаси майдони A<sub>s</sub>.</b> Маълумот етарли эди — "
                "фильтрлардан кейин 3055 воқеа қолди — лекин усул етарли эмас: IQR "
                "медиананинг 123% и, ва 56 та fold жуфтлигидан 32 таси бир-бирига зид. "
                "Медиана ойна узунлиги билан монотон ўсади, яъни у конвергенция эмас, "
                "силжиш. Диагноз: кузатилмайдиган кириш сарфининг ўзгармаслиги фарази "
                "бузилади.",
                "<b>The pool surface area A<sub>s</sub>.</b> The data were sufficient — 3055 "
                "events survived the filters — but the method was not: the IQR is 123% of "
                "the median and 32 of 56 fold pairs contradict each other. The median grows "
                "monotonically with the window length, which is drift rather than "
                "convergence. The diagnosis is that the assumption of a steady unobserved "
                "inflow does not hold.",
            )
        )
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "archive_diagnostics:storage.n_accepted",
                    context.pick("қабул қилинган воқеа (мезон: ≥ 500)", "accepted events (criterion: ≥ 500)"),
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:storage.iqr_ratio",
                    context.pick(
                        "IQR ⁄ медиана (мезон: < 0.5)", "IQR ⁄ median (criterion: below 0.5)"
                    ),
                    formatter=lambda v: f"{v:.3f}",
                    tone="fail",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:storage.negative_fraction",
                    context.pick(
                        "манфий баҳолар улуши — физик жиҳатдан имконсиз",
                        "share of negative estimates — physically impossible",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 1),
                    tone="fail",
                ),
            ],
            columns=3,
        )
    )
    card.add(w.divider())
    card.add(
        w.paragraph(
            context.pick(
                "<b>Затвор остонаси z<sub>0</sub>.</b> Мослик оптимум атрофида 2.975 ft "
                "ли қидирув соҳасининг 0.82 футида ажратиб бўлмас даражада текис, ва "
                "оптимумда эркин оқим улуши амалда ноль. Демак маълумот тўлиқ ботирилган "
                "талқинни фаол афзал кўради — бу эталоннинг «затворлар ҳар доим ботирилган» "
                "фаразини реал архив билан тасдиқлайди. Модел бир параметрли шаклга ўтади: "
                "<b>Q = Γ·a·√(2g·(H₁−H₂))</b>.",
                "<b>The gate sill z<sub>0</sub>.</b> Around the optimum the fit is "
                "indistinguishably flat across 0.82 ft of the 2.975 ft searched, and the "
                "free-flow fraction there is effectively zero. The data actively prefer the "
                "fully submerged reading, which confirms the benchmark's “gates are always "
                "submerged” assumption against a real archive. The model collapses to one "
                "parameter: <b>Q = Γ·a·√(2g·(H₁−H₂))</b>.",
            )
        )
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "gate_law:h0c2_second_condition.flat_valley_width_ft",
                    context.pick(
                        "текис водийнинг кенглиги, ft — 2.975 ft ли соҳадан",
                        "width of the flat valley, ft — out of a 2.975 ft range",
                    ),
                    formatter=lambda v: f"{v:.2f}",
                    tone="fail",
                ),
                w.number_card(
                    results,
                    "gate_law:full_fit.free_fraction",
                    context.pick(
                        "оптимумдаги эркин оқим улуши",
                        "free-flow fraction at the optimum",
                    ),
                    formatter=lambda v: f"{v:.2e}",
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law:n_usable_samples",
                    context.pick(
                        "мослаштиришда ишлатилган ўлчов",
                        "observations used in the fit",
                    ),
                ),
            ],
            columns=3,
        )
    )
    return card


# ----------------------------------------------------------------------- defects


def _defects(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "«Approved» белгиси тозаликнинг кафолати эмас",
            "An “Approved” flag is no guarantee of clean data",
        ),
        context.pick(
            "Архивда 100% `Approved` деб белгиланган, лекин физик жиҳатдан имконсиз "
            "қийматлар бор. Энг ёрқини — 2015 йилдаги максимал сарф: у ўша сайтдаги 317 "
            "гаугингнинг энг каттасидан 13.9 баробар, бошқа йилларнинг энг юқори "
            "қийматидан эса 13.0 баробар катта. 2015 fold рўйхатида эмас, шунинг учун "
            "бирорта натижа унга боғлиқ эмас — лекин қоида ҳамма йилга тегишли: тозалаш "
            "қатлами сифат назоратини ўзи қилиши шарт.",
            "The archive contains values flagged 100% `Approved` that are physically "
            "impossible. The clearest is the 2015 annual maximum: it is 13.9 times the "
            "largest of the 317 gaugings at that site and 13.0 times the highest of the "
            "other annual maxima. 2015 is not among the folds, so no result depends on it — "
            "but the lesson applies to every year: the cleaning layer has to do its own "
            "quality control.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "archive_diagnostics:extremes.gate_opening.min.value",
                    context.pick(
                        "манфий затвор очилиши, ft — сенсор нолининг силжиши",
                        "negative gate opening, ft — a sensor zero offset",
                    ),
                    formatter=lambda v: f"{v:+.2f}",
                    tone="warn",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:extremes.headwater.min.value",
                    context.pick(
                        "юқори бьефнинг минимуми, ft (2021) — канал бўшатилган",
                        "minimum headwater, ft (2021) — the canal was drawn down",
                    ),
                    formatter=lambda v: f"{v:.2f}",
                    tone="warn",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:extremes.discharge.max.value",
                    context.pick(
                        "fold йилларидаги максимал сарф, ft³/s",
                        "maximum discharge across the fold years, ft³/s",
                    ),
                    formatter=lambda v: gdata.as_number(v, 0),
                ),
            ],
            columns=3,
        )
    )
    return card


# ---------------------------------------------------------------------- coverage


def _coverage(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Қамров — саккиз fold, ҳар бири бир йил",
            "Coverage — eight folds, one year each",
        ),
        context.pick(
            "Тўрттала қатор бир вақтда мавжуд бўлган сатрлар, ва улардан фильтрлардан "
            "кейин қолганлари. Fold рўйхатига кириш қоидаси олдиндан ёзилган: тўрттала "
            "сигнал тўлиқ йил давомида мавжуд бўлиши ва биргаликдаги қамров 20 000 дан "
            "ошиши керак.",
            "Rows where all four series are present, and how many of them survive the "
            "filters. The rule for admitting a year was written in advance: all four "
            "signals must be present through the year and their joint coverage must exceed "
            "20 000 readings.",
        ),
    )
    coverage = results.value("archive_diagnostics:coverage")
    if coverage.ok and isinstance(coverage.value, dict):
        pairs = []
        for year in sorted(coverage.value):
            block = coverage.value[year]
            if not isinstance(block, dict):
                continue
            pairs.append(
                (
                    str(year),
                    context.pick(
                        f"{gdata.as_number(block.get('rows_with_all_four'))} сатр  ·  "
                        f"{gdata.as_number(block.get('usable'))} яроқли",
                        f"{gdata.as_number(block.get('rows_with_all_four'))} rows  ·  "
                        f"{gdata.as_number(block.get('usable'))} usable",
                    ),
                )
            )
        card.add(w.key_values(pairs, columns=2))
    checks = results.value("archive_diagnostics:reproduction_checks")
    if checks.ok and isinstance(checks.value, list):
        failed = [c for c in checks.value if isinstance(c, dict) and not c.get("ok")]
        card.add(
            w.paragraph(
                context.pick(
                    f"Оммавий йўл хусусий йўлни такрорлади: {len(checks.value)} та "
                    f"текширувдан {len(checks.value) - len(failed)} таси мос, "
                    f"{len(failed)} таси мос эмас.",
                    f"The public path reproduced the private one: "
                    f"{len(checks.value) - len(failed)} of {len(checks.value)} checks "
                    f"matched, {len(failed)} did not.",
                )
            )
        )
    return card


# -------------------------------------------------------------------- excitation


def _excitation(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Қўзғатиш — идентификация нимага таянади",
            "Excitation — what the identification rests on",
        ),
        context.pick(
            "Затвор ҳақиқатан ҳаракатланади, ва ҳаракатлар кичик эмас. Бу муҳим, чунки "
            "қимирламайдиган затвордан затвор қонунини ажратиб бўлмайди.",
            "The gate really does move, and not by small amounts. That matters, because a "
            "gate law cannot be separated from a gate that never moves.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "archive_diagnostics:gate_movement.moved",
                    context.pick(
                        "ҳаракат қайд этилган жуфтлик (273 100 тадан)",
                        "consecutive pairs with a movement (of 273 100)",
                    ),
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:gate_movement.above_threshold",
                    context.pick(
                        "0.02 ft остонасидан катта ҳаракат",
                        "movements above the 0.02 ft threshold",
                    ),
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:gate_movement.q95_move_ft",
                    context.pick("ҳаракатларнинг 95-квантили, ft", "95th percentile move, ft"),
                    formatter=lambda v: f"{v:.2f}",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:gate_movement.max_move_ft",
                    context.pick("энг катта ҳаракат, ft", "largest single move, ft"),
                    formatter=lambda v: f"{v:.2f}",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:gate_movement.distinct_step_sizes",
                    context.pick(
                        "ҳар хил қадам ўлчами — дискрет бошқарув изи",
                        "distinct step sizes — the trace of discrete control",
                    ),
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.overnight_move",
                    context.pick(
                        "энг катта бир кечалик κ силжиши — рейтинг сакрашининг ўзи",
                        "largest overnight shift in κ — the rating step itself",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="circular",
                ),
            ],
            columns=3,
        )
    )
    return card


# ----------------------------------------------------------------------- figures


def _add_figures(context: Context, layout, numbers: tuple[int, ...]) -> None:
    available = {figure.number: figure for figure in gdata.figures(context.paths, context.results)}
    for number in numbers:
        figure = available.get(number)
        if figure is not None:
            layout.addWidget(w.FigureCard(figure, context.paths, context.language))
