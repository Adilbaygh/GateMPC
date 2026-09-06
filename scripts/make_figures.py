"""Every figure in the manuscript, drawn from published result files.

    python scripts/make_figures.py                  # all of them
    python scripts/make_figures.py --list           # what exists
    python scripts/make_figures.py --only kappa     # one, while iterating

No figure is drawn by hand and none reads a private file: each one takes a
``results/`` table or JSON that a script in this directory wrote and that a
reader can download, so every published picture can be regenerated from the
repository alone.

Journal requirements, from the Extrica template (requirements/journal.md):

  * text width is 167 mm less 15 mm margins either side, so a full-width figure
    is exactly 137 mm and is inserted at 100 per cent -- never rescaled in Word,
    which would change the effective resolution and the text size together;
  * bitmaps at 300 dpi or better: these are written at 600;
  * the figure must be ONE graphical object with nothing added on top of it in
    the document, so every annotation, panel label and legend lives inside the
    PNG;
  * captions go below the figure as "Fig. n." in 9 pt -- they are written in the
    manuscript, not burned into the image, so the caption text is not here.

Colour is used, but never alone. The categorical palette below passes the
colour-vision checks (adjacent-pair separation, chroma, contrast against the
page), and on top of that every series also differs in marker or dash pattern,
so the figures survive a greyscale print and a colourblind reader equally.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as exc:                                  # pragma: no cover
    raise SystemExit(f"matplotlib and numpy are required to draw figures: {exc}")

RESULTS = os.path.join(ROOT, "results")
TABLES = os.path.join(RESULTS, "tables")
FIGURES = os.path.join(RESULTS, "figures")
PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")

MM = 1.0 / 25.4
WIDTH = 137 * MM                    # the journal's text width, exactly
DPI = 600

# Fixed categorical order. Never cycled, never reassigned between figures: a
# reader who learns that vermillion is "after the rating change" in one figure
# should not meet it as something else in the next.
BLUE, VERMILLION, GREEN = "#0072B2", "#D55E00", "#009E73"
INK, MUTED, FAINT = "#1a1a1a", "#5c5c5c", "#b9b9b9"
BAND = "#dfe7ee"                    # criterion / envelope shading


def style() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        # Times New Roman matches the manuscript; the fallbacks keep the script
        # runnable where it is not installed, at the cost of a font mismatch
        # that the run reports rather than hides.
        "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "axes.linewidth": 0.6, "lines.linewidth": 1.0,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": INK,
        "axes.grid": True, "grid.color": FAINT, "grid.linewidth": 0.4,
        "grid.alpha": 0.7,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.handlelength": 2.4,
        "figure.dpi": DPI, "savefig.dpi": DPI,
    })


def panel(ax, letter: str, title: str = "") -> None:
    """Panel label inside the axes, where Word cannot separate it from the art."""
    ax.set_title(f"{letter}) {title}" if title else f"{letter})",
                 loc="left", pad=3, fontsize=8)


"""Files opened while drawing the figure currently in hand.

