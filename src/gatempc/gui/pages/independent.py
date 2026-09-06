"""Argument page — the way out of the circle: independent field gaugings (H4).

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
                "Доирадан чиқиш йўли: мустақил дала гаугинглари",
                "The way out of the circle: independent field gaugings",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Ўша сайтда USGS дискрет сарф ўлчовларини ҳам қилади. Улар узлуксиз "
                "қатордан <b>мустақил</b> — рейтинг уларга калибрланади, аксинча эмас. "
                "Эталоннинг идеаллаштирилган қонуни айнан ўшаларга қарши текширилади, "
                "ва у ҳеч қачон уларга мослаштирилмаган.",
                "At the same site USGS also takes discrete discharge measurements. They are "
                "<b>independent</b> of the continuous series — the rating is calibrated to "
                "them, not the other way round. The benchmark's idealised law is checked "
                "against those, and it was never fitted to them.",
            )
        )
    )

    layout.addWidget(_selection(context))
    layout.addWidget(_result(context))
    layout.addWidget(_by_class(context))
    layout.addWidget(_source(context))
    _add_figure(context, layout, 2)
    layout.addWidget(
        w.TableCard(
            context.paths.tables / "table_6_h4.csv",
            context.paths,
            context.language,
            title=context.pick(
                "Жадвал 6 — H4: мустақил гаугингларга нисбатан қолдиқлар",
                "Table 6 — H4: residuals against independent gaugings",
            ),
            max_height=420,
        )
    )
    return w.wrap_scroll(body)


# --------------------------------------------------------------------- selection


def _selection(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Танлаш — қоидалар ўлчашдан олдин ёзилган",
            "Selection — the rules were written before the measurement",
        ),
        context.pick(
            "Ҳар бир рад этиш сабаби билан саналади. Диққат қиладиган сон — ±15 дақиқада "
            "мос келмаган гаугинглар сони нол: узлуксиз қатор гаугинг вақтларини тўлиқ "
            "қоплайди, шунинг учун танлашда яширин фильтр йўқ.",
            "Every rejection is counted with its reason. The number to note is that no "
            "gauging failed to find a match within ±15 minutes: the continuous series "
            "covers the gauging times completely, so the selection hides no filter.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "gate_law_validation:gaugings_total",
                    context.pick("жами гаугинг, 1984–2026", "gaugings in total, 1984–2026"),
                ),
                w.number_card(
                    results,
                    "gate_law_validation:accepted",
                    context.pick("қабул қилинди", "accepted"),
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law_validation:rejected.outside_fold_window",
                    context.pick(
                        "рад: fold ойнасидан ташқарида (2018–2025 дан чиқади)",
                        "rejected: outside the fold window (before 2018 or after 2025)",
                    ),
                ),
                w.number_card(
                    results,
                    "gate_law_validation:rejected.rating_poor_or_missing",
                    context.pick(
                        "рад: ўлчов сифати `Poor` ёки белгиланмаган",
                        "rejected: measurement quality `Poor` or unrated",
                    ),
                ),
                w.number_card(
                    results,
                    "gate_law_validation:rejected.gate_moved_within_30min",
                    context.pick(
                        "рад: ўлчов пайтида затвор ҳаракатланган (±30 дақиқа)",
                        "rejected: the gate moved during the measurement (±30 min)",
                    ),
                ),
                w.number_card(
                    results,
                    "gate_law_validation:rejected.no_match_within_15min",
                    context.pick(
                        "рад: ±15 дақиқада мос ўлчов топилмади",
                        "rejected: no continuous reading within ±15 minutes",
                    ),
                    tone="measured",
                ),
            ],
            columns=3,
        )
    )
    return card


# ------------------------------------------------------------------------ result


def _result(context: Context) -> QWidget:
    results = context.results
    signed = lambda v: gdata.as_signed_percent(v, 2)  # noqa: E731
    plain = lambda v: gdata.as_percent(v, 2)  # noqa: E731
    card = w.Card(
        context.pick(
            "Натижа — иккала мезон ҳам бажарилди",
            "Result — both criteria were met",
        ),
        context.pick(
            "Мезонлар ўлчашдан олдин белгиланган эди: силжиш ±5% ичида ва предикторлар "
            "бўйича тузилиш 5% дан кичик.",
            "The criteria were fixed before the measurement: bias within ±5% and residual "
            "structure below 5% across the predictors.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "gate_law_validation:relative_residual.median",
                    context.pick("медиана (силжиш) — мезон ±5%", "median (bias) — criterion ±5%"),
                    formatter=signed,
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law_validation:relative_residual.iqr",
                    context.pick("IQR — тарқалиш", "IQR — the scatter"),
                    formatter=plain,
                ),
                w.number_card(
                    results,
                    "gate_law_validation:structure_spread.a/dh",
                    context.pick(
                        "тузилиш: a/Δh бўйича бин медианаларининг тарқалиши — мезон 5%",
                        "structure: spread of bin medians across a/Δh — criterion 5%",
                    ),
                    formatter=plain,
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law_validation:structure_spread.dh",
                    context.pick(
                        "тузилиш: Δh бўйича — мезон 5%",
                        "structure: across Δh — criterion 5%",
                    ),
                    formatter=plain,
                    tone="measured",
                ),
                w.number_card(
                    results,
                    "gate_law_validation:relative_residual.min",
                    context.pick("энг манфий қолдиқ", "most negative residual"),
                    formatter=signed,
                ),
                w.number_card(
                    results,
                    "gate_law_validation:relative_residual.max",
                    context.pick("энг мусбат қолдиқ", "most positive residual"),
                    formatter=signed,
                ),
            ],
            columns=3,
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "Рейтинг сакрашининг иккала томонида ҳам текширилди: сакрашдан олдинги 35 "
                "гаугингнинг медиана |қолдиқ| и 0.61%, кейинги 42 тасиники 0.26%. Яъни "
                "хулоса битта рейтинг даврига боғлиқ эмас.",
                "The check was run on both sides of the rating step: the 35 gaugings before "
                "it have a median |residual| of 0.61%, the 42 after it 0.26%. The conclusion "
                "does not depend on one rating period.",
            )
        )
    )
    return card


# ---------------------------------------------------------------------- by class


def _by_class(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Ўлчов сифати бўйича — қолдиқнинг катта қисми ўлчовнинг ўзиники",
            "By measurement quality — most of the residual belongs to the measurement",
        ),
        context.pick(
            "USGS ҳар бир гаугингга сифат баҳосини қўяди ва ҳар бир баҳо учун ўз "
            "аниқлигини эълон қилади. Сифатлироқ ўлчовларда тарқалиш кичикроқ чиқди — "
            "бу кутилган нарса, ва у қолдиқнинг манбаини кўрсатади.",
            "USGS rates every gauging and publishes a stated accuracy for each rating. The "
            "better-rated measurements scatter less, which is what one would expect and "
            "which says where the residual comes from.",
        ),
    )
    by_rating = results.value("gate_law_validation:by_rating")
    if by_rating.ok and isinstance(by_rating.value, dict):
        cards = []
        for name in sorted(by_rating.value):
            block = by_rating.value[name]
            if not isinstance(block, dict):
                continue
            outside = int(block.get("n_outside_stated", 0) or 0)
            count = int(block.get("n", 0) or 0)
            stated = block.get("stated_accuracy")
            cards.append(
                w.NumberCard(
                    f"{count - outside} / {count}",
                    context.pick(
                        f"`{name}` синфи: эълон қилинган {gdata.as_percent(stated, 0)} "
                        f"аниқлик ичида қолган гаугинглар",
                        f"`{name}` class: gaugings inside the stated "
                        f"{gdata.as_percent(stated, 0)} accuracy",
                    ),
                    f"results/gate_law_validation.json -> by_rating.{name}",
                    tone="measured" if outside == 0 else "warn",
                    note=context.pick(
                        f"медиана {gdata.as_signed_percent(block.get('median'), 2)}, "
                        f"IQR {gdata.as_percent(block.get('iqr'), 2)}",
                        f"median {gdata.as_signed_percent(block.get('median'), 2)}, "
                        f"IQR {gdata.as_percent(block.get('iqr'), 2)}",
                    ),
                )
            )
        if cards:
            card.add(w.card_row(cards, columns=len(cards)))
    return card


# ------------------------------------------------------------------------ source


def _source(context: Context) -> QWidget:
    results = context.results
    source = results.value("gate_law_validation:rating_source")
    card = w.Card(
        context.pick(
            "Аниқлик синфларининг таърифи қаердан олинган",
            "Where the accuracy classes are defined",
        ),
        context.pick(
            "H4 нинг ±5% мезони бу манба топилишидан <b>олдин</b> белгиланган эди; манба "
            "уни кейин тасдиқлади. Тартиб шу ерда очиқ ёзилади, чунки акс ҳолда мезон "
            "манбадан келтириб чиқарилгандек кўринади.",
            "H4's ±5% criterion was fixed <b>before</b> this source was found; the source "
            "then confirmed it. The order is stated openly here, because otherwise the "
            "criterion would look as if it had been derived from the source.",
        ),
    )
    if source.ok and isinstance(source.value, dict):
        block = source.value
        pairs = [
            (context.pick("Ном", "Title"), str(block.get("title", "—"))),
            (context.pick("Нашриёт", "Publisher"), str(block.get("publisher", "—"))),
            (context.pick("Серия", "Series"), str(block.get("series", "—"))),
            (context.pick("URL", "URL"), str(block.get("url", "—"))),
            (context.pick("Кўрилган сана", "Accessed"), str(block.get("accessed_utc", "—"))),
        ]
        if block.get("page_carries_no_date"):
            pairs.append(
                (
                    context.pick("Изоҳ", "Note"),
                    context.pick(
                        "саҳифанинг ўзида сана йўқ — шунинг учун кўрилган сана келтирилади",
                        "the page carries no date of its own, so the access date is cited",
                    ),
                )
            )
        card.add(w.key_values(pairs, columns=1))
    return card


# ------------------------------------------------------------------------ figure


def _add_figure(context: Context, layout, number: int) -> None:
    available = {figure.number: figure for figure in gdata.figures(context.paths, context.results)}
    figure = available.get(number)
    if figure is None:
        return
    card = w.FigureCard(figure, context.paths, context.language)
    card.add(
        w.paragraph(
            context.pick(
                "<b>(a) панелида бин медианалари чизиғи йўқ.</b> H4 нинг тузилиш тести "
                "олдиндан фақат a/Δh ва Δh бўйича ёзилган эди; сарфнинг ўзи бўйича бинлаш "
                "пре-регистрацияда йўқ, шунинг учун у ерга чизиқ қўйилмайди.",
                "<b>Panel (a) carries no binned-median line.</b> H4's structure test was "
                "pre-registered against a/Δh and Δh only; binning by discharge itself is "
                "not in the pre-registration, so no line is drawn there.",
            )
        )
    )
    layout.addWidget(card)
