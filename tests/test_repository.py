"""Hygiene checks on the directories the public repository ships.

Why this file exists
--------------------
The published tree is an allowlist: .gitignore excludes everything and then lets
named paths back in, and ``src/**`` and ``tests/**`` are let back in wholesale.
That is convenient and it is also the hole -- any file that lands in one of those
directories is published, whether or not anyone meant it to be.

One did. Working copies of three files were saved into the tree beside the
originals under the browser's duplicate names (``archive-1.py``,
``make_tables-1.py``, ``test_data_package-1.py``). Two of the three sat inside
wholesale-allowed directories, and the third was a second, stale copy of this
suite: it was collected and run, so the test count rose by 23 while nobody had
written 23 tests. A stale duplicate of a test file is worse than a useless one,
because it goes on asserting a rule the project has since changed its mind about.

These tests are cheap and they read the working tree rather than any result, so
they say something about the repository rather than about the study.
"""
import csv
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories the allowlist publishes, or publishes from.
PUBLISHED = ("src", "tests", "scripts", "DATA",
             os.path.join("results", "tables"),
             os.path.join("results", "figures"))

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
             ".hypothesis", ".git", ".venv", "node_modules"}

# What a copy looks like when a browser, an editor or a file manager makes one.
DUPLICATE = re.compile(
    r"""(
          -\d+          |   # archive-1.py
          \s\(\d+\)     |   # archive (1).py
          [ _-]cop(y|ie) |  # archive copy.py, archive_copy.py
          [ _-]nusxa        # the same word, on a localised system
        )$""",
    re.IGNORECASE | re.VERBOSE)

LEFTOVER_SUFFIXES = (".bak", ".orig", ".rej", ".tmp", ".temp", ".swp", "~")


def walk_published():
    """Every file under a published directory, as a path relative to ROOT."""
    for top in PUBLISHED:
        base = os.path.join(ROOT, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, ROOT).replace("\\", "/")


def test_no_duplicate_or_leftover_files_in_the_published_tree():
    """A second copy of a file is published as readily as the first one.

    The name is the whole signal here: nothing in this project is meant to be
    called ``something-1.py``. If a duplicate is a file worth keeping it needs a
    name that says what it is; if it is not, it does not belong in a directory
    the repository publishes wholesale.
    """
    offenders = []
    for rel in walk_published():
        name = os.path.basename(rel)
        stem, _ext = os.path.splitext(name)
        if DUPLICATE.search(stem) or name.endswith(LEFTOVER_SUFFIXES):
            offenders.append(rel)
    assert not offenders, (
        "files that look like copies or editor leftovers are sitting in "
        "directories the repository publishes:\n  " + "\n  ".join(offenders) +
        "\nDelete them, or give them a name that says what they are and put "
        "them somewhere private (build/ is not published).")


def test_every_module_in_src_can_actually_be_imported_by_its_name():
    """A file in ``src`` whose name is not an identifier is dead weight.

    ``archive-1.py`` cannot be imported under any circumstances -- the name is
    not a legal Python identifier -- so its only possible effect is to be
    published and read as if it were part of the package.
    """
    src = os.path.join(ROOT, "src")
    bad = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            stem = name[:-3]
            if not stem.isidentifier():
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
                bad.append(rel.replace("\\", "/"))
    assert not bad, (
        "these files ship inside the package but no import statement can ever "
        "name them:\n  " + "\n  ".join(bad))


