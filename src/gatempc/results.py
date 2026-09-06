"""Reading what the scripts published, with the source of every number attached.

The rule this module exists to enforce: a number shown to anyone carries the file and
the key it came from. A caller never indexes into a dictionary by hand; it asks for a
*reference* such as ``gate_law:full_fit.alpha`` and gets back both the value and the
string ``results/gate_law.json -> full_fit.alpha``. If a result file is missing or a
key was renamed, the caller reports that instead of a plausible-looking number.

Two things read results this way: the results explorer, and the script that builds the
manuscript. That is why this lives in the package rather than under ``gui`` — it began
there, and the name was a small lie as soon as the manuscript started reading the same
files. Nothing here imports Qt, so it works on a machine with no GUI toolkit at all.

Paths are built with pathlib only, so the same code runs on Windows, macOS and Linux.
"""

from __future__ import annotations

import csv
import json
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------- paths

#: A directory is the project root when all of these are found inside it.
ROOT_MARKERS: tuple[str, ...] = ("scripts", "src", "tests")


@dataclass(frozen=True)
class ProjectPaths:
    """Where the published material lives, relative to one root directory."""

    root: Path

    @classmethod
    def discover(cls, start: Path | str | None = None) -> "ProjectPaths":
        """Walk up from ``start`` (default: this file) until the markers are found.

        Falls back to the second parent of this file, which is the root in the
        layout the repository ships with: ``<root>/src/gatempc/results.py``. The
        count was three while this module was ``<root>/src/gatempc/gui/data.py``,
        and moving the file did not move the count with it — so the fallback
        pointed one level ABOVE the repository, and a laboratory run reaching it
        would have created ``build/`` outside the project. A clone never reaches
        the fallback, since the markers are found; an installed package does.
        """
        here = Path(start).resolve() if start is not None else Path(__file__).resolve()
        for candidate in (here, *here.parents):
            if candidate.is_dir() and all((candidate / m).is_dir() for m in ROOT_MARKERS):
                return cls(candidate)
        return cls(Path(__file__).resolve().parents[2])

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def figures(self) -> Path:
        return self.results / "figures"

    @property
    def tables(self) -> Path:
        return self.results / "tables"

    @property
    def scripts(self) -> Path:
        return self.root / "scripts"

    @property
    def data_package(self) -> Path:
        return self.root / "DATA" / "USGS_canal_gates_v1"

    def relative(self, path: Path) -> str:
        """``path`` written the way the manuscript writes it: forward slashes, no root."""
        try:
            rel = path.resolve().relative_to(self.root.resolve())
        except ValueError:
            return str(path)
        return rel.as_posix()


# ------------------------------------------------------------------------- results

#: Result files the GUI knows about, in the order the pipeline writes them.
RESULT_FILES: tuple[str, ...] = (
    # A dated snapshot of somebody else's archive rather than a computation over
    # the published package: it answers how many structures publish what the
    # method needs, as of the day it was asked, and a later run may legitimately
    # answer differently. Every other file here is reproducible offline from
    # DATA/ and will give the same number in ten years. The file carries its own
    # query and retrieval date for that reason.
    "station_survey",
    "archive_diagnostics",
    "gate_law",
    "discharge_coefficient",
    "gate_law_validation",
    "second_structure",
    "model_error_envelope",
    "control_comparison",
    "figure_provenance",
)

MISSING = object()


@dataclass(frozen=True)
class Value:
    """A number (or string) together with the file and key it was read from.

    ``ok`` is False when the file or the key was absent. Widgets render that state
    rather than substituting a default, because a blank card is honest and a stale
    number is not.
    """

    value: Any
    source: str
    ok: bool = True
    problem: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.ok


