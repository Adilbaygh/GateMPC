"""Apparatus page — how to use the window, and what its words mean.

Written for two readers who arrive with different questions: a reviewer who wants to
check a number and leave, and an engineer who wants to point the detector at their own
gate. The glossary is here because the study's argument turns on a handful of symbols,
and a reader who mixes up κ with C_d will misread every page.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ... import results as gdata
from .. import widgets as w
from . import Context


def build(context: Context) -> QWidget:
    body = w.column(16)
    layout = w.body_of(body)

    layout.addWidget(
        w.page_title(context.pick("Ёрдам", "Help"))
    )
    layout.addWidget(
        w.page_lead(
            context.pick(
                "Бу ойна иккита ишни бажаради: мақоланинг натижаларини кўрсатади ва "
                "мақоланинг усулини сизнинг маълумотингизга қўллайди. Қуйида — "
                "қаердан бошлаш, ҳар бир саҳифа нима қилади, белгилар нимани "
                "билдиради ва файллар қаерда.",
                "This window does two things: it shows the study's results, and it "
                "applies the study's method to your data. Below: where to start, what "
                "each page does, what the symbols mean, and where the files are.",
            )
        )
    )

    layout.addWidget(_start(context))
    layout.addWidget(_pages(context))
    layout.addWidget(_glossary(context))
    layout.addWidget(_files(context))
    layout.addWidget(_shortcuts(context))
    layout.addWidget(_rules(context))
    return w.wrap_scroll(body)


# ------------------------------------------------------------------ where to start


def _start(context: Context) -> QWidget:
    card = w.Card(context.pick("Қаердан бошлаш", "Where to start"))
    card.add(
        w.paragraph(
            context.pick(
                "<b>Тақризчи бўлсангиз:</b> «1 · Даъво» → «6 · Пре-регистрация» → "
                "«11 · Қайта юритиш». Учинчисида «Тўлиқ юришни бошлаш» тугмаси бор; "
                "у мақоладаги ҳар бир сонни нолдан қайта чиқаради ва ҳар бир "
                "буйруқни экранда кўрсатади.<br><br>"
                "<b>Муҳандис бўлсангиз:</b> «7 · Затвор калькулятори» да иккита қонунни "
                "ўз иш нуқтангизда таққосланг, кейин «8 · Доиравийлик детектори» да ўз "
                "иншоотингизнинг маълумотини текширинг.<br><br>"
                "<b>Шошилинч савол:</b> экраннинг тепасидаги сатр мақоланинг бутун "
                "даъвосини учта сон билан айтади.",
                "<b>If you are reviewing:</b> “1 · The claim” → “6 · Pre-registration” → "
                "“11 · Reproduce”. The last of those has a button that rebuilds every "
                "number in the manuscript from scratch and prints each command as it "
                "runs.<br><br>"
                "<b>If you are an engineer:</b> compare the two laws at your own operating "
                "point on “7 · Gate calculator”, then test your own structure's data on "
                "“8 · Circularity detector”.<br><br>"
                "<b>In a hurry:</b> the strip at the top of the window states the whole "
                "claim in three numbers.",
            )
        )
    )
    return card


# ------------------------------------------------------------------------- pages


def _pages(context: Context) -> QWidget:
    card = w.Card(context.pick("Саҳифалар", "The pages"))
    rows = [
        (
            context.pick("1–6 · Мақоланинг йўли", "1–6 · The argument"),
            context.pick(
                "Даъводан хулосагача бўлган занжир. Ҳар бир сон ўз файли ва калити "
                "билан кўрсатилади; қўлда киритилган сон йўқ.",
                "The chain from claim to conclusion. Every number carries the file and "
                "key it was read from; none of them is typed in.",
            ),
        ),
        (
            context.pick("7 · Затвор калькулятори", "7 · Gate calculator"),
            context.pick(
                "a, H₁, H₂ киритилади — иккита қонун бўйича Q, уларнинг фарқи ва κ "
                "чиқади. Тескари ҳисоб ҳам бор: керакли Q → зарур очилиш. Архивдаги "
                "диапазондан чиқсангиз, ойна экстраполяция қилаётганини айтади.",
                "Type a, H₁ and H₂ and read off Q under both laws, the gap between them "
                "and κ. The inverse works too: a required Q gives the opening each law "
                "asks for. Outside the range the archive covers, the page says it is "
                "extrapolating.",
            ),
        ),
        (
            context.pick("8 · Доиравийлик детектори", "8 · Circularity detector"),
            context.pick(
                "Маълумот тўпламидаги сайт-йил ёки ўзингизнинг CSV файлингиз. Керак "
                "бўладиган устунлар: вақт, затвор очилиши, юқори ва қуйи бьеф, сарф. "
                "Ҳукм олдиндан ёзилган уч тармоқли қоида бўйича чиқади.",
                "A site-year from the data package, or your own CSV. The columns it needs "
                "are: time, gate opening, both stages and discharge. The verdict follows "
                "the three-branch rule fixed in advance.",
            ),
        ),
        (
            context.pick("9 · Бошқарув тажрибаси", "9 · Control experiment"),
            context.pick(
                "Такрорлар сони, бьеф узунлиги ва ўлик зона киритилади; ойна "
                "`control_comparison.py` ни ўша параметрлар билан юритади ва δ ни "
                "кўрсатади. Натижа `build/lab/` га ёзилади.",
                "Set the replicates, the pool length and the deadband; the window runs "
                "`control_comparison.py` with those parameters and shows δ. The output "
                "goes to `build/lab/`.",
            ),
        ),
        (
            context.pick("10 · Расм ва жадваллар", "10 · Figures and tables"),
            context.pick(
                "Ўнта расм ва барча жадвал, ҳар бири қайси файллардан чизилгани билан.",
                "The ten figures and every table, each with the files it was drawn from.",
            ),
        ),
        (
            context.pick("11 · Қайта юритиш", "11 · Reproduce"),
            context.pick(
                "Ўнта скрипт, тестлар, ва бу машина билан натижалар ўлчанган "
                "машинанинг таққослови.",
                "The ten scripts, the tests, and this machine set beside the machine the "
                "results were measured on.",
            ),
        ),
    ]
    card.add(w.key_values(rows, columns=1))
    return card


# ---------------------------------------------------------------------- glossary


def _glossary(context: Context) -> QWidget:
    card = w.Card(
        context.pick("Белгилар", "Symbols"),
        context.pick(
            "Мақоланинг бутун далили шу еттита белгига таянади.",
            "The whole argument rests on these seven.",
        ),
    )
    rows = [
        ("a", context.pick("затвор очилиши, м", "gate opening, m")),
        ("H₁, H₂", context.pick("юқори ва қуйи бьеф сатҳлари, м",
                                "headwater and tailwater stage, m")),
        ("Δh", context.pick("напор фарқи, H₁ − H₂", "head difference, H₁ − H₂")),
        ("Q", context.pick("сарф, м³/с", "discharge, m³/s")),
        (
            "κ",
            context.pick(
                "Q ⁄ (a·√(2g·Δh)). Идеал ботирилган тешик қонунида бу C_d·W_эфф га "
                "тенг, яъни ДОИМИЙ. Демак κ нинг қимирламаслиги — сарф ўша формула "
                "билан ҳисобланганининг белгиси.",
                "Q ⁄ (a·√(2g·Δh)). Under the ideal submerged-orifice law this equals "
                "C_d·W_eff, that is, a CONSTANT. So a κ that does not move is the "
                "signature of a discharge computed by that formula.",
            ),
        ),
        (
            "Γ, α, β",
            context.pick(
                "Q = Γ·a^α·Δh^β даги коэффициент ва кўрсаткичлар. Идеал қонунда "
                "α = 1, β = 0.5.",
                "the coefficient and exponents in Q = Γ·a^α·Δh^β. The ideal law has "
                "α = 1 and β = 0.5.",
            ),
        ),
        (
            "δ",
            context.pick(
                "Идентификация қилинган қонунда созилган контроллернинг эталон "
                "қонунида созилганига нисбатан ютуғи, фоизда. Манфий — "
                "идентификация қилинган қонун фойдасига.",
                "what a controller tuned on the identified law gains over one tuned on "
                "the benchmark law, in per cent. Negative favours the identified law.",
            ),
        ),
        (
            "MAE, IAE, StE, IAQ, IAW",
            context.pick(
                "ASCE нинг бошқарув кўрсаткичлари: максимал ва интеграл абсолют "
                "хато, турғун ҳолат хатоси, сарф ва затвор ҳаракатининг интеграл "
                "ўзгариши.",
                "the ASCE control indicators: maximum and integrated absolute error, "
                "steady-state error, and the integrated absolute change in discharge and "
                "in gate position.",
            ),
        ),
    ]
    card.add(w.key_values(rows, columns=1))
    return card


# ------------------------------------------------------------------------- files


def _files(context: Context) -> QWidget:
    paths = context.paths
    card = w.Card(
        context.pick("Файллар қаерда", "Where the files are"),
        context.pick(
            "Ойна фақат оммавий репозиторийдаги нарсаларни ўқийди.",
            "The window reads only what is in the public repository.",
        ),
    )
    rows = [
        (context.pick("Лойиҳа папкаси", "Project folder"), str(paths.root)),
        (
            "DATA/USGS_canal_gates_v1/",
            context.pick(
                "нормаллаштирилган USGS қатламлари, провенанс ва SHA-256 йиғиндилари",
                "the normalised USGS layers, their provenance and SHA-256 checksums",
            ),
        ),
        (
            "scripts/",
            context.pick("эълон қилинган сонларни чиқарадиган ўнта скрипт",
                         "the ten scripts that produce the published numbers"),
        ),
        (
            "results/",
            context.pick("натижа JSON'лари, расмлар ва жадваллар",
                         "the result JSONs, figures and tables"),
        ),
        (
            "build/lab/",
            context.pick(
                "бу ойнадаги форма орқали чиқарилган нарсалар. results/ га ҳеч қачон "
                "ёзилмайди, ва build/ оммавий репозиторийга кирмайди.",
                "anything produced from a form in this window. It is never written into "
                "results/, and build/ is not part of the public repository.",
            ),
        ),
        (
            "tests/",
            context.pick(
                "маълумот тўплами, затвор қонуни, USGS мижози ва репозиторийнинг ўз "
                "тартиби учун тестлар",
                "tests for the data package, the gate law, the USGS client and the "
                "repository's own hygiene",
            ),
        ),
    ]
    card.add(w.key_values(rows, columns=1))
    return card


# --------------------------------------------------------------------- shortcuts


def _shortcuts(context: Context) -> QWidget:
    card = w.Card(context.pick("Тезкор тугмалар", "Keyboard shortcuts"))
    rows = [
        ("Ctrl+1 … Ctrl+9", context.pick("саҳифаларга ўтиш", "go to a page")),
        ("Ctrl+L", context.pick("тилни алмаштириш", "switch the language")),
        ("F1", context.pick("шу саҳифа", "this page")),
        ("F5", context.pick("тўлиқ юришни бошлаш", "run the whole pipeline")),
        ("Ctrl+T", context.pick("тестларни юритиш", "run the tests")),
        ("Esc", context.pick("юритилаётган ишни тўхтатиш", "stop what is running")),
        ("Ctrl+Q", context.pick("чиқиш", "quit")),
    ]
    card.add(w.key_values(rows, columns=2))
    return card


# ------------------------------------------------------------------------- rules


def _rules(context: Context) -> QWidget:
    card = w.Card(
        context.pick(
            "Ойна ўзига қўйган тўртта қоида",
            "Four rules this window holds itself to",
        )
    )
    card.add(
        w.paragraph(
            context.pick(
                "<b>1. Манбасиз сон кўрсатилмайди.</b> Ҳар бир карточканинг тагида уни "
                "ўқиган файл ва калит турибди. Калит топилмаса, ўрнига «калит йўқ» "
                "ёзилади — тахминий сон эмас.<br><br>"
                "<b>2. Ойна ҳеч нарсани яширинча ҳисобламайди.</b> Скрипт юритадиган "
                "ҳар бир тугманинг ёнида терминалда ёзиладиган айнан ўша сатр "
                "кўрсатилади.<br><br>"
                "<b>3. Формадан чиққан натижа results/ га ёзилмайди.</b> У "
                "<code>build/lab/</code> га боради, чунки эълон қилинган сон — "
                "рўйхатдан ўтган параметрлар билан юритилган скрипт ёзгани.<br><br>"
                "<b>4. Экстраполяция айтилади.</b> Даража қонуни ҳар қандай сонга жавоб "
                "беради; ўлчанган диапазондан чиққанда ойна шуни ёзади.",
                "<b>1. No number without its source.</b> Every card carries the file and "
                "key it was read from. If a key is missing, the card says so instead of "
                "showing a plausible number.<br><br>"
                "<b>2. The window computes nothing behind your back.</b> Every button that "
                "runs a script prints the exact command line you would type in a "
                "terminal.<br><br>"
                "<b>3. Nothing produced from a form is written into results/.</b> It goes "
                "to <code>build/lab/</code>, because a published number is what a script "
                "wrote with its registered parameters.<br><br>"
                "<b>4. Extrapolation is stated.</b> A power law will answer for any input; "
                "outside the measured range the window says so.",
            )
        )
    )
    missing = context.results.missing_files()
    if missing:
        card.add(
            w.paragraph(
                context.pick(
                    "Ҳозир етишмаётган натижа файллари: " + ", ".join(missing),
                    "Result files currently missing: " + ", ".join(missing),
                )
            )
        )
    else:
        card.add(
            w.paragraph(
                context.pick(
                    f"Ҳозир {len(gdata.RESULT_FILES)} та натижа файлининг ҳаммаси жойида.",
                    f"All {len(gdata.RESULT_FILES)} result files are present.",
                )
            )
        )
    return card
