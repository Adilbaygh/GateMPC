"""Everything the archive figures are drawn from, computed from public files only.

    python scripts/archive_diagnostics.py

Three of this study's findings were first measured by private build scripts that
read the raw API cache. The cache is not published -- it is rebuildable, not
archival -- so a figure drawn from it would rest on a file no reader has. This
script recomputes the same quantities from the published data package, which a
reader does have and can verify against SHA256SUMS.

    1. kappa = Q / (a sqrt(2 g dh)) as a time series.
       The evidence that the continuous discharge series is a rating OUTPUT and
       not an independent measurement: within each rating period kappa is
       constant to a precision no hydraulic measurement achieves, and it steps
       once, at a water-year boundary. The step date is FOUND here, not assumed,
       so the finding is reproduced rather than restated.

    2. A_s, the pool storage area, estimated from gate transients (H0c-1).
       Pre-registered as a test of what an open archive can identify; it failed,
       and the spread of the estimates is the figure that shows why.

    3. The distribution of gate movements, on the archive's own 0.01 ft grid.
       What excitation the record actually contains.

Moving an estimator from private to public code is only honest if it changes
nothing, so this script does not merely recompute: it CHECKS its answers against
the numbers the private runs recorded in requirements/hypotheses.md, and exits
non-zero if any of them has moved. A mismatch would mean the package is not a
faithful rendering of the observations the findings were measured on, which is a
finding in itself and must stop the pipeline rather than be smoothed over.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.archive import (  # noqa: E402
    FT, MOVE_THRESHOLD_FT, empty_rejects, gate_steps, kappa, load_fold,
    median, quantile, storage_estimates,
)

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")

SITE = "09522700"
FOLDS = list(range(2018, 2026))           # hypotheses.md, H0b

# H0c-1 fixed all of these before the estimator existed.
WINDOWS = [4, 8, 12]
W_PRIMARY = 8
C5_PRIMARY = 5.0
SIGMA = 3.0
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20260905
FULL_DAY = int(24 * 3600 / 900)           # 96 samples: a complete day
SHIFT_WINDOW_DAYS = 30                    # a rating change is persistent
LOCALISE_DAYS = 15                        # then placed to the day
EXCURSION_LEVELS = (0.001, 0.005, 0.01, 0.05)

MIN_EVENTS = 500                          # criterion 1
MAX_IQR_RATIO = 0.50                      # criterion 2

# What the private runs recorded. This script's job is to reproduce them from
# public files; see requirements/hypotheses.md H0c-1 and the "ЛОЙИҲА БУРИЛИШИ"
# entry in requirements/decisions.md.
EXPECTED = {
    "storage": {
        "n_accepted": 3055,
        "median_m2": 297189.5254354293,
        "iqr_ratio": 1.231153218289041,
        "negative_fraction": 0.1479541734860884,
        "rejects": {"C2_neighbour_move": 2038,
                    "C3_slope_change_not_significant": 1485,
                    "C4_shut_or_no_head": 68,
                    "C5_Q_outlier": 0,
                    "dQ_not_significant": 144,
                    "degenerate_slope": 0,
                    "window_off_grid": 30},
        "window_medians": {4: 241288.75341474073,
                           8: 297189.5254354293,
                           12: 334123.5342506106},
        "window_counts": {4: 2358, 8: 3055, 12: 3050},
    },
    "kappa": {
        "n_usable": 266322,
        "period_medians": [5.6474, 5.8651],   # m, to the recorded precision
        "step_relative": 0.0385,
        "split_after": "2021-10-07",
        "period_counts": [128734, 137588],
    },
}
TOL = 1e-9          # relative, for values that should be bit-for-bit identical


def boot_ci(vals, seed, n_boot=BOOTSTRAP):
    """Percentile interval for the median. Same draw sequence as the private run."""
    rng = random.Random(seed)
    n = len(vals)
    meds = sorted(median([vals[rng.randrange(n)] for _ in range(n)])
                  for _ in range(n_boot))
    return quantile(meds, 0.025), quantile(meds, 0.975)


def close(a, b, tol=TOL):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1.0)


class Checks:
    """Collects every reproduction check so one failure does not hide the rest."""

    def __init__(self):
        self.rows = []

    def add(self, name, got, want, ok):
        self.rows.append((name, got, want, ok))

    def exact(self, name, got, want):
        self.add(name, got, want, got == want)

    def near(self, name, got, want, tol=TOL):
        self.add(name, got, want, close(got, want, tol))

    @property
    def failed(self):
        return [r for r in self.rows if not r[3]]

    def report(self):
        print("\n" + "=" * 74)
        print("REPRODUCTION CHECKS -- public package against the recorded runs")
        print("=" * 74)
        for name, got, want, ok in self.rows:
            mark = "ok  " if ok else "FAIL"
            print(f"  {mark}  {name:<44} got {got!r:>22}  want {want!r}")
        if self.failed:
            print(f"\n  {len(self.failed)} check(s) FAILED. The published package "
                  f"does not reproduce the recorded\n  findings. Do not draw "
                  f"figures from this run -- find out why first.")
        else:
            print("\n  all checks passed: the public path reproduces the private "
                  "one exactly.")


# ------------------------------------------------------------------ 1. kappa

def kappa_layer(data, checks):
    print("=" * 74)
    print("1. kappa = Q / (a sqrt(2 g dh))  --  is the discharge series a rating?")
    print("=" * 74)

    per_day = defaultdict(list)
    n_usable = 0
    for year in FOLDS:
        for s in data[year]:
            k = kappa(s)
            if k is None:
                continue
            per_day[s.time[:10]].append(k)
            n_usable += 1
    checks.exact("kappa: usable samples", n_usable, EXPECTED["kappa"]["n_usable"])

    days = sorted(per_day)
    daily = {d: median(per_day[d]) for d in days}
    complete = {d for d in days if len(per_day[d]) == FULL_DAY}
    print(f"  {len(days)} days with usable samples, {len(complete)} of them "
          f"complete ({FULL_DAY} samples)")

    # The step is FOUND, not assumed, in two stages -- and the first version of
    # this code used only the second, which was wrong.
    #
    # A rating revision is a PERSISTENT level shift. The largest single-day move
    # in the record is not: it is a spike on a day with one or two usable
    # samples, and a one-day detector picks it every time. So stage one compares
    # the median of the SHIFT_WINDOW_DAYS days before a boundary with the same
    # span after it, which a transient cannot move, and stage two places the
    # boundary precisely by the largest one-day move among complete days near
    # the shift. Robust first, precise second.
    naive = max(((abs(daily[b] / daily[a] - 1.0), a, b)
                 for a, b in zip(days, days[1:])
                 if dt.date.fromisoformat(b) - dt.date.fromisoformat(a)
                 == dt.timedelta(1)), default=(0.0, "", ""))
    print(f"  largest single-day move anywhere : {100 * naive[0]:8.2f}%  "
          f"{naive[1]} -> {naive[2]}  "
          f"(n = {len(per_day.get(naive[1], []))} and "
          f"{len(per_day.get(naive[2], []))} samples -- a spike, not a step)")

    W = SHIFT_WINDOW_DAYS
    shifts = []
    for i in range(W, len(days) - W):
        before = [daily[days[k]] for k in range(i - W + 1, i + 1)
                  if days[k] in complete]
        after = [daily[days[k]] for k in range(i + 1, i + 1 + W)
                 if days[k] in complete]
        if len(before) < W // 2 or len(after) < W // 2:
            continue
        a, b = median(before), median(after)
        shifts.append((abs(b / a - 1.0), i, a, b))
    if not shifts:
        raise RuntimeError("no boundary had enough complete days on both sides")
    shifts.sort(reverse=True)
    shift_mag, shift_i, _, _ = shifts[0]
    elsewhere = max((v for v, i, _, _ in shifts if abs(i - shift_i) > 2 * W),
                    default=0.0)
    print(f"  largest {W}-day level shift        : {100 * shift_mag:8.2f}%  "
          f"near {days[shift_i]}")
    ratio = f"  ({shift_mag / elsewhere:.0f}x smaller)" if elsewhere > 0 else ""
    print(f"  largest shift anywhere else      : {100 * elsewhere:8.2f}%{ratio}")

    near = []
    for k in range(max(1, shift_i - LOCALISE_DAYS),
                   min(len(days), shift_i + LOCALISE_DAYS + 1)):
        a_d, b_d = days[k - 1], days[k]
        if a_d not in complete or b_d not in complete:
            continue
        if dt.date.fromisoformat(b_d) - dt.date.fromisoformat(a_d) != dt.timedelta(1):
            continue
        near.append((abs(daily[b_d] / daily[a_d] - 1.0), a_d, b_d))
    if not near:
        raise RuntimeError("no complete-day pair near the shift to place it on")
    near.sort(reverse=True)
    day_jump, split_after, split_before = near[0]
    print(f"  boundary placed at               : {split_after} -> "
          f"{split_before}   ({100 * day_jump:.2f}% overnight)")
    checks.exact("kappa: rating step found on", split_after,
                 EXPECTED["kappa"]["split_after"])

    # Period statistics use EVERY usable sample, not only complete days: the
    # complete-day filter exists to keep the detector honest, not to prune the
    # record the statistics describe.
    periods = []
    for lo, hi in ((days[0], split_after), (split_before, days[-1])):
        vals = sorted(k for d in days if lo <= d <= hi for k in per_day[d])
        med = quantile(vals, 0.5)
        iqr = quantile(vals, 0.75) - quantile(vals, 0.25)
        dm = [daily[d] for d in sorted(complete) if lo <= d <= hi]
        dev = sorted(abs(v / median(dm) - 1.0) for v in dm) if dm else [float("nan")]
        periods.append({
            "from": lo, "to": hi, "n": len(vals), "median_m": med,
            "iqr_m": iqr, "relative_iqr": iqr / med,
            "q05": quantile(vals, 0.05), "q95": quantile(vals, 0.95),
            "complete_days": len(dm),
            "daily_deviation": {"p50": quantile(dev, 0.5),
                                "p90": quantile(dev, 0.9),
                                "p99": quantile(dev, 0.99),
                                "max": dev[-1]},
            "complete_days_beyond": {str(lvl): sum(1 for x in dev if x > lvl)
                                     for lvl in EXCURSION_LEVELS},
        })
    step = periods[1]["median_m"] / periods[0]["median_m"] - 1.0

    print(f"\n  {'period':<26} {'n':>8} {'median, m':>11} "
          f"{'typical day':>13} {'worst day':>11}")
    for p in periods:
        print(f"  {p['from']} .. {p['to']}  {p['n']:8d} {p['median_m']:11.4f} "
              f"{100 * p['daily_deviation']['p50']:12.4f}% "
              f"{100 * p['daily_deviation']['max']:10.2f}%")
    print(f"\n  step across the boundary: {100 * step:+.2f}%")
    print(f"  On a typical complete day the daily median sits within "
          f"{100 * max(p['daily_deviation']['p50'] for p in periods):.3f}% of its "
          f"period median.\n  A coefficient measured in the field does not do "
          f"that, then move {100 * step:.2f}% overnight\n  at a water-year "
          f"boundary and hold the new value.")
    beyond = [p["complete_days_beyond"]["0.005"] for p in periods]
    print(f"  Not welded, though: {beyond[0]} and {beyond[1]} complete days "
          f"(of {periods[0]['complete_days']} and\n  "
          f"{periods[1]['complete_days']}) depart by more than 0.5%. Those are "
          f"reported, not trimmed.")

    for i, p in enumerate(periods):
        checks.exact(f"kappa: period {i + 1} samples", p["n"],
                     EXPECTED["kappa"]["period_counts"][i])
        checks.near(f"kappa: period {i + 1} median (4 dp)",
                    round(p["median_m"], 4),
                    EXPECTED["kappa"]["period_medians"][i], 1e-12)
    checks.near("kappa: step size (4 dp)", round(step, 4),
                EXPECTED["kappa"]["step_relative"], 1e-12)

    with open(os.path.join(RESULTS, "tables", "kappa_daily.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "n", "complete", "kappa_median_m",
                    "kappa_q25_m", "kappa_q75_m"])
        for d in days:
            v = sorted(per_day[d])
            w.writerow([d, len(v), int(d in complete), f"{quantile(v, 0.5):.6f}",
                        f"{quantile(v, 0.25):.6f}", f"{quantile(v, 0.75):.6f}"])
    return {"n_usable": n_usable, "days": len(days),
            "complete_days": len(complete),
            "split_after": split_after, "split_before": split_before,
            "step_relative": step, "overnight_move": day_jump,
            "window_shift": {"days": W, "magnitude": shift_mag,
                             "largest_elsewhere": elsewhere},
            "largest_single_day_move_anywhere": naive[0],
            "periods": periods}


# ------------------------------------------------------------------ 2. storage

def storage_layer(data, checks):
    print("\n" + "=" * 74)
    print("2. A_s from gate transients  --  H0c-1, pre-registered and failed")
    print("=" * 74)

    by_window = {}
    for w in WINDOWS:
        rej = empty_rejects()
        per_fold = {y: storage_estimates(data[y], w, C5_PRIMARY, SIGMA, rej)
                    for y in FOLDS}
        allv = [v for y in FOLDS for v in per_fold[y]]
        by_window[w] = {"per_fold": per_fold, "all": allv, "reject": rej}
        checks.exact(f"A_s: accepted events, window {w}", len(allv),
                     EXPECTED["storage"]["window_counts"][w])
        checks.near(f"A_s: pooled median, window {w}", median(allv),
                    EXPECTED["storage"]["window_medians"][w])

    primary = by_window[W_PRIMARY]
    allv = primary["all"]
    srt = sorted(allv)
    med = quantile(srt, 0.5)
    iqr = quantile(srt, 0.75) - quantile(srt, 0.25)
    neg = sum(1 for v in allv if v < 0) / len(allv)

    for k, v in sorted(primary["reject"].items()):
        checks.exact(f"A_s: rejects, {k}", v, EXPECTED["storage"]["rejects"][k])
    checks.near("A_s: IQR / median", iqr / med, EXPECTED["storage"]["iqr_ratio"])
    checks.near("A_s: negative fraction", neg,
                EXPECTED["storage"]["negative_fraction"])

    print(f"  accepted events   : {len(allv)}   (criterion 1 needs >= {MIN_EVENTS}"
          f" -- {'pass' if len(allv) >= MIN_EVENTS else 'FAIL'})")
    print(f"  pooled median A_s : {med:,.0f} m2")
    print(f"  IQR / median      : {iqr / med:.3f}   (criterion 2 needs <= "
          f"{MAX_IQR_RATIO} -- {'pass' if iqr / med <= MAX_IQR_RATIO else 'FAIL'})")
    print(f"  physically impossible (negative) estimates: {100 * neg:.1f}%")
    print(f"  window sensitivity: " + "   ".join(
        f"w={w}: {median(by_window[w]['all']):,.0f} m2" for w in WINDOWS))

    print(f"\n  {'fold':>6} {'n':>6} {'median, m2':>14} {'95% CI':>30}")
    per_fold_out = {}
    for y in FOLDS:
        v = primary["per_fold"][y]
        lo, hi = boot_ci(v, BOOTSTRAP_SEED)
        per_fold_out[y] = {"n": len(v), "median": median(v),
                           "ci_lo": lo, "ci_hi": hi}
        print(f"  {y:6d} {len(v):6d} {median(v):14,.0f}"
              f"   [{lo:11,.0f}, {hi:11,.0f}]")

    fold_meds = [per_fold_out[y]["median"] for y in FOLDS]
    print(f"\n  fold medians span {min(fold_meds):,.0f} .. {max(fold_meds):,.0f} m2"
          f"  -- a factor of {max(fold_meds) / min(fold_meds):.2f}")
    print("  A_s is a fixed property of the pool. An estimator that returns a "
          "different\n  value each year, with 15% of its estimates physically "
          "impossible, has not\n  identified it -- and that is the reported result.")

    with open(os.path.join(RESULTS, "tables", "storage_estimates.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["fold", "a_s_m2"])
        for y in FOLDS:
            for v in primary["per_fold"][y]:
                w.writerow([y, f"{v:.6f}"])

    return {"window_primary": W_PRIMARY, "windows": WINDOWS,
            "c5_iqr_multiplier": C5_PRIMARY, "sigma": SIGMA,
            "bootstrap": BOOTSTRAP, "bootstrap_seed": BOOTSTRAP_SEED,
            "n_accepted": len(allv), "median_m2": med, "iqr_m2": iqr,
            "iqr_ratio": iqr / med, "negative_fraction": neg,
            "criterion_1_pass": len(allv) >= MIN_EVENTS,
            "criterion_2_pass": iqr / med <= MAX_IQR_RATIO,
            "identified": False,
            "rejects": primary["reject"],
            "window_medians": {str(w): median(by_window[w]["all"]) for w in WINDOWS},
            "window_counts": {str(w): len(by_window[w]["all"]) for w in WINDOWS},
            "per_fold": {str(y): per_fold_out[y] for y in FOLDS}}


# ------------------------------------------------------------------ 3. moves

def movement_layer(data):
    print("\n" + "=" * 74)
    print("3. Gate movements, on the archive's own 0.01 ft grid")
    print("=" * 74)

    hist = Counter()
    steps = []
    for year in FOLDS:
        for d in gate_steps(data[year]):
            steps.append(d)
            hist[int(round(d / FT * 100))] += 1     # hundredths of a foot, exact
    moving = [abs(d) for d in steps if abs(d) > 1e-12]
    big = [d for d in moving if d > MOVE_THRESHOLD_FT * FT]
    srt = sorted(moving)

    print(f"  consecutive on-grid pairs      : {len(steps):,}")
    print(f"  of which the gate moved at all : {len(moving):,} "
          f"({100 * len(moving) / len(steps):.1f}%)")
    print(f"  moves above the {MOVE_THRESHOLD_FT} ft threshold  : {len(big):,} "
          f"({100 * len(big) / len(steps):.2f}% of steps)")
    print(f"  move size, median / q95 / max  : {quantile(srt, 0.5) / FT:.2f}"
          f" / {quantile(srt, 0.95) / FT:.2f} / {max(srt) / FT:.2f} ft")

    with open(os.path.join(RESULTS, "tables", "gate_step_histogram.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["step_hundredths_ft", "step_m", "count"])
        for k in sorted(hist):
            w.writerow([k, f"{k * FT / 100:.6f}", hist[k]])

    return {"pairs": len(steps), "moved": len(moving), "above_threshold": len(big),
            "threshold_ft": MOVE_THRESHOLD_FT,
            "median_move_ft": quantile(srt, 0.5) / FT,
            "q95_move_ft": quantile(srt, 0.95) / FT,
            "max_move_ft": max(srt) / FT,
            "distinct_step_sizes": len(hist)}


# ---------------------------------------------------------------- extremes

SERIES_COLUMNS = ("gate_opening", "headwater", "tailwater", "discharge")


def extremes_layer():
    """The largest and smallest published value in each series, with its approval.

    The manuscript claims four concrete data-quality defects, and one of them is
    a discharge reading far outside anything the structure can pass, carrying the
    archive's own Approved label. A claim like that must come from a file rather
    than from someone's memory of having seen it, so it is measured here: every
    fold year is scanned in the raw published columns -- not through load_fold(),
    which drops the approval flags and skips rows that are blank elsewhere -- and
    the extreme of each series is reported with the status the archive gives it.
    """
    out = {}
    for column in SERIES_COLUMNS:
        lo = hi = None
        for year in FOLDS:
            path = os.path.join(PACKAGE, "observations", f"{SITE}_{year}.csv")
            with open(path, encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    raw = row[column]
                    if not raw:
                        continue
                    v = float(raw)
                    rec = {"value": v, "raw": raw, "time_utc": row["time_utc"],
                           "approval": row[column + "_approval"]}
                    if lo is None or v < lo["value"]:
                        lo = rec
                    if hi is None or v > hi["value"]:
                        hi = rec
        out[column] = {"min": lo, "max": hi}

    print("\n" + "=" * 74)
    print("Extremes of each published series, with the archive's own approval")
    print("=" * 74)
    print(f"  {'series':<14} {'minimum':>12} {'approval':>12}"
          f" {'maximum':>12} {'approval':>12}")
    for column in SERIES_COLUMNS:
        e = out[column]
        print(f"  {column:<14} {e['min']['raw']:>12} {e['min']['approval']:>12}"
              f" {e['max']['raw']:>12} {e['max']['approval']:>12}")
    print(f"\n  {out['discharge']['max']['raw']} ft3/s at "
          f"{out['discharge']['max']['time_utc']} is marked "
          f"{out['discharge']['max']['approval']!r};")
    print("  a negative gate opening is an instrument zero, also published.")
    return out


# ------------------------------------------------------------------ coverage

def coverage_layer(data, checks):
    """Per-fold counts, cross-checked against the package's own grid diagnostics."""
    published = {}
    with open(os.path.join(PACKAGE, "grid_diagnostics.csv"),
              encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            published[(row["site"], int(row["year"]))] = int(row["rows_with_all_four"])

    out = {}
    print("\n" + "=" * 74)
    print("Coverage of the published folds")
    print("=" * 74)
    print(f"  {'fold':>6} {'all four series':>17} {'usable for kappa':>18}")
    for y in FOLDS:
        n_all = len(data[y])
        n_use = sum(1 for s in data[y] if s.a > 0 and s.dh > 0)
        out[str(y)] = {"rows_with_all_four": n_all, "usable": n_use}
        checks.exact(f"coverage: {y} matches grid_diagnostics.csv", n_all,
                     published[(SITE, y)])
        print(f"  {y:6d} {n_all:17,} {n_use:18,}")
    return out


# ------------------------------------------------------------------ main

def main() -> int:
    os.makedirs(os.path.join(RESULTS, "tables"), exist_ok=True)
    print(f"reading {PACKAGE}\n")
    data = {y: load_fold(PACKAGE, SITE, y) for y in FOLDS}

    checks = Checks()
    cov = coverage_layer(data, checks)
    print()
    kap = kappa_layer(data, checks)
    sto = storage_layer(data, checks)
    mov = movement_layer(data)
    ext = extremes_layer()
    checks.report()

    payload = {
        "package": os.path.basename(PACKAGE),
        "site": SITE,
        "folds": FOLDS,
        "environment": {"python": sys.version.split()[0]},
        "coverage": cov,
        "kappa": kap,
        "storage": sto,
        "gate_movement": mov,
        "extremes": ext,
        "reproduction_checks": [
            {"name": n, "got": g, "want": wv, "ok": ok}
            for n, g, wv, ok in checks.rows
        ],
        "all_checks_passed": not checks.failed,
    }
    with open(os.path.join(RESULTS, "archive_diagnostics.json"),
              "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote results/archive_diagnostics.json and three tables")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
