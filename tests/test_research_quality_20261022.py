"""Portable close-only replay of eleven actual October 22 retained records.

The fixture records source paths, canonical source-row hashes and exact extracted
close observations. No network, runtime DB, completed session or T0 is written.
"""
import copy
import json
from pathlib import Path

import pytest
import technical_structure_context as technical
import ai_research_session_delivery as delivery
from stocklookup_core.tactical.market_structure_breakout_product_projection import _project_ticker
from stocklookup_core.decision import integrated_investment_decision_product as owner

FIXTURE = Path(__file__).parent / "fixtures/research_quality_20261022.json"


def policy(tactical, inputs):
    phase, supports, counters = owner.evaluate_tactical_phase(tactical)
    return owner.decide_research_action_posture(
        tactical_rec=tactical, tactical_phase=phase, tac_supports=supports,
        tac_counters=counters, **inputs)


@pytest.mark.parametrize("ticker", "HPG SSI PAN EVF POW PNJ NVL FPT PVD VNM QNS".split())
def test_actual_close_series_through_structure_policy_and_delivery(ticker):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = fixture["records"][ticker]
    snapshot = copy.deepcopy(row)
    session = fixture["session"]
    old = row["old_technical"]
    new = technical._classify_ticker(ticker, descriptive_record=row["descriptive"],
                                    pf_record=row["snapshot"], target_session=session,
                                    recovery_identity=old["technical_history_lineage"]["recovery_artifact_identity"])
    previous = _project_ticker(ticker, old, session)
    current = _project_ticker(ticker, new, session)
    before = policy(previous, row["policy"])
    after = policy(current, row["policy"])
    retained = row["retained_decision"]
    assert (before[0], before[3]) == (retained["research_action_posture"], retained["posture_condition_class"])
    if ticker == "EVF":
        assert old["swing_structure"]["swing_high_sequence"] == "LH"
        assert new["swing_structure"]["swing_high_sequence"] == "EH"
        assert current["market_structure_state"] == "RANGE"
        assert current["bos_state"] == "BULLISH_BOS_DETECTED_BY_RULE"
        assert current["invalidation_level"] == 11.45
        assert current["invalidation_close_comparison_operator"] == "<"
        assert before[0] == after[0] == "INITIATE_ON_BREAKOUT"
        assert "fundamental direction unconfirmed" in after[1]
        assert "NOT_APPLICABLE_ENTITY" in after[1]
    elif ticker == "VNM":
        assert old["swing_structure"]["market_structure_state"] == "DOWNTREND"
        assert current["market_structure_state"] == "RANGE"
        assert current["trigger_level"] == 58.4
        assert current["trigger_state"] == "APPROACHING"
        assert current["invalidation_level"] == 57.2
        assert after[0] == "WAIT_FOR_CONFIRMATION"
        assert row["policy"]["fundamental_state"] == "DETERIORATING"
        assert after[3] == "FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY"
    else:
        assert old == new  # all measurements for the other nine are unchanged
        assert (before[0], before[3]) == (after[0], after[3])
    if ticker == "NVL":
        assert after[0] == "INITIATE_ON_BREAKOUT"  # standing fresh-trigger precedence
        assert "recovery attempt against bearish swing structure" in after[1]
        assert "volume magnitude only, not bullish confirmation" in after[1]
        assert current["invalidation_thesis_scope"] == "BEARISH_STRUCTURE"
        assert current["trigger_level"] == current["invalidation_level"] == 10.55
        assert current["trigger_close_comparison_operator"] == current["invalidation_close_comparison_operator"] == ">"

    # The real structural producer owns each boundary; delivery preserves scope,
    # horizon and basis even when confirmation and bearish invalidation coincide.
    built = owner.build_ticker_integrated_decision(
        ticker=ticker, as_of_session=session, tactical_record=current, financial_record=None,
        valuation_record=None, relative_volume_record=None, market_sector_record=None,
        structural_condition_source_identity="diagnostic:oct22-projection",
        producer_artifact_identities={"technical_structure": "diagnostic:oct22-projection"},
        technical_coverage_disposition_record={"disposition": "SAME_SESSION_TECHNICAL_COVERED",
            "has_exact_session_bar": True, "is_current_session": True, "feature_as_of_session": session})
    projected = delivery.project_integrated_decision_for_ai_delivery(built, source_session=session)
    card = delivery._decision_card(ticker, built, None, source_session=session)
    for boundary in ("trigger", "invalidation"):
        for field in ("horizon", "price_basis", "condition", "warning"):
            assert projected[boundary][field] == built[boundary][field]
    assert card["invalidation"] == projected["invalidation"]
    assert projected["invalidation"]["thesis_scope"] == current["invalidation_thesis_scope"]
    assert built["authority_boundary"]["is_actionable"] is False
    if ticker == "NVL":
        from current_evidence_bound_scenario import _bound_record
        bound = _bound_record(built, "diagnostic:oct22-integrated", session, None)
        assert bound["bull_case"]["case_status"] == "CONDITIONAL"
        assert bound["invalidation"] == built["invalidation"]
        assert bound["invalidation_qualified"] is True
        assert bound["bear_case"]["case_status"] == "INSUFFICIENT_EVIDENCE"
        assert bound["bear_case"]["invalidation"] is None
        assert "UPWARD_INVALIDATION_RESOLVES_BEARISH_STRUCTURE_NOT_LONG_SETUP" in bound["limitations"]
    assert row == snapshot


@pytest.mark.parametrize("availability", ["ABSENT", "STALE_ONLY", "CURRENT_NON_DIRECTIONAL", "NOT_APPLICABLE_ENTITY"])
def test_missing_fundamentals_never_become_positive_confirmation(availability):
    from test_integrated_investment_decision_product import _sample_tactical_record
    inputs = dict(ticker="SYN", fundamental_state="INSUFFICIENT", fund_supports=[], fund_counters=[],
                  val_supports=[], val_counters=[], part_supports=[], part_counters=[],
                  fundamental_evidence_availability=availability)
    posture, why, _, _ = policy(_sample_tactical_record(), inputs)
    assert posture == "INITIATE_ON_BREAKOUT"  # lack of evidence is neither support nor veto
    assert availability in why and "missing direction is not fundamental support" in why
    assert "non-conflicting fundamentals" not in why and "actionable initiation" not in why


@pytest.mark.parametrize("ticker", ["HPG", "SSI", "PVD"])
def test_actual_historical_financial_momentum_keeps_period_in_markdown(ticker):
    from stocklookup_core.decision.current_research_decision_packet_product import ticker_markdown
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    financial = fixture["historical_financial_momentum"][ticker]
    text = "\n".join(ticker_markdown({"ticker": ticker, "financial_momentum_context": {"payload": financial}}))
    assert "financial_period=2024" in text
    assert financial["financial_momentum_state"] in text
    assert "not current-session fundamental confirmation" in text
