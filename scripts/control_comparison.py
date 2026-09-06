"""H2, stage two: what does a controller lose by carrying the benchmark's law?

    python scripts/control_comparison.py

Stage one measured the modelling error itself -- up to 2.30 per cent of
commanded discharge over the observed operating envelope -- and that cleared the
one per cent gate the protocol had fixed in advance. This script closes the
question the error was raised for: put that error inside a closed loop and see
what it costs.

The design, all of it registered in requirements/hypotheses.md before any of
this was written:

  four combinations   tuning model M in {syn, id} x evaluation plant P in
                      {syn, id}, so that the effect of the model can be told
                      apart from the effect of the plant;
  two controllers     PI and a receding-horizon controller, both tuned by the
                      SAME algorithm over the SAME grid with the SAME number of
                      attempts -- enforced below rather than promised (V11);
  one hundred         paired replicates, seeds 0..99, identical across every
                      combination, so the comparison is within-seed;
  the headline        delta = (IAE(M_syn->P_id) - IAE(M_id->P_id))
                              / IAE(M_id->P_id), median and bootstrap interval:
                      on the real structure, how much worse is the controller
                      that was tuned on the benchmark's idealised gate law.

Three things are reported that the protocol did not require but that a reader
would ask for, and each is marked as what it is:

  * the mirror combination on the synthetic plant, which must show the penalty
    running the other way if the experiment measures a model mismatch at all
    and not simply "the identified law is worse";
  * sensitivity of delta to the joint confidence region of the identified
    exponents (V10), to the pool it is run on, and to the 0.5 per cent
    minimum gate movement of [C98] p. 24 -- which the stage-two protocol did
    not include, so it is a declared sensitivity axis and never the headline;
  * the fraction of each run spent against the gate limits (V9), flagged above
    five per cent.

What this experiment cannot say is stated in the manuscript's limitations and
repeated here: the pool is an integrator with delay, not a Saint-Venant reach,
so the ABSOLUTE indicator values are not realistic canal performance. The pool
is identical in both arms, which is exactly why the RELATIVE difference is the
only number reported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.canal import G, GateLaw, MPC, PI, Pool, simulate  # noqa: E402

RESULTS = os.path.join(ROOT, "results")

# ------------------------------------------------------------------ constants
# Every value below carries its source. Nothing here is a round number chosen
# because it looked reasonable.

CD_ASCE = 0.61          # [B25] Table 5
W_ASCE = 7.0            # m, gate width, pools I-III            [C98] Table 3
GATE_HEIGHT = 2.3       # m, gate height, pool I    Model/02 section 3 table
A_MIN, A_MAX = 0.0, GATE_HEIGHT
MIN_STEP = 0.005 * GATE_HEIGHT          # 11.5 mm               [C98] p. 24

Q_REF = 11.0            # m3/s, heading gate initial flow       [C98] Table 6
DH_REF = 0.2            # m, drop at each gate                  [C98] Table 1

# results/gate_law.json, cross-validated over the eight year-folds 2018-2025.
ALPHA, BETA = 1.0005, 0.5086
ALPHA_CI = (0.9999, 1.0012)
BETA_CI = (0.5068, 0.5104)
GAMMA_FIT = 25.5580     # rescaled away by capacity matching; kept for the record

POOL_LENGTH = 7000.0    # m, pool I             Model/02 section 3, see 8.1
BOTTOM_WIDTH = 7.0      # m
SIDE_SLOPE = 1.5        # horizontal : vertical
TARGET_DEPTH = 2.1      # m
TAILWATER_DEPTH = TARGET_DEPTH - DH_REF   # so the gate sits at the 0.2 m drop

DT = 900.0              # s, regulation step, >= 15 min for canal 2  [C98] p.24

# Randomness: three sources, each with a reason. hypotheses.md, stage-two table.
LEVEL_QUANT = 0.0015    # m = 0.005 ft, the archive's 0.01 ft step (H0)
TIMING_SHIFT = 15 * 60  # s, one regulation step
LEVEL0_SPREAD = 0.02    # m, about 1 per cent of the target depth
N_REPLICATES = 100      # seeds 0..99, paired across every combination
NOISE_STREAM = 1_000_000  # keeps measurement noise independent of the scenario

BOOTSTRAP = 10_000
BOOT_SEED = 20260905
SATURATION_FLAG = 0.05  # V9: above this the scenario exceeds the plant


# ------------------------------------------------------------------ scenarios

class Scenario:
    """A three-level schedule with two breakpoints, as the ASCE tests are."""

    def __init__(self, key, name, inflow, offtake, breaks, duration, source):
        self.key, self.name, self.source = key, name, source
        self.inflow, self.offtake = inflow, offtake
        self.breaks, self.duration = breaks, duration

    def build(self, shifts=(0.0, 0.0)):
        t1 = self.breaks[0] + shifts[0]
        t2 = self.breaks[1] + shifts[1]

        def pick(levels):
            return lambda t: levels[0] if t < t1 else (levels[1] if t < t2
                                                       else levels[2])
        return pick(self.inflow), pick(self.offtake)


S_EVAL = Scenario(
    "S_eval", "ASCE Test 2-1",
    inflow=(11.0, 13.5, 11.5), offtake=(1.0, 1.0, 1.0),
    breaks=(2 * 3600.0, 14 * 3600.0), duration=24 * 3600.0,
    source="[C98] Table 6; transcribed and balance-checked in Model/02 section 5",
)

# The head-flow row of S_tune is the one the protocol fixed. The pool-I offtake
# is reconstructed: [C98] Table 7's initial offtakes are 0.2, 0.3, 0.2, 0.3, 0.2,
# 0.3, 0.2, 0.3 with scheduled changes 1.5, 1.5, 2.5, -, -, 0.5, 1.0, 2.0
# (Model/02 section 8.2, cross-checked against [B25] Table 6), which puts pool I
# at 0.2 -> 1.7. The return to the initial state at 14 h follows the head-flow
# row and has NOT been read off Table 7. This is declared rather than hidden --
# and it cannot bias the result: S_tune only sets the gains, both models are
# tuned on the same S_tune by the same algorithm, and every number reported
# comes from S_eval, which is transcribed in full.
S_TUNE = Scenario(
    "S_tune", "ASCE Test 2-2",
    inflow=(2.7, 13.7, 2.7), offtake=(0.2, 1.7, 0.2),
    breaks=(2 * 3600.0, 14 * 3600.0), duration=24 * 3600.0,
    source="[C98] Table 7; head-flow row pre-registered, pool-I offtake "
           "reconstructed from Model/02 section 8.2 -- see the note in this file",
)

# ------------------------------------------------------------------ tuning grid
# The grid IS the tuning budget, so its edges must not be the thing that chooses
# the gains. The first attempt at this script fixed the bounds by hand and both
# controllers tuned to the largest gain on offer -- which says nothing about the
# controller and everything about where the author stopped the axis. So the grid
# GROWS: an axis whose optimum lands on a movable edge is extended by a decade
# and the search is repeated, both models together, until every optimum is
# interior or a fixed number of expansions is spent. What actually ran is
# written into the output.
#
# An axis end marked ``floor`` is physical and is never extended: no integral
# action at all (K_i = 0) and a one-step prediction horizon are real endpoints,
# not places the author gave up.

MAX_EXPANSIONS = 6


class Axis:
    def __init__(self, values, floor_low=False, floor_high=False):
        self.values = tuple(values)
        self.floor_low, self.floor_high = floor_low, floor_high

    def at_edge(self, v):
        return ((v == self.values[0] and not self.floor_low)
                or (v == self.values[-1] and not self.floor_high))

    def hits(self, v):
        """(low, high): which movable ends this optimum landed on."""
        return (v == self.values[0] and not self.floor_low,
                v == self.values[-1] and not self.floor_high)

    def grown(self, low, high, factor=10.0):
        """A copy extended by one decade past the ends asked for."""
        vals = list(self.values)
        if low and vals[0] > 0:
            vals.insert(0, vals[0] / factor)
        if high:
            top = vals[-1] * factor
            vals.append(int(round(top)) if isinstance(vals[-1], int) else top)
        return Axis(vals, self.floor_low, self.floor_high)


def start_axes(kind):
    if kind == "PI":
        return [Axis((2.0, 5.0, 10.0, 20.0, 35.0, 60.0)),
                Axis((0.0, 2e-4, 6e-4, 2e-3, 6e-3, 2e-2), floor_low=True)]
    return [Axis((1e2, 3e2, 1e3, 3e3, 1e4, 1e5)),                  # q/r
            Axis((1, 2, 4, 8, 16, 24), floor_low=True)]             # horizon


def grid_of(axes):
    return tuple((a, b) for a in axes[0].values for b in axes[1].values)

# The control horizon is 1 by construction: the MPC solves the single-move
# problem in closed form. The registered protocol listed N_c as a tuning
# dimension; the implementation makes it degenerate, and saying so is cheaper
# than pretending a third axis was searched.
CONTROL_HORIZON = 1


def make_controller(kind, params, pool):
    if kind == "PI":
        kp, ki = params
        return PI(kp, ki)
    rho, np_ = params
    return MPC(q_weight=rho, r_weight=1.0, horizon=np_,
               control_horizon=CONTROL_HORIZON,
               area=pool.storage_area, dt=DT)


def fingerprint(candidates):
    """A hash of exactly what the tuner tried, in order.

    V11 asks that both models get the same tuning budget. A count is easy to
    satisfy and easy to satisfy dishonestly; two identical fingerprints say the
    two searches were the same search, over the same points, in the same order.
    """
    payload = json.dumps([list(c) for c in candidates], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ laws, pools

def ideal_law():
    """The benchmark's law, in the same form as the fitted one."""
    return GateLaw(CD_ASCE * W_ASCE * math.sqrt(2 * G), 1.0, 0.5, "asce")


