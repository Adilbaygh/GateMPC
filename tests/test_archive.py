"""Tests for the public archive reader and the estimators that run on it.

The estimators here were moved out of private build scripts so that the figures
drawn from them rest on published files. The move is only defensible if the
estimator still does what the private one did, so the tests that matter most are
the ones that pin its behaviour on data whose answer is known by construction --
and the one that checks the reader reproduces the package's own published row
counts.
"""
import datetime as dt
import math
import os

import pytest

from gatempc.archive import (
    FT, G_ACCEL, Sample, census_move_events, contiguous_runs, empty_rejects,
    find_events, gate_steps, kappa, load_fold, mean_se, median, ols_slope,
    quantile, storage_estimates,
)

DT = 900.0
PACKAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "DATA", "USGS_canal_gates_v1")


def at(i, a=1.0, h1=3.0, h2=2.0, q=10.0):
    """A sample on the 15-minute grid, index i, SI units."""
    t = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=i * DT)
    return Sample(t.isoformat(), a, h1, h2, q)


# ---------------------------------------------------------------- kappa

def test_kappa_is_the_ratio_it_claims_to_be():
    s = at(0, a=2.0, h1=3.0, h2=2.0, q=50.0)
    assert kappa(s) == pytest.approx(50.0 / (2.0 * math.sqrt(2 * G_ACCEL * 1.0)))


def test_kappa_is_undefined_for_a_shut_gate_or_no_head():
    assert kappa(at(0, a=0.0)) is None
    assert kappa(at(0, h1=2.0, h2=2.0)) is None
    assert kappa(at(0, h1=1.0, h2=2.0)) is None


def test_kappa_is_datum_free():
    """Raising both stages by the same amount must not move kappa.

    This is why kappa is the quantity used: the sill elevation is not
    identifiable from this archive, so any statistic that needed it would be
    unusable.
    """
    a = kappa(at(0, h1=3.0, h2=2.0))
    b = kappa(at(0, h1=8.0, h2=7.0))
    assert a == pytest.approx(b)


# ---------------------------------------------------------------- reader

HEADER = ("time_utc,gate_opening,gate_opening_approval,headwater,"
          "headwater_approval,tailwater,tailwater_approval,discharge,"
          "discharge_approval\n")


def write_package(tmp_path, rows, site="09522700", year=2020):
    obs = tmp_path / "observations"
    obs.mkdir(exist_ok=True)
    (obs / f"{site}_{year}.csv").write_text(HEADER + "".join(rows), encoding="utf-8")
    return str(tmp_path)


def test_reader_skips_blanks_clips_negatives_and_converts_units(tmp_path):
    rows = [
        "2020-01-01T00:00:00+00:00,1.00,Approved,10.00,Approved,6.00,Approved,100,Approved\n",
        "2020-01-01T00:15:00+00:00,,Approved,10.00,Approved,6.00,Approved,100,Approved\n",
        "2020-01-01T00:30:00+00:00,-0.02,Approved,10.00,Approved,6.00,Approved,100,Approved\n",
    ]
    got = load_fold(write_package(tmp_path, rows), "09522700", 2020)
    assert len(got) == 2, "the row with a blank gate reading must not appear"
    assert got[0].a == pytest.approx(1.0 * FT)
    assert got[0].h1 == pytest.approx(10.0 * FT)
    assert got[0].q == pytest.approx(100 * FT ** 3)
    assert got[1].a == 0.0, "a negative gate reading is zero drift, clipped not dropped"


def test_a_blank_is_not_a_zero(tmp_path):
    """If blanks were read as zeros the sample count would be right and every
    number computed from it wrong -- the failure mode worth a test of its own."""
    rows = ["2020-01-01T00:00:00+00:00,,Approved,,Approved,,Approved,,Approved\n"]
    assert load_fold(write_package(tmp_path, rows), "09522700", 2020) == []


# ---------------------------------------------------------------- structure

def test_runs_break_where_the_grid_breaks():
    rows = [at(i) for i in (0, 1, 2, 5, 6, 7, 8)]
    runs = contiguous_runs(rows)
    assert [len(r) for r in runs] == [3, 4]


def test_a_lone_sample_is_not_a_run():
    rows = [at(0), at(4), at(5)]
    assert [len(r) for r in contiguous_runs(rows)] == [2]


def test_ols_slope_recovers_a_known_line_exactly():
    y = [1.0 + 3e-5 * i * DT for i in range(8)]
    b, se = ols_slope(y)
    assert b == pytest.approx(3e-5, rel=1e-12)
    assert se == pytest.approx(0.0, abs=1e-18)


def test_mean_se_of_a_constant_is_certain():
    m, se = mean_se([7.0] * 5)
    assert (m, se) == (7.0, 0.0)


