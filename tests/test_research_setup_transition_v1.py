"""Opt-in qualified-session setup transition. Synthetic only; no providers or private data."""
from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

import next_session_decision_brief as brief_mod
import personal_investment_decision_action_center as ac
import stocklookup_core.decision.integrated_investment_decision_product as iid

SESSION = "2026-08-28"
PREVIOUS = "2026-08-27"
HELPERS = runpy.run_path(str(Path(__file__).with_name("test_integrated_investment_decision_product.py")))
WATCHLIST_HELPERS = runpy.run_path(str(Path(__file__).with_name("test_watchlist_tactical_entry_classifier.py")))
WATCHLIST_HELPERS["_build"].__globals__["SESSION"] = SESSION
WATCHLIST = WATCHLIST_HELPERS["_build"]()[-1]["records"]
CONDITIONAL = runpy.run_path(str(Path(__file__).with_name("test_action_center_conditional_opportunity.py")))

BASIS = {
    "price_basis_verified": True,
    "research_label": "SYNTHETIC_COMPATIBLE_BASIS",
    "price_unit": "SYNTHETIC_PRICE_UNIT",
    "historical_pit_eligible": False,
}


def _tactical(session, **changes):
    tactical = HELPERS["_sample_tactical_record"](
        breakout_state_v3="NO_VALID_PIVOT", trigger_state="NOT_TRIGGERED", bos_state="NO_BOS",
    )
    tactical.update(
        base_status="NONE", range_state="NONE", as_of_session=session,
        trigger_close_comparison_operator=">", invalidation_close_comparison_operator="<",
        price_basis_qualification=copy.deepcopy(BASIS),
    )
    tactical.update(changes)
    return tactical


def _market(session, ticker, *, bearish=False, group="BANKS", leadership="LEADING"):
    return {
        "session": session, "artifact_identity": "synthetic:market:" + session,
        "market": {
            "session": session, "official_universe_count": 100, "exact_session_observed_count": 100,
            "missing_current_session_count": 0, "current_breadth_state": "BEARISH" if bearish else "NEUTRAL",
        },
        "ticker_contexts": {ticker: {"sector_leadership_context": {
            "status": "AVAILABLE", "leadership_state": leadership, "group_key": group,
        }}},
    }


def _record(session, ticker, watch_key, changes, *, financial="current", market=None, priority=None):
    if financial is None:
        financial_record = None
    else:
        period = "2024-Q1" if financial == "stale" else "2026-Q2"
        financial_record = HELPERS["_sample_financial_record"](as_of_period=period)
    queue_record = priority or {
        "research_priority_tier": "RESEARCH_LATER", "entry_relevant": False,
        "entry_action": WATCHLIST[watch_key]["entry_action"], "priority_reasons": ["SYNTHETIC_CONTEXT"],
        "lane_specific_priority": {},
    }
    return iid.build_ticker_integrated_decision(
        ticker=ticker, as_of_session=session, tactical_record=_tactical(session, **changes),
        financial_record=financial_record, valuation_record=None, relative_volume_record=None,
        market_sector_record=market, priority_queue_record=queue_record,
        legacy_opportunity_record=WATCHLIST[watch_key],
        structural_condition_source_identity="synthetic:structure",
        technical_coverage_disposition_record=HELPERS["_current_disposition"](session),
    )


def _artifact(session, records):
    artifact = {
        "contract_version": iid.CONTRACT_VERSION, "session": session,
        "research_action_policy_version": iid.RESEARCH_ACTION_POLICY_VERSION, "records": records,
    }
    artifact.update(iid.content_identity(artifact))
    return artifact


def _row(previous_record, current_record, previous_artifact, current_artifact):
    return {
        "transition": ac._expected_posture_label(previous_record, current_record, previous_artifact, current_artifact),
        "previous_posture": None if previous_record is None else previous_record.get("research_action_posture"),
        "current_posture": current_record.get("research_action_posture"),
        "previous_decision_identity": None if previous_record is None else previous_record.get("decision_identity"),
        "current_decision_identity": current_record.get("decision_identity"),
    }


