import copy

import pytest

import financial_analysis_product_projection as projection
import current_research_valuation_context as peers
import integrated_investment_decision_product as decision
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def inputs(*, period="2026-Q1", issuer="corporate", fitness="READY", value=0.2):
    feature = {"fitness": fitness, "value": value, "method": "same_provider_same_period_gross_margin/v2",
               "period_identity": [period, period], "scope": ["consolidated"], "currency": None, "scale": None,
               "period_semantics": ["STANDALONE_QUARTER"], "provider_source_provenance": [{"provider": "KBS"}],
               "reason_codes": [] if fitness == "READY" else ["RESEARCH_PROXY_ONLY"]}
    records = {f"T{i}": {"issuer_type": issuer, "features": {"gross_margin": {**feature, "value": value + i / 100}}}
               for i in range(6)}
    engine = {"contract_version": projection.ENGINE_CONTRACT, "records": records}
    engine.update(projection._identity(engine))
    compact = projection.build_product_projection(financial_context=engine, product_tickers=list(records), requested_at="fixed")
    wrapper = {"contract_version": "canonical_daily_financial_v2_materialization/v1", "decision_session": "2026-09-30",
               "financial_analysis_product": compact, "financial_content_identity": compact["artifact_identity"],
               "financial_v2_engine_identity": engine["artifact_identity"],
               "engine_fundamental_peer_context": peers.attach_engine_fundamental_peers(records)}
    wrapper.update(projection._identity(wrapper))
    return wrapper, compact, records


def join(wrapper, compact):
    return projection.financial_peer_contexts(materialization=wrapper, product=compact, session="2026-09-30")


def resign(wrapper):
    wrapper.update(projection._identity(wrapper))