class Results:
    """Lazy reader over ``results/*.json``."""

    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths
        self._cache: dict[str, Any] = {}

    # -- file level -------------------------------------------------------------

    def path_of(self, name: str) -> Path:
        return self.paths.results / f"{name}.json"

    def has(self, name: str) -> bool:
        return self.path_of(name).is_file()

    def document(self, name: str) -> Any:
        if name not in self._cache:
            path = self.path_of(name)
            if not path.is_file():
                self._cache[name] = MISSING
            else:
                with path.open(encoding="utf-8") as handle:
                    self._cache[name] = json.load(handle)
        return self._cache[name]

    def missing_files(self) -> list[str]:
        return [n for n in RESULT_FILES if not self.has(n)]

    # -- value level ------------------------------------------------------------

    def value(self, reference: str) -> Value:
        """``"gate_law:full_fit.alpha"`` -> the number plus its provenance string.

        A key may be an integer to index into a list: ``"a:folds.0.rmse"``.
        """
        file_name, _, dotted = reference.partition(":")
        source = f"results/{file_name}.json"
        if dotted:
            source += f" -> {dotted}"
        document = self.document(file_name)
        if document is MISSING:
            return Value(None, source, False, f"results/{file_name}.json not found")
        node: Any = document
        for key in filter(None, dotted.split(".")):
            if isinstance(node, dict) and key in node:
                node = node[key]
            elif isinstance(node, (list, tuple)) and key.lstrip("-").isdigit():
                index = int(key)
                if -len(node) <= index < len(node):
                    node = node[index]
                else:
                    return Value(None, source, False, f"index {key} out of range")
            else:
                return Value(None, source, False, f"key {key!r} not present")
        return Value(node, source)

    def number(self, reference: str) -> float | None:
        found = self.value(reference)
        return float(found.value) if found.ok and isinstance(found.value, (int, float)) else None


# ---------------------------------------------------------------------- formatting


def as_percent(value: Any, digits: int = 2) -> str:
    """0.0521 -> ``5.21%``. Fractions are what every criterion in this study uses."""
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value * 100:.{digits}f}%"


def as_signed_percent(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value * 100:+.{digits}f}%"


def as_number(value: Any, digits: int = 4) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    if isinstance(value, float):
        return f"{value:,.{digits}f}".replace(",", " ")
    if value is None:
        return "—"
    return str(value)


def as_interval(pair: Any, digits: int = 4) -> str:
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return f"[{as_number(pair[0], digits)}, {as_number(pair[1], digits)}]"
    return "—"


# -------------------------------------------------------------------------- tables


@dataclass(frozen=True)
class Table:
    """A CSV under ``results/tables`` prepared for display."""

    path: Path
    header: list[str]
    rows: list[list[str]]
    truncated: bool = False

    @property
    def name(self) -> str:
        return self.path.name


def read_table(path: Path, limit: int = 400) -> Table | None:
    """Read a results CSV. ``limit`` keeps a 38 000-row profile out of the window."""
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return Table(path, [], [])
        rows: list[list[str]] = []
        truncated = False
        for row in reader:
            if len(rows) >= limit:
                truncated = True
                break
            rows.append(row)
    return Table(path, header, rows, truncated)


def manuscript_tables(paths: ProjectPaths) -> list[Path]:
    """``table_1_series.csv`` … ``table_A1_provenance.csv``, in manuscript order."""
    directory = paths.tables
    if not directory.is_dir():
        return []
    numbered = sorted(directory.glob("table_[0-9]*.csv"), key=lambda p: p.name)
    appendix = sorted(directory.glob("table_A*.csv"), key=lambda p: p.name)
    return numbered + appendix


def supporting_tables(paths: ProjectPaths) -> list[Path]:
    """Everything else under ``results/tables`` — the per-fold and per-bin detail."""
    directory = paths.tables
    if not directory.is_dir():
        return []
    manuscript = {p.name for p in manuscript_tables(paths)}
    return sorted(
        (p for p in directory.glob("*.csv") if p.name not in manuscript),
        key=lambda p: p.name,
    )


# ------------------------------------------------------------------------- figures


@dataclass(frozen=True)
class Figure:
    """One published figure and the files it was drawn from."""

    number: int
    name: str
    path: Path
    section: str = ""
    what: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def figures(paths: ProjectPaths, results: Results) -> list[Figure]:
    """Merge ``results/figure_provenance.json`` with what is actually on disk.

    Provenance is authoritative for the caption and the source list because
    ``make_figures.py`` records the files it opened at run time. Disk is
    authoritative for existence.
    """
    provenance = results.document("figure_provenance")
    entries = provenance.get("figures", []) if isinstance(provenance, dict) else []
    known: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("number"), int):
            known[entry["number"]] = entry

    found: list[Figure] = []
    for image in sorted(paths.figures.glob("fig[0-9][0-9]_*.png")):
        try:
            number = int(image.name[3:5])
        except ValueError:
            continue
        entry = known.get(number, {})
        sources = entry.get("sources") or []
        found.append(
            Figure(
                number=number,
                name=str(entry.get("name") or image.stem.split("_", 1)[-1]),
                path=image,
                section=str(entry.get("section") or ""),
                what=str(entry.get("what") or ""),
                sources=[str(s) for s in sources if isinstance(s, str)],
            )
        )
    return found