def _seal(current, previous, rows, *, gained=(), lost=(), retained=(), direction="DOWN"):
    posture = {
        "availability": "UNAVAILABLE" if previous is None else "AVAILABLE",
        "reason_codes": ["NO_PREVIOUS_QUALIFIED_SESSION"] if previous is None else [],
        "records": rows,
        "source_lineage": {"current_integrated_decision_identity": current["artifact_identity"]},
    }
    if previous is not None:
        posture["source_lineage"]["previous_integrated_decision_identity"] = previous["artifact_identity"]
    body = {
        "contract_version": brief_mod.CONTRACT_VERSION,
        "current_session": current["session"],
        "previous_qualified_session": None if previous is None else previous["session"],
        "posture_transition": posture,
        "market_transition": {"availability": "AVAILABLE", "transition": {
            "advance_ratio_direction": direction, "advance_ratio_delta": 0.25,
        }},
        "sector_transition": {"sectors": {"BANKS": {"transition": direction}, "OTHER": {"transition": "FLAT"}}},
        "tactical_transition": {
            "availability": "UNAVAILABLE" if previous is None else "AVAILABLE",
            "reason_codes": ["NO_PREVIOUS_QUALIFIED_SESSION"] if previous is None else [],
            "gained_confirmation": list(gained), "retained_confirmation": list(retained), "lost_confirmation": list(lost),
        },
        "authority_boundary": {"is_actionable": False, "derived_evidence_not_new_factual_authority": True},
    }
    body.update(brief_mod.content_identity(body))
    return body


def _center(current, previous, brief, tickers):
    return ac.build_artifact(
        session=current["session"], requested_at="synthetic", integrated_decision_artifact=current,
        coverage_disposition_artifact={"session": current["session"], "records": {
            ticker: {"disposition": "SAME_SESSION_TECHNICAL_COVERED"} for ticker in current["records"]
        }},
        owner_focus={"owner_focus_tickers": (), "broader_watchlist": tuple(tickers)},
        include_conditional_research=True, next_session_artifact=brief,
        previous_integrated_decision_artifact=previous,
    )


