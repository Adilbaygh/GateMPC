"""Shared pieces for the three pages that compute rather than display.

Two rules hold everywhere in the laboratory:

* nothing it produces is written into ``results/``. A published number is what a
  published script wrote with its registered parameters; anything computed from a
  form belongs somewhere else, and :func:`lab_directory` is where it goes.
* the arithmetic is the package's own. The calculator uses ``gatempc.canal.GateLaw``,
  the detector uses ``gatempc.detector``, and the experiment page runs
  ``scripts/control_comparison.py`` as a subprocess. Nothing is reimplemented for the
  window, because a second implementation is a second answer waiting to happen.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .. import results as gdata

FT = 0.3048          # exact, by definition
FT3 = FT ** 3        # exact
G_ACCEL = 9.80665    # m/s2, standard gravity


def lab_directory(paths: gdata.ProjectPaths) -> Path:
    """Where a run started from a form writes its output.

    ``build/`` is excluded from the public repository, so an exploratory run can
    never be mistaken for a published result or committed as one.
    """
    directory = paths.root / "build" / "lab"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def stamped(prefix: str, suffix: str) -> str:
    moment = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{moment}{suffix}"


# ------------------------------------------------------------------------ units

#: (key, label, factor to SI) for the two length conventions in play.
LENGTH_UNITS = (("m", "m", 1.0), ("ft", "ft", FT))
FLOW_UNITS = (("m3s", "m³/s", 1.0), ("ft3s", "ft³/s", FT3))


def to_si(value: float, factor: float) -> float:
    return value * factor


def from_si(value: float, factor: float) -> float:
    return value / factor if factor else float("nan")


# ------------------------------------------------------------------------- laws


def laws_from_results(results: gdata.Results):
    """The two gate laws the manuscript compares, read from ``results/gate_law.json``.

    Returns ``(identified, ideal, problem)``. ``problem`` is a string when the
    result file is not there yet, so the page can say so instead of inventing
    coefficients.
    """
    from ..canal import GateLaw  # imported here so this module stays import-cheap

    gamma = results.value("gate_law:full_fit.gamma_m")
    alpha = results.value("gate_law:full_fit.alpha")
    beta = results.value("gate_law:full_fit.beta")
    ideal_gamma = results.value("gate_law:ideal_law_same_sill.gamma_m")
    for found in (gamma, alpha, beta, ideal_gamma):
        if not found.ok:
            return None, None, found.problem or f"{found.source} is missing"
    identified = GateLaw(float(gamma.value), float(alpha.value), float(beta.value),
                         "identified")
    ideal = GateLaw(float(ideal_gamma.value), 1.0, 0.5, "ideal")
    return identified, ideal, ""


def observed_range(results: gdata.Results) -> tuple[tuple[float, float] | None,
                                                    tuple[float, float] | None]:
    """The opening and head ranges the archive actually contains, in metres.

    The calculator warns outside them. A power law will happily return a number
    for any input; whether that number means anything is a different question,
    and this is the honest boundary of what was measured.
    """
    a_range = results.value(
        "model_error_envelope:envelopes.observed_wellton_mohawk.a_range_m")
    dh_range = results.value(
        "model_error_envelope:envelopes.observed_wellton_mohawk.dh_range_m")

    def pair(found):
        value = found.value if found.ok else None
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return float(value[0]), float(value[1])
        return None

    return pair(a_range), pair(dh_range)


def kappa_of(q: float, a: float, dh: float) -> float | None:
    """The detector statistic, for a single point typed into a form."""
    import math

    if a <= 0 or dh <= 0:
        return None
    return q / (a * math.sqrt(2 * G_ACCEL * dh))


# ------------------------------------------------------------------------- CSV


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))
    return path


class ColumnMappingError(ValueError):
    """The reader's file does not carry what the detector needs."""


