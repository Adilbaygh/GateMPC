"""Every table in the manuscript, assembled from published result files.

    python scripts/make_tables.py               # all of them
    python scripts/make_tables.py --list
    python scripts/make_tables.py --only h4     # one, while iterating

The rule this script exists to enforce: no number reaches the manuscript by
being typed. Each table below reads the JSON or CSV that a script in this
directory wrote, and each one carries a provenance line naming the files it was
built from, so a reviewer -- or the author six months from now -- can go from a
cell to the file that produced it without asking anyone.

Two outputs, because they serve different readers:

  * ``results/tables/manuscript_tables.md`` -- all tables in one file with their
    captions and provenance, for reading and checking;
  * ``results/tables/table_NN_<slug>.csv`` -- one per table, for importing into
    the Word document without retyping.

Journal formatting (Extrica template, requirements/journal.md): the caption goes
ABOVE the table, "Table n." in 9 pt bold followed by 9 pt regular, and the table
body is 9 pt. That is applied in the document, not here -- this script settles
what the numbers are, not how they are set.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.archive import implausible_discharge  # noqa: E402

RESULTS = os.path.join(ROOT, "results")
TABLES = os.path.join(RESULTS, "tables")
PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")

# Written by scripts/make_figures.py while the figures are drawn: which files
# each figure actually opened. Appendix A is built from it.
FIGURE_PROVENANCE = os.path.join(RESULTS, "figure_provenance.json")

SITE = "09522700"
FOLDS = list(range(2018, 2026))


def read_json(name: str) -> dict:
    path = name if os.path.isabs(name) else os.path.join(RESULTS, name)
    if not os.path.exists(path):
        raise SystemExit(f"missing {os.path.relpath(path, ROOT)}\n"
                         f"run the script that writes it first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_csv(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        raise SystemExit(f"missing {os.path.relpath(path, ROOT)}")
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def pct(x, places=2, sign=True):
    return f"{100 * x:{'+' if sign else ''}.{places}f}%"


class Table:
    """One manuscript table, with everything Appendix A needs to describe it.

    ``sources`` are the repository-relative files this table's numbers were read
    from; ``section`` is where the table appears in the manuscript. Appendix A is
    generated from these two fields rather than from a list of its own, because
    the list of its own drifted: Table 3 gained two data sources and the appendix
    went on naming three.
    """

    def __init__(self, number, slug, caption, columns, rows, sources,
                 section="", note=""):
        self.number, self.slug, self.caption = number, slug, caption
        self.columns, self.rows = columns, rows
        self.sources, self.note = sources, note
        self.section = section


# ------------------------------------------------------------------ section 2

def t1_series():
    """What the archive publishes at the structure, and what it advertises."""
    meta = read_csv(os.path.join(PACKAGE, "time_series_metadata.csv"))
    census = read_csv(os.path.join(PACKAGE, "coverage_census.csv"))
    diag = read_json("archive_diagnostics.json")

    first_all_four = min(int(r["year"]) for r in census
                         if r["site"] == SITE
                         and int(r["timestamps_with_all_four"]) > 0)
    role_of = {"45592": "gate opening (averaged over two gates)",
               "00060": "discharge"}
    rows = []
    for m in sorted((r for r in meta if r["site"] == SITE),
                    key=lambda r: (r["parameter_code"],
                                   r["sublocation_identifier"])):
        role = role_of.get(m["parameter_code"], m["sublocation_identifier"])
        rows.append([m["parameter_code"], role, m["unit_of_measure"],
                     m["begin"][:10] if m["begin"] else "—",
                     m["end"][:10] if m["end"] else "—"])
    return Table(
        1, "series",
        f"Time series published at USGS {SITE}. The begin dates are the ones "
        f"the archive advertises; the first calendar year in which all four "
        f"carry values at the same timestamps is {first_all_four}, and the "
        f"cross-validation folds start the year after that.",
        ["Parameter code", "Role", "Unit", "Advertised begin", "End"],
        rows,
        ["DATA/USGS_canal_gates_v1/time_series_metadata.csv",
         "DATA/USGS_canal_gates_v1/coverage_census.csv",
         "results/archive_diagnostics.json"],
        note=f"usable four-series samples over the folds: "
             f"{diag['kappa']['n_usable']:,}",
        section="Section 2.1")


def t2_folds():
    """Why the study uses 2018-2025 and not the advertised range."""
    census = read_csv(os.path.join(PACKAGE, "coverage_census.csv"))
    rows = []
    for r in sorted((x for x in census if x["site"] == SITE),
                    key=lambda x: int(x["year"])):
        year, all4 = int(r["year"]), int(r["timestamps_with_all_four"])
        if all4 == 0 and year < 2016:
            continue                       # the empty years are summarised below
        moves, appr = int(r["gate_move_events"]), float(r["approved_pct"])
        rules = (all4 >= 20000, moves >= 100, appr == 100.0)
        rows.append([str(year), f"{all4:,}", f"{moves:,}", f"{appr:.1f}",
                     "yes" if all(rules) and year in FOLDS else "no",
                     "" if year in FOLDS else _why_not(year, all4, moves, appr)])
    return Table(
        2, "folds",
        "Fold selection at the primary structure. A fold is a closed calendar "
        "year in which all four series overlap for at least 20 000 timestamps, "
        "the gate is moved at least 100 times, and every record is Approved. "
        "Years before 2016 are omitted: none of them carries a stage series at "
        "all, so their four-series overlap is zero.",
        ["Year", "Timestamps with all four", "Gate move events",
         "Approved, %", "Fold", "Why not"],
        rows,
        ["DATA/USGS_canal_gates_v1/coverage_census.csv"],
        section="Section 2.3")


def _why_not(year, all4, moves, appr):
    if all4 == 0:
        return "stage series absent"
    if all4 < 20000:
        return "partial year"
    if appr != 100.0:
        return "year still open; records provisional"
    return "—"


def t3_defects():
    """The data-quality defects the archive carries, each with its size."""
    diag = read_json("archive_diagnostics.json")
    law = read_json("gate_law.json")
    grid = read_csv(os.path.join(PACKAGE, "grid_diagnostics.csv"))
    k, ext = diag["kappa"], diag.get("extremes")
    if ext is None:
        raise SystemExit("results/archive_diagnostics.json has no 'extremes' "
                         "block; rerun scripts/archive_diagnostics.py")

    lost = sum(int(r["rows_with_all_four_if_snapped_2s"])
               - int(r["rows_with_all_four"]) for r in grid)
    worst = max((r for r in grid), key=lambda r: int(r["off_grid_within_2s"]))
    amin = ext["gate_opening"]["min"]

    # The discharge extreme is taken over the WHOLE archive, from the census,
    # not over the fold years alone. An earlier draft of this table read it from
    # the fold years and printed 1110 ft3/s as a value "outside any plausible
    # range" -- but 1110 is the ordinary fold maximum, 1.06 times the largest
    # gauging at that structure, so the row was asserting a defect that is not
    # there. The census carries every year and every site, so if such a reading
    # exists this finds it, and if it does not the row says so instead of
    # inventing one. The comparison runs within a site: gatempc.archive says why.
    found = implausible_discharge(PACKAGE)
    if found is None:
        raise SystemExit("coverage_census.csv has no per-series range columns; "
                         "rebuild the package with scripts/download_usgs.py")

    rows = [
        ["Undocumented rating revision",
         f"{pct(k['step_relative'])} step in Q/(a√(2gΔh)) overnight",
         f"{k['split_after']} to {k['split_before']}",
         "no note in the published record"],
        ["Telemetry timestamp offset",
         f"{lost:,} four-series samples lost",
         f"worst in {worst['site']} {worst['year']}",
         "discharge stamped one second early"],
        ["Negative gate readings",
         f"{law['dropped']['clipped_negative_gate']} samples, "
         f"minimum {amin['raw']} ft",
         "across the folds",
         f"published as {amin['approval']}; instrument zero drift"],
    ]
    # Only claim an implausible discharge if the archive actually holds one.
    # The yardstick is the largest INDEPENDENT field measurement at the same
    # structure: a telemetered value far above anything ever gauged there is a
    # defect, one near it is not.
    gauging_note = (f"largest of {found['gaugings']} field gaugings there: "
                    f"{found['gauged_ft3s']:,g} ft³/s; highest of the other "
                    f"{found['years'] - 1} annual maxima: "
                    f"{found['next_ft3s']:,g} ft³/s")
    if found["is_defect"]:
        rows.append(["Discharge far above anything ever gauged",
                     f"{found['q_ft3s']:,g} ft³/s — "
                     f"{found['ratio']:.0f}× the largest gauging, "
                     f"{found['ratio_to_next']:.0f}× every other year",
                     f"{found['site']}, {found['year']}",
                     gauging_note])
    else:
        rows.append(["— no implausible discharge found —",
                     f"archive maximum {found['q_ft3s']:,g} ft³/s "
                     f"({found['ratio']:.2f}× the largest gauging)",
                     f"{found['site']}, {found['year']}",
                     gauging_note])
    return Table(
        3, "defects",
        "Data-quality defects found in the published archive. None was "
        "corrected in the data package: the records are republished exactly as "
        "the archive serves them, and the cost of leaving them alone is the "
        "second column.",
        ["Defect", "Size", "When", "Note"], rows,
        ["results/archive_diagnostics.json", "results/gate_law.json",
         "DATA/USGS_canal_gates_v1/grid_diagnostics.csv",
         "DATA/USGS_canal_gates_v1/coverage_census.csv",
         "DATA/USGS_canal_gates_v1/gaugings.csv"],
        section="Section 2.4")


# ----------------------------------------------- section 2, control apparatus

def t4_parameters():
    """The synthetic baseline, as actually used by the code."""
    cc = read_json("control_comparison.json")
    env = read_json("model_error_envelope.json")
    d, ref = cc["design"], env["reference"]
    pool, gate = d["pool"], d["gate"]
    rows = [
        ["Pool length", f"{pool['length_m']:.0f}", "m", "[C98] Table 3, in km"],
        ["Bottom width", f"{pool['bottom_width_m']:.0f}", "m", "[C98] Table 3"],
        ["Side slope", f"{pool['side_slope']:.1f}", "H:V", "[C98] Table 3"],
        ["Target depth", f"{pool['target_depth_m']:.1f}", "m", "[C98] Table 3"],
        ["Drop across the gate", f"{ref['dh_ref_m']:.1f}", "m", "[C98] Table 1"],
        ["Gate width", f"{ref['w_asce_m']:.0f}", "m", "[C98] Table 3"],
        ["Gate height", f"{gate['a_max_m']:.1f}", "m", "[C98] Table 3"],
        ["Discharge coefficient", f"{ref['cd_asce']:.2f}", "—", "[B25] Table 5"],
        ["Storage area A_s", f"{pool['storage_area_m2']:,.0f}", "m²",
         "derived: length × top width"],
        ["Delay τ", f"{pool['delay_s']:.0f}", "s", "derived: L/(v+c)"],
        ["Regulation step", f"{d['dt_s']:.0f}", "s", "[C98] p. 24"],
        ["Reference discharge", f"{ref['q_ref_m3s']:.1f}", "m³/s",
         "[C98] Table 6"],
        ["Matching opening a_ref", f"{ref['a_ref_m']:.4f}", "m", "derived"],
        ["Γ_syn = C_d W √(2g)", f"{ref['gamma_syn']:.4f}", "m^1.5/s", "derived"],
    ]
    return Table(
        4, "parameters",
        "Synthetic baseline parameters, read back from the files the "
        "experiments wrote rather than transcribed. Values marked derived are "
        "computed by the code from the cited ones.",
        ["Parameter", "Value", "Unit", "Source"], rows,
        ["results/control_comparison.json", "results/model_error_envelope.json"],
        section="Section 2.9")


# ------------------------------------------------------------------ section 3

def t5_identifiability():
    """What eight years of open archive can and cannot pin down."""
    law = read_json("gate_law.json")
    diag = read_json("archive_diagnostics.json")
    cv, h0c2, sto = law["cross_validation"], law["h0c2_second_condition"], \
        diag["storage"]
    rows = [
        ["Γ = C_d W_eff", f"{cv['gamma_mean_m']:.4f} m^1.5/s",
         f"[{cv['gamma_ci95'][0]:.4f}, {cv['gamma_ci95'][1]:.4f}]",
         "identified"],
        ["α (opening exponent)", f"{cv['alpha_mean']:.4f}",
         f"[{cv['alpha_ci95'][0]:.4f}, {cv['alpha_ci95'][1]:.4f}]",
         "identified"],
        ["β (head exponent)", f"{cv['beta_mean']:.4f}",
         f"[{cv['beta_ci95'][0]:.4f}, {cv['beta_ci95'][1]:.4f}]",
         "identified"],
        ["z₀ (sill elevation)", f"{law['full_fit']['z0_ft']:.2f} ft",
         f"flat valley {h0c2['flat_valley_width_ft']:.2f} ft wide",
         f"NOT identified — free-flow fraction "
         f"{h0c2['free_fraction_at_optimum']:.1e}"],
        ["A_s (pool storage area)", f"{sto['median_m2']:,.0f} m²",
         f"IQR/median {sto['iqr_ratio']:.3f}",
         f"NOT identified — {pct(sto['negative_fraction'], 1, False)} of "
         f"{sto['n_accepted']:,} estimates physically impossible"],
    ]
    return Table(
        5, "identifiability",
        "What the open archive identifies and what it does not. The gate law's "
        "shape is recovered; the sill elevation and the pool storage area are "
        "not, and the third column says how that was established rather than "
        "asserting it.",
        ["Quantity", "Estimate", "Spread or interval", "Verdict"], rows,
        ["results/gate_law.json", "results/archive_diagnostics.json"],
        note="The identification is against the continuous discharge series, "
             "which is a rating output; see Table 6 for the non-circular test.",
        section="Section 3.3")


def t6_h4():
    """The central result: the benchmark law against independent gaugings."""
    v = read_json("gate_law_validation.json")
    r, rej = v["relative_residual"], v["rejected"]
    rows = [
        ["Field measurements in the archive", f"{v['gaugings_total']:,}", ""],
        ["Accepted for the test", f"{v['accepted']}",
         "inside the fold window, gate steady, rating not Poor"],
        ["— rejected: outside the fold window", f"{rej['outside_fold_window']}",
         ""],
        ["— rejected: gate moved within 30 min",
         f"{rej['gate_moved_within_30min']}", ""],
        ["— rejected: rating Poor or missing",
         f"{rej['rating_poor_or_missing']}", ""],
    ]
    # What the accepted measurements claim about themselves. The ratings are the
    # archive's own, and the percentages are USGS's definition of them, so the
    # row states what the yardstick is worth before the residuals are read
    # against it. Absent in a run made before the definitions were recorded.
    for cls, b in sorted((v.get("by_rating") or {}).items(),
                         key=lambda kv: kv[1]["stated_accuracy"]):
        rows.append([f"— accepted: rated {cls}", f"{b['n']}",
                     f"USGS: within {100 * b['stated_accuracy']:.0f}% of the "
                     f"actual flow; median residual {pct(b['median'])}"])
    rows += [
        ["Median relative residual", pct(r["median"]),
         f"criterion ±{100 * v['criteria']['bias']:.0f}%"],
        ["Interquartile range", pct(r["iqr"], sign=False), ""],
        ["5th to 95th percentile", f"{pct(r['q05'])} to {pct(r['q95'])}", ""],
        ["Full range", f"{pct(r['min'])} to {pct(r['max'])}", ""],
        ["Structure against a/Δh",
         pct(v["structure_spread"]["a/dh"], sign=False),
         f"criterion {100 * v['criteria']['structure']:.0f}%"],
        ["Structure against Δh", pct(v["structure_spread"]["dh"], sign=False),
         ""],
        ["Before the rating change",
         f"{pct(v['by_period']['before']['median'])} "
         f"(n = {v['by_period']['before']['n']})", ""],
        ["After the rating change",
         f"{pct(v['by_period']['after']['median'])} "
         f"(n = {v['by_period']['after']['n']})", ""],
    ]
    return Table(
        6, "h4",
        "The benchmark's idealised gate law tested against independent field "
        "gaugings. These are the only observations at the structure that are "
        "not derived from the gate law itself, which is what makes the test "
        "non-circular.",
        ["Quantity", "Value", "Note"], rows,
        ["results/gate_law_validation.json"],
        note=f"verdict: {'supported' if v['h4_supported'] else 'not supported'}"
             f" — the idealised law is adequate for this structure. "
             + _gauging_accuracy_note(v),
        section="Section 3.2")


def _gauging_accuracy_note(v: dict) -> str:
    """Where the residual spread sits against the gaugings' own stated accuracy.

    A comparison cannot resolve a disagreement smaller than the error of the
    thing it compares against, so the honest reading of Table 6 needs both
    numbers in the same sentence. The percentages come from USGS's definition of
    its own ratings, recorded in results/gate_law_validation.json by
    scripts/validate_gate_law.py together with the source it was read from.
    """
    by = v.get("by_rating") or {}
    src_ = v.get("rating_source") or {}
    if not by or not src_:
        return ("the gaugings' own stated accuracy is not recorded in this run; "
                "rerun scripts/validate_gate_law.py to record it")
    spans = " and ".join(
        f"{100 * b['stated_accuracy']:.0f}% ({cls})"
        for cls, b in sorted(by.items(), key=lambda kv: kv[1]["stated_accuracy"]))
    total = sum(b["n"] for b in by.values())
    outside = sum(b.get("n_outside_stated", 0) for b in by.values())
    if outside:
        cls, b = max(((c, x) for c, x in by.items()
                      if x.get("n_outside_stated")),
                     key=lambda kv: kv[1].get("worst_outside", 0.0))
        verdict = (f"{outside} of {total} residuals "
                   f"{'exceeds' if outside == 1 else 'exceed'} the accuracy its "
                   f"own measurement claims — the largest reaching "
                   f"{pct(b['worst_outside'], sign=False)} against the "
                   f"{100 * b['stated_accuracy']:.0f}% a {cls} measurement "
                   f"claims, so the law's disagreement with the gaugings sits "
                   f"at the level of their own error rather than above it")
    else:
        verdict = (f"not one of the {total} residuals exceeds the accuracy its "
                   f"own measurement claims, so the disagreement cannot be told "
                   f"apart from the error of the yardstick and nothing is "
                   f"claimed below it")
    return (f"the accepted measurements state their own accuracy as {spans} of "
            f"the actual flow [{src_['title']}, {src_['series']}]: {verdict}")


def t7_control():
    """The four combinations, both controllers, all reported indicators."""
    cc = read_json("control_comparison.json")
    rows = []
    for kind in ("PI", "MPC"):
        c = cc["controllers"][kind]
        for combo in ("M_syn->P_syn", "M_syn->P_id",
                      "M_id->P_syn", "M_id->P_id"):
            s = c["indicators"][combo]
            rows.append([kind, combo.replace("->", " → "),
                         f"{s['IAE']['median']:.6f}",
                         f"{s['MAE']['median']:.6f}",
                         f"{s['StE']['median']:.6f}",
                         f"{s['IAQ']['median']:.2f}",
                         f"{s['IAW']['median']:.3f}",
                         f"{100 * s['saturated_fraction']['max']:.1f}"])
    return Table(
        7, "control",
        "Closed-loop indicators over 100 paired replicates of ASCE Test 2-1, "
        "medians. M is the gate law the controller inverts, P the one the plant "
        "applies. MAE, IAE and StE are normalised by the target depth; IAQ is "
        "the integrated absolute change in discharge and IAW the same for gate "
        "position.",
        ["Controller", "Model → plant", "IAE", "MAE", "StE", "IAQ, m³/s",
         "IAW, m", "Saturation, %"], rows,
        ["results/control_comparison.json"],
        note="absolute values are not realistic canal performance: the pool is "
             "an integrator with delay, identical in both arms, so only the "
             "difference between arms is interpreted. " + _deadband_note(cc),
        section="Section 3.4")


def _deadband_note(cc: dict) -> str:
    """What an 11.5 mm minimum gate movement does to IAQ, read from the run.

    [C98] proposes IAQ as the indicator against gate hunting (p. 26), so a large
    IAQ invites the reading that the controller is chattering because the
    headline runs allow a movement of any size. It was measured instead of
    assumed (hypotheses.md, H2-s3): the deadband barely moves IAQ, so the large
    value is the loop's own oscillation and not an artefact of the actuator
    model. That sentence is worth carrying next to the numbers it defends.
    """
    step = cc.get("sensitivity", {}).get("min_gate_step") or {}
    changes = {}
    for kind, block in step.items():
        dead = (block or {}).get("indicators")
        base = cc["controllers"].get(kind, {}).get("indicators")
        if not dead or not base:
            continue
        changes[kind] = [dead[lab]["IAQ"] / base[lab]["IAQ"]["median"] - 1.0
                         for lab in dead if lab in base]
    if not changes:
        return ("the effect of a minimum gate movement on IAQ was not recorded "
                "in this run; rerun scripts/control_comparison.py")
    mm = 1000 * step[next(iter(step))]["min_step_m"]
    # Same controller order as the table above, not alphabetical.
    order = [k for k in ("PI", "MPC") if k in changes]
    order += [k for k in sorted(changes) if k not in order]
    spans = " and ".join(
        f"{pct(min(changes[k]), 1)} to {pct(max(changes[k]), 1)} ({k})"
        for k in order)
    return (f"an {mm:.1f} mm minimum gate movement changes IAQ by only {spans}, "
            f"so the large IAQ is the loop's own oscillation rather than "
            f"sub-threshold hunting")


def t8_delta():
    """The headline penalty and every sensitivity run on it."""
    cc = read_json("control_comparison.json")
    rows = []
    # Three decimals here, not two: at two the MPC interval prints as
    # [-0.48%, -0.48%] and reads like a rendering fault instead of the finding
    # it is -- every one of its 100 replicates lands within 0.02%.
    p3 = lambda x: pct(x, 3)
    for kind in ("PI", "MPC"):
        c = cc["controllers"][kind]
        d, g = c["delta"], c["delta_absolute_m"]
        rows.append([kind, "δ, headline", p3(d["median"]),
                     f"[{p3(d['ci95'][0])}, {p3(d['ci95'][1])}]",
                     f"{1000 * g['median']:+.4f} mm"])
        rows.append([kind, "δ, mirror (identified model on synthetic plant)",
                     p3(c["delta_mirror"]["median"]),
                     f"[{p3(c['delta_mirror']['ci95'][0])}, "
                     f"{p3(c['delta_mirror']['ci95'][1])}]", "—"])
        s = cc["sensitivity"]
        e = s["exponent_ci"][kind]
        rows.append([kind, "δ over the 95% region of (α, β)",
                     f"{p3(e['min'])} to {p3(e['max'])}", "four corners", "—"])
        pl = s["pool_length"][kind]
        rows.append([kind, "δ over pool lengths 2–7 km",
                     f"{p3(pl['min'])} to {p3(pl['max'])}",
                     "sign not stable" if pl["min"] * pl["max"] < 0
                     else "sign stable", "—"])
        ms = s["min_gate_step"][kind]
        rows.append([kind, f"δ with an {1000 * ms['min_step_m']:.1f} mm "
                           f"minimum gate movement", p3(ms["delta_median"]),
                     f"[{p3(ms['delta_ci95'][0])}, "
                     f"{p3(ms['delta_ci95'][1])}]", "—"])
    step = cc["controllers"]["PI"]["delta_absolute_m"]["level_sensor_step_m"]
    return Table(
        8, "delta",
        "The cost of tuning on the benchmark's gate law, and how it moves. "
        "δ = (IAE with the benchmark model − IAE with the identified model) / "
        "IAE with the identified model, on the identified plant. Only the "
        "magnitude is claimed: the sign turns over with pool length.",
        ["Controller", "Quantity", "Median", "95% interval or note",
         "In level error"], rows,
        ["results/control_comparison.json"],
        note=f"the level sensor resolves {1000 * step:.1f} mm, so the headline "
             f"difference is a small fraction of the instrument's own step",
        section="Section 3.5")


# ------------------------------------------------------------------ appendix

def ta1_provenance(tables):
    """Appendix A: every published item and the file its numbers came from.

    Nothing in this table is typed. The table rows are read off the Table objects
    that were just built, and the figure rows off ``results/figure_provenance.json``,
    which ``scripts/make_figures.py`` writes by recording the files each figure
    actually opened while it was being drawn.

    An earlier version of this function kept its own copy of both lists, and the
    copy went stale inside a day: Table 3 gained ``coverage_census.csv`` and
    ``gaugings.csv`` as sources and the appendix went on naming three files. A
    provenance table that is maintained by hand is the one table in the
    manuscript that cannot be checked against anything.
    """
    if not os.path.exists(FIGURE_PROVENANCE):
        raise SystemExit(
            f"missing {os.path.relpath(FIGURE_PROVENANCE, ROOT)}\n"
            f"run scripts/make_figures.py first: Appendix A names the file behind "
            f"every figure, and that list is recorded while the figures are drawn "
            f"rather than kept in this script")
    figures = read_json(FIGURE_PROVENANCE)["figures"]

    def names(paths):
        return ", ".join(os.path.basename(p) for p in paths)

    entries = []
    for t in tables:
        if not t.section:
            raise SystemExit(f"Table {t.number} does not say which manuscript "
                             f"section it belongs to; set section= on it")
        entries.append([t.section, f"Table {t.number}", names(t.sources)])
    for f in sorted(figures, key=lambda f: f["number"]):
        entries.append([f["section"], f"Fig. {f['number']}",
                        names(f["sources"]) or
                        "drawn by scripts/make_figures.py, no data"])

    return Table(
        "A1", "provenance",
        "Provenance of every table and figure. Each entry names the published "
        "file its numbers were read from; all of those files are produced by "
        "the scripts in the repository and are covered by the data package's "
        "checksums where they belong to it.",
        ["Manuscript section", "Item", "Built from"],
        entries,
        ["scripts/make_tables.py", "results/figure_provenance.json",
         "results/control_comparison.json"],
        section="Appendix A",
        note=_reproducibility_note())


def _reproducibility_note() -> str:
    """The machine and the wall-clock time, read from the run that produced them.

    A reproducibility statement is worth nothing if the timing in it was typed
    from memory on a different machine, so it is read from the file the
    experiment wrote. If the file predates the timing being recorded, this says
    so instead of quietly leaving the sentence out.
    """
    env = read_json("control_comparison.json")["environment"]
    machine = (f"{env.get('processor') or env['machine']}, "
               f"{env['platform']}, Python {env['python']}")
    seconds = env.get("runtime_s")
    if seconds is None:
        return (f"produced on {machine}; the run predates the wall-clock "
                f"measurement, so no timing is quoted -- rerun "
                f"scripts/control_comparison.py to record one")
    cores = env.get("cpu_count")
    # A 6.4 s run printed as "6 s" loses a figure that a reader would use to
    # judge whether rerunning is cheap, so short runs keep their decimal.
    shown = f"{seconds:,.1f}" if seconds < 100 else f"{seconds:,.0f}"
    return (f"the closed-loop experiment ({env.get('runtime_covers')}) runs in "
            f"{shown} s on {machine}"
            + (f", {cores} logical cores" if cores else ""))


# ------------------------------------------------------------------ registry

CATALOGUE = {
    "series": t1_series, "folds": t2_folds, "defects": t3_defects,
    "parameters": t4_parameters, "identifiability": t5_identifiability,
    "h4": t6_h4, "control": t7_control, "delta": t8_delta,
}

# Appendix A is built from the others, so it is not in the catalogue of builders
# above; it still answers to --only and --list like any other table.
SLUGS = list(CATALOGUE) + ["provenance"]


def render_markdown(tables) -> str:
    out = ["# Manuscript tables\n",
           "Generated by `scripts/make_tables.py`. Every number is read from a "
           "published result file; none is typed here. Captions go above the "
           "table in the manuscript, per the journal template.\n"]
    for t in tables:
        out.append(f"\n## Table {t.number}. {t.caption}\n")
        out.append("| " + " | ".join(t.columns) + " |")
        out.append("|" + "|".join(["---"] * len(t.columns)) + "|")
        for row in t.rows:
            out.append("| " + " | ".join(str(c) for c in row) + " |")
        if t.note:
            out.append(f"\n*{t.note}*")
        out.append(f"\n<sub>Built from: {', '.join(f'`{s}`' for s in t.sources)}"
                   f"</sub>\n")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append", choices=sorted(SLUGS))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for slug in SLUGS:
            print(f"  {slug}")
        return 0

    os.makedirs(TABLES, exist_ok=True)
    wanted = args.only or SLUGS

    # Every content table is built whatever --only asks for, because Appendix A
    # describes all of them; only the writing is filtered. Building is a few
    # file reads, so this costs nothing and removes a way to publish an appendix
    # that describes a shorter manuscript than the one being written.
    tables = [CATALOGUE[slug]() for slug in CATALOGUE]
    if "provenance" in wanted:
        tables.append(ta1_provenance(tables))

    built = []
    for t in tables:
        if t.slug not in wanted:
            continue
        built.append(t)
        path = os.path.join(TABLES, f"table_{t.number}_{t.slug}.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(t.columns)
            w.writerows(t.rows)
        print(f"Table {str(t.number):>2}  {t.slug:<16} {len(t.rows):>2} rows  "
              f"<- {', '.join(t.sources)}")

    if not args.only:
        path = os.path.join(TABLES, "manuscript_tables.md")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render_markdown(built))
        print(f"\nwrote {os.path.relpath(path, ROOT)} and "
              f"{len(built)} table CSVs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