def test_quantile_interpolates_and_median_agrees():
    v = [1.0, 2.0, 3.0, 4.0]
    assert quantile(v, 0.5) == pytest.approx(2.5)
    assert median(v) == pytest.approx(2.5)


def test_find_events_marks_one_move_and_its_extent():
    rows = [at(i, a=(1.0 if i < 15 else 1.5) * FT) for i in range(30)]
    run = contiguous_runs(rows)[0]
    assert find_events(rows, run) == [(14, 15)]


def test_a_movement_below_the_threshold_is_not_an_event():
    rows = [at(i, a=(1.0 if i < 15 else 1.01) * FT) for i in range(30)]
    run = contiguous_runs(rows)[0]
    assert find_events(rows, run) == [], "0.01 ft is the archive's own resolution"


def test_gate_steps_never_span_a_gap():
    rows = [at(0, a=1.0), at(1, a=1.5), at(9, a=9.0)]
    steps = gate_steps(rows)
    assert steps == pytest.approx([0.5]), "the jump across the gap is not a movement"


# ---------------------------------------------------------------- census

def by_time(values):
    """A year-sequence keyed by timestamp, as the census builder assembles it."""
    return {f"2020-01-{1 + i // 96:02d}T{(i % 96) // 4:02d}:"
            f"{15 * (i % 4):02d}:00+00:00": v for i, v in enumerate(values)}


def test_a_run_of_large_steps_is_one_move_not_several():
    assert census_move_events(by_time([1.0, 1.0, 2.0, 3.0, 4.0, 4.0])) == 1


def test_two_separated_moves_are_two():
    assert census_move_events(by_time([1.0, 2.0, 2.0, 2.0, 3.0, 3.0])) == 2


def test_steps_at_the_archives_resolution_are_not_moves():
    """0.01 ft is the recording step; the census threshold is 0.02 ft."""
    assert census_move_events(by_time([1.0, 1.01, 1.02, 1.03])) == 0


def test_the_census_counter_is_order_of_time_not_order_of_insertion():
    forward = by_time([1.0, 1.0, 3.0, 3.0])
    shuffled = dict(reversed(list(forward.items())))
    assert census_move_events(shuffled) == census_move_events(forward) == 1


def test_the_census_counter_and_the_physical_one_disagree_across_a_gap():
    """The whole reason both exist. A jump either side of a gap is not a movement,
    but the census counts the year as published and so does see it."""
    rows = [at(0, a=1.0 * FT), at(1, a=1.0 * FT), at(40, a=3.0 * FT)]
    assert gate_steps(rows) == [0.0]                 # the gap is not stepped over
    assert census_move_events({r.time: r.a / FT for r in rows}) == 1


# ---------------------------------------------------------------- storage

def synthetic_transient(a_s, q_in, q0, q1, n=30, move_at=15):
    """A pool with a KNOWN storage area, one gate move, constant inflow.

    A_s dH1/dt = Q_in - Q, so the level slope changes when the gate does, and
    the estimator must return exactly the A_s that generated the data.
    """
    s0, s1 = (q_in - q0) / a_s, (q_in - q1) / a_s
    rows = []
    for i in range(n):
        if i <= move_at:
            h1 = 3.0 + s0 * i * DT
        else:
            h1 = 3.0 + s0 * move_at * DT + s1 * (i - move_at) * DT
        rows.append(at(i,
                       a=(1.0 if i < move_at else 1.5) * FT,
                       h1=h1, h2=2.0,
                       q=q0 if i < move_at else q1))
    return rows


def test_the_estimator_returns_the_storage_area_that_made_the_data():
    rows = synthetic_transient(a_s=100_000.0, q_in=20.0, q0=18.0, q1=22.0)
    rej = empty_rejects()
    got = storage_estimates(rows, window=8, c5_mult=5.0, sigma=3.0, reject=rej)
    assert len(got) == 1, f"expected one accepted event, rejects = {rej}"
    assert got[0] == pytest.approx(100_000.0, rel=1e-9)


def test_impossible_estimates_are_kept_not_quietly_dropped():
    """A negative A_s means the constant-inflow assumption failed for that event.

    H0c-1 forbids filtering them: their share is the diagnostic. Reversing the
    sign of the discharge change produces one, and it must appear in the output.
    """
    rows = synthetic_transient(a_s=100_000.0, q_in=20.0, q0=22.0, q1=18.0)
    rej = empty_rejects()
    got = storage_estimates(rows, window=8, c5_mult=5.0, sigma=3.0, reject=rej)
    assert len(got) == 1 and got[0] > 0
    # now break the balance so the two windows disagree about the sign
    broken = [Sample(r.time, r.a, 3.0 - (r.h1 - 3.0), r.h2, r.q) for r in rows]
    got2 = storage_estimates(broken, window=8, c5_mult=5.0, sigma=3.0,
                             reject=empty_rejects())
    assert len(got2) == 1 and got2[0] < 0, "a physically impossible estimate is kept"


