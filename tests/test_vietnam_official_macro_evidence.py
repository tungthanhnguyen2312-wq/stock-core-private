import base64
import hashlib
from email.message import Message
from pathlib import Path

import pytest

import stocklookup_core.evidence.vietnam_official_macro_evidence as nso
from current_macro_regime import build as build_macro, session_context
from stocklookup_core.evidence.vietnam_official_macro_evidence import build, content_identity, current_macro_observations


def raw(source_id, body, locator):
    return {"source_id": source_id, "locator": locator, "retrieval_timestamp": "2026-08-24T00:00:00Z", "publication_date": None, "content_type": "text/html", "payload_sha256": hashlib.sha256(body.encode()).hexdigest(), "payload_base64": base64.b64encode(body.encode()).decode(), "parse_status": "RETAINED_UNPARSED"}


def test_nso_cpi_is_source_bound_replayable_and_has_no_generic_freshness_days():
    june = "<p>The Consumer Price Index (CPI) in June 2026 rose by 4.69% year-on-year.</p><p>Reference period: 6/2026 Date of issue: 03/07/2026</p>"
    july = "<p>The consumer price index (CPI) in July 2026 rose by 4.45% over the same period last year.</p><p>Reference period: 7/2026 Date of issue: 03/08/2026</p>"
    calendar = "<p>Next releases 03/9/2026: Consumer price index, gold, and USD price indexes in August 2026</p>"
    artifact = build(raw_records=[raw("NSO_VIETNAM_CPI_RELEASE", june, "https://nso.example/june"), raw("NSO_VIETNAM_CPI_RELEASE", july, "https://nso.example/july"), raw("NSO_RELEASE_CALENDAR", calendar, "https://nso.example/")], retrieved_at="2026-08-24T00:00:00Z")
    assert content_identity(artifact)["artifact_identity"] == artifact["artifact_identity"]
    assert [row["value"] for row in artifact["observations"]["vn_cpi_yoy"]] == [4.69, 4.45]
    assert artifact["freshness_rules"]["vn_cpi_yoy"]["next_expected_official_release"] == "2026-09-03"
    assert "generic day" in artifact["freshness_rules"]["vn_cpi_yoy"]["rule"].lower()
    assert artifact["revisions_retained"]["revision_payloads"] == 0


def test_adapter_does_not_turn_missing_into_zero_or_infer_a_change():
    body = "<p>The Consumer Price Index (CPI) in July 2026 rose by 4.45% over the same period last year.</p><p>Reference period: 7/2026 Date of issue: 03/08/2026</p>"
    artifact = build(raw_records=[raw("NSO_VIETNAM_CPI_RELEASE", body, "https://nso.example/july")], retrieved_at="2026-08-24T00:00:00Z")
    macro = build_macro(observations=current_macro_observations(artifact), raw_sources=[], retrieved_at="2026-08-24T00:00:00Z")
    assert macro["observations"]["vn_cpi_yoy"]["value"] == 4.45
    assert macro["observations"]["vn_policy_rate"]["value"] is None
    assert macro["state_axes"]["INFLATION_PRESSURE"]["state"] == "UNKNOWN"
    assert session_context(macro, "2026-08-21")["status"] == "UNAVAILABLE"


def test_cpi_becomes_stale_at_its_retained_next_release_not_a_generic_age_limit():
    body = "<p>The Consumer Price Index (CPI) in July 2026 rose by 4.45% over the same period last year.</p><p>Reference period: 7/2026 Date of issue: 03/08/2026</p>"
    calendar = "<p>Next releases 03/9/2026: Consumer price index, gold, and USD price indexes in August 2026</p>"
    artifact = build(raw_records=[raw("NSO_VIETNAM_CPI_RELEASE", body, "https://nso.example/july"), raw("NSO_RELEASE_CALENDAR", calendar, "https://nso.example/")], retrieved_at="2026-09-03T00:00:00Z")
    assert artifact["freshness_rules"]["vn_cpi_yoy"]["status"] == "STALE_OR_UNAVAILABLE"