def identified_law(alpha=ALPHA, beta=BETA):
    """The identified law, matched to the benchmark's capacity at the reference.

    Gamma lumps the discharge coefficient with an unpublished gate width, so an
    unmatched pair of laws would mostly differ in gate SIZE. After matching they
    differ only in shape, which is the thing under test.
    """
    ref = ideal_law()
    a_ref = ref.opening_for(Q_REF, DH_REF)
    return GateLaw(GAMMA_FIT, alpha, beta, "identified").matched_to(
        ref, a_ref, DH_REF)


def make_pool(length=POOL_LENGTH):
    return Pool(length=length, bottom_width=BOTTOM_WIDTH, side_slope=SIDE_SLOPE,
                target_depth=TARGET_DEPTH, tailwater_depth=TAILWATER_DEPTH)


# ------------------------------------------------------------------ experiment

def search(kind, law, pool, grid, min_step=0.0):
    """One exhaustive pass over one grid, plant and model both this law.

    An engineer tunes against the model they have; that is what makes the two
    arms different. The run is deterministic -- no noise, no timing shift, no
    initial offset -- so the search is not chasing one realisation of the noise.
    """
    inflow, offtake = S_TUNE.build()
    best = None
    attempted, usable = [], []
    for params in grid:
        attempted.append(params)
        res = simulate(pool, law, law, make_controller(kind, params, pool),
                       inflow, offtake, S_TUNE.duration, DT, pool.target_depth,
                       pool.target_depth, 0.0, random.Random(0),
                       A_MIN, A_MAX, min_step)
        ind = res.indicators(pool.target_depth, DT)
        if not math.isfinite(ind["IAE"]):
            continue
        usable.append(params)
        if best is None or ind["IAE"] < best[1]:
            best = (params, ind["IAE"], ind)
    if best is None:
        raise RuntimeError(f"no {kind} candidate produced a finite IAE")
    return {"params": list(best[0]), "tuning_iae": best[1],
            "candidates_evaluated": len(attempted),
            "candidates_usable": len(usable),
            "attempted_fingerprint": fingerprint(attempted),
            "tuning_saturated_fraction": best[2]["saturated_fraction"]}


