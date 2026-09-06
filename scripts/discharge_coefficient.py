"""H3: how flat is kappa across the operating range -- and why that is a
measure of the archive, not of the structure.

    python scripts/discharge_coefficient.py

READ THIS BEFORE QUOTING ANY NUMBER FROM HERE. This script was written to ask
whether the discharge coefficient is constant. It cannot answer that question,
because kappa is computed from the continuous discharge series and that series
is the rating's own output -- Q is calculated from the gate opening and the two
stages by the same formula kappa inverts. What comes out is how tightly the
rating holds its coefficient, which is the evidence for this study's second
finding, and it is reported as that. The question the script was named for is
answered by H4 instead, against 77 independent field gaugings.

The discharge coefficient of a vertical sluice gate is not a constant, and the
submerged case this study lives in is the one where that matters most. Belaud,
Cassan and Baume (2009), J. Hydraul. Eng. 135(12), 1086-1091, state it in their
abstract: "The contraction coefficient varies with the relative gate opening and
the relative submergence, especially at large gate openings" -- the two ratios
this script bins by -- and their method carries that through "to a discharge
coefficient, Cd". Their introduction adds the part that bears on this structure:
when gate openings are large the head loss is small and the flow largely
submerged, and "such conditions generally lead to large deviations between
models and discharge measurements". Wellton-Mohawk operates there.

Swamee (1992), J. Irrig. Drain. Eng. 118(1), 56-60, opens by stating that it "is an
involved function of geometric and hydraulic parameters... for submerged flow,
in addition to these parameters, it depends on tail-water depth", and his Fig. 2
-- the curves Henry (1950) measured -- carries Cd from 0 to its free-flow limit
of 0.611 as the upstream depth to gate-opening ratio grows, with a separate
curve for each tail-water to opening ratio. That is the whole range of the
coefficient, driven by exactly the ratios binned here.

Those two normalise by the upstream depth ABOVE THE SILL, Q = Cd a b sqrt(2 g
h0), which this archive cannot form: the sill elevation is not identifiable
(H0c-2). Wu and Rajaratnam (2015), J. Irrig. Drain. Eng. 141, article 06015003,
close that gap, because they work in EXACTLY the form used here --

    q = Cd a sqrt(2 g dH),   dH = H1 - H2                        their Eq. (3)

-- and state of it: "The discharge coefficient Cd is a function of a/H1 and is
independent of yt. The variation of Cd with a/H1 is consistent with Rajaratnam
and Subramanya (1967b) and is shown in Fig. 3." They contrast this explicitly
with the Henry/Swamee form, where "H2 disappears under the square root" and the
coefficient then depends on both H1/a and yt/a.

That makes the comparison exact rather than qualitative. In their Eq. (3),
kappa = Q/(a sqrt(2 g dH)) is Cd times the gate width, so kappa constant means
Cd constant -- and the literature says Cd varies with a/H1. Over these eight
years the gate opening moves through three decades, and the upstream depth
cannot follow it (a canal held near target depth has nowhere to go), so a/H1
sweeps its range while kappa does not move by one part in ten thousand.

The ASCE test
cases use a single constant value. A single power law -- which H1 fitted and
found close to ideal -- can only absorb a *monotone* dependence, so a
non-monotone or localised one would survive in the residuals, and a systematic
error is precisely the kind a controller cannot average away.

The quantity examined is datum-free, which matters because the sill elevation
turned out not to be identifiable (hypotheses.md H0c-2):

    kappa = Q / (a * sqrt(2 g dh)) = Cd * W_eff,     dh = H1 - H2

W_eff is a constant, so every movement of kappa is a movement of Cd.

The bins live INSIDE a rating period. The archive contains a documented rating
revision -- kappa steps 3.85 per cent overnight at a water-year boundary, which
is this study's second finding -- and a bin drawn across it would report that
step as a dependence on gate opening. The pooled figure is printed too, with the
inflation measured, so the difference between the two is on the record.

Threshold, fixed before measuring and taken from the source rather than from
these data: the ASCE untuned tests perturb the controller's assumed check-gate
discharges by 10 per cent ([C98] p. 25), so the benchmark itself treats a 10 per
cent discharge error as something a controller must tolerate. H3 calls the
constant-coefficient assumption practically broken if the spread of binned
medians exceeds 5 per cent of the overall median -- half that margin.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.gatelaw import FT, FT3, G_ACCEL, Sample  # noqa: E402

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")
SITE = "09522700"
FOLDS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

N_BINS = 10                 # deciles, fixed before measuring
SPREAD_CRITERION = 0.05     # 5% of the overall median; see the module docstring

# The rating revision, located by the two-stage detector in
# scripts/archive_diagnostics.py and recorded in requirements/decisions.md: the
# coefficient steps 3.85 per cent overnight at a water-year boundary.
#
# WHY THIS SPLIT BELONGS HERE. Binning the whole archive at once mixes the two
# rating periods, and the "spread of bin medians" that comes out is then mostly
# that 3.85 per cent step -- an event with nothing to do with gate opening or
# head. The first version of this script did exactly that and reported 3.6 per
# cent, of which almost all was the step. The question H3 asks is whether the
# coefficient varies ACROSS THE OPERATING RANGE, so the bins have to live inside
# a period. Both numbers are reported below, each labelled with what it measures.
RATING_BREAK = "2021-10-08T00:00:00+00:00"


def load() -> list[Sample]:
    """Same filtering as scripts/identify_gate_law.py, so the two agree."""
    out = []
    for year in FOLDS:
        path = os.path.join(PACKAGE, "observations", f"{SITE}_{year}.csv")
        if not os.path.exists(path):
            sys.exit(f"missing {path}\nBuild it: python scripts/download_usgs.py")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if not all(row[c] for c in ("gate_opening", "headwater",
                                            "tailwater", "discharge")):
                    continue
                a = float(row["gate_opening"])
                a = 0.0 if a < 0 else a
                h1, h2, q = (float(row["headwater"]), float(row["tailwater"]),
                             float(row["discharge"]))
                if a <= 0 or h1 <= h2 or q <= 0:
                    continue
                out.append(Sample(row["time_utc"], a * FT, h1 * FT, h2 * FT,
                                  q * FT3, year))
    return out


def median(v: list[float]) -> float:
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def quantile(s: list[float], p: float) -> float:
    i = p * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def binned(pairs: list[tuple[float, float]], n_bins: int):
    """Equal-count bins of the first coordinate; median of the second in each."""
    pairs = sorted(pairs)
    per = len(pairs) // n_bins
    rows = []
    for b in range(n_bins):
        lo = b * per
        hi = len(pairs) if b == n_bins - 1 else (b + 1) * per
        chunk = pairs[lo:hi]
        xs = [x for x, _y in chunk]
        ys = sorted(y for _x, y in chunk)
        rows.append({
            "bin": b + 1, "n": len(chunk),
            "x_lo": xs[0], "x_hi": xs[-1], "x_median": median(xs),
            "kappa_median": median(ys),
            "kappa_q25": quantile(ys, 0.25), "kappa_q75": quantile(ys, 0.75),
        })
    return rows


def report(name: str, rows, overall: float, out_rows: list[list[str]],
           period: str = "all"):
    meds = [r["kappa_median"] for r in rows]
    spread = (max(meds) - min(meds)) / overall
    print("\n" + "=" * 74)
    print(f"kappa = Cd * W_eff  BINNED BY {name}   [{period}]")
    print("=" * 74)
    print("%4s %8s %11s %11s %11s %10s %9s"
          % ("bin", "n", "x_lo", "x_hi", "kappa_med", "vs overall", "IQR/med"))
    for r in rows:
        print("%4d %8d %11.4f %11.4f %11.4f %9.2f%% %8.2f%%"
              % (r["bin"], r["n"], r["x_lo"], r["x_hi"], r["kappa_median"],
                 100 * (r["kappa_median"] / overall - 1),
                 100 * (r["kappa_q75"] - r["kappa_q25"]) / r["kappa_median"]))
        out_rows.append([period, name, str(r["bin"]), str(r["n"]),
                         f"{r['x_lo']:.6f}", f"{r['x_hi']:.6f}",
                         f"{r['x_median']:.6f}", f"{r['kappa_median']:.6f}",
                         f"{r['kappa_q25']:.6f}", f"{r['kappa_q75']:.6f}"])
    print(f"\n  spread of bin medians = {100 * spread:.2f}% of the overall median"
          f"   (criterion {100 * SPREAD_CRITERION:.0f}%)")
    return spread


def main() -> int:
    samples = load()
    print(f"usable samples: {len(samples)}")
    root2g = math.sqrt(2 * G_ACCEL)

    kappa, by_ratio, by_head = [], [], []
    for s in samples:
        dh = s.h1 - s.h2                 # fully submerged: datum-free (H0c-2)
        k = s.q / (s.a * root2g * math.sqrt(dh))
        kappa.append(k)
        by_ratio.append((s.a / dh, k))
        by_head.append((dh, k))

    overall = median(kappa)
    ks = sorted(kappa)
    print(f"\noverall kappa median = {overall:.4f} m")
    print(f"  q0.05 .. q0.95      = {quantile(ks, 0.05):.4f} .. {quantile(ks, 0.95):.4f}")
    print(f"  implied Cd*W        = {overall:.4f} m; at Cd = 0.61, "
          f"W_eff = {overall / 0.61:.2f} m")

    out_rows: list[list[str]] = []
    pooled_ratio = report("a/dh (relative opening)", binned(by_ratio, N_BINS),
                          overall, out_rows, "pooled")
    pooled_head = report("dh (head difference, m)", binned(by_head, N_BINS),
                         overall, out_rows, "pooled")
    print("\n  Those two numbers are not the ones H3 asks for. The archive holds")
    print("  two rating periods, so a bin drawn across both mixes them, and the")
    print("  spread that comes out confounds the step between the periods with")
    print("  any real dependence on opening or head. How much of it is the step")
    print("  is measured below rather than asserted here.")

    periods = {}
    for label, keep in (("before", lambda t: t < RATING_BREAK),
                        ("after", lambda t: t >= RATING_BREAK)):
        sub = [s for s in samples if keep(s.time)]
        if len(sub) < N_BINS * 10:
            sys.exit(f"only {len(sub)} samples in the '{label}' rating period; "
                     f"cannot bin into {N_BINS} deciles. Check RATING_BREAK "
                     f"against the fold window.")
        ks_p, ratio_p, head_p = [], [], []
        for s in sub:
            dh = s.h1 - s.h2
            k = s.q / (s.a * root2g * math.sqrt(dh))
            ks_p.append(k)
            ratio_p.append((s.a / dh, k))
            head_p.append((dh, k))
        med_p = median(ks_p)
        sr = report("a/dh (relative opening)", binned(ratio_p, N_BINS),
                    med_p, out_rows, label)
        sh = report("dh (head difference, m)", binned(head_p, N_BINS),
                    med_p, out_rows, label)
        periods[label] = {"n": len(sub), "kappa_median_m": med_p,
                          "spread_by_relative_opening": sr,
                          "spread_by_head_difference": sh}
        print(f"  [{label}] n = {len(sub)},  kappa median = {med_p:.4f} m")

    s_ratio = max(p["spread_by_relative_opening"] for p in periods.values())
    s_head = max(p["spread_by_head_difference"] for p in periods.values())
    worst = max(s_ratio, s_head)
    print("\n" + "=" * 74)
    print("H3 VERDICT  -- computed WITHIN each rating period")
    print("=" * 74)
    for label, p in periods.items():
        print(f"  {label:<7} n = {p['n']:7d}   by a/dh "
              f"{100 * p['spread_by_relative_opening']:5.2f}%   by dh "
              f"{100 * p['spread_by_head_difference']:5.2f}%")
    print(f"  worst spread within a period : {100 * worst:6.2f}%")
    print(f"  criterion                    : {100 * SPREAD_CRITERION:6.2f}%"
          f"   (half the ASCE untuned margin of 10%)")
    pooled_worst = max(pooled_ratio, pooled_head)
    print(f"  the same statistic pooled across both periods: "
          f"{100 * pooled_worst:6.2f}%")
    if worst <= 0:
        print("  -> the within-period spread is zero to the printed precision")
    elif pooled_worst > worst:
        print(f"  -> pooling inflates it {pooled_worst / worst:.1f}-fold. The "
              f"excess comes from the step\n     between the periods, not from "
              f"opening or head.")
    else:
        print("  -> pooling did NOT inflate it, which it should have if the two "
              "periods\n     differ. Check RATING_BREAK against the data before "
              "using either number.")
    supported = worst > SPREAD_CRITERION
    if supported:
        print("\n  -> H3 SUPPORTED. The discharge coefficient is not constant at a")
        print("     scale the benchmark itself treats as material. A controller")
        print("     tuned on a constant-coefficient gate carries this as systematic,")
        print("     not random, model error.")
    else:
        print("\n  -> H3 NOT SUPPORTED by this statistic -- AND THE STATISTIC IS")
        print("     CIRCULAR, so it must not be reported as evidence about Cd.")
        print("     kappa is computed from the continuous discharge series, and that")
        print("     series is the rating's own output: Q is calculated from the gate")
        print("     opening and the two stages by this very formula. Finding kappa")
        print("     flat across ten deciles of relative opening therefore says the")
        print("     rating used one coefficient, not that the structure has one.")
        print("     The flatness is arithmetic, and its size is the measure of that:")
        print(f"     {100 * worst:.2f}% across the operating range is not a precision")
        print("     any field measurement reaches.")
        print("\n     The non-circular answer to 'is Cd constant' is H4, where the")
        print("     same law is tested against 77 independent gaugings and shows no")
        print("     structure against opening, head or submergence within +-5%.")
        print("     THAT is what the manuscript cites for the claim; this number is")
        print("     cited only as evidence that the discharge series is a rating.")

    os.makedirs(os.path.join(RESULTS, "tables"), exist_ok=True)
    with open(os.path.join(RESULTS, "tables", "discharge_coefficient_bins.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["period", "binned_by", "bin", "n", "x_lo", "x_hi",
                    "x_median", "kappa_median", "kappa_q25", "kappa_q75"])
        w.writerows(out_rows)

    with open(os.path.join(RESULTS, "discharge_coefficient.json"),
              "w", encoding="utf-8", newline="\n") as fh:
        json.dump({
            "site": SITE, "folds": FOLDS, "n_samples": len(samples),
            "n_bins": N_BINS, "criterion": SPREAD_CRITERION,
            "kappa_median_m": overall,
            "kappa_q05_m": quantile(ks, 0.05), "kappa_q95_m": quantile(ks, 0.95),
            "implied_w_eff_m_at_cd_061": overall / 0.61,
            "rating_break_utc": RATING_BREAK,
            "by_period": periods,
            "spread_by_relative_opening": s_ratio,
            "spread_by_head_difference": s_head,
            "pooled_spread_by_relative_opening": pooled_ratio,
            "pooled_spread_by_head_difference": pooled_head,
            "pooled_inflation": (pooled_worst / worst) if worst > 0 else None,
            "pooled_note": ("bins drawn across both rating periods confound the "
                            "step between them with any dependence on opening "
                            "or head; pooled_inflation is how much larger the "
                            "pooled spread is than the within-period one"),
            "h3_supported": bool(supported),
            "circular": True,
            "circularity_note": (
                "kappa is computed from the continuous discharge series, which "
                "is itself a rating output produced from the gate opening and "
                "the two stages by this same formula. The within-period "
                "flatness is therefore evidence that the series is a rating, "
                "NOT a measurement of the structure's discharge coefficient. "
                "The non-circular test of that is H4 "
                "(results/gate_law_validation.json)."),
        }, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote results/discharge_coefficient.json, "
          "results/tables/discharge_coefficient_bins.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