# --- NSO_CPI_ACQUISITION_PARSER_FRESHNESS_CORRECTIVE_20261023: exact retained official bytes ---
FIXTURES = Path(__file__).parent / "fixtures" / "nso_cpi"
JUNE_URL, JULY_URL = nso.NSO_CPI_RELEASES
SEPT_URL = "https://www.nso.gov.vn/en/data-and-statistics/2026/10/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-september-2026-q3-2026-and-the-nine-months-of-2026/"
HOMEPAGE_SHA = "8106772719386ad3025095e98134eec2fa8096ce0aa9e6fc7b98da7011529944"
PROVENANCE = {"source_id": "NSO_RELEASE_CALENDAR", "locator": nso.NSO_HOMEPAGE, "payload_sha256": HOMEPAGE_SHA}
RETRIEVED = "2026-10-22T11:03:45Z"
CUTOFF = "2026-10-22T18:30:00+07:00"


def fixture_record(name, source_id, locator, retrieved=RETRIEVED, body=None, discovered_from=None):
    data = body if body is not None else (FIXTURES / name).read_bytes()
    return nso._raw_record(source_id=source_id, url=locator, raw=data, content_type="text/html", retrieved_at=retrieved, http_status=200, discovered_from=discovered_from)


def homepage(retrieved=RETRIEVED):
    return fixture_record("homepage_20261022.html", "NSO_RELEASE_CALENDAR", nso.NSO_HOMEPAGE, retrieved)


def sept(retrieved=RETRIEVED, body=None):
    return fixture_record("cpi_2026-09_release.html", nso.SOURCE_ID, SEPT_URL, retrieved, body, PROVENANCE)


def june_july(retrieved=RETRIEVED):
    return [fixture_record("cpi_2026-06_release.html", nso.SOURCE_ID, JUNE_URL, retrieved), fixture_record("cpi_2026-07_release.html", nso.SOURCE_ID, JULY_URL, retrieved)]


def synthetic(body, locator="https://nso.example/sep"):
    return fixture_record("", nso.SOURCE_ID, locator, body=body.encode())


def test_fixture_bytes_are_the_retained_official_payloads():
    sums = {name: digest for digest, name in (line.split(" *") for line in (FIXTURES / "SHA256SUMS").read_text().splitlines())}
    assert {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() for name in sums} == sums
    assert sums["homepage_20261022.html"] == HOMEPAGE_SHA


def test_real_june_july_september_releases_parse_with_distinct_yoy_and_mom():
    artifact = build(raw_records=[*june_july(), sept(), homepage()], retrieved_at=RETRIEVED)
    rows = {row["observation_period"]: row for row in artifact["observations"]["vn_cpi_yoy"]}
    assert {period: row["value"] for period, row in rows.items()} == {"2026-06": 4.69, "2026-07": 4.45, "2026-09": 5.08}
    assert {period: row["month_on_month"]["value"] for period, row in rows.items()} == {"2026-06": -0.39, "2026-07": -0.12, "2026-09": 0.62}
    september = rows["2026-09"]
    assert (september["publication_date"], september["locator"]) == ("2026-10-03", SEPT_URL)
    assert september["raw_payload_sha256"] == "c0ac16c747c1b99b880b125783686ccbacf688744b875a6c12329ba9c258e865"
    assert september["discovered_from"] == PROVENANCE
    assert september["month_on_month"]["regime_input"] == "NOT_AN_AXIS" and september["unit"] == "percent_yoy"
    assert artifact["parse_failures"] == []