Appendix A of the manuscript names the published file behind every figure. That
list used to be typed out beside the drawing code, and it drifted: a table gained
two data sources and its appendix entry did not follow, which is the same failure
this project keeps finding in recorded numbers. So the list is not written down
here -- it is recorded as the readers below are called, and `make_tables.py`
builds the appendix from what the figures actually opened.
"""
OPENED: set[str] = set()


def _record(path: str) -> str:
    OPENED.add(os.path.relpath(path, ROOT).replace("\\", "/"))
    return path


def read_csv(path: str) -> list[dict[str, str]]:
    with open(_record(path), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(path: str) -> dict:
    with open(_record(path), encoding="utf-8") as fh:
        return json.load(fh)


def need(*paths: str) -> None:
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise SystemExit(
            "missing input(s):\n  " + "\n  ".join(
                os.path.relpath(m, ROOT) for m in missing)
            + "\nrun the script that writes them first")


# ------------------------------------------------------------------ fig: kappa

def fig_kappa():
    """The circularity evidence: a coefficient that does not behave like one.

    Panel (a) is the daily median of kappa over the eight folds. Panel (b) is
    the distribution of how far a complete day's median sits from its period
    median, as a cumulative curve on a log axis -- chosen over a histogram
    because the two facts that matter live four decades apart: the typical day
    is off by a hundredth of a per cent, and a handful of days are off by more
    than one per cent. A histogram shows one or the other; the curve shows both.
    """
    need(os.path.join(TABLES, "kappa_daily.csv"),
         os.path.join(RESULTS, "archive_diagnostics.json"))
    rows = read_csv(os.path.join(TABLES, "kappa_daily.csv"))
    diag = read_json(os.path.join(RESULTS, "archive_diagnostics.json"))["kappa"]
    split = diag["split_after"]

    days = [r["date"] for r in rows]
    x = [dt.date.fromisoformat(d) for d in days]
    y = [float(r["kappa_median_m"]) for r in rows]
    complete = [r["complete"] == "1" for r in rows]
    p1, p2 = diag["periods"]

    fig, (ax, bx) = plt.subplots(
        1, 2, figsize=(WIDTH, 52 * MM), layout="constrained",
        gridspec_kw={"width_ratios": [1.75, 1]})

    # Complete days only. A "daily median" of one or two samples is not a daily
    # median -- that is exactly what fooled the first version of the step
    # detector -- so the picture is drawn from the days that have a full 96.
    xc = [d for d, ok in zip(x, complete) if ok]
    yc = [v for v, ok in zip(y, complete) if ok]
    ax.plot(xc, yc, color=MUTED, lw=0.45, zorder=2)
    for p, c, ls in ((p1, BLUE, "--"), (p2, VERMILLION, ":")):
        seg = [d for d in xc if p["from"] <= d.isoformat() <= p["to"]]
        ax.plot([seg[0], seg[-1]], [p["median_m"]] * 2, color=c, ls=ls, lw=1.3,
                zorder=3, label=f"median {p['median_m']:.4f} m")
    ax.axvline(dt.date.fromisoformat(split), color=INK, lw=0.7, zorder=4)
    lo, hi = min(yc), max(yc)
    pad = 0.08 * (hi - lo)
    ax.set_ylim(lo - pad, hi + 2.2 * pad)
    ax.annotate(f"rating change {split}, {100 * diag['step_relative']:+.2f}%",
                xy=(dt.date.fromisoformat(split), hi + 1.4 * pad), xytext=(4, 0),
                textcoords="offset points", ha="left", va="center", fontsize=7,
                color=INK)
    ax.set_ylabel(r"$\kappa = Q/(a\sqrt{2g\,\Delta h})$,  m")
    ax.set_xlabel("daily median, complete days only")
    ax.legend(loc="lower right", ncol=1)
    panel(ax, "a")

    counts = []
    for p, c, ls, lab in ((p1, BLUE, "--", "before"), (p2, VERMILLION, ":", "after")):
        dev = sorted(abs(v / p["median_m"] - 1.0)
                     for d, v, ok in zip(days, y, complete)
                     if ok and p["from"] <= d <= p["to"])
        dev = [d for d in dev if d > 0]
        counts.append(len(dev))
        frac = np.arange(1, len(dev) + 1) / len(dev)
        bx.plot(dev, 100 * frac, color=c, ls=ls, lw=1.2, label=lab)
    bx.set_xscale("log")
    bx.axvline(0.005, color=INK, lw=0.7, ls="-.")
    bx.text(0.005, 46, " 0.5%", fontsize=7, color=INK, ha="left")
    # Constrained layout reserves HEIGHT for an x label, not width, so a label
    # wider than its narrow panel runs off the figure and is cut. Two lines.
    bx.set_xlabel("deviation from\nthe period median")
    bx.set_ylabel("complete days below, %")
    bx.set_ylim(0, 100)
    bx.legend(loc="upper left")
    panel(bx, "b", f"n = {counts[0]} / {counts[1]} days")
    return fig


# ------------------------------------------------------------ fig: validation

def fig_gaugings():
    """H4: the benchmark law against 77 independent field measurements.

    The question is not "is the median residual zero" -- with n = 77 and ADCP
    measurements of a few per cent, it could not be. It is whether the residual
    carries STRUCTURE: a trend against opening, head, or submergence would be a
    systematic error a controller cannot average away. So three panels plot the
    residual against each, with the binned medians on top, and the fourth shows
    the distribution against the pre-registered 5 per cent criterion.
    """
    need(os.path.join(TABLES, "gauging_residuals.csv"),
         os.path.join(TABLES, "gauging_residual_bins.csv"),
         os.path.join(RESULTS, "gate_law_validation.json"))
    rows = read_csv(os.path.join(TABLES, "gauging_residuals.csv"))
    bins = read_csv(os.path.join(TABLES, "gauging_residual_bins.csv"))
    val = read_json(os.path.join(RESULTS, "gate_law_validation.json"))
    crit = val["criteria"]["bias"]
    med = val["relative_residual"]["median"]

    a = np.array([float(r["gate_opening_m"]) for r in rows])
    dh = np.array([float(r["head_difference_m"]) for r in rows])
    res = np.array([100 * float(r["relative_residual"]) for r in rows])
    after = np.array([r["period"] == "after" for r in rows])

    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 88 * MM), layout="constrained")
    (ax, bx), (cx, dx) = axes

    def scatter(axis, xs, xlabel, letter, binned=None):
        axis.axhspan(-100 * crit, 100 * crit, color=BAND, zorder=0)
        axis.axhline(0, color=MUTED, lw=0.6, zorder=1)
        axis.axhline(100 * med, color=GREEN, lw=1.0, ls="--", zorder=2)
        for mask, colour, marker, lab in (
                (~after, BLUE, "o", "before 2021-10-08"),
                (after, VERMILLION, "^", "after 2021-10-08")):
            axis.plot(xs[mask], res[mask], marker, ms=3.2, mfc="none", mew=0.8,
                      color=colour, ls="none", label=lab, zorder=3)
        if binned:
            bx_, by_ = zip(*binned)
            axis.plot(bx_, by_, "s", ms=5, color=INK, ls="-", lw=0.9, zorder=4,
                      mfc="white", mew=0.9, label="binned median")
        axis.set_xlabel(xlabel)
        axis.set_ylim(-8, 8)
        panel(axis, letter)

    def binned_for(key, xs):
        out = []
        for b in bins:
            if b["binned_by"] != key:
                continue
            lo, hi = float(b["x_lo"]), float(b["x_hi"])
            inside = xs[(xs >= lo) & (xs <= hi)]
            centre = float(np.median(inside)) if inside.size else (lo + hi) / 2
            out.append((centre, 100 * float(b["median_residual"])))
        return out

    scatter(ax, a, "gate opening $a$, m", "a")
    ax.set_ylabel("relative residual, %")
    scatter(bx, dh, r"head difference $\Delta h$, m", "b",
            binned_for("dh", dh))
    scatter(cx, a / dh, r"relative opening $a/\Delta h$", "c",
            binned_for("a/dh", a / dh))
    cx.set_ylabel("relative residual, %")
    # One legend for the whole figure, above the panels: a legend sitting inside
    # a scatter covers the very points it explains.
    handles, labels = cx.get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncol=3,
               markerscale=1.6, columnspacing=1.8)

    order = np.sort(res)
    dx.plot(order, 100 * np.arange(1, order.size + 1) / order.size,
            color=INK, lw=1.2)
    dx.axvspan(-100 * crit, 100 * crit, color=BAND, zorder=0)
    dx.axvline(100 * med, color=GREEN, lw=1.0, ls="--")
    dx.text(100 * med, 4, f" median {100 * med:+.2f}%", fontsize=7, color=INK)
    dx.set_xlabel("relative residual, %")
    dx.set_ylabel("gaugings below, %")
    dx.set_xlim(-8, 8)
    dx.set_ylim(0, 100)
    panel(dx, "d", f"n = {val['accepted']}")
    return fig


# ---------------------------------------------------------------- fig: storage

def fig_storage():
    """H0c-1: what an unidentifiable parameter looks like.

    A_s is a fixed property of the pool. Panel (a) is the pooled distribution of
    the per-event estimates, with the physically impossible negative half marked
    -- not removed, because removing them is the tuning the pre-registration
    forbids. Panel (b) is the per-fold median with its bootstrap interval: eight
    estimates of one constant that do not agree.
    """
    need(os.path.join(TABLES, "storage_estimates.csv"),
         os.path.join(RESULTS, "archive_diagnostics.json"))
    rows = read_csv(os.path.join(TABLES, "storage_estimates.csv"))
    sto = read_json(os.path.join(RESULTS, "archive_diagnostics.json"))["storage"]
    vals = np.array([float(r["a_s_m2"]) for r in rows]) / 1000.0     # 10^3 m2

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(WIDTH, 52 * MM),
                                 layout="constrained",
                                 gridspec_kw={"width_ratios": [1.15, 1]})

    lo, hi = -1000.0, 2000.0
    inside = vals[(vals >= lo) & (vals <= hi)]
    ax.hist(inside, bins=70, range=(lo, hi), color=BLUE, alpha=0.85, lw=0)
    ax.axvspan(lo, 0, color=VERMILLION, alpha=0.12, zorder=0)
    ax.axvline(0, color=VERMILLION, lw=0.9)
    ax.axvline(sto["median_m2"] / 1000.0, color=INK, lw=1.0, ls="--")
    ax.text(sto["median_m2"] / 1000.0, ax.get_ylim()[1] * 0.94,
            f" median {sto['median_m2'] / 1000:.0f}", fontsize=7, color=INK)
    ax.text(lo * 0.95, ax.get_ylim()[1] * 0.94,
            f"physically\nimpossible\n{100 * sto['negative_fraction']:.1f}%",
            fontsize=7, color=VERMILLION, va="top")
    ax.set_xlabel(r"local estimate of $A_s$,  $10^3$ m$^2$")
    ax.set_ylabel(f"events (n = {sto['n_accepted']})")
    panel(ax, "a", f"{vals.size - inside.size} of {vals.size} fall outside "
                   f"this range")

    folds = sorted(sto["per_fold"], key=int)
    med = np.array([sto["per_fold"][f]["median"] for f in folds]) / 1000.0
    lo_ci = np.array([sto["per_fold"][f]["ci_lo"] for f in folds]) / 1000.0
    hi_ci = np.array([sto["per_fold"][f]["ci_hi"] for f in folds]) / 1000.0
    xs = np.arange(len(folds))
    bx.errorbar(xs, med, yerr=[med - lo_ci, hi_ci - med], fmt="o", ms=4,
                color=BLUE, ecolor=MUTED, elinewidth=0.9, capsize=2.5, mfc="white",
                mew=1.0)
    bx.axhline(sto["median_m2"] / 1000.0, color=INK, lw=1.0, ls="--",
               label="pooled median")
    bx.set_xticks(xs)
    bx.set_xticklabels(folds, rotation=90)
    bx.set_ylabel(r"$A_s$,  $10^3$ m$^2$")
    bx.set_xlabel("cross-validation fold")
    bx.legend(loc="upper right")
    panel(bx, "b", f"span {max(med) / min(med):.2f}×")
    return fig


# ----------------------------------------------------------------- fig: census

def fig_census():
    """Why the study uses 2018-2025, as a measurement rather than a claim.

    The gate series advertises a begin date of 2007; stage does not exist until
    2017. A sequential ramp carries the record count, one hue light to dark, and
    the fold years are marked on the axis. The two structures are separate
    panels because they are separate questions: one supplies the folds, the
    other is the external check.
    """
    need(os.path.join(PACKAGE, "coverage_census.csv"))
    rows = read_csv(os.path.join(PACKAGE, "coverage_census.csv"))
    series = ["gate_opening", "headwater", "tailwater", "discharge",
              "timestamps_with_all_four"]
    labels = ["gate opening", "headwater", "tailwater", "discharge",
              "all four"]
    folds = {"09522700": set(range(2018, 2026)), "09428500": set()}
    # Primary structure first: it is the one the folds come from, and a reader
    # meeting the external check before the subject of the study reads the
    # figure backwards.
    sites = sorted({r["site"] for r in rows},
                   key=lambda s: (not folds.get(s), s))

    fig, axes = plt.subplots(len(sites), 1, figsize=(WIDTH, 62 * MM),
                             layout="constrained")
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "counts", ["#f4f8fb", BLUE])
    im = None
    for axis, site in zip(np.atleast_1d(axes), sites):
        srows = sorted((r for r in rows if r["site"] == site),
                       key=lambda r: int(r["year"]))
        years = [int(r["year"]) for r in srows]
        grid = np.array([[int(r[s]) for r in srows] for s in series]) / 1000.0
        im = axis.imshow(grid, aspect="auto", cmap=cmap, vmin=0, vmax=36,
                         interpolation="nearest")
        axis.set_yticks(range(len(series)), labels)
        axis.set_xticks(range(len(years)),
                        [str(y) for y in years], rotation=90)
        axis.grid(False)
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                if grid[i, j] > 0:
                    axis.text(j, i, f"{grid[i, j]:.0f}", ha="center",
                              va="center", fontsize=5.2,
                              color="white" if grid[i, j] > 20 else INK)
        marked = False
        for j, y in enumerate(years):
            if y in folds.get(site, ()):
                axis.plot([j - 0.5, j + 0.5], [len(series) - 0.35] * 2,
                          color=VERMILLION, lw=2.2, solid_capstyle="butt",
                          clip_on=False, zorder=5)
                marked = True
        # The note belongs in the title, not loose on the canvas: a stray text
        # object at the figure edge lands on the year labels.
        note = " — cross-validation folds underlined" if marked else ""
        axis.set_title(f"USGS {site}{note}", loc="left", fontsize=8, pad=3)
    fig.colorbar(im, ax=np.atleast_1d(axes).tolist(), shrink=0.7,
                 label=r"records, $10^3$")
    return fig


# ------------------------------------------------------------- fig: envelope

def fig_envelope():
    """H2, stage one: the modelling error a controller would actually carry.

    After capacity matching, the two laws differ only by their exponents, so the
    relative discharge error is a smooth surface over (a, dh) that follows from
    the fit alone and depends on no simulation assumption. What matters is where
    on that surface the structure operates, so both envelopes are drawn on it --
    the benchmark's, and the one the archive actually visited.
    """
    need(os.path.join(RESULTS, "model_error_envelope.json"))
    env = read_json(os.path.join(RESULTS, "model_error_envelope.json"))
    ref, exp = env["reference"], env["exponents"]
    a_ref, dh_ref = ref["a_ref_m"], ref["dh_ref_m"]
    da, db = exp["alpha"] - 1.0, exp["beta"] - 0.5

    boxes = [(env["envelopes"]["asce_test_2_1"], BLUE, "-", "ASCE Test 2-1"),
             (env["envelopes"]["observed_wellton_mohawk"], VERMILLION, "--",
              "observed at Wellton-Mohawk")]
    a_lo = min(b[0]["a_range_m"][0] for b in boxes) * 0.9
    a_hi = max(b[0]["a_range_m"][1] for b in boxes) * 1.05
    dh_lo = min(b[0]["dh_range_m"][0] for b in boxes) * 0.9
    dh_hi = max(b[0]["dh_range_m"][1] for b in boxes) * 1.05

    aa = np.linspace(max(a_lo, 1e-3), a_hi, 400)
    hh = np.linspace(dh_lo, dh_hi, 400)
    A, H = np.meshgrid(aa, hh)
    Z = 100 * ((A / a_ref) ** da * (H / dh_ref) ** db - 1.0)

    fig, ax = plt.subplots(figsize=(WIDTH, 62 * MM), layout="constrained")
    top = float(np.nanmax(np.abs(Z)))
    levels = np.linspace(-top, top, 21)
    cs = ax.contourf(A, H, Z, levels=levels, cmap="RdBu_r", extend="neither")
    ax.contour(A, H, Z, levels=[0], colors=[INK], linewidths=0.8)
    for box, colour, ls, label in boxes:
        (x0, x1), (y0, y1) = box["a_range_m"], box["dh_range_m"]
        ax.add_patch(matplotlib.patches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=colour, ls=ls,
            lw=1.4, label=f"{label}  ≤ "
                          f"{100 * box['error_largest_ci']:.2f}%"))
    ax.plot([a_ref], [dh_ref], "o", ms=5, mfc="white", mec=INK, mew=1.0,
            label="matching point")
    ax.set_xlabel("gate opening $a$, m")
    ax.set_ylabel(r"head difference $\Delta h$, m")
    ax.grid(False)
    # Below the axes, not on them: dark text on a dark contour is unreadable,
    # and a legend box large enough to fix that would cover the surface.
    handles, labels = ax.get_legend_handles_labels()
    # Two rows, not three columns: at 137 mm a single row of three entries runs
    # off both ends of the figure.
    fig.legend(handles, labels, loc="outside lower center", ncol=2,
               columnspacing=2.0)
    cb = fig.colorbar(cs, ax=ax, shrink=0.85, ticks=np.linspace(-top, top, 7),
                      label=r"$Q_\mathrm{id}/Q_\mathrm{syn}-1$,  %")
    cb.ax.set_yticklabels([f"{v:+.1f}" for v in np.linspace(-top, top, 7)])
    return fig


# -------------------------------------------------------------- fig: control

def fig_control():
    """H2, stage two: what the model error costs, and why its sign means little.

    Panel (a) is the paired penalty over 100 replicates for each controller.
    Panel (b) is the same statistic on pools of other lengths -- the sign turns
    over, which is the evidence that what is being measured is a small loop-gain
    error and not a property of either gate law.
    """
    need(os.path.join(RESULTS, "control_comparison.json"))
    cc = read_json(os.path.join(RESULTS, "control_comparison.json"))

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(WIDTH, 55 * MM),
                                 layout="constrained")
    for kind, colour, ls in (("PI", BLUE, "--"), ("MPC", VERMILLION, ":")):
        d = cc["controllers"][kind]["delta"]
        vals = np.sort(np.array(d["per_seed"]) * 100)
        ax.plot(vals, 100 * np.arange(1, vals.size + 1) / vals.size,
                color=colour, ls=ls, lw=1.3, label=kind)
        ax.axvspan(100 * d["ci95"][0], 100 * d["ci95"][1], color=colour,
                   alpha=0.13, lw=0)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel(r"$\delta$, %")
    ax.set_ylabel("replicates below, %")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper left")
    spans = {k: (max(cc["controllers"][k]["delta"]["per_seed"])
                 - min(cc["controllers"][k]["delta"]["per_seed"])) * 100
             for k in ("PI", "MPC")}
    # The MPC curve is a vertical line at this scale. That is a result, not a
    # drawing fault, so the two spreads are named in the panel title -- an
    # annotation large enough to say it inside the axes lands on the PI curve.
    panel(ax, "a", f"spread over 100 seeds: PI {spans['PI']:.1f}%, "
                   f"MPC {spans['MPC']:.2f}%")

    for kind, colour, marker, ls in (("PI", BLUE, "o", "--"),
                                     ("MPC", VERMILLION, "^", ":")):
        pools = cc["sensitivity"]["pool_length"][kind]["pools"]
        xs = [p["length_m"] / 1000.0 for p in pools]
        ys = [100 * p["delta_median"] for p in pools]
        bx.plot(xs, ys, marker=marker, ls=ls, color=colour, ms=4.5, lw=1.2,
                mfc="white", mew=1.0, label=kind)
    bx.axhline(0, color=INK, lw=0.8)
    bx.set_xlabel("pool length, km")
    bx.set_ylabel(r"median $\delta$, %")
    bx.legend(loc="upper right")
    panel(bx, "b", "the sign is not stable")
    return fig


# --------------------------------------------------------------- fig: moves

def fig_moves():
    """What excitation the record contains, on the archive's own 0.01 ft grid."""
    need(os.path.join(TABLES, "gate_step_histogram.csv"),
         os.path.join(RESULTS, "archive_diagnostics.json"))
    rows = read_csv(os.path.join(TABLES, "gate_step_histogram.csv"))
    mov = read_json(os.path.join(RESULTS, "archive_diagnostics.json"))["gate_movement"]
    steps = np.array([int(r["step_hundredths_ft"]) for r in rows]) / 100.0
    counts = np.array([int(r["count"]) for r in rows], dtype=float)

    fig, ax = plt.subplots(figsize=(WIDTH, 52 * MM), layout="constrained")
    keep = (steps >= -1.0) & (steps <= 1.0)
    ax.bar(steps[keep], counts[keep], width=0.01, color=BLUE, lw=0)
    for sign in (-1, 1):
        ax.axvline(sign * mov["threshold_ft"], color=VERMILLION, lw=1.0, ls="--")
    ax.text(mov["threshold_ft"], counts.max() * 0.5,
            f"  ±{mov['threshold_ft']} ft: the move threshold\n"
            f"  {mov['above_threshold']:,} of {mov['moved']:,} movements exceed it",
            fontsize=7, color=VERMILLION, va="top")
    ax.set_yscale("log")
    ax.set_xlabel("gate movement between consecutive 15-minute samples, ft")
    ax.set_ylabel("count")
    outside = int(counts[~keep].sum())
    ax.set_title(f"{mov['pairs']:,} consecutive pairs; {outside:,} movements "
                 f"larger than 1 ft are off the axis",
                 loc="left", fontsize=8, pad=3)
    return fig