# ------------------------------------------------------------------- data package


def package_files(paths: ProjectPaths) -> list[Path]:
    directory = paths.data_package
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*") if p.is_file())


def checksum_count(paths: ProjectPaths) -> int:
    """How many files ``SHA256SUMS`` covers. 0 when the package is absent."""
    sums = paths.data_package / "SHA256SUMS"
    if not sums.is_file():
        return 0
    with sums.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


# ----------------------------------------------------------------------- pipeline


@dataclass(frozen=True)
class Step:
    """One runnable script, with the reason it exists and what it writes."""

    script: str
    uzbek: str
    english: str
    writes: tuple[str, ...]
    arguments: tuple[str, ...] = ()
    minutes: str = ""

    def command(self, paths: ProjectPaths) -> list[str]:
        """The exact command line, using the interpreter that is running the GUI."""
        return [sys.executable, str(paths.scripts / self.script), *self.arguments]


#: The published pipeline, in dependency order. Every script here is allowlisted for
#: the public repository; nothing in ``build/`` is offered, because a reviewer does
#: not have it.
PIPELINE: tuple[Step, ...] = (
    Step(
        "download_usgs.py",
        "Маълумот тўпламини текшириш — ҳар бир файлнинг SHA-256 йиғиндиси",
        "Verify the data package — SHA-256 of every file",
        ("DATA/USGS_canal_gates_v1/SHA256SUMS",),
        ("--verify",),
        "< 1",
    ),
    Step(
        "download_usgs.py",
        "Архив сурати (H6): затвор очилишини эълон қиладиган иншоотлардан "
        "нечтаси усул талаб қиладиган тўртта қаторни ҳам эълон қилади. "
        "ТАРМОҚ керак; уланиш бўлмаса эълон қилинган сурат сақлаб қолинади",
        "A census of the archive (H6): how many structures publishing a gate "
        "opening also publish the four series the method needs. NEEDS THE "
        "NETWORK; with none, the published snapshot is kept rather than lost",
        ("results/station_survey.json",),
        ("--survey",),
        "< 1",
    ),
    Step(
        "archive_diagnostics.py",
        "Архивнинг диагностикаси: қамров, нуқсонлар, затвор ҳаракатлари, кунлик κ",
        "Archive diagnostics: coverage, defects, gate movement, daily kappa",
        ("results/archive_diagnostics.json", "results/tables/kappa_daily.csv"),
        minutes="1–2",
    ),
    Step(
        "identify_gate_law.py",
        "Затвор қонунини идентификация қилиш (H1) ва z₀ профили (H0c-2)",
        "Identify the gate law (H1) and profile z0 (H0c-2)",
        ("results/gate_law.json", "results/tables/gate_law_folds.csv"),
        minutes="1–3",
    ),
    Step(
        "discharge_coefficient.py",
        "κ рейтинг даврлари ичида қанчалик текис (H3 — доиравийликнинг ўлчови)",
        "How flat kappa is within a rating period (H3 — the measure of circularity)",
        ("results/discharge_coefficient.json",),
        minutes="< 1",
    ),
    Step(
        "validate_gate_law.py",
        "Мустақил дала гаугинглари билан текширув (H4)",
        "Check against independent field gaugings (H4)",
        ("results/gate_law_validation.json", "results/tables/gauging_residuals.csv"),
        minutes="< 1",
    ),
    Step(
        "second_structure.py",
        "Доиравийлик иккинчи иншоотда ҳам борми (H5, H5b)",
        "Does the circularity repeat at a second structure (H5, H5b)",
        ("results/second_structure.json",),
        minutes="< 1",
    ),
    Step(
        "model_error_envelope.py",
        "Бошқарувчи кўтарадиган модел хатосининг чегараси (H2, 1-босқич)",
        "The model error a controller would carry (H2, stage one)",
        ("results/model_error_envelope.json",),
        minutes="< 1",
    ),
    Step(
        "control_comparison.py",
        "Ёпиқ ҳалқа таққослови: MPC ва PI, тўртта комбинация, сезгирлик",
        "Closed-loop comparison: MPC and PI, four combinations, sensitivity",
        ("results/control_comparison.json", "results/tables/control_comparison.csv"),
        minutes="< 1",
    ),
    Step(
        "make_figures.py",
        "Ўнта расм ва улар очган файлларнинг рўйхати",
        "The ten figures and the list of files each one opened",
        ("results/figures/*.png", "results/figure_provenance.json"),
        minutes="1",
    ),
    Step(
        "make_tables.py",
        "Мақоланинг жадваллари ва Илова A",
        "The manuscript tables and Appendix A",
        ("results/tables/table_*.csv", "results/tables/manuscript_tables.md"),
        minutes="< 1",
    ),
)


