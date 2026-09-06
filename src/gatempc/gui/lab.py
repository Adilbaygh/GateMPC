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
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from . import data as gdata

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
