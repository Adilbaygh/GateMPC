"""Build the published USGS data package from the OGC API.

    python scripts/download_usgs.py              # build (or top up) the package
    python scripts/download_usgs.py --verify     # check it against SHA256SUMS

What lands in the package (``DATA/USGS_canal_gates_v1`` by default):

    README.md                  what the package is, how to rebuild and verify it
    provenance.json            per layer: request URL, query, licence, counts, sha256
    SHA256SUMS                 checksums of the data layers
    time_series_metadata.csv   series roles (H1/H2), units, record extent
    observations/<site>_<year>.csv

Raw API payloads are deliberately NOT part of the package: the repository
allowlist keeps them out and requires this script to be able to rebuild them.
They are cached under ``DATA/.raw_cache`` so that an interrupted run resumes
without spending quota twice, and that directory is never published.

Determinism
-----------
The data layers must be byte-identical across runs, including after the cache is
deleted and everything is fetched again. That is what makes the checksums a
regression test rather than decoration. Three things make it hold:

* observation values are written as the **original decimal strings** returned by
  the API, never parsed into floats and reformatted, so no representation drift;
* rows are sorted by UTC timestamp, which for ISO-8601 is lexicographic order,
  and columns are fixed;
* JSON is written with sorted keys and a trailing newline.

``provenance.json`` is the one file NOT covered by ``SHA256SUMS``: it records the
retrieval date, which is genuinely different on a later run. Keeping it out of
the checksum set is what lets the data layers be reproducible while the
provenance stays honest about when the archive was read.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from gatempc.archive import census_move_events  # noqa: E402
from gatempc.usgs import (  # noqa: E402
    LICENCE, FetchFailed, QuotaExhausted, UsgsClient, dump_json,
)

# Series roles resolved from the time-series-metadata collection on 2026-09-05
# (the sublocation_identifier field), not inferred from the values.
SITES: dict[str, dict[str, object]] = {
    "09522700": {
        "name": "Wellton-Mohawk Main Canal near Yuma, AZ",
        "role": "primary structure; cross-validation folds",
        "years": list(range(2018, 2026)),
        "series": {
            "aa7306544e844561ad2ccf2476f7ca58": ("gate_opening", "45592", "ft"),
            "373d93c6f7d24462aae0c5e9b3056415": ("headwater", "00065", "ft"),
            "4b3972dec3cc43beb1c05be12b7804f7": ("tailwater", "00065", "ft"),
            "d3ec91292d17403397678bc7ed056f2d": ("discharge", "00060", "ft3_s"),
        },
    },
    "09428500": {
        "name": "CRIR Main Canal near Parker, AZ",
        "role": "external validation only; not a cross-validation fold",
        "years": [2026],
        "series": {
            "190daf89": ("gate_opening", "45592", "ft"),
            "aa6d1692": ("headwater", "00065", "ft"),
            "14eef6ee": ("tailwater", "00065", "ft"),
            "52737a6e": ("discharge", "00060", "ft3_s"),
        },
    },
}
PCODES = ("45592", "00065", "00060")
ROLE_ORDER = ("gate_opening", "headwater", "tailwater", "discharge")

OBS_COLUMNS = ["time_utc"]
for _role in ROLE_ORDER:
    OBS_COLUMNS += [_role, _role + "_approval"]

GRID_COLUMNS = [
    "site", "year", "rows", "on_grid_timestamps", "off_grid_timestamps",
    "off_grid_within_2s", "off_grid_beyond_2s",
    "rows_with_all_four", "rows_with_all_four_if_snapped_2s",
]

# The census spans the whole archive, not only the folds. Its purpose is to
# answer "why these eight years" with a measurement instead of an assertion: the
# published `begin` field of the gate series claims 2007-10-01, and the actual
# four-series overlap does not start until 2017. A reader cannot check the fold
# choice without this, so it is a published layer rather than a private note.
CENSUS_YEARS = list(range(2011, 2027))

CENSUS_COLUMNS = [
    "site", "year", "gate_opening", "headwater", "tailwater", "discharge",
    "timestamps_with_all_four", "gate_move_events", "approved_pct",
    # The published range of each series, added 2026-09-06. The manuscript
    # claims specific out-of-range readings as data-quality defects, and a claim
    # like that has to be checkable against a published file over the WHOLE
    # archive -- not only the fold years, which are the only ones the
    # observations layer carries. Without these columns a reader cannot verify
    # the claim and the author cannot either: one such claim turned out not to
    # survive contact with the data.
    "gate_opening_min", "gate_opening_max", "headwater_min", "headwater_max",
    "tailwater_min", "tailwater_max", "discharge_min", "discharge_max",
]

GAUGING_COLUMNS = [
    "site", "time_utc", "parameter_code", "value", "unit_of_measure",
    "measurement_rated", "observing_procedure", "observing_procedure_code",
    "control_condition", "approval_status", "measuring_agency",
    "field_visit_id", "qualifier",
]

TSMETA_COLUMNS = [
    "site", "time_series_id", "parameter_code", "parameter_name",
    "sublocation_identifier", "unit_of_measure", "statistic_id",
    "computation_period_identifier", "begin", "end", "primary", "data_gap_interval",
]


def role_of(site: str, tsid: str) -> str | None:
    for prefix, (role, _pcode, _unit) in SITES[site]["series"].items():  # type: ignore[index]
        if tsid.startswith(prefix):
            return role
    return None


def write_csv(path: str, columns: list[str], rows: list[list[str]]) -> None:
    """Write a CSV with fixed columns, LF endings and no locale dependence."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    os.replace(tmp, path)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


