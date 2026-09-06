"""The circularity detector, as a function anyone can call on any structure.

``scripts/second_structure.py`` used to hold this code. It was moved here so that
the same implementation answers three callers -- the published script, the results
explorer, and a reader who wants to point it at their own gate -- because a detector
that exists in two copies is a detector whose two answers can drift apart.

What it decides, and by which rule, is fixed in the project's hypothesis log (H5 and
H5b) and is passed in as :class:`Thresholds` rather than hidden in the body, so a run
always states the numbers it was judged by.

    kappa = Q / (a sqrt(2 g dh))

If the published discharge was produced by the gate equation, kappa cannot move. If it
does move, a rating of another form may still be behind it, so a second fit is made in
logarithms and what it leaves behind is examined: a rating leaves a residual that is
*structured* in the predictors, an instrument leaves scatter.

Nothing here reads a file or prints. Feed it :class:`gatempc.archive.Sample` objects
from wherever they come from.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .archive import Sample, contiguous_runs, kappa, median, quantile

# The three branches, from hypotheses.md H5, and the H5b rule. Defaults are the values
# that were written down before the measurement; a caller may pass others, and the
# result then carries whatever it was judged by.
KAPPA_TIGHT = 0.001          # 0.1% -- same circularity, same form
RATING_TIGHT = 0.01          # 1%   -- circularity, different rating form
STRUCTURED = 1.0             # ratio above this: deterministic, misspecified
UNSTRUCTURED = 0.5           # ratio below this: scatter, no conclusion drawn
BINS = 5


@dataclass(frozen=True)
class Thresholds:
    """Everything the verdict depends on, in one object that travels with it."""

    kappa_tight: float = KAPPA_TIGHT
    rating_tight: float = RATING_TIGHT
    structured_above: float = STRUCTURED
    unstructured_at_or_below: float = UNSTRUCTURED
    bins: int = BINS


# ------------------------------------------------------------------- statistics


def spread(values: Sequence[float]) -> float:
    """Relative spread of a quantity about its own median: IQR / |median|.

    Robust, and the same shape of statistic used for kappa at the primary
    structure, so the two numbers can be read against each other.
    """
    med = median(values)
    if med == 0:
        return float("nan")
    s = sorted(values)
    return (quantile(s, 0.75) - quantile(s, 0.25)) / abs(med)


def daily(samples: Iterable[Sample], value_of: Callable[[Sample], float | None]):
    """value_of applied per sample, grouped by calendar day (UTC)."""
    out = defaultdict(list)
    for s in samples:
        v = value_of(s)
        if v is not None:
            out[s.time[:10]].append(v)
    return out


def ols3(rows):
    """Least squares for y = c0 + c1 x1 + c2 x2 by normal equations.

    Three parameters and a well-conditioned design; a dependency-free solve
    keeps this runnable wherever the rest of the repository is.
    """
    sxx = [[0.0] * 3 for _ in range(3)]
    sxy = [0.0] * 3
    for y, x1, x2 in rows:
        x = (1.0, x1, x2)
        for i in range(3):
            sxy[i] += x[i] * y
            for j in range(3):
                sxx[i][j] += x[i] * x[j]
    # Gaussian elimination with partial pivoting.
    a = [row[:] + [sxy[i]] for i, row in enumerate(sxx)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None, None
        a[col], a[piv] = a[piv], a[col]
        for r in range(3):
            if r == col:
                continue
            f = a[r][col] / a[col][col]
            for c in range(col, 4):
                a[r][c] -= f * a[col][c]
    coef = [a[i][3] / a[i][i] for i in range(3)]
    resid = [y - (coef[0] + coef[1] * x1 + coef[2] * x2) for y, x1, x2 in rows]
    return coef, resid


def binned_residual(values, resid, n_bins: int = BINS):
    """Median residual in equal-count bins of a predictor.

    Equal-count rather than equal-width: the predictors here are far from
    uniform, and equal-width bins would put almost everything in one of them and
    make the spread a statement about the binning instead of about the data.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    edges = [len(order) * k // n_bins for k in range(n_bins + 1)]
    out = []
    for k in range(n_bins):
        idx = order[edges[k]:edges[k + 1]]
        if not idx:
            continue
        out.append({"n": len(idx),
                    "x_lo": values[idx[0]], "x_hi": values[idx[-1]],
                    "median_residual": median([resid[i] for i in idx])})
    return out


def lag1_autocorrelation(samples, resid):
    """Correlation of consecutive residuals, within runs on the 15-minute grid.

    Reported, never used in the verdict: the flow itself is autocorrelated, so a
    high value is consistent with both readings and settles nothing.
    """
    pairs = []
    for run in contiguous_runs(samples):
        for j in range(1, len(run)):
            pairs.append((resid[run[j - 1]], resid[run[j]]))
    if len(pairs) < 3:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else None


# ----------------------------------------------------------------------- blocks


def kappa_summary(samples: Sequence[Sample], label: str) -> dict | None:
    """kappa over one set of samples, plus how far a complete day strays.

    A complete day is one with all 96 readings of the 15-minute grid; an
    incomplete day could stray for the ordinary reason that it covers a
    different part of the operating range.
    """
    ks = [(s, kappa(s)) for s in samples]
    usable = [(s, k) for s, k in ks if k is not None]
    if not usable:
        return None
    vals = [k for _s, k in usable]
    med = median(vals)
    by_day = daily([s for s, _k in usable], kappa)
    full = {d: v for d, v in by_day.items() if len(v) >= 96}
    dev = sorted(abs(median(v) / med - 1.0) for v in full.values())
    return {
        "label": label,
        "n_samples": len(samples),
        "n_usable": len(usable),
        "median_m": med,
        "spread_iqr_over_median": spread(vals),
        "complete_days": len(full),
        "typical_complete_day_deviation": median(dev) if dev else None,
        "worst_complete_day_deviation": dev[-1] if dev else None,
    }


def rating_fit(samples: Sequence[Sample]) -> tuple[dict | None, list, list]:
    """Fit log Q on log dh and log a; return the summary, the kept samples, residuals.

    Residuals come back as relative errors (exp(r) - 1), which is what both the
    spread statistic and the structure test are stated in.
    """
    kept = [s for s in samples if s.q > 0 and s.dh > 0 and s.a > 0]
    rows = [(math.log(s.q), math.log(s.dh), math.log(s.a)) for s in kept]
    coef, resid = ols3(rows)
    if coef is None:
        return None, kept, []
    relative = [math.exp(r) - 1.0 for r in resid]
    absolute = sorted(abs(r) for r in relative)
    summary = {
        "n": len(rows),
        "form": "log Q = c0 + c1 log(dh) + c2 log(a)",
        "c0": coef[0], "c1_dh": coef[1], "c2_a": coef[2],
        "median_abs_relative_residual": median(absolute),
        "q95_abs_relative_residual": quantile(absolute, 0.95),
    }
    return summary, kept, relative


def structure_of(kept, relative, median_abs: float, thresholds: Thresholds) -> dict:
    """H5b: is what the rating fit leaves behind structure, or scatter?"""
    out: dict = {}
    for name, getter in (("a", lambda s: s.a), ("dh", lambda s: s.dh)):
        bins = binned_residual([getter(s) for s in kept], relative, thresholds.bins)
        span = (max(b["median_residual"] for b in bins)
                - min(b["median_residual"] for b in bins))
        out[name] = {"bins": bins, "spread_of_bin_medians": span,
                     "ratio_to_median_abs_residual": span / median_abs}
    out["lag1_autocorrelation"] = lag1_autocorrelation(kept, relative)
    return out


# ---------------------------------------------------------------------- verdict


def h5b_branch(structure: dict, thresholds: Thresholds) -> tuple[str, str]:
    ratios = [structure[n]["ratio_to_median_abs_residual"] for n in ("a", "dh")]
    if max(ratios) > thresholds.structured_above:
        return "structured", (
            "the residual is dominated by structure in the predictors, so the "
            "discharge is a deterministic function of them and this power law is "
            "the wrong form: computed, not measured")
    if max(ratios) <= thresholds.unstructured_at_or_below:
        return "unstructured", (
            "the residual carries no structure in the predictors, so an "
            "independent measurement with about one per cent noise cannot be "
            "ruled out; the warning stays confined to the primary structure")
    return "ambiguous", (
        "the ratio falls between the two thresholds fixed beforehand; nothing is "
        "concluded either way")


def h5_branch(kappa_spread: float, rating_median: float,
              thresholds: Thresholds) -> tuple[str, str]:
    if kappa_spread < thresholds.kappa_tight:
        return "same_form", (
            "kappa is constant here too: the circularity repeats in the SAME "
            "form, and the warning generalises directly")
    if rating_median < thresholds.rating_tight:
        return "different_form", (
            "kappa moves, but the discharge is still reproduced by a "
            "stage-and-opening rating to within a fraction of a per cent: the "
            "circularity repeats in a DIFFERENT form")
    return "not_a_rating", (
        "neither the gate equation nor a stage-and-opening rating reproduces "
        "this discharge tightly; it may be an independent measurement, and the "
        "warning is confined to structures whose rating is gate-based")


class DetectorError(RuntimeError):
    """Raised when the data cannot answer the question, rather than guessing."""


def analyse(samples: Sequence[Sample],
            approved: Sequence[Sample] | None = None,
            thresholds: Thresholds | None = None) -> dict:
    """Run the whole detector and return the record it is judged by.

    ``approved`` is the subset carrying the archive's Approved flag on all four
    series; it is summarised separately because a site-year that is only partly
    approved must be shown to survive on the approved subset alone.
    """
    thresholds = thresholds or Thresholds()
    if not samples:
        raise DetectorError("no timestamps with all four series")

    all_block = kappa_summary(samples, "all four-series timestamps")
    if all_block is None:
        raise DetectorError(
            "kappa is undefined everywhere: every timestamp has a shut gate or no head")
    approved_block = (kappa_summary(approved, "Approved only")
                      if approved else None)

    rating, kept, relative = rating_fit(samples)
    if rating is None:
        raise DetectorError(
            "the log-log design is singular; report this rather than forcing a fit")

    structure = structure_of(kept, relative, rating["median_abs_relative_residual"],
                             thresholds)
    h5b, h5b_verdict = h5b_branch(structure, thresholds)
    branch, verdict = h5_branch(all_block["spread_iqr_over_median"],
                                rating["median_abs_relative_residual"], thresholds)
    return {
        "n_four_series": len(samples),
        "n_approved": len(approved) if approved is not None else 0,
        "kappa_all": all_block,
        "kappa_approved": approved_block,
        "rating_fit": rating,
        "thresholds": {"kappa_spread": thresholds.kappa_tight,
                       "rating_residual": thresholds.rating_tight},
        "branch": branch, "verdict": verdict,
        "h5b": {"structure": structure, "branch": h5b, "verdict": h5b_verdict,
                "thresholds": {"structured_above": thresholds.structured_above,
                               "unstructured_at_or_below":
                                   thresholds.unstructured_at_or_below,
                               "bins": thresholds.bins}},
    }
