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


# --------------------------------------------------- adding a station by hand
#
# The downloader accepts a site the registry does not hold, but only under terms
# that keep the published package out of reach. None of these tests goes near the
# network: every one of them is refused, or answered, before a request is made.


def downloader():
    """Import ``scripts/download_usgs.py`` as a module, with a pristine registry."""
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "scripts", "download_usgs.py")
    spec = importlib.util.spec_from_file_location("gatempc_downloader_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(module, *arguments):
    """Drive ``main()`` with an argument list and hand back its exit code."""
    argv = sys.argv
    sys.argv = ["download_usgs.py", *arguments]
    try:
        return module.main()
    finally:
        sys.argv = argv


def test_the_default_command_is_unchanged_by_the_exploratory_flags():
    """The flags are additive: with none of them, nothing about the run moved.

    This is the test that lets the published package stay reproducible while the
    script learns to fetch somewhere else. If a later edit changes the default
    sites, their years, or where they are written, it fails here rather than in a
    checksum mismatch nobody can explain.
    """
    module = downloader()
    assert set(module.SITES) == {"09522700", "09428500"}
    assert list(module.SITES["09522700"]["years"]) == list(range(2018, 2026))
    assert list(module.SITES["09428500"]["years"]) == [2026]
    assert module.DEFAULT_OUT.replace("\\", "/").endswith("DATA/USGS_canal_gates_v1")
    for site, entry in module.SITES.items():
        roles = sorted(role for role, _p, _u in entry["series"].values())
        assert roles == sorted(module.ROLE_ORDER), site


def test_the_exploratory_flags_refuse_the_published_package():
    """A package built from someone's own choices must not land where the paper's is."""
    module = downloader()
    assert run(module, "--years", "2024") == 1
    assert run(module, "--sites", "09429000", "--series",
               "gate_opening=a,headwater=b,tailwater=c,discharge=d",
               "--years", "2024") == 1
    assert set(module.SITES) == {"09522700", "09428500"}, "the registry was touched"


def test_a_registered_site_cannot_be_redefined(tmp_path):
    """--series on a published site would change what that site's package means."""
    module = downloader()
    assert run(module, "--sites", "09522700", "--series",
               "gate_opening=a,headwater=b,tailwater=c,discharge=d",
               "--years", "2024", "--out", str(tmp_path / "p")) == 1
    assert module.SITES["09522700"]["series"], "the registered series were replaced"


def test_an_added_site_has_to_name_its_years(tmp_path):
    """Most years at most stations do not carry all four series; silence is not a range."""
    module = downloader()
    assert run(module, "--sites", "09429000", "--series",
               "gate_opening=a,headwater=b,tailwater=c,discharge=d",
               "--out", str(tmp_path / "p")) == 1


def test_all_four_roles_are_required_and_named_correctly():
    module = downloader()
    with pytest.raises(ValueError, match="tailwater, discharge"):
        module.parse_series("gate_opening=a,headwater=b")
    with pytest.raises(ValueError, match="unknown role"):
        module.parse_series("upstream=a,headwater=b,tailwater=c,discharge=d")
    with pytest.raises(ValueError, match="given twice"):
        module.parse_series("headwater=a,headwater=b,tailwater=c,discharge=d")
    with pytest.raises(ValueError, match="no time-series id"):
        module.parse_series("gate_opening=,headwater=b,tailwater=c,discharge=d")
    mapping = module.parse_series(
        "gate_opening=aa73,headwater=373d,tailwater=4b39,discharge=d3ec")
    assert mapping["aa73"] == ("gate_opening", "45592", "")
    assert mapping["373d"][1] == mapping["4b39"][1] == "00065", (
        "the two stages share a parameter code; that is why they need labels"
    )


def test_a_year_range_is_read_and_a_bad_one_is_refused():
    module = downloader()
    assert module.parse_years("2018-2021") == [2018, 2019, 2020, 2021]
    assert module.parse_years("2024,2026") == [2024, 2026]
    assert module.parse_years(" 2026 ") == [2026]
    for bad in ("2026-2024", "", "twenty", "1900-2026"):
        with pytest.raises(ValueError):
            module.parse_years(bad)


# Records shaped as the archive returned them for the three sites below, so that
# what these tests assert is what the API actually says. That is not decoration:
# the first version of PALO_VERDE was invented rather than read, marked one of
# the two discharge series Primary and the other not, and so let the proposer's
# "none is marked Primary" pass a test at a site where BOTH carry it.

PALO_VERDE = [   # USGS 09429000, Palo Verde Canal near Blythe, CA, read 2026-09-06
    {"id": "802340bb2ae94dd4a9a06cb30c5d2911", "parameter_code": "00060",
     "sublocation_identifier": None, "primary": "Primary",
     "begin": "2022-10-06T07:00:00", "end": "2026-09-06T00:00:00"},
    {"id": "8adc2c0ff7584f9e8a3b988c6231e809", "parameter_code": "00060",
     "sublocation_identifier": None, "primary": "Primary",
     "begin": "1950-10-01T08:00:00", "end": "2026-09-05T00:00:00"},
    {"id": "dc99134088034c49bba6a844c75324ff", "parameter_code": "00065",
     "sublocation_identifier": None, "primary": "Primary",
     "begin": "2022-10-06T07:00:00", "end": "2026-09-06T00:00:00"},
    {"id": "a3be319abedc468493f67449f7732863", "parameter_code": "72254",
     "primary": "Primary"},
    {"id": "d42916019cc54d3cb562e65a9f557533", "parameter_code": "72255",
     "primary": "Primary"},
]

# USGS 09428500, the published package's second structure, from its own
# time_series_metadata.csv. Only the discharge series carries Primary here, so
# this is the case where that column settles nothing — and does not need to,
# because every role has exactly one candidate.
CRIR = [
    {"id": "190daf8903e04cc5a2d22c9662607e6f", "parameter_code": "45592",
     "sublocation_identifier": None, "primary": ""},
    {"id": "aa6d169214d14ad1979eacd6943737b3", "parameter_code": "00065",
     "sublocation_identifier": "H1 (Headwater)", "primary": ""},
    {"id": "14eef6ee402b4c50a7341a0efccf0cd4", "parameter_code": "00065",
     "sublocation_identifier": "H2 (Tailwater)", "primary": ""},
    {"id": "52737a6ed1904f7c9763e451cea6307f", "parameter_code": "00060",
     "sublocation_identifier": None, "primary": "Primary"},
]

WELLTON_MOHAWK = [   # USGS 09522700, the shape a usable structure has
    {"id": "aa7306544e844561ad2ccf2476f7ca58", "parameter_code": "45592",
     "sublocation_identifier": "Gate Opening", "primary": "Primary"},
    {"id": "373d93c6f7d24462aae0c5e9b3056415", "parameter_code": "00065",
     "sublocation_identifier": "H1 (Headwater)", "primary": "Primary"},
    {"id": "4b3972dec3cc43beb1c05be12b7804f7", "parameter_code": "00065",
     "sublocation_identifier": "H2 (Tailwater)", "primary": "Primary"},
    {"id": "d3ec91292d17403397678bc7ed056f2d", "parameter_code": "00060",
     "sublocation_identifier": None, "primary": "Primary"},
]


def test_a_usable_structure_gets_all_four_roles_proposed():
    module = downloader()
    proposal, problems = module.propose_roles(WELLTON_MOHAWK)
    assert set(proposal) == set(module.ROLE_ORDER)
    assert proposal["headwater"].startswith("373d")
    assert proposal["tailwater"].startswith("4b39")
    assert problems == []


def test_a_station_without_the_four_series_is_told_so_rather_than_guessed_at():
    """09429000 is a real canal station that the detector cannot use.

    It publishes discharge, one stage and two velocities, and no gate opening at
    all. The lookup has to say that in words, because the alternative is a reader
    spending an hour of quota to discover it from an empty package.
    """
    module = downloader()
    proposal, problems = module.propose_roles(PALO_VERDE)
    assert "gate_opening" not in proposal
    assert any("45592" in p for p in problems)
    assert any("two, a headwater and a tailwater" in p for p in problems)
    # The wording has to match the archive: both discharge series carry Primary,
    # so neither "the one marked Primary" nor "none marked Primary" is true here.
    assert "discharge" not in proposal
    assert any("2 discharge series, all 2 of them marked Primary" in p
               for p in problems), problems


def test_the_second_published_structure_is_proposed_without_help_from_primary():
    """Every role has one candidate at 09428500, and Primary settles nothing there."""
    module = downloader()
    proposal, problems = module.propose_roles(CRIR)
    assert set(proposal) == set(module.ROLE_ORDER)
    assert proposal["headwater"].startswith("aa6d1692")
    assert proposal["tailwater"].startswith("14eef6ee")
    assert proposal["gate_opening"].startswith("190daf89")
    assert problems == []


def test_unlabelled_stages_are_not_guessed_at():
    """Which stage is the headwater is a claim about the world, not a coin toss."""
    module = downloader()
    records = [
        {"id": "1" * 32, "parameter_code": "45592"},
        {"id": "2" * 32, "parameter_code": "00060"},
        {"id": "3" * 32, "parameter_code": "00065", "sublocation_identifier": "A"},
        {"id": "4" * 32, "parameter_code": "00065", "sublocation_identifier": "B"},
    ]
    proposal, problems = module.propose_roles(records)
    assert "headwater" not in proposal and "tailwater" not in proposal
    assert any("not labelled clearly enough" in p for p in problems)


def test_an_id_that_matches_nothing_stops_the_run_before_anything_is_written():
    """The defect this guards was real: a placeholder id built an empty package.

    Pasting the printed template verbatim gave every role the id ``<id>``. The
    run matched no series, wrote an empty metadata layer, an empty observation
    file per year and a set of checksums, reported success, and spent 49 requests
    against a 140-per-hour quota doing it.
    """
    module = downloader()
    module.SITES["09429000"] = {
        "name": "test", "role": "test", "years": [2024],
        "series": module.parse_series(
            "gate_opening=<id>,headwater=<id>,tailwater=<id>,discharge=<id>"),
    }
    rows = [["09429000", record["id"], record["parameter_code"]] + [""] * 9
            for record in PALO_VERDE]
    message = module.unresolved_series(["09429000"], rows)
    assert "nothing in the archive matches" in message
    assert "nothing was written" in message


def test_an_ambiguous_id_prefix_stops_the_run_too():
    """Two series behind one prefix is not a fetch, it is a coin toss."""
    module = downloader()
    module.SITES["09429000"] = {
        "name": "test", "role": "test", "years": [2024],
        "series": module.parse_series(
            "gate_opening=aa,headwater=bb,tailwater=cc,discharge=8"),
    }
    rows = [["09429000", record["id"], record["parameter_code"]] + [""] * 9
            for record in PALO_VERDE]
    message = module.unresolved_series(["09429000"], rows)
    assert "matches" in message and "nothing was written" in message
