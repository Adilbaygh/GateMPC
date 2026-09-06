"""Two languages, chosen once and applied everywhere.

Uzbek (Cyrillic) is the language the project is worked in; English is the language the
manuscript is written in. A reviewer reading the English side should see exactly the
wording the manuscript uses, so translations here are checked against the manuscript
rather than produced freely.

The helper is deliberately tiny: pages pass both strings at the point of use, which
keeps a sentence and its translation on adjacent lines where they can be compared.
"""

from __future__ import annotations

LANGUAGES: tuple[str, ...] = ("uz", "en")

DEFAULT_LANGUAGE = "uz"

#: What each language calls itself, for the switch in the header.
ENDONYM: dict[str, str] = {"uz": "Ўзбекча", "en": "English"}


def normalise(language: str | None) -> str:
    """Accept ``uz``/``uzbek``/``UZ`` and anything else falls back to the default."""
    if not language:
        return DEFAULT_LANGUAGE
    lowered = language.strip().lower()
    if lowered.startswith("uz") or lowered.startswith("ўз") or lowered.startswith("uz_"):
        return "uz"
    if lowered.startswith("en"):
        return "en"
    return DEFAULT_LANGUAGE


def pick(language: str, uzbek: str, english: str) -> str:
    """Return one of the two strings. Unknown languages get Uzbek."""
    return english if normalise(language) == "en" else uzbek


#: Labels that appear in the frame rather than in a page.
UI: dict[str, tuple[str, str]] = {
    "app_title": (
        "GateMPC — натижалар кўргичи",
        "GateMPC — results explorer",
    ),
    "headline_strip": (
        "Доиравий тест: 0.01%  ·  ҳалол чегара: 5%  ·  фарқ 500 баробар",
        "Circular test: 0.01%  ·  honest limit: 5%  ·  a factor of 500",
    ),
    "source_prefix": ("Манба", "Source"),
    "open_folder": ("Папкани очиш", "Open folder"),
    "missing_results": (
        "Натижа файллари топилмади. «Қайта юритиш» саҳифасидан тўлиқ юришни бошланг.",
        "No result files found. Start a full run from the “Reproduce” page.",
    ),
    "stale_results": (
        "Баъзи натижалар уларни ёзадиган коддан эскироқ.",
        "Some results are older than the code that writes them.",
    ),
    "everything_current": (
        "Барча натижа файллари жойида ва коддан янгироқ.",
        "Every result file is present and newer than the code.",
    ),
    "no_figure": (
        "Расм ҳали чизилмаган. `make_figures.py` ни юритинг.",
        "This figure has not been drawn yet. Run `make_figures.py`.",
    ),
    "rows_shown": ("кўрсатилди", "shown"),
    "of_rows": ("сатрдан", "of"),
    "copy": ("Нусха олиш", "Copy"),
    "copied": ("Нусха олинди", "Copied"),
    "run": ("Юритиш", "Run"),
    "stop": ("Тўхтатиш", "Stop"),
    "running": ("Юритилмоқда…", "Running…"),
    "done": ("Тайёр", "Done"),
    "failed": ("Хато", "Failed"),
    "not_run": ("Юритилмаган", "Not run"),
}


def ui(language: str, key: str) -> str:
    uzbek, english = UI[key]
    return pick(language, uzbek, english)
