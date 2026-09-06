"""Failure-mode tests for the USGS client.

Every test here exists because the behaviour it pins down was got wrong once
during development. The first version of the census script read
``payload.get("features", [])`` with no status check, so when the API began
refusing requests the error body — valid JSON, no ``features`` key — was read as
"this year has no data" and the emptiness was cached. Twelve real years and four
fabricated-empty years then looked identical.

The lesson generalises: a data pipeline must never be able to turn a failed
request into a plausible-looking empty result. These tests are the guard.

No network access: every test drives the client with a stub session.
"""
import json
import os
import sys

import pytest

from gatempc.usgs import FetchFailed, QuotaExhausted, UsgsClient, dump_json


class StubResponse:
    def __init__(self, status_code, body="", headers=None, json_body=None):
        self.status_code = status_code
        self.text = body
        self.headers = headers or {}
        self._json = json_body

    def json(self):
        if self._json is None:
            raise ValueError("no JSON object could be decoded")
        return self._json


def client(tmp_path, responses, **kw):
    """A client whose session returns ``responses`` in order."""
    c = UsgsClient(cache_dir=str(tmp_path / "cache"), log=lambda _m: None, **kw)
    c.session.get = lambda url, timeout=None: responses.pop(0)  # type: ignore[assignment]
    return c


FEATURE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {"properties": {"time_series_id": "abc", "time": "2020-01-01T00:00:00+00:00",
                        "value": "1.23", "approval_status": "Approved"}}
    ],
    "links": [],
}


def test_error_body_that_is_valid_json_raises_instead_of_looking_empty(tmp_path):
    """The original defect: a rate-limit body has no 'features' and must not pass."""
    c = client(tmp_path, [StubResponse(200, json_body={"code": "RateLimited",
                                                       "message": "too many requests"})])
    with pytest.raises(FetchFailed) as exc:
        c.observations("09522700", "45592", 2023)
    assert "FeatureCollection" in str(exc.value)


def test_a_failed_year_is_never_cached(tmp_path):
    """A failure must leave no artefact behind, or the next run inherits the lie."""
    c = client(tmp_path, [StubResponse(403, body="forbidden")])
    with pytest.raises(FetchFailed):
        c.observations("09522700", "45592", 2023)
    cache = tmp_path / "cache"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_http_403_raises(tmp_path):
    c = client(tmp_path, [StubResponse(403, body="forbidden")])
    with pytest.raises(FetchFailed):
        c.observations("09522700", "45592", 2023)


def test_non_json_response_raises(tmp_path):
    c = client(tmp_path, [StubResponse(200, body="<html>maintenance</html>")])
    with pytest.raises(FetchFailed):
        c.observations("09522700", "45592", 2023)


def test_quota_longer_than_max_wait_stops_instead_of_sleeping(tmp_path, monkeypatch):
    """A one-hour Retry-After must abort, never be slept through.

    The sleep is intercepted rather than timed: a version of the client that
    honours the hour would otherwise make this test hang for an hour before
    failing, and a test that can only fail after an hour does not protect
    anything in practice.
    """
    import time as _time

    def no_long_sleep(seconds):
        if seconds > 180.0:
            raise AssertionError(
                f"client tried to sleep {seconds:.0f} s; it must raise "
                f"QuotaExhausted instead of waiting out an hourly quota")

    monkeypatch.setattr("gatempc.usgs.time.sleep", no_long_sleep)
    c = client(tmp_path,
               [StubResponse(429, body="slow down", headers={"Retry-After": "3601"})],
               max_wait=180.0)
    started = _time.time()
    with pytest.raises(QuotaExhausted):
        c.observations("09522700", "45592", 2023)
    assert _time.time() - started < 5.0


def test_a_short_retry_after_is_honoured_then_the_request_succeeds(tmp_path):
    """Transient throttling should be waited out, not treated as fatal."""
    c = client(tmp_path,
               [StubResponse(429, body="slow", headers={"Retry-After": "0"}),
                StubResponse(200, json_body=FEATURE_COLLECTION)])
    records, _url, from_cache = c.observations("09522700", "45592", 2023)
    assert len(records) == 1 and from_cache is False


def test_a_genuinely_empty_year_is_cached_as_empty(tmp_path):
    """An empty result is trustworthy only because every request returned 200."""
    empty = {"type": "FeatureCollection", "features": [], "links": []}
    c = client(tmp_path, [StubResponse(200, json_body=empty)])
    records, _url, from_cache = c.observations("09522700", "00065", 2011)
    assert records == [] and from_cache is False
    # served from cache on the second call, with no session left to answer
    c.session.get = lambda url, timeout=None: pytest.fail("must not refetch")
    records, _url, from_cache = c.observations("09522700", "00065", 2011)
    assert records == [] and from_cache is True


def test_cache_round_trip_preserves_records(tmp_path):
    c = client(tmp_path, [StubResponse(200, json_body=FEATURE_COLLECTION)])
    first, _u, _f = c.observations("09522700", "45592", 2023)
    c.session.get = lambda url, timeout=None: pytest.fail("must not refetch")
    second, _u, from_cache = c.observations("09522700", "45592", 2023)
    assert first == second and from_cache is True


def test_records_are_sorted_so_two_runs_agree(tmp_path):
    """Order must not depend on how the API happened to interleave the series."""
    shuffled = {
        "type": "FeatureCollection",
        "links": [],
        "features": [
            {"properties": {"time_series_id": "b", "time": "2020-01-01T00:15:00+00:00",
                            "value": "2"}},
            {"properties": {"time_series_id": "a", "time": "2020-01-01T00:15:00+00:00",
                            "value": "1"}},
            {"properties": {"time_series_id": "a", "time": "2020-01-01T00:00:00+00:00",
                            "value": "0"}},
        ],
    }
    c = client(tmp_path, [StubResponse(200, json_body=shuffled)])
    records, _u, _f = c.observations("09522700", "45592", 2020)
    keys = [(r["time_series_id"], r["time"]) for r in records]
    assert keys == sorted(keys)


def test_dump_json_is_byte_stable(tmp_path):
    """Deterministic serialisation is what makes the checksums meaningful."""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    dump_json({"z": 1, "a": [3, 2, 1], "m": {"y": 0, "x": 9}}, str(a))
    dump_json({"m": {"x": 9, "y": 0}, "a": [3, 2, 1], "z": 1}, str(b))
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes().endswith(b"\n")


def test_year_query_uses_one_request_per_year(tmp_path):
    """limit=50000 returns a whole 15-minute year in a single page.

    Measured 2026-09-05: 34 929 records, no 'next' link; limit=100000 is
    rejected with HTTP 400. Paging at the default 10 000 would quadruple the
    request count against an hourly quota for no benefit.
    """
    url, params = UsgsClient.year_query("09522700", "45592", 2023)
    assert params["limit"] == 50000
    assert params["datetime"] == "2023-01-01T00:00:00Z/2023-12-31T23:59:59Z"
    assert "monitoring_location_id=USGS-09522700" in url