def tune_pair(kind, syn, idl, pool, min_step=0.0):
    """Tune both models on the SAME grid, growing it until nothing is on an edge.

    Growing is driven by EITHER model's optimum, and both are then retuned on
    the enlarged grid, so the two searches never diverge -- V11 holds at every
    stage and the fingerprints prove it.
    """
    axes = start_axes(kind)
    history, edges = [], []
    for attempt in range(MAX_EXPANSIONS + 1):
        grid = grid_of(axes)
        best = {"syn": search(kind, syn, pool, grid, min_step),
                "id": search(kind, idl, pool, grid, min_step)}
        if (best["syn"]["attempted_fingerprint"]
                != best["id"]["attempted_fingerprint"]):
            raise RuntimeError("V11 violated: the two models were tuned over "
                               "different candidate sets")
        wanted = [[False, False], [False, False]]     # per axis: (low, high)
        for model in ("syn", "id"):
            for i, ax in enumerate(axes):
                lo, hi = ax.hits(best[model]["params"][i])
                wanted[i][0] |= lo
                wanted[i][1] |= hi
        edges = [f"axis{i}:{'low' if w[0] else ''}{'high' if w[1] else ''}"
                 for i, w in enumerate(wanted) if w[0] or w[1]]
        history.append({"grid_size": len(grid),
                        "axis0": list(axes[0].values),
                        "axis1": list(axes[1].values),
                        "params_syn": best["syn"]["params"],
                        "params_id": best["id"]["params"],
                        "iae_syn": best["syn"]["tuning_iae"],
                        "iae_id": best["id"]["tuning_iae"],
                        "on_edge": edges})
        if not edges or attempt == MAX_EXPANSIONS:
            break
        axes = [ax.grown(w[0], w[1]) for ax, w in zip(axes, wanted)]

    # An optimum still on an edge has two very different explanations, and they
    # must not be reported as one. Either the grid was too small -- a defect --
    # or the objective approaches a limit along that axis and no finite grid
    # will ever contain the optimum. A decade of extra range that buys almost
    # no improvement is the signature of the second: the search is walking
    # towards an asymptote, here the deadbeat controller that pure IAE always
    # wants when nothing charges for gate movement.
    asymptotic = False
    if edges and len(history) > 1:
        prev, last = history[-2]["iae_syn"], history[-1]["iae_syn"]
        asymptotic = prev > 0 and (prev - last) / prev < 1e-4
    return best, {"expansions": len(history) - 1,
                  "final_grid_size": len(grid),
                  "terminated_interior": not edges,
                  "optimum_is_asymptotic": bool(asymptotic),
                  "last_expansion_gain": (
                      None if len(history) < 2 or history[-2]["iae_syn"] <= 0
                      else (history[-2]["iae_syn"] - history[-1]["iae_syn"])
                      / history[-2]["iae_syn"]),
                  "grid_fingerprint": best["syn"]["attempted_fingerprint"],
                  "history": history}


