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

#: The parameter code each role is published under. Fixed by the archive: the two
#: stages share 00065 and are told apart only by their sublocation label, which is
#: why the roles cannot be inferred from the codes alone.
ROLE_PCODE = {"gate_opening": "45592", "headwater": "00065",
              "tailwater": "00065", "discharge": "00060"}

#: Where the published package goes. Named so that the exploratory flags below can
#: refuse to write here: that directory is what SHA256SUMS pins and what the
#: manuscript's numbers were computed from.
DEFAULT_OUT = os.path.join(ROOT, "DATA", "USGS_canal_gates_v1")

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


# ------------------------------------------------------- adding another station


def parse_series(text: str) -> dict[str, tuple[str, str, str]]:
    """``gate_opening=aa73,headwater=373d,…`` -> a ``SITES`` series mapping.

    All four roles are required, because a package missing one of them cannot
    answer the question this repository exists to ask. The value is an id prefix,
    matched with ``startswith`` in :func:`role_of` exactly as the registered sites
    are, so a few characters are enough as long as they are unique at that site.
    """
    mapping: dict[str, tuple[str, str, str]] = {}
    seen: set[str] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        role, _, prefix = part.partition("=")
        role, prefix = role.strip(), prefix.strip()
        if role not in ROLE_ORDER:
            raise ValueError(f"unknown role {role!r}; expected one of "
                             f"{', '.join(ROLE_ORDER)}")
        if role in seen:
            raise ValueError(f"role {role} was given twice")
        if not prefix:
            raise ValueError(f"role {role} has no time-series id")
        seen.add(role)
        mapping[prefix] = (role, ROLE_PCODE[role], "")
    missing = [role for role in ROLE_ORDER if role not in seen]
    if missing:
        raise ValueError("no time-series id for: " + ", ".join(missing))
    return mapping


def parse_years(text: str) -> list[int]:
    """``2018-2025`` or ``2024,2026`` -> a sorted list of years."""
    years: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        first, separator, last = part.partition("-")
        try:
            start = int(first)
            stop = int(last) if separator else start
        except ValueError:
            raise ValueError(f"not a year or a year range: {part!r}") from None
        if stop < start:
            raise ValueError(f"the range runs backwards: {part!r}")
        if stop - start > 40:
            raise ValueError(f"the range is longer than the archive: {part!r}")
        years.update(range(start, stop + 1))
    if not years:
        raise ValueError("no years given")
    return sorted(years)


#: Words an operating office has been seen to use for each side of a gate. The
#: two stages share parameter code 00065 and are told apart only by this
#: free-text label, so the match is a proposal for a person to check, never an
#: answer. "H1 (Headwater)" and "H2 (Tailwater)" are what both published sites
#: say; nothing obliges another office to say either.
STAGE_WORDS = {
    "headwater": ("headwater", "head water", "h1", "upstream", "pool", "forebay"),
    "tailwater": ("tailwater", "tail water", "h2", "downstream", "tailbay"),
}


def one_of(records: list[dict], what: str) -> tuple[str, str]:
    """Pick one series out of the candidates for a role, or say why none was picked.

    Returns ``(id, problem)``; either may be empty and both may be filled, because
    a proposal worth making can still be worth questioning.

    ``primary`` is the archive's own answer to "which of these is the one", so it
    is used where it settles the question and reported exactly where it does not.
    Every candidate carrying it is not the same fact as none of them carrying it,
    and the first version of this said "none is marked Primary" at a site whose
    two discharge series are both marked Primary. A message that misreports the
    archive is worse than no message: it is the thing the reader will quote.
    """
    if not records:
        return "", f"no {what}"
    if len(records) == 1:
        return str(records[0].get("id") or ""), ""
    primary = [record for record in records
               if str(record.get("primary") or "").lower() == "primary"]
    if len(primary) == 1:
        return (str(primary[0].get("id") or ""),
                f"{len(records)} {what}; the only one marked Primary was proposed — "
                f"check that it is the one you want")
    marked = (f", all {len(primary)} of them marked Primary"
              if len(primary) == len(records)
              else f", {len(primary)} of them marked Primary" if primary
              else " and none marked Primary")
    return "", (f"{len(records)} {what}{marked}; choose one yourself from the table "
                f"above")


