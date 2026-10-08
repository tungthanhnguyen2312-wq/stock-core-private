"""Comparative research cases over synthetic inputs. No ticker-specific branches, no sizing."""
from __future__ import annotations

import copy
import json

import pytest

import portfolio_opportunity_cost_research as research
import portfolio_research_decision_workbench as workbench

SESSION = "2026-10-08"
DATES = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]


def _lens(**fields):
    return {"source_identity": "integrated_investment_decision_product/v1:abc", "session": SESSION,
            "fitness": "READY_RESEARCH", **fields}


def _candidate(ticker, *, role="CORE", horizon="STRUCTURAL", sector="materials", fundamental="STABLE",
               thesis="INTACT", valuation="IN_LINE_RELATIVE_RESEARCH", methods=("P/B",), phase="TREND_CONTINUATION",
               thesis_ids=(), event_ids=(), **extra):
    row = {
        "ticker": ticker, "session": SESSION, "thesis_id": f"thesis-{ticker.lower()}", "horizon": horizon,
        "portfolio_role": role, "sector": sector, "thesis_ids": list(thesis_ids), "event_ids": list(event_ids),
        "source_artifact_identities": {"integrated_investment_decision_product": "integrated_investment_decision_product/v1:abc"},
        "structural": _lens(fundamental_state=fundamental, thesis_status=thesis) if fundamental else None,
        "valuation": _lens(relative_research_state=valuation,
                           supporting_methods=[{"method": m, "basis": "CURRENT_RESEARCH"} for m in methods]) if valuation else None,
        "tactical": _lens(tactical_phase=phase) if phase else None,
        "invalidation": [f"{ticker}_SOURCE_INVALIDATION_LEVEL_BREACHED"],
    }
    row.update(extra)
    return row


def _state(holdings, *, sector_weights, cash=100.0, nav=1000.0, policy=None, unresolved=(), unweighted=()):
    positions = {}
    for ticker, sector in holdings.items():
        positions[ticker] = {
            "ticker": ticker, "is_active": True, "current_quantity": 100.0, "current_position_status": "CURRENT_CONFIRMED",
            "current_weight": None if ticker in unweighted else 0.2, "sector": sector,
        }
    for ticker in unresolved:
        positions[ticker] = {"ticker": ticker, "is_active": True, "current_quantity": None,
                             "current_position_status": "UNRESOLVED", "current_weight": None, "sector": "materials"}
    return {
        "contract_version": "portfolio_state/v1", "status": "AVAILABLE", "as_of_date": SESSION,
        "positions": positions, "sector_weights": sector_weights, "effective_nav": nav, "nav_basis": "NAV_BROKER_REPORTED",
        "cash_available": cash, "effective_policy": policy or {},
        "source_identities": {"portfolio_snapshot_identity": "portfolio_snapshot/v1:synthetic"},
    }


def _cases(built, kind, ticker=None):
    return [c for c in built["research_cases"] if c["case"] == kind and (ticker is None or c["ticker"] == ticker)]


def _no_capital_decision(built):
    for key in ("capital_decision", "universal_score", "winner", "target_weights", "position_size", "order", "expected_return"):
        assert built[key] is None
    assert built["is_actionable"] is False
    for case in built["research_cases"]:
        assert case["is_instruction"] is False
        for comparison in case.get("comparisons") or []:
            assert comparison["comparability"]["winner"] is None
            assert comparison["comparability"]["superiority"] is None
    text = json.dumps(built)
    for word in ("BUY", "SELL", "ROTATE_TO", "TARGET_WEIGHT"):
        assert word not in text


# ── Six required scenarios ──────────────────────────────────────────────────────

def test_scenario1_strong_core_thesis_weak_tactical_structure_keeps_lenses_independent():
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("AAA", fundamental="IMPROVING", phase="BREAKDOWN")],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}, policy={"max_sector_weight": 0.4}),
    )
    hold = _cases(built, research.HOLD_CORE_REVIEW, "AAA")[0]
    assert hold["structural_case_status"] == "THESIS_INTACT_EVIDENCE"
    assert "FUNDAMENTAL_IMPROVING" in hold["supporting_evidence"]
    assert "TACTICAL_BREAKDOWN_ADVERSE" in hold["counter_evidence"]
    assert hold["tactical_lens_is_independent"] is True
    unit = built["comparison_units"][0]
    assert unit["lenses"]["core_structural"]["fundamental_state"] == "IMPROVING"
    assert unit["lenses"]["tactical"]["confirmation"] == "ADVERSE"
    assert "AAA_SOURCE_INVALIDATION_LEVEL_BREACHED" in hold["decision_changers"]
    _no_capital_decision(built)


