"""Tests for the results explorer that need no display and no PyQt6.

The one that earns its keep is ``test_every_reference_used_by_a_page_resolves``. Every
number the window shows is addressed as ``file:dotted.key``; the test collects those
strings out of the page sources and looks each one up in the real result files. If a
script renames a key, the window would otherwise show a dash where a number used to be
and nobody would notice until a reviewer did.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gatempc.gui import data as gdata
from gatempc.gui import i18n, preregistration

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "gatempc" / "gui"

#: ``"gate_law:full_fit.alpha"`` as it appears inside a page source.
REFERENCE = re.compile(
    r"""["'](?P<file>[a-z_]+):(?P<key>[A-Za-z0-9_.\-/]*)["']"""
)


def gui_sources() -> list[Path]:
    return sorted(p for p in GUI.rglob("*.py") if "__pycache__" not in p.parts)


def collect_references() -> set[str]:
    found: set[str] = set()
    for source in gui_sources():
        text = source.read_text(encoding="utf-8")
        for match in REFERENCE.finditer(text):
            if match.group("file") in gdata.RESULT_FILES:
                found.add(f"{match.group('file')}:{match.group('key')}")
    return found


# ------------------------------------------------------------------ project paths


def test_project_root_is_found_from_the_gui_package():
    paths = gdata.ProjectPaths.discover()
    assert paths.root == ROOT
    for marker in gdata.ROOT_MARKERS:
        assert (paths.root / marker).is_dir()


def test_relative_paths_are_written_with_forward_slashes():
    paths = gdata.ProjectPaths.discover()
    assert paths.relative(paths.results / "gate_law.json") == "results/gate_law.json"


# --------------------------------------------------------------------- references


def test_every_result_file_is_read_somewhere_in_the_gui():
    """A published result nothing displays is either dead weight or a forgotten page."""
    used = {reference.split(":", 1)[0] for reference in collect_references()}
    # ``figure_provenance`` is read as a whole document rather than key by key.
    for source in gui_sources():
        text = source.read_text(encoding="utf-8")
        for name in gdata.RESULT_FILES:
            if f'document("{name}")' in text:
                used.add(name)
    unused = set(gdata.RESULT_FILES) - used
    assert not unused, f"result files no page ever reads: {sorted(unused)}"


def test_every_reference_used_by_a_page_resolves():
    paths = gdata.ProjectPaths.discover()
    results = gdata.Results(paths)
    missing_files = results.missing_files()
    if missing_files:
        pytest.skip(f"results not built yet: {', '.join(missing_files)}")
    broken = []
    for reference in sorted(collect_references()):
        found = results.value(reference)
        if not found.ok:
            broken.append(f"{reference}: {found.problem}")
    assert not broken, "references a page shows but the result files do not carry:\n" + "\n".join(
        broken
    )


def test_every_preregistration_reference_resolves():
    paths = gdata.ProjectPaths.discover()
    results = gdata.Results(paths)
    if results.missing_files():
        pytest.skip("results not built yet")
    broken = []
    for entry in preregistration.RECORD:
        for reference in entry.evidence:
            found = results.value(reference)
            if not found.ok:
                broken.append(f"{entry.key} -> {reference}: {found.problem}")
    assert not broken, "\n".join(broken)


# ---------------------------------------------------------- pre-registration record


def test_preregistration_entries_are_complete_and_bilingual():
    assert preregistration.RECORD
    keys = [entry.key for entry in preregistration.RECORD]
    assert len(keys) == len(set(keys)), "duplicate hypothesis key"
    for entry in preregistration.RECORD:
        for field in (
            entry.question_uz,
            entry.question_en,
            entry.expected_uz,
            entry.expected_en,
            entry.measured_uz,
            entry.measured_en,
        ):
            assert field.strip(), f"{entry.key} has an empty field"
        assert entry.script, f"{entry.key} names no script"


