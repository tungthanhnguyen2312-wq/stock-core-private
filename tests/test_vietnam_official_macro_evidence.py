import base64
import hashlib

from current_macro_regime import build as build_macro, session_context
from vietnam_official_macro_evidence import build, content_identity, current_macro_observations


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