def test_scenario2_attractive_candidate_with_high_existing_sector_concentration():
    built = research.build_comparison(
        session=SESSION,
        candidates=[
            _candidate("AAA", thesis_ids=["steel-cycle"]),
            _candidate("BBB", role="STRATEGIC", horizon="STRATEGIC", valuation="ATTRACTIVE_RELATIVE_RESEARCH",
                       thesis_ids=["steel-cycle"]),
        ],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.45}, policy={"max_sector_weight": 0.4}),
    )
    alternative = _cases(built, research.ALTERNATIVE_INVESTMENT_REVIEW, "BBB")[0]
    assert "QUALIFIED_ATTRACTIVE_RELATIVE_VALUATION" in alternative["supporting_evidence"]
    assert "OWNER_SECTOR_AT_OR_ABOVE_LIMIT" in alternative["counter_evidence"]
    assert "LIKELY_REDUNDANT_WITH_HELD:AAA" in alternative["counter_evidence"]
    assert alternative["concentration_overlap"]["owner_sector_weight"] == 0.45
    assert alternative["concentration_overlap"]["status"] == "AT_OR_ABOVE_OWNER_SECTOR_LIMIT"
    # Owner exposure is a weight, the opportunity count is a count: they are not the same thing.
    assert built["opportunity_concentration"]["sector"]["counts"]["materials"] == 2
    assert built["opportunity_concentration"]["sector"]["basis"] == workbench.OPPORTUNITY_COUNT_BASIS
    assert built["owner_exposure"]["basis"] == "OWNER_CURRENT_WEIGHT_OF_NAV"
    # The owner limit narrows the held Core add case; it does not create or remove holdings.
    assert not _cases(built, research.ADD_CORE_REVIEW, "AAA")
    assert {"ticker": "AAA", "case": research.ADD_CORE_REVIEW, "reason": "OWNER_SECTOR_LIMIT_REACHED"} in built["narrowed_by_owner_constraints_or_evidence"]
    _no_capital_decision(built)


def test_scenario3_sound_core_with_qualified_expensive_valuation_is_trim_review_without_thesis_break():
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("AAA", valuation="EXPENSIVE_RELATIVE_RESEARCH", methods=("P/E_TTM", "P/B"))],
        owner_portfolio_state=_state({"AAA": "consumer"}, sector_weights={"consumer": 0.2}),
    )
    trim = _cases(built, research.VALUATION_TRIM_REVIEW, "AAA")[0]
    assert trim["fundamental_thesis_break"] is False
    assert trim["trim_basis"] == "VALUATION_ONLY"
    assert trim["supporting_evidence"] == ["QUALIFIED_EXPENSIVE_RELATIVE_VALUATION:P/B,P/E_TTM"]
    assert "THESIS_INTACT" in trim["counter_evidence"]
    assert _cases(built, research.HOLD_CORE_REVIEW, "AAA")
    assert not _cases(built, research.ADD_CORE_REVIEW, "AAA")
    _no_capital_decision(built)


def test_scenario4_rotation_with_incomparable_earnings_valuation_is_not_a_superiority_claim():
    built = research.build_comparison(
        session=SESSION,
        candidates=[
            _candidate("AAA", methods=("P/E_TTM",)),
            _candidate("BBB", role="STRATEGIC", horizon="STRATEGIC", sector="technology",
                       valuation="ATTRACTIVE_RELATIVE_RESEARCH", methods=("EV/Sales",)),
        ],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}),
    )
    comparison = _cases(built, research.ALTERNATIVE_INVESTMENT_REVIEW, "BBB")[0]["comparisons"][0]["comparability"]
    assert comparison["common_valuation_methods"] == []
    assert comparison["axes"]["strategic"] == research.NOT_COMPARABLE
    assert comparison["status"] == research.PARTIALLY_COMPARABLE
    assert comparison["winner"] is None
    # Fundamental also unknown on the candidate: nothing left to compare on.
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("AAA", methods=("P/E_TTM",)),
                    _candidate("BBB", role="STRATEGIC", horizon="STRATEGIC", fundamental="INSUFFICIENT", valuation=None)],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}),
    )
    insufficient = _cases(built, research.INSUFFICIENT_COMPARABLE_EVIDENCE, "BBB")[0]
    assert insufficient["comparisons"][0]["comparability"]["status"] == research.NOT_COMPARABLE
    assert "VALUATION_EVIDENCE_NOT_SUPPLIED" in insufficient["evidence_gaps"]
    assert not _cases(built, research.ALTERNATIVE_INVESTMENT_REVIEW, "BBB")
    _no_capital_decision(built)