def test_preregistration_keeps_its_failures():
    """A record with nothing but successes would not be a pre-registration."""
    counts = preregistration.counts()
    assert counts[preregistration.Verdict.NOT_IDENTIFIED] >= 1
    assert counts[preregistration.Verdict.EXPECTATION_WRONG] >= 1
    assert counts[preregistration.Verdict.WITHDRAWN] >= 1


def test_no_latex_survives_into_the_interface():
    """Qt labels render HTML, not TeX, so a stray ``$...$`` would show as markup."""
    offenders = []
    for entry in preregistration.RECORD:
        for field in (
            entry.question_uz,
            entry.question_en,
            entry.expected_uz,
            entry.expected_en,
            entry.measured_uz,
            entry.measured_en,
        ):
            if "$" in field or "\\" in field:
                offenders.append(entry.key)
    assert not offenders, f"TeX left in: {sorted(set(offenders))}"


# ---------------------------------------------------------------------- pipeline


def test_every_pipeline_step_names_a_published_script():
    paths = gdata.ProjectPaths.discover()
    allowlist = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for step in gdata.PIPELINE:
        assert (paths.scripts / step.script).is_file(), f"{step.script} is missing"
        assert f"!/scripts/{step.script}" in allowlist, (
            f"{step.script} is offered by the GUI but is not published"
        )
        assert step.uzbek.strip() and step.english.strip()


def test_the_explorer_itself_is_published():
    """A reader told to run `python main.py` must find main.py in the public repository."""
    allowlist = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("!/main.py", "!/pyproject.toml", "!/requirements-gui.txt", "!/src/**"):
        assert entry in allowlist, f"{entry} is missing from the allowlist"
    for name in ("main.py", "pyproject.toml", "requirements-gui.txt"):
        assert (ROOT / name).is_file(), f"{name} is allowlisted but absent"


def test_pipeline_commands_use_the_running_interpreter():
    import sys

    paths = gdata.ProjectPaths.discover()
    for step in gdata.PIPELINE:
        command = step.command(paths)
        assert command[0] == sys.executable
        assert Path(command[1]).is_file()


# --------------------------------------------------------------- cross-platform


PLATFORM_SPECIFIC = (
    re.compile(r"[A-Za-z]:\\\\"),          # a drive letter, e.g. C:\\
    re.compile(r"os\.sep\s*==\s*['\"]\\\\"),
    re.compile(r"['\"]/(usr|home|Users|opt)/"),  # an absolute POSIX path
)


def test_the_gui_hard_codes_no_platform_specific_path():
    """The same source has to run on Windows, macOS and Linux."""
    offenders = []
    for source in gui_sources() + [ROOT / "main.py"]:
        text = source.read_text(encoding="utf-8")
        for pattern in PLATFORM_SPECIFIC:
            if pattern.search(text):
                offenders.append(f"{source.name}: {pattern.pattern}")
    assert not offenders, offenders


def test_the_gui_builds_paths_with_pathlib_only():
    """``os.path.join`` would be portable too, but mixing the two invites bugs."""
    offenders = []
    for source in gui_sources():
        text = source.read_text(encoding="utf-8")
        if "os.path.join" in text:
            offenders.append(source.name)
    assert not offenders, offenders


QT_IMPORT = re.compile(r"^\s*(?:import|from)\s+PyQt6\b", re.MULTILINE)


def test_the_qt_free_layer_imports_without_pyqt():
    """A reviewer who never installs PyQt6 must still be able to import the data layer."""
    for module in ("__init__", "data", "i18n", "preregistration"):
        source = (GUI / f"{module}.py").read_text(encoding="utf-8")
        assert not QT_IMPORT.search(source), f"{module}.py imports Qt at module level"


# ------------------------------------------------------------------------- i18n


def test_every_ui_string_exists_in_both_languages():
    for key, pair in i18n.UI.items():
        assert len(pair) == 2, key
        uzbek, english = pair
        assert uzbek.strip() and english.strip(), key
        assert i18n.ui("uz", key) == uzbek
        assert i18n.ui("en", key) == english


def test_unknown_languages_fall_back_to_uzbek():
    assert i18n.normalise(None) == "uz"
    assert i18n.normalise("de") == "uz"
    assert i18n.normalise("EN") == "en"
    assert i18n.pick("de", "uzbek", "english") == "uzbek"