def _cases():
    specs = {
        "AAA_SAME": ("BAS", {"market_structure_state": "SIDEWAYS", "base_status": "IN_BASE", "range_state": "RANGE_STABLE"}, "current", False),
        "CCC_BASE": ("BAS", {"market_structure_state": "SIDEWAYS", "base_status": "IN_BASE", "range_state": "RANGE_STABLE"}, "current", False),
        "DDD_PEND": ("BRK", {"breakout_state_v3": "TESTING_PIVOT", "trigger_state": "APPROACHING"}, "current", False),
        "EEE_CONF": ("BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "current", False),
        "FFF_WEAK": ("BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "current", False),
        "GGG_PRIORITY": ("UPT", {}, "current", False),
        "HHH_ABSENT": ("REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, None, False),
        "III_STALE": ("REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, "stale", False),
        "KKK_THIN": ("THN", {"eligible": False, "market_structure_state": "INSUFFICIENT_HISTORY"}, "current", False),
    }
    current_changes = {
        "CCC_BASE": ("BRK", {"breakout_state_v3": "TESTING_PIVOT", "trigger_state": "APPROACHING"}, "current", False),
        "DDD_PEND": ("BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "current", False),
        "EEE_CONF": ("DST", {"breakout_state_v3": "FAILED_BREAKOUT"}, "current", False),
        "FFF_WEAK": ("BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "current", True),
    }
    previous_records, current_records = {}, {}
    for ticker, spec in specs.items():
        watch, changes, financial, bearish = spec
        previous_records[ticker] = _record(
            PREVIOUS, ticker, watch, changes, financial=financial,
            market=_market(PREVIOUS, ticker, bearish=False),
        )
        watch_c, changes_c, financial_c, bearish_c = current_changes.get(ticker, spec)
        priority = None
        if ticker == "GGG_PRIORITY":
            priority = {
                "research_priority_tier": "PRIORITY_NOW", "entry_relevant": True, "entry_action": "WAIT",
                "priority_reasons": ["TREND_MOMENTUM=PRIORITY_NOW"], "lane_specific_priority": {"TREND_MOMENTUM": "PRIORITY_NOW"},
            }
        current_records[ticker] = _record(
            SESSION, ticker, watch_c, changes_c, financial=financial_c, priority=priority,
            market=_market(SESSION, ticker, bearish=bearish_c, leadership="LAGGING" if bearish_c else "LEADING"),
        )
    current_records["BBB_NEW"] = _record(
        SESSION, "BBB_NEW", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL", "choch_state": "BULLISH_CHOCH_DETECTED_BY_RULE"},
        market=_market(SESSION, "BBB_NEW"),
    )
    epoch = copy.deepcopy(previous_records["AAA_SAME"])
    epoch["ticker"] = "JJJ_EPOCH"
    epoch["as_of_session"] = PREVIOUS
    epoch["research_action_policy_version"] = "v1"
    epoch["decision_identity"] = iid.decision_identity(epoch)
    previous_records["JJJ_EPOCH"] = epoch
    current_epoch = copy.deepcopy(current_records["AAA_SAME"])
    current_epoch["ticker"] = "JJJ_EPOCH"
    current_epoch["decision_identity"] = iid.decision_identity(current_epoch)
    current_records["JJJ_EPOCH"] = current_epoch
    return _artifact(PREVIOUS, previous_records), _artifact(SESSION, current_records)


def _prepared():
    previous, current = _cases()
    rows = {}
    for ticker, current_record in current["records"].items():
        rows[ticker] = _row(previous["records"].get(ticker), current_record, previous, current)
    gained = [ticker for ticker, row in rows.items() if row["transition"] == "WAIT_TO_INITIATE"]
    lost = [ticker for ticker, row in rows.items() if row["transition"] == "BREAKOUT_FAILED"]
    brief = _seal(current, previous, rows, gained=gained, lost=lost)
    return previous, current, brief, _center(current, previous, brief, tuple(sorted(current["records"])))


def _transition(artifact, ticker):
    return next(row["evidence"]["conditional_research"]["setup_transition"]
                for row in artifact["watchlist"]["entries"] if row["ticker"] == ticker)


def test_default_conditional_identity_is_unchanged_without_a_brief():
    integrated, coverage, _queued = CONDITIONAL["scenario_inputs"]()
    disabled = CONDITIONAL["build"](integrated, coverage, enabled=False)
    enabled = CONDITIONAL["build"](integrated, coverage)
    assert disabled["artifact_identity"] == (
        "personal_investment_decision_action_center/v1:ad9e9f15b1e26f1ddff4d2783c74fdd55ce7bf67184d06c06bfc6e7e8f3ca97d"
    )
    assert "setup_transition" not in enabled["conditional_research_presentation"]
    assert "Research-state evolution" not in ac.markdown(enabled)


def test_no_previous_qualified_session_invents_no_label():
    _previous, current = _cases()
    brief = _seal(current, None, {})
    artifact = _center(current, None, brief, tuple(current["records"]))
    shown = _transition(artifact, "BBB_NEW")
    assert shown["status"] == "UNAVAILABLE"
    assert shown["governed_transition_label"] is None
    assert shown["research_limitations"] == ["NO_PREVIOUS_QUALIFIED_SESSION_NO_TRANSITION_INVENTED"]
    assert "NO_PREVIOUS_QUALIFIED_SESSION_NO_TRANSITION_INVENTED" in ac.markdown(artifact)


def test_qualified_pair_explains_each_required_setup_change_without_a_new_cause():
    previous, current, _brief, artifact = _prepared()
    same = _transition(artifact, "AAA_SAME")
    assert same["governed_transition_label"] == "POSTURE_UNCHANGED"
    assert same["setup_context"]["breakout_state_v3"]["status"] == "UNCHANGED"
    assert same["current_canonical_posture"] == previous["records"]["AAA_SAME"]["research_action_posture"]

    fresh = _transition(artifact, "BBB_NEW")
    assert fresh["status"] == "AVAILABLE"
    assert fresh["governed_transition_label"] == "NEWLY_AVAILABLE"
    assert fresh["previous_research_action_posture"] is None
    assert fresh["current_canonical_posture"] == "EARLY_WATCH"
    assert "EARLY_WATCH_IS_RESEARCH_POSTURE_NOT_CAPITAL_AUTHORIZATION" in fresh["research_limitations"]
    assert fresh["setup_context"]["tactical_phase"]["status"] == "PREVIOUS_RECORD_ABSENT"

    base = _transition(artifact, "CCC_BASE")
    assert base["governed_transition_label"] == "POSTURE_CHANGED_OTHER"
    assert base["previous_research_action_posture"] == "EARLY_WATCH"
    assert base["current_canonical_posture"] == "WAIT_FOR_CONFIRMATION"
    assert base["setup_context"]["breakout_state_v3"]["status"] == "CHANGED"
    assert base["setup_context"]["breakout_state_v3"]["previous"] != base["setup_context"]["breakout_state_v3"]["current"]

    confirmed = _transition(artifact, "DDD_PEND")
    assert confirmed["governed_transition_label"] == "WAIT_TO_INITIATE"
    assert confirmed["tactical_confirmation"]["status"] == "GAINED_CONFIRMATION"
    assert confirmed["previous_research_action_posture"] == "WAIT_FOR_CONFIRMATION"
    assert confirmed["current_canonical_posture"] == "INITIATE_ON_BREAKOUT"

    failed = _transition(artifact, "EEE_CONF")
    assert failed["governed_transition_label"] == "BREAKOUT_FAILED"
    assert failed["tactical_confirmation"]["status"] == "LOST_CONFIRMATION"
    assert failed["current_canonical_posture"] == "WAIT_FOR_CONFIRMATION"

    weak = _transition(artifact, "FFF_WEAK")
    assert weak["previous_research_action_posture"] == "INITIATE_ON_BREAKOUT"
    assert weak["current_canonical_posture"] == "WAIT_FOR_CONFIRMATION"
    assert weak["governed_transition_label"] == "BREAKOUT_FAILED"
    assert weak["technical_market_sector_evidence"]["market_regime"]["status"] == "CHANGED"
    assert weak["technical_market_sector_evidence"]["governed_market_direction"] == "DOWN"
    assert weak["technical_market_sector_evidence"]["governed_sector_direction"] == "DOWN"
    assert weak["technical_market_sector_evidence"]["market_weakness_is_context_not_a_new_veto"] is True
    assert "advance_ratio_delta" not in json.dumps(weak)

    priority = _transition(artifact, "GGG_PRIORITY")
    assert priority["current_canonical_posture"] == "WAIT_FOR_CONFIRMATION"
    assert priority["priority_posture_reconciliation"]["research_priority_tier"] == "PRIORITY_NOW"
    assert priority["priority_posture_reconciliation"]["reason"] == "PRIORITY_REVIEW_REMAINS_DISTINCT_FROM_ACTION_READINESS"
    assert "PRIORITY_NOW_IS_RESEARCH_ATTENTION_NOT_BUY_NOW" in priority["research_limitations"]

    absent = _transition(artifact, "HHH_ABSENT")
    assert absent["current_canonical_posture"] == "EARLY_WATCH"
    assert current["records"]["HHH_ABSENT"]["fundamental_state"] == iid.FUNDAMENTAL_INSUFFICIENT
    assert "FUNDAMENTAL_GAP_DOES_NOT_REMOVE_TECHNICAL_STATE" in absent["research_limitations"]
    assert absent["setup_context"]["tactical_phase"]["current"] not in (None, "INSUFFICIENT")

    stale = _transition(artifact, "III_STALE")
    assert stale["setup_context"]["fundamental_state"]["current"] == "INSUFFICIENT"
    assert stale["setup_context"]["fundamental_evidence_availability"]["current"] == "STALE_ONLY"
    assert absent["setup_context"]["fundamental_evidence_availability"]["current"] == "ABSENT"
    assert stale["setup_context"]["tactical_phase"] == {"status": "UNCHANGED", "previous": "EARLY_REVERSAL", "current": "EARLY_REVERSAL"}
    assert "FUNDAMENTAL_GAP_DOES_NOT_REMOVE_TECHNICAL_STATE" in stale["research_limitations"]

    epoch = _transition(artifact, "JJJ_EPOCH")
    assert epoch["status"] == "NOT_COMPARABLE"
    assert epoch["governed_transition_label"] == "NOT_COMPARABLE_POLICY_CHANGE"
    assert epoch["tactical_confirmation"]["status"] == "NOT_INTERPRETED"
    assert "POLICY_EPOCH_CHANGE_BLOCKS_CROSS_SESSION_INTERPRETATION" in epoch["research_limitations"]

    thin = _transition(artifact, "KKK_THIN")
    detail = next(row["evidence"]["conditional_research"] for row in artifact["watchlist"]["entries"] if row["ticker"] == "KKK_THIN")
    assert detail["trigger"]["numeric_display_status"] == "WITHHELD_UNQUALIFIED_BOUNDARY"
    assert detail["trigger"]["trigger_level"] is None
    assert "trigger_level" not in thin
    rendered = ac.markdown(artifact)
    thin_block = rendered.split("**KKK_THIN**")[1].split("\n- **")[0]
    assert "40.0" not in thin_block
    assert "WITHHELD_UNQUALIFIED_BOUNDARY" in thin_block
    assert "0.25" not in rendered
    assert "A transition label is not an investment outcome." in rendered
    assert "Market weakness is context, not a new veto." in rendered
    assert "PRIORITY_REVIEW_REMAINS_DISTINCT_FROM_ACTION_READINESS" in rendered
    assert artifact["conditional_research_presentation"]["setup_transition"]["explanation_only"] is True
    assert current["records"]["DDD_PEND"]["research_action_posture"] == "INITIATE_ON_BREAKOUT"
    assert previous["records"]["DDD_PEND"]["research_action_posture"] == "WAIT_FOR_CONFIRMATION"


def test_investor_preview_shows_the_governed_change_and_leaves_the_default_silent():
    previous, current, brief, after = _prepared()
    before = ac.build_artifact(
        session=SESSION, requested_at="synthetic", integrated_decision_artifact=current,
        owner_focus={"owner_focus_tickers": (), "broader_watchlist": ("DDD_PEND", "GGG_PRIORITY")},
        include_conditional_research=True,
    )
    before_text = ac.markdown(before)
    after_text = ac.markdown(after)
    assert "Research-state evolution" not in before_text
    confirm = [line for line in after_text.splitlines() if "DDD_PEND" in line or "WAIT_TO_INITIATE" in line or "GAINED_CONFIRMATION" in line]
    priority = [line for line in after_text.splitlines() if "GGG_PRIORITY" in line or "PRIORITY_NOW_IS_RESEARCH_ATTENTION_NOT_BUY_NOW" in line]
    assert any("WAIT_TO_INITIATE" in line for line in confirm)
    assert any("GAINED_CONFIRMATION" in line for line in confirm)
    assert any("PRIORITY_NOW_IS_RESEARCH_ATTENTION_NOT_BUY_NOW" in line for line in priority)
    assert previous["records"]["DDD_PEND"]["decision_identity"] != current["records"]["DDD_PEND"]["decision_identity"]
    assert brief["authority_boundary"]["is_actionable"] is False


@pytest.mark.parametrize("mutation", ["label", "lineage", "session", "price_basis", "price_label", "membership", "brief_without_research"])
def test_conflicts_fail_closed_without_emitting_a_transition(mutation):
    previous, current, brief, _artifact = _prepared()
    tickers = tuple(sorted(current["records"]))
    if mutation == "label":
        brief["posture_transition"]["records"]["AAA_SAME"]["transition"] = "NEW_BREAKOUT"
        brief.pop("artifact_identity"); brief.pop("artifact_sha256")
        brief.update(brief_mod.content_identity(brief))
    elif mutation == "lineage":
        brief["posture_transition"]["source_lineage"]["current_integrated_decision_identity"] = "other"
        brief.pop("artifact_identity"); brief.pop("artifact_sha256")
        brief.update(brief_mod.content_identity(brief))
    elif mutation == "session":
        brief["previous_qualified_session"] = SESSION
        brief.pop("artifact_identity"); brief.pop("artifact_sha256")
        brief.update(brief_mod.content_identity(brief))
    elif mutation == "price_basis":
        previous["records"]["AAA_SAME"]["trigger"]["price_basis"]["price_unit"] = "OTHER_UNIT"
    elif mutation == "price_label":
        previous["records"]["AAA_SAME"]["trigger"]["price_basis"]["research_label"] = "OTHER_LABEL"
        artifact = _center(current, previous, brief, tickers)
        shown = _transition(artifact, "AAA_SAME")
        assert shown["governed_transition_label"] == "POSTURE_UNCHANGED"
        assert "PRICE_BASIS_LABEL_CHANGED_NUMBERS_STAY_WITHHELD" in shown["research_limitations"]
        assert "40.0" not in json.dumps(shown)
        return
    elif mutation == "membership":
        brief["tactical_transition"]["gained_confirmation"].append("EEE_CONF")
        brief.pop("artifact_identity"); brief.pop("artifact_sha256")
        brief.update(brief_mod.content_identity(brief))
    else:
        with pytest.raises(ac.ActionCenterError, match="SETUP_TRANSITION_REQUIRES_CONDITIONAL_RESEARCH"):
            ac.build_artifact(
                session=SESSION, requested_at="synthetic", integrated_decision_artifact=current,
                include_conditional_research=False, next_session_artifact=brief,
                previous_integrated_decision_artifact=previous,
            )
        return
    with pytest.raises(ac.ActionCenterError):
        _center(current, previous, brief, tickers)