# ----------------------------------------------------------------- fig: grid

def fig_grid():
    """The one-second timestamp offset, and what it costs.

    Discharge at 09522700 is stamped a second early through parts of 2023 and
    2024, so those readings are not simultaneous with stage and gate opening and
    drop out of any four-series analysis. The archive is left exactly as
    published; this is the price of that decision, as a number.
    """
    need(os.path.join(PACKAGE, "grid_diagnostics.csv"))
    rows = sorted(read_csv(os.path.join(PACKAGE, "grid_diagnostics.csv")),
                  key=lambda r: (r["site"] != "09522700", r["site"],
                                 int(r["year"])))
    labels = [f"{r['site']}\n{r['year']}" for r in rows]
    have = np.array([int(r["rows_with_all_four"]) for r in rows]) / 1000.0
    snap = np.array([int(r["rows_with_all_four_if_snapped_2s"])
                     for r in rows]) / 1000.0
    xs = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(WIDTH, 52 * MM), layout="constrained")
    ax.bar(xs, have, width=0.6, color=BLUE, lw=0, label="as published")
    ax.bar(xs, snap - have, width=0.6, bottom=have, color=VERMILLION, lw=0,
           label="recoverable by snapping within 2 s")
    for x, h, s in zip(xs, have, snap):
        if s - h > 0.05:
            ax.text(x, s + 0.4, f"+{1000 * (s - h):.0f}", ha="center",
                    fontsize=6.5, color=VERMILLION)
    ax.set_xticks(xs, labels, fontsize=6)
    ax.set_ylabel(r"timestamps with all four, $10^3$")
    ax.set_ylim(0, 44)
    ax.legend(loc="upper center", ncol=2)
    return fig


