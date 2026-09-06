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
