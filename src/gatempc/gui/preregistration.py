"""The pre-registration record: what was expected before each measurement, and what came out.

This is the part of the study that no result file can hold, because it is a record of
expectations — including the ones that turned out wrong. Every entry below is a short
faithful rendering of one section of the project's internal hypothesis log, which is
written before the corresponding script is run and is never edited afterwards. Where an
entry states a measured number, ``evidence`` names the published result file the number
can be read from, so a reviewer can check the claim without taking the log on trust.

The record keeps its failures: two quantities the archive cannot identify, two
expectations the measurement contradicted, and two hypotheses whose criteria were met
but which were withdrawn afterwards. They are here for the same reason the successes
are.

No Qt is imported here, so the record can be printed, tested or exported without a
display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    """How an entry ended. The colour each one gets is decided in ``theme.py``."""

    SUPPORTED = "supported"
    #: The pre-registered criterion was met, but the finding was withdrawn afterwards
    #: because the quantity it rested on turned out to be a rating output.
    WITHDRAWN = "withdrawn"
    #: The quantity could not be estimated from the archive at all.
    NOT_IDENTIFIED = "not_identified"
    #: The measurement contradicted the expectation. The expectation stands unedited.
    EXPECTATION_WRONG = "expectation_wrong"


@dataclass(frozen=True)
class Entry:
    """One pre-registered question."""

    key: str
    question_uz: str
    question_en: str
    expected_uz: str
    expected_en: str
    measured_uz: str
    measured_en: str
    verdict: Verdict
    evidence: tuple[str, ...] = field(default_factory=tuple)
    script: str = ""


RECORD: tuple[Entry, ...] = (
    Entry(
        key="H0c-1",
        question_uz="Бьефнинг сув юзаси майдони A<sub>s</sub> архивдан баҳоланадими?",
        question_en="Can the pool surface area A<sub>s</sub> be estimated from the archive?",
        expected_uz=(
            "Учта мезон олдиндан ёзилди: қабул қилинган воқеалар ≥ 500; медиана мусбат ва "
            "IQR медиананинг 50% идан кичик; ҳар бир fold медианаси қолганларининг 95% "
            "интервалида. Тушиб қолиш йўли ҳам ёзилди — баҳоланмаса, бьеф тўлиқ ASCE "
            "Test Case 2 дан олинади."
        ),
        expected_en=(
            "Three criteria fixed in advance: at least 500 accepted events; a positive "
            "median with an IQR below 50% of it; every fold median inside the 95% interval "
            "of the others. A fallback was written at the same time: if it is not "
            "identified, the pool is taken entirely from ASCE Test Case 2."
        ),
        measured_uz=(
            "3055 воқеа қабул қилинди — маълумот етарли. Лекин IQR медиананинг 123.1% и, "
            "ва 56 та fold жуфтлигидан 32 таси бузилди. Медиана ойна узунлиги билан "
            "монотон ўсади (241 289 → 297 190 → 334 124 м²) — конвергенция эмас, силжиш."
        ),
        measured_en=(
            "3055 events were accepted, so the data were sufficient; the method was not. "
            "The IQR is 123.1% of the median and 32 of 56 fold pairs disagree. The median "
            "grows monotonically with the window length (241 289 → 297 190 → 334 124 m²), "
            "which is drift, not convergence."
        ),
        verdict=Verdict.NOT_IDENTIFIED,
        evidence=("archive_diagnostics:storage",),
        script="archive_diagnostics.py",
    ),
    Entry(
        key="H0c-2",
        question_uz="Затвор остонаси z<sub>0</sub> баҳоланадими, ва эркин оқим улуши қанча?",
        question_en="Can the gate sill z<sub>0</sub> be estimated, and how much free flow is there?",
        expected_uz="«Эркин оқим улуши 5% дан кам бўлади деб кутаман.»",
        expected_en="“I expect the free-flow fraction to stay below 5%.”",
        measured_uz=(
            "Рухсат этилган соҳанинг юқори қисмида улуш 32.2% гача чиқади — кутиш рад "
            "этилди ва ўзгартирилмади. z<sub>0</sub> нинг ўзи ҳам баҳоланмайди: оптимум атрофида "
            "мослик 2.975 ft ли қидирув соҳасининг 0.82 футида ажратиб бўлмас даражада "
            "текис, оптимумдаги эркин оқим улуши эса амалда ноль."
        ),
        measured_en=(
            "In the upper part of the admissible range the fraction reaches 32.2%: the "
            "expectation was contradicted, and it stands unedited. z<sub>0</sub> itself is also not "
            "identified — the fit is indistinguishably flat across 0.82 ft of the 2.975 ft "
            "searched, and the free-flow fraction at the optimum is effectively zero."
        ),
        verdict=Verdict.EXPECTATION_WRONG,
        evidence=("gate_law:h0c2_second_condition", "gate_law:full_fit.free_fraction"),
        script="identify_gate_law.py",
    ),
    Entry(
        key="H1",
        question_uz=(
            "Идентификация қилинган даражалар идеал затвор қонунининг 1 ва 0.5 "
            "қийматларидан фарқ қиладими?"
        ),
        question_en=(
            "Do the identified exponents differ from the ideal gate law's 1 and 0.5?"
        ),
        expected_uz=(
            "Мезон: fold'лар бўйича 95% ишонч интервали идеал қийматни ўз ичига олмаса, "
            "фарқ бор деб ҳисобланади."
        ),
        expected_en=(
            "Criterion: a difference is accepted when the 95% cross-validation interval "
            "excludes the ideal value."
        ),
        measured_uz=(
            "α = 1.0005, ИИ [0.9999, 1.0012] — идеал 1 ни ўз ичига олади. β = 0.5086, "
            "ИИ [0.5068, 0.5104] — 0.5 ни ўз ичига олмайди, демак мезон бажарилди. "
            "Лекин эркин даражали мослик RMSE ни атиги 1.09% га яхшилайди, ва мослик "
            "узлуксиз сарф қаторига қилинган — у эса рейтингнинг ўз чиқиши. Шунинг учун "
            "H1 физика ҳақидаги далил сифатида қайтариб олинади."
        ),
        measured_en=(
            "α = 1.0005 with interval [0.9999, 1.0012], which contains the ideal 1. "
            "β = 0.5086 with interval [0.5068, 0.5104], which excludes 0.5, so the "
            "criterion is met. But free exponents improve the RMSE by only 1.09%, and the "
            "fit is to the continuous discharge series, which is itself a rating output. "
            "H1 is therefore withdrawn as evidence about the physics."
        ),
        verdict=Verdict.WITHDRAWN,
        evidence=("gate_law:h1", "gate_law:effect_size"),
        script="identify_gate_law.py",
    ),
    Entry(
        key="H3",
        question_uz="Сарф коэффициенти иш диапазони бўйича доимийми?",
        question_en="Is the discharge coefficient constant across the operating range?",
        expected_uz="«Тарқалиш 0.1–0.5% атрофида бўлади деб кутаман; ҳар ҳолда 1% дан анча кичик.»",
        expected_en=(
            "“I expect a spread of roughly 0.1–0.5%; in any case well below 1%.”"
        ),
        measured_uz=(
            "Ҳар бир рейтинг даври ичида 0.01% — кутганимдан бир тартиб кичик. Йўналиш "
            "тўғри, катталик эмас; кутиш ўзгартирилмади. Бу сон физика ҳақида эмас: "
            "κ узлуксиз сарф қаторидан ҳисобланади, у қатор эса айнан шу формула "
            "билан ҳосил қилинган. H3 ҳам H1 каби қайтариб олинади — ва айнан шу 0.01% "
            "доиравийликнинг энг кучли ўлчови бўлиб қолади."
        ),
        measured_en=(
            "0.01% within each rating period — an order of magnitude tighter than expected. "
            "The direction was right, the magnitude was not; the expectation stands "
            "unedited. The number says nothing about the physics: kappa is computed from "
            "the continuous discharge series, which is produced by this very formula. H3 is "
            "withdrawn like H1 — and that same 0.01% becomes the strongest measure of the "
            "circularity."
        ),
        verdict=Verdict.WITHDRAWN,
        evidence=(
            "discharge_coefficient:by_period",
            "discharge_coefficient:pooled_inflation",
        ),
        script="discharge_coefficient.py",
    ),
    Entry(
        key="H4",
        question_uz=(
            "Идеал затвор қонуни ҳеч қачон мослаштирилмаган мустақил дала гаугингларини "
            "такрорлайдими?"
        ),
        question_en=(
            "Does the ideal gate law reproduce independent field gaugings it was never "
            "fitted to?"
        ),
        expected_uz=(
            "Иккита мезон олдиндан ёзилди: нисбий қолдиқнинг медианаси ±5% ичида, ва "
            "қолдиқнинг предикторлар бўйича тузилиши 5% дан кичик."
        ),
        expected_en=(
            "Two criteria fixed in advance: the median relative residual within ±5%, and "
            "residual structure across the predictors below 5%."
        ),
        measured_uz=(
            "317 та гаугингдан 77 таси қабул қилинди. Медиана +0.51%, IQR 3.58%, "
            "тузилиш 2.26% ва 1.78%. Иккала мезон ҳам бажарилди. Баҳо синфи бўйича: "
            "`Good` (n=28) IQR 2.94%, `Fair` (n=49) IQR 4.24% — сифатлироқ ўлчовда "
            "тарқалиш кичикроқ, яъни қолдиқнинг катта қисми ўлчов ноаниқлиги."
        ),
        measured_en=(
            "77 of 317 gaugings were accepted. Median +0.51%, IQR 3.58%, structure 2.26% "
            "and 1.78%: both criteria met. By quality class, Good (n=28) has an IQR of "
            "2.94% and Fair (n=49) of 4.24% — the better measurements scatter less, which "
            "says most of the residual is measurement uncertainty."
        ),
        verdict=Verdict.SUPPORTED,
        evidence=(
            "gate_law_validation:relative_residual",
            "gate_law_validation:structure_spread",
            "gate_law_validation:by_rating",
        ),
        script="validate_gate_law.py",
    ),
    Entry(
        key="H2-1",
        question_uz=(
            "Бошқарувчи эталон қонунини кўтарганда қиладиган модел хатоси ёпиқ ҳалқа "
            "тестини оқлайдиган даражада каттами?"
        ),
        question_en=(
            "Is the model error a controller carries by using the benchmark law large "
            "enough to warrant a closed-loop test?"
        ),
        expected_uz="«Максимал конверт бўйича хато 1% дан катта бўлса, 2-босқич ўтказилади.»",
        expected_en=(
            "“If the error over the maximum envelope exceeds 1%, stage two goes "
            "ahead.”"
        ),
        measured_uz=(
            "Иккита конверт иккита жавоб берди: ASCE Test 2-1 диапазонида 0.906% "
            "(остонадан паст), кузатилган диапазонда 2.302% (юқори). Пре-регистрацияда "
            "«қайси конверт» ёзилмаган эди — бўшлиқ очиқ қайд этилди ва ўлчанган конверт "
            "фойдасига ҳал қилинди, чунки бўшлиқни иш ҳажмини камайтирадиган томонга ҳал "
            "қилиш — айнан пре-регистрация тўсадиган нарса."
        ),
        measured_en=(
            "The two envelopes gave two answers: 0.906% over the ASCE Test 2-1 range "
            "(below the threshold) and 2.302% over the observed range (above it). The "
            "pre-registration had not said which envelope decides. The gap was recorded "
            "openly and resolved in favour of the measured envelope, because resolving a "
            "gap towards less work is exactly what pre-registration exists to prevent."
        ),
        verdict=Verdict.SUPPORTED,
        evidence=(
            "model_error_envelope:largest_error_including_ci",
            "model_error_envelope:threshold",
        ),
        script="model_error_envelope.py",
    ),
    Entry(
        key="H2-2",
        question_uz=(
            "Идентификация қилинган қонунда созилган бошқарувчи эталон қонунидагисидан "
            "яхшироқ ишлайдими?"
        ),
        question_en=(
            "Does a controller tuned on the identified law outperform one tuned on the "
            "benchmark law?"
        ),
        expected_uz=(
            "Мезон: δ нинг bootstrap интервали нолни ўз ичига олса, натижа рад "
            "этувчи ҳисобланади. Механизм ҳақидаги кутиш ҳам ёзилди — интеграл таъсир "
            "турғун ҳолат хатосини йўқотади."
        ),
        expected_en=(
            "Criterion: the result is negative if the bootstrap interval for δ contains "
            "zero. A mechanism expectation was recorded too: integral action removes the "
            "steady-state error."
        ),
        measured_uz=(
            "100 жуфтланган такрор: PI да δ = −1.658% [−1.756, −1.553], MPC да "
            "−0.482% [−0.484, −0.480] — интервал нолни ўз ичига олмайди. Абсолют фарқ эса "
            "0.07 мм, яъни сатҳ датчиги қадамининг 5% и. Механизм тасдиқланди: PI да StE "
            "тўртала комбинацияда уч хона аниқликда бир хил, интеграл ҳадсиз MPC да эса "
            "фарқ қилади."
        ),
        measured_en=(
            "Over 100 paired replicates δ is −1.658% [−1.756, −1.553] for PI and −0.482% "
            "[−0.484, −0.480] for MPC, so the interval excludes zero. In absolute terms "
            "that is 0.07 mm, about 5% of one level-sensor step. The mechanism expectation "
            "held: PI's steady-state error is identical to three digits across all four "
            "combinations, while MPC, which has no integral term, differs."
        ),
        verdict=Verdict.SUPPORTED,
        evidence=(
            "control_comparison:controllers.PI.delta",
            "control_comparison:controllers.MPC.delta",
            "control_comparison:controllers.MPC.delta_absolute_m",
        ),
        script="control_comparison.py",
    ),
    Entry(
        key="H2-s3",
        question_uz=(
            "Минимал затвор қадами (ўлик зона) IAQ ни қанча туширади — юқори IAQ "
            "артефактми?"
        ),
        question_en=(
            "How much does a minimum gate step lower IAQ — is the high IAQ an artefact?"
        ),
        expected_uz=(
            "Йўналиш: «IAQ ва IAW иккала контроллерда ҳам камаяди (ёки ўзгармайди)». "
            "Катталик: «PI да камайиш 20% дан кам». Тартиб: «MPC даги нисбий ўзгариш PI "
            "никидан катта». Қарор қоидаси: камайиш >50% бўлса артефакт, <20% бўлса "
            "ҳақиқий тебраниш."
        ),
        expected_en=(
            "Direction: “IAQ and IAW fall (or stay put) for both controllers.” "
            "Magnitude: “the fall for PI is under 20%.” Ordering: “the "
            "relative change is larger for MPC than for PI.” Decision rule: above "
            "50% the high IAQ is an artefact, below 20% it is genuine oscillation."
        ),
        measured_uz=(
            "PI да IAQ **ошди** (+0.3% … +1.3%) — йўналиш кутиши нотўғри чиқди ва "
            "ўзгартирилмади. Катталик ва тартиб кутишлари тўғри: MPC да IAQ −4.5% … −4.9%, "
            "IAW −7.1% … −7.7%. Қарор қоидасининг «<20%» тармоғи ишлади, демак 86 м³/с ли "
            "IAQ ўлик зона йўқлигининг артефакти эмас. Протоколдаги бўшлиқ ҳам ёзилди: "
            "ўлчовдан фақат медианалар сақланган, шунинг учун PI даги кичик ошиш нолдан "
            "фарқ қиладими — айтиб бўлмайди."
        ),
        measured_en=(
            "For PI, IAQ *rose* (+0.3% … +1.3%): the direction expectation was wrong and "
            "stands unedited. The magnitude and ordering expectations held — for MPC, IAQ "
            "changed by −4.5% … −4.9% and IAW by −7.1% … −7.7%. The rule's “below "
            "20%” branch applies, so the 86 m³/s IAQ is not an artefact of the missing "
            "deadband. A gap in the protocol is recorded too: only medians were stored, so "
            "whether PI's small rise differs from zero cannot be said."
        ),
        verdict=Verdict.EXPECTATION_WRONG,
        evidence=("control_comparison:sensitivity.min_gate_step",),
        script="control_comparison.py",
    ),
    Entry(
        key="H5",
        question_uz="Доиравийлик иккинчи, мустақил иншоотда ҳам такрорланадими?",
        question_en="Does the circularity repeat at a second, independent structure?",
        expected_uz=(
            "Учта тармоқ олдиндан ёзилди. κ тарқалиши < 0.1% — доиравийлик айнан "
            "ўша шаклда; ≥ 0.1% лекин рейтинг мослиги < 1% — доиравийлик такрорланади, "
            "шакли бошқа; иккаласи ҳам бажарилмаса — такрорланмайди. Кутиш: κ "
            "доимий бўлмайди (>1%), лекин сарф барибир рейтинг чиқиши бўлади."
        ),
        expected_en=(
            "Three branches fixed in advance: a kappa spread below 0.1% means the "
            "circularity repeats in the same form; at or above 0.1% but with a rating fit "
            "below 1% it repeats in a different form; neither means it does not repeat. "
            "The expectation recorded was that kappa would not be constant (above 1%) but "
            "the discharge would still be a rating output."
        ),
        measured_uz=(
            "09428500 да κ тарқалиши 17.16%, типик тўлиқ кун 9.56% — асосий "
            "сайтдаги 0.0093% билан таққосланмайди. Лекин log Q ни log Δh ва "
            "log a бўйича мослаш медиана |қолдиқ| ни 0.85% га туширади. Иккинчи тармоқ: "
            "**доиравийлик такрорланади, шакли бошқа**. Кутишнинг иккала қисми ҳам тўғри "
            "чиқди."
        ),
        measured_en=(
            "At 09428500 the kappa spread is 17.16% and a typical complete day deviates by "
            "9.56%, against 0.0093% at the primary site. Yet a fit of log Q on log Δh and "
            "log a leaves a median absolute residual of 0.85%. That is branch two: the "
            "circularity repeats in a different form. Both halves of the expectation were "
            "correct."
        ),
        verdict=Verdict.SUPPORTED,
        evidence=(
            "second_structure:kappa_all",
            "second_structure:rating_fit",
            "second_structure:branch",
        ),
        script="second_structure.py",
    ),
    Entry(
        key="H5b",
        question_uz=(
            "Иккинчи иншоотдаги 0.85% лик қолдиқ тузилганми (ҳисоблашнинг нотўғри шакли) "
            "ёки шовқинми (ҳақиқий ўлчов)?"
        ),
        question_en=(
            "Is the 0.85% residual at the second structure structured (a wrong formula) or "
            "noise (a real measurement)?"
        ),
        expected_uz=(
            "Мезон олдиндан ёзилди: бин медианаларининг тарқалиши медиана |қолдиқ| дан 1.0 "
            "баробар катта бўлса — тузилган; 0.5 дан кичик бўлса — шовқин."
        ),
        expected_en=(
            "Criterion fixed in advance: if the spread of bin medians exceeds the median "
            "absolute residual by a factor above 1.0 the residual is structured; at or "
            "below 0.5 it is noise."
        ),
        measured_uz=(
            "Нисбат a бўйича 2.57, Δh бўйича 2.50 — иккаласи ҳам 1.0 дан катта; "
            "lag-1 автокорреляция 0.9761. Қолдиқ **тузилган**, демак сарф ўлчанмайди, "
            "ҳисобланади. Эҳтиёт очиқ ёзилди: иккала предиктор коллинеар "
            "(H<sub>1</sub> деярли доимий бўлгани учун Δh ≈ const − H<sub>2</sub>), шунинг "
            "учун иккита бин таҳлили битта тузилишнинг икки кўриниши."
        ),
        measured_en=(
            "The ratio is 2.57 against a and 2.50 against Δh, both above 1.0, with a lag-1 "
            "autocorrelation of 0.9761. The residual is structured, so the discharge is "
            "computed rather than measured. One caveat is recorded openly: the two "
            "predictors are collinear (H1 is nearly constant, so Δh ≈ const − H2), which "
            "makes the two bin analyses one structure seen twice."
        ),
        verdict=Verdict.SUPPORTED,
        evidence=("second_structure:h5b",),
        script="second_structure.py",
    ),
)


def by_verdict(verdict: Verdict) -> tuple[Entry, ...]:
    return tuple(entry for entry in RECORD if entry.verdict is verdict)


def counts() -> dict[Verdict, int]:
    return {verdict: len(by_verdict(verdict)) for verdict in Verdict}
