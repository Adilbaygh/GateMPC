"""Argument page — the detector, and the two structures it was run on.

The page's number is not written here. It comes from this module's position in
``pages.PAGES``, so a reordering cannot leave a stale number behind in a docstring.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ... import results as gdata
from .. import widgets as w
from . import Context


def build(context: Context) -> QWidget:
    body = w.column(18)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Доиравийликнинг детектори, ва у иккита иншоотда нима кўрсатди",
                "The detector for the circularity, and what it showed at two structures",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Детектор датумга муҳтож эмас ва фақат эълон қилинган қаторларга таянади, "
                "шунинг учун уни ҳар ким такрорлай олади.",
                "The detector needs no datum and uses only the published series, so anyone "
                "can repeat it.",
            )
        )
    )

    layout.addWidget(_detector(context))
    layout.addWidget(_primary(context))
    layout.addWidget(_step(context))
    layout.addWidget(_second(context))
    layout.addWidget(_general(context))
    _add_figures(context, layout, (1, 9, 10))
    return w.wrap_scroll(body)


# ---------------------------------------------------------------------- detector


def _detector(context: Context) -> QWidget:
    card = w.Card(
        context.pick("Детектор нима қилади", "What the detector does"),
        context.pick(
            "Эълон қилинган сарфни затвор очилиши ва напор фарқига бўламиз:<br><br>"
            "&nbsp;&nbsp;<b>κ = Q ⁄ (a·√(2g·Δh))</b>&nbsp;&nbsp;— идеал ботирилган тешик "
            "қонунида бу катталик <b>C<sub>d</sub>·W<sub>эфф</sub></b> га тенг.<br><br>"
            "Агар Q ҳақиқий ўлчов бўлса, κ дала ўлчовининг ноаниқлиги даражасида "
            "тебранади. Агар Q айнан шу тенглама билан ҳисобланган бўлса, κ арифметик "
            "аниқликда доимий бўлади. Оралиқда талқин қилинадиган нарса йўқ: фарқ уч "
            "тартибда.",
            "Divide the published discharge by the opening and the head:<br><br>"
            "&nbsp;&nbsp;<b>κ = Q ⁄ (a·√(2g·Δh))</b>&nbsp;&nbsp;— under the ideal "
            "submerged-orifice law this equals <b>C<sub>d</sub>·W<sub>eff</sub></b>.<br><br>"
            "If Q is a real measurement, κ scatters at the level of field-measurement "
            "uncertainty. If Q was produced by this very equation, κ is constant to "
            "arithmetic precision. There is nothing in between to interpret: the two "
            "cases differ by three orders of magnitude.",
        ),
    )
    return card


# ----------------------------------------------------------------- primary site


def _primary(context: Context) -> QWidget:
    results = context.results
    site = results.value("discharge_coefficient:site")
    card = w.Card(
        context.pick(
            f"Биринчи иншоот — USGS {site.value if site.ok else ''}, 2018–2025",
            f"First structure — USGS {site.value if site.ok else ''}, 2018–2025",
        ),
        context.pick(
            "Ҳар бир рейтинг даври ичида, нисбий очилиш бўйича ўнта децилда ва напор "
            "фарқи бўйича ўнта децилда — κ қимирламайди. Нисбий очилиш 0.002 дан 6.11 "
            "гача, яъни уч минг баробар диапазонда ўзгаради; κ эса 0.01% да туради.",
            "Within each rating period, across ten deciles of relative opening and ten of "
            "head difference, κ does not move. The relative opening ranges over a factor "
            "of three thousand, from 0.002 to 6.11; κ stays put at 0.01%.",
        ),
    )
    percent2 = lambda v: gdata.as_percent(v, 4)  # noqa: E731
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "discharge_coefficient:by_period.before.spread_by_relative_opening",
                    context.pick(
                        "олдинги давр (2018-01-01 … 2021-10-07): a/Δh бўйича тарқалиш",
                        "earlier period (2018-01-01 … 2021-10-07): spread across a/Δh",
                    ),
                    formatter=percent2,
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "discharge_coefficient:by_period.after.spread_by_relative_opening",
                    context.pick(
                        "кейинги давр (2021-10-08 … 2025-12-31): a/Δh бўйича тарқалиш",
                        "later period (2021-10-08 … 2025-12-31): spread across a/Δh",
                    ),
                    formatter=percent2,
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.periods.0.daily_deviation.p50",
                    context.pick(
                        "типик тўлиқ куннинг медианадан четланиши",
                        "deviation of a typical complete day from the median",
                    ),
                    formatter=percent2,
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "discharge_coefficient:n_samples",
                    context.pick(
                        "бир вақтли кузатув — тўрттала қатор мавжуд бўлган ўлчовлар",
                        "simultaneous observations with all four series present",
                    ),
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.complete_days",
                    context.pick(
                        "тўлиқ кун (96 та ўлчовли), 2 849 кундан",
                        "complete days (96 readings each), out of 2 849",
                    ),
                ),
                w.number_card(
                    results,
                    "discharge_coefficient:kappa_median_m",
                    context.pick(
                        "κ нинг медианаси, м — C<sub>d</sub>=0.61 да эффектив кенглик "
                        "9.59 м га тўғри келади",
                        "median κ in metres — at C<sub>d</sub>=0.61 this implies an "
                        "effective width of 9.59 m",
                    ),
                    formatter=lambda v: gdata.as_number(v, 3),
                ),
            ],
            columns=3,
        )
    )
    return card


# ---------------------------------------------------------------- the rating step


def _step(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Иккинчи белги — сув йили чегарасидаги белгиланмаган сакраш",
            "The second signature — an undocumented step at the water-year boundary",
        ),
        context.pick(
            "Иншоотнинг ўзи ўзгарса, у ихтиёрий кунда ўзгаради. Рейтинг қайта кўриб "
            "чиқилса — сув йили чегарасида. Сакраш айнан 2021-10-08 да, ва ўша ойда "
            "бошқа жойда шунга яқин ҳеч нарса йўқ. Учинчи белги эса USGS каталогининг "
            "ўзида: ўша координатада эски ёрдамчи сайт номи "
            "«<i>WELLTON-MOHAWK CANAL K VALUES (BOTH GATES)</i>» — «K values» рейтинг "
            "коэффициентлари демакдир.",
            "If the structure itself changes, it changes on an arbitrary day. If a rating "
            "is revised, it changes at a water-year boundary. The step falls exactly on "
            "2021-10-08, and nothing comparable happens elsewhere in that month. A third "
            "signature sits in the USGS catalogue itself: an old auxiliary site at the "
            "same coordinates is named "
            "“<i>WELLTON-MOHAWK CANAL K VALUES (BOTH GATES)</i>” — K values are rating "
            "coefficients.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.step_relative",
                    context.pick(
                        "2021-10-08 даги сакрашнинг катталиги",
                        "size of the step at 2021-10-08",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "archive_diagnostics:kappa.window_shift.largest_elsewhere",
                    context.pick(
                        "ўша ±30 кунлик ойнада бошқа жойдаги энг катта силжиш — "
                        "20 баробар кичик",
                        "largest shift anywhere else in the same ±30-day window — "
                        "twenty times smaller",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                ),
                w.number_card(
                    results,
                    "discharge_coefficient:pooled_inflation",
                    context.pick(
                        "иккита даврни аралаштириш тарқалишни неча баробар шиширади "
                        "(3.62% ↔ 0.01%)",
                        "how much mixing the two periods inflates the spread "
                        "(3.62% ↔ 0.01%)",
                    ),
                    formatter=lambda v: f"{v:.1f}×",
                    tone="warn",
                ),
            ],
            columns=3,
        )
    )
    return card


# ---------------------------------------------------------------- second site


def _second(context: Context) -> QWidget:
    results = context.results
    site = results.value("second_structure:site")
    year = results.value("second_structure:year")
    card = w.Card(
        context.pick(
            f"Иккинчи иншоот — USGS {site.value if site.ok else ''}, "
            f"{year.value if year.ok else ''} (H5, H5b)",
            f"Second structure — USGS {site.value if site.ok else ''}, "
            f"{year.value if year.ok else ''} (H5, H5b)",
        ),
        context.pick(
            "Бу ерда κ <b>доимий эмас</b> — 17% га тарқалади. Демак детекторнинг оддий "
            "шакли ишламайди. Лекин сарф барибир ўлчанмайди: log Q ни log Δh ва log a "
            "бўйича мослаш медиана қолдиқни 0.85% га туширади, ва қолдиқ "
            "<b>тузилган</b> — шовқин эмас. Яъни бу иншоотда бошқа шаклдаги рейтинг "
            "ишлатилган.",
            "Here κ is <b>not</b> constant — it spreads by 17%, so the simple form of the "
            "detector fails. Yet the discharge is still not measured: a fit of log Q on "
            "log Δh and log a leaves a median residual of 0.85%, and that residual is "
            "<b>structured</b>, not noise. A rating of a different form is in use.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "second_structure:kappa_all.spread_iqr_over_median",
                    context.pick("κ нинг тарқалиши (IQR ⁄ медиана)", "spread of κ (IQR ⁄ median)"),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="warn",
                ),
                w.number_card(
                    results,
                    "second_structure:kappa_all.typical_complete_day_deviation",
                    context.pick(
                        "типик тўлиқ куннинг четланиши — биринчи иншоотда 0.0093%",
                        "deviation of a typical complete day — 0.0093% at the first structure",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="warn",
                ),
                w.number_card(
                    results,
                    "second_structure:rating_fit.median_abs_relative_residual",
                    context.pick(
                        "log Q ~ (log Δh, log a) мослигининг медиана |қолдиқ| и",
                        "median |residual| of the log Q ~ (log Δh, log a) fit",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 2),
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "second_structure:h5b.structure.a.ratio_to_median_abs_residual",
                    context.pick(
                        "a бўйича бин медианаларининг қолдиққа нисбати "
                        "(мезон: >1.0 — тузилган)",
                        "ratio of bin medians across a to the residual "
                        "(criterion: above 1.0 means structured)",
                    ),
                    formatter=lambda v: f"{v:.2f}",
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "second_structure:h5b.structure.dh.ratio_to_median_abs_residual",
                    context.pick(
                        "Δh бўйича ўша нисбат",
                        "the same ratio across Δh",
                    ),
                    formatter=lambda v: f"{v:.2f}",
                    tone="circular",
                ),
                w.number_card(
                    results,
                    "second_structure:h5b.structure.lag1_autocorrelation",
                    context.pick(
                        "қолдиқнинг lag-1 автокорреляцияси — тасодифий ўлчов хатоси "
                        "бундай бўлмайди",
                        "lag-1 autocorrelation of the residual — random measurement error "
                        "does not look like this",
                    ),
                    formatter=lambda v: f"{v:.4f}",
                    tone="circular",
                ),
            ],
            columns=3,
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>Эҳтиёт, очиқ ёзилади.</b> Иккала предиктор коллинеар: юқори бьеф йил "
                "бўйи деярли доимий, шунинг учун Δh ≈ const − H₂. Демак иккита бин "
                "таҳлили — битта тузилишнинг икки кўриниши. Мослиқдаги a нинг 3.19 "
                "даражаси физик эмас, ва рейтингнинг <i>шакли</i> ҳақида ҳеч қандай даъво "
                "қилинмайди — фақат сарфнинг ҳисобланиши ҳақида.",
                "<b>One caveat, stated openly.</b> The two predictors are collinear: the "
                "headwater is nearly constant through the year, so Δh ≈ const − H₂. The "
                "two bin analyses are therefore one structure seen twice. The exponent of "
                "3.19 on a is not physical, and no claim is made about the <i>form</i> of "
                "the rating — only that the discharge is computed.",
            )
        )
    )
    return card


# ------------------------------------------------------------- general signature


def _general(context: Context) -> QWidget:
    return w.Card(
        context.pick(
            "Умумлаштирилган белги — ва нима учун иккита иншоот керак бўлди",
            "The generalised signature — and why two structures were needed",
        ),
        context.pick(
            "Битта иншоотда «κ доимий» деган белги етарли бўларди, лекин у фақат оддий "
            "шаклдаги рейтингни тутади. Иккинчи иншоот шакли бошқа бўлиб чиқди, ва "
            "шунинг учун белги умумийроқ ёзилади — иккита ўлчанадиган шарт:"
            "<br><br>"
            "&nbsp;&nbsp;<b>(i)</b> Q ўлчанган ўзгарувчилардан <i>дала ўлчовининг "
            "аниқлигидан анча тор</i> такрорланади;<br>"
            "&nbsp;&nbsp;<b>(ii)</b> қолган қолдиқ <i>тузилган</i> — шовқин эмас."
            "<br><br>"
            "Иккови ҳам бажарилса, эълон қилинган сарф — рейтинг чиқиши, рейтингнинг "
            "тури қандай бўлишидан қатъи назар.",
            "At one structure “κ is constant” would have been enough, but it only "
            "catches a rating of the simple form. The second structure turned out to use a "
            "different form, so the signature is written more generally, as two measurable "
            "conditions:"
            "<br><br>"
            "&nbsp;&nbsp;<b>(i)</b> Q is reproduced from the measured variables <i>far more "
            "tightly than field-measurement accuracy allows</i>;<br>"
            "&nbsp;&nbsp;<b>(ii)</b> what residual remains is <i>structured</i>, not scatter."
            "<br><br>"
            "When both hold, the published discharge is a rating output, whatever form the "
            "rating takes.",
        ),
    )


# ----------------------------------------------------------------------- figures


def _add_figures(context: Context, layout, numbers: tuple[int, ...]) -> None:
    available = {figure.number: figure for figure in gdata.figures(context.paths, context.results)}
    for number in numbers:
        figure = available.get(number)
        if figure is not None:
            layout.addWidget(w.FigureCard(figure, context.paths, context.language))