GRID_SECONDS = 900.0


def grid_diagnostics(site: str, year: int, rows: list[list[str]]) -> list[str]:
    """Count how many observations sit off the 15-minute grid, and what it costs.

    Why this layer exists. Discharge at 09522700 is timestamped one second early
    during parts of 2023 and 2024 (``:14:59`` instead of ``:15:00``). Those
    samples are then not simultaneous with stage and gate opening, so they drop
    out of any four-series analysis even though the readings are perfectly good.
    A reader comparing the row counts against 35 040 (a 15-minute year) will
    notice and ask; this layer answers without anyone having to re-derive it.

    The package does NOT snap the timestamps -- see requirements/decisions.md.
    The last column reports what snapping within two seconds *would* recover, so
    that the cost of leaving the archive untouched is a published number rather
    than an assertion.
    """
    idx = {name: i for i, name in enumerate(OBS_COLUMNS)}
    series_cols = [idx[r] for r in ROLE_ORDER]
    epoch = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)

    on_grid: dict[dt.datetime, set[int]] = {}
    off: list[tuple[dt.datetime, set[int]]] = []
    for row in rows:
        t = dt.datetime.fromisoformat(row[0])
        present = {c for c in series_cols if row[c] != ""}
        if t.minute % 15 == 0 and t.second == 0 and t.microsecond == 0:
            on_grid.setdefault(t, set()).update(present)
        else:
            off.append((t, present))

    snapped = {k: set(v) for k, v in on_grid.items()}
    within = beyond = 0
    for t, present in off:
        steps = round((t - epoch).total_seconds() / GRID_SECONDS)
        nearest = epoch + dt.timedelta(seconds=steps * GRID_SECONDS)
        if abs((nearest - t).total_seconds()) <= 2.0:
            within += 1
            snapped.setdefault(nearest, set()).update(present)
        else:
            beyond += 1

    full = sum(1 for v in on_grid.values() if len(v) == 4)
    full_snapped = sum(1 for v in snapped.values() if len(v) == 4)
    return [site, str(year), str(len(rows)), str(len(on_grid)), str(len(off)),
            str(within), str(beyond), str(full), str(full_snapped)]


def build_observations(client: UsgsClient, site: str, year: int,
                       provenance: list[dict[str, object]]) -> list[list[str]]:
    """One row per timestamp present in any series, all four series as columns."""
    by_time: dict[str, dict[str, str]] = {}
    for pcode in PCODES:
        records, url, from_cache = client.observations(site, pcode, year)
        counts: dict[str, int] = {}
        for rec in records:
            role = role_of(site, rec["time_series_id"])
            if role is None:                       # a series this study does not use
                continue
            counts[role] = counts.get(role, 0) + 1
            slot = by_time.setdefault(rec["time"], {})
            # The API returns the value as a decimal string; keep it verbatim.
            slot[role] = str(rec["value"])
            slot[role + "_approval"] = str(rec.get("approval_status") or "")
        provenance.append({
            "layer": f"observations/{site}_{year}.csv",
            "site": site,
            "parameter_code": pcode,
            "year": year,
            "request_url": url,
            "records_returned": len(records),
            "records_used_by_role": dict(sorted(counts.items())),
            "served_from_cache": from_cache,
            "licence": LICENCE,
        })
    rows = []
    for t in sorted(by_time):
        slot = by_time[t]
        rows.append([t] + [slot.get(c, "") for c in OBS_COLUMNS[1:]])
    return rows