def replicate(seed, pool, plant, model, kind, params, min_step=0.0):
    """One paired draw of S_eval. The seed fixes the scenario AND the noise."""
    rs = random.Random(seed)
    shifts = (rs.uniform(-TIMING_SHIFT, TIMING_SHIFT),
              rs.uniform(-TIMING_SHIFT, TIMING_SHIFT))
    level0 = pool.target_depth + rs.uniform(-LEVEL0_SPREAD, LEVEL0_SPREAD)
    inflow, offtake = S_EVAL.build(shifts)
    res = simulate(pool, plant, model, make_controller(kind, params, pool),
                   inflow, offtake, S_EVAL.duration, DT, pool.target_depth,
                   level0, LEVEL_QUANT, random.Random(NOISE_STREAM + seed),
                   A_MIN, A_MAX, min_step)
    ind = res.indicators(pool.target_depth, DT)
    half = len(res.level) // 2
    ind["IAE_first_half"] = res.window(0, half).indicators(
        pool.target_depth, DT)["IAE"]
    ind["IAE_second_half"] = res.window(half, len(res.level)).indicators(
        pool.target_depth, DT)["IAE"]
    return ind


def arm(pool, plant, model, kind, params, n, min_step=0.0):
    return [replicate(s, pool, plant, model, kind, params, min_step)
            for s in range(n)]


def paired_delta(worse, better):
    """Within-seed relative penalty. Undefined where the reference is zero."""
    out = []
    for a, b in zip(worse, better):
        if b["IAE"] > 0:
            out.append((a["IAE"] - b["IAE"]) / b["IAE"])
    return out


