"""Offline demonstrations, never official source admission or production coverage."""
import copy
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from stocklookup_core.evidence import business_update_observations as business

HPG_LOCATOR = "https://www.hoaphat.com.vn/tin-tuc/hoa-phat-ban-hon-10-3-trieu-tan-thep-trong-9-thang-tang-39-so-voi-cung-ky-nam-truoc.html"


def fixture(ticker="HPG", kind="official_operating_update", value="3.0", **metadata):
    # Synthetic text: numeric values/native labels/endpoints are NOT verified HPG facts.
    text = f"DEMO ONLY. Q3: 2026-07-01 to 2026-09-30. Sales {value} million tonnes Q3; YoY 10 percent."
    raw = text.encode()
    manifest = dict(ticker=ticker, issuer_name=f"{ticker} synthetic issuer", source_id="issuer_ir",
                    document_id="demo-q3", source_url=HPG_LOCATOR, document_type=kind,
                    content_sha256=hashlib.sha256(raw).hexdigest(),
                    published_at="2026-10-12T10:21:00+07:00", observed_at="2026-10-13T09:00:00+07:00",
                    known_at="2026-10-13T09:00:00+07:00", assurance="UNKNOWN")
    manifest.update(metadata)
    fact = dict(native_label="Sales", concept="major_steel_sales", value=value,
                unit="million tonnes", native_value=value, native_unit="million tonnes",
                metric_kind="SALES", basis="MAJOR_STEEL_PRODUCTS", sector="STEEL", sector_applicability=True,
                period_label="Q3", period_start="2026-07-01", period_end="2026-09-30",
                period_proof="Q3: 2026-07-01 to 2026-09-30",
                span=dict(start=0, end=len(text), text=text),
                comparison=dict(basis="YoY", value="10", native_value="10", unit="percent",
                                method="EXPLICIT", source_span="YoY 10 percent"))
    return manifest, raw, fact


def envelope(ticker="HPG", kind="official_operating_update", value="3.0", **metadata):
    manifest, raw, fact = fixture(ticker, kind, value, **metadata)
    if kind == "preliminary_earnings_disclosure":
        manifest["assurance"] = "PRELIMINARY_UNASSURED"
        fact["metric_kind"] = "EARNINGS"
        fact["accounting_scope"] = "CONSOLIDATED_ESTIMATE"
    elif kind == "management_guidance":
        fact["metric_kind"] = "GUIDANCE"
    return business.observe(manifest=manifest, source_bytes=raw, observations=[fact],
                            cutoff="2026-10-13T15:00:00+07:00", research_fixture=True)


def test_fixture_is_restricted_source_bound_and_duplicate_stable():
    observation = envelope()
    assert observation["research_usable"]
    assert observation["coverage_kind"] == "OFFLINE_FIXTURE"
    assert not observation["official_qualified"]
    assert observation["route_decision"]["decision"] == "refused"
    ctx = business.research_context([observation, observation], ticker="HPG", cutoff="2026-10-13T15:00:00+07:00")
    assert len(ctx["documents"]) == len(ctx["FACT"]) == 1
    assert ctx["FACT"][0]["comparison"]["value"] == "10"
    assert ctx["posture_effect"] == ctx["valuation_effect"] == "NONE"


@pytest.mark.parametrize("key,value,reason", [
    ("published_at", None, "PUBLISHED_AT_UNKNOWN"),
    ("published_at", "2026-10-13T15:01:00+07:00", "PUBLISHED_AT_AFTER_CUTOFF"),
    ("observed_at", "2026-10-14T09:00:00+07:00", "OBSERVED_AT_AFTER_CUTOFF"),
    ("known_at", "2026-10-13T09:00:00", "KNOWN_AT_UNKNOWN"),
    ("content_sha256", "0" * 64, "SOURCE_HASH_MISMATCH"),
    ("ticker", None, "ISSUER_SOURCE_IDENTITY_MISSING"),
    ("source_id", None, "ISSUER_SOURCE_IDENTITY_MISSING"),
    ("known_at", "2026-10-12T12:00:00+07:00", "KNOWN_AT_PRECEDES_OBSERVATION"),
])
def test_document_temporal_and_identity_fail_closed(key, value, reason):
    observation = envelope(**{key: value})
    assert reason in observation["blockers"]
    assert not observation["research_usable"]


@pytest.mark.parametrize("mutate,reason", [
    ({"value": "30"}, "NUMERIC_TOKEN_MISMATCH"),
    ({"unit": "VND"}, "UNIT_CONVERSION_NOT_AUTHORIZED"),
    ({"period_start": "2026-01-01", "period_label": "9M"}, "PERIOD_ENDPOINTS_NOT_PROVEN"),
    ({"native_label": "Crude-steel production"}, "NATIVE_FACT_NOT_IN_SPAN"),
    ({"metric_kind": "EARNINGS"}, "OPERATING_UPDATE_IS_NOT_EARNINGS"),
    ({"sector_applicability": False}, "SECTOR_APPLICABILITY_UNKNOWN_OR_FALSE"),
    ({"value": "NaN"}, "NUMERIC_TOKEN_MISMATCH"),
    ({"comparison": {"basis": "YoY", "method": "COMPUTED", "unit": "percent"}}, "COMPARISON_NOT_SOURCE_BOUND"),
])
def test_numeric_period_and_unit_fail_closed(mutate, reason):
    manifest, raw, fact = fixture()
    fact.update(mutate)
    observation = business.observe(manifest=manifest, source_bytes=raw, observations=[fact],
                                   cutoff="2026-10-13T15:00:00+07:00", research_fixture=True)
    assert reason in observation["observations"][0]["blockers"]
    assert not observation["research_usable"]


