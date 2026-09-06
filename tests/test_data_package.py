"""Integrity tests for the published data package.

These make the build its own regression test: if a data layer changes, or stops
agreeing with its own diagnostics, the test suite says so before any number
built on it reaches the manuscript.

They read only files already on disk — no network — so they are safe to run in
CI and on a reviewer's machine.

A checksum failure on bytes the reviewer has not touched means the upstream USGS
archive was revised after retrieval. That is a finding to report, not a reason to
regenerate SHA256SUMS.
"""
import csv
import datetime as dt
import hashlib
import json
import os

import pytest

from gatempc.archive import (
    IMPLAUSIBLE_RATIO,
    gauging_maxima,
    implausible_discharge,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(PACKAGE),
    reason="data package absent; build it with scripts/download_usgs.py",
)

ROLES = ("gate_opening", "headwater", "tailwater", "discharge")
APPROVALS = {"Approved", "Provisional", ""}

PRIMARY_SITE = "09522700"
FOLD_YEARS = range(2018, 2026)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sums():
    sums = {}
    with open(os.path.join(PACKAGE, "SHA256SUMS"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                digest, rel = line.rstrip("\n").split("  ", 1)
                sums[rel] = digest
    return sums


def data_files():
    found = []
    for root, _dirs, files in os.walk(PACKAGE):
        for name in files:
            if name.endswith(".csv"):
                rel = os.path.relpath(os.path.join(root, name), PACKAGE)
                found.append(rel.replace("\\", "/"))
    return sorted(found)


def observation_files():
    return sorted(f for f in data_files() if f.startswith("observations/"))


def load_rows(rel):
    with open(os.path.join(PACKAGE, rel), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- integrity

def test_every_data_file_matches_its_checksum():
    sums = read_sums()
    assert sums, "SHA256SUMS is empty"
    for rel, expected in sorted(sums.items()):
        path = os.path.join(PACKAGE, rel)
        assert os.path.exists(path), f"{rel} is listed in SHA256SUMS but missing"
        assert sha256_file(path) == expected, (
            f"{rel} does not match SHA256SUMS. If you have not edited it, the "
            f"upstream archive was revised after retrieval — report that rather "
            f"than regenerating the checksums."
        )


def test_no_data_file_is_left_out_of_the_checksums():
    """An untracked layer would silently escape the regression test."""
    assert set(data_files()) == set(read_sums())


def test_provenance_is_not_checksummed_and_says_why_it_cannot_be():
    """provenance.json records the retrieval date, so it cannot be byte-stable."""
    assert "provenance.json" not in read_sums()
    prov = json.load(open(os.path.join(PACKAGE, "provenance.json"), encoding="utf-8"))
    assert prov["retrieved_utc"]
    assert prov["layers"], "provenance records no layers"


def test_provenance_records_a_request_url_and_licence_for_every_layer():
    prov = json.load(open(os.path.join(PACKAGE, "provenance.json"), encoding="utf-8"))
    for entry in prov["layers"]:
        assert entry["request_url"].startswith("https://api.waterdata.usgs.gov/")
        assert entry["licence"]
        assert os.path.exists(os.path.join(PACKAGE, entry["layer"]))


# ---------------------------------------------------------------- schema

def test_observation_files_have_the_expected_columns():
    expected = ["time_utc"]
    for role in ROLES:
        expected += [role, role + "_approval"]
    for rel in observation_files():
        with open(os.path.join(PACKAGE, rel), encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        assert header == expected, f"{rel} has unexpected columns"


def test_timestamps_are_utc_and_strictly_increasing():
    for rel in observation_files():
        previous = None
        for row in load_rows(rel):
            t = dt.datetime.fromisoformat(row["time_utc"])
            assert t.utcoffset() == dt.timedelta(0), f"{rel}: {row['time_utc']} not UTC"
            assert previous is None or t > previous, f"{rel}: {row['time_utc']} out of order"
            previous = t


def test_values_parse_and_approvals_are_from_the_known_set():
    for rel in observation_files():
        for row in load_rows(rel):
            for role in ROLES:
                raw = row[role]
                if raw != "":
                    float(raw)                       # raises if the cell is corrupt
                assert row[role + "_approval"] in APPROVALS, (
                    f"{rel}: unexpected approval {row[role + '_approval']!r}")


def test_a_value_and_its_approval_are_present_together():
    """An approval without a value (or the reverse) means the row was mis-assembled."""
    for rel in observation_files():
        for row in load_rows(rel):
            for role in ROLES:
                assert (row[role] == "") == (row[role + "_approval"] == ""), (
                    f"{rel} at {row['time_utc']}: {role} value and approval disagree")


def test_no_row_is_entirely_empty():
    for rel in observation_files():
        for row in load_rows(rel):
            assert any(row[role] for role in ROLES), (
                f"{rel} at {row['time_utc']}: row carries no observation")


# ---------------------------------------------------------------- diagnostics

def test_grid_diagnostics_agree_with_the_observations_they_describe():
    """Recompute the diagnostics from the CSVs and compare, line by line.

    This is the test that would catch a silent change in how simultaneity is
    counted — the number the cross-validation folds are built on.
    """
    diag = {(r["site"], r["year"]): r
            for r in load_rows("grid_diagnostics.csv")}
    assert diag, "grid_diagnostics.csv is empty"

    for rel in observation_files():
        site, year = os.path.basename(rel)[:-4].split("_")
        assert (site, year) in diag, f"{rel} has no diagnostics row"
        rows = load_rows(rel)
        on_grid, off_grid, full = 0, 0, 0
        for row in rows:
            t = dt.datetime.fromisoformat(row["time_utc"])
            if t.minute % 15 == 0 and t.second == 0 and t.microsecond == 0:
                on_grid += 1
                if all(row[role] != "" for role in ROLES):
                    full += 1
            else:
                off_grid += 1
        d = diag[(site, year)]
        assert int(d["rows"]) == len(rows), f"{rel}: row count"
        assert int(d["on_grid_timestamps"]) == on_grid, f"{rel}: on-grid count"
        assert int(d["off_grid_timestamps"]) == off_grid, f"{rel}: off-grid count"
        assert int(d["rows_with_all_four"]) == full, f"{rel}: four-series count"


def test_snapping_would_only_ever_add_samples():
    """A sanity bound: aligning timestamps cannot destroy simultaneity."""
    for r in load_rows("grid_diagnostics.csv"):
        assert int(r["rows_with_all_four_if_snapped_2s"]) >= int(r["rows_with_all_four"])


# ---------------------------------------------------------------- series roles

def test_headwater_and_tailwater_come_from_metadata_not_from_the_values():
    """The H1/H2 assignment must be a recorded fact, not an inference.

    Guessing "the higher series is the headwater" would be an assumption that
    happens to be true here; the archive states it outright, so the package
    carries the statement.
    """
    meta = load_rows("time_series_metadata.csv")
    stage = [r for r in meta if r["parameter_code"] == "00065"]
    assert stage, "no stage series in the metadata layer"
    labels = {r["sublocation_identifier"] for r in stage}
    assert any("Headwater" in x for x in labels), labels
    assert any("Tailwater" in x for x in labels), labels


# ---------------------------------------------------------------- gaugings

def test_the_gaugings_layer_exists_and_is_checksummed():
    """The central result rests on these, so they must be published, not cached.

    The continuous discharge series is a rating output computed from the gate
    opening and the two stages; only these field measurements are independent of
    the gate law. A result built on a private cache is not reproducible.
    """
    assert "gaugings.csv" in read_sums(), (
        "gaugings.csv is missing from the package or from its checksums")


def test_gaugings_have_the_expected_columns_and_parse():
    rows = load_rows("gaugings.csv")
    assert rows, "gaugings.csv is empty"
    expected = ["site", "time_utc", "parameter_code", "value", "unit_of_measure",
                "measurement_rated", "observing_procedure",
                "observing_procedure_code", "control_condition",
                "approval_status", "measuring_agency", "field_visit_id",
                "qualifier"]
    assert list(rows[0]) == expected
    for row in rows:
        float(row["value"])                       # raises on a corrupt cell
        dt.datetime.fromisoformat(row["time_utc"])
        assert row["parameter_code"] == "00060"
        assert row["measurement_rated"] in {"Good", "Fair", "Poor", ""}


def test_gaugings_are_sorted_and_unique_per_visit():
    rows = load_rows("gaugings.csv")
    keys = [(r["site"], r["time_utc"], r["field_visit_id"]) for r in rows]
    assert keys == sorted(keys), "gaugings.csv is not in its canonical order"
    assert len(set(keys)) == len(keys), "a field visit appears twice"


def test_enough_gaugings_fall_inside_the_cross_validation_window():
    """If this ever drops, the H4 result loses its basis and must be revisited."""
    rows = load_rows("gaugings.csv")
    inside = [r for r in rows
              if 2018 <= dt.datetime.fromisoformat(r["time_utc"]).year <= 2025
              and r["measurement_rated"] in {"Good", "Fair"}]
    assert len(inside) >= 50, (
        f"only {len(inside)} usable gaugings in 2018-2025; H4 was established "
        f"on 77 accepted after the pre-registered selection rules")


# ---------------------------------------------------------------- census

CENSUS = os.path.join(PACKAGE, "coverage_census.csv")
CENSUS_COLUMNS = ["site", "year", "gate_opening", "headwater", "tailwater",
                  "discharge", "timestamps_with_all_four", "gate_move_events",
                  "approved_pct",
                  "gate_opening_min", "gate_opening_max",
                  "headwater_min", "headwater_max",
                  "tailwater_min", "tailwater_max",
                  "discharge_min", "discharge_max"]
CENSUS_SERIES = ("gate_opening", "headwater", "tailwater", "discharge")


def census_rows():
    with open(CENSUS, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_the_census_layer_exists_with_the_expected_columns_and_is_checksummed():
    assert os.path.exists(CENSUS), "coverage_census.csv is a published layer"
    with open(CENSUS, encoding="utf-8", newline="") as fh:
        assert next(csv.reader(fh)) == CENSUS_COLUMNS
    with open(os.path.join(PACKAGE, "SHA256SUMS"), encoding="utf-8") as fh:
        listed = {line.split("  ", 1)[1].strip() for line in fh if line.strip()}
    assert "coverage_census.csv" in listed


def test_census_counts_parse_and_are_sane():
    for r in census_rows():
        for col in CENSUS_COLUMNS[2:8]:
            assert int(r[col]) >= 0, f"{col} negative in {r['site']} {r['year']}"
        assert 0.0 <= float(r["approved_pct"]) <= 100.0
        assert int(r["timestamps_with_all_four"]) <= min(
            int(r[c]) for c in ROLES), "an intersection cannot exceed its parts"


def test_census_and_grid_diagnostics_agree_where_they_overlap():
    """Two layers counting the same thing by different routes.

    grid_diagnostics.csv counts timestamps carrying all four series from the
    written observation rows; the census counts them from the raw records. If
    they ever disagree, one of them is wrong and neither can be trusted.
    """
    got = {(r["site"], r["year"]): r["timestamps_with_all_four"]
           for r in census_rows()}
    checked = 0
    with open(os.path.join(PACKAGE, "grid_diagnostics.csv"),
              encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["site"], r["year"])
            assert key in got, f"{key} is in grid_diagnostics but not the census"
            assert got[key] == r["rows_with_all_four"], key
            checked += 1
    assert checked > 0


def test_the_census_is_why_the_folds_start_in_2018():
    """The layer's whole purpose, asserted rather than asserted-in-prose.

    The gate series advertises a begin date years before stage exists, so the
    metadata alone would justify a far longer study period. Only a measured
    census shows there is no four-series overlap to work with until 2017.
    """
    primary = [r for r in census_rows() if r["site"] == "09522700"]
    assert primary, "the primary structure must appear in the census"
    with_all_four = [int(r["year"]) for r in primary
                     if int(r["timestamps_with_all_four"]) > 0]
    assert with_all_four, "no year has all four series -- the study has no data"
    assert min(with_all_four) >= 2017, (
        "a four-series year before 2017 would mean the fold choice is unjustified")

    early = [r for r in primary if int(r["year"]) < min(with_all_four)]
    assert early, "the census must reach back before the first usable year"
    assert all(int(r["timestamps_with_all_four"]) == 0 for r in early)
    assert any(int(r["gate_opening"]) > 0 for r in early), (
        "the gate series must be present in those early years -- that is exactly "
        "why the metadata looks more promising than the record is")

    with open(os.path.join(PACKAGE, "time_series_metadata.csv"),
              encoding="utf-8", newline="") as fh:
        begins = [r["begin"] for r in csv.DictReader(fh)
                  if r["site"] == "09522700" and r["parameter_code"] == "45592"
                  and r["begin"]]
    assert begins, "the gate series must publish a begin date"
    assert min(begins)[:4] < str(min(with_all_four)), (
        "the advertised begin should predate the first usable year; if it does "
        "not, the finding this layer records has changed and the text must too")


def test_census_ranges_are_present_exactly_where_the_series_is():
    """A range column is filled if and only if that series has records.

    The ranges were added so that a claim about an out-of-range reading can be
    checked against a published file over the whole archive rather than over the
    fold years alone -- one such claim did not survive that check. A blank where
    there are records, or a number where there are none, would make the layer
    useless for exactly that purpose.
    """
    for r in census_rows():
        for series in CENSUS_SERIES:
            n = int(r[series])
            lo, hi = r[series + "_min"], r[series + "_max"]
            where = f"{r['site']} {r['year']} {series}"
            if n == 0:
                assert lo == "" and hi == "", f"{where}: range without records"
            else:
                assert lo and hi, f"{where}: {n} records but no range"
                assert float(lo) <= float(hi), f"{where}: min above max"


def test_the_archive_still_holds_the_discharge_reading_table_3_reports():
    """A regression pin on a claim that was withdrawn and then reinstated.

    The contribution list names a telemetered discharge far above anything ever
    gauged among the archive's data-quality defects. Measured over the fold years
    that claim failed -- the fold maximum is 1.06 times the largest gauging at
    that structure, which is ordinary operation -- and it was struck out. The
    census layer was then extended to carry per-series ranges over the whole
    archive so the claim could be checked from a published file rather than from
    a private build script, and measured there it holds.

    This pins the second result. The checksums already pin the bytes; what this
    adds is the sentence those bytes are carrying. If USGS revises the archive,
    the package is rebuilt and the reading goes away, this fires and names what
    has to be rewritten -- instead of the manuscript quietly keeping a defect the
    data no longer shows.
    """
    found = implausible_discharge(PACKAGE)
    assert found is not None, (
        "coverage_census.csv has no per-series range columns, so this claim "
        "cannot be checked from a published file at all; rebuild the package "
        "with scripts/download_usgs.py")
    assert found["is_defect"], (
        f"the archive's largest telemetered discharge now stands at "
        f"{found['q_ft3s']:g} ft3/s ({found['site']}, {found['year']}), only "
        f"{found['ratio']:.2f} times the largest of {found['gaugings']} field "
        f"gaugings at that structure ({found['gauged_ft3s']:g} ft3/s) -- below "
        f"the {IMPLAUSIBLE_RATIO:g}x threshold. The defect this pins is gone: "
        f"strike the fourth row of Table 3 and the fourth item in the "
        f"contribution list, and record the revision.")


def test_only_one_year_of_the_archive_carries_that_reading():
    """The reading is a single anomalous year, not a high-flow period.

    This is what makes the defect a defect rather than an unusual season. The
    same site's other annual maxima sit in a narrow band; one year stands an
    order of magnitude above it and is published without a qualifier. The
    yardstick is the pre-registered one, applied to every year in turn: if a
    second year ever crosses it, "one anomalous year" is the wrong description
    and the manuscript has to say what the record actually shows.
    """
    found = implausible_discharge(PACKAGE)
    assert found is not None and found["is_defect"]
    gauged, _n = gauging_maxima(PACKAGE)[found["site"]]

    others = [(int(r["year"]), float(r["discharge_max"])) for r in census_rows()
              if r["site"] == found["site"] and r["discharge_max"]
              and int(r["year"]) != found["year"]]
    assert others, "the census must carry more than the one flagged year"
    crossing = [(y, q) for y, q in others if q > IMPLAUSIBLE_RATIO * gauged]
    assert not crossing, (
        f"{len(crossing)} further year(s) at {found['site']} also exceed "
        f"{IMPLAUSIBLE_RATIO:g}x the gauged maximum {gauged:g} ft3/s: "
        f"{crossing}. Table 3 reports a single anomalous year; it now has to "
        f"report a period, and the wording has to change with it")
    assert found["q_ft3s"] > max(q for _y, q in others), (
        "the flagged year is not the highest; implausible_discharge and this "
        "test disagree about which year they are describing")


def test_the_fold_years_alone_would_not_have_shown_that_defect():
    """Why the census layer exists, asserted rather than explained in prose.

    The eight modelled years are a small and well-behaved slice of a fifteen-year
    archive. If the defect were visible in them, the census would be a
    convenience; because it is not, the census is the only published file from
    which the claim can be checked, and removing it would leave a claim in the
    manuscript with nothing public behind it.
    """
    gauged, _n = gauging_maxima(PACKAGE)[PRIMARY_SITE]
    fold_max = 0.0
    for year in FOLD_YEARS:
        path = os.path.join(PACKAGE, "observations",
                            f"{PRIMARY_SITE}_{year}.csv")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row["discharge"]:
                    fold_max = max(fold_max, float(row["discharge"]))
    assert fold_max > 0, "the fold years must carry discharge at all"
    assert fold_max <= IMPLAUSIBLE_RATIO * gauged, (
        f"the fold years now show {fold_max:g} ft3/s against a gauged maximum "
        f"of {gauged:g} -- the defect is inside the modelled period after all, "
        f"and the account of why the census layer was added is wrong")

    found = implausible_discharge(PACKAGE)
    assert found is not None and found["q_ft3s"] > fold_max, (
        "the whole-archive maximum is not above the fold maximum; the census "
        "is then adding nothing and this test is measuring the wrong thing")