# ---------------------------------------------------------------- fig: rating

def fig_rating():
    """How tightly the rating holds its coefficient -- and what pooling hides.

    This is NOT a measurement of the discharge coefficient. kappa comes from the
    continuous discharge series, which is the rating's own output, so flatness
    here says the rating used one coefficient. The picture is drawn because the
    size of that flatness is the evidence: 0.01 per cent across three decades of
    relative opening is arithmetic, not hydraulics. The pooled bins are shown in
    grey to make visible what binning across a rating change does.
    """
    need(os.path.join(TABLES, "discharge_coefficient_bins.csv"),
         os.path.join(RESULTS, "discharge_coefficient.json"))
    rows = read_csv(os.path.join(TABLES, "discharge_coefficient_bins.csv"))
    dc = read_json(os.path.join(RESULTS, "discharge_coefficient.json"))

    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 56 * MM), layout="constrained")
    keys = [("a/dh (relative opening)", r"relative opening $a/\Delta h$", True),
            ("dh (head difference, m)", r"head difference $\Delta h$, m", False)]
    for axis, (key, xlabel, logx), letter in zip(axes, keys, "ab"):
        for period, colour, marker, ls, z in (
                ("pooled", FAINT, "s", "-", 2),
                ("before", BLUE, "o", "--", 3),
                ("after", VERMILLION, "^", ":", 3)):
            sel = [r for r in rows if r["period"] == period
                   and r["binned_by"] == key]
            if not sel:
                continue
            xs = [float(r["x_median"]) for r in sel]
            ys = [float(r["kappa_median"]) for r in sel]
            axis.plot(xs, ys, marker=marker, ls=ls, color=colour, ms=4,
                      lw=1.1, mfc="white", mew=0.9, zorder=z, label=period)
        if logx:
            axis.set_xscale("log")
        axis.set_xlabel(xlabel)
        panel(axis, letter)
    axes[0].set_ylabel(r"$\kappa$ per decile,  m")
    worst = max(dc["spread_by_relative_opening"], dc["spread_by_head_difference"])
    axes[0].legend(loc="center left", title=None)
    axes[1].text(0.97, 0.5,
                 f"within a period the ten decile\nmedians span "
                 f"{100 * worst:.2f}%; pooling across\nthe rating change "
                 f"inflates that\n{dc['pooled_inflation']:.0f}-fold",
                 transform=axes[1].transAxes, fontsize=7, color=INK,
                 ha="right", va="center")
    return fig