def test_scenario5_early_tactical_reversal_without_confirmation():
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("CCC", role="TACTICAL", horizon="TACTICAL", sector="energy", fundamental="MIXED",
                               thesis="UNKNOWN", phase="EARLY_REVERSAL")],
        owner_portfolio_state=_state({}, sector_weights={}),
    )
    case = _cases(built, research.ALTERNATIVE_INVESTMENT_REVIEW, "CCC")[0]
    assert "TACTICAL_EARLY_REVERSAL_UNCONFIRMED" in case["counter_evidence"]
    assert not any(item.startswith("TACTICAL_") for item in case["supporting_evidence"])
    assert built["comparison_units"][0]["lenses"]["core_structural"]["fundamental_state"] == "MIXED"
    assert "NO_CONFIRMED_HOLDING_TO_COMPARE_AGAINST" in case["evidence_gaps"]
    _no_capital_decision(built)


def test_scenario6_cash_optionality_when_alternatives_are_incomplete_carries_no_return():
    built = research.build_comparison(
        session=SESSION,
        candidates=[
            _candidate("AAA"),
            _candidate("BBB", role="STRATEGIC", horizon="STRATEGIC", sector="technology", valuation=None),
            _candidate("CCC", role="STRATEGIC", horizon="STRATEGIC", sector="energy", fundamental=None, valuation=None),
        ],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}, cash=50.0,
                                     policy={"minimum_cash_reserve_to_nav": 0.05}),
    )
    cash = _cases(built, research.CASH_OPTIONALITY_REVIEW)[0]
    assert cash["expected_return"] is None
    assert cash["return_assumption"] == "NONE_NOT_INVENTED"
    assert cash["cash_fact"]["cash_to_nav"] == 0.05
    assert "ALTERNATIVES_WITH_INCOMPLETE_EVIDENCE:BBB,CCC" in cash["supporting_evidence"]
    assert "CASH_AT_OR_BELOW_OWNER_RESERVE_POLICY" in cash["supporting_evidence"]
    assert "CASH_HAS_NO_RESEARCH_RETURN_EVIDENCE" in cash["counter_evidence"]
    _no_capital_decision(built)


# ── Fail-closed identity and evidence restrictions ──────────────────────────────

@pytest.mark.parametrize("mutate, code", [
    (lambda c: c.update(session="2026-10-07"), "CANDIDATE_SESSION_MISMATCH:AAA"),
    (lambda c: c["valuation"].update(session="2026-10-07"), "VALUATION:AAA_SESSION_MISMATCH"),
    (lambda c: c["tactical"].pop("source_identity"), "TACTICAL:AAA_SOURCE_IDENTITY_MISSING"),
    (lambda c: c["structural"].update(fundamental_state="GREAT"), "STRUCTURAL_STATE_UNKNOWN_VOCABULARY:AAA"),
    (lambda c: c.update(position_size=10), "FORBIDDEN_CANDIDATE_POSITION_SIZE"),
    (lambda c: c.update(expected_return=0.2), "FORBIDDEN_CANDIDATE_EXPECTED_RETURN"),
    (lambda c: c["valuation"].update(target_price=1), "FORBIDDEN_VALUATION_TARGET_PRICE"),
])
def test_session_and_identity_mismatches_fail_closed(mutate, code):
    candidate = _candidate("AAA")
    mutate(candidate)
    with pytest.raises(research.OpportunityCostResearchError) as raised:
        research.build_comparison(session=SESSION, candidates=[candidate])
    assert str(raised.value) == code


