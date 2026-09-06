"""H2, stage one: how large is the model error a controller would actually carry?

    python scripts/model_error_envelope.py

Both gate laws are matched to deliver the same discharge at the ASCE Test Case 2
reference point, so that the only thing left between them is the SHAPE of the
law. After matching,

    Q_id / Q_syn = (a / a_ref)**(alpha - 1) * (dh / dh_ref)**(beta - 0.5)

which is the modelling error a controller tuned on the benchmark would carry on
the identified plant. It follows from the fitted exponents alone and depends on
no simulation assumption, which is why it comes before any closed-loop work:
requirements/hypotheses.md fixes 1 per cent of discharge error as the threshold
below which a closed-loop experiment could only measure its own noise.

Capacity matching is not cosmetic. Gamma lumps the discharge coefficient with an
unpublished gate width, so an unmatched comparison would mostly measure "these
gates are a different size", which is not a statement about anyone's model.
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

from gatempc.gatelaw import FT, FT3, G_ACCEL, IDEAL_ALPHA, IDEAL_BETA  # noqa: E402

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")
SITE = "09522700"
FOLDS = list(range(2018, 2026))

# ASCE Test Case 2 reference point, fixed in hypotheses.md before computing.
Q_REF = 11.0          # m3/s, heading check gate, initial condition, [C98] Table 6
DH_REF = 0.2          # m, drop at each gate,                        [C98] Table 1
CD_ASCE = 0.61        # [B25] Table 5
W_ASCE = 7.0          # m, gate width of pools I-III,                [C98] Table 3

# Identified exponents, results/gate_law.json (cross-validated over eight folds).
ALPHA = 1.0005
BETA = 0.5086
ALPHA_CI = (0.9999, 1.0012)
BETA_CI = (0.5068, 0.5104)

THRESHOLD = 0.01      # 1% of discharge; hypotheses.md, H2 stage gate

# ASCE Test 2-1 envelope. Check flows run 3.0 .. 13.5 m3/s across the scenario
# ([C98] Table 6). The head across a gate is nominally the 0.2 m drop and moves
# with the level deviations the controller is fighting; +/- 0.1 m about target
# is a generous band for a scenario whose whole point is to keep levels steady.
ASCE_Q = (3.0, 13.5)
ASCE_DH = (0.10, 0.35)


def gamma_syn() -> float:
    """Benchmark coefficient in the same form as the fitted one: Q = G a dh^0.5."""
    return CD_ASCE * W_ASCE * math.sqrt(2 * G_ACCEL)


def observed_envelope():
    """The (a, dh) box the real structure actually visited, for comparison."""
    a_lo = dh_lo = float("inf")
    a_hi = dh_hi = 0.0
    n = 0
    for year in FOLDS:
        path = os.path.join(PACKAGE, "observations", f"{SITE}_{year}.csv")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if not all(row[c] for c in ("gate_opening", "headwater", "tailwater")):
                    continue
                a = float(row["gate_opening"])
                a = 0.0 if a < 0 else a
                dh = (float(row["headwater"]) - float(row["tailwater"])) * FT
                a *= FT
                if a <= 0 or dh <= 0:
                    continue
                a_lo, a_hi = min(a_lo, a), max(a_hi, a)
                dh_lo, dh_hi = min(dh_lo, dh), max(dh_hi, dh)
                n += 1
    return (a_lo, a_hi), (dh_lo, dh_hi), n


def error_at(a: float, dh: float, a_ref: float, alpha: float, beta: float) -> float:
    """Relative discharge difference between the two matched laws."""
    return ((a / a_ref) ** (alpha - IDEAL_ALPHA)
            * (dh / DH_REF) ** (beta - IDEAL_BETA)) - 1.0


def corners(a_rng, dh_rng, a_ref, alpha, beta):
    """The extremes live at the corners: the map is monotone in both arguments."""
    vals = [error_at(a, dh, a_ref, alpha, beta)
            for a in a_rng for dh in dh_rng]
    return min(vals), max(vals)


def main() -> int:
    g_syn = gamma_syn()
    a_ref = Q_REF / (g_syn * math.sqrt(DH_REF))
    print("CAPACITY MATCHING AT THE ASCE REFERENCE POINT")
    print(f"  Q_ref  = {Q_REF} m3/s          [C98] Table 6, heading gate")
    print(f"  dh_ref = {DH_REF} m             [C98] Table 1, drop at each gate")
    print(f"  Gamma_syn = Cd W sqrt(2g) = {CD_ASCE} * {W_ASCE} * "
          f"{math.sqrt(2 * G_ACCEL):.4f} = {g_syn:.4f}")
    print(f"  -> a_ref = {a_ref:.4f} m   (gate opening that delivers Q_ref)")
    print(f"\n  identified exponents: alpha = {ALPHA}, beta = {BETA}")
    print(f"  ideal exponents     : alpha = {IDEAL_ALPHA}, beta = {IDEAL_BETA}")
    print(f"  after matching, the laws differ ONLY by these exponents")

    a_obs, dh_obs, n_obs = observed_envelope()
    a_asce = (ASCE_Q[0] / (g_syn * math.sqrt(ASCE_DH[1])),
              ASCE_Q[1] / (g_syn * math.sqrt(ASCE_DH[0])))

    envelopes = {
        "asce_test_2_1": {"a": a_asce, "dh": ASCE_DH,
                          "note": "from the Test 2-1 check-flow range"},
        "observed_wellton_mohawk": {"a": a_obs, "dh": dh_obs,
                                    "note": f"{n_obs} samples, 2018-2025"},
    }

    print("\n" + "=" * 74)
    print("MODEL ERROR OVER EACH OPERATING ENVELOPE")
    print("=" * 74)
    summary = {}
    worst = 0.0
    for name, env in envelopes.items():
        lo, hi = corners(env["a"], env["dh"], a_ref, ALPHA, BETA)
        # sensitivity over the joint confidence region: worst of the four corners
        ci_lo, ci_hi = 0.0, 0.0
        for al in ALPHA_CI:
            for be in BETA_CI:
                c_lo, c_hi = corners(env["a"], env["dh"], a_ref, al, be)
                ci_lo, ci_hi = min(ci_lo, c_lo), max(ci_hi, c_hi)
        big = max(abs(lo), abs(hi))
        big_ci = max(abs(ci_lo), abs(ci_hi))
        worst = max(worst, big_ci)
        print(f"\n  {name}   ({env['note']})")
        print(f"    a  range : {env['a'][0]:8.4f} .. {env['a'][1]:8.4f} m")
        print(f"    dh range : {env['dh'][0]:8.4f} .. {env['dh'][1]:8.4f} m")
        print(f"    error    : {100 * lo:+7.3f}% .. {100 * hi:+7.3f}%"
              f"    | largest {100 * big:.3f}%")
        print(f"    with the 95% CI on the exponents: {100 * ci_lo:+7.3f}% .. "
              f"{100 * ci_hi:+7.3f}%  | largest {100 * big_ci:.3f}%")
        summary[name] = {
            "a_range_m": list(env["a"]), "dh_range_m": list(env["dh"]),
            "error_min": lo, "error_max": hi, "error_largest": big,
            "error_min_ci": ci_lo, "error_max_ci": ci_hi,
            "error_largest_ci": big_ci, "note": env["note"],
        }

    print("\n" + "=" * 74)
    print("H2 STAGE GATE")
    print("=" * 74)
    print(f"  largest model error anywhere, including exponent uncertainty:"
          f" {100 * worst:.3f}%")
    print(f"  threshold for running a closed-loop experiment: {100 * THRESHOLD:.0f}%")
    proceed = worst > THRESHOLD
    if proceed:
        print("\n  -> ABOVE the threshold. A closed-loop experiment is warranted;")
        print("     the mismatch is large enough for a controller to feel.")
    else:
        print("\n  -> BELOW the threshold, by a wide margin. A closed-loop")
        print("     experiment is NOT run, and hypotheses.md fixed that rule before")
        print("     this number existed. An input error this small cannot produce a")
        print("     measurable degradation; a simulation claiming otherwise would be")
        print("     reporting its own numerical noise.")
        print("\n     Reported conclusion: for a check structure of this class,")
        print("     tuning a controller on the benchmark's idealised gate law costs")
        print(f"     at most {100 * worst:.2f}% in commanded discharge across the whole")
        print("     operating envelope. That is a measured bound, not an assumption.")

    os.makedirs(os.path.join(RESULTS, "tables"), exist_ok=True)
    with open(os.path.join(RESULTS, "tables", "model_error_envelope.csv"),
              "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["envelope", "a_lo_m", "a_hi_m", "dh_lo_m", "dh_hi_m",
                    "error_min", "error_max", "error_min_ci", "error_max_ci"])
        for name, r in sorted(summary.items()):
            w.writerow([name, f"{r['a_range_m'][0]:.6f}", f"{r['a_range_m'][1]:.6f}",
                        f"{r['dh_range_m'][0]:.6f}", f"{r['dh_range_m'][1]:.6f}",
                        f"{r['error_min']:.8f}", f"{r['error_max']:.8f}",
                        f"{r['error_min_ci']:.8f}", f"{r['error_max_ci']:.8f}"])
    with open(os.path.join(RESULTS, "model_error_envelope.json"),
              "w", encoding="utf-8", newline="\n") as fh:
        json.dump({
            "reference": {"q_ref_m3s": Q_REF, "dh_ref_m": DH_REF,
                          "a_ref_m": a_ref, "gamma_syn": g_syn,
                          "cd_asce": CD_ASCE, "w_asce_m": W_ASCE},
            "exponents": {"alpha": ALPHA, "beta": BETA,
                          "alpha_ci95": list(ALPHA_CI), "beta_ci95": list(BETA_CI)},
            "envelopes": summary,
            "largest_error_including_ci": worst,
            "threshold": THRESHOLD,
            "closed_loop_warranted": bool(proceed),
        }, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote results/model_error_envelope.json and its table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