# -------------------------------------------------------------- fig: structure

def fig_structure():
    """The structure, its two gauges, and what each published series measures.

    Drawn here rather than by hand so that no figure in the manuscript is
    outside the repository: a schematic that only exists as a drawing file is a
    figure a reader cannot regenerate.
    """
    fig, ax = plt.subplots(figsize=(WIDTH, 52 * MM), layout="constrained")
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.35, 4.3)

    bed, sill = 0.0, 0.0
    h1, h2, gate_x, gate_w, a = 3.1, 2.05, 5.0, 0.16, 0.85
    water = "#cfe3f2"

    ax.fill_between([0.2, gate_x - gate_w / 2], bed, h1, color=water, lw=0)
    ax.fill_between([gate_x + gate_w / 2, 9.8], bed, h2, color=water, lw=0)
    ax.plot([0.2, 9.8], [bed, bed], color=INK, lw=1.4)
    ax.add_patch(matplotlib.patches.Rectangle(
        (gate_x - gate_w / 2, sill + a), gate_w, 4.2 - (sill + a),
        facecolor="#9aa4ad", edgecolor=INK, lw=0.8))
    ax.annotate("", xy=(gate_x, sill), xytext=(gate_x, sill + a),
                arrowprops=dict(arrowstyle="<->", lw=0.8, color=INK))
    ax.text(gate_x + 0.18, sill + a / 2, "$a$", fontsize=9, va="center")
    ax.text(gate_x + 0.42, sill + a / 2, "45592", fontsize=6.5,
            color=MUTED, va="center")

    for x, lev, name, code, colour in ((2.4, h1, "$H_1$ headwater", "00065", BLUE),
                                       (7.9, h2, "$H_2$ tailwater", "00065",
                                        VERMILLION)):
        ax.plot([x, x], [bed, lev + 0.75], color=colour, lw=1.1)
        ax.plot([x - 0.28, x + 0.28], [lev, lev], color=colour, lw=1.6)
        ax.plot(x, lev, "v", ms=5, color=colour)
        ax.text(x, lev + 0.9, f"{name}\n{code}", fontsize=7, ha="center",
                color=INK)
    ax.annotate("", xy=(gate_x - 0.75, h1), xytext=(gate_x - 0.75, h2),
                arrowprops=dict(arrowstyle="<->", lw=0.8, color=INK))
    ax.text(gate_x - 0.68, (h1 + h2) / 2, r"$\Delta h$", fontsize=9, va="center")

    ax.annotate("", xy=(1.9, 1.0), xytext=(0.6, 1.0),
                arrowprops=dict(arrowstyle="-|>", lw=1.1, color=INK))
    ax.text(1.25, 1.18, "flow", fontsize=7, ha="center", color=INK)
    # Everything that is not part of the drawing goes below the bed line, where
    # nothing can collide with a gauge label or the water surface.
    # Q belongs beside the water it describes, in the empty upper right; the
    # provenance lines go under the bed, where nothing can collide with them.
    # Three caption rows under the bed line. Anything placed inside the drawing
    # ends up on top of a gauge label sooner or later; below it, nothing can.
    ax.text(0.2, -0.28,
            "USGS 09522700, Wellton-Mohawk Main Canal near Yuma, AZ",
            fontsize=7, ha="left", va="top", color=MUTED)
    ax.text(0.2, -0.60, "two gates, averaged opening; sill elevation not "
                        "identifiable from the archive",
            fontsize=7, ha="left", va="top", color=MUTED)
    ax.text(0.2, -0.92, "$Q$ discharge, 00060 — a RATING OUTPUT, computed from "
                        "$a$, $H_1$ and $H_2$",
            fontsize=7, ha="left", va="top", color=GREEN)
    return fig