def propose_roles(records: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Guess which series is which, and say where the guess has no basis.

    Returns ``(proposal, problems)``. A role appears in the proposal only when
    exactly one series can carry it; everything else lands in ``problems`` as a
    sentence a reader can act on. Nothing here decides anything: the proposal is
    printed for a person to accept, and the two stages are the reason — getting
    them the wrong way round inverts the head difference and nothing complains.
    """
    by_code: dict[str, list[dict]] = {}
    for record in records:
        by_code.setdefault(str(record.get("parameter_code") or ""), []).append(record)

    def identifier(record: dict) -> str:
        return str(record.get("id") or "")

    proposal: dict[str, str] = {}
    problems: list[str] = []

    gates = by_code.get("45592", [])
    if not gates:
        problems.append("no gate opening series (parameter code 45592): this site "
                        "cannot be used by the detector at all")
    elif len(gates) > 1:
        # Not a choice to hand to the reader. A station reporting Gate 1..Gate 14
        # publishes one opening per leaf and ONE discharge for the whole
        # structure, so pairing that discharge with a single leaf's opening is
        # not the relation this detector tests -- it is a different structure
        # with a different area. The published primary site avoids this by
        # reporting the average over its two leaves as one series, which the
        # manuscript states as a limitation rather than a convenience.
        labels = ", ".join(sorted(str(record.get("sublocation_identifier") or "?")
                                  for record in gates)[:6])
        problems.append(
            f"{len(gates)} gate opening series, one per leaf ({labels}...): the "
            f"discharge is published for the structure as a whole, so no single "
            f"leaf's opening pairs with it. This detector needs a structure whose "
            f"opening is published as one series")
    else:
        proposal["gate_opening"] = identifier(gates[0])

    flows = by_code.get("00060", [])
    if not flows:
        problems.append("no discharge series (parameter code 00060)")
    else:
        chosen, problem = one_of(flows, "discharge series")
        if chosen:
            proposal["discharge"] = chosen
        if problem:
            problems.append(problem)

    stages = by_code.get("00065", [])
    if len(stages) < 2:
        problems.append(f"{len(stages)} stage series (parameter code 00065); the "
                        f"detector needs two, a headwater and a tailwater")
    else:
        for role, words in STAGE_WORDS.items():
            hits = [r for r in stages
                    if any(word in str(r.get("sublocation_identifier") or "").lower()
                           for word in words)]
            if len(hits) == 1:
                proposal[role] = identifier(hits[0])
        if "headwater" not in proposal or "tailwater" not in proposal:
            problems.append("the stage series are not labelled clearly enough to "
                            "tell the headwater from the tailwater; read the "
                            "sublocation column and decide")
        elif proposal["headwater"] == proposal["tailwater"]:
            problems.append("one stage series matched both sides; decide yourself")
    return proposal, problems


def unresolved_series(sites: list[str], meta_rows: list[list[str]]) -> str:
    """Check every role resolves to exactly one real series, before anything is fetched.

    Without this the run accepts ids that match nothing at all. It then writes an
    empty metadata layer, an empty observation file per year and a checksummed
    package, prints "package written to …", and exits successfully — having spent
    the hourly quota to produce nothing. That is exactly the failure this
    repository's client tests were written against: a pipeline must never be able
    to turn a request that found nothing into a plausible-looking empty result.
    The hole opened as soon as the ids stopped being typed into SITES by hand.
    """
    for site in sites:
        matched: dict[str, list[str]] = {role: [] for role in ROLE_ORDER}
        for row in meta_rows:
            if row[0] != site:
                continue
            role = role_of(site, row[1])
            if role is not None:
                matched[role].append(row[1])
        empty = [role for role in ROLE_ORDER if not matched[role]]
        if empty:
            return (f"{site}: nothing in the archive matches " + ", ".join(empty)
                    + ". Look the site up with --list-series and use the "
                      "time_series_id values it prints; nothing was written.")
        crowded = [f"{role} matches {len(matched[role])} series"
                   for role in ROLE_ORDER if len(matched[role]) > 1]
        if crowded:
            return (f"{site}: " + "; ".join(crowded)
                    + ". Give more characters of the id; nothing was written.")
    return ""


def stations_from_series(records: list[dict]) -> dict[str, dict]:
    """Group time-series records by the station that publishes them.

    Returns ``{site: {"series": int, "begin": str, "end": str, "where": [str]}}``
    with the site number stripped of its agency prefix. Pure, so both the command
    line and the window can format the same grouping instead of each writing its
    own — the first version had two, and the printed one carried a bracket error
    that only a live query could reach.
    """
    stations: dict[str, dict] = {}
    for record in records:
        site = str(record.get("monitoring_location_id") or "").replace("USGS-", "")
        if not site:
            continue
        entry = stations.setdefault(
            site, {"series": 0, "begin": "", "end": "", "where": set()})
        entry["series"] += 1
        begin = str(record.get("begin") or "")[:10]
        end = str(record.get("end") or "")[:10]
        if begin and (not entry["begin"] or begin < entry["begin"]):
            entry["begin"] = begin
        if end > entry["end"]:
            entry["end"] = end
        label = str(record.get("sublocation_identifier") or "")
        if label:
            entry["where"].add(label)
    for entry in stations.values():
        entry["where"] = sorted(entry["where"])
    return stations


def full_calendar_years(records: list[dict]) -> tuple[int, ...]:
    """Calendar years every one of these series covers from 1 January to 31 December.

    A series beginning on 2011-03-30 does not cover 2011, and one ending on
    2026-09-06 does not cover 2026: a partial year is not a year of overlap. The
    dates are the archive's advertised extent, which overstates — the primary
    site's gate series advertises 2007 while stage is absent until 2017 — so this
    is an upper bound, and H6 registered it as one.
    """
    starts: list[int] = []
    stops: list[int] = []
    for record in records:
        begin = str(record.get("begin") or "")[:10]
        end = str(record.get("end") or "")[:10]
        if len(begin) < 10 or len(end) < 10:
            return ()
        starts.append(int(begin[:4]) + (0 if begin[5:] == "01-01" else 1))
        stops.append(int(end[:4]) - (0 if end[5:] == "12-31" else 1))
    if not starts or max(starts) > min(stops):
        return ()
    return tuple(range(max(starts), min(stops) + 1))


#: The reasons a station can fail, as stable keys. The counts in
#: ``results/station_survey.json`` are grouped by these and the manuscript cites
#: them, so they are part of a published file's contract: rewording a message
#: below must never silently rename a key the paper refers to. That is why the
#: category is returned alongside the prose instead of being parsed back out of it.
REFUSALS = (
    "no_gate_series",
    "one_opening_per_leaf",
    "stages_not_two",
    "stages_not_labelled",
    "no_discharge_series",
    "no_whole_year_in_common",
)


def meets_the_method(records: list[dict]) -> tuple[bool, str, str, dict[str, str]]:
    """Does this station publish what the detector needs? The H6 criteria, literally.

    Written to match ``requirements/hypotheses.md`` H6, which was registered
    before this ran, and deliberately not adjusted to what the archive turned out
    to hold. Two of them are worth restating because they are where stations fail:

    * exactly ONE gate series. Several means one opening per leaf against a single
      discharge for the whole structure, which is a different object.
    * exactly TWO stage series, labelled clearly enough to tell head from tail.
      Guessing would invert the head difference in silence.

    Discharge is registered as "at least one", so an ambiguous choice does not
    disqualify a station: the question is whether a usable combination exists, and
    the reader picks. The discharge giving the longest overlap is the one tested.
    """
    by_code: dict[str, list[dict]] = {}
    for record in records:
        by_code.setdefault(str(record.get("parameter_code") or ""), []).append(record)

    gates = by_code.get("45592", [])
    if not gates:
        return False, "no_gate_series", "no gate series", {}
    if len(gates) > 1:
        return False, "one_opening_per_leaf", f"{len(gates)} gate series, one per leaf", {}
    stages = by_code.get("00065", [])
    if len(stages) != 2:
        return False, "stages_not_two", f"{len(stages)} stage series, needs 2", {}
    labelled: dict[str, dict] = {}
    for role, words in STAGE_WORDS.items():
        hits = [record for record in stages
                if any(word in str(record.get("sublocation_identifier") or "").lower()
                       for word in words)]
        if len(hits) == 1:
            labelled[role] = hits[0]
    if set(labelled) != {"headwater", "tailwater"}:
        return False, "stages_not_labelled", "stages not labelled head/tail", {}
    if labelled["headwater"] is labelled["tailwater"]:
        return False, "stages_not_labelled", "one stage matched both sides", {}
    flows = by_code.get("00060", [])
    if not flows:
        return False, "no_discharge_series", "no discharge series", {}

    base = [gates[0], labelled["headwater"], labelled["tailwater"]]
    best: tuple[dict, tuple[int, ...]] | None = None
    for flow in flows:
        years = full_calendar_years(base + [flow])
        if years and (best is None or len(years) > len(best[1])):
            best = (flow, years)
    if best is None:
        return False, "no_whole_year_in_common", \
            "the four never share a whole calendar year", {}
    flow, years = best
    chosen = {
        "gate_opening": str(gates[0].get("id") or ""),
        "headwater": str(labelled["headwater"].get("id") or ""),
        "tailwater": str(labelled["tailwater"].get("id") or ""),
        "discharge": str(flow.get("id") or ""),
    }
    return True, "usable", f"{years[0]}-{years[-1]}", chosen


SURVEY_OUT = os.path.join(ROOT, "results", "station_survey.json")


def survey(client: UsgsClient, out: str = SURVEY_OUT) -> int:
    """H6: how many gate-opening stations carry everything the method needs.

    One metadata request per station, all of them cached, so a second run costs
    nothing. Metadata only: no observations are downloaded.

    The result is a **dated snapshot of somebody else's archive**, not a
    computation over the published package, and the two must not be confused.
    Every other result file in this repository is reproducible offline from
    ``DATA/`` and will give the same number in ten years; this one answers a
    question about the archive as it stood on the day it was asked, and a later
    run may legitimately answer differently. So the file records its query and
    its retrieval date, the manuscript reports the number as of that date, and a
    reader with no network keeps the published snapshot rather than losing it:
    the run says why it could not refresh and leaves the file alone.
    """
    try:
        records, url, from_cache = client.sites_with_parameter(
            ROLE_PCODE["gate_opening"])
    except (FetchFailed, QuotaExhausted) as error:
        if os.path.exists(out):
            print(f"could not reach the archive: {error}")
            print(f"keeping the published snapshot at {out}; it is dated, and a "
                  f"reader offline should not lose it")
            return 0
        return _fail(f"could not reach the archive and there is no snapshot to "
                     f"keep: {error}", quota=isinstance(error, QuotaExhausted))
    stations = stations_from_series(records)
    print(f"# H6 — {len(stations)} stations publish a gate opening series"
          + ("  [list from cache]" if from_cache else ""))
    print(f"# {url}")
    print("# criteria registered in requirements/hypotheses.md before this ran")
    print(f"\n{'site':12}  {'verdict':8}  reason, or the years the four share")
    usable: list[str] = []
    by_site: list[dict[str, object]] = []
    refused: dict[str, int] = {key: 0 for key in REFUSALS}
    unreachable = 0
    for site in sorted(stations):
        try:
            found, _url, _cached = client.time_series_metadata(site)
        except (FetchFailed, QuotaExhausted) as error:
            print(f"{site:12}  {'?':8}  {type(error).__name__}: {error}")
            by_site.append({"site": site, "usable": None,
                            "reason": f"{type(error).__name__}: {error}"})
            unreachable += 1
            continue
        ok, category, detail, chosen = meets_the_method(found)
        print(f"{site:12}  {'USABLE' if ok else 'no':8}  {detail}")
        by_site.append({"site": site, "usable": ok, "why": category,
                        "detail": detail, "series": chosen})
        if ok:
            usable.append(site)
        else:
            refused[category] = refused.get(category, 0) + 1
    print(f"\n# {len(usable)} of {len(stations)} stations publish all four series "
          f"with at least one full calendar year in common")
    if usable:
        print("#   " + ", ".join(usable))
    print(f"# {client.requests_made} HTTP requests this run")

    if unreachable:
        # A partial survey is a different number from a complete one, and the two
        # must never be printed the same way. Nothing is written.
        return _fail(f"{unreachable} of {len(stations)} stations could not be "
                     f"read; a partial count is not the measurement and was not "
                     f"written")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    dump_json({
        "question": "how many structures in the archive publish the four series "
                    "this method needs",
        "registered_as": "requirements/hypotheses.md, H6, before this was run",
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0).isoformat(),
        "query": url,
        "parameter_code": ROLE_PCODE["gate_opening"],
        "licence": LICENCE,
        "criteria": [
            "exactly one series with parameter code 45592",
            "exactly two with 00065, labelled clearly enough to tell the "
            "headwater from the tailwater",
            "at least one with 00060",
            "the four share at least one whole calendar year of advertised "
            "record, 1 January to 31 December",
        ],
        "stations_with_a_gate": len(stations),
        "usable": len(usable),
        "usable_sites": sorted(usable),
        "refused_because": refused,
        "by_site": by_site,
    }, out)
    print(f"written to {out}")
    return 0


def find_stations(client: UsgsClient) -> int:
    """Every station in the archive that publishes a gate opening series.

    One request. The gate opening is the scarce one — discharge and stage are at
    thousands of stations, a gate opening at very few — so asking the metadata
    collection for parameter code 45592 with no site attached turns "which
    structure could I use" from a guess into a list. It is a list of candidates
    and nothing more: a station here still has to carry two stages and a
    discharge, which ``--list-series`` checks one station at a time.
    """
    records, url, from_cache = client.sites_with_parameter(ROLE_PCODE["gate_opening"])
    stations = stations_from_series(records)
    print(f"# {len(stations)} stations publish a gate opening series "
          f"(parameter code {ROLE_PCODE['gate_opening']})"
          + ("  [from cache]" if from_cache else ""))
    print(f"# {url}")
    print(f"\n{'site':12}  {'series':6}  {'sublocation':24}  {'begin':10}  {'end':10}")
    for site in sorted(stations):
        entry = stations[site]
        where = ", ".join(entry["where"])
        print(f"{site:12}  {entry['series']:<6}  {where[:24]:24}  "
              f"{entry['begin']:10}  {entry['end']:10}")
    print("\n# a gate opening is necessary, not sufficient: check a candidate with")
    print("#   python scripts/download_usgs.py --list-series --sites <site>")
    return 0


def list_series(client: UsgsClient, sites: list[str]) -> int:
    """Print every time series a site publishes, with no role assigned to any.

    This is the lookup that has to happen before an unregistered site can be
    fetched, and it deliberately stops at printing. Which of two identical stage
    series is the headwater is written in ``sublocation_identifier``, a free-text
    field worded by the operating office — "H1 (Headwater)" at both sites in the
    published package, but nothing obliges another office to say the same thing,
    or anything at all. So the table is read by a person, who then names the four
    ids in ``--series``.
    """
    for site in sites:
        records, url, from_cache = client.time_series_metadata(site)
        print(f"\n# {site} — {len(records)} series"
              + ("  [from cache]" if from_cache else ""))
        print(f"# {url}")
        if not records:
            print("no time series at this site")
            continue
        print(f"{'time_series_id':34}  {'pcode':6}  {'parameter':24}  "
              f"{'sublocation':22}  {'unit':7}  {'primary':8}  {'begin':10}  {'end':10}")
        for record in sorted(records, key=lambda r: (
                str(r.get("parameter_code") or ""),
                str(r.get("sublocation_identifier") or ""))):
            print(f"{str(record.get('id') or '')[:34]:34}  "
                  f"{str(record.get('parameter_code') or ''):6}  "
                  f"{str(record.get('parameter_name') or '')[:24]:24}  "
                  f"{str(record.get('sublocation_identifier') or '')[:22]:22}  "
                  f"{str(record.get('unit_of_measure') or ''):7}  "
                  f"{str(record.get('primary') or '')[:8]:8}  "
                  f"{str(record.get('begin') or '')[:10]:10}  "
                  f"{str(record.get('end') or '')[:10]:10}")

        # The reader is not left to assemble the flag from the table by hand. Where
        # the four roles resolve, the line below is ready to paste; where they do
        # not, the reason is named. A printed template with <id> in it invites
        # being pasted verbatim, which is how this site was first "fetched".
        proposal, problems = propose_roles(records)
        print()
        for problem in problems:
            print(f"# ! {problem}")
        if len(proposal) == len(ROLE_ORDER):
            flag = ",".join(f"{role}={proposal[role]}" for role in ROLE_ORDER)
            print("# check the two stages against the sublocation column above, then:")
            print(f"#   --sites {site} --series {flag} \\")
            print(f"#     --years <YYYY-YYYY> --out build/lab/package_{site}")
        else:
            print("# this site cannot be fetched: the four series it needs are not "
                  "all there.")
    return 0


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
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, "DATA", ".raw_cache"))
    ap.add_argument("--sites", default=",".join(SITES))
    ap.add_argument("--verify", action="store_true",
                    help="recompute checksums and compare with SHA256SUMS")
    ap.add_argument("--list-series", action="store_true",
                    help="print the time series each --sites publishes, and stop")
    ap.add_argument("--find-stations", action="store_true",
                    help="list every station that publishes a gate opening, and stop")
    ap.add_argument("--survey", action="store_true",
                    help="H6: check every gate-opening station against the "
                         "method's requirements, and stop")
    ap.add_argument("--series", default="",
                    help="role=time_series_id for a site the registry does not "
                         "hold, comma separated; all four roles are required")
    ap.add_argument("--years", default="",
                    help="years to fetch, e.g. 2024-2026; needs an --out of its own")
    ap.add_argument("--site-name", default="",
                    help="a label for an added site, recorded in its provenance")
    args = ap.parse_args()

    sites = [s.strip() for s in args.sites.split(",") if s.strip()]

    # Looking is not fetching: these work for any site number and write nothing.
    if args.survey:
        return survey(UsgsClient(args.cache_dir))
    if args.find_stations:
        return find_stations(UsgsClient(args.cache_dir))
    if args.list_series:
        return list_series(UsgsClient(args.cache_dir), sites)

    # The exploratory flags may not touch the published package. That directory is
    # what SHA256SUMS pins and what the manuscript's numbers were computed from; a
    # package built from years somebody chose, or from roles somebody assigned by
    # reading a free-text label, is a different object and belongs somewhere else.
    exploratory = bool(args.series or args.years or args.site_name)
    if exploratory and os.path.abspath(args.out) == os.path.abspath(DEFAULT_OUT):
        return _fail("--series, --years and --site-name need an --out of their own; "
                     "they must not write into the published package")

    if args.series:
        if len(sites) != 1:
            return _fail("--series describes one site; give exactly one --sites")
        added = sites[0]
        if added in SITES:
            return _fail(f"{added} is already in the registry; --series would change "
                         f"what a published site means, so it is refused")
        if not args.years:
            return _fail("--series needs --years: the archive holds years in which "
                         "the four series do not all exist, and this script cannot "
                         "tell which those are without asking for them")
        try:
            series = parse_series(args.series)
            years = parse_years(args.years)
        except ValueError as error:
            return _fail(str(error))
        # Registered here rather than threaded through every builder, so that SITES
        # stays the one place that answers "what is this site" for the whole run.
        SITES[added] = {
            "name": args.site_name or f"USGS {added}",
            "role": "added at the command line; the four series were assigned by "
                    "the person who ran it, not by the study",
            "years": years,
            "series": series,
        }
    elif args.years:
        try:
            years = parse_years(args.years)
        except ValueError as error:
            return _fail(str(error))
        for site in sites:
            if site not in SITES:
                return _fail(f"unknown site {site}; --years does not add one, "
                             f"--series does")
            SITES[site] = dict(SITES[site], years=years)  # type: ignore[arg-type]

    for s in sites:
        if s not in SITES:
            return _fail(f"unknown site {s}; known: {', '.join(SITES)}. "
                         f"To add another, look it up with --list-series and name "
                         f"its four series with --series.")

    if args.verify:
        return verify(args.out)

    client = UsgsClient(args.cache_dir)
    provenance: list[dict[str, object]] = []

    try:
        # One request, and the whole assignment stands or falls on it. Nothing is
        # created on disk until every role has been matched to exactly one series
        # that the archive actually holds, so a wrong id costs a single request
        # instead of a quota's worth of empty files.
        meta_rows = build_metadata(client, sites, provenance)
        unresolved = unresolved_series(sites, meta_rows)
        if unresolved:
            return _fail(unresolved)

        os.makedirs(os.path.join(args.out, "observations"), exist_ok=True)
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
        # Who decided which series is the headwater. In the published package that
        # was the study, reading sublocation_identifier once and writing it down;
        # anywhere else it is whoever typed --series, and a reader of the result is
        # entitled to know which of the two they are holding.
        "series_roles_assigned_by": ("the person who ran the script" if exploratory
                                     else "the study, from sublocation_identifier"),
        "layers": sorted(provenance, key=lambda e: (str(e["layer"]),
                                                    str(e.get("parameter_code", "")))),
    }, os.path.join(args.out, "provenance.json"))

    with open(os.path.join(args.out, "README.md"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(lab_readme(sites, args.out) if exploratory else README)

    print(f"\n{len(data_files)} data files checksummed; "
          f"{client.requests_made} HTTP requests this run")
    print(f"package written to {args.out}")
    return 0


def lab_readme(sites: list[str], out: str) -> str:
    """The README for a package built with the exploratory flags.

    It says the one thing that matters about such a package: it is not the one the
    paper's numbers came from, and the four series were named by a person. Getting
    the two stages the wrong way round inverts the head difference without raising
    anything, so the warning is at the top rather than in a footnote.
    """
    rows = []
    for site in sites:
        entry = SITES[site]
        roles = ", ".join(f"{role}={tsid}" for tsid, (role, _p, _u)
                          in sorted(entry["series"].items(),   # type: ignore[union-attr]
                                    key=lambda item: ROLE_ORDER.index(item[1][0])))
        years = ", ".join(str(y) for y in entry["years"])       # type: ignore[union-attr]
        rows.append(f"| USGS {site} | {entry['name']} | {years} | {roles} |")
    return LAB_README.format(rows="\n".join(rows), out=out.replace("\\", "/"))


LAB_README = """\
# USGS canal observations — built with GateMPC's downloader

**This is not the GateMPC data package.** It was produced by
`scripts/download_usgs.py` with `--series` or `--years`, so its contents were
chosen by whoever ran that command, not by the study. In particular the four
series below were assigned to their roles by a person reading the archive's
free-text `sublocation_identifier` labels. If the headwater and the tailwater
are the wrong way round, the head difference changes sign and every number
computed from this package is wrong without anything failing. Check them.

| Site | Name | Years | Series roles |
|---|---|---|---|
{rows}

The layers, the column meanings and the checksum contract are the same as the
published package; its `DATA/USGS_canal_gates_v1/README.md` documents them. This
one verifies the same way:

    python scripts/download_usgs.py --verify --out {out}
"""


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
