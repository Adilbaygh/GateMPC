"""Reading the published data package, and the estimators that run on it.

Why this module exists
----------------------
The diagnostics behind several of the paper's figures were first written as
private build scripts that read the raw API cache. That cache is never
published, so a figure drawn from it could not be checked by anyone: the
repository rule is that every path named in public text must lead to a public
file. This module holds the same estimators, reading the same quantities from
the published package instead, so the figures and the numbers under them stand
on files a reader has.

That move is only honest if it changes nothing. The package and the cache are
supposed to hold the same observations -- ``download_usgs.py --verify`` is what
asserts the package is a faithful, byte-reproducible rendering of them -- so the
public path must reproduce the recorded results exactly, and
``scripts/archive_diagnostics.py`` checks that it does rather than assuming it.

Units. The archive publishes feet and cubic feet per second; everything leaving
this module is SI. The conversion is exact by definition (1 ft = 0.3048 m). The
one exception is the data-quality section at the foot of this file, which also
carries the archive's own foot-based numbers: a statement about what a published
file contains has to quote that file in the units it was published in.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
from dataclasses import dataclass

FT = 0.3048                 # exact, by definition
FT3 = FT ** 3               # exact
G_ACCEL = 9.80665           # m/s2, standard gravity
DT = 900.0                  # s, the archive's 15-minute grid

MOVE_THRESHOLD_FT = 0.02    # the same gate-move rule used by H0 and the census


@dataclass(frozen=True)
class Sample:
    """One timestamp at which all four series have a value. SI units."""
    time: str               # ISO 8601, exactly as the archive publishes it
    a: float                # gate opening, m
    h1: float               # headwater, m
    h2: float               # tailwater, m
    q: float                # discharge, m3/s

    @property
    def dh(self) -> float:
        return self.h1 - self.h2


def load_fold(package: str, site: str, year: int, with_approval: bool = False):
    """Every timestamp in one site-year where all four series have a value.

    Rows with any blank cell are skipped; a blank means the series has no value
    there, which is not the same as a zero, and the package README says so.

    Negative gate readings are clipped to zero rather than dropped. They are
    instrument zero-drift on a shut gate -- the archive contains a handful --
    and clipping is what the private estimator did, so the public path must do
    the same or the two are not comparable.

    Returns a list of samples. With ``with_approval`` it returns that list and a
    parallel list of booleans, True where ALL FOUR series carry the Approved
    flag at that timestamp -- needed where a site-year is not fully approved and
    a result has to be shown to survive on the approved subset alone. The
    default return shape is unchanged, so existing callers are unaffected.
    """
    path = os.path.join(package, "observations", f"{site}_{year}.csv")
    out, approved = [], []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not all(row[c] for c in
                       ("gate_opening", "headwater", "tailwater", "discharge")):
                continue
            out.append(Sample(row["time_utc"],
                              max(float(row["gate_opening"]), 0.0) * FT,
                              float(row["headwater"]) * FT,
                              float(row["tailwater"]) * FT,
                              float(row["discharge"]) * FT3))
            approved.append(all(row.get(c + "_approval") == "Approved"
                                for c in ("gate_opening", "headwater",
                                          "tailwater", "discharge")))
    return (out, approved) if with_approval else out


def kappa(s: Sample) -> float | None:
    """kappa = Q / (a sqrt(2 g dh)) = Cd * W_eff, in metres.

    Datum-free, which is what makes it usable here: the sill elevation is not
    identifiable from this archive (hypotheses.md, H0c-2). W_eff is a constant,
    so every movement of kappa is a movement of the discharge coefficient -- and
    the absence of movement is the signature that the discharge series is an
    output of this very formula rather than an independent measurement.
    """
    if s.a <= 0 or s.dh <= 0:
        return None
    return s.q / (s.a * math.sqrt(2 * G_ACCEL * s.dh))


# ------------------------------------------------------------------ statistics

def quantile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    i = p * (len(sorted_vals) - 1)
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def median(vals) -> float:
    return quantile(sorted(vals), 0.5)


def ols_slope(y: list[float]):
    """Slope per second and its standard error, x = 0, DT, 2 DT, ..."""
    n = len(y)
    xm = (n - 1) / 2.0 * DT
    ym = sum(y) / n
    sxx = sum((i * DT - xm) ** 2 for i in range(n))
    sxy = sum((i * DT - xm) * (y[i] - ym) for i in range(n))
    if sxx == 0:
        return None, None
    b = sxy / sxx
    a = ym - b * xm
    if n <= 2:
        return b, float("inf")
    resid = sum((y[i] - (a + b * i * DT)) ** 2 for i in range(n))
    return b, math.sqrt((resid / (n - 2)) / sxx)


def mean_se(v: list[float]):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, float("inf")
    var = sum((x - m) ** 2 for x in v) / (n - 1)
    return m, math.sqrt(var / n)


# ------------------------------------------------------------------ structure

def contiguous_runs(samples: list[Sample]) -> list[list[int]]:
    """Index runs whose samples are exactly DT apart, so slopes see a real grid.

    The archive is not uniformly on the grid: discharge at 09522700 is
    timestamped one second early through parts of 2023 and 2024, and the package
    reports what that costs in grid_diagnostics.csv. Splitting here means an
    estimator never fits a line across a gap it cannot see.
    """
    runs, cur = [], [0]
    for i in range(1, len(samples)):
        gap = (dt.datetime.fromisoformat(samples[i].time)
               - dt.datetime.fromisoformat(samples[i - 1].time)).total_seconds()
        if abs(gap - DT) < 1.0:
            cur.append(i)
        else:
            if len(cur) > 1:
                runs.append(cur)
            cur = [i]
    if len(cur) > 1:
        runs.append(cur)
    return runs


def find_events(samples: list[Sample], run: list[int]) -> list[tuple[int, int]]:
    """Gate moves: maximal stretches of consecutive steps above the threshold."""
    thr = MOVE_THRESHOLD_FT * FT
    events, start = [], None
    for j in range(1, len(run)):
        big = abs(samples[run[j]].a - samples[run[j - 1]].a) > thr
        if big and start is None:
            start = j - 1
        elif not big and start is not None:
            events.append((start, j - 1))
            start = None
    if start is not None:
        events.append((start, len(run) - 1))
    return events


def gate_steps(samples: list[Sample]) -> list[float]:
    """Signed gate movements, metres, between consecutive on-grid samples."""
    out = []
    for run in contiguous_runs(samples):
        for j in range(1, len(run)):
            out.append(samples[run[j]].a - samples[run[j - 1]].a)
    return out


def census_move_events(values_by_time: dict[str, float],
                       threshold: float = MOVE_THRESHOLD_FT) -> int:
    """Gate move events over a year's sequence AS PUBLISHED, gaps included.

    This is the coverage indicator behind coverage_census.csv -- "was the gate
    moved enough in this year for it to be a usable fold" -- and it is defined
    over the raw sorted sequence so that a reader can recompute it from that one
    column with no further rule. A pair either side of a long gap can therefore
    count as one move.

    ``gate_steps`` above is the physical one: it splits the record into runs
    exactly one grid step apart, because a difference across a gap is not a
    movement. The two live next to each other so that the difference is visible
    rather than buried in two files that look alike. Values are in the units of
    ``values_by_time``; the census passes feet, and the default threshold is the
    0.02 ft rule used throughout.
    """
    values = [values_by_time[t] for t in sorted(values_by_time)]
    events, running = 0, False
    for x, y in zip(values, values[1:]):
        big = abs(y - x) > threshold
        if big and not running:
            events += 1
        running = big
    return events


# ------------------------------------------------------------------ storage

def storage_estimates(samples: list[Sample], window: int, c5_mult: float,
                      sigma: float, reject: dict) -> list[float]:
    """Local estimates of the pool storage area A_s, one per accepted gate move.

    From the volume balance A_s dH1/dt = Q_in(t - tau) - Q(t) with Q_in
    unobserved: written in a window before the move and a window after it, and
    subtracted so the unobserved inflow cancels,

        A_s = -(Q_after - Q_before) / (s_after - s_before)

    where s is the fitted level slope. The acceptance rules C1..C5, the window
    sizes and the significance factor were fixed in hypotheses.md (H0c-1) before
    any of this ran, and nothing here may be tuned to improve the answer.

    Physically impossible negative estimates are NOT filtered out. They mean the
    constant-inflow assumption failed for that event, and removing them after
    the fact would be exactly the tuning the pre-registration forbids; their
    share is reported as a diagnostic instead.
    """
    qs = sorted(s.q for s in samples)
    q_med = quantile(qs, 0.5)
    q_iqr = quantile(qs, 0.75) - quantile(qs, 0.25)
    q_lo, q_hi = q_med - c5_mult * q_iqr, q_med + c5_mult * q_iqr

    out = []
    for run in contiguous_runs(samples):
        events = find_events(samples, run)
        starts = [e[0] for e in events]
        for i0, i1 in events:
            if i0 - window < 0 or i1 + 1 + window > len(run):
                reject["window_off_grid"] += 1
                continue
            pre = [run[k] for k in range(i0 - window, i0)]
            post = [run[k] for k in range(i1 + 1, i1 + 1 + window)]

            if any(s != i0 and i0 - window <= s <= i1 + window for s in starts):
                reject["C2_neighbour_move"] += 1          # another move nearby
                continue
            if any(samples[k].a <= 0 or samples[k].dh <= 0 for k in pre + post):
                reject["C4_shut_or_no_head"] += 1
                continue
            if any(not (q_lo <= samples[k].q <= q_hi) for k in pre + post):
                reject["C5_Q_outlier"] += 1
                continue

            s_m, se_m = ols_slope([samples[k].h1 for k in pre])
            s_p, se_p = ols_slope([samples[k].h1 for k in post])
            if s_m is None or s_p is None:
                reject["degenerate_slope"] += 1
                continue
            q_m, seq_m = mean_se([samples[k].q for k in pre])
            q_p, seq_p = mean_se([samples[k].q for k in post])

            ds, dq = s_p - s_m, q_p - q_m
            if abs(ds) <= sigma * math.hypot(se_m, se_p):
                reject["C3_slope_change_not_significant"] += 1
                continue
            if abs(dq) <= sigma * math.hypot(seq_m, seq_p):
                reject["dQ_not_significant"] += 1
                continue
            out.append(-dq / ds)
    return out


def empty_rejects() -> dict:
    return {"window_off_grid": 0, "C2_neighbour_move": 0,
            "C4_shut_or_no_head": 0, "C5_Q_outlier": 0,
            "degenerate_slope": 0, "C3_slope_change_not_significant": 0,
            "dQ_not_significant": 0}


# -------------------------------------------------------------- data quality

IMPLAUSIBLE_RATIO = 5.0
"""How far above the field gaugings a telemetered discharge must stand before it
is called a defect rather than an unusually high flow.