def test_real_unapproved_route_no_bytes_and_third_party_stay_discovery():
    manifest, raw, fact = fixture()
    real = business.observe(manifest=manifest, source_bytes=raw, observations=[fact], cutoff="2026-10-13T15:00:00+07:00")
    assert not real["research_usable"]
    absent = business.observe(manifest=manifest, source_bytes=None, observations=[fact], cutoff="2026-10-13T15:00:00+07:00", research_fixture=True)
    assert "NO_SOURCE_BYTES" in absent["blockers"] and not absent["research_usable"]
    assert not envelope(kind="third_party_report")["research_usable"]


def test_later_observation_cannot_repair_historical_cutoff():
    observation = envelope()
    ctx = business.research_context([observation], ticker="HPG", cutoff="2026-10-12T15:00:00+07:00")
    assert not ctx["FACT"] and not ctx["documents"]
    before = envelope(observed_at="2026-10-12T11:00:00+07:00", known_at="2026-10-12T11:00:00+07:00")
    assert business.research_context([before], ticker="HPG", cutoff="2026-10-12T15:00:00+07:00")["FACT"]


def test_revision_and_conflicts_never_choose_a_preferred_fact():
    original = envelope()
    revision = envelope(value="4.0", document_id="revision", supersedes_document_id="demo-q3",
                        observed_at="2026-10-14T09:00:00+07:00", known_at="2026-10-14T09:00:00+07:00")
    # Build the correction with its actual later cutoff.
    manifest, raw, fact = fixture(value="4.0", document_id="revision", supersedes_document_id="demo-q3",
                                  observed_at="2026-10-14T09:00:00+07:00", known_at="2026-10-14T09:00:00+07:00")
    revision = business.observe(manifest=manifest, source_bytes=raw, observations=[fact], cutoff="2026-10-14T15:00:00+07:00", research_fixture=True)
    assert len(business.research_context([original, revision], ticker="HPG", cutoff="2026-10-13T15:00:00+07:00")["FACT"]) == 1
    later = business.research_context([original, revision], ticker="HPG", cutoff="2026-10-14T15:00:00+07:00")
    assert [f["value"] for f in later["FACT"]] == ["4.0"]
    assert later["superseded_identities"] == [original["observation_identity"]]
    conflict = business.research_context([original, envelope(value="4.0", document_id="other")], ticker="HPG", cutoff="2026-10-13T15:00:00+07:00")
    assert "CONTRADICTORY_SOURCE_FACTS" in conflict["conflicts"] and not conflict["research_usable"]
    hash_conflict = business.research_context([original, envelope(value="4.0")], ticker="HPG", cutoff="2026-10-13T15:00:00+07:00")
    assert "DOCUMENT_ID_HAS_DIFFERENT_HASHES" in hash_conflict["conflicts"]


def test_distinct_document_classes_never_become_financial_inputs():
    assert envelope("XYZ", "preliminary_earnings_disclosure")["document_class"] == "PRELIMINARY_EARNINGS_DISCLOSURE"
    assert envelope("XYZ", "management_guidance")["document_class"] == "MANAGEMENT_GUIDANCE"
    formal = envelope("XYZ", "reviewed_interim_financial_statements")
    assert "ROUTE_TO_EXISTING_FINANCIAL_OWNER" in formal["blockers"]
    assert not formal["research_usable"]
    for kind in ("preliminary_earnings_disclosure", "management_guidance", "reviewed_interim_financial_statements"):
        assert not envelope("XYZ", kind)["accounting_fact_authority"]


def test_tampered_envelope_is_rejected():
    observation = envelope()
    observation["observations"][0]["value"] = "99"
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        business.research_context([observation], ticker="HPG", cutoff="2026-10-13T15:00:00+07:00")


def test_native_real_lane_denies_other_domains_and_protected_paths():
    # Read-only simulation through the released live gate; no prohibited file is written.
    import roadmap_execution_state as roadmap
    coordinator = Path(r"C:\Projects\StockLookup\integration-coordinator-20261013")
    if not coordinator.exists():
        pytest.skip("Owner-host live acceptance only; hermetic CLI cases cover clean clones")
    state = roadmap.load_state(coordinator / "docs/ROADMAP_STATE.json")
    mid = "OFFICIAL_BUSINESS_UPDATES_CURRENT_RESEARCH_INTEGRATION_V1"
    if not any(l["milestone_id"] == mid for l in state.get("development_control", {}).get("lanes", [])):
        pytest.skip("Host coordinator does not contain this lane")
    with patch.object(roadmap, "_changed_paths", return_value=(["stocklookup_core/evidence/business_update_observations.py"], [])):
        assert not roadmap.check_lane(state, mid, repo=coordinator)["errors"]
    for path in ("tools/reliability/claude.py", "data/private.json", "config/official_source_registry.json"):
        with patch.object(roadmap, "_changed_paths", return_value=([path], [])):
            assert "LANE_PROHIBITED_CHANGE:" + path in roadmap.check_lane(state, mid, repo=coordinator)["errors"]
