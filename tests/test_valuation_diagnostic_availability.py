import integrated_investment_decision_product as product
import copy
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def valuation():
    return {"earnings_state": "PE_NOT_MEANINGFUL", "methods": {
        "P/E_TTM": {"status": "PE_NOT_MEANINGFUL", "value": None, "blocker_reason_codes": ["NEGATIVE_TTM_EARNINGS"]},
        "P/B": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["PRICE_SESSION_MISSING"]},
        "market_cap": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["PRICE_SESSION_MISSING"]},
    }}


def test_negative_earnings_diagnosis_is_partial_not_a_usable_multiple():
    summary, supports, counters, uncertainties = product.evaluate_valuation_context(valuation(), None)
    assert summary["status"] == "PARTIAL"
    assert summary["pe_multiple"] is None
    assert summary["earnings_state"] == "PE_NOT_MEANINGFUL"
    assert "PRICE_SESSION_MISSING" in summary["unavailable_reason_codes"]
    assert "NEGATIVE_TTM_EARNINGS" in summary["unavailable_reason_codes"]
    assert "PE_NOT_MEANINGFUL_NEGATIVE_EARNINGS" in uncertainties
    assert not supports and not counters


def test_other_usable_method_remains_available_with_its_own_basis():
    record = valuation()
    record["methods"]["P/B"] = {"status": "RESEARCH_USABLE", "value": 1.2, "period_basis": "2026-Q2"}
    summary, _, _, _ = product.evaluate_valuation_context(record, None)
    assert summary["status"] == "AVAILABLE"
    assert summary["pe_multiple"] is None
    assert summary["pb_multiple"] == 1.2
    assert summary["pb_basis"]["method"] == "P/B"


def test_size_context_does_not_upgrade_a_diagnosis_to_a_valuation_multiple():
    record = valuation()
    record["methods"]["market_cap"] = {"status": "RESEARCH_USABLE", "value": 1000000}
    summary, _, _, _ = product.evaluate_valuation_context(record, None)
    assert summary["status"] == "PARTIAL"
    assert summary["size_context"]["status"] == "AVAILABLE"


def test_summary_axis_and_delivery_match_without_changing_security_posture():
    kwargs = dict(ticker="TEST", as_of_session="2026-09-30", tactical_record=None,
                  financial_record=None, relative_volume_record=None, market_sector_record=None)
    without = product.build_ticker_integrated_decision(**kwargs, valuation_record=None)
    with_diagnosis = product.build_ticker_integrated_decision(**kwargs, valuation_record=valuation())
    assert with_diagnosis["valuation_context_summary"]["status"] == "PARTIAL"
    assert with_diagnosis["evidence_axes"]["VALUATION"]["fitness"] == "PARTIAL"
    assert with_diagnosis["current_research_decision_input"]["dimensions"]["VALUATION"]["state"] == "PARTIAL"
    assert with_diagnosis["research_action_posture"] == without["research_action_posture"]
    view = project_integrated_decision_for_ai_delivery(with_diagnosis)
    assert view["valuation_context_summary"]["status"] == "PARTIAL"
    assert view["is_actionable"] is False


def test_absent_diagnostic_and_all_blocked_methods_remain_unavailable():
    record = valuation()
    record.pop("earnings_state")
    record["methods"].pop("P/E_TTM")
    summary, _, _, _ = product.evaluate_valuation_context(record, None)
    assert summary["status"] == "UNAVAILABLE"


def test_financial_history_and_valuation_peer_context_keep_separate_semantics():
    financial = {"history_context": {
        "current_ratio": {"status": "AVAILABLE", "percentile": 1.0},
        "equity_to_assets": {"status": "AVAILABLE", "percentile": 1.0},
        "gross_margin": {"status": "AVAILABLE", "percentile": 0.0},
    }}
    original = copy.deepcopy(financial)
    value = valuation()
    value["relative_research_state"] = "ATTRACTIVE_RELATIVE_RESEARCH"
    summary, supports, counters, _ = product.evaluate_valuation_context(value, financial)
    assert summary["peer_relative_state"] == "CHEAP_VS_PEERS"
    assert summary["own_history_state"] == "UNAVAILABLE"
    assert summary["own_history_reason_codes"] == ["COMPARABLE_VALUATION_HISTORY_NOT_RETAINED"]
    assert not any("OWN_HISTORICAL_RANGE" in code for code in supports + counters)
    assert financial == original


def test_metric_name_and_percentile_alone_do_not_qualify_valuation_history():
    # Even an asserted P/E key has no comparable price/period/method lineage
    # in the Financial V2 history contract. A numeric percentile is not proof.
    financial = {"history_context": {"P/E": {"status": "AVAILABLE", "percentile": 0.1}}}
    summary, supports, counters, _ = product.evaluate_valuation_context(valuation(), financial)
    assert summary["own_history_state"] == "UNAVAILABLE"
    assert not any("OWN_HISTORICAL_RANGE" in code for code in supports + counters)