def test_every_page_declares_both_nav_labels():
    from gatempc.gui import pages

    for key in pages.PAGE_KEYS:
        module = pages.module_of(key)
        uzbek, english = module.NAV
        assert uzbek.strip() and english.strip(), key
        assert "&" not in uzbek + english, (
            f"{key}: '&' becomes a keyboard mnemonic in a Qt button"
        )
        assert hasattr(module, "build"), f"{key} has no build()"


def test_nav_numbers_follow_the_page_order():
    """A reader is told to open “7 · …”; the seventh entry has to be it."""
    from gatempc.gui import pages

    for position, key in enumerate(pages.PAGE_KEYS, start=1):
        for label in pages.module_of(key).NAV:
            assert label.split("\u00b7")[0].strip() == str(position), (
                f"{key} is numbered {label!r} but sits at position {position}"
            )


def test_every_page_belongs_to_a_named_section():
    from gatempc.gui import pages

    for key in pages.PAGE_KEYS:
        section = pages.section_of(key)
        assert section in pages.SECTIONS, f"{key} is in the unknown section {section!r}"
    assert {pages.section_of(k) for k in pages.PAGE_KEYS} == set(pages.SECTIONS)


# --------------------------------------------------------------------- formatting


def test_formatters_never_invent_a_number():
    assert gdata.as_percent(None) == "—"
    assert gdata.as_number(None) == "—"
    assert gdata.as_interval(None) == "—"
    assert gdata.as_percent(0.0521, 2) == "5.21%"
    assert gdata.as_signed_percent(0.0051, 2) == "+0.51%"


def test_a_missing_key_is_reported_rather_than_defaulted():
    paths = gdata.ProjectPaths.discover()
    results = gdata.Results(paths)
    found = results.value("gate_law:no_such_key")
    assert not found.ok
    assert found.value is None
    assert "no_such_key" in found.problem or "not found" in found.problem



# ----------------------------------------------------------------- the laboratory


def test_laboratory_output_never_lands_in_results():
    """A run started from a form must not be able to overwrite a published number."""
    from gatempc.gui import lab

    paths = gdata.ProjectPaths.discover()
    directory = lab.lab_directory(paths)
    assert directory.is_relative_to(paths.root / "build")
    assert not directory.is_relative_to(paths.results)


def test_the_laboratory_is_qt_free():
    source = (GUI / "lab.py").read_text(encoding="utf-8")
    assert not QT_IMPORT.search(source), "lab.py imports Qt at module level"


def test_a_readers_own_csv_becomes_samples(tmp_path):
    from gatempc.gui import lab

    path = tmp_path / "readings.csv"
    path.write_text(
        "when,gate_ft,upstream_ft,downstream_ft,flow_cfs\n"
        "2026-01-01T00:00:00Z,1.0,10.0,8.0,100\n"
        "2026-01-01T00:15:00Z,,10.0,8.0,100\n"          # incomplete: skipped
        "2026-01-01T00:30:00Z,-0.02,10.0,8.0,0\n",      # negative opening: clipped
        encoding="utf-8",
    )
    mapping = {"time": "when", "a": "gate_ft", "h1": "upstream_ft",
               "h2": "downstream_ft", "q": "flow_cfs"}
    samples, skipped = lab.samples_from_csv(path, mapping, lab.FT, lab.FT3)
    assert skipped == 1
    assert len(samples) == 2
    assert samples[0].a == pytest.approx(0.3048)
    assert samples[0].dh == pytest.approx(2 * 0.3048)
    assert samples[1].a == 0.0, "a negative reading is clipped, as the archive reader does"


def test_a_missing_column_is_refused_rather_than_guessed(tmp_path):
    from gatempc.gui import lab

    path = tmp_path / "readings.csv"
    path.write_text("when,gate\n2026-01-01T00:00:00Z,1.0\n", encoding="utf-8")
    with pytest.raises(lab.ColumnMappingError):
        lab.samples_from_csv(path, {"time": "when", "a": "gate", "h1": "", "h2": "",
                                    "q": ""}, 1.0, 1.0)