def test_cross_source_identity_and_market_session_mismatch_fail_closed():
    other = _candidate("BBB", source_artifact_identities={"integrated_investment_decision_product": "integrated_investment_decision_product/v1:other"})
    with pytest.raises(research.OpportunityCostResearchError, match="CROSS_SOURCE_INTEGRATED_IDENTITY_MISMATCH"):
        research.build_comparison(session=SESSION, candidates=[_candidate("AAA"), other])
    with pytest.raises(research.OpportunityCostResearchError, match="MARKET_CONTEXT_SESSION_MISMATCH"):
        research.build_comparison(session=SESSION, candidates=[_candidate("AAA")],
                                  market_context={"market_state": "RISK_OFF", "source_identity": "macro:x", "session": "2026-10-07"})
    with pytest.raises(research.OpportunityCostResearchError, match="OWNER_PORTFOLIO_STATE_CONTRACT_MISMATCH"):
        research.build_comparison(session=SESSION, candidates=[_candidate("AAA")], owner_portfolio_state={"contract_version": "x"})


def test_missing_or_unqualified_valuation_never_becomes_attractive_value():
    built = research.build_comparison(session=SESSION, candidates=[
        _candidate("AAA", valuation=None),
        _candidate("BBB", valuation="ATTRACTIVE_RELATIVE_RESEARCH", methods=("market_cap",)),
    ])
    for case in built["research_cases"]:
        assert "QUALIFIED_ATTRACTIVE_RELATIVE_VALUATION" not in case["supporting_evidence"]
    lens = built["comparison_units"][1]["lenses"]["strategic"]
    assert lens["relative_research_state"] == "UNQUALIFIED_ATTRACTIVE_RELATIVE_RESEARCH"
    assert lens["valuation_qualified"] is False
    assert "RELATIVE_LABEL_WITHOUT_SUPPORTING_METHOD" in lens["gaps"]


def test_unqualified_expensive_label_does_not_open_trim_review():
    built = research.build_comparison(
        session=SESSION, candidates=[_candidate("AAA", valuation="EXPENSIVE_RELATIVE_RESEARCH", methods=())],
        owner_portfolio_state=_state({"AAA": "consumer"}, sector_weights={"consumer": 0.2}),
    )
    assert not _cases(built, research.VALUATION_TRIM_REVIEW)
    assert {"ticker": "AAA", "case": research.VALUATION_TRIM_REVIEW,
            "reason": "EXPENSIVE_LABEL_WITHOUT_SUPPORTING_RELATIVE_METHOD"} in built["narrowed_by_owner_constraints_or_evidence"]


def test_thesis_break_is_not_relabelled_as_valuation_trim():
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("AAA", thesis="BROKEN", valuation="EXPENSIVE_RELATIVE_RESEARCH")],
        owner_portfolio_state=_state({"AAA": "consumer"}, sector_weights={"consumer": 0.2}),
    )
    assert not _cases(built, research.VALUATION_TRIM_REVIEW)
    assert _cases(built, research.HOLD_CORE_REVIEW)[0]["structural_case_status"] == "THESIS_BREAK_REPORTED"


def test_core_lens_is_independent_of_tactical_inputs():
    state = _state({"AAA": "materials"}, sector_weights={"materials": 0.2})
    strong = research.build_comparison(session=SESSION, candidates=[_candidate("AAA", phase="BREAKOUT_CONFIRMED")], owner_portfolio_state=state)
    weak = research.build_comparison(session=SESSION, candidates=[_candidate("AAA", phase="BREAKDOWN")], owner_portfolio_state=state)
    assert strong["comparison_units"][0]["lenses"]["core_structural"] == weak["comparison_units"][0]["lenses"]["core_structural"]
    assert strong["comparison_units"][0]["lenses"]["strategic"] == weak["comparison_units"][0]["lenses"]["strategic"]
    assert _cases(strong, research.HOLD_CORE_REVIEW)[0]["structural_case_status"] == _cases(weak, research.HOLD_CORE_REVIEW)[0]["structural_case_status"]


def test_overlap_by_thesis_or_event_without_same_sector_is_partial_not_redundant():
    built = research.build_comparison(
        session=SESSION,
        candidates=[_candidate("AAA", event_ids=["rights-issue-1"]),
                    _candidate("BBB", sector="technology", event_ids=["rights-issue-1"], thesis_ids=["x"])],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}),
    )
    redundancy = built["pairwise"][0]["redundancy"]
    assert redundancy["state"] == "PARTIAL_OVERLAP"
    assert redundancy["signals"] == ["SHARED_EVENT"]
    assert redundancy["shared_event_ids"] == ["rights-issue-1"]
    built = research.build_comparison(
        session=SESSION, candidates=[_candidate("AAA"), _candidate("BBB", sector=None)],
        owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}),
    )
    assert built["pairwise"][0]["redundancy"]["state"] == "OVERLAP_UNKNOWN"