def build_census(client: UsgsClient, sites: list[str],
                 provenance: list[dict[str, object]]) -> list[list[str]]:
    """Per site-year record counts across the whole archive.

    ``timestamps_with_all_four`` is the number of timestamps carrying all four
    series, so it is zero in a year where any of them is absent -- which is the
    honest answer to "could this year have been a fold". The private census that
    first established the fold list reported the intersection of whatever series
    happened to exist, which reads as a large number for a year that has only
    two of them; that ambiguity is removed here. For the fold years the column
    must agree with ``rows_with_all_four`` in grid_diagnostics.csv, and main()
    checks that it does.
    """
    rows = []
    for site in sites:
        for year in CENSUS_YEARS:
            times: dict[str, set[str]] = {}
            gate: dict[str, float] = {}
            span: dict[str, list[float]] = {}
            approved = total = 0
            for pcode in PCODES:
                records, url, from_cache = client.observations(site, pcode, year)
                used = 0
                for rec in records:
                    role = role_of(site, rec["time_series_id"])
                    if role is None:
                        continue
                    used += 1
                    times.setdefault(role, set()).add(rec["time"])
                    value = float(rec["value"])
                    if role in span:
                        span[role][0] = min(span[role][0], value)
                        span[role][1] = max(span[role][1], value)
                    else:
                        span[role] = [value, value]
                    total += 1
                    if (rec.get("approval_status") or "") == "Approved":
                        approved += 1
                    if role == "gate_opening":
                        gate[rec["time"]] = float(rec["value"])
                provenance.append({
                    "layer": "coverage_census.csv",
                    "site": site,
                    "parameter_code": pcode,
                    "year": year,
                    "request_url": url,
                    "records_returned": len(records),
                    "records_used": used,
                    "served_from_cache": from_cache,
                    "licence": LICENCE,
                })
            common: set[str] = set()
            if all(r in times for r in ROLE_ORDER):
                common = set.intersection(*(times[r] for r in ROLE_ORDER))
            pct = 100.0 * approved / total if total else 0.0
            extremes: list[str] = []
            for role in ROLE_ORDER:
                lo_hi = span.get(role)
                extremes += ["", ""] if lo_hi is None else [
                    f"{lo_hi[0]:g}", f"{lo_hi[1]:g}"]
            rows.append([site, str(year)]
                        + [str(len(times.get(r, ()))) for r in ROLE_ORDER]
                        + [str(len(common)),
                           str(census_move_events(gate)),
                           f"{pct:.1f}"]
                        + extremes)
    return rows


def build_gaugings(client: UsgsClient, sites: list[str],
                   provenance: list[dict[str, object]]) -> list[list[str]]:
    """Discrete field discharge measurements -- the independent observations.

    These are why the package exists in its present form. The continuous
    discharge series at a gated structure is a rating output computed from the
    gate opening and the two stages, so a gate law fitted to it only recovers
    the rating's own coefficient. These measurements are made on site with a
    current profiler and the rating is calibrated to them, so they are the only
    non-circular check available. The manuscript's central result rests on them
    (requirements/hypotheses.md H4), which is why they are published here with
    provenance and a checksum rather than left in a private cache.
    """
    rows = []
    for site in sites:
        records, url, from_cache = client.field_measurements(site)
        for rec in records:
            rows.append([site, str(rec.get("time", "")),
                         str(rec.get("parameter_code", "")),
                         str(rec.get("value", "")),
                         str(rec.get("unit_of_measure", "")),
                         str(rec.get("measurement_rated") or ""),
                         str(rec.get("observing_procedure") or ""),
                         str(rec.get("observing_procedure_code") or ""),
                         str(rec.get("control_condition") or ""),
                         str(rec.get("approval_status") or ""),
                         str(rec.get("measuring_agency") or ""),
                         str(rec.get("field_visit_id") or ""),
                         str(rec.get("qualifier") or "")])
        provenance.append({
            "layer": "gaugings.csv", "site": site, "request_url": url,
            "records_returned": len(records), "served_from_cache": from_cache,
            "licence": LICENCE,
        })
    rows.sort(key=lambda r: (r[0], r[1], r[11]))
    return rows


