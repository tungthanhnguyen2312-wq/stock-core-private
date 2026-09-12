"""Focused contract tests for current event catalyst semantics."""
from __future__ import annotations

import current_event_catalyst_classification as cec
import current_thesis_case_context as thesis
import current_valuation_opportunity_integration as integration


SESSION = "2026-09-11"


def _official(*, event_type="CASH_DIVIDEND", event_state="UPCOMING", **extra):
    event = {
        "event_id": "official-event:1", "event_type": event_type, "event_state": event_state,
        "materiality_status": "PRICE_SHARE_AFFECTING", "qualification": "EX_DATE_OFFICIAL_QUALIFIED",
        "ex_date": "2026-09-12", "warnings": ["No event impact, probability, score, target, or recommendation is derived."],
    }
    event.update(extra)
    return event


def _official_artifact(records):
    return {"contract_version": cec.OFFICIAL_CONTRACT, "artifact_identity": "official:1", "research_session": SESSION, "records": records}


def test_production_event_state_positive_catalyst_is_strictly_qualified():
    item = cec.classify_event(_official(), contract_version=cec.OFFICIAL_CONTRACT)
    assert item["eligible"] is True
    assert item["catalyst_class"] == cec.POSITIVE_CATALYST
    assert item["event_state"] == "UPCOMING"
    assert item["reason_codes"] == ["CURRENT_QUALIFIED_PRICE_SHARE_EVENT"]


def test_agm_is_neutral_information_not_a_positive_catalyst():
    item = cec.classify_event(_official(event_type="AGM", event_state="RECENT", materiality_status="INFORMATIONAL_GOVERNANCE"), contract_version=cec.OFFICIAL_CONTRACT)
    assert item["eligible"] is False
    assert item["catalyst_class"] == cec.NEUTRAL_INFORMATION


def test_unknown_official_state_degrades_explicitly_without_acceptance():
    item = cec.classify_event(_official(event_state="MADE_UP_STATE"), contract_version=cec.OFFICIAL_CONTRACT)
    assert item["catalyst_class"] == cec.UNRESOLVED
    assert item["reason_codes"] == ["UNRECOGNIZED_EVENT_STATE"]


def test_legacy_status_is_version_aware_and_adverse_is_not_active_catalyst():
    event = {"event_id": "legacy:1", "event_type": "CASH_DIVIDEND", "event_status": "CANCELLED"}
    legacy = cec.classify_event(event, contract_version=cec.CORPORATE_CONTRACT)
    current = cec.classify_event(event, contract_version=cec.OFFICIAL_CONTRACT)
    assert legacy["catalyst_class"] == cec.NEGATIVE_CATALYST
    assert legacy["eligible"] is False
    assert current["reason_codes"] == ["UNRECOGNIZED_EVENT_STATE"]


def test_boilerplate_warning_never_changes_event_classification():
    clean = cec.classify_event(_official(warnings=[]), contract_version=cec.OFFICIAL_CONTRACT)
    warned = cec.classify_event(_official(), contract_version=cec.OFFICIAL_CONTRACT)
    assert clean["catalyst_class"] == warned["catalyst_class"] == cec.POSITIVE_CATALYST


def test_past_and_incomplete_dates_preserve_source_temporal_semantics_without_inference():
    past = cec.classify_event(_official(event_state="PAST"), contract_version=cec.OFFICIAL_CONTRACT)
    incomplete = cec.classify_event(_official(event_state="DATE_INCOMPLETE", ex_date=None), contract_version=cec.OFFICIAL_CONTRACT)
    assert past["catalyst_class"] == cec.INELIGIBLE
    assert past["temporal_status"] == "PAST_PER_SOURCE_CONTRACT"
    assert incomplete["catalyst_class"] == cec.UNRESOLVED
    assert incomplete["event_date"] is None


def test_event_identity_deduplication_and_ordering_are_deterministic():
    first = _official(event_id="official-event:b")
    second = _official(event_id="official-event:a")
    rows = cec.classify_events([first, first, second], contract_version=cec.OFFICIAL_CONTRACT)
    assert [item["source_event_identity"] for item in rows] == ["official-event:a", "official-event:b"]


def test_eligible_event_creates_one_catalyst_thesis_case_with_lineage():
    events = _official_artifact({"AAA": {"ticker": "AAA", "events": [_official()]}})
    artifact = thesis.build_artifact(as_of_session=SESSION, requested_at="t", daily_tickers={"AAA"}, financial_analysis_product_context=None, events=events)
    record = artifact["records"]["AAA"]
    assert record["case_classes_present"] == ["CATALYST"]
    assert len(record["catalysts"]) == 1
    assert record["catalysts"][0]["source_event_identity"] == "official-event:1"
    assert record["method_versions"]["catalyst_classification"] == cec.METHOD_VERSION


def test_neutral_or_unresolved_event_does_not_create_a_thesis_catalyst_or_drop_ticker():
    events = _official_artifact({
        "AAA": {"ticker": "AAA", "events": [_official(event_type="AGM", event_state="RECENT", materiality_status="INFORMATIONAL_GOVERNANCE")]},
        "BBB": {"ticker": "BBB", "events": [_official(event_state="UNKNOWN")]},
    })
    artifact = thesis.build_artifact(as_of_session=SESSION, requested_at="t", daily_tickers={"AAA", "BBB", "CCC"}, financial_analysis_product_context=None, events=events)
    assert set(artifact["records"]) == {"AAA", "BBB", "CCC"}
    assert all(not artifact["records"][ticker]["catalysts"] for ticker in artifact["records"])


def test_opportunity_and_security_consume_current_event_state_through_the_boundary():
    watchlist = {"session": SESSION, "artifact_identity": "watch:1", "records": {"AAA": {"entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE"}}}
    valuation = {"valuation_session": SESSION, "artifact_identity": "val:1", "records": {"AAA": {}}}
    events = _official_artifact({"AAA": {"ticker": "AAA", "events": [_official()]}})
    result = integration.build_artifacts(as_of_session=SESSION, watchlist=watchlist, valuation=valuation, events=events, requested_at="t")
    opportunity = result["opportunity_context"]["records"]["AAA"]
    assert opportunity["catalyst"]["status"] == "CONFIRMED"
    assert opportunity["catalyst"]["qualified_current_catalysts"][0]["event_state"] == "UPCOMING"
    assert result["security_decision_context"]["records"]["AAA"]["as_of_session"] == SESSION
