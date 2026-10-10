"""Forward-driver contract: dated provenance, conservative qualification, no votes."""
import copy

import pytest

import current_corporate_intelligence_axis as axis
import stocklookup_core.decision.integrated_investment_decision_product as product


def event(**changes):
    value = dict(event_id="event:1", ticker="TEST", event_type="DIVIDEND",
                 event_subtype="CASH_DIVIDEND", status="APPROVED",
                 original_event_status="CONFIRMED_UPCOMING", classification="INFORMATIONAL",
                 evidence_tier="OFFICIAL_QUALIFIED", source="retained:official",
                 source_identities=["source:1"], temporal_fitness="READY",
                 freshness="ACTIVE", materiality="POTENTIALLY_MATERIAL",
                 record_date="2026-10-05", ex_date=None, execution_date=None,
                 announcement_date="2026-09-05", effective_date=None,
                 reason_codes=[], limitations=[], conflicts=[])
    value.update(changes)
    return value


def context(events=None, session="2026-10-01", **changes):
    record = dict(ticker="TEST", research_session=session, state="INFORMATIONAL_ONLY",
                  fitness="AVAILABLE", events=events if events is not None else [event()])
    record.update(changes)
    return axis.build_forward_driver_context(record, as_of_session="2026-10-01")


def test_planned_execution_schedule_is_not_observed_execution():
    planned = context([event(status="PLANNED", original_event_status="PLANNED_NOT_EXECUTED",
                             execution_date="2026-10-20")])["drivers"][0]
    executed = context([event(status="EXECUTED", original_event_status="EXECUTED",
                              execution_date="2026-09-20")])["drivers"][0]
    assert planned["status"] == "PLANNED" and planned["qualified"]
    assert executed["status"] == "EXECUTED" and executed["qualified"]
    assert planned["known_dates"]["ex_date"] is None
    assert planned["known_dates"]["record_date"] == "2026-10-05"


@pytest.mark.parametrize("session,fitness,qualified", [
    ("2026-09-05", "PARTIAL", True), ("2026-10-02", "BLOCKED", False),
    (None, "BLOCKED", False), ("2026-10-01junk", "BLOCKED", False)])
def test_source_session_fails_closed_without_relabelling(session, fitness, qualified):
    driver = context(session=session)["drivers"][0]
    assert driver["fitness"] == fitness and driver["qualified"] is qualified
    assert driver["evidence_session"] == session


@pytest.mark.parametrize("kind", ["DIVIDEND", "CAPITAL_RAISE", "BORROWING", "ACQUISITION",
                                  "PROJECT_ANNOUNCEMENT", "BONUS_ISSUE", "BUYBACK"])
@pytest.mark.parametrize("classification,direction", [("POTENTIAL_CATALYST", "UNKNOWN"),
                                                      ("POTENTIAL_RISK", "UNKNOWN"),
                                                      ("INFORMATIONAL", "INFORMATIONAL"), ("MIXED", "MIXED")])
def test_bare_type_and_unsupported_direction_never_vote(kind, classification, direction):
    d = context([event(event_type=kind, classification=classification, direction="SUPPORTIVE")])["drivers"][0]
    assert d["direction"] == direction
    assert "NO_DIRECTIONAL_THESIS_VOTE" in d["limitations"]


@pytest.mark.parametrize("changes,code", [
    ({"conflicts": ["status conflict"]}, "FORWARD_DRIVER_CONFLICTING_EVIDENCE"),
    ({"record_date": "2026-10-05junk"}, "FORWARD_DRIVER_DATE_MALFORMED"),
    ({"record_date": None, "announcement_date": None}, "FORWARD_DRIVER_KNOWN_DATE_ABSENT"),
    ({"announcement_date": "2026-10-02"}, "FORWARD_DRIVER_FUTURE_OBSERVATION"),
    ({"status": "EXECUTED", "execution_date": "2026-10-02"}, "FORWARD_DRIVER_FUTURE_OBSERVATION"),
    ({"evidence_tier": "UNQUALIFIED"}, "FORWARD_DRIVER_SOURCE_NOT_QUALIFIED"),
    ({"source_identities": []}, "FORWARD_DRIVER_PROVENANCE_INCOMPLETE"),
    ({"temporal_fitness": "UNKNOWN"}, "FORWARD_DRIVER_TEMPORAL_FITNESS_UNAVAILABLE"),
    ({"ticker": "OTHER"}, "FORWARD_DRIVER_TICKER_MISMATCH"),
    ({"status": "UNKNOWN"}, "FORWARD_DRIVER_STATUS_UNRESOLVED")])
def test_local_blockers_preserve_raw_evidence(changes, code):
    raw = event(**changes)
    before = copy.deepcopy(raw)
    d = context([raw])["drivers"][0]
    assert not d["qualified"] and code in d["blocker_reason_codes"]
    assert raw == before
    assert d["event_identity"] == raw["event_id"]


def test_no_event_and_no_qualified_driver_are_explicit_absence():
    empty = context([])
    blocked = context([event(conflicts=["conflicting"])])
    assert empty["qualified_driver_count"] == blocked["qualified_driver_count"] == 0
    assert "NO_QUALIFIED_FORWARD_DRIVER" in empty["blocker_reason_codes"]
    assert axis.forward_driver_coverage([empty, blocked])["no_qualified_driver_count"] == 2