def test_homepage_discovery_is_bounded_and_yields_only_the_september_release():
    assert nso.discover_cpi_release_locators(homepage()) == [SEPT_URL]
    stem = "/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-x/"
    links = "".join(f'<a href="https://www.nso.gov.vn/en/data-and-statistics/2026/{month:02d}{stem}">x</a>' for month in range(1, 9))
    links += f'<a href="https://evil.example/en/data-and-statistics/2026/12{stem}">x</a>'
    found = nso.discover_cpi_release_locators(fixture_record("", "NSO_RELEASE_CALENDAR", nso.NSO_HOMEPAGE, body=links.encode()))
    assert found == [f"https://www.nso.gov.vn/en/data-and-statistics/2026/{month:02d}{stem}" for month in (8, 7, 6)]


def test_retained_october22_inputs_fail_closed_because_the_linked_september_release_was_not_retained():
    artifact = build(raw_records=[*june_july(), homepage()], retrieved_at=RETRIEVED)
    freshness = artifact["freshness_rules"]["vn_cpi_yoy"]
    assert artifact["release_discovery"]["locator_status"] == {SEPT_URL: "DISCOVERED_NOT_RETAINED"}
    assert freshness["status"] == "STALE_OR_UNAVAILABLE" and "NEWER_DISCOVERED_RELEASE_NOT_QUALIFIED" in freshness["reason_codes"]
    assert artifact["observations"]["vn_cpi_yoy"][-1]["value"] == 4.45


def test_september_supersedes_the_lagging_calendar_entry_and_reaches_session_context_as_level_only():
    artifact = build(raw_records=[*june_july(), sept(), homepage()], retrieved_at=RETRIEVED)
    freshness = artifact["freshness_rules"]["vn_cpi_yoy"]
    assert freshness["status"] == "CURRENT_NEXT_RELEASE_UNANNOUNCED" and freshness["next_expected_official_release"] is None
    assert freshness["superseded_calendar_entry"] == {"release_date": "2026-10-03", "reference_period": "2026-09"}
    assert freshness["reason_codes"] == ["CALENDAR_ENTRY_ALREADY_RETAINED"] and freshness["valid_through"] == "2026-11-30"
    rows = current_macro_observations(artifact)
    cpi = rows[0]
    assert (cpi["value"], cpi["observation_date"], cpi["released_at"], cpi["url"]) == (5.08, "2026-09", "2026-10-03", SEPT_URL)
    assert cpi["previous_value"] is None and cpi["previous_observation_date"] is None
    assert "PREDECESSOR_PERIOD_NOT_ADJACENT:2026-07->2026-09" in cpi["limitations"]
    assert cpi["month_on_month"]["value"] == 0.62
    macro = build_macro(observations=rows, raw_sources=[], retrieved_at=RETRIEVED)
    assert macro["state_axes"]["INFLATION_PRESSURE"]["state"] == "UNKNOWN"
    context = session_context(macro, "2026-10-22", cutoff=CUTOFF)
    assert context["status"] == "AVAILABLE" and "vn_cpi_yoy" not in context["excluded_observations"]
    assert context["observations"]["vn_cpi_yoy"]["value"] == 5.08
    assert context["observations"]["vn_cpi_yoy"]["temporal"]["release_precision"] == "DATE_ONLY"
    assert context["macro_regime"]["state"] == "INSUFFICIENT_EVIDENCE"


def test_adjacent_predecessor_still_yields_a_direction():
    august = synthetic("<title>Consumer Price Index, Gold Price Index and US Dollar Price Index in August 2026</title><p>The consumer price index (CPI) in August 2026 increased by 0.20% compared to the previous month, and rose by 4.90% over the same period last year.</p><p>Reference period: 8/2026 Date of issue: 03/09/2026</p>", "https://nso.example/aug")
    rows = current_macro_observations(build(raw_records=[august, sept(), homepage()], retrieved_at=RETRIEVED))
    assert (rows[0]["previous_observation_date"], rows[0]["previous_value"]) == ("2026-08", 4.9)
    assert build_macro(observations=rows, raw_sources=[], retrieved_at=RETRIEVED)["state_axes"]["INFLATION_PRESSURE"]["state"] == "ACCELERATING"