def samples_from_csv(path: Path, mapping: dict[str, str],
                     length_factor: float, flow_factor: float):
    """Build detector samples from a reader's own file.

    ``mapping`` names which column holds the time, the opening, the two stages and
    the discharge. Rows with a blank in any of the five are skipped, exactly as the
    archive reader skips them: a blank means the series has no value there, which is
    not the same as a zero.

    Returns ``(samples, skipped)`` so the page can report how much of the file was
    unusable rather than silently shrinking it.
    """
    from ..archive import Sample

    needed = ("time", "a", "h1", "h2", "q")
    missing = [key for key in needed if not mapping.get(key)]
    if missing:
        raise ColumnMappingError("no column chosen for: " + ", ".join(missing))

    samples: list[Sample] = []
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ColumnMappingError("the file has no header row")
        unknown = [mapping[key] for key in needed if mapping[key] not in reader.fieldnames]
        if unknown:
            raise ColumnMappingError("column not in the file: " + ", ".join(unknown))
        for row in reader:
            values = {key: (row.get(mapping[key]) or "").strip() for key in needed}
            if not all(values.values()):
                skipped += 1
                continue
            try:
                a = max(float(values["a"]), 0.0) * length_factor
                h1 = float(values["h1"]) * length_factor
                h2 = float(values["h2"]) * length_factor
                q = float(values["q"]) * flow_factor
            except ValueError:
                skipped += 1
                continue
            samples.append(Sample(values["time"], a, h1, h2, q))
    if not samples:
        raise ColumnMappingError(
            "no row had all five values; check the column choices and the units")
    return samples, skipped


def csv_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            return [cell.strip() for cell in row]
    return []


# --------------------------------------------------------------- data package


def package_site_years(paths: gdata.ProjectPaths,
                       package: Path | None = None) -> list[tuple[str, int]]:
    """Every ``<site>_<year>.csv`` in a data package, sorted."""
    directory = (package or paths.data_package) / "observations"
    if not directory.is_dir():
        return []
    found: list[tuple[str, int]] = []
    for path in directory.glob("*_[0-9][0-9][0-9][0-9].csv"):
        site, _, year = path.stem.rpartition("_")
        if site and year.isdigit():
            found.append((site, int(year)))
    return sorted(found)


def lab_packages(paths: gdata.ProjectPaths) -> list[Path]:
    """Packages a fetch started from the window wrote.

    They land under :func:`lab_directory` for the same reason everything else from
    a form does: a package fetched here is not the published one, and must not be
    able to look like it or to overwrite it.
    """
    directory = paths.root / "build" / "lab"
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("package_*")
                  if (path / "observations").is_dir())


def available_folds(paths: gdata.ProjectPaths) -> list[tuple[Path, str, int]]:
    """Every site-year the window can read, and which package each came from.

    The published package first, then anything fetched from the window. The
    package travels with the site and year because the two kinds live in
    different directories and the reader is entitled to know which is which.
    """
    found = [(paths.data_package, site, year)
             for site, year in package_site_years(paths)]
    for package in lab_packages(paths):
        found += [(package, site, year)
                  for site, year in package_site_years(paths, package)]
    return found


def registered_sites(paths: gdata.ProjectPaths) -> dict[str, dict]:
    """The sites ``download_usgs.py`` fetches, and the years of each, from that script.

    A station's four series are bound to their roles by hand: which of two
    identical stage series is the headwater is not something the downloader can
    work out, so it refuses a site it has not been taught —

        for s in sites:
            if s not in SITES:
                return _fail(f"unknown site {s}; known: {', '.join(SITES)}")

    — and the window must therefore offer exactly what the script accepts. The
    years are registered the same way and are not a choice either: they are the
    years the archive carries all four series for, which ``coverage_census.csv``
    in the data package reports year by year for the whole record. The registry
    is read from the script rather than copied here: two lists that can disagree
    are worse than one that cannot. A missing or broken script gives an empty
    registry and the page hides the offer, rather than taking the window down
    with it.

    Returns ``{site: {"name": str, "years": tuple[int, ...]}}``.
    """
    module = downloader(paths)
    if module is None:
        return {}
    registry = getattr(module, "SITES", None)
    if not isinstance(registry, dict):
        return {}
    found: dict[str, dict] = {}
    for site, entry in registry.items():
        if not isinstance(entry, dict):
            continue
        years = entry.get("years", ())
        found[str(site)] = {
            "name": str(entry.get("name", "")),
            "years": tuple(int(year) for year in years) if isinstance(
                years, (list, tuple)) else (),
            "series": {},
            "source": "registry",
        }
    return found


def downloader(paths: gdata.ProjectPaths):
    """``scripts/download_usgs.py`` as a module, or ``None`` if it cannot be read.

    The window borrows three things from the script — the site registry, the role
    proposal and the parameter codes — rather than keeping copies that could drift
    away from it. A broken or missing script disables the offer instead of taking
    the window down.
    """
    import importlib.util

    script = paths.scripts / "download_usgs.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("gatempc_downloader", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


# ------------------------------------------------------- stations you added


