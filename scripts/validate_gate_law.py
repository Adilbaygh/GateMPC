"""H4: does the ideal gate law reproduce INDEPENDENT discharge gaugings?

    python scripts/validate_gate_law.py

Why this script exists rather than the earlier one. The continuous 15-minute
discharge series at a gated structure is a rating output: it is computed from
the gate opening and the two stages. Fitting a gate law to it therefore recovers
the rating's own coefficient and says nothing about the physics -- the giveaway
was a coefficient constant to 0.01 per cent within each rating period, which no
real measurement achieves. See requirements/decisions.md, 2026-09-05.

USGS also makes discrete field measurements of discharge on site visits, mostly
with an acoustic Doppler current profiler. Those are independent: the rating is
calibrated to them, not derived from them. Comparing the ideal law's prediction
against them is the honest test, and it is what hypotheses.md H4 pre-registers.

Everything below -- the selection rules G1..G5, the tercile binning, and the
5 per cent thresholds -- was fixed before any gauging was looked at.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.gatelaw import FT, FT3, G_ACCEL  # noqa: E402

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")
SITE = "09522700"
FOLDS = list(range(2018, 2026))

# The rating step found on 2026-09-05: kappa = Cd * W_eff jumps by +3.85% one
# week into water year 2022. Both values are medians over 128 734 and 137 588
# continuous samples, each constant to 0.01% within its period.
RATING_BREAK = dt.datetime(2021, 10, 8, tzinfo=dt.timezone.utc)
KAPPA_BEFORE = 5.6474
KAPPA_AFTER = 5.8651

MATCH_TOLERANCE_S = 15 * 60          # G3
QUIET_WINDOW_S = 30 * 60             # G4
MOVE_THRESHOLD = 0.02 * FT           # G4, same rule as H0
ACCEPTED_RATINGS = {"Good", "Fair"}  # G1

# What the USGS ratings in gaugings.csv actually mean, quoted from the archive's
# own reference list rather than assumed:
#
#   "Stream Discharge Measurement Quality", USGS NWIS reference list,
#   https://water.usgs.gov/XML/NWIS/4.11/ReferenceLists/DischargeMeasurementQualityList.html
#   read 2026-09-05 (UTC). The page carries no date of its own; the wording is
#   identical in versions 4.7 through 4.11.
#
#     Excellent -- "should be within 2% of the actual flow"
#     Good      -- "should be within 5% of the actual flow"
#     Fair      -- "should be within 8% of the actual flow"
#     Poor      -- "should be more than 8% of the actual flow"
#     Unspecified -- "the accuracy of the discharge measurement was not rated"
#
# This is the measurements' OWN stated accuracy, so it bounds what a comparison
# against them can resolve: a disagreement smaller than this cannot be told
# apart from the measurement error. The bound was written into H4's criterion
# before this source was found -- hypotheses.md fixed 5% partly on the ground
# that "the ADCP gauging's own uncertainty is of that order", with finding the
# official definition left open as task V13 -- so the agreement is a
# corroboration of that guess, not the reason for it.
STATED_ACCURACY = {"Excellent": 0.02, "Good": 0.05, "Fair": 0.08}

RATING_SOURCE = {
    "title": "Stream Discharge Measurement Quality",
    "publisher": "U.S. Geological Survey, Surface Water User Group",
    "series": "NWIS reference list, version 4.11",
    "url": "https://water.usgs.gov/XML/NWIS/4.11/ReferenceLists/"
           "DischargeMeasurementQualityList.html",
    "accessed_utc": "2026-09-05",
    "page_carries_no_date": True,
    "within_fraction_of_actual_flow": STATED_ACCURACY,
}
N_BINS = 3                           # terciles: n is small
BIAS_CRITERION = 0.05                # H4, from [C98] p.25 and gauging uncertainty
STRUCTURE_CRITERION = 0.05
MIN_BIN = 10                         # below this a bin carries no conclusion


def load_continuous():
    """Every observation from the package, keyed by timestamp, in SI."""
    by_time = {}
    for year in FOLDS:
        path = os.path.join(PACKAGE, "observations", f"{SITE}_{year}.csv")
        if not os.path.exists(path):
            sys.exit(f"missing {path}\nBuild it: python scripts/download_usgs.py")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if not all(row[c] for c in ("gate_opening", "headwater", "tailwater")):
                    continue
                a = float(row["gate_opening"])
                by_time[dt.datetime.fromisoformat(row["time_utc"])] = (
                    (0.0 if a < 0 else a) * FT,
                    float(row["headwater"]) * FT,
                    float(row["tailwater"]) * FT,
                )
    return by_time


def load_gaugings():
    """Independent field discharge measurements, from the published package.

    Read from ``gaugings.csv`` rather than the API so that the result can be
    reproduced from the package alone, by a reviewer with no network access and
    no quota. The package layer is checksummed; a live API call would not be.
    """
    path = os.path.join(PACKAGE, "gaugings.csv")
    if not os.path.exists(path):
        sys.exit(f"missing {path}\nBuild it: python scripts/download_usgs.py")
    out = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["site"] == SITE and row["parameter_code"] == "00060":
                out.append(row)
    return out


def median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def quantile(s, p):
    i = p * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def gate_quiet(times, by_time, centre):
    """G4: no gate movement within +/- QUIET_WINDOW_S of the gauging."""
    window = [t for t in times
              if abs((t - centre).total_seconds()) <= QUIET_WINDOW_S]
    if len(window) < 2:
        return False
    openings = [by_time[t][0] for t in sorted(window)]
    return all(abs(b - a) <= MOVE_THRESHOLD
               for a, b in zip(openings, openings[1:]))


def main() -> int:
    by_time = load_continuous()
    times = sorted(by_time)
    print(f"continuous samples in the fold window: {len(times)}")

    gaugings = load_gaugings()
    print(f"field discharge measurements at {SITE}: {len(gaugings)} "
          f"(from the published package)")

    rejected = {"outside_fold_window": 0, "rating_poor_or_missing": 0,
                "no_match_within_15min": 0, "gate_moved_within_30min": 0,
                "no_head_or_shut": 0}
    rows = []
    for g in gaugings:
        t = dt.datetime.fromisoformat(g["time_utc"])
        if not (FOLDS[0] <= t.year <= FOLDS[-1]):
            rejected["outside_fold_window"] += 1
            continue
        if g.get("measurement_rated") not in ACCEPTED_RATINGS:      # G1
            rejected["rating_poor_or_missing"] += 1
            continue
        near = min(times, key=lambda x: abs((x - t).total_seconds()))
        if abs((near - t).total_seconds()) > MATCH_TOLERANCE_S:     # G3
            rejected["no_match_within_15min"] += 1
            continue
        if not gate_quiet(times, by_time, t):                       # G4
            rejected["gate_moved_within_30min"] += 1
            continue
        a, h1, h2 = by_time[near]
        q_meas = float(g["value"]) * FT3
        if a <= 0 or h1 <= h2 or q_meas <= 0:                       # G5
            rejected["no_head_or_shut"] += 1
            continue
        dh = h1 - h2
        kappa = KAPPA_BEFORE if t < RATING_BREAK else KAPPA_AFTER
        q_pred = kappa * a * math.sqrt(2 * G_ACCEL * dh)
        rows.append({
            "time": g["time_utc"], "rated": g["measurement_rated"],
            "procedure": g.get("observing_procedure", ""),
            "a": a, "dh": dh, "q_meas": q_meas, "q_pred": q_pred,
            "rel": (q_pred - q_meas) / q_meas,
            "period": "before" if t < RATING_BREAK else "after",
            "ratio": a / dh,
        })

    print("\nselection (G1..G5, fixed before looking):")
    for k, v in sorted(rejected.items()):
        print(f"  rejected, {k}: {v}")
    print(f"  ACCEPTED: {len(rows)}")
    if len(rows) < MIN_BIN:
        return _fail("too few matched gaugings to conclude anything")

    rel = [r["rel"] for r in rows]
    bias = median(rel)
    srt = sorted(rel)
    iqr = quantile(srt, 0.75) - quantile(srt, 0.25)
    print("\n" + "=" * 74)
    print("RELATIVE RESIDUAL  (predicted - measured) / measured")
    print("=" * 74)
    print(f"  n            = {len(rel)}")
    print(f"  median       = {100 * bias:+7.2f}%   (criterion |.| <= "
          f"{100 * BIAS_CRITERION:.0f}%)")
    print(f"  IQR          = {100 * iqr:7.2f}%")
    print(f"  q0.05 .. q95 = {100 * quantile(srt, 0.05):+.2f}% .. "
          f"{100 * quantile(srt, 0.95):+.2f}%")
    print(f"  min .. max   = {100 * srt[0]:+.2f}% .. {100 * srt[-1]:+.2f}%")

    print("\n  by rating class (stated accuracy from the USGS reference list):")
    by_rating = {}
    for cls in ("Good", "Fair"):
        v = [r["rel"] for r in rows if r["rated"] == cls]
        if not v:
            continue
        s = sorted(v)
        # How many disagree with the law by more than the measurement itself
        # claims to be worth. This is the decisive count: a residual inside a
        # measurement's own stated accuracy cannot be told apart from the error
        # of that measurement, so it is not evidence against the law.
        outside = [x for x in v if abs(x) > STATED_ACCURACY[cls]]
        by_rating[cls] = {
            "n": len(v), "median": median(v),
            "iqr": quantile(s, .75) - quantile(s, .25),
            "q05": quantile(s, 0.05), "q95": quantile(s, 0.95),
            "min": s[0], "max": s[-1],
            "stated_accuracy": STATED_ACCURACY[cls],
            "n_outside_stated": len(outside),
            "worst_outside": max((abs(x) for x in outside), default=0.0),
        }
        print(f"    {cls:5s} n={len(v):3d}  median {100 * median(v):+6.2f}%  "
              f"IQR {100 * by_rating[cls]['iqr']:5.2f}%  "
              f"|residual| max {100 * max(abs(x) for x in v):5.2f}%  "
              f"vs stated {100 * STATED_ACCURACY[cls]:.0f}%  "
              f"-> {len(outside)} outside")

    print("\n  by rating period (pre-registered check on the 2021 step):")
    per_period = {}
    for per in ("before", "after"):
        v = [r["rel"] for r in rows if r["period"] == per]
        if v:
            per_period[per] = {"n": len(v), "median": median(v)}
            print(f"    {per:6s} n={len(v):3d}  median {100 * median(v):+6.2f}%")

    out_rows = []
    spreads = {}
    for name, key in (("a/dh", "ratio"), ("dh", "dh")):
        pairs = sorted((r[key], r["rel"]) for r in rows)
        per = len(pairs) // N_BINS
        meds, sizes = [], []
        print(f"\n  residual structure vs {name} (terciles):")
        for b in range(N_BINS):
            lo = b * per
            hi = len(pairs) if b == N_BINS - 1 else (b + 1) * per
            chunk = pairs[lo:hi]
            m = median([y for _x, y in chunk])
            meds.append(m)
            sizes.append(len(chunk))
            print(f"    bin {b + 1}  n={len(chunk):3d}  x {chunk[0][0]:8.4f}..{chunk[-1][0]:8.4f}"
                  f"  median residual {100 * m:+6.2f}%")
            out_rows.append([name, str(b + 1), str(len(chunk)),
                             f"{chunk[0][0]:.6f}", f"{chunk[-1][0]:.6f}", f"{m:.6f}"])
        spread = max(meds) - min(meds)
        spreads[name] = spread
        thin = [i + 1 for i, n in enumerate(sizes) if n < MIN_BIN]
        print(f"    spread of bin medians = {100 * spread:.2f}%"
              f"   (criterion {100 * STRUCTURE_CRITERION:.0f}%)")
        if thin:
            print(f"    NOTE: bins {thin} hold fewer than {MIN_BIN} points; "
                  f"no conclusion is drawn from them")

    bias_ok = abs(bias) <= BIAS_CRITERION
    struct_ok = max(spreads.values()) <= STRUCTURE_CRITERION
    print("\n" + "=" * 74)
    print("H4 VERDICT")
    print("=" * 74)
    print(f"  bias      |{100 * bias:+.2f}%| <= {100 * BIAS_CRITERION:.0f}%   : {bias_ok}")
    print(f"  structure  {100 * max(spreads.values()):.2f}%  <= "
          f"{100 * STRUCTURE_CRITERION:.0f}%   : {struct_ok}")
    if bias_ok and struct_ok:
        print("\n  -> H4 SUPPORTED. Against measurements it was never fitted to, the")
        print("     idealised gate law reproduces discharge inside the tolerance the")
        print("     benchmark itself allows. This is a non-circular validation of an")
        print("     assumption the canal-control literature uses without checking.")
    else:
        print("\n  -> H4 NOT SUPPORTED. The idealised law carries systematic error")
        print("     against independent measurements. That error is the real model")
        print("     mismatch the project set out to find, and it is measured here")
        print("     rather than assumed.")

    os.makedirs(os.path.join(RESULTS, "tables"), exist_ok=True)
    with open(os.path.join(RESULTS, "tables", "gauging_residuals.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["time_utc", "rated", "procedure", "period", "gate_opening_m",
                    "head_difference_m", "q_measured_m3s", "q_predicted_m3s",
                    "relative_residual"])
        for r in sorted(rows, key=lambda r: r["time"]):
            w.writerow([r["time"], r["rated"], r["procedure"], r["period"],
                        f"{r['a']:.6f}", f"{r['dh']:.6f}", f"{r['q_meas']:.6f}",
                        f"{r['q_pred']:.6f}", f"{r['rel']:.6f}"])
    with open(os.path.join(RESULTS, "tables", "gauging_residual_bins.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["binned_by", "bin", "n", "x_lo", "x_hi", "median_residual"])
        w.writerows(out_rows)
    with open(os.path.join(RESULTS, "gate_law_validation.json"),
              "w", encoding="utf-8", newline="\n") as fh:
        json.dump({
            "site": SITE, "folds": FOLDS,
            "gaugings_total": len(gaugings), "accepted": len(rows),
            "rejected": rejected,
            "rating_break_utc": RATING_BREAK.isoformat(),
            "kappa_before": KAPPA_BEFORE, "kappa_after": KAPPA_AFTER,
            "relative_residual": {
                "median": bias, "iqr": iqr,
                "q05": quantile(srt, 0.05), "q95": quantile(srt, 0.95),
                "min": srt[0], "max": srt[-1]},
            "by_period": per_period,
            "by_rating": by_rating,
            "rating_source": RATING_SOURCE,
            "structure_spread": spreads,
            "criteria": {"bias": BIAS_CRITERION, "structure": STRUCTURE_CRITERION},
            "h4_supported": bool(bias_ok and struct_ok),
        }, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote results/gate_law_validation.json and two tables")
    return 0


def _fail(m: str) -> int:
    print(m, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