def paired_gap_m(worse, better, target):
    """The same difference in METRES of mean level error.

    A ratio of two small numbers can be large while the thing it describes is
    invisible. IAE is normalised by the target depth, so multiplying it back
    gives the mean level error, and the difference between the two arms can then
    be held against something physical -- the level sensor's own resolution.
    """
    return [(a["IAE"] - b["IAE"]) * target for a, b in zip(worse, better)]


def bootstrap_ci(values, rng, n=BOOTSTRAP, level=0.95):
    if not values:
        return (float("nan"), float("nan"))
    k = len(values)
    meds = sorted(statistics.median(rng.choices(values, k=k)) for _ in range(n))
    lo = meds[max(0, int((1 - level) / 2 * n))]
    hi = meds[min(n - 1, int((1 + level) / 2 * n) - 1)]
    return lo, hi


COMBOS = (("syn", "syn"), ("syn", "id"), ("id", "syn"), ("id", "id"))


def label(model, plant):
    return f"M_{model}->P_{plant}"


def run_block(pool, syn, idl, kind, n, min_step=0.0):
    """The four combinations for one controller, one pool, one actuator setting."""
    tuned, grid_log = tune_pair(kind, syn, idl, pool, min_step)
    laws = {"syn": syn, "id": idl}
    arms = {label(m, p): arm(pool, laws[p], laws[m], kind,
                             tuned[m]["params"], n, min_step)
            for m, p in COMBOS}
    return tuned, grid_log, arms


# ------------------------------------------------------------------ reporting

def summarise(runs):
    keys = ("MAE", "IAE", "StE", "IAQ", "IAW", "saturated_fraction",
            "IAE_first_half", "IAE_second_half")
    return {k: {"median": statistics.median(r[k] for r in runs),
                "min": min(r[k] for r in runs),
                "max": max(r[k] for r in runs)} for k in keys}


def pct(x):
    return f"{100 * x:+.3f}%"


