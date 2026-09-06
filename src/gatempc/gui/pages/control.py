"""Page 5 — what carrying the benchmark law costs a controller."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from .. import data as gdata
from .. import widgets as w
from . import Context

NAV = ("5 · Бошқарув", "5 · Control")


def build(context: Context) -> QWidget:
    body = w.column(18)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(
            context.pick(
                "Эталон қонунини кўтаришнинг нархи — ёпиқ ҳалқада ўлчанди",
                "The cost of carrying the benchmark law — measured in closed loop",
            )
        )
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Савол «қайси контроллер яхши» эмас. Савол: бир хил контроллер "
                "идентификация қилинган қонунда созилса, эталон қонунида созилганига "
                "нисбатан нима ютади? Фарқ <b>δ</b> деб белгиланади ва 100 жуфтланган "
                "такрорда ўлчанади — иккала тармоқ бир хил уруғлар, бир хил шовқин ва "
                "бир хил сценарийда юритилади.",
                "The question is not which controller is better. It is: what does the same "
                "controller gain when it is tuned on the identified law instead of the "
                "benchmark law? That difference is <b>δ</b>, measured over 100 paired "
                "replicates in which both arms see the same seeds, the same noise and the "
                "same scenario.",
            )
        )
    )

    layout.addWidget(_stage_one(context))
    layout.addWidget(_headline(context))
    layout.addWidget(_honesty(context))
    layout.addWidget(_sensitivity(context))
    layout.addWidget(_setup(context))
    _add_figures(context, layout, (5, 6, 7, 8))
    for name, uz, en in (
        ("table_7_control.csv", "Жадвал 7 — бошқарув кўрсаткичлари", "Table 7 — control indicators"),
        ("table_8_delta.csv", "Жадвал 8 — δ ва сезгирлик", "Table 8 — δ and sensitivity"),
    ):
        layout.addWidget(
            w.TableCard(
                context.paths.tables / name,
                context.paths,
                context.language,
                title=context.pick(uz, en),
                max_height=380,
            )
        )
    return w.wrap_scroll(body)


# --------------------------------------------------------------------- stage one


def _stage_one(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "1-босқич — ёпиқ ҳалқа тести умуман керакми?",
            "Stage one — is a closed-loop test warranted at all?",
        ),
        context.pick(
            "Аввал модел хатосининг ўзи ўлчанди: сиғим тенглаштирилгандан кейин иккала "
            "қонун фақат кўрсаткичлар билан фарқ қилади. Остона олдиндан 1% деб "
            "белгиланган эди.",
            "First the model error itself was measured: once the two laws are matched at a "
            "reference point they differ only in their exponents. The threshold was fixed "
            "in advance at 1%.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "model_error_envelope:envelopes.asce_test_2_1.error_largest_ci",
                    context.pick(
                        "ASCE Test 2-1 диапазонида энг катта хато (ИИ билан) — остонадан паст",
                        "largest error over the ASCE Test 2-1 range (with CI) — below the threshold",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 3),
                ),
                w.number_card(
                    results,
                    "model_error_envelope:envelopes.observed_wellton_mohawk.error_largest_ci",
                    context.pick(
                        "кузатилган диапазонда энг катта хато (ИИ билан) — остонадан юқори",
                        "largest error over the observed range (with CI) — above the threshold",
                    ),
                    formatter=lambda v: gdata.as_percent(v, 3),
                    tone="accent",
                ),
                w.number_card(
                    results,
                    "model_error_envelope:threshold",
                    context.pick("олдиндан ёзилган остона", "the pre-registered threshold"),
                    formatter=lambda v: gdata.as_percent(v, 0),
                ),
            ],
            columns=3,
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>Пре-регистрацияда бўшлиқ бор эди:</b> «максимум конверт бўйича» деб "
                "ёзилган, лекин <i>қайси</i> конверт ҳал қилиши айтилмаган. Иккита жавоб "
                "чиқди. Бўшлиқ кузатилган конверт фойдасига ҳал қилинди — у ўлчанган, "
                "ASCE конверти эса Δh бўйича фаразга таянади; ва бўшлиқни иш ҳажмини "
                "камайтирадиган томонга ҳал қилиш айнан пре-регистрация тўсадиган нарса. "
                "Ёнида ўз ҳақи бор кузатув: ASCE Test 2-1 нинг напор диапазони (0.10–0.35 м) "
                "реал каналникидан (0.27–1.68 м) анча тор, яъни эталонда синалган "
                "контроллер реал иншоотнинг тўлиқ иш диапазонида синалмаган бўлади.",
                "<b>The pre-registration had a gap:</b> it said “over the maximum "
                "envelope” without saying <i>which</i> envelope decides, and two answers "
                "came out. The gap was resolved in favour of the observed envelope, because "
                "that one is measured while the ASCE envelope rests on an assumption about "
                "Δh — and because resolving a gap towards less work is what pre-registration "
                "exists to prevent. A finding in its own right sits beside it: the ASCE "
                "Test 2-1 head range (0.10–0.35 m) is much narrower than the real canal's "
                "(0.27–1.68 m), so a controller validated on the benchmark has not been "
                "tested over the real structure's full operating range.",
            )
        )
    )
    return card


# ---------------------------------------------------------------------- headline


def _ci_note(results: gdata.Results, reference: str) -> str:
    """A bootstrap interval rendered in percent, or an empty note if it is absent."""
    found = results.value(reference)
    pair = found.value if found.ok else None
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return ""
    if not all(isinstance(item, (int, float)) for item in pair):
        return ""
    low, high = (float(item) * 100 for item in pair)
    return f"[{low:+.3f}, {high:+.3f}] %, 95% bootstrap"


def _headline(context: Context) -> QWidget:
    results = context.results
    signed = lambda v: gdata.as_signed_percent(v, 3)  # noqa: E731
    card = w.Card(
        context.pick(
            "2-босқич — асосий рақам δ",
            "Stage two — the headline number δ",
        ),
        context.pick(
            "Манфий δ идентификация қилинган қонунда созилган контроллернинг устунлигини "
            "билдиради. Мезон олдиндан ёзилган эди: bootstrap интервали нолни ўз ичига "
            "олса, натижа рад этувчи ҳисобланади.",
            "A negative δ means the controller tuned on the identified law does better. The "
            "criterion was fixed in advance: the result is negative if the bootstrap "
            "interval contains zero.",
        ),
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "control_comparison:controllers.PI.delta.median",
                    context.pick("PI — δ нинг медианаси", "PI — median δ"),
                    formatter=signed,
                    tone="accent",
                    note=_ci_note(results, "control_comparison:controllers.PI.delta.ci95"),
                ),
                w.number_card(
                    results,
                    "control_comparison:controllers.MPC.delta.median",
                    context.pick("MPC — δ нинг медианаси", "MPC — median δ"),
                    formatter=signed,
                    tone="accent",
                    note=_ci_note(results, "control_comparison:controllers.MPC.delta.ci95"),
                ),
                w.number_card(
                    results,
                    "control_comparison:controllers.MPC.delta_absolute_m.in_sensor_steps",
                    context.pick(
                        "ўша фарқ сатҳ датчигининг қадамига нисбатан — 1.5 мм ли қадамнинг ≈4.5% и",
                        "the same difference in level-sensor steps — about 4.5% of one "
                        "1.5 mm step",
                    ),
                    formatter=lambda v: f"{v:.3f}",
                    tone="warn",
                ),
            ],
            columns=3,
        )
    )
    return card


# ----------------------------------------------------------------------- honesty


def _honesty(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Аҳамиятли, лекин кичик — иккаласи ҳам ёзилади",
            "Significant, and small — both are stated",
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "δ нинг интервали нолни ўз ичига олмайди, демак мезон бажарилди. Лекин "
                "абсолют фарқ 0.07 мм — сатҳ датчигининг битта қадамидан 20 баробар "
                "кичик — йигирма баробардан ортиқ. Икковини бирга айтмаслик натижани катталаштириб кўрсатган бўларди."
                "<br><br>"
                "<b>δ нинг ишораси моделнинг эмас, ҳалқанинг хоссаси.</b> Тескари ҳисоблаш "
                "хатоси ҳалқа кучайтиришининг кичик хатоси сифатида ишлайди: иш нуқтасида "
                "ҳалқа оптимал кучайтиришдан қайси томонда турганига қараб у ёрдам ҳам, "
                "зарар ҳам беради. Барқарор нарса — <b>катталик</b>. Кўзгу тест буни "
                "тасдиқлайди: тармоқлар алмаштирилганда белги тескарига айланади, "
                "катталик эса деярли ўзгармайди.",
                "The interval for δ excludes zero, so the criterion is met. But the absolute "
                "difference is 0.07 mm — more than twenty times smaller than one step of the level "
                "sensor. Reporting one without the other would overstate the result."
                "<br><br>"
                "<b>The sign of δ is a property of the loop, not of the model.</b> An "
                "inversion error acts as a small error in loop gain, so depending on which "
                "side of the optimal gain the loop sits at the operating point it can help "
                "or hurt. What is stable is the <b>magnitude</b>. The mirror test confirms "
                "it: swapping the arms flips the sign and barely changes the size.",
            )
        )
    )
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "control_comparison:controllers.PI.delta_mirror.median",
                    context.pick("PI — кўзгу тест", "PI — mirror test"),
                    formatter=lambda v: gdata.as_signed_percent(v, 3),
                ),
                w.number_card(
                    results,
                    "control_comparison:controllers.MPC.delta_mirror.median",
                    context.pick("MPC — кўзгу тест", "MPC — mirror test"),
                    formatter=lambda v: gdata.as_signed_percent(v, 3),
                ),
                w.number_card(
                    results,
                    "control_comparison:controllers.MPC.matched_arm_check.max_iae_gap",
                    context.pick(
                        "мос тармоқлар текшируви: бир хил моделда IAE фарқи",
                        "matched-arm check: IAE gap when both arms use the same model",
                    ),
                    formatter=lambda v: f"{v:.2e}",
                    tone="measured",
                ),
            ],
            columns=3,
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>Кўрсаткичларнинг таққосланиши ҳақида.</b> [C98] нинг 9-жадвали "
                "Канал 1 / Тест 1 га тегишли ва IAW ни келтирмайди, шунинг учун бу ердан "
                "фақат MAE, IAE ва StE таққосланади; IAQ таққосланмайди ва у объектнинг "
                "хоссаси сифатида изоҳланади.",
                "<b>On comparability.</b> Table 9 of [C98] is for Canal 1 / Test 1 and does "
                "not report IAW, so only MAE, IAE and StE are comparable from here; IAQ is "
                "not, and it is interpreted as a property of the pool.",
            )
        )
    )
    return card


# ------------------------------------------------------------------- sensitivity


def _sensitivity(context: Context) -> QWidget:
    results = context.results
    card = w.Card(
        context.pick(
            "Сезгирлик — ҳеч бири асосий рақам эмас",
            "Sensitivity — none of these is the headline",
        ),
        context.pick(
            "Учта сўров олдиндан режалаштирилган эди: даражаларнинг ишонч интервали "
            "бўйича бурчаклар, минимал затвор қадами, ва бьеф узунлиги.",
            "Three sweeps were planned in advance: the corners of the exponent confidence "
            "interval, a minimum gate step, and the pool length.",
        ),
    )
    pool = results.value("control_comparison:sensitivity.pool_length.MPC.pools")
    if pool.ok and isinstance(pool.value, list):
        pairs = []
        for entry in pool.value:
            if not isinstance(entry, dict):
                continue
            pairs.append(
                (
                    f"{gdata.as_number(entry.get('length_m'), 0)} m",
                    gdata.as_signed_percent(entry.get("delta_median"), 3),
                )
            )
        card.add(
            w.paragraph(
                context.pick(
                    "<b>Бьеф узунлиги (MPC).</b> Бьеф қисқарган сари δ ўсади — яъни "
                    "асосий рақам бу лойиҳада танланган 7 км ли бьеф учун энг кичик "
                    "қиймат, ва у қисқа бьефларда сезиларли бўлади:",
                    "<b>Pool length (MPC).</b> δ grows as the pool gets shorter, so the "
                    "headline is the smallest value of the family — for the 7 km pool used "
                    "here — and it becomes appreciable in short pools:",
                )
            )
        )
        card.add(w.key_values(pairs, columns=4))
    card.add(
        w.card_row(
            [
                w.number_card(
                    results,
                    "control_comparison:sensitivity.exponent_ci.MPC.min",
                    context.pick(
                        "даражалар ИИ бурчакларида δ нинг энг манфийи (MPC)",
                        "most negative δ at the exponent-CI corners (MPC)",
                    ),
                    formatter=lambda v: gdata.as_signed_percent(v, 3),
                ),
                w.number_card(
                    results,
                    "control_comparison:sensitivity.exponent_ci.MPC.max",
                    context.pick(
                        "ўша бурчаклардаги энг кам манфийи (MPC)",
                        "least negative δ at the same corners (MPC)",
                    ),
                    formatter=lambda v: gdata.as_signed_percent(v, 3),
                ),
                w.number_card(
                    results,
                    "control_comparison:sensitivity.min_gate_step.MPC.min_step_m",
                    context.pick(
                        "синалган минимал затвор қадами, м",
                        "minimum gate step tested, m",
                    ),
                    formatter=lambda v: f"{v:.4f}",
                ),
            ],
            columns=3,
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>Минимал затвор қадами (H2-s3).</b> Ўлик зона қўшилганда MPC да IAQ "
                "4.5–4.9% га тушади, PI да эса 0.3–1.3% га <i>ошади</i>. Иккала ҳолда "
                "ҳам ўзгариш 20% дан кичик — демак олдиндан ёзилган қоида бўйича катта "
                "IAQ ўлик зона йўқлигининг артефакти эмас, ҳалқанинг ҳақиқий тебраниши.",
                "<b>Minimum gate step (H2-s3).</b> With a deadband, MPC's IAQ falls by "
                "4.5–4.9% while PI's <i>rises</i> by 0.3–1.3%. Either way the change is "
                "under 20%, so by the pre-registered rule the large IAQ is not an artefact "
                "of the missing deadband but genuine oscillation of the loop.",
            )
        )
    )
    return card


# ------------------------------------------------------------------------- setup


def _setup(context: Context) -> QWidget:
    results = context.results
    design = results.value("control_comparison:design")
    card = w.Card(
        context.pick("Тажриба қандай қурилган", "How the experiment is set up"))
    if design.ok and isinstance(design.value, dict):
        block = design.value
        pool = block.get("pool", {}) if isinstance(block.get("pool"), dict) else {}
        noise = block.get("noise", {}) if isinstance(block.get("noise"), dict) else {}
        evaluate = (
            block.get("scenario_eval", {}) if isinstance(block.get("scenario_eval"), dict) else {}
        )
        tune = (
            block.get("scenario_tune", {}) if isinstance(block.get("scenario_tune"), dict) else {}
        )
        card.add(
            w.key_values(
                [
                    (
                        context.pick("Созлаш сценарийси", "Tuning scenario"),
                        str(tune.get("name", "—")),
                    ),
                    (
                        context.pick("Баҳолаш сценарийси", "Evaluation scenario"),
                        str(evaluate.get("name", "—")),
                    ),
                    (
                        context.pick("Такрорлар", "Replicates"),
                        gdata.as_number(block.get("replicates")),
                    ),
                    (
                        context.pick("Қадам, с", "Time step, s"),
                        gdata.as_number(block.get("dt_s"), 0),
                    ),
                    (
                        context.pick("Бьеф узунлиги, м", "Pool length, m"),
                        gdata.as_number(pool.get("length_m"), 0),
                    ),
                    (
                        context.pick("Кечикиш, с", "Delay, s"),
                        gdata.as_number(pool.get("delay_s"), 1),
                    ),
                    (
                        context.pick("Сатҳ квантлаш қадами, м", "Level quantisation, m"),
                        gdata.as_number(noise.get("level_quantisation_m"), 4),
                    ),
                    (
                        context.pick("Вақт силжиши, с", "Timing shift, s"),
                        gdata.as_number(noise.get("timing_shift_s"), 0),
                    ),
                ],
                columns=2,
            )
        )
        for label, block_ in (
            (context.pick("Созлаш манбаи", "Tuning source"), tune),
            (context.pick("Баҳолаш манбаи", "Evaluation source"), evaluate),
        ):
            if block_.get("source"):
                card.add(w.paragraph(f"<b>{label}:</b> {block_['source']}"))
    return card


# ----------------------------------------------------------------------- figures


def _add_figures(context: Context, layout, numbers: tuple[int, ...]) -> None:
    available = {figure.number: figure for figure in gdata.figures(context.paths, context.results)}
    for number in numbers:
        figure = available.get(number)
        if figure is not None:
            layout.addWidget(w.FigureCard(figure, context.paths, context.language))