# ------------------------------------------------------------------ registry

# number, function, one-line purpose, and the manuscript section the figure
# belongs to. The section is the one thing here that cannot be measured -- it is
# an editorial decision -- so it is declared, and Appendix A reads it from here
# rather than from a second list of its own.
CATALOGUE = {
    "kappa": (1, fig_kappa, "kappa is a rating output, not a measurement",
              "Section 3.1"),
    "gaugings": (2, fig_gaugings, "benchmark gate law against 77 gaugings",
                 "Section 3.2"),
    "storage": (3, fig_storage, "A_s is not identifiable from the archive",
                "Section 3.3"),
    "census": (4, fig_census, "why the folds are 2018-2025",
               "Section 2.3"),
    "envelope": (5, fig_envelope, "modelling error over the operating envelope",
                 "Section 3.4"),
    "control": (6, fig_control, "closed-loop cost, and its unstable sign",
                "Section 3.4"),
    "moves": (7, fig_moves, "gate movements on the archive's own grid",
              "Section 2.2"),
    "grid": (8, fig_grid, "the one-second timestamp offset and its cost",
             "Section 2.4"),
    "rating": (9, fig_rating, "how tightly the rating holds its coefficient",
               "Section 3.1"),
    "structure": (10, fig_structure, "the structure and its published series",
                  "Section 2.1"),
}