def test_correlation_is_comparable_only_when_dates_align():
    returns_a = [0.01, 0.02, -0.01, 0.00, 0.03]
    returns_b = [0.02, 0.01, -0.02, 0.01, 0.02]
    dated = research.build_comparison(session=SESSION, candidates=[
        _candidate("AAA", current_returns=returns_a, current_return_dates=DATES),
        _candidate("BBB", current_returns=returns_b[1:], current_return_dates=DATES[1:]),
    ], owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}))
    corr = dated["pairwise"][0]["redundancy"]["current_correlation"]
    assert corr["comparable"] is True
    assert corr["aligned_points"] == 4
    assert corr["authority"] == "CURRENT_RESEARCH_ONLY_NOT_PIT"
    undated = research.build_comparison(session=SESSION, candidates=[
        _candidate("AAA", current_returns=returns_a), _candidate("BBB", current_returns=returns_b),
    ], owner_portfolio_state=_state({"AAA": "materials"}, sector_weights={"materials": 0.2}))
    corr = undated["pairwise"][0]["redundancy"]["current_correlation"]
    assert corr["comparable"] is False
    assert corr["date_alignment"] == workbench.ALIGNMENT_UNVERIFIED
    assert "DATE_ALIGNED_CORRELATION" in undated["pairwise"][0]["redundancy"]["unknown_dimensions"]


def test_concentration_uncertainty_is_explicit():
    state = _state({"AAA": "materials", "ZZZ": None}, sector_weights={"materials": 0.2}, unweighted=("ZZZ",),
                   policy={"max_sector_weight": 0.4})
    built = research.build_comparison(session=SESSION, candidates=[_candidate("BBB", role="STRATEGIC", horizon="STRATEGIC")],
                                      owner_portfolio_state=state)
    assert built["owner_exposure"]["status"] == "PARTIAL_UNCERTAIN"
    assert "ACTIVE_POSITIONS_WITHOUT_CURRENT_WEIGHT:ZZZ" in built["owner_exposure"]["uncertainty"]
    case = _cases(built, research.ALTERNATIVE_INVESTMENT_REVIEW, "BBB")[0]
    assert case["concentration_overlap"]["status"] == "BELOW_OWNER_SECTOR_LIMIT_LOWER_BOUND_ONLY"
    absent = research.build_comparison(session=SESSION, candidates=[_candidate("BBB")])
    assert absent["owner_exposure"]["status"] == research.OWNER_STATE_NOT_SUPPLIED
    case = absent["research_cases"][0]
    assert case["holding_fact"] == research.OWNER_STATE_NOT_SUPPLIED
    assert case["concentration_overlap"]["status"] == "OWNER_EXPOSURE_UNKNOWN"
    # Without owner facts no hold/add/trim case may assert a holding.
    assert not _cases(absent, research.HOLD_CORE_REVIEW)


def test_unresolved_position_never_gets_a_holding_or_alternative_case():
    built = research.build_comparison(session=SESSION, candidates=[_candidate("AAA")],
                                      owner_portfolio_state=_state({}, sector_weights={}, unresolved=("AAA",)))
    assert built["holding_fact_unresolved_or_excluded"] == [{"ticker": "AAA", "holding_fact": research.POSITION_UNRESOLVED}]
    assert [c["case"] for c in built["research_cases"]] == [research.CASH_OPTIONALITY_REVIEW]


def test_no_universal_score_identity_stable_and_inputs_not_mutated():
    candidates = [_candidate("AAA"), _candidate("BBB", sector="technology")]
    original = copy.deepcopy(candidates)
    state = _state({"AAA": "materials"}, sector_weights={"materials": 0.2})
    first = research.build_comparison(session=SESSION, candidates=candidates, owner_portfolio_state=state)
    second = research.build_comparison(session=SESSION, candidates=list(reversed(candidates)), owner_portfolio_state=state)
    assert first["comparison_identity"] == second["comparison_identity"]
    assert candidates == original
    assert first["persisted"] is False
    text = json.dumps(first).lower()
    assert '"score"' not in text and '"rank"' not in text


def test_module_has_no_daily_or_filesystem_writer():
    source = open(research.__file__, encoding="utf-8").read()
    for token in ("open(", "write_text", "mkdir", "daily_pipeline", "owner_daily", "dashboard"):
        assert token not in source.lower()