def build_metadata(client: UsgsClient, sites: list[str],
                   provenance: list[dict[str, object]]) -> list[list[str]]:
    rows = []
    for site in sites:
        records, url, from_cache = client.time_series_metadata(site)
        kept = 0
        for rec in records:
            if role_of(site, str(rec.get("id", ""))) is None:
                continue
            kept += 1
            rows.append([site] + [
                str(rec.get(k, "") if rec.get(k) is not None else "")
                for k in ("id", "parameter_code", "parameter_name",
                          "sublocation_identifier", "unit_of_measure", "statistic_id",
                          "computation_period_identifier", "begin", "end",
                          "primary", "data_gap_interval")
            ])
        provenance.append({
            "layer": "time_series_metadata.csv",
            "site": site,
            "request_url": url,
            "records_returned": len(records),
            "records_used": kept,
            "served_from_cache": from_cache,
            "licence": LICENCE,
        })
    rows.sort(key=lambda r: (r[0], r[2], r[1]))
    return rows


README = """\
# USGS canal gate observations — GateMPC data package

Normalized 15-minute observations at two instrumented canal check structures,
used to identify a gate discharge relation from real operating records.

| Site | Structure | Role in the study | Years |
|---|---|---|---|
| USGS 09522700 | Wellton-Mohawk Main Canal near Yuma, AZ | primary; cross-validation folds | 2018-2025 |
| USGS 09428500 | CRIR Main Canal near Parker, AZ | external validation only | 2026 |

## Files

- `observations/<site>_<year>.csv` — one row per timestamp present in any series.
  Columns: gate opening, headwater stage, tailwater stage, discharge, each with
  its USGS approval status. Empty cells mean that series has no value at that
  timestamp; they are not zeros.
- `time_series_metadata.csv` — which time series is which. The headwater/tailwater
  assignment comes from the `sublocation_identifier` field, so it is a recorded
  fact rather than an inference from the values.
- `grid_diagnostics.csv` — how many observations fall off the 15-minute grid in
  each site-year, and how many four-series samples that costs. Discharge at
  09522700 is timestamped one second early during parts of 2023 and 2024, which
  is why those years show fewer simultaneous samples than their neighbours. The
  timestamps are left exactly as the archive publishes them; the last column
  reports what snapping within two seconds would recover, so the cost of that
  choice is a published number.
- `coverage_census.csv` — one row per site and calendar year over the whole
  archive (2011-2026), with the number of 15-minute records in each of the four
  series, the number of timestamps carrying all four, the number of gate move
  events larger than 0.02 ft, and the share of records marked Approved. This is
  why the study uses 2018-2025 and not the range the metadata advertises: the
  gate series reports a `begin` of 2007-10-01, but stage is absent until 2017,
  so there is no four-series overlap before then and the column shows it. The
  gate move count here is taken over the year's sequence as published, without
  splitting at gaps -- it is a coverage indicator, not a physical measurement.
- `gaugings.csv` — discrete field discharge measurements, mostly by acoustic
  Doppler current profiler, each with the USGS rating of its quality. These are
  the only observations here that are independent of the gate law: the
  continuous discharge series is a rating output computed from the gate opening
  and the two stages, so it cannot be used to test that law without circularity.
  The central result of the study is a comparison against these.

  The `measurement_rated` column carries the archive's own quality rating. USGS
  defines what each rating claims, quoted here from the reference list that
  governs the column -- "Stream Discharge Measurement Quality", NWIS reference
  list version 4.11, <https://water.usgs.gov/XML/NWIS/4.11/ReferenceLists/DischargeMeasurementQualityList.html>,
  read 2026-09-05; the page carries no date of its own and the wording is
  unchanged from version 4.7:

  | Rating | USGS definition, quoted |
  |---|---|
  | Excellent | "should be within 2% of the actual flow" |
  | Good | "should be within 5% of the actual flow" |
  | Fair | "should be within 8% of the actual flow" |
  | Poor | "should be more than 8% of the actual flow" |
  | Unspecified | "the accuracy of the discharge measurement was not rated" |

  The Poor wording is the source's own; read as an error larger than 8%. These
  percentages are the measurements' stated accuracy, so they bound what any
  comparison against them can resolve: a disagreement smaller than the rating
  cannot be told apart from the error of the measurement itself. The study
  accepts Good and Fair and reports the Poor and unrated ones it dropped.
- `provenance.json` — for every layer: the exact request URL, the record counts,
  the licence and the retrieval date.
- `SHA256SUMS` — checksums of the data layers.

## Units

Values are kept in the units the archive publishes: feet for gate opening and
stage, cubic feet per second for discharge. They are written as the original
decimal strings, never parsed and reformatted, so nothing is lost or drifted.

## Rebuilding and verifying

    python scripts/download_usgs.py            # rebuild the package
    python scripts/download_usgs.py --verify   # check it against SHA256SUMS

Raw API payloads are not part of this package; the download script rebuilds them
on demand and caches them privately. Deleting that cache and rebuilding must
reproduce these files byte for byte, and `--verify` is what proves it.

`provenance.json` is deliberately **not** covered by `SHA256SUMS`: it records the
retrieval date, which differs on a later run. The data layers are reproducible;
the provenance stays honest about when the archive was read.

A `--verify` failure on a file whose bytes are unchanged locally means the
upstream archive was revised after retrieval. That is a finding, not a defect —
report it rather than regenerating the checksums.

## Licence and citation

U.S. Geological Survey water data are in the public domain. Retrieved from the
USGS OGC API, collection `continuous`:
<https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "DATA", "USGS_canal_gates_v1"))
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, "DATA", ".raw_cache"))
    ap.add_argument("--sites", default=",".join(SITES))
    ap.add_argument("--verify", action="store_true",
                    help="recompute checksums and compare with SHA256SUMS")
    args = ap.parse_args()

    sites = [s.strip() for s in args.sites.split(",") if s.strip()]
    for s in sites:
        if s not in SITES:
            return _fail(f"unknown site {s}; known: {', '.join(SITES)}")

    if args.verify:
        return verify(args.out)

    os.makedirs(os.path.join(args.out, "observations"), exist_ok=True)
    client = UsgsClient(args.cache_dir)
    provenance: list[dict[str, object]] = []

    try:
        meta_rows = build_metadata(client, sites, provenance)
        write_csv(os.path.join(args.out, "time_series_metadata.csv"),
                  TSMETA_COLUMNS, meta_rows)
        print(f"time_series_metadata.csv: {len(meta_rows)} series")

        gauging_rows = build_gaugings(client, sites, provenance)
        write_csv(os.path.join(args.out, "gaugings.csv"),
                  GAUGING_COLUMNS, gauging_rows)
        print(f"gaugings.csv: {len(gauging_rows)} field discharge measurements")

        grid_rows = []
        for site in sites:
            for year in SITES[site]["years"]:            # type: ignore[index]
                rows = build_observations(client, site, year, provenance)
                path = os.path.join(args.out, "observations", f"{site}_{year}.csv")
                write_csv(path, OBS_COLUMNS, rows)
                diag = grid_diagnostics(site, year, rows)
                grid_rows.append(diag)
                print(f"observations/{site}_{year}.csv: {len(rows)} rows, "
                      f"{diag[7]} with all four series")
        write_csv(os.path.join(args.out, "grid_diagnostics.csv"),
                  GRID_COLUMNS, sorted(grid_rows, key=lambda r: (r[0], r[1])))
        print(f"grid_diagnostics.csv: {len(grid_rows)} site-years")

        census_rows = build_census(client, sites, provenance)
        write_csv(os.path.join(args.out, "coverage_census.csv"),
                  CENSUS_COLUMNS, census_rows)
        # The census and the grid diagnostics count the same thing by different
        # routes -- one from the raw records, one from the written observation
        # rows -- so disagreement means one of them is wrong. Better to stop here
        # than to publish two numbers that contradict each other.
        grid_by_key = {(r[0], r[1]): r[7] for r in grid_rows}
        for r in census_rows:
            want = grid_by_key.get((r[0], r[1]))
            if want is not None and want != r[6]:
                return _fail(
                    f"coverage_census.csv and grid_diagnostics.csv disagree for "
                    f"{r[0]} {r[1]}: census says {r[6]} timestamps with all four "
                    f"series, grid diagnostics say {want}. Not writing a package "
                    f"whose own layers contradict each other.")
        usable = sum(1 for r in census_rows if int(r[6]) > 0)
        print(f"coverage_census.csv: {len(census_rows)} site-years, "
              f"{usable} with all four series present")
    except QuotaExhausted as exc:
        return _fail(f"STOPPED: {exc}", quota=True)
    except FetchFailed as exc:
        return _fail(f"FETCH FAILED: {exc}\nNothing was cached for the failed layer; "
                     f"rerun to retry only what is missing.")

    data_files = collect_data_files(args.out)
    sums = {rel: sha256_file(os.path.join(args.out, rel)) for rel in data_files}
    write_sha256sums(args.out, sums)

    for entry in provenance:
        entry["sha256"] = sums.get(str(entry["layer"]), "")
    dump_json({
        "package": "USGS_canal_gates_v1",
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0).isoformat(),
        "api_collection": "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous",
        "licence": LICENCE,
        "http_requests_made_this_run": client.requests_made,
        "sites": {s: {k: v for k, v in SITES[s].items() if k != "series"} for s in sites},
        "series_roles": {s: {tsid: role for tsid, (role, _p, _u)
                             in SITES[s]["series"].items()}     # type: ignore[union-attr]
                         for s in sites},
        "layers": sorted(provenance, key=lambda e: (str(e["layer"]),
                                                    str(e.get("parameter_code", "")))),
    }, os.path.join(args.out, "provenance.json"))

    with open(os.path.join(args.out, "README.md"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(README)

    print(f"\n{len(data_files)} data files checksummed; "
          f"{client.requests_made} HTTP requests this run")
    print(f"package written to {args.out}")
    return 0


def collect_data_files(out: str) -> list[str]:
    """Data layers only: provenance.json and README.md are not checksummed."""
    found = []
    for root, _dirs, files in os.walk(out):
        for name in sorted(files):
            if not name.endswith(".csv"):
                continue
            found.append(os.path.relpath(os.path.join(root, name), out).replace("\\", "/"))
    return sorted(found)


def write_sha256sums(out: str, sums: dict[str, str]) -> None:
    lines = [f"{sums[rel]}  {rel}\n" for rel in sorted(sums)]
    tmp = os.path.join(out, "SHA256SUMS.part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
    os.replace(tmp, os.path.join(out, "SHA256SUMS"))


def verify(out: str) -> int:
    path = os.path.join(out, "SHA256SUMS")
    if not os.path.exists(path):
        return _fail(f"no SHA256SUMS in {out}; build the package first")
    expected: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                digest, rel = line.rstrip("\n").split("  ", 1)
                expected[rel] = digest

    present = set(collect_data_files(out))
    bad, missing = [], []
    for rel, digest in sorted(expected.items()):
        full = os.path.join(out, rel)
        if not os.path.exists(full):
            missing.append(rel)
        elif sha256_file(full) != digest:
            bad.append(rel)
    extra = sorted(present - set(expected))

    for rel in missing:
        print(f"MISSING   {rel}")
    for rel in bad:
        print(f"CHANGED   {rel}")
    for rel in extra:
        print(f"UNTRACKED {rel}")
    if bad or missing or extra:
        print(f"\nFAILED: {len(bad)} changed, {len(missing)} missing, "
              f"{len(extra)} untracked, out of {len(expected)} tracked files.")
        print("If your local bytes are unchanged, the upstream archive was revised "
              "after retrieval. Report that; do not regenerate the checksums.")
        return 1
    print(f"OK: {len(expected)} files match SHA256SUMS")
    return 0


def _fail(message: str, quota: bool = False) -> int:
    print(message, file=sys.stderr)
    if quota:
        print("Everything fetched so far is cached; rerun the same command later.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