#: Where an assignment the reader made is remembered. Under ``build/lab`` with
#: everything else from a form: it is not part of the published package and must
#: never be able to look like it.
STATIONS = "stations.json"


def stations_path(paths: gdata.ProjectPaths) -> Path:
    return paths.root / "build" / "lab" / STATIONS


def read_stations(paths: gdata.ProjectPaths) -> dict[str, dict]:
    """Stations the reader looked up and assigned roles to, in the same shape.

    A file that is missing, unreadable or malformed gives an empty result rather
    than an exception: this is a convenience store, and losing it costs a lookup,
    not a result.
    """
    path = stations_path(paths)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    found: dict[str, dict] = {}
    for site, entry in loaded.items():
        if not isinstance(entry, dict):
            continue
        series, years = entry.get("series"), entry.get("years")
        if not isinstance(series, dict) or not isinstance(years, (list, tuple)):
            continue
        try:
            found[str(site)] = {
                "name": str(entry.get("name", "")),
                "years": tuple(int(year) for year in years),
                "series": {str(role): str(tsid) for role, tsid in series.items()},
                "source": "you",
            }
        except (TypeError, ValueError):
            continue
    return found


def write_station(paths: gdata.ProjectPaths, site: str, name: str,
                  years: Sequence[int], series: dict[str, str]) -> Path:
    """Remember one assignment, with the moment it was made.

    The timestamp is not decoration. The roles here were decided by a person
    reading a free-text label, and if a later result looks wrong the first
    question is which assignment produced it and when.
    """
    path = stations_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    stations: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            stations = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            stations = {}
    stations[str(site)] = {
        "name": name,
        "years": [int(year) for year in years],
        "series": {str(role): str(tsid) for role, tsid in series.items()},
        "assigned_utc": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path.write_text(json.dumps(stations, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def known_sites(paths: gdata.ProjectPaths) -> dict[str, dict]:
    """Everything the window can fetch: the script's registry, then yours.

    A site the script already carries is never shadowed by a stored assignment.
    The published registry is the one the study stands behind, and a stale entry
    in ``build/lab`` must not be able to quietly replace it.
    """
    found = registered_sites(paths)
    for site, entry in read_stations(paths).items():
        if site not in found:
            found[site] = entry
    return found


def lookup_station(paths: gdata.ProjectPaths, site: str):
    """Ask the archive what a station publishes; propose the four roles.

    Returns ``(records, proposal, problems, url, from_cache)``. This is the one
    place in the window that goes to the network, and it goes for exactly one
    request. The proposal comes from the downloader's own ``propose_roles`` so
    that the window and the command line cannot disagree about what a station
    can offer.
    """
    module = downloader(paths)
    if module is None:
        raise RuntimeError("scripts/download_usgs.py could not be read")
    from ..usgs import UsgsClient

    client = UsgsClient(str(paths.root / "DATA" / ".raw_cache"))
    records, url, from_cache = client.time_series_metadata(site)
    proposal, problems = module.propose_roles(records)
    return records, proposal, problems, url, from_cache


def advertised_years(records: Sequence[dict], chosen: dict[str, str]) -> tuple[int, ...]:
    """The years the four chosen series claim to overlap in.

    An upper bound and nothing more. ``begin`` is what the archive advertises for
    a series, and this project already knows it overstates: at the primary
    structure the gate series reports a begin of 2007 while stage is absent until
    2017, which is the whole reason ``coverage_census.csv`` exists. So this bounds
    the year boxes and the fetch reports, year by year, what was really there.
    """
    by_id = {str(record.get("id") or ""): record for record in records}
    starts: list[int] = []
    stops: list[int] = []
    for tsid in chosen.values():
        record = by_id.get(tsid)
        if record is None:
            return ()
        begin, end = str(record.get("begin") or "")[:4], str(record.get("end") or "")[:4]
        if not (begin.isdigit() and end.isdigit()):
            return ()
        starts.append(int(begin))
        stops.append(int(end))
    if not starts or max(starts) > min(stops):
        return ()
    return tuple(range(max(starts), min(stops) + 1))


def years_as_text(years: Sequence[int]) -> str:
    """``(2018, …, 2025)`` -> ``2018–2025``; anything gappy is listed in full."""
    ordered = sorted(set(int(year) for year in years))
    if not ordered:
        return ""
    if len(ordered) == 1:
        return str(ordered[0])
    if ordered[-1] - ordered[0] + 1 == len(ordered):
        return f"{ordered[0]}–{ordered[-1]}"
    return ", ".join(str(year) for year in ordered)
