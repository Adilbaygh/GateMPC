"""Does the circularity signature repeat at a second structure? (H5)

    python scripts/second_structure.py

The methodological finding this study reports -- that the continuous discharge
published at a gated structure is a rating output rather than a measurement --
rests on one structure. One case is an anecdote; two make it a property worth
warning about. The data package already carries a second site, so the test costs
nothing but the running of it.

What is measured, fixed in hypotheses.md (H5) before this was run:

  1. kappa = Q / (a sqrt(2 g dh)) at every four-series timestamp, its daily
     medians, and the same statistic reported for the primary structure: how far
     a COMPLETE day's median sits from the median of the whole record. If the
     archive's discharge is computed from the gate equation, kappa cannot move.

  2. If kappa does move, the discharge may still be a rating output of a
     different form. So a second fit is made in logarithms,

         log Q = c0 + c1 log(dh) + c2 log(a),

     and the spread of its residuals is reported. A rating leaves residuals far
     tighter than physical scatter; an independent measurement does not.

  3. The approved share, and the headline statistic repeated on the Approved
     subset alone, because this site-year is not fully approved.

The verdict is decided by the three-way rule in hypotheses.md and is printed
here so that the run itself states which branch it fell into.

The computation lives in ``gatempc.detector`` so that the results explorer can run
the same detector on another site or on a reader's own file without a second copy of
it. Every option below defaults to the value that was fixed before the measurement,
so running this script with no arguments reproduces the published numbers; the
options exist for exploring other structures, and such a run should be written
somewhere other than results/ with --out.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.archive import load_fold  # noqa: E402
from gatempc.detector import (  # noqa: E402
    BINS, KAPPA_TIGHT, RATING_TIGHT, STRUCTURED, UNSTRUCTURED,
    DetectorError, Thresholds, analyse,
)

PACKAGE = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")
RESULTS = os.path.join(ROOT, "results")

SITE = "09428500"
YEAR = 2026


def print_kappa_block(block) -> None:
    if block is None:
        return
    print(f"  {block['label']}")
    print(f"    usable samples          {block['n_usable']:,} of {block['n_samples']:,}")
    print(f"    kappa median            {block['median_m']:.4f} m")
    print(f"    kappa spread (IQR/med)  {100 * block['spread_iqr_over_median']:.3f}%")
    if block["complete_days"]:
        print(f"    complete days           {block['complete_days']}")
        print(f"    typical day deviates by "
              f"{100 * block['typical_complete_day_deviation']:.4f}%")
        print(f"    worst day deviates by   "
              f"{100 * block['worst_complete_day_deviation']:.4f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default=SITE,
                    help=f"USGS site number in the data package (default {SITE})")
    ap.add_argument("--year", type=int, default=YEAR,
                    help=f"calendar year of the site-year file (default {YEAR})")
    ap.add_argument("--package", default=PACKAGE,
                    help="data package directory")
    ap.add_argument("--bins", type=int, default=BINS,
                    help=f"equal-count bins for the structure test (default {BINS})")
    ap.add_argument("--kappa-tight", type=float, default=KAPPA_TIGHT,
                    help=f"kappa spread below which the form is the same "
                         f"(default {KAPPA_TIGHT})")
    ap.add_argument("--rating-tight", type=float, default=RATING_TIGHT,
                    help=f"rating residual below which it is still a rating "
                         f"(default {RATING_TIGHT})")
    ap.add_argument("--out", default=os.path.join(RESULTS, "second_structure.json"),
                    help="where to write the result; point it away from results/ "
                         "when exploring another structure")
    args = ap.parse_args()

    print("=" * 74)
    print(f"H5 -- IS THE DISCHARGE AT {args.site} ALSO A RATING OUTPUT?")
    print("=" * 74)
    if not os.path.isdir(args.package):
        raise SystemExit(f"data package missing at {os.path.relpath(args.package, ROOT)};"
                         f" build it with scripts/download_usgs.py")

    samples, approvals = load_fold(args.package, args.site, args.year,
                                   with_approval=True)
    if not samples:
        raise SystemExit(f"no four-series timestamps at {args.site} in {args.year}")
    approved = [s for s, ap_ in zip(samples, approvals) if ap_]
    print(f"  four-series timestamps  {len(samples):,}")
    print(f"  fully Approved          {len(approved):,} "
          f"({100 * len(approved) / len(samples):.1f}%)")

    thresholds = Thresholds(kappa_tight=args.kappa_tight,
                            rating_tight=args.rating_tight,
                            structured_above=STRUCTURED,
                            unstructured_at_or_below=UNSTRUCTURED,
                            bins=args.bins)
    try:
        out = analyse(samples, approved, thresholds)
    except DetectorError as error:
        raise SystemExit(str(error))
    out["site"], out["year"] = args.site, args.year

    print("\n(1) kappa = Q / (a sqrt(2 g dh))")
    print_kappa_block(out["kappa_all"])
    print_kappa_block(out["kappa_approved"])

    rating = out["rating_fit"]
    print("\n(2) is the discharge a rating output of a different form?")
    print(f"    fitted on {rating['n']:,} samples")
    print(f"    log Q = {rating['c0']:+.4f} {rating['c1_dh']:+.4f} log(dh) "
          f"{rating['c2_a']:+.4f} log(a)")
    print(f"    |residual| median       "
          f"{100 * rating['median_abs_relative_residual']:.3f}%")
    print(f"    |residual| 95th pct     "
          f"{100 * rating['q95_abs_relative_residual']:.3f}%")

    structure = out["h5b"]["structure"]
    print("\n(3) H5b -- is that residual structure, or scatter?")
    for name in ("a", "dh"):
        block = structure[name]
        print(f"    binned by {name}: spread of bin medians "
              f"{100 * block['spread_of_bin_medians']:.3f}%  ->  ratio "
              f"{block['ratio_to_median_abs_residual']:.2f}")
        for b in block["bins"]:
            print(f"      n={b['n']:6d}  {b['x_lo']:8.4f}..{b['x_hi']:8.4f}  "
                  f"median residual {100 * b['median_residual']:+7.3f}%")
    if structure["lag1_autocorrelation"] is not None:
        print(f"    lag-1 autocorrelation of residuals "
              f"{structure['lag1_autocorrelation']:.4f}  "
              f"(reported only; not part of the rule)")

    print("\n" + "=" * 74)
    print("H5 VERDICT")
    print("=" * 74)
    print(f"  branch: {out['branch']}")
    print(f"  {out['verdict']}")
    print(f"\n  thresholds fixed before the run: kappa spread < "
          f"{100 * thresholds.kappa_tight:g}% -> same form;")
    print(f"  otherwise rating residual < {100 * thresholds.rating_tight:g}% "
          f"-> different form")
    print(f"\n  H5b branch: {out['h5b']['branch']}")
    print(f"  {out['h5b']['verdict']}")
    print(f"  rule: max ratio > {thresholds.structured_above:g} -> structured; "
          f"<= {thresholds.unstructured_at_or_below:g} -> unstructured")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(args.out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
