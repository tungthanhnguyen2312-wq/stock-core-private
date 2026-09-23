"""CURRENT_DECISION_SURFACE_CONVERGENCE_V1 -- hermetic cross-surface convergence contract.

One canonical tuple ``(ticker, research_action_posture, evidence_currency)`` for every ticker of
the canonical denominator, identical on every compared surface:

* Producer Integrated Decision record (the authority),
* Dashboard Workspace card, its published public read model (index), Screener decision view,
* AI handoff Daily Integrated Decision Brief full-universe ``decision_surface_index``,
* Action Center full-universe ``decision_surface_index``.

Also pins the M1 invariants: evidence currency lineage, NO_CURRENT_EVIDENCE never WAIT, priority
orthogonality (never posture / currency / trigger / invalidation / decision identity), explicit
position context, research_stance secondary only. Every Integrated Decision artifact here is built
by the real production builder -- nothing is hand-faked.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

import canonical_current_product_projections as ccpp
import canonical_post_close_pipeline as cpc
import current_opportunity_prioritization as opportunity_module
import daily_integrated_decision_brief as brief_module
import dashboard_home_summary as home_module
import full_universe_entry_candidate_triage as triage_module
import integrated_investment_decision_product as iidp
import investment_decision_workspace_projection as workspace_module
import personal_investment_decision_action_center as action_center
import workspace_public_read_model as read_model
from _integrated_decision_fixture import disposition_artifact, disposition_record, integrated_decision
from test_canonical_current_product_projections import _registry_inputs
from test_integrated_investment_decision_product import _sample_financial_record, _sample_tactical_record

SESSION = "2026-09-11"
CUR = iidp.EVIDENCE_CURRENCY_CURRENT_SESSION
NONE = iidp.EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE

# Scenario archetypes chosen to reach every major posture branch through the unmodified policy.
_ARCHETYPES = {
    "BREAKOUT": dict(tactical=_sample_tactical_record(), financial=True),
    "DOWNTREND": dict(tactical=_sample_tactical_record(
        market_structure_state="DOWNTREND", breakout_state_v3="NO_VALID_PIVOT", trigger_state="BELOW_TRIGGER",
        trigger_type="NO_TRIGGER", bos_state="BEARISH_BOS_DETECTED_BY_RULE"), financial=True),
    "EXTENDED": dict(tactical=_sample_tactical_record(breakout_state_v3="EXTENDED_AFTER_BREAKOUT", distance_to_pivot_pct=0.12), financial=True),
    "UPTREND_HOLD": dict(tactical=_sample_tactical_record(
        breakout_state_v3="NO_VALID_PIVOT", trigger_state="BELOW_TRIGGER", trigger_type="NO_TRIGGER", bos_state="NO_BOS"), financial=True),
    "RANGE_WAIT": dict(tactical=_sample_tactical_record(
        market_structure_state="RANGE", breakout_state_v3="NO_VALID_PIVOT", trigger_state="BELOW_TRIGGER",
        trigger_type="NO_TRIGGER", bos_state="NO_BOS"), financial=True),
    "RETEST": dict(tactical=_sample_tactical_record(
        breakout_state_v3="TESTING_PIVOT", trigger_state="BELOW_TRIGGER", trigger_type="RETEST_BROKEN_PIVOT", bos_state="NO_BOS"), financial=True),
    "EARLY_REVERSAL": dict(tactical=_sample_tactical_record(
        market_structure_state="EARLY_BULLISH_REVERSAL", breakout_state_v3="NO_VALID_PIVOT", trigger_state="BELOW_TRIGGER",
        trigger_type="NO_TRIGGER", bos_state="NO_BOS", choch_state="BULLISH_CHOCH_DETECTED_BY_RULE"), financial=True),
    "NO_TECHNICAL_WITH_FUNDAMENTALS": dict(tactical={"eligible": False}, financial=True),
    "NOTHING": dict(tactical={"eligible": False}, financial=False),
}
_CURRENCIES = (CUR, "LAST_TRADE_AS_OF:2026-09-04", NONE, "LAST_TRADE_AS_OF:2026-08-26")


def _no_base(record):
    # Neither compressed nor basing: keeps the record out of the BREAKOUT_SETUP phase.
    return {**record, "base_status": "NO_BASE", "range_state": "NORMAL"}


_ARCHETYPES["UPTREND_HOLD"]["tactical"] = _no_base(_ARCHETYPES["UPTREND_HOLD"]["tactical"])
_ARCHETYPES["RANGE_WAIT"]["tactical"] = _no_base(_ARCHETYPES["RANGE_WAIT"]["tactical"])


def _universe(size: int = 72):
    """Deterministic synthetic canonical universe covering archetype x currency combinations."""
    names = sorted(_ARCHETYPES)
    tickers, tactical, financial, currency = [], {}, {}, {}
    for index in range(size):
        ticker = f"{chr(65 + index % 26)}{index:02d}"
        archetype = _ARCHETYPES[names[index % len(names)]]
        tickers.append(ticker)
        tactical[ticker] = {"ticker": ticker, **copy.deepcopy(archetype["tactical"])}
        if archetype["financial"]:
            financial[ticker] = _sample_financial_record()
        currency[ticker] = _CURRENCIES[(index // len(names)) % len(_CURRENCIES)]
    return sorted(tickers), tactical, financial, currency


def _integrated(tickers, tactical, financial, currency, **kwargs):
    return integrated_decision(SESSION, tickers, tactical_records=tactical, financial_records=financial,
                               currency_by_ticker=currency, **kwargs)


def _priority_queue(tickers):
    tiers = ("PRIORITY_NOW", "SETUP_WATCH", "MONITOR", "DATA_LIMITED")
    records = {
        t: {"ticker": t, "research_priority_tier": tiers[i % len(tiers)], "entry_relevant": i % 3 == 0,
            "entry_action": "EARLY_ENTRY" if i % 3 == 0 else "WATCH", "priority_reasons": ["TEST"],
            "content_identity": f"daily_opportunity_decision_record:{t}"}
        for i, t in enumerate(tickers) if i % 5 != 4  # some tickers explicitly lack priority evidence
    }
    return {"contract_version": "daily_opportunity_decision_queue/v1", "research_session": SESSION,
            "artifact_identity": "daily_opportunity_decision_queue:test", "records": records}


def _tuple(row):
    return (row["ticker"], row["research_action_posture"], row["evidence_currency"])


# ── Evidence currency contract ─────────────────────────────────────────────────────────────────

def test_evidence_currency_semantics_are_derived_only_from_retained_disposition_evidence():
    resolve = iidp.resolve_evidence_currency
    assert resolve(disposition_record("A", session=SESSION, currency=CUR), decision_session=SESSION) == CUR
    assert resolve(disposition_record("A", session=SESSION, currency="LAST_TRADE_AS_OF:2026-09-04"),
                   decision_session=SESSION) == "LAST_TRADE_AS_OF:2026-09-04"
    assert resolve(None, decision_session=SESSION) == NONE
    assert resolve({"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL"}, decision_session=SESSION) == NONE
    # Same-session coverage claimed but the feature date is not the decision session: never CURRENT.
    assert resolve({"disposition": "SAME_SESSION_TECHNICAL_COVERED", "has_exact_session_bar": True,
                    "is_current_session": True, "feature_as_of_session": "2026-09-10"}, decision_session=SESSION) == NONE
    # An exact bar without a current technical window is not established technical evidence.
    assert resolve({"disposition": "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION", "has_exact_session_bar": True,
                    "feature_as_of_session": None}, decision_session=SESSION) == NONE
    # Conflicted evidence never yields a dated currency; nor does a future/undated date.
    assert resolve({"disposition": "MALFORMED_OR_CONFLICTED", "feature_as_of_session": "2026-09-04"}, decision_session=SESSION) == NONE
    assert resolve({"disposition": "PROVIDER_SESSION_UNAVAILABLE", "feature_as_of_session": "2026-09-12"}, decision_session=SESSION) == NONE
    assert resolve({"disposition": "PROVIDER_SESSION_UNAVAILABLE", "feature_as_of_session": "garbage"}, decision_session=SESSION) == NONE
    assert all(iidp.is_valid_evidence_currency(v) for v in (CUR, NONE, "LAST_TRADE_AS_OF:2026-09-04"))
    assert not iidp.is_valid_evidence_currency("LAST_TRADE_AS_OF:yesterday")


def test_evidence_currency_source_is_strictly_session_and_identity_checked():
    records = {"AAA": disposition_record("AAA", session=SESSION, currency=CUR)}
    tactical = {"artifact_identity": "t", "records": {"AAA": _sample_tactical_record()}}
    with pytest.raises(iidp.IntegratedDecisionProductError, match="SESSION_MISMATCH"):
        iidp.build_artifact(session=SESSION, requested_at="t", technical_structure_artifact=tactical,
                            technical_coverage_disposition_artifact=disposition_artifact(records, session="2026-09-10"))
    tampered = disposition_artifact(records, session=SESSION)
    tampered["records"]["AAA"]["feature_as_of_session"] = "2026-09-01"
    with pytest.raises(iidp.IntegratedDecisionProductError, match="CONTENT_IDENTITY_INVALID"):
        iidp.build_artifact(session=SESSION, requested_at="t", technical_structure_artifact=tactical,
                            technical_coverage_disposition_artifact=tampered)
    # Absent source: fail closed to NO_CURRENT_EVIDENCE, never silently CURRENT.
    absent = iidp.build_artifact(session=SESSION, requested_at="t", technical_structure_artifact=tactical)
    assert absent["records"]["AAA"]["evidence_currency"] == NONE
    assert absent["source_artifacts"]["technical_coverage_disposition"] is None


# ── NO_CURRENT_EVIDENCE / WAIT invariant ──────────────────────────────────────────────────────

def test_no_current_evidence_never_yields_wait_for_confirmation_across_the_universe():
    tickers, tactical, financial, currency = _universe()
    artifact = _integrated(tickers, tactical, financial, currency)
    records = artifact["records"]
    assert artifact["coverage"]["no_current_evidence_wait_count"] == 0
    for record in records.values():
        if record["evidence_currency"] == NONE:
            assert record["research_action_posture"] != iidp.POSTURE_WAIT_FOR_CONFIRMATION
    gated = [r for r in records.values() if r["evidence_currency_gate"]["applied"]]
    assert gated, "the fixture must exercise the gate"
    for record in gated:
        assert record["research_action_posture"] == iidp.POSTURE_INSUFFICIENT
        assert record["evidence_currency_gate"]["ungated_policy_output"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION
        assert record["missing_evidence_decision_effect"] == iidp.EFFECT_BLOCKS_DECISION
    # The same policy output with established evidence keeps WAIT (only the gate changed, no policy).
    waits_with_evidence = [r for r in records.values() if r["research_action_posture"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION]
    assert waits_with_evidence and all(r["evidence_currency"] != NONE for r in waits_with_evidence)


def test_gate_changes_only_wait_and_no_other_posture():
    tickers, tactical, financial, currency = _universe()
    none_everywhere = _integrated(tickers, tactical, financial, {t: NONE for t in tickers})
    current_everywhere = _integrated(tickers, tactical, financial, {t: CUR for t in tickers})
    for ticker in tickers:
        with_evidence = current_everywhere["records"][ticker]["research_action_posture"]
        without = none_everywhere["records"][ticker]["research_action_posture"]
        if with_evidence == iidp.POSTURE_WAIT_FOR_CONFIRMATION:
            assert without == iidp.POSTURE_INSUFFICIENT
        else:
            assert without == with_evidence


def test_evidence_currency_is_part_of_decision_identity():
    tickers, tactical, financial, _ = _universe(9)
    a = _integrated(tickers, tactical, financial, {t: CUR for t in tickers})
    b = _integrated(tickers, tactical, financial, {t: "LAST_TRADE_AS_OF:2026-09-04" for t in tickers})
    for ticker in tickers:
        assert a["records"][ticker]["research_action_posture"] == b["records"][ticker]["research_action_posture"]
        assert a["records"][ticker]["decision_identity"] != b["records"][ticker]["decision_identity"]


# ── Opportunity priority: wired, orthogonal ────────────────────────────────────────────────────

_PRIORITY_ONLY_FIELDS = {"opportunity_priority", "priority_posture_reconciliation", "evidence_axes", "source_identities"}


def test_priority_is_orthogonal_to_posture_currency_trigger_invalidation_and_decision_identity():
    tickers, tactical, financial, currency = _universe()
    without = _integrated(tickers, tactical, financial, currency)
    with_priority = _integrated(tickers, tactical, financial, currency, priority_queue=_priority_queue(tickers))
    assert with_priority["coverage"]["opportunity_priority_available_count"] > 0
    assert without["coverage"]["opportunity_priority_available_count"] == 0
    assert with_priority["artifact_identity"] != without["artifact_identity"]  # enclosing identity may change
    for ticker in tickers:
        a, b = without["records"][ticker], with_priority["records"][ticker]
        for field in ("research_action_posture", "evidence_currency", "trigger", "invalidation", "decision_identity",
                      "why_now", "evidence_currency_gate", "position_context"):
            assert a[field] == b[field], (ticker, field)
        changed = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
        assert changed <= _PRIORITY_ONLY_FIELDS, (ticker, changed)
        axes_changed = {k for k in a["evidence_axes"] if a["evidence_axes"][k] != b["evidence_axes"][k]}
        assert axes_changed <= {"OPPORTUNITY_PRIORITY"}
        src_changed = {k for k in a["source_identities"] if a["source_identities"][k] != b["source_identities"][k]}
        assert src_changed <= {"priority_queue_record_identity"}
    assert Counter(r["research_action_posture"] for r in without["records"].values()) == Counter(
        r["research_action_posture"] for r in with_priority["records"].values())


def test_stale_priority_queue_is_refused_never_resurrected():
    tickers, tactical, financial, currency = _universe(9)
    stale = _priority_queue(tickers)
    stale["research_session"] = "2026-09-10"
    with pytest.raises(iidp.IntegratedDecisionProductError, match="PRIORITY_QUEUE_SESSION_MISMATCH"):
        _integrated(tickers, tactical, financial, currency, priority_queue=stale)


def _opportunity_and_triage(session):
    record = {
        "priority_tier": "PRIORITY_NOW", "eligible_strategies": ["BREAKOUT"], "lane_priority": {"BREAKOUT": "PRIORITY_NOW"},
        "tactical_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION", "scenario_status": "SCENARIO_READY",
        "event_context_status": "NONE", "fundamental_context_status": "AVAILABLE", "data_quality_status": "AVAILABLE",
        "priority_reasons": ["BREAKOUT=PRIORITY_NOW"], "blocking_reasons": [], "invalidation_or_context_warnings": [],
        "content_identity": "opp_record:1", "source_input_identities": {},
    }
    opportunity = {"contract_version": "current_opportunity_prioritization/v1", "research_session": session,
                   "coverage": {"current_official_universe": 1}, "records": {"AAA": record}}
    opportunity.update(opportunity_module.content_identity(opportunity))
    triage = {"source_market_session": session, "high_priority_review_eligible_records": [], "cohort_definitions": {}}
    triage.update(triage_module.content_identity(triage))
    return opportunity, triage


def test_current_session_priority_queue_resolution_reuses_the_governed_queue_and_fails_closed():
    opportunity, triage = _opportunity_and_triage(SESSION)
    queue, status = cpc.resolve_current_session_priority_queue(SESSION, opportunity=opportunity, triage=triage)
    assert status["status"] == "RESOLVED_SAME_SESSION"
    assert queue["contract_version"] == "daily_opportunity_decision_queue/v1"
    assert queue["research_session"] == SESSION
    assert queue["records"]["AAA"]["research_priority_tier"] == "PRIORITY_NOW"
    stale_opportunity, stale_triage = _opportunity_and_triage("2026-09-10")
    assert cpc.resolve_current_session_priority_queue(SESSION, opportunity=stale_opportunity, triage=triage)[1]["reason"] == \
        "CURRENT_OPPORTUNITY_PRIORITIZATION_SESSION_MISMATCH"
    assert cpc.resolve_current_session_priority_queue(SESSION, opportunity=opportunity, triage=stale_triage)[1]["reason"] == \
        "SESSION_ENTRY_CANDIDATE_TRIAGE_SESSION_MISMATCH"
    tampered = copy.deepcopy(opportunity)
    tampered["records"]["AAA"]["priority_tier"] = "MONITOR"
    assert cpc.resolve_current_session_priority_queue(SESSION, opportunity=tampered, triage=triage)[1]["reason"] == \
        "CURRENT_OPPORTUNITY_PRIORITIZATION_CONTENT_IDENTITY_INVALID"
    assert cpc.resolve_current_session_priority_queue(SESSION, opportunity=None, triage=triage) == (
        None, {"status": "UNAVAILABLE", "reason": "CURRENT_OPPORTUNITY_PRIORITIZATION_NOT_RETAINED"})


def test_canonical_paths_no_longer_hardwire_priority_off():
    source = (Path(cpc.__file__).parent / "canonical_daily_operation.py").read_text(encoding="utf-8")
    assert "priority_queue_artifact=None" not in source
    assert "priority_queue_artifact=None" not in Path(cpc.__file__).read_text(encoding="utf-8")


# ── Position context ────────────────────────────────────────────────────────────────────────────

def test_missing_private_portfolio_is_unknown_position_never_not_held():
    tickers, tactical, financial, currency = _universe(9)
    artifact = _integrated(tickers, tactical, financial, currency)
    for record in artifact["records"].values():
        assert record["position_context"] == {"status": "NOT_SUPPLIED", "position_state": iidp.POSITION_UNKNOWN_NOT_SUPPLIED}
        assert record["portfolio_context"]["is_held"] is None
    supplied = _integrated(tickers, tactical, financial, currency, portfolio_record={"status": "AVAILABLE", "is_held": True})
    assert all(r["position_context"]["position_state"] == "HELD" for r in supplied["records"].values())


# ── Workspace boundary ─────────────────────────────────────────────────────────────────────────

def _workspace_inputs(tickers, session=SESSION):
    registry_inputs = _registry_inputs(tuple(tickers), session=session)
    return registry_inputs


def test_workspace_requires_same_session_same_ticker_set_self_consistent_integrated_decision():
    tickers = ["AAA", "BBB"]
    registry_inputs = _workspace_inputs(tickers)
    good = integrated_decision(SESSION, tickers)
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=registry_inputs, supplementary={}, requested_at="t",
        integrated_investment_decision_product=good,
    )
    assert bundle["workspace"]["source_artifacts"]["integrated_investment_decision_product"] == good["artifact_identity"]
    for bad, reason in (
        (None, "INTEGRATED_DECISION_INPUT_REQUIRED"),
        (integrated_decision("2026-09-10", tickers), "INTEGRATED_DECISION_SESSION_MISMATCH"),
        (integrated_decision(SESSION, ["AAA"]), "INTEGRATED_DECISION_TICKER_SET_MISMATCH"),
    ):
        with pytest.raises(workspace_module.InvestmentDecisionWorkspaceError, match=reason):
            ccpp.materialize_current_investment_decision_workspace(
                session=SESSION, registry_inputs=registry_inputs, supplementary={}, requested_at="t",
                integrated_investment_decision_product=bad,
            )
    tampered = copy.deepcopy(good)
    tampered["records"]["AAA"]["research_action_posture"] = iidp.POSTURE_INITIATE_ON_BREAKOUT
    with pytest.raises(workspace_module.InvestmentDecisionWorkspaceError, match="CONTENT_IDENTITY_INVALID"):
        ccpp.materialize_current_investment_decision_workspace(
            session=SESSION, registry_inputs=registry_inputs, supplementary={}, requested_at="t",
            integrated_investment_decision_product=tampered,
        )


def test_top_level_materialization_without_integrated_decision_is_skipped_not_a_stance_fallback(tmp_path):
    result = ccpp.materialize_and_write_current_product_projections(
        root=tmp_path, session=SESSION, operation_dir=tmp_path / "op", registry_inputs=_workspace_inputs(["AAA"]),
        requested_at="t",
    )
    assert result["status"] == "SKIPPED"
    assert "INTEGRATED_DECISION_INPUT_REQUIRED" in result["detail"]
    assert not (tmp_path / "op" / ccpp.WORKSPACE_ARTIFACT_FILENAME).exists()


# ── Full-universe cross-surface convergence ────────────────────────────────────────────────────

@pytest.fixture()
def converged_surfaces(tmp_path):
    tickers, tactical, financial, currency = _universe()
    integrated = _integrated(tickers, tactical, financial, currency, priority_queue=_priority_queue(tickers))
    snapshot = tmp_path / "runtime" / "screen_snapshot.csv"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("ticker,exchange,date\n" + "\n".join(f"{t},HSX,{SESSION}" for t in tickers) + "\n", encoding="utf-8")
    result = ccpp.materialize_and_write_current_product_projections(
        root=tmp_path, session=SESSION, operation_dir=tmp_path / "op", registry_inputs=_workspace_inputs(tickers),
        requested_at="t", runtime_root_override=snapshot.parent, integrated_investment_decision_product=integrated,
    )
    assert result["status"] == "MATERIALIZED", result
    op = tmp_path / "op"
    workspace = json.loads((op / ccpp.WORKSPACE_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    screener = json.loads((op / ccpp.SCREENER_MASTER_JSON_FILENAME).read_text(encoding="utf-8"))
    home = json.loads((op / ccpp.HOME_SUMMARY_JSON_FILENAME).read_text(encoding="utf-8"))
    index, shards = read_model.build_public_read_model(workspace)
    brief = brief_module.build_artifact(session=SESSION, requested_at="t", integrated_decision_current=integrated,
                                        next_session_brief={"current_session": SESSION})
    center = action_center.build_artifact(session=SESSION, requested_at="t", integrated_decision_artifact=integrated)
    return {"tickers": tickers, "integrated": integrated, "workspace": workspace, "screener": screener, "home": home,
            "index": index, "shards": shards, "brief": brief, "action_center": center}


def test_full_universe_tuple_parity_across_every_surface(converged_surfaces):
    s = converged_surfaces
    tickers = s["tickers"]
    producer = {t: _tuple({"ticker": t, **r}) for t, r in s["integrated"]["records"].items()}
    assert set(producer) == set(tickers) and len(producer) == len(tickers)
    postures = Counter(v[1] for v in producer.values())
    currencies = Counter(iidp.evidence_currency_class(v[2]) for v in producer.values())
    assert len(postures) >= 6 and set(currencies) == {"CURRENT_SESSION", "LAST_TRADE_AS_OF", "NO_CURRENT_EVIDENCE"}

    surfaces = {
        "workspace_card": [{"ticker": t, **c} for t, c in s["workspace"]["cards"].items()],
        "published_workspace_index": list(s["index"]["cards"].values()),
        "published_workspace_detail_shard": [c for shard in s["shards"].values() for c in shard["tickers"].values()],
        "screener_decision": [{"ticker": t, **c["decision"]} for t, c in s["screener"]["cards"].items()],
        "ai_brief_index": s["brief"]["decision_surface_index"]["rows"],
        "action_center_index": s["action_center"]["decision_surface_index"]["rows"],
    }
    for name, rows in surfaces.items():
        seen = Counter(row["ticker"] for row in rows)
        assert set(seen) == set(tickers), name
        assert all(count == 1 for count in seen.values()), name
        for row in rows:
            assert _tuple(row) == producer[row["ticker"]], (name, row["ticker"])
    assert s["brief"]["decision_surface_index"]["denominator"] == len(tickers)
    assert s["action_center"]["decision_surface_index"]["denominator"] == len(tickers)
    for index in (s["brief"]["decision_surface_index"], s["action_center"]["decision_surface_index"]):
        assert index["source_integrated_investment_decision_product_identity"] == s["integrated"]["artifact_identity"]
        assert index["role"] == "READ_MODEL_NOT_AUTHORITY"


def test_primary_summaries_are_posture_based_and_stance_is_secondary_only(converged_surfaces):
    s = converged_surfaces
    posture_counts = Counter(r["research_action_posture"] for r in s["integrated"]["records"].values())
    assert s["workspace"]["coverage"]["research_action_posture_distribution"] == dict(sorted(posture_counts.items()))
    assert s["screener"]["coverage"]["research_action_posture_distribution"] == dict(sorted(posture_counts.items()))
    home = s["home"]
    assert home["primary_decision_field"] == "research_action_posture"
    assert {k: v for k, v in home["research_action_posture"]["counts"].items() if v} == dict(posture_counts)
    assert sum(home["evidence_currency"]["counts"].values()) == len(s["tickers"])
    assert home["evidence_currency"]["counts"] == {
        **{k: 0 for k in home_module.EVIDENCE_CURRENCY_ORDER},
        **s["integrated"]["coverage"]["evidence_currency_distribution"],
    }
    assert home["research_stance"]["role"] == "SECONDARY_RESEARCH_SCREEN_DIAGNOSTIC"
    authority = s["workspace"]["decision_authority"]
    assert authority["primary_action_decision_field"] == "research_action_posture"
    assert authority["primary_action_decision_source"] == s["integrated"]["artifact_identity"]
    assert authority["research_stance_role"].startswith("SECONDARY_RESEARCH_SCREEN")
    assert s["index"]["decision_authority"] == authority
    # research_stance remains available as secondary context and may legitimately disagree.
    assert all(card["research_stance"] for card in s["workspace"]["cards"].values())
    assert all(card["research"]["stance"] for card in s["screener"]["cards"].values())


def test_public_surfaces_never_claim_not_held_and_hold_is_conditional(converged_surfaces):
    s = converged_surfaces
    for card in list(s["workspace"]["cards"].values()) + list(s["index"]["cards"].values()):
        assert card["position_context"]["position_state"] == iidp.POSITION_UNKNOWN_NOT_SUPPLIED
        conditional = card["research_action_posture"] in iidp.POSITION_CONDITIONAL_POSTURES
        assert card["action_presentation"]["position_conditional"] is conditional
        assert card["action_presentation"]["condition"] == ("IF_CURRENTLY_HELD" if conditional else None)
    holds = [c for c in s["workspace"]["cards"].values() if c["research_action_posture"] == iidp.POSTURE_HOLD]
    assert holds, "fixture must exercise HOLD"
    for row in s["action_center"]["decision_surface_index"]["rows"]:
        assert row["position_context"] == iidp.POSITION_UNKNOWN_NOT_SUPPLIED
        assert set(row) == {"ticker", "research_action_posture", "evidence_currency", "opportunity_priority_tier", "position_context"}
    assert s["action_center"]["decision_surface_index"]["position_context_source"] == "NOT_SUPPLIED"


def test_priority_is_a_separate_inspection_field_on_every_surface(converged_surfaces):
    s = converged_surfaces
    for ticker, record in s["integrated"]["records"].items():
        tier = record["opportunity_priority"]["research_priority_tier"]
        assert s["workspace"]["cards"][ticker]["opportunity_priority"]["research_priority_tier"] == tier
        assert s["index"]["cards"][ticker]["opportunity_priority"]["research_priority_tier"] == tier
        assert s["screener"]["cards"][ticker]["decision"]["opportunity_priority_tier"] == tier
        assert tier not in (s["workspace"]["cards"][ticker]["research_action_posture"],)
    assert any(r["opportunity_priority"]["status"] == "UNAVAILABLE" for r in s["integrated"]["records"].values())


def test_no_new_score_probability_target_sizing_or_pit_authority_introduced(converged_surfaces):
    s = converged_surfaces
    forbidden = ("score", "probability", "target_price", "position_size", "sizing", "raw_as_traded", "pit_authority")
    for payload in (s["brief"]["decision_surface_index"], s["action_center"]["decision_surface_index"]):
        text = json.dumps(payload).lower()
        assert not any(term in text for term in forbidden)
    assert s["integrated"]["authority_boundary"]["is_actionable"] is False
    assert s["workspace"]["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