def test_command(paths: ProjectPaths) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", str(paths.root / "tests")]


# -------------------------------------------------------------------- environment


def environment() -> dict[str, str]:
    """This machine, described the way the manuscript describes its own."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine() or "—",
        "processor": platform.processor() or "—",
        "executable": sys.executable,
    }


def recorded_environment(results: Results) -> dict[str, Any]:
    """The machine the published control numbers were measured on."""
    document = results.document("control_comparison")
    if isinstance(document, dict) and isinstance(document.get("environment"), dict):
        return dict(document["environment"])
    return {}


def same_machine(results: Results) -> bool | None:
    """Is the GUI running where the published timings were measured?

    ``None`` when there is nothing to compare against. The reproduce page uses this
    to say plainly whether a re-run would produce comparable timings, because the
    published runtime belongs to one machine and the manuscript says so.
    """
    recorded = recorded_environment(results)
    if not recorded:
        return None
    return (
        str(recorded.get("platform", "")) == platform.platform()
        and str(recorded.get("processor", "")) == (platform.processor() or "")
    )


def freshness(paths: ProjectPaths) -> list[tuple[str, float]]:
    """(relative path, mtime) for every published result file that exists."""
    found: list[tuple[str, float]] = []
    for name in RESULT_FILES:
        path = paths.results / f"{name}.json"
        if path.is_file():
            found.append((paths.relative(path), path.stat().st_mtime))
    return found


#: ``from gatempc.archive import ...`` / ``import gatempc.detector`` in a script.
_IMPORT = re.compile(r"^\s*(?:from|import)\s+gatempc\.([A-Za-z_][A-Za-z0-9_]*)",
                     re.MULTILINE)


def _producer_of(name: str) -> Step | None:
    """The pipeline step that writes ``results/<name>.json``, if any."""
    target = f"results/{name}.json"
    for step in PIPELINE:
        if target in step.writes:
            return step
    return None


def newest_source_change(paths: ProjectPaths, script: str | None = None) -> float:
    """Newest mtime among the code that produces a given result.

    Being precise here matters. An earlier version compared every result against the
    newest file anywhere under ``scripts/`` and ``src/``, so editing one script marked
    all eight results stale — a warning that is wrong is a warning people learn to
    ignore. What is compared now is the script that actually writes the result, plus
    the ``gatempc`` modules that script imports. The GUI is never part of it: it only
    displays.

    With no ``script``, the answer covers every published script, which is the right
    yardstick for "is anything out of date at all".
    """
    candidates: list[Path] = []
    scripts = [script] if script else [step.script for step in PIPELINE]
    for name in scripts:
        path = paths.scripts / name
        if not path.is_file():
            continue
        candidates.append(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file
            continue
        for module in set(_IMPORT.findall(text)):
            if module == "gui":
                continue
            imported = paths.root / "src" / "gatempc" / f"{module}.py"
            if imported.is_file():
                candidates.append(imported)
    return max((path.stat().st_mtime for path in candidates), default=0.0)


def stale_results(paths: ProjectPaths) -> list[str]:
    """Published results written before the code that produces them last changed.

    Returns the paths as the manuscript writes them, so the warning names a file the
    reader can go and look at.
    """
    stale: list[str] = []
    for relative_path, mtime in freshness(paths):
        step = _producer_of(Path(relative_path).stem)
        cutoff = newest_source_change(paths, step.script if step else None)
        if cutoff and mtime < cutoff:
            stale.append(relative_path)
    return stale


def sequence_of(names: Iterable[str]) -> Sequence[str]:  # pragma: no cover - helper
    return tuple(names)