def test_a_second_move_nearby_disqualifies_the_event():
    rows = synthetic_transient(a_s=100_000.0, q_in=20.0, q0=18.0, q1=22.0)
    rows[20] = Sample(rows[20].time, rows[20].a + 0.5 * FT,
                      rows[20].h1, rows[20].h2, rows[20].q)
    rej = empty_rejects()
    got = storage_estimates(rows, window=8, c5_mult=5.0, sigma=3.0, reject=rej)
    assert got == []
    assert rej["C2_neighbour_move"] >= 1


def test_no_head_in_either_window_disqualifies_the_event():
    """C4 rejects a window where the structure is not passing submerged flow.

    The head is drowned rather than the gate shut, deliberately: shutting the
    gate would itself register as a second gate movement and the event would be
    thrown out by C2 instead, so the test would pass while proving nothing about
    C4.
    """
    rows = synthetic_transient(a_s=100_000.0, q_in=20.0, q0=18.0, q1=22.0)
    rows[7] = Sample(rows[7].time, rows[7].a, rows[7].h2, rows[7].h2, rows[7].q)
    rej = empty_rejects()
    assert storage_estimates(rows, 8, 5.0, 3.0, rej) == []
    assert rej["C4_shut_or_no_head"] == 1


def test_no_slope_change_means_no_estimate():
    """Equal discharges before and after: nothing moved, nothing to estimate.

    Which of the two significance guards fires is deliberately NOT pinned. On an
    exactly degenerate case both the slope change and the discharge change are
    zero to within rounding, and whether the difference of the two fitted slopes
    lands on 0.0 or on 1e-21 depends on the platform's floating point -- this
    test asserted the slope guard, passed on Linux and failed on Windows for
    exactly that reason. What is worth pinning is that no estimate comes out and
    that one guard, not none, accounted for it.
    """
    rows = synthetic_transient(a_s=100_000.0, q_in=20.0, q0=18.0, q1=18.0)
    rej = empty_rejects()
    assert storage_estimates(rows, 8, 5.0, 3.0, rej) == []
    assert (rej["C3_slope_change_not_significant"]
            + rej["dQ_not_significant"]) == 1


# ---------------------------------------------------------------- the package

@pytest.mark.skipif(not os.path.isdir(PACKAGE), reason="data package not built")
def test_the_reader_reproduces_the_packages_own_row_counts():
    """grid_diagnostics.csv publishes how many timestamps carry all four series.

    The reader arrives at that number by a completely different route -- reading
    the observation files and skipping blanks -- so agreement is a real check on
    both, and it is what licenses using the package in place of the raw cache.
    """
    import csv
    with open(os.path.join(PACKAGE, "grid_diagnostics.csv"),
              encoding="utf-8", newline="") as fh:
        published = {(r["site"], int(r["year"])): int(r["rows_with_all_four"])
                     for r in csv.DictReader(fh)}
    checked = 0
    for (site, year), want in sorted(published.items()):
        path = os.path.join(PACKAGE, "observations", f"{site}_{year}.csv")
        if not os.path.exists(path):
            continue
        assert len(load_fold(PACKAGE, site, year)) == want, f"{site} {year}"
        checked += 1
    assert checked > 0, "no observation files found to check"


def test_load_fold_can_report_which_timestamps_are_fully_approved():
    """The approval flags travel with the samples, and only when asked for.

    A site-year that is not fully approved cannot carry a headline number unless
    the number survives on the approved subset alone, so the loader has to be
    able to say which timestamps those are. The default return shape stays a
    plain list, because every existing caller depends on it.
    """
    site, year = "09522700", 2020          # a fold year: fully Approved by rule
    if not os.path.exists(os.path.join(PACKAGE, "observations",
                                       f"{site}_{year}.csv")):
        import pytest
        pytest.skip("data package absent; build it with scripts/download_usgs.py")

    plain = load_fold(PACKAGE, site, year)
    pair = load_fold(PACKAGE, site, year, with_approval=True)
    assert isinstance(plain, list)
    assert isinstance(pair, tuple) and len(pair) == 2

    samples, approved = pair
    assert samples == plain, "asking for approvals must not change the samples"
    assert len(approved) == len(samples)
    assert all(isinstance(a, bool) for a in approved)
    assert all(approved), (
        "a fold year is defined as fully Approved; if this fires, the fold rule "
        "and the approval flags disagree and one of them is wrong")