def test_valid_context_preserves_comparison_and_delivery_provenance():
    wrapper, compact, _ = inputs()
    context = join(wrapper, compact)["T0"]
    metric = context["metrics"]["gross_margin"]
    assert context["status"] == "PARTIAL"  # Other metrics keep their exact missing-evidence reasons.
    assert metric["relative_position"] == "BELOW_PEER_MEDIAN"
    assert metric["freshness"]["freshness_status"] == "CURRENT"
    assert metric["comparability_basis"]["providers"] == ["KBS"]
    result = build(compact["records"]["T0"], context)
    delivered = project_integrated_decision_for_ai_delivery(result)
    assert delivered["financial_peer_context"] == context
    assert delivered["evidence_axes"]["FUNDAMENTAL"]["context"]["financial_peer_context"] == context
    assert delivered["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["financial_peer_context"] == context
    assert delivered["is_actionable"] is False
    delivered["financial_peer_context"]["metrics"].clear()
    assert result["financial_peer_context"]["metrics"]


def build(financial, context=None, *, reversal=False):
    tactical = {"market_structure_state": "EARLY_BULLISH_REVERSAL" if reversal else "UPTREND",
                "breakout_state_v3": "BREAKOUT_SETUP" if reversal else "FAILED_BREAKOUT", "trigger_state": "NOT_TRIGGERED"}
    return decision.build_ticker_integrated_decision(
        ticker="T0", as_of_session="2026-09-30", tactical_record=tactical, financial_record=financial,
        valuation_record=None, relative_volume_record=None, market_sector_record=None,
        financial_peer_context=context,
        technical_coverage_disposition_record={"has_exact_session_bar": True, "is_current_session": True,
            "feature_as_of_session": "2026-09-30", "disposition": "SAME_SESSION_TECHNICAL_COVERED"})


@pytest.mark.parametrize("reversal,value", [(False, 0.9), (True, -0.9)])
def test_peer_rank_never_independently_promotes_or_suppresses_posture(reversal, value):
    wrapper, compact, _ = inputs(value=value)
    metric = wrapper["engine_fundamental_peer_context"]["T0"]["gross_margin"]
    metric["percentile"] = 0.99 if not reversal else 0.01
    resign(wrapper)
    before = build(compact["records"]["T0"], reversal=reversal)
    after = build(compact["records"]["T0"], join(wrapper, compact)["T0"], reversal=reversal)
    for field in ("research_action_posture", "why_now", "counter_thesis", "fundamental_state", "fundamental_support",
                  "valuation_context_summary", "fundamental_synthesis", "evidence_axis_coherence"):
        assert after[field] == before[field], field
    assert after["research_action_posture"] not in {"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST", "AVOID"}


def test_missing_input_keeps_compatibility_and_missing_ticker_is_explicit():
    assert projection.financial_peer_contexts(materialization=None, product=None, session="2026-09-30") == {}
    wrapper, compact, _ = inputs()
    wrapper["engine_fundamental_peer_context"].pop("T0")
    resign(wrapper)
    context = join(wrapper, compact)["T0"]
    assert context["status"] == "UNAVAILABLE"
    assert context["reason_codes"] == ["FINANCIAL_PEER_CONTEXT_ABSENT"]
    assert build(compact["records"]["T0"], context)["counter_thesis"] == build(compact["records"]["T0"])["counter_thesis"]


@pytest.mark.parametrize("period,reason", [("2024-Q1", "FINANCIAL_PEER_NOT_CURRENT"),
                                         ("2026-Q4", "FINANCIAL_PERIOD_AFTER_DECISION_SESSION")])
def test_stale_and_future_periods_do_not_enter_current_peer_evidence(period, reason):
    wrapper, compact, _ = inputs(period=period)
    metric = join(wrapper, compact)["T0"]["metrics"]["gross_margin"]
    assert metric["status"] == "BLOCKED"
    assert reason in metric["consumer_blocker_reason_codes"]
    assert "relative_position" not in metric
    assert metric["source_status"] == "READY_RESEARCH_ONLY"


@pytest.mark.parametrize("change", ["provider", "period", "entity", "scope", "semantics", "method"])
def test_incompatible_peer_members_never_pool(change):
    _, _, records = inputs()
    records = copy.deepcopy(records)
    feature = records["T5"]["features"]["gross_margin"]
    if change == "provider":
        feature["provider_source_provenance"] = [{"provider": "VCI"}]
    elif change == "period":
        feature["period_identity"] = ["2026-Q2"]
    elif change == "entity":
        records["T5"]["issuer_type"] = "bank"
    elif change == "scope":
        feature["scope"] = ["separate"]
    elif change == "semantics":
        feature["period_semantics"] = ["YTD"]
    else:
        feature["method"] = "other_method/v1"
    result = peers.attach_engine_fundamental_peers(records, industry_by_ticker={t: "same_sector" for t in records})
    assert result["T0"]["gross_margin"]["peer_count"] == 5
    assert result["T5"]["gross_margin"]["status"] != "READY_RESEARCH_ONLY"


@pytest.mark.parametrize("issuer", ["bank", "securities"])
def test_specialists_prove_corporate_peer_non_applicability(issuer):
    wrapper, compact, _ = inputs(issuer=issuer)
    context = join(wrapper, compact)["T0"]
    assert context["status"] == "NOT_APPLICABLE"
    assert context["usable_metric_count"] == 0
    assert all("relative_position" not in m for m in context["metrics"].values())


def test_proxy_remains_proxy_and_exact_blocker_survives():
    wrapper, compact, _ = inputs(fitness="RESEARCH_PROXY")
    context = join(wrapper, compact)["T0"]
    assert context["status"] == "BLOCKED"
    assert context["metrics"]["gross_margin"]["reason"] == ["RESEARCH_PROXY_ONLY"]
    assert context["metrics"]["gross_margin"]["comparability_basis"]["fitness"] == "RESEARCH_PROXY"


@pytest.mark.parametrize("change,reason", [("count", "FINANCIAL_PEER_COHORT_TOO_SMALL"),
                                         ("period", "FINANCIAL_PEER_PERIOD_MISMATCH"),
                                         ("basis", "FINANCIAL_PEER_COMPARABILITY_BASIS_UNPROVEN")])
def test_consumer_rejects_unqualified_claim_even_with_valid_wrapper_identity(change, reason):
    wrapper, compact, _ = inputs()
    metric = wrapper["engine_fundamental_peer_context"]["T0"]["gross_margin"]
    if change == "count":
        metric["peer_count"] = 1
    elif change == "period":
        metric["as_of_period"] = "2026-Q2"
    else:
        metric.pop("comparability_basis")
    resign(wrapper)
    result = join(wrapper, compact)["T0"]["metrics"]["gross_margin"]
    assert result["status"] == "BLOCKED"
    assert reason in result["consumer_blocker_reason_codes"]


@pytest.mark.parametrize("change", ["tamper", "session", "nested_identity"])
def test_wrapper_binding_fails_closed(change):
    wrapper, compact, _ = inputs()
    if change == "tamper":
        wrapper["engine_fundamental_peer_context"].clear()
    elif change == "session":
        wrapper["decision_session"] = "2026-10-01"
        resign(wrapper)
    else:
        wrapper["financial_content_identity"] = "other"
        resign(wrapper)
    with pytest.raises(projection.FinancialAnalysisProductProjectionError):
        join(wrapper, compact)
