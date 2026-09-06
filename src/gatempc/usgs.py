"""Client for the USGS OGC API ``continuous`` and ``time-series-metadata`` collections.

Design notes that are not obvious from the code
-----------------------------------------------
**A failed request is never mistaken for an empty archive.** Every response is
checked for HTTP status *and* for being a GeoJSON FeatureCollection. An error
body is often valid JSON without a ``features`` key, so reading ``.get("features",
[])`` would turn a rate-limit refusal into "this year has no data" and cache the
emptiness. That failure mode cost two ruined census runs during development and
is the reason for :class:`FetchFailed`.

**The API enforces an hourly quota.** Measured 2026-09-05: roughly 140 requests
in seven minutes triggers HTTP 429, and the ``Retry-After`` header can ask for a
full hour. Sleeping through that is useless, so a wait longer than ``max_wait``
raises :class:`QuotaExhausted` and the caller is expected to stop cleanly and
resume later. The disk cache makes resuming cheap.

**One request per series-year.** ``limit=50000`` returns a whole year of
15-minute data in a single page (measured: 34 929 records, no ``next`` link);
``limit=100000`` is rejected with HTTP 400. Paging at the default 10 000 would
quadruple the request count against that quota for no benefit.

**Cached payloads are stored verbatim and deterministically.** Keys are sorted so
that re-fetching writes identical bytes, which is what makes the data package its
own regression test.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlencode

import requests

BASE = "https://api.waterdata.usgs.gov/ogcapi/v0/collections"
ITEMS = BASE + "/continuous/items"
TS_METADATA = BASE + "/time-series-metadata/items"
FIELD_MEASUREMENTS = BASE + "/field-measurements/items"

PAGE_LIMIT = 50000
MIN_INTERVAL = 1.0
MAX_ATTEMPTS = 4
BACKOFF_BASE = 5.0
MAX_WAIT = 180.0
TIMEOUT = 300

LICENCE = (
    "USGS water data are public domain (U.S. Geological Survey, "
    "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)"
)


class FetchFailed(Exception):
    """A request could not be completed. Never swallowed, never cached."""


class QuotaExhausted(Exception):
    """The server asked for a wait longer than ``max_wait``. Stop and resume later."""


class UsgsClient:
    """Quota-aware, cache-backed reader for the USGS OGC API."""

    def __init__(
        self,
        cache_dir: str,
        user_agent: str = "GateMPC/0.1 (research; reproducibility package)",
        max_wait: float = MAX_WAIT,
        log: Callable[[str], None] = print,
    ) -> None:
        self.cache_dir = cache_dir
        self.max_wait = max_wait
        self.log = log
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last_call = 0.0
        self.requests_made = 0

    # ---------------------------------------------------------------- transport

    def _get(self, url: str) -> dict[str, Any]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            gap = MIN_INTERVAL - (time.time() - self._last_call)
            if gap > 0:
                time.sleep(gap)
            try:
                resp = self.session.get(url, timeout=TIMEOUT)
                self.requests_made += 1
            except requests.RequestException as exc:
                if attempt == MAX_ATTEMPTS:
                    raise FetchFailed(f"network error after {attempt} attempts: {exc}")
                time.sleep(min(self.max_wait, BACKOFF_BASE * 2 ** (attempt - 1)))
                continue
            finally:
                self._last_call = time.time()

            if resp.status_code == 429 or resp.status_code >= 500:
                delay = BACKOFF_BASE * 2 ** (attempt - 1)
                try:
                    delay = max(delay, float(resp.headers.get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
                if delay > self.max_wait:
                    raise QuotaExhausted(
                        f"HTTP {resp.status_code}; the server asked for {delay:.0f} s "
                        f"({delay / 3600:.1f} h). Everything fetched so far is cached; "
                        f"rerun the same command after that window."
                    )
                if attempt == MAX_ATTEMPTS:
                    raise FetchFailed(f"HTTP {resp.status_code} after {attempt} attempts")
                self.log(f"    HTTP {resp.status_code}, waiting {delay:.0f} s "
                         f"(attempt {attempt}/{MAX_ATTEMPTS})")
                time.sleep(delay)
                continue

            if resp.status_code != 200:
                raise FetchFailed(f"HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise FetchFailed(f"response was not JSON: {exc}")
            # An error body can be valid JSON without being a feature collection.
            # Accepting it here is exactly the defect described in the module docstring.
            if payload.get("type") != "FeatureCollection" or "features" not in payload:
                raise FetchFailed(
                    f"not a FeatureCollection: keys={sorted(payload)[:8]}")
            return payload
        raise FetchFailed("exhausted attempts")

    # ---------------------------------------------------------------- cache

    def _cache_path(self, name: str) -> str:
        return os.path.join(self.cache_dir, name + ".json")

    def _read_cache(self, name: str) -> list[dict[str, Any]] | None:
        path = self._cache_path(name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
        except ValueError:
            os.remove(path)
            self.log(f"    unreadable cache discarded: {os.path.basename(path)}")
            return None
        if isinstance(blob, dict) and "records" in blob:
            return blob["records"]
        os.remove(path)
        self.log(f"    cache in an unknown format discarded: {os.path.basename(path)}")
        return None

    def _write_cache(self, name: str, records: list[dict[str, Any]], query: str) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        path = self._cache_path(name)
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"query": query, "records": records}, fh,
                      sort_keys=True, ensure_ascii=False)
        os.replace(tmp, path)

    # ---------------------------------------------------------------- queries

    @staticmethod
    def year_query(site: str, parameter_code: str, year: int) -> tuple[str, dict[str, Any]]:
        params = {
            "monitoring_location_id": f"USGS-{site}",
            "parameter_code": parameter_code,
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
            "limit": PAGE_LIMIT,
            "f": "json",
        }
        return ITEMS + "?" + urlencode(params), params

    def observations(self, site: str, parameter_code: str, year: int
                     ) -> tuple[list[dict[str, Any]], str, bool]:
        """Observation properties for one site/parameter/year.

        Returns ``(records, request_url, from_cache)``. Records are the GeoJSON
        ``properties`` objects verbatim; geometry is dropped because it repeats
        the monitoring-location coordinates on every one of ~35 000 rows.

        A year is cached only when every request behind it succeeded, so a cached
        empty year is provably empty rather than provably broken.
        """
        name = f"{site}_{parameter_code}_{year}"
        url, _ = self.year_query(site, parameter_code, year)
        cached = self._read_cache(name)
        if cached is not None:
            return cached, url, True

        records: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            payload = self._get(next_url)
            records.extend(f["properties"] for f in payload["features"])
            nxt = [l["href"] for l in payload.get("links", []) if l.get("rel") == "next"]
            next_url = nxt[0] if nxt else None
        records.sort(key=lambda r: (r.get("time_series_id", ""), r.get("time", "")))
        self._write_cache(name, records, url)
        return records, url, False

    def time_series_metadata(self, site: str) -> tuple[list[dict[str, Any]], str, bool]:
        """Time-series metadata for one site, including ``sublocation_identifier``.

        That field is what distinguishes the two ``00065`` stage series as
        H1 (Headwater) and H2 (Tailwater); guessing from the values would be an
        assumption, and this makes it a measurement.
        """
        name = f"{site}_tsmeta"
        params = {"monitoring_location_id": f"USGS-{site}", "limit": 100, "f": "json"}
        url = TS_METADATA + "?" + urlencode(params)
        cached = self._read_cache(name)
        if cached is not None:
            return cached, url, True
        payload = self._get(url)
        records = [f["properties"] for f in payload["features"]]
        records.sort(key=lambda r: (r.get("parameter_code", ""), r.get("id", "")))
        self._write_cache(name, records, url)
        return records, url, False


    def field_measurements(self, site: str) -> tuple[list[dict[str, Any]], str, bool]:
        """Discrete field discharge measurements -- the INDEPENDENT observations.

        This matters more than it looks. The continuous ``00060`` series at a
        gated structure is a rating output: it is computed from the gate opening
        and the two stages. These field measurements are not. They are made with
        a current profiler on a site visit, and the rating is calibrated to them.
        Testing a gate law against the continuous series therefore only recovers
        the rating's own coefficient; testing it against these is the honest
        comparison. See requirements/hypotheses.md H4.
        """
        name = f"{site}_gaugings"
        params = {"monitoring_location_id": f"USGS-{site}",
                  "parameter_code": "00060", "limit": 10000, "f": "json"}
        url = FIELD_MEASUREMENTS + "?" + urlencode(params)
        cached = self._read_cache(name)
        if cached is not None:
            return cached, url, True
        payload = self._get(url)
        records = [f["properties"] for f in payload["features"]
                   if f["properties"].get("reading_type") == "Discharge"]
        records.sort(key=lambda r: (r.get("time", ""), r.get("field_visit_id", "")))
        self._write_cache(name, records, url)
        return records, url, False


def dump_json(obj: Any, path: str) -> None:
    """Write JSON so that two runs produce identical bytes."""
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, sort_keys=True, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