The threshold is deliberately loose. A canal can run higher than it happened to
be gauged, and a factor of two would catch ordinary operation; five times the
largest measurement ever made at the structure is not operation. It was fixed
before the census was rebuilt, and it is not to be moved to make a claim come
out one way -- an earlier version of this claim failed its check and was struck
out rather than have the yardstick loosened.
"""


def gauging_maxima(package: str) -> dict[str, tuple[float, int]]:
    """Largest field-measured discharge per site, ft3/s, with the count.

    Field gaugings are made with a current meter at the section; they do not
    come from the gate equation, so they are the one discharge quantity in this
    package that is independent of the telemetry. That independence is what lets
    them bound what the structure actually passes, and it is why the circularity
    that disqualifies the continuous series (hypotheses.md, H1 and H3) does not
    reach them.
    """
    values: dict[str, list[float]] = {}
    with open(os.path.join(package, "gaugings.csv"),
              encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["parameter_code"] == "00060" and row["value"]:
                values.setdefault(row["site"], []).append(float(row["value"]))
    return {site: (max(v), len(v)) for site, v in values.items()}


def implausible_discharge(package: str) -> dict | None:
    """The site-year whose telemetered discharge stands furthest above gaugings.

    Read from ``coverage_census.csv``, which spans the whole archive rather than
    the eight fold years, because a claim about a reading the archive contains is
    about the archive and not about the years this study models. Measured over
    the folds alone the same claim fails; that is how it came to be written down
    twice, once as withdrawn and once as reinstated (decisions.md, 2026-09-06).

    The comparison is made WITHIN a site. Pooling would let one canal's gaugings
    license the other's telemetry, and the two structures do not carry the same
    flow -- the pooled maximum is 1520 ft3/s while the primary structure has
    never been gauged above 1050.

    Returns ``None`` for a package built before the census carried per-series
    ranges, so a caller can say so instead of reporting a missing defect as an
    absent one. Otherwise a dict describing the worst site-year, with
    ``is_defect`` set by ``IMPLAUSIBLE_RATIO``; SI values are given alongside the
    archive's own ft3/s.

    ``next_ft3s`` and ``ratio_to_next`` compare the reading with the highest
    annual maximum of every OTHER year at the same site -- a second yardstick,
    made of the archive's own numbers rather than of field measurements. It is
    reported, not applied: the verdict stays on the gauging test, which was
    written down before the census was rebuilt. A criterion introduced after the
    answer is known is not a criterion, and this claim in particular has already
    failed one check, so it is not to be rescued by a second one.
    """
    gauged = gauging_maxima(package)
    maxima: dict[str, dict[int, float]] = {}
    with open(os.path.join(package, "coverage_census.csv"),
              encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if "discharge_max" not in row:
                return None
            if not row["discharge_max"] or row["site"] not in gauged:
                continue
            maxima.setdefault(row["site"], {})[int(row["year"])] = \
                float(row["discharge_max"])

    worst = None
    for site, by_year in maxima.items():
        g, n = gauged[site]
        for year, q in by_year.items():
            ratio = q / g
            if worst is not None and ratio <= worst["ratio"]:
                continue
            others = [v for y, v in by_year.items() if y != year]
            nxt = max(others) if others else float("nan")
            worst = {"site": site, "year": year,
                     "q_ft3s": q, "q_m3s": q * FT3,
                     "gauged_ft3s": g, "gauged_m3s": g * FT3,
                     "gaugings": n, "ratio": ratio,
                     "next_ft3s": nxt, "ratio_to_next": q / nxt,
                     "years": len(by_year),
                     "is_defect": ratio > IMPLAUSIBLE_RATIO}
    return worst