def test_newer_discovered_release_that_fails_parsing_fails_closed():
    broken = (FIXTURES / "cpi_2026-09_release.html").read_bytes().replace(b"year on year", b"y/y")
    artifact = build(raw_records=[*june_july(), sept(body=broken), homepage()], retrieved_at=RETRIEVED)
    assert artifact["release_discovery"]["locator_status"][SEPT_URL] == "PARSE_BLOCKED"
    freshness = artifact["freshness_rules"]["vn_cpi_yoy"]
    assert freshness["status"] == "STALE_OR_UNAVAILABLE" and freshness["unqualified_discovered_locators"] == [SEPT_URL]
    macro = build_macro(observations=current_macro_observations(artifact), raw_sources=[], retrieved_at=RETRIEVED)
    assert "OBSERVATION_FRESHNESS_NOT_CURRENT" in session_context(macro, "2026-10-22", cutoff=CUTOFF)["excluded_observations"]["vn_cpi_yoy"]


def test_discovered_release_fetch_failure_is_retained_and_fails_closed():
    failed = nso._fetch_failed_record(url=SEPT_URL, retrieved_at=RETRIEVED, error=TimeoutError(), discovered_from=PROVENANCE)
    artifact = build(raw_records=[*june_july(), failed, homepage()], retrieved_at=RETRIEVED)
    assert artifact["release_discovery"]["locator_status"][SEPT_URL] == "FETCH_FAILED"
    assert artifact["freshness_rules"]["vn_cpi_yoy"]["status"] == "STALE_OR_UNAVAILABLE"
    assert [row["value"] for row in artifact["observations"]["vn_cpi_yoy"]] == [4.69, 4.45]


@pytest.mark.parametrize("body, reason", [
    ("<p>The Consumer Price Index (CPI) in September 2026 rose by 5.08% year on year and by 5.10% over the same period last year.</p><p>Reference period: 9/2026 Date of issue: 03/10/2026</p>", "NSO_CPI_AMBIGUOUS_YOY_CLAIM"),
    ("<title>Consumer Price Index, Gold Price Index, and US Dollar Price Index in August 2026</title><p>The Consumer Price Index (CPI) in September rose by 5.08% year on year.</p><p>Reference period: 9/2026 Date of issue: 03/10/2026</p>", "NSO_CPI_TITLE_REFERENCE_PERIOD_MISMATCH"),
    ("<p>The Consumer Price Index (CPI) in September 2026 decreased by -0.30% year-on-year.</p><p>Reference period: 9/2026 Date of issue: 03/10/2026</p>", "NSO_CPI_AMBIGUOUS_SIGN"),
    ("<p>The Consumer Price Index (CPI) in September 2026 was 5.08% higher than a year earlier.</p><p>Reference period: 9/2026 Date of issue: 03/10/2026</p>", "NSO_CPI_REQUIRED_PUBLICATION_METADATA_OR_YOY_CLAIM_NOT_FOUND"),
])
def test_ambiguous_mismatched_or_unsupported_wording_is_parse_blocked(body, reason):
    artifact = build(raw_records=[synthetic(body)], retrieved_at=RETRIEVED)
    assert artifact["observations"]["vn_cpi_yoy"] == [] and artifact["parse_failures"] == [reason]
    assert artifact["raw_payloads"][0]["parse_status"] == "PARSE_BLOCKED:" + reason


def test_explicit_decrease_is_negative_without_sign_inversion():
    body = "<p>The Consumer Price Index (CPI) in September 2026 decreased by 0.10% compared with the previous month and fell by 0.30% year-on-year.</p><p>Reference period: 9/2026 Date of issue: 03/10/2026</p>"
    row = build(raw_records=[synthetic(body)], retrieved_at=RETRIEVED)["observations"]["vn_cpi_yoy"][0]
    assert (row["value"], row["month_on_month"]["value"]) == (-0.30, -0.10)


