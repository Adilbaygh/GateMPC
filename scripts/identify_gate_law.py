"""Identify the gate discharge relation at USGS 09522700 and test hypothesis H1.

    python scripts/identify_gate_law.py

Reads the published data package, fits

    Q = G * a**alpha * dh**beta,   dh = (H1 - z0) - max(H2 - z0, a)

and writes results/gate_law.json plus the tables the manuscript cites.

What is tested, and why it is the exponents
-------------------------------------------
``G`` lumps the discharge coefficient with the effective gate width, and the two
gates here have no published width, so a difference in ``G`` between this
structure and the ASCE benchmark could equally mean "different physics" or
"different size". The exponents cannot be confounded that way: no gate width
changes a dimensionless exponent. The ideal submerged-orifice law used in the
benchmark is alpha = 1, beta = 0.5, and requirements/hypotheses.md H1 asks
whether the real structure departs from it.

Everything below follows the pre-registration written before this script existed:
the sill elevation is searched on a grid (not by gradient), the folds are the
eight complete years fixed in H0b, and the acceptance criteria for H0c-2 were
fixed before any fit was run.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import math  # noqa: E402

from gatempc.gatelaw import (  # noqa: E402
    FT, FT3, G_ACCEL, IDEAL_ALPHA, IDEAL_BETA, Sample, best, fit_loglinear,
    head_difference, profile_z0_fast, rmse_linear, usable,
)

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")
SITE = "09522700"
FOLDS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]   # hypotheses.md H0b

# H0c-2, fixed before measuring: z0 counts as identified only if at least this
# share of samples can be in free flow, and the profile has a clear minimum.
FREE_FRACTION_CRITERION = 0.05
GRID_STEP_FT = 0.005


def load_samples() -> list[Sample]:
    """Every four-series observation from the folds, filtered and in SI.

    Filtering follows Model/01_plant_model.md 4.3 and 7.3: a negative gate
    reading is sensor zero drift and is clipped to zero, a shut gate carries no
    information about the law, and a sample without positive head cannot be
    produced by the law at all and is dropped rather than silently zeroed
    (task V3 -- the count is reported).
    """
    out: list[Sample] = []
    dropped = {"gate_shut": 0, "no_head": 0, "clipped_negative_gate": 0,
               "non_positive_discharge": 0}
    for year in FOLDS:
        path = os.path.join(PACKAGE, "observations", f"{SITE}_{year}.csv")
        if not os.path.exists(path):
            sys.exit(f"missing {path}\nBuild the package: python scripts/download_usgs.py")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if not all(row[c] for c in
                           ("gate_opening", "headwater", "tailwater", "discharge")):
                    continue
                a = float(row["gate_opening"])
                if a < 0:
                    dropped["clipped_negative_gate"] += 1
                    a = 0.0
                if a <= 0:
                    dropped["gate_shut"] += 1
                    continue
                h1, h2 = float(row["headwater"]), float(row["tailwater"])
                if h1 <= h2:
                    dropped["no_head"] += 1
                    continue
                q = float(row["discharge"])
                if q <= 0:
                    dropped["non_positive_discharge"] += 1
                    continue
                out.append(Sample(row["time_utc"], a * FT, h1 * FT, h2 * FT,
                                  q * FT3, year))
    return out, dropped


def z0_grid(samples: list[Sample]) -> list[float]:
    """Sill elevations worth trying, in metres on the gauge datum.

    Upper bound: the sill must lie below the lowest tailwater, or the tailwater
    depth is negative. Lower bound: half a foot below the lowest switch point
    ``min(H2 - a)``, which is where the last sample stops being able to run free
    and the profile goes flat.
    """
    top = min(s.h2 for s in samples)
    bottom = min(s.h2 - s.a for s in samples) - 0.5 * FT
    step = GRID_STEP_FT * FT
    n = int((top - bottom) / step)
    return [bottom + i * step for i in range(n + 1)]


def ci95(values: list[float]) -> tuple[float, float]:
    """Fold-to-fold interval: mean +/- t * SE with 7 degrees of freedom."""
    if len(values) < 2:
        return (float("nan"), float("nan"))
    m = statistics.fmean(values)
    se = statistics.stdev(values) / (len(values) ** 0.5)
    t = 2.365 if len(values) == 8 else 2.776           # two-sided 95%, df = n-1
    return (m - t * se, m + t * se)


def main() -> int:
    samples, dropped = load_samples()
    print(f"usable samples: {len(samples)}")
    for k, v in sorted(dropped.items()):
        print(f"  dropped, {k}: {v}")
    if len(samples) < 1000:
        return _fail("too few usable samples to identify anything")

    grid = z0_grid(samples)
    print(f"\nsill grid: {len(grid)} points, "
          f"{grid[0] / FT:.3f} .. {grid[-1] / FT:.3f} ft")

    fits = profile_z0_fast(samples, grid)
    if not fits:
        return _fail("the profile is empty; no sill elevation admits a fit")
    top = best(fits)

    print("\n" + "=" * 74)
    print("FULL-DATA FIT (all eight folds)")
    print("=" * 74)
    print(f"  z0            = {top.z0 / FT:9.3f} ft   ({top.z0:7.4f} m)")
    print(f"  alpha         = {top.alpha:9.4f}   (ideal {IDEAL_ALPHA})")
    print(f"  beta          = {top.beta:9.4f}   (ideal {IDEAL_BETA})")
    print(f"  Gamma         = {top.gamma:9.4f} m")
    print(f"  n             = {top.n}")
    print(f"  free fraction = {top.free_fraction:9.4f}")
    rmse, n_pred = rmse_linear(top, samples)
    print(f"  RMSE          = {rmse:9.4f} m3/s on {n_pred} samples")

    ideal = fit_loglinear(samples, top.z0, IDEAL_ALPHA, IDEAL_BETA)
    rmse_i = float("nan")
    if ideal is not None:
        rmse_i, _n = rmse_linear(ideal, samples)
        print("\n  ideal law at the same sill (alpha=1, beta=0.5):")
        print(f"    Gamma       = {ideal.gamma:9.4f} m")
        print(f"    RMSE        = {rmse_i:9.4f} m3/s   "
              f"({100 * (rmse_i / rmse - 1):+.1f}% vs the fitted exponents)")

    # Gamma cannot be compared with the benchmark, because it lumps the
    # discharge coefficient with an unpublished width. Inverting it under the
    # benchmark's own coefficient turns that into something checkable on site.
    implied_w = top.gamma / (0.61 * math.sqrt(2 * G_ACCEL))
    print(f"\n  Gamma = {top.gamma:.4f} m cannot be compared with the ASCE value")
    print(f"  ({0.61 * 7 * math.sqrt(2 * G_ACCEL):.3f} for a 7 m gate) because the")
    print(f"  width here is unpublished. Inverted at the benchmark's Cd = 0.61 it")
    print(f"  implies a combined effective width of {implied_w:.2f} m, about "
          f"{implied_w / 2:.2f} m per gate.")

    # ------------------------------------------------ H0c-2, second condition
    #
    # "Is the minimum interior to the grid?" was the obvious check and it is a
    # trap: where every sample is submerged the objective is flat in z0 to
    # machine precision, argmin picks an arbitrary point in that valley, and the
    # point is interior. The first run reported an interior minimum at 2.11 ft
    # with a free fraction of exactly zero -- a contradiction, since z0 is only
    # observable through free flow. What matters is the WIDTH of the flat valley.
    per_sample = [f.sse / f.n for f in fits]
    lo, hi = min(per_sample), max(per_sample)
    # 0.1% of the minimum: a band no experiment could tell apart, rather than a
    # float-noise threshold that reports a single point and looks decisive.
    tol = lo * 1.001
    flat = [f.z0 / FT for f, v in zip(fits, per_sample) if v <= tol]
    flat_width = max(flat) - min(flat) if flat else 0.0
    admissible = (grid[-1] - grid[0]) / FT
    print("\n" + "=" * 74)
    print("H0c-2 SECOND CONDITION: is the sill actually pinned down?")
    print("=" * 74)
    print(f"  profile spread (mean sq. error) : {lo:.8f} .. {hi:.8f}")
    print(f"  indistinguishable band (+0.1%%)  : {min(flat):.3f} .. {max(flat):.3f} ft"
          f"  = {flat_width:.3f} ft of {admissible:.3f} ft searched")
    print(f"  free fraction at the optimum    : {top.free_fraction:.4f} "
          f"(criterion {FREE_FRACTION_CRITERION})")
    z0_ok = (top.free_fraction >= FREE_FRACTION_CRITERION
             and flat_width < 0.10 * admissible)
    print(f"  -> z0 {'IS' if z0_ok else 'is NOT'} reported as identified")
    if not z0_ok:
        print("     Per the pre-registered fallback the law collapses to its")
        print("     one-parameter form Q = G * a * sqrt(2 g (H1 - H2)), which needs")
        print("     no sill datum. The exponents are unaffected: inside the flat")
        print("     valley dh = H1 - H2 for every sample, so alpha, beta and Gamma")
        print("     take the same value at every z0 in it.")

    # ------------------------------------------------ cross-validation
    print("\n" + "=" * 74)
    print("EIGHT-FOLD CROSS-VALIDATION (fit on seven years, test on the eighth)")
    print("=" * 74)
    print("%6s %8s %9s %9s %9s %10s %10s"
          % ("fold", "n_train", "z0_ft", "alpha", "beta", "Gamma", "RMSE_test"))
    rows, alphas, betas, gammas, z0s = [], [], [], [], []
    for year in FOLDS:
        train = [s for s in samples if s.year != year]
        test = [s for s in samples if s.year == year]
        f = best(profile_z0_fast(train, grid))
        r, nt = rmse_linear(f, test)
        rows.append([str(year), str(len(train)), f"{f.z0 / FT:.4f}",
                     f"{f.alpha:.6f}", f"{f.beta:.6f}", f"{f.gamma:.6f}",
                     f"{r:.6f}", str(nt), f"{f.free_fraction:.6f}"])
        alphas.append(f.alpha)
        betas.append(f.beta)
        gammas.append(f.gamma)
        z0s.append(f.z0 / FT)
        print("%6d %8d %9.4f %9.4f %9.4f %10.4f %10.4f"
              % (year, len(train), f.z0 / FT, f.alpha, f.beta, f.gamma, r))

    a_lo, a_hi = ci95(alphas)
    b_lo, b_hi = ci95(betas)
    print("\n  alpha  mean %.4f   95%% CI [%.4f, %.4f]" % (statistics.fmean(alphas), a_lo, a_hi))
    print("  beta   mean %.4f   95%% CI [%.4f, %.4f]" % (statistics.fmean(betas), b_lo, b_hi))
    print("  Gamma  mean %.4f   95%% CI [%.4f, %.4f]" % (statistics.fmean(gammas), *ci95(gammas)))
    print("  z0     mean %.4f   95%% CI [%.4f, %.4f]  ft" % (statistics.fmean(z0s), *ci95(z0s)))

    # ------------------------------------------------ H1
    alpha_differs = not (a_lo <= IDEAL_ALPHA <= a_hi)
    beta_differs = not (b_lo <= IDEAL_BETA <= b_hi)
    print("\n" + "=" * 74)
    print("H1 VERDICT")
    print("=" * 74)
    print(f"  alpha CI excludes {IDEAL_ALPHA}   : {alpha_differs}")
    print(f"  beta  CI excludes {IDEAL_BETA} : {beta_differs}")
    gain = 100.0 * (1.0 - rmse / rmse_i) if rmse_i == rmse_i else float("nan")
    print(f"\n  EFFECT SIZE, beside the significance test:")
    print(f"    fitted exponents beat the ideal law by {gain:.2f}% of RMSE")
    print(f"    ({rmse:.4f} vs {rmse_i:.4f} m3/s over {top.n} samples)")
    if alpha_differs or beta_differs:
        print("\n  -> The pre-registered criterion is MET (a confidence interval")
        print("     excludes its ideal value), so H1 is recorded as supported.")
        print("     READ THE EFFECT SIZE BEFORE THE VERDICT. With n in the hundreds")
        print("     of thousands a confidence interval this narrow will exclude the")
        print("     ideal value for any systematic departure however small, so the")
        print("     criterion alone does not establish that the departure matters.")
    else:
        print("\n  -> H1 NOT SUPPORTED. Both exponents are consistent with the ideal")
        print("     law. Per the pre-registration this is a publishable result in its")
        print("     own right: the idealised gate law used in the benchmarks is")
        print("     adequate in form for this real structure.")

    os.makedirs(os.path.join(RESULTS, "tables"), exist_ok=True)
    with open(os.path.join(RESULTS, "tables", "gate_law_folds.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["fold", "n_train", "z0_ft", "alpha", "beta", "gamma_m",
                    "rmse_test_m3s", "n_test", "free_fraction"])
        w.writerows(rows)

    with open(os.path.join(RESULTS, "tables", "gate_law_profile.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["z0_ft", "n", "mean_squared_error_log", "alpha", "beta",
                    "gamma_m", "free_fraction"])
        for f in fits:
            w.writerow([f"{f.z0 / FT:.5f}", f.n, f"{f.sse / f.n:.10f}",
                        f"{f.alpha:.6f}", f"{f.beta:.6f}", f"{f.gamma:.6f}",
                        f"{f.free_fraction:.6f}"])

    summary = {
        "site": SITE, "folds": FOLDS,
        "n_usable_samples": len(samples), "dropped": dropped,
        "grid_step_ft": GRID_STEP_FT, "grid_points": len(grid),
        "full_fit": {"z0_ft": top.z0 / FT, "z0_m": top.z0, "alpha": top.alpha,
                     "beta": top.beta, "gamma_m": top.gamma, "n": top.n,
                     "free_fraction": top.free_fraction, "rmse_m3s": rmse},
        "ideal_law_same_sill": (
            {"gamma_m": ideal.gamma, "rmse_m3s": rmse_linear(ideal, samples)[0]}
            if ideal else None),
        "cross_validation": {
            "alpha_mean": statistics.fmean(alphas), "alpha_ci95": [a_lo, a_hi],
            "beta_mean": statistics.fmean(betas), "beta_ci95": [b_lo, b_hi],
            "gamma_mean_m": statistics.fmean(gammas), "gamma_ci95": list(ci95(gammas)),
            "z0_mean_ft": statistics.fmean(z0s), "z0_ci95_ft": list(ci95(z0s)),
        },
        "h1": {"ideal_alpha": IDEAL_ALPHA, "ideal_beta": IDEAL_BETA,
               "alpha_ci_excludes_ideal": alpha_differs,
               "beta_ci_excludes_ideal": beta_differs,
               "supported": bool(alpha_differs or beta_differs)},
        "h0c2_second_condition": {
            "flat_valley_ft": [min(flat), max(flat)] if flat else None,
            "flat_valley_width_ft": flat_width,
            "admissible_range_ft": admissible,
            "free_fraction_at_optimum": top.free_fraction,
            "criterion": FREE_FRACTION_CRITERION,
            "z0_identified": bool(z0_ok)},
        "effect_size": {"rmse_fitted_exponents_m3s": rmse,
                        "rmse_ideal_law_m3s": rmse_i,
                        "rmse_reduction_percent": gain},
        "implied_effective_width_m_at_cd_061": implied_w,
    }
    with open(os.path.join(RESULTS, "gate_law.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote results/gate_law.json, results/tables/gate_law_folds.csv, "
          "results/tables/gate_law_profile.csv")
    return 0


def _fail(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