def test_historical_resolved_events_are_retained_without_forward_qualification():
    d = context([event(status="EXECUTED", original_event_status="EXECUTED",
                      record_date="2024-01-01", announcement_date=None)])["drivers"][0]
    assert d["freshness"] == "RESOLVED_HISTORICAL" and not d["qualified"]


def test_identity_conflicts_and_input_order_stability():
    a, b = event(), event(event_id="event:2", status="PLANNED", source_identities=["b", "a"])
    assert context([a, b]) == context([b, a])
    conflict = context([a, event(status="CANCELLED")])
    assert all("FORWARD_DRIVER_IDENTITY_CONFLICT" in d["blocker_reason_codes"] for d in conflict["drivers"])
    reversed_sources = copy.deepcopy(b)
    reversed_sources["source_identities"].reverse()
    assert context([b]) == context([reversed_sources])


def test_source_fitness_cannot_be_widened_by_retained_event():
    assert not context(fitness="UNAVAILABLE")["drivers"][0]["qualified"]


def test_integration_is_additive_and_has_no_posture_or_decision_identity_effect():
    kwargs = dict(ticker="TEST", as_of_session="2026-10-01", tactical_record=None,
                  financial_record=None, valuation_record=None, relative_volume_record=None,
                  market_sector_record=None)
    source = dict(ticker="TEST", research_session="2026-10-01", state="INFORMATIONAL_ONLY",
                  fitness="AVAILABLE", events=[event()])
    with_driver = product.build_ticker_integrated_decision(**kwargs, corporate_intelligence_record=source)
    without_events = product.build_ticker_integrated_decision(**kwargs, corporate_intelligence_record={**source, "events": []})
    assert with_driver["research_action_posture"] == without_events["research_action_posture"]
    assert with_driver["decision_identity"] == without_events["decision_identity"]
    c = with_driver["corporate_intelligence_context"]["forward_driver_context"]
    assert with_driver["evidence_axes"]["CORPORATE_INTELLIGENCE"]["context"]["forward_driver_context"] == c
    assert with_driver["current_research_decision_input"]["dimensions"]["CORPORATE"]["forward_driver_context"] == c
    assert c["qualified_driver_count"] == 1



def replay_inputs():
    source_record = dict(ticker="TEST", research_session="2026-10-01", state="INFORMATIONAL_ONLY",
                         fitness="AVAILABLE", events=[event()])
    source = dict(contract_version=axis.CONTRACT_VERSION, records={"TEST": source_record})
    source.update(axis.content_identity(source))
    record = product.build_ticker_integrated_decision(
        ticker="TEST", as_of_session="2026-10-01", tactical_record=None, financial_record=None,
        valuation_record=None, relative_volume_record=None, market_sector_record=None,
        corporate_intelligence_record=source_record)
    record["corporate_intelligence_context"].pop("forward_driver_context")
    record["evidence_axes"]["CORPORATE_INTELLIGENCE"]["context"].pop("forward_driver_context")
    record["current_research_decision_input"]["dimensions"]["CORPORATE"].pop("forward_driver_context")
    before = dict(contract_version=product.CONTRACT_VERSION, session="2026-10-01",
                  records={"TEST": record}, source_artifacts={"corporate_intelligence": source["artifact_identity"]}, coverage={})
    before.update(product.content_identity(before))
    return before, source


def test_replay_checks_the_exact_additive_allowlist_and_preserves_inputs():
    from tools.replay_forward_driver_context import replay
    before, source = replay_inputs()
    frozen = copy.deepcopy((before, source))
    after, report = replay(before, source)
    assert (before, source) == frozen
    assert (after, report) == replay(before, source)
    assert report["unexplained_changes"] == report["posture_changes"] == report["decision_identities_changed"] == 0
    assert report["product_identity_before"] != report["product_identity_after"]
    assert report["qualified_driver_after"]["tickers_with_qualified_driver"] == 1


@pytest.mark.parametrize("fault,code", [("lineage", "LINEAGE_MISMATCH"),
                                        ("summary", "SUMMARY_DRIFT"), ("dimension", "DIMENSION_DRIFT"),
                                        ("source_bytes", "CORPORATE_IDENTITY_MISMATCH")])
def test_replay_rejects_unexplained_or_unbound_changes(fault, code):
    from tools.replay_forward_driver_context import replay
    before, source = replay_inputs()
    if fault == "lineage":
        before["source_artifacts"]["corporate_intelligence"] = "other"
    elif fault == "summary":
        before["records"]["TEST"]["corporate_intelligence_context"]["state"] = "OTHER"
    elif fault == "dimension":
        before["records"]["TEST"]["current_research_decision_input"]["dimensions"]["CORPORATE"]["state"] = "BLOCKED"
    else:
        source["records"]["TEST"]["events"][0]["status"] = "EXECUTED"
    before.update(product.content_identity(before))
    with pytest.raises(ValueError, match=code):
        replay(before, source)
