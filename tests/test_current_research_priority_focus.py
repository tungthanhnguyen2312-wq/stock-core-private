"""Research-focus selection, provenance and dossier semantics. Synthetic unless noted."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import runpy

import pytest

import daily_opportunity_decision_queue as queues
import daily_research_session_operations as ops
import personal_investment_decision_action_center as action_center
from stocklookup_core.decision import bounded_research_preview as preview
from stocklookup_core.decision import current_opportunity_prioritization as opportunity
from stocklookup_core.decision import current_research_priority_focus as focus
from stocklookup_core.decision import integrated_investment_decision_product as integrated
from stocklookup_core.tactical import watchlist_tactical_entry_classifier as tactical

HELPERS = runpy.run_path(str(Path(__file__).with_name("test_research_setup_transition_v1.py")))


def _queue(specs):
    """specs: (ticker, lane, tier). Builds a hash-valid queue and matching opportunity."""
    records = {}
    for ticker, lane, tier in specs:
        records[ticker] = {
            "priority_tier": tier, "eligible_strategies": [lane], "lane_priority": {lane: tier},
            "tactical_state": "EARLY_REVERSAL_CANDIDATE", "entry_action": "EARLY_ENTRY",
            "scenario_status": "SCENARIO_PARTIAL", "event_context_status": "NONE",
            "fundamental_context_status": "INSUFFICIENT", "data_quality_status": "SUFFICIENT",
            "priority_reasons": [lane + "_REASON"], "blocking_reasons": ["FUNDAMENTAL_CONTEXT_ABSENT"],
            "invalidation_or_context_warnings": [], "content_identity": "opportunity:" + ticker,
            "source_input_identities": {"tactical": "synthetic:tactical"},
            "official_current_universe_status": "CURRENT_OFFICIAL",
        }
    artifact = {"schema_version": "1.0.0", "contract_version": opportunity.CONTRACT_VERSION,
                "research_session": "2026-01-02", "source_artifact_identities": {"synthetic": "opportunity-inputs"},
                "records": records, "coverage": {"current_official_universe": len(records)}}
    artifact.update(opportunity.content_identity(artifact))
    queue = queues.build(opportunity=artifact, triage={
        "high_priority_review_eligible_records": [], "cohort_definitions": {}, "artifact_identity": "triage:synthetic"})
    return artifact, queue


def test_round_robin_preserves_lane_order_without_a_cross_lane_score():
    _, queue = _queue([
        ("A1", "EARLY_REVERSAL", "PRIORITY_NOW"), ("A2", "EARLY_REVERSAL", "SETUP_WATCH"),
        ("B1", "BASE_ACCUMULATION", "PRIORITY_NOW"),
        ("C1", "BREAKOUT", "PRIORITY_NOW"), ("C2", "BREAKOUT", "SETUP_WATCH"),
        ("M1", "BREAKOUT", "MONITOR"),
    ])
    selected = focus.select_from_queue(queue, lanes=focus.DEFAULT_LANES, tiers=focus.DEFAULT_TIERS, max_tickers=4)
    assert [item["ticker"] for item in selected["selected"]] == ["A1", "B1", "C1", "A2"]
    assert selected["lanes"][0]["selected_tickers"] == ["A1", "A2"]
    assert selected["lanes"][2]["selected_tickers"] == ["C1"]
    assert {item["ticker"] for item in selected["cap_excluded"]} == {"C2"}
    assert selected["qualified_count"] == 5
    assert "M1" not in {item["ticker"] for item in selected["cap_excluded"]} | {item["ticker"] for item in selected["selected"]}


def test_overlap_is_labeled_and_not_a_second_dossier_slot():
    opportunity_artifact, queue = _queue([("X1", "EARLY_REVERSAL", "PRIORITY_NOW")])
    # The built queue has only EARLY_REVERSAL. Add BREAKOUT on the record and the lane index, then reseal.
    queue["records"]["X1"]["lane_specific_priority"]["BREAKOUT"] = "SETUP_WATCH"
    queue["records"]["X1"]["eligible_strategies"] = ["EARLY_REVERSAL", "BREAKOUT"]
    queue["lane_queues"]["BREAKOUT"] = queues._lane_queue("BREAKOUT", queue["records"])
    queue.update(queues.content_identity(queue))
    focus._assert_lane_order(queue)
    selected = focus.select_from_queue(queue, lanes=("EARLY_REVERSAL", "BREAKOUT"), tiers=focus.DEFAULT_TIERS, max_tickers=4)
    assert [item["ticker"] for item in selected["selected"]] == ["X1"]
    assert selected["overlaps"][0]["reason"] == "ALREADY_SELECTED_IN_EARLIER_REQUESTED_LANE"
    assert selected["selected"][0]["lanes"] == ["EARLY_REVERSAL", "BREAKOUT"]


def test_tampered_queue_and_unknown_lane_fail_closed(tmp_path):
    _, queue = _queue([("A1", "EARLY_REVERSAL", "PRIORITY_NOW")])
    path = tmp_path / "daily_opportunity_decision_queue_artifact.json"
    broken = copy.deepcopy(queue)
    broken["lane_queues"]["EARLY_REVERSAL"]["tickers"].append({"ticker": "ZZ", "lane_priority": "PRIORITY_NOW"})
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(focus.ResearchFocusError, match="QUEUE_IDENTITY"):
        focus._verified_queue(path, session="2026-01-02", expected_identity=queue["artifact_identity"])
    with pytest.raises(focus.ResearchFocusError, match="QUEUE_LANE_NOT_IN_SOURCE_CONTRACT"):
        focus.select_from_queue(queue, lanes=("NOT_A_LANE",), tiers=focus.DEFAULT_TIERS, max_tickers=1)


def test_different_queue_artifact_unbinds_record_identity_without_hiding_a_same_artifact_miss():
    lineage = focus._priority_lineage(
        {"artifact_identity": "daily_opportunity_decision_queue:aaa"},
        {"source_artifacts": {"priority_queue": "daily_opportunity_decision_queue:bbb"}})
    assert lineage["record_identity_comparable"] is False
    assert lineage["status"] == "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    _, queue = _queue([("A1", "EARLY_REVERSAL", "PRIORITY_NOW")])
    record = queue["records"]["A1"]
    decision = {"ticker": "A1", "source_identities": {"priority_queue_record_identity": "other"},
                "opportunity_priority": {"status": "AVAILABLE", "research_priority_tier": record["research_priority_tier"],
                                         "entry_relevant": record["entry_relevant"]}}
    opportunity_record = {"content_identity": record["opportunity_record_content_identity"]}
    assert focus._bind(record, decision, opportunity_record)["status"] == "SOURCE_IDENTITY_MISMATCH"
    assert focus._bind(record, decision, opportunity_record, require_queue_record_identity=False)["status"] == "BOUND"


def test_population_difference_and_identity_mismatch_are_not_a_missing_listing():
    _, queue = _queue([("A1", "EARLY_REVERSAL", "PRIORITY_NOW")])
    record = queue["records"]["A1"]
    decision = {"ticker": "A1", "as_of_session": "2026-01-02", "source_identities": {"priority_queue_record_identity": "other"},
                "opportunity_priority": {"status": "AVAILABLE", "research_priority_tier": "PRIORITY_NOW", "entry_relevant": False}}
    bound = focus._bind(record, decision, {"content_identity": record["opportunity_record_content_identity"]})
    assert bound["status"] == "SOURCE_IDENTITY_MISMATCH"
    absent = focus._bind(record, None, {"content_identity": record["opportunity_record_content_identity"]})
    assert absent["status"] == "INTEGRATED_DECISION_RECORD_ABSENT"
    assert "NOT_IN_INTEGRATED_DECISION_POPULATION" in absent["reason"]


def test_evolution_labels_follow_source_states_and_do_not_invent_policy():
    current = {"research_action_posture": "WAIT_FOR_CONFIRMATION", "tactical_phase": "BREAKOUT_SETUP",
               "breakout_state_v3": "TESTING_PIVOT", "fundamental_state": integrated.FUNDAMENTAL_INSUFFICIENT,
               "fundamental_decision_policy_version": "v1"}
    assert focus._evolution(None, current, "NEWLY_AVAILABLE", "NOT_IN_CONFIRMATION_DELTA")["code"] == "NEW_CANDIDATE"
    confirmed = {**current, "tactical_phase": integrated.TACTICAL_BREAKOUT_CONFIRMED}
    assert focus._evolution(current, confirmed, "POSTURE_UNCHANGED", "GAINED_CONFIRMATION")["code"] == "CONFIRMED_SETUP"
    failed = {**current, "tactical_phase": integrated.TACTICAL_BREAKDOWN, "research_action_posture": "WAIT_FOR_CONFIRMATION"}
    assert focus._evolution(confirmed, failed, "BREAKOUT_FAILED", "LOST_CONFIRMATION")["code"] == "INVALIDATED_OR_WEAKENING"
    waiting = focus._evolution(current, current, "POSTURE_UNCHANGED", "NOT_IN_CONFIRMATION_DELTA")
    assert waiting["code"] == "AWAITING_CONFIRMATION"
    retained_but_waiting = focus._evolution(current, current, "POSTURE_UNCHANGED", "RETAINED_CONFIRMATION")
    assert retained_but_waiting["code"] == "AWAITING_CONFIRMATION"
    improved = {**current, "fundamental_state": integrated.FUNDAMENTAL_IMPROVING, "tactical_phase": "BASE", "breakout_state_v3": "IN_BASE"}
    prior = {**current, "fundamental_state": integrated.FUNDAMENTAL_DETERIORATING, "tactical_phase": "BASE", "breakout_state_v3": "IN_BASE",
             "research_action_posture": "HOLD"}
    assert focus._evolution(prior, improved, "POSTURE_CHANGED_OTHER", "NOT_IN_CONFIRMATION_DELTA")["code"] == "IMPROVING_CANDIDATE"
    other_epoch = {**improved, "fundamental_decision_policy_version": "other"}
    assert focus._evolution(prior, other_epoch, "POSTURE_CHANGED_OTHER", "NOT_IN_CONFIRMATION_DELTA")["code"] == "NOT_COMPARABLE"
    assert focus._evolution(current, current, "NOT_COMPARABLE_POLICY_CHANGE", "NOT_IN_CONFIRMATION_DELTA")["code"] == "NOT_COMPARABLE"


def test_relationships_keep_market_weakness_and_missing_fundamentals_from_becoming_votes():
    decision = {
        "tactical_phase": integrated.TACTICAL_BREAKOUT_SETUP, "fundamental_state": integrated.FUNDAMENTAL_INSUFFICIENT,
        "research_action_posture": "WAIT_FOR_CONFIRMATION", "evidence_axis_coherence": {
            "state": integrated.EVIDENCE_AXIS_COHERENCE_MIXED,
            "reason_codes": ["CONSTRUCTIVE_TECHNICAL_STRUCTURE_WITH_WEAK_MARKET_OR_SECTOR_CONTEXT"]},
        "market_sector_context": {"market_regime": "RISK_OFF"},
        "valuation_context_summary": {"status": "UNAVAILABLE", "unavailable_reason_codes": ["VALUATION_NO_USABLE_RELATIVE_METHOD"],
                                     "peer_relative_state": "NOT_COMPARABLE", "size_context": {"role": "SIZE_CONTEXT_NOT_A_VALUATION_MULTIPLE"}},
        "exact_capabilities_unavailable": ["HISTORICAL_PIT"],
        "corporate_intelligence_context": {"freshest_material_event": {"title": "Tender", "effective_date": None},
                                          "blocker_reason_codes": []},
        "fundamental_synthesis": {}, "missing_evidence_decision_effect": {}, "trigger": {}, "invalidation": {},
    }
    queue_record = {"research_priority_tier": "PRIORITY_NOW", "blocking_reasons": ["FUNDAMENTAL_CONTEXT_ABSENT"],
                    "priority_reasons": [], "content_identity": "q"}
    kinds = {item["kind"] for item in focus._relationships(queue_record, decision)}
    assert "PRIORITY_DIFFERS_FROM_ACTION_READINESS" in kinds
    assert "TACTICAL_CONSTRUCTIVE_FUNDAMENTAL_INSUFFICIENT" in kinds
    assert "TACTICAL_CONSTRUCTIVE_MARKET_CONTEXT_WEAK" in kinds
    assert "NON_COMPARABLE" in kinds
    assert "HISTORICAL_OR_EXACT_AUTHORITY_CLOSED" in kinds
    questions = focus._questions(queue_record, decision, {"trigger": {"numeric_display_reason_codes": ["CONDITION_NOT_MACHINE_EVALUABLE"]}, "invalidation": {}})
    assert any(item["source_code"] == "EFFECTIVE_DATE_ABSENT" for item in questions)
    assert any("không suy ra" in item["question"].lower() or "Không suy" in item["question"] for item in questions)
    valuation = focus._valuation(decision)
    assert valuation["prohibited"].startswith("NO_FAIR_VALUE")
    assert "fair_value" not in valuation


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _install(root, artifact, queue, opportunity_artifact, *, tactical_state):
    date = artifact["session"]
    artifact = copy.deepcopy(artifact)
    artifact["schema_version"] = "integrated_investment_decision_product/1.0.0"
    artifact["coverage"] = {"universe_denominator": len(artifact["records"]), "integrated_context_available": len(artifact["records"])}
    artifact.update(integrated.content_identity(artifact))
    iid_path = root / "operations-review" / ("integrated-investment-decision-product-v1-" + date.replace("-", "")) / "integrated_investment_decision_product_artifact.json"
    _write(iid_path, artifact)
    tactical_artifact = {"session": date, "contract_version": tactical.CONTRACT_VERSION,
                         "records": {ticker: {"entry_state": tactical_state} for ticker in artifact["records"]}}
    tactical_artifact.update(tactical.content_identity(tactical_artifact))
    tactical_path = _write(root / ("tactical-" + date + ".json"), tactical_artifact)
    selection = {name: {"path": name + ".json", "artifact_identity": "synthetic:" + name + ":" + date} for name in ops.REQUIRED}
    selection["tactical"] = {"path": tactical_path.relative_to(root).as_posix(), "artifact_identity": tactical_artifact["artifact_identity"]}
    return artifact, selection, iid_path


@pytest.fixture(autouse=True)
def safe_host(monkeypatch):
    original = preview.resource_gate
    monkeypatch.setattr(preview, "resource_gate", lambda available_bytes=None: original(available_bytes=2 * 1024**3))


def test_end_to_end_binds_queue_to_decision_and_renders_without_a_vote(tmp_path):
    current_session, previous_session = "2026-01-02", "2026-01-01"
    specs = [("REV1", "EARLY_REVERSAL", "PRIORITY_NOW"), ("BAS1", "BASE_ACCUMULATION", "PRIORITY_NOW"),
             ("BRK1", "BREAKOUT", "SETUP_WATCH")]
    opportunity_artifact, queue = _queue(specs)
    opportunity_artifact["research_session"] = current_session
    opportunity_artifact.update(opportunity.content_identity(opportunity_artifact))
    queue = queues.build(opportunity=opportunity_artifact, triage={"high_priority_review_eligible_records": [], "artifact_identity": "triage:synthetic"})
    records = {}
    for ticker, lane, _tier in specs:
        watch = {"EARLY_REVERSAL": "REV", "BASE_ACCUMULATION": "BAS", "BREAKOUT": "BRK"}[lane]
        changes = {"market_structure_state": "EARLY_BULLISH_REVERSAL"} if lane == "EARLY_REVERSAL" else (
            {"market_structure_state": "SIDEWAYS", "base_status": "IN_BASE", "range_state": "RANGE_STABLE"} if lane == "BASE_ACCUMULATION"
            else {"breakout_state_v3": "TESTING_PIVOT", "trigger_state": "APPROACHING"})
        records[ticker] = HELPERS["_record"](current_session, ticker, watch, changes, priority=queue["records"][ticker])
    # A second integrated record is outside the queue on purpose.
    records["EXTRA"] = HELPERS["_record"](current_session, "EXTRA", "UPT", {})
    current = {"contract_version": integrated.CONTRACT_VERSION, "session": current_session,
               "research_action_policy_version": integrated.RESEARCH_ACTION_POLICY_VERSION, "records": records}
    previous_records = {ticker: HELPERS["_record"](previous_session, ticker, "REV", {"market_structure_state": "SIDEWAYS"})
                        for ticker, _, _ in specs}
    previous = {"contract_version": integrated.CONTRACT_VERSION, "session": previous_session,
                "research_action_policy_version": integrated.RESEARCH_ACTION_POLICY_VERSION, "records": previous_records}
    current, current_selection, _ = _install(tmp_path, current, queue, opportunity_artifact, tactical_state="SIDEWAYS_NEUTRAL")
    previous, previous_selection, _ = _install(tmp_path, previous, queue, opportunity_artifact, tactical_state="SIDEWAYS_NEUTRAL")
    registry = {"contract_version": "daily_research_session_input_registry/v1", "sessions": {}, "completed_sessions": {}}
    locations = {}
    for artifact, selection in ((previous, previous_selection), (current, current_selection)):
        date = artifact["session"]
        lock = {key: value["artifact_identity"] for key, value in selection.items()}
        registry["sessions"][date] = selection
        registry["completed_sessions"][date] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
                                                "frozen_input_identities": lock}
        manifest = {"contract_version": ops.CONTRACT_VERSION, "schema_version": "1.0.0", "market_session": date,
                    "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
                    "input_artifacts": {key: {"artifact_identity": value} for key, value in lock.items()},
                    "outputs": {"integrated_investment_decision_product": artifact["artifact_identity"],
                                "daily_opportunity_decision_queue": queue["artifact_identity"] if date == current_session else "daily_opportunity_decision_queue:absent",
                                "opportunity_prioritization": opportunity_artifact["artifact_identity"] if date == current_session else "current_opportunity_prioritization:absent"}}
        # Previous session needs its own valid queue. Reuse the builder with the previous session.
        if date == previous_session:
            previous_opportunity = copy.deepcopy(opportunity_artifact)
            previous_opportunity["research_session"] = previous_session
            previous_opportunity.update(opportunity.content_identity(previous_opportunity))
            previous_queue = queues.build(opportunity=previous_opportunity, triage={"high_priority_review_eligible_records": [], "artifact_identity": "triage:previous"})
            manifest["outputs"]["daily_opportunity_decision_queue"] = previous_queue["artifact_identity"]
            manifest["outputs"]["opportunity_prioritization"] = previous_opportunity["artifact_identity"]
        else:
            previous_queue = previous_opportunity = None
        manifest["operation_identity"] = ops._identity(manifest)
        operation = tmp_path / "operations-review/daily-research-session-operations-v1" / date / manifest["operation_identity"].split(":")[1]
        _write(operation / "run_manifest.json", manifest)
        if date == current_session:
            _write(operation / focus.QUEUE_FILE, queue)
            _write(operation / focus.OPPORTUNITY_FILE, opportunity_artifact)
        else:
            _write(operation / focus.QUEUE_FILE, previous_queue)
            _write(operation / focus.OPPORTUNITY_FILE, previous_opportunity)
        locations[date] = operation
    _write(tmp_path / "config/daily_research_session_input_registry.json", registry)
    # The previous integrated records were built with the current queue's priority identity.
    # Rebuild previous decisions against the previous queue so the join is real.
    previous_queue = json.loads((locations[previous_session] / focus.QUEUE_FILE).read_text(encoding="utf-8"))
    previous["records"] = {ticker: HELPERS["_record"](previous_session, ticker, "REV", {"market_structure_state": "SIDEWAYS"},
                                                      priority=previous_queue["records"][ticker])
                           for ticker, _, _ in specs}
    previous, previous_selection, _ = _install(tmp_path, previous, previous_queue, opportunity_artifact, tactical_state="SIDEWAYS_NEUTRAL")
    lock = {key: value["artifact_identity"] for key, value in previous_selection.items()}
    registry["sessions"][previous_session] = previous_selection
    registry["completed_sessions"][previous_session]["frozen_input_identities"] = lock
    manifest = json.loads((locations[previous_session] / "run_manifest.json").read_text(encoding="utf-8"))
    manifest["input_artifacts"] = {key: {"artifact_identity": value} for key, value in lock.items()}
    manifest["outputs"]["integrated_investment_decision_product"] = previous["artifact_identity"]
    manifest.pop("operation_identity", None)
    manifest["operation_identity"] = ops._identity(manifest)
    new_operation = tmp_path / "operations-review/daily-research-session-operations-v1" / previous_session / manifest["operation_identity"].split(":")[1]
    if new_operation != locations[previous_session]:
        _write(new_operation / "run_manifest.json", manifest)
        _write(new_operation / focus.QUEUE_FILE, previous_queue)
        _write(new_operation / focus.OPPORTUNITY_FILE, json.loads((locations[previous_session] / focus.OPPORTUNITY_FILE).read_text(encoding="utf-8")))
        locations[previous_session] = new_operation
    else:
        _write(locations[previous_session] / "run_manifest.json", manifest)
    _write(tmp_path / "config/daily_research_session_input_registry.json", registry)
    report = focus.evaluate_research_focus(
        repo_root=tmp_path, session=current_session, current_operation=locations[current_session],
        previous_operation=locations[previous_session], max_tickers=3)
    assert report["status"] == "COMPLETE"
    assert report["population"]["opportunity_queue_denominator"] == 3
    assert report["population"]["integrated_decision_denominator"] == 4
    assert report["population"]["difference_interpretation"].startswith("DISTINCT_SOURCE_DEFINED")
    assert [item["ticker"] for item in report["dossiers"]] == ["REV1", "BAS1", "BRK1"]
    assert all(item["authority_boundary"]["is_actionable"] is False for item in report["dossiers"])
    blob = json.dumps(report["dossiers"])
    assert "target_price" not in blob and "fair_value" not in blob and "expected_return" not in blob
    assert all(item["thesis"]["not_a_vote"] is True for item in report["dossiers"])
    assert "PRIORITY_NOW_IS_RESEARCH_ATTENTION_NOT_BUY_NOW" in blob
    rendered = focus.render_markdown(report)
    assert "không phải khuyến nghị" in rendered
    assert "Ủng hộ từ quyết định" in rendered
    assert "Lý do ưu tiên của hàng đợi phiên" in rendered
    assert "Trùng danh tính mới được nối" in rendered
    assert "REV1" in rendered and "BRK1" in rendered
    first = report["dossiers"][0]
    assert "EARLY_REVERSAL_REASON" in first["discovery"]["priority_reasons"]
    assert "EARLY_REVERSAL_REASON" not in first["thesis"]["supporting"]
    assert "FUNDAMENTAL_CONTEXT_ABSENT" in first["discovery"]["blocking_reasons"]
    assert "FUNDAMENTAL_CONTEXT_ABSENT" not in first["thesis"]["opposing"]
    assert first["source"]["queue_record_identity_comparable"] is True
    again = focus.evaluate_research_focus(
        repo_root=tmp_path, session=current_session, current_operation=locations[current_session],
        previous_operation=locations[previous_session], max_tickers=3)
    assert again["artifact_identity"] == report["artifact_identity"]
    preview_before = action_center.evaluate_selected_research_preview(
        repo_root=tmp_path, session=current_session, tickers=["REV1"],
        current_operation=locations[current_session], previous_operation=locations[previous_session])
    assert preview_before["contract_version"] == preview.CONTRACT
    assert preview_before["scope"]["selection_rule"] == "EXPLICIT_TICKER_SELECTION"


def test_absent_queue_blocks_lane_selection_and_keeps_explicit_preview(tmp_path):
    _, queue = _queue([("A1", "EARLY_REVERSAL", "PRIORITY_NOW")])
    record = HELPERS["_record"]("2026-01-02", "A1", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, priority=queue["records"]["A1"])
    artifact = {"contract_version": integrated.CONTRACT_VERSION, "session": "2026-01-02",
                "research_action_policy_version": integrated.RESEARCH_ACTION_POLICY_VERSION, "records": {"A1": record}}
    artifact, selection, _ = _install(tmp_path, artifact, queue, {}, tactical_state="SIDEWAYS_NEUTRAL")
    lock = {key: value["artifact_identity"] for key, value in selection.items()}
    registry = {"contract_version": "daily_research_session_input_registry/v1",
                "sessions": {"2026-01-02": selection},
                "completed_sessions": {"2026-01-02": {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
                                                     "frozen_input_identities": lock}}}
    manifest = {"contract_version": ops.CONTRACT_VERSION, "schema_version": "1.0.0", "market_session": "2026-01-02",
                "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
                "input_artifacts": {key: {"artifact_identity": value} for key, value in lock.items()},
                "outputs": {"integrated_investment_decision_product": artifact["artifact_identity"]}}
    manifest["operation_identity"] = ops._identity(manifest)
    operation = tmp_path / "operations-review/daily-research-session-operations-v1/2026-01-02" / manifest["operation_identity"].split(":")[1]
    _write(operation / "run_manifest.json", manifest)
    _write(tmp_path / "config/daily_research_session_input_registry.json", registry)
    with pytest.raises(focus.ResearchFocusError, match="QUEUE_OR_OPPORTUNITY_OUTPUT_NOT_IN_OPERATION_MANIFEST"):
        focus.evaluate_research_focus(repo_root=tmp_path, session="2026-01-02", current_operation=operation, max_tickers=1)
    report = focus.evaluate_research_focus(
        repo_root=tmp_path, session="2026-01-02", current_operation=operation, max_tickers=1,
        explicit_tickers_when_queue_blocked=["A1"])
    assert report["status"] == "SELECTION_BLOCKED_EXPLICIT_PREVIEW"
    assert report["selection_authority"] == "EXPLICIT_TICKER_PREVIEW_QUEUE_BLOCKED"
    assert report["dossiers"][0]["ticker"] == "A1"
    assert report["dossiers"][0]["primary_lane"] is None


def _opportunity(specs, *, session, source_tag, reasons):
    records = {}
    for ticker, lane, tier in specs:
        records[ticker] = {
            "priority_tier": tier, "eligible_strategies": [lane], "lane_priority": {lane: tier},
            "tactical_state": "EARLY_REVERSAL_CANDIDATE", "entry_action": "EARLY_ENTRY",
            "scenario_status": "SCENARIO_PARTIAL", "event_context_status": "NONE",
            "fundamental_context_status": "INSUFFICIENT", "data_quality_status": "SUFFICIENT",
            "priority_reasons": list(reasons), "blocking_reasons": ["FUNDAMENTAL_CONTEXT_ABSENT"],
            "invalidation_or_context_warnings": [], "content_identity": "opportunity:" + ticker + ":" + source_tag,
            "source_input_identities": {"tactical": source_tag},
            "official_current_universe_status": "CURRENT_OFFICIAL",
        }
    artifact = {"schema_version": "1.0.0", "contract_version": opportunity.CONTRACT_VERSION,
                "research_session": session, "source_artifact_identities": {"synthetic": source_tag},
                "records": records, "coverage": {"current_official_universe": len(records)}}
    artifact.update(opportunity.content_identity(artifact))
    queue = queues.build(opportunity=artifact, triage={
        "high_priority_review_eligible_records": [], "cohort_definitions": {}, "artifact_identity": "triage:" + source_tag})
    return artifact, queue


def _seal_focus_session(root, *, session, queue, opportunity_artifact, decision_records, decision_queue_identity):
    artifact = {"contract_version": integrated.CONTRACT_VERSION, "session": session,
                "research_action_policy_version": integrated.RESEARCH_ACTION_POLICY_VERSION,
                "records": decision_records,
                "source_artifacts": {"priority_queue": decision_queue_identity}}
    artifact, selection, _ = _install(root, artifact, queue, opportunity_artifact, tactical_state="SIDEWAYS_NEUTRAL")
    lock = {key: value["artifact_identity"] for key, value in selection.items()}
    registry = {"contract_version": "daily_research_session_input_registry/v1",
                "sessions": {session: selection},
                "completed_sessions": {session: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
                                                 "frozen_input_identities": lock}}}
    manifest = {"contract_version": ops.CONTRACT_VERSION, "schema_version": "1.0.0", "market_session": session,
                "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
                "input_artifacts": {key: {"artifact_identity": value} for key, value in lock.items()},
                "outputs": {"integrated_investment_decision_product": artifact["artifact_identity"],
                            "daily_opportunity_decision_queue": queue["artifact_identity"],
                            "opportunity_prioritization": opportunity_artifact["artifact_identity"]}}
    manifest["operation_identity"] = ops._identity(manifest)
    operation = root / "operations-review/daily-research-session-operations-v1" / session / manifest["operation_identity"].split(":")[1]
    _write(operation / "run_manifest.json", manifest)
    _write(operation / focus.QUEUE_FILE, queue)
    _write(operation / focus.OPPORTUNITY_FILE, opportunity_artifact)
    _write(root / "config/daily_research_session_input_registry.json", registry)
    return operation


def test_two_valid_queues_keep_tier_match_from_becoming_lineage(tmp_path):
    session = "2026-01-02"
    specs = [("ANT", "EARLY_REVERSAL", "PRIORITY_NOW")]
    operation_opportunity, operation_queue = _opportunity(specs, session=session, source_tag="operation", reasons=["OPERATION_QUEUE_REASON"])
    _decision_opportunity, decision_queue = _opportunity(specs, session=session, source_tag="decision", reasons=["DECISION_QUEUE_REASON"])
    assert operation_queue["artifact_identity"] != decision_queue["artifact_identity"]
    assert queues.content_identity(operation_queue)["artifact_identity"] == operation_queue["artifact_identity"]
    assert queues.content_identity(decision_queue)["artifact_identity"] == decision_queue["artifact_identity"]
    operation_record = operation_queue["records"]["ANT"]
    decision_record = decision_queue["records"]["ANT"]
    assert operation_record["research_priority_tier"] == decision_record["research_priority_tier"] == "PRIORITY_NOW"
    assert operation_record["entry_relevant"] == decision_record["entry_relevant"]
    assert operation_record["content_identity"] != decision_record["content_identity"]
    built = HELPERS["_record"](session, "ANT", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, priority=decision_record)
    assert built["research_action_posture"] in {"EARLY_WATCH", "WAIT_FOR_CONFIRMATION", "AVOID"}
    original_posture = built["research_action_posture"]
    operation = _seal_focus_session(
        tmp_path, session=session, queue=operation_queue, opportunity_artifact=operation_opportunity,
        decision_records={"ANT": built}, decision_queue_identity=decision_queue["artifact_identity"])
    report = focus.evaluate_research_focus(repo_root=tmp_path, session=session, current_operation=operation, max_tickers=1)
    assert report["status"] == "LANE_SELECTION_QUALIFIED_PRIORITY_RECORD_LINEAGE_UNBOUND"
    assert report["priority_lineage"]["current"]["record_identity_comparable"] is False
    assert report["population"]["opportunity_queue_denominator"] == 1
    assert report["population"]["integrated_decision_denominator"] == 1
    assert report["qualified_count"] == 1
    assert report["selected_count"] == 1
    dossier = report["dossiers"][0]
    assert dossier["summary"]["research_priority_tier"] == "PRIORITY_NOW"
    assert dossier["summary"]["research_action_posture"] == original_posture
    assert dossier["source"]["priority_record_lineage"] == "UNBOUND_DIFFERENT_QUEUE_ARTIFACT"
    assert dossier["source"]["queue_record_identity_comparable"] is False
    assert dossier["source"]["priority_queue_record_identity"] == operation_record["content_identity"]
    assert dossier["source"]["decision_priority_queue_record_identity"] == decision_record["content_identity"]
    assert "OPERATION_QUEUE_REASON" in dossier["discovery"]["priority_reasons"]
    assert "OPERATION_QUEUE_REASON" not in dossier["thesis"]["supporting"]
    assert "DECISION_QUEUE_REASON" not in dossier["thesis"]["supporting"]
    assert all(item["causal"] is False for item in dossier["relationships"])
    rendered = focus.render_markdown(report)
    assert "Không suy ra cùng một bản ghi" in rendered
    assert "là cùng một bản ghi" not in rendered
    assert operation_record["content_identity"] in rendered
    assert decision_record["content_identity"] in rendered
    assert "Lý do ưu tiên của hàng đợi phiên" in rendered
    assert "Ủng hộ từ quyết định" in rendered
    assert original_posture != "AVOID" or dossier["summary"]["research_action_posture"] == "AVOID"


def test_unbound_queue_still_rejects_embedded_tier_disagreement_and_same_artifact_tamper():
    _, operation_queue = _opportunity([("ANT", "EARLY_REVERSAL", "PRIORITY_NOW")], session="2026-01-02", source_tag="operation", reasons=["OPERATION_QUEUE_REASON"])
    _, decision_queue = _opportunity([("ANT", "EARLY_REVERSAL", "SETUP_WATCH")], session="2026-01-02", source_tag="decision-tier", reasons=["DECISION_QUEUE_REASON"])
    operation_record = operation_queue["records"]["ANT"]
    decision = {"ticker": "ANT", "source_identities": {"priority_queue_record_identity": decision_queue["records"]["ANT"]["content_identity"]},
                "opportunity_priority": {"status": "AVAILABLE",
                                         "research_priority_tier": decision_queue["records"]["ANT"]["research_priority_tier"],
                                         "entry_relevant": decision_queue["records"]["ANT"]["entry_relevant"]}}
    opportunity_record = {"content_identity": operation_record["opportunity_record_content_identity"]}
    unbound = focus._bind(operation_record, decision, opportunity_record, require_queue_record_identity=False)
    assert unbound["status"] == "SOURCE_IDENTITY_MISMATCH"
    assert "EMBEDDED_PRIORITY_TIER_MISMATCH" in unbound["reason_codes"]
    same_artifact = focus._priority_lineage(
        {"artifact_identity": operation_queue["artifact_identity"]},
        {"source_artifacts": {"priority_queue": operation_queue["artifact_identity"]}})
    assert same_artifact["status"] == "SAME_QUEUE_ARTIFACT"
    assert same_artifact["record_identity_comparable"] is True
    conflict = focus._bind(operation_record, decision, opportunity_record, require_queue_record_identity=True)
    assert "PRIORITY_QUEUE_RECORD_IDENTITY_MISMATCH" in conflict["reason_codes"]
    absent = focus._priority_lineage({"artifact_identity": operation_queue["artifact_identity"]}, {})
    assert absent["status"] == "DECISION_PRIORITY_QUEUE_IDENTITY_ABSENT"
    assert absent["record_identity_comparable"] is False


def test_tampered_priority_record_and_queue_bytes_fail_closed(tmp_path):
    session = "2026-01-02"
    opportunity_artifact, queue = _opportunity([("ANT", "EARLY_REVERSAL", "PRIORITY_NOW")], session=session, source_tag="sealed", reasons=["OPERATION_QUEUE_REASON"])
    path = tmp_path / "daily_opportunity_decision_queue_artifact.json"
    tampered = copy.deepcopy(queue)
    tampered["records"]["ANT"]["content_identity"] = "daily_opportunity_decision_record:tampered"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(focus.ResearchFocusError, match="QUEUE_IDENTITY"):
        focus._verified_queue(path, session=session, expected_identity=queue["artifact_identity"])
    decision = {"ticker": "OTHER", "source_identities": {"priority_queue_record_identity": queue["records"]["ANT"]["content_identity"]},
                "opportunity_priority": {"status": "AVAILABLE", "research_priority_tier": "PRIORITY_NOW",
                                         "entry_relevant": queue["records"]["ANT"]["entry_relevant"]}}
    mismatch = focus._bind(queue["records"]["ANT"], decision, {"content_identity": queue["records"]["ANT"]["opportunity_record_content_identity"]})
    assert "TICKER_MISMATCH" in mismatch["reason_codes"]


def test_withholding_epoch_and_insufficient_fundamental_keep_their_own_meaning():
    current = {"research_action_posture": "EARLY_WATCH", "tactical_phase": "EARLY_REVERSAL",
               "breakout_state_v3": "BELOW_PIVOT", "fundamental_state": integrated.FUNDAMENTAL_INSUFFICIENT,
               "fundamental_decision_policy_version": "v1"}
    assert focus._evolution(None, current, "NEW_EARLY_WATCH", "NOT_IN_CONFIRMATION_DELTA")["code"] == "NEW_CANDIDATE"
    assert current["fundamental_state"] == integrated.FUNDAMENTAL_INSUFFICIENT
    other = {**current, "fundamental_decision_policy_version": "other-epoch", "fundamental_state": integrated.FUNDAMENTAL_IMPROVING}
    assert focus._evolution(current, other, "POSTURE_UNCHANGED", "NOT_IN_CONFIRMATION_DELTA")["code"] == "NOT_COMPARABLE"
    confirmation = focus._confirmation(
        {"tactical_phase": "BREAKOUT_SETUP", "trigger": {"status": "ARMED"}},
        {"trigger": {"status": "ARMED", "numeric_display_status": "WITHHELD_UNQUALIFIED_BOUNDARY"},
         "invalidation": {"numeric_display_status": "AVAILABLE"}},
        None)
    assert confirmation["numeric_levels_withheld"] is True
    assert confirmation["observed_confirmation"] is False
    assert confirmation["future_trigger_is_not_an_observed_event"] is True


def test_default_preview_identity_stays_outside_this_projection():
    assert preview.CONTRACT == "action_center_selected_research_preview/v1"
    assert focus.CONTRACT == "current_research_priority_focus/v1"
    assert not hasattr(action_center, "evaluate_research_focus")