PROVENANCE = os.path.join(RESULTS, "figure_provenance.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append", choices=sorted(CATALOGUE),
                    help="draw just this figure; may be repeated")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for name, (n, _fn, what, _sec) in sorted(CATALOGUE.items(),
                                                 key=lambda kv: kv[1][0]):
            print(f"  fig{n:02d}  {name:<10s} {what}")
        return 0

    style()
    resolved = matplotlib.font_manager.FontProperties(
        family=plt.rcParams["font.serif"][0]).get_name()
    actual = matplotlib.font_manager.findfont(
        matplotlib.font_manager.FontProperties(family="serif"))
    if "times" not in os.path.basename(actual).lower():
        print(f"!! Times New Roman not found; matplotlib chose "
              f"{os.path.basename(actual)}.\n   The figures will not match the "
              f"manuscript's typeface. Install the font or\n   accept the "
              f"mismatch deliberately -- do not let it pass unnoticed.\n")

    os.makedirs(FIGURES, exist_ok=True)
    wanted = args.only or sorted(CATALOGUE, key=lambda k: CATALOGUE[k][0])
    manifest = []
    for name in sorted(wanted, key=lambda k: CATALOGUE[k][0]):
        number, fn, what, section = CATALOGUE[name]
        OPENED.clear()
        fig = fn()
        path = os.path.join(FIGURES, f"fig{number:02d}_{name}.png")
        fig.savefig(path, dpi=DPI)
        plt.close(fig)
        manifest.append({"number": number, "name": name, "section": section,
                         "what": what, "sources": sorted(OPENED)})
        w_in, h_in = fig.get_size_inches()
        print(f"fig{number:02d}_{name}.png  {w_in * 25.4:.1f} × "
              f"{h_in * 25.4:.1f} mm   {int(w_in * DPI)} × {int(h_in * DPI)} px "
              f"@ {DPI} dpi   — {what}")
    print(f"\nwritten to {os.path.relpath(FIGURES, ROOT)}; insert at 100% scale")

    # Only a full run may write the provenance file: a partial one would leave
    # Appendix A describing a manuscript with three figures in it.
    if not args.only:
        with open(PROVENANCE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"figures": manifest}, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"provenance recorded in {os.path.relpath(PROVENANCE, ROOT)} "
              f"-- Appendix A is built from it, not from a second list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