def test_the_tests_directory_holds_no_second_copy_of_this_suite():
    """Two files defining the same test are two answers to the same question.

    Duplicate test modules do not collide -- pytest collects both -- so the only
    symptom is a test count that does not match what was written. That is a
    quiet failure mode, and it is worth one loud test.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    seen: dict[str, list[str]] = {}
    for name in os.listdir(here):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(here, name), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("def test_"):
                    fn = line[4:line.index("(")]
                    seen.setdefault(fn, []).append(name)
    clashes = {fn: files for fn, files in seen.items() if len(files) > 1}
    assert not clashes, (
        "the same test name is defined in more than one module, which usually "
        "means one of them is a stale copy:\n  " +
        "\n  ".join(f"{fn}: {', '.join(files)}" for fn, files in clashes.items()))


# --------------------------------------------------------------- provenance

APPENDIX_A = os.path.join(ROOT, "results", "tables", "table_A1_provenance.csv")

INDEXED = ("DATA", "results", "scripts", "src", "tests")


def files_by_name():
    """Every file in the tree that a provenance entry could be naming."""
    index: dict[str, list[str]] = {}
    for top in INDEXED:
        base = os.path.join(ROOT, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
                index.setdefault(name, []).append(rel.replace("\\", "/"))
    return index


def test_every_file_named_in_appendix_a_is_on_disk():
    """The repository's own rule, applied to the table that states it.

    Appendix A is the manuscript's promise that every number can be traced to a
    published file. A name in it that leads nowhere breaks that promise more
    quietly than a wrong number would, because a reader only finds out when they
    go looking. The table is generated rather than typed, so this should hold by
    construction -- which is exactly why it is worth asserting: the day it stops
    holding, something in the generation has quietly changed.

    Both columns are checked. The artefact a row describes has to be on disk too,
    not only the files it was built from: a row for a figure nobody draws any more
    would describe the provenance of nothing.
    """
    if not os.path.exists(APPENDIX_A):
        pytest.skip("Appendix A has not been built; run scripts/make_tables.py")

    index = files_by_name()
    missing = []
    with open(APPENDIX_A, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            artefact = row["Artefact"].strip()
            if artefact not in index:
                missing.append((artefact, artefact))
            for token in row["Built from"].split(","):
                token = token.strip()
                # Prose entries ("drawn by ..., no data") are not file names.
                if not token or " " in token or "." not in token:
                    continue
                if token not in index:
                    missing.append((artefact, token))
    assert not missing, (
        "Appendix A names files that are not in the repository:\n  " +
        "\n  ".join(f"{item}: {name}" for item, name in missing))


def test_appendix_a_covers_every_table_and_figure_that_exists():
    """A provenance table that lists only some of the work is worse than none.

    The figures on disk and the table CSVs beside them are the manuscript's
    inventory; Appendix A has to account for all of them. This catches the
    failure where a new figure is drawn and the appendix, built from a stale
    provenance file, goes on describing the previous set.
    """
    if not os.path.exists(APPENDIX_A):
        pytest.skip("Appendix A has not been built; run scripts/make_tables.py")

    with open(APPENDIX_A, encoding="utf-8", newline="") as fh:
        listed = {row["Artefact"].strip() for row in csv.DictReader(fh)}

    tables_dir = os.path.join(ROOT, "results", "tables")
    figures_dir = os.path.join(ROOT, "results", "figures")

    # File names on both sides. An earlier version of this test rebuilt the expected
    # set as "Table 1", "Fig. 1" ... from those same file names, which quietly assumed
    # that a figure's file number is its number in the manuscript. It is not: the
    # manuscript numbers by order of appearance, and the two agreed for none of the
    # ten figures. Appendix A is keyed by file name for that reason, and the
    # manuscript number against each row is supplied by build/make_manuscript.py.
    expected = set()
    for name in os.listdir(tables_dir):
        m = re.fullmatch(r"table_(\w+?)_\w+\.csv", name)
        if m and m.group(1) != "A1":
            expected.add(name)
    if os.path.isdir(figures_dir):
        for name in os.listdir(figures_dir):
            if re.fullmatch(r"fig(\d+)_\w+\.png", name):
                expected.add(name)

    assert expected, "no tables or figures on disk to check the appendix against"
    assert expected <= listed, (
        "these exist on disk but Appendix A does not account for them: "
        f"{sorted(expected - listed)}. Rerun scripts/make_figures.py and then "
        f"scripts/make_tables.py so the appendix is rebuilt from what is there.")


def test_no_table_cites_a_source_by_private_shorthand():
    """A table's sources have to be citations, not codes only the author knows.

    Table 4 named its sources [C98] and [B25]. The builder resolves [@key] and
    passes everything else through, so both reached the manuscript as themselves.
    Nobody saw it because the committed CSV was older than the script that writes
    it and still carried the [@key] form -- the build had been reading a file that
    no longer matched its own generator, and the day the generator was rerun the
    paper quietly lost a reference.
    """
    tables_dir = os.path.join(ROOT, "results", "tables")
    if not os.path.isdir(tables_dir):
        pytest.skip("no tables built; run scripts/make_tables.py")

    shorthand = re.compile(r"\[(?!@)[A-Za-z][A-Za-z0-9]*\]")
    found = []
    for name in sorted(os.listdir(tables_dir)):
        if not name.endswith(".csv"):
            continue
        with open(os.path.join(tables_dir, name), encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                for cell in row:
                    for code in shorthand.findall(cell):
                        found.append(f"{name}: {code}")
    assert not found, (
        "these table cells name a source by a code a reader cannot look up:\n  "
        + "\n  ".join(sorted(set(found)))
        + "\nWrite it as [@key] against paper/references.json and rerun "
          "scripts/make_tables.py.")