@pytest.mark.parametrize("retrieved, status", [("2026-11-30T09:00:00Z", "CURRENT_NEXT_RELEASE_UNANNOUNCED"), ("2026-12-01T09:00:00Z", "STALE_OR_UNAVAILABLE")])
def test_next_release_unannounced_has_a_hard_ceiling(retrieved, status):
    freshness = build(raw_records=[*june_july(retrieved), sept(retrieved), homepage(retrieved)], retrieved_at=retrieved)["freshness_rules"]["vn_cpi_yoy"]
    assert freshness["status"] == status and freshness["valid_through"] == "2026-11-30"
    assert ("FRESHNESS_CEILING_EXCEEDED" in freshness["reason_codes"]) == (status == "STALE_OR_UNAVAILABLE")


def test_session_context_enforces_the_ceiling_on_a_previously_built_artifact():
    artifact = build(raw_records=[*june_july(), sept(), homepage()], retrieved_at=RETRIEVED)
    macro = build_macro(observations=current_macro_observations(artifact), raw_sources=[], retrieved_at=RETRIEVED)
    assert "FRESHNESS_CEILING_EXCEEDED" in session_context(macro, "2026-12-01", cutoff="2026-12-01T18:30:00+07:00")["excluded_observations"]["vn_cpi_yoy"]
    assert "vn_cpi_yoy" not in session_context(macro, "2026-11-30", cutoff="2026-11-30T18:30:00+07:00")["excluded_observations"]


def test_a_genuinely_future_calendar_entry_keeps_the_stricter_release_date_rule():
    page = fixture_record("", "NSO_RELEASE_CALENDAR", nso.NSO_HOMEPAGE, body=b"<p>Next releases 03/11/2026: Consumer price index, gold, and USD price indexes in October 2026</p>")
    current = build(raw_records=[sept(), page], retrieved_at=RETRIEVED)["freshness_rules"]["vn_cpi_yoy"]
    assert (current["status"], current["next_expected_official_release"], current["valid_through"]) == ("CURRENT", "2026-11-03", "2026-11-02")
    due = build(raw_records=[sept("2026-11-03T09:00:00Z"), page], retrieved_at="2026-11-03T09:00:00Z")["freshness_rules"]["vn_cpi_yoy"]
    assert due["status"] == "STALE_OR_UNAVAILABLE" and due["reason_codes"] == ["NEXT_OFFICIAL_RELEASE_DUE"]


class _Response:
    def __init__(self, body):
        self.body, self.status, self.headers = body, 200, Message()
        self.headers["Content-Type"] = "text/html; charset=UTF-8"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize("september_reachable", [True, False])
def test_acquire_follows_only_homepage_linked_official_releases_with_provenance(monkeypatch, september_reachable):
    pages = {nso.NSO_HOMEPAGE: "homepage_20261022.html", JUNE_URL: "cpi_2026-06_release.html", JULY_URL: "cpi_2026-07_release.html", SEPT_URL: "cpi_2026-09_release.html"}
    requested = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        if request.full_url == SEPT_URL and not september_reachable:
            raise TimeoutError("offline")
        return _Response((FIXTURES / pages[request.full_url]).read_bytes())

    monkeypatch.setattr(nso, "urlopen", fake_urlopen)
    artifact = nso.acquire(retrieved_at=RETRIEVED)
    assert requested == [nso.NSO_HOMEPAGE, JUNE_URL, JULY_URL, SEPT_URL]
    retained = {row["locator"]: row for row in artifact["raw_payloads"]}
    assert retained[SEPT_URL]["discovered_from"] == PROVENANCE
    freshness = artifact["freshness_rules"]["vn_cpi_yoy"]
    if september_reachable:
        assert current_macro_observations(artifact)[0]["value"] == 5.08 and freshness["status"] == "CURRENT_NEXT_RELEASE_UNANNOUNCED"
    else:
        assert retained[SEPT_URL]["parse_status"] == "FETCH_FAILED:TimeoutError" and retained[SEPT_URL]["payload_base64"] is None
        assert freshness["status"] == "STALE_OR_UNAVAILABLE"