def main() -> int:
    started = time.perf_counter()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replicates", type=int, default=N_REPLICATES,
                    help="paired replicates; the registered value is 100")
    ap.add_argument("--skip-sensitivity", action="store_true",
                    help="headline only, for a quick check that it runs")
    ap.add_argument("--pool-length", type=float, default=POOL_LENGTH,
                    help=f"pool length in metres; the registered value is "
                         f"{POOL_LENGTH:g}")
    ap.add_argument("--min-gate-step", type=float, default=0.0,
                    help="smallest gate movement in metres for the HEADLINE run; "
                         "the registered protocol has none (0.0) and carries the "
                         "deadband as a declared sensitivity axis instead")
    ap.add_argument("--out", default=os.path.join(RESULTS, "control_comparison.json"),
                    help="where to write the result; point it away from results/ "
                         "when running with parameters other than the registered ones")
    ap.add_argument("--out-csv",
                    default=os.path.join(RESULTS, "tables", "control_comparison.csv"),
                    help="where to write the indicator table")
    args = ap.parse_args()
    n = args.replicates
    departures = []
    if n != N_REPLICATES:
        departures.append(f"{n} replicates, not the registered {N_REPLICATES}")
    if args.pool_length != POOL_LENGTH:
        departures.append(f"pool length {args.pool_length:g} m, "
                          f"not the registered {POOL_LENGTH:g} m")
    if args.min_gate_step:
        departures.append(f"headline minimum gate step {1000 * args.min_gate_step:g} mm, "
                          f"which the registered protocol does not have")
    if departures:
        print("!! " + "; ".join(departures)
              + ".\n!! This run is NOT the reported result.\n")

    syn, idl = ideal_law(), identified_law()
    pool = make_pool(args.pool_length)
    boot = random.Random(BOOT_SEED)

    print("=" * 74)
    print("H2 STAGE TWO -- CLOSED-LOOP COST OF THE BENCHMARK'S GATE LAW")
    print("=" * 74)
    print(f"  plant P_syn : Q = {syn.gamma:.4f} a^1 dh^0.5        "
          f"(Cd W sqrt(2g), [C98]/[B25])")
    print(f"  plant P_id  : Q = {idl.gamma:.4f} a^{ALPHA} dh^{BETA}  "
          f"(identified, capacity-matched)")
    print(f"  pool        : {pool.length:.0f} m, A_s = {pool.storage_area:.0f} m2, "
          f"tau = {pool.delay:.0f} s -> {max(1, round(pool.delay / DT))} step(s)")
    print(f"  tune on     : {S_TUNE.name}   {S_TUNE.inflow} m3/s, "
          f"offtake {S_TUNE.offtake}")
    print(f"  evaluate on : {S_EVAL.name}   {S_EVAL.inflow} m3/s, "
          f"offtake {S_EVAL.offtake}")
    print(f"  replicates  : {n} paired, seeds 0..{n - 1}")

    out = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            # Filled in at the end of the run: see "runtime_s" below. A timing
            # is only meaningful next to the machine that produced it and the
            # work it covers, so both are recorded here rather than in prose.
            "runtime_s": None,
            "runtime_covers": None,
        },
        "design": {
            "replicates": n,
            "seeds": [0, n - 1],
            "dt_s": DT,
            "scenario_tune": {"name": S_TUNE.name, "inflow_m3s": S_TUNE.inflow,
                              "offtake_m3s": S_TUNE.offtake,
                              "breaks_s": S_TUNE.breaks,
                              "source": S_TUNE.source},
            "scenario_eval": {"name": S_EVAL.name, "inflow_m3s": S_EVAL.inflow,
                              "offtake_m3s": S_EVAL.offtake,
                              "breaks_s": S_EVAL.breaks,
                              "source": S_EVAL.source},
            "pool": {"length_m": pool.length, "bottom_width_m": pool.bottom_width,
                     "side_slope": pool.side_slope,
                     "target_depth_m": pool.target_depth,
                     "tailwater_depth_m": pool.tailwater_depth,
                     "storage_area_m2": pool.storage_area,
                     "delay_s": pool.delay},
            "gate": {"a_min_m": A_MIN, "a_max_m": A_MAX,
                     "min_step_m_available": MIN_STEP,
                     "min_step_m_in_headline": args.min_gate_step},
            "noise": {"level_quantisation_m": LEVEL_QUANT,
                      "timing_shift_s": TIMING_SHIFT,
                      "initial_level_spread_m": LEVEL0_SPREAD},
            "tuning": {"control_horizon": CONTROL_HORIZON,
                       "max_expansions": MAX_EXPANSIONS,
                       "objective": "IAE on S_tune, noiseless, plant = model",
                       "grid_rule": "exhaustive; an axis whose optimum lands on "
                                    "a movable edge is extended by a decade and "
                                    "BOTH models are retuned"},
        },
        "laws": {
            "syn": {"gamma": syn.gamma, "alpha": syn.alpha, "beta": syn.beta},
            "id": {"gamma": idl.gamma, "alpha": idl.alpha, "beta": idl.beta,
                   "alpha_ci95": list(ALPHA_CI), "beta_ci95": list(BETA_CI)},
            "reference_point": {"q_ref_m3s": Q_REF, "dh_ref_m": DH_REF,
                                "a_ref_m": syn.opening_for(Q_REF, DH_REF)},
        },
        "controllers": {},
        "sensitivity": {},
    }

    rows = []
    for kind in ("PI", "MPC"):
        print("\n" + "-" * 74)
        print(f"{kind}")
        print("-" * 74)
        tuned, grid_log, arms = run_block(pool, syn, idl, kind, n,
                                          args.min_gate_step)
        for model in ("syn", "id"):
            t = tuned[model]
            print(f"  tuned M_{model:<3}: {t['params']}   "
                  f"IAE(S_tune) = {t['tuning_iae']:.6f}   "
                  f"{t['candidates_evaluated']} candidates")
        if grid_log["terminated_interior"]:
            verdict = "interior"
        elif grid_log["optimum_is_asymptotic"]:
            verdict = (f"asymptotic -- a further decade bought "
                       f"{grid_log['last_expansion_gain']:.2e} of IAE, so the "
                       f"objective is\n    walking to the deadbeat limit, not "
                       f"hitting a grid the author drew too small")
        else:
            verdict = "STILL ON AN EDGE -- the grid is truncating the search"
        print(f"    grid grew {grid_log['expansions']} time(s) to "
              f"{grid_log['final_grid_size']} points; optimum {verdict}")
        print(f"    same candidate set for both: "
              f"{grid_log['grid_fingerprint']}  (V11)")
        if tuned["syn"]["params"] == tuned["id"]["params"]:
            print("    both models tuned to the SAME gains -- the tuning stage "
                  "cannot separate them,\n    so delta below isolates the gate-law "
                  "inversion error alone")

        print(f"\n  {'combination':<16} {'IAE median':>12} {'MAE median':>12} "
              f"{'StE median':>12} {'IAW median':>12} {'sat':>8}")
        summaries = {}
        for model, plant in COMBOS:
            name = label(model, plant)
            s = summarise(arms[name])
            summaries[name] = s
            sat = s["saturated_fraction"]["max"]
            mark = " !" if sat > SATURATION_FLAG else ""
            print(f"  {name:<16} {s['IAE']['median']:12.6f} "
                  f"{s['MAE']['median']:12.6f} {s['StE']['median']:12.6f} "
                  f"{s['IAW']['median']:12.4f} {sat:7.1%}{mark}")
            rows.append([kind, name, tuned[model]["params"],
                         s["IAE"]["median"], s["MAE"]["median"],
                         s["StE"]["median"], s["IAQ"]["median"],
                         s["IAW"]["median"], sat])

        head = paired_delta(arms[label("syn", "id")], arms[label("id", "id")])
        mirror = paired_delta(arms[label("id", "syn")], arms[label("syn", "syn")])
        h_med, h_ci = statistics.median(head), bootstrap_ci(head, boot)
        m_med, m_ci = statistics.median(mirror), bootstrap_ci(mirror, boot)
        crosses = h_ci[0] <= 0.0 <= h_ci[1]

        gap_m = paired_gap_m(arms[label("syn", "id")], arms[label("id", "id")],
                             pool.target_depth)
        g_med, g_ci = statistics.median(gap_m), bootstrap_ci(gap_m, boot)

        print(f"\n  delta  (benchmark-tuned controller on the real plant)")
        print(f"    median {pct(h_med)}   95% CI [{pct(h_ci[0])}, {pct(h_ci[1])}]"
              f"   n = {len(head)}")
        print(f"    -> the interval {'INCLUDES' if crosses else 'excludes'} zero")
        print(f"    same difference in metres of mean level error: "
              f"{g_med * 1000:+.4f} mm")
        print(f"    the level sensor resolves {LEVEL_QUANT * 1000:.1f} mm, so "
              f"this is {abs(g_med) / LEVEL_QUANT:.1e} x the sensor step")
        print(f"  mirror (identified-tuned controller on the synthetic plant)")
        print(f"    median {pct(m_med)}   95% CI [{pct(m_ci[0])}, {pct(m_ci[1])}]")

        # Internal check with a proof behind it. In a MATCHED arm the controller
        # inverts the same law the plant applies, so the delivered discharge is
        # the commanded discharge exactly and the gate law cancels out of the
        # level equation. With equal gains the two matched arms must therefore
        # produce identical levels, differing only in gate POSITION. If they do
        # not -- outside saturation, where the caps do differ -- the mismatch is
        # leaking somewhere it should not.
        same_gains = tuned["syn"]["params"] == tuned["id"]["params"]
        gap = max(abs(a["IAE"] - b["IAE"]) for a, b in
                  zip(arms[label("syn", "syn")], arms[label("id", "id")]))
        clean = max(r["saturated_fraction"] for r in arms[label("syn", "syn")]
                    + arms[label("id", "id")]) == 0.0
        print(f"  check  matched arms agree to {gap:.2e} in IAE"
              f"   (gains equal: {same_gains}, no saturation: {clean})")
        if same_gains and clean and gap > 1e-12:
            print("    !! they should be IDENTICAL -- the gate law cancels in a "
                  "matched arm.\n       Something is carrying the mismatch where "
                  "it should not.")

        out["controllers"][kind] = {
            "tuned": tuned,
            "grid": grid_log,
            "indicators": summaries,
            "matched_arm_check": {"gains_equal": same_gains,
                                  "no_saturation": clean,
                                  "max_iae_gap": gap},
            "delta": {"median": h_med, "ci95": list(h_ci), "n": len(head),
                      "ci_includes_zero": bool(crosses),
                      "per_seed": head},
            "delta_absolute_m": {"median": g_med, "ci95": list(g_ci),
                                 "level_sensor_step_m": LEVEL_QUANT,
                                 "in_sensor_steps": abs(g_med) / LEVEL_QUANT},
            "delta_mirror": {"median": m_med, "ci95": list(m_ci),
                             "n": len(mirror)},
        }

    # ------------------------------------------------------------- sensitivity
    if not args.skip_sensitivity:
        print("\n" + "=" * 74)
        print("SENSITIVITY -- none of these is the headline")
        print("=" * 74)
        sens = {}

        print("\n  (a) joint 95% confidence region of the identified exponents (V10)")
        sens["exponent_ci"] = {}
        for kind in ("PI", "MPC"):
            corner_rows = []
            for al in ALPHA_CI:
                for be in BETA_CI:
                    law = identified_law(al, be)
                    _, _, a2 = run_block(pool, syn, law, kind, n)
                    d = paired_delta(a2[label("syn", "id")], a2[label("id", "id")])
                    corner_rows.append({"alpha": al, "beta": be,
                                        "delta_median": statistics.median(d)})
            meds = [c["delta_median"] for c in corner_rows]
            sens["exponent_ci"][kind] = {"corners": corner_rows,
                                         "min": min(meds), "max": max(meds)}
            print(f"    {kind:<4} delta median ranges "
                  f"{pct(min(meds))} .. {pct(max(meds))} over the four corners")

        print("\n  (b) pool the experiment is run on")
        sens["pool_length"] = {}
        for kind in ("PI", "MPC"):
            per = []
            for length in (2000.0, 3000.0, 4000.0, 7000.0):
                p2 = make_pool(length)
                _, _, a2 = run_block(p2, syn, idl, kind, n)
                d = paired_delta(a2[label("syn", "id")], a2[label("id", "id")])
                per.append({"length_m": length,
                            "delta_median": statistics.median(d)})
            meds = [c["delta_median"] for c in per]
            sens["pool_length"][kind] = {"pools": per,
                                         "min": min(meds), "max": max(meds)}
            print(f"    {kind:<4} delta median ranges "
                  f"{pct(min(meds))} .. {pct(max(meds))} over "
                  f"2000-7000 m pools")

        print(f"\n  (c) 0.5% minimum gate movement, {MIN_STEP * 1000:.1f} mm "
              f"([C98] p. 24) -- NOT in the registered protocol")
        sens["min_gate_step"] = {}
        for kind in ("PI", "MPC"):
            _, _, a2 = run_block(pool, syn, idl, kind, n, MIN_STEP)
            d = paired_delta(a2[label("syn", "id")], a2[label("id", "id")])
            med, ci = statistics.median(d), bootstrap_ci(d, boot)
            sens["min_gate_step"][kind] = {
                "min_step_m": MIN_STEP,
                "delta_median": med,
                "delta_ci95": list(ci),
                # H2-s3: [C98] proposes IAQ as the indicator against gate
                # hunting, and the headline runs allow a movement of any size.
                # These are the same runs that produced delta above, so the two
                # cannot disagree about which protocol they describe.
                "indicators": {
                    lab: {k: statistics.median(r[k] for r in runs)
                          for k in ("MAE", "IAE", "StE", "IAQ", "IAW")}
                    for lab, runs in a2.items()},
            }
            print(f"    {kind:<4} delta median {pct(med)}   "
                  f"95% CI [{pct(ci[0])}, {pct(ci[1])}]")
        out["sensitivity"] = sens

    # ------------------------------------------------------------------ output
    out["environment"]["runtime_s"] = round(time.perf_counter() - started, 1)
    out["environment"]["runtime_covers"] = (
        f"{n} paired replicates x 4 combinations x 2 controllers, tuning "
        f"included" + ("" if args.skip_sensitivity else ", plus the three "
                       "sensitivity sweeps"))

    for target in (args.out, args.out_csv):
        os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["controller", "combination", "gains", "IAE_median",
                    "MAE_median", "StE_median", "IAQ_median", "IAW_median",
                    "saturated_fraction_max"])
        for r in rows:
            w.writerow([r[0], r[1], " ".join(f"{v:g}" for v in r[2])]
                       + [f"{v:.8f}" for v in r[3:]])
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(args.out, ROOT)} and "
          f"{os.path.relpath(args.out_csv, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