def test_the_calculator_reads_its_laws_rather_than_carrying_them():
    """The coefficients must come from the result file, never from a literal."""
    source = (GUI / "pages" / "calculator.py").read_text(encoding="utf-8")
    assert "gate_law:full_fit" in (GUI / "lab.py").read_text(encoding="utf-8")
    assert "25.55" not in source and "0.5087" not in source, (
        "a fitted coefficient is hard-coded in the calculator"
    )


# --------------------------------------------------------------------- detector


def test_the_detector_thresholds_are_the_registered_ones():
    from gatempc.detector import BINS, KAPPA_TIGHT, RATING_TIGHT, STRUCTURED, UNSTRUCTURED

    assert (KAPPA_TIGHT, RATING_TIGHT) == (0.001, 0.01)
    assert (STRUCTURED, UNSTRUCTURED, BINS) == (1.0, 0.5, 5)


def test_second_structure_uses_the_shared_detector():
    """The script must not keep a private copy of the functions that were moved."""
    source = (ROOT / "scripts" / "second_structure.py").read_text(encoding="utf-8")
    assert "from gatempc.detector import" in source
    for moved in ("def ols3", "def binned_residual", "def lag1_autocorrelation",
                  "def spread"):
        assert moved not in source, f"{moved} is defined twice"


def test_the_published_detector_result_is_reproduced_by_the_shared_code():
    """Re-run the detector and compare it with what the published file says.

    This is the regression test for moving the computation out of the script: if the
    move changed anything, the two disagree here.
    """
    paths = gdata.ProjectPaths.discover()
    results = gdata.Results(paths)
    published = results.document("second_structure")
    if published is gdata.MISSING:
        pytest.skip("results/second_structure.json has not been built")
    site = published.get("site")
    year = published.get("year")
    observations = paths.data_package / "observations" / f"{site}_{year}.csv"
    if not observations.is_file():
        pytest.skip("the data package is not built")

    from gatempc.archive import load_fold
    from gatempc.detector import analyse

    samples, approvals = load_fold(str(paths.data_package), site, year,
                                   with_approval=True)
    approved = [s for s, flag in zip(samples, approvals) if flag]
    fresh = analyse(samples, approved)
    assert fresh["branch"] == published["branch"]
    assert fresh["h5b"]["branch"] == published["h5b"]["branch"]
    assert fresh["kappa_all"]["spread_iqr_over_median"] == pytest.approx(
        published["kappa_all"]["spread_iqr_over_median"])
    assert fresh["rating_fit"]["median_abs_relative_residual"] == pytest.approx(
        published["rating_fit"]["median_abs_relative_residual"])


# ------------------------------------------------------- parameters from the window


def test_the_scripts_the_window_parametrises_accept_those_flags():
    """Every flag the laboratory pages build has to exist in the script."""
    expected = {
        "second_structure.py": ("--site", "--year", "--bins", "--kappa-tight",
                                "--rating-tight", "--out"),
        "control_comparison.py": ("--replicates", "--pool-length", "--min-gate-step",
                                  "--out", "--out-csv", "--skip-sensitivity"),
    }
    for name, flags in expected.items():
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for flag in flags:
            assert f'"{flag}"' in source, f"{name} does not accept {flag}"


def test_parametrised_scripts_default_to_the_registered_values():
    """Running them with no flags must still produce the published numbers."""
    source = (ROOT / "scripts" / "control_comparison.py").read_text(encoding="utf-8")
    assert 'default=POOL_LENGTH' in source
    assert 'default=N_REPLICATES' in source
    assert '"--min-gate-step", type=float, default=0.0' in source
    second = (ROOT / "scripts" / "second_structure.py").read_text(encoding="utf-8")
    for default in ("default=SITE", "default=YEAR", "default=BINS",
                    "default=KAPPA_TIGHT", "default=RATING_TIGHT"):
        assert default in second, f"second_structure.py is missing {default}"
