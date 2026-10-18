"""Qualified sector trajectory comparisons and end-to-end research transport."""
import copy

import pytest

from tests.test_financial_analysis_engine_v2 import row
from tests.test_valuation_balance_sheet_divergence import fixture, run, SESSION
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import financial_analysis_product_projection as projection
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.decision import integrated_investment_decision_product as decision
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery, _decision_card
import canonical_daily_financial_v2_materialization as material


PERIODS = ["2025-Q3","2025-Q4","2026-Q1"]


def scenario(kind="resilient", count=6):
    evaluated,wrapper,sectors,raw = fixture()
    records = {}
    for i,ticker in enumerate(list(evaluated["records"])[:count]):
        cash = [40,30,20]
        debt = [20,30,40]
        if kind == "resilient" and i == 0 or kind == "improving":
            cash,debt = [10,20,30],[40,30,20]
        if kind in {"firm_risk","conflict"} and i > 0:
            cash,debt = [10,20,30],[40,30,20]
        if kind == "conflict":
            cash = [10,20,30] if i == 0 else [40,30,20]
        if kind == "opposed":
            cash = [40,30,20] if i == 0 else [10,20,30]
            debt = [40,30,20]
        rows = []
        for j,p in enumerate(PERIODS):
            for metric,value in [("cash_and_cash_equivalents",cash[j]),("total_assets",100),
                ("total_interest_bearing_debt",debt[j]),("shareholders_equity",80)]:
                r = row(metric,value,p,ticker=ticker,provider="VCI",sha="balance:sha",semantic=engine.PIT)
                r["statement_family"] = "balance_sheet"
                rows.append(r)
        records[ticker] = engine.build_ticker_context(ticker,rows,issuer_type="corporate",source_identities={})
    evaluated["records"] = {t:r for t,r in evaluated["records"].items() if t in records}
    artifact = {"contract_version":engine.CONTRACT_VERSION,"records":records}
    artifact.update(engine.content_identity(artifact))
    compact = projection.build_product_projection(financial_context=artifact,product_tickers=list(records),requested_at="fixed")
    wrapper.update(financial_analysis_product=compact,financial_content_identity=compact["artifact_identity"],
        financial_v2_engine_identity=artifact["artifact_identity"],
        engine_fundamental_peer_context=valuation.attach_engine_fundamental_peers(records,industry_by_ticker=sectors))
    wrapper.update(material._identity(wrapper))
    evaluated["source_financial_v2_identity"] = artifact["artifact_identity"]
    evaluated.update(material._identity(evaluated))
    return evaluated,wrapper,sectors,raw


@pytest.mark.parametrize("kind,expected", [
    ("resilient","RESILIENCE_AGAINST_WEAK_PEERS"),
    ("firm_risk","COMPANY_SPECIFIC_WEAKNESS"),
    ("shared","DETERIORATION_SHARED_WITH_SECTOR_SAMPLE"),
    ("improving","RECOVERY_OR_IMPROVEMENT_WITH_PEERS"),
    ("conflict","CONFLICTING_FINANCIAL_RESILIENCE"),
    ("opposed","CONFLICTING_FINANCIAL_RESILIENCE")])
def test_actual_observations_differentiate_company_and_sector_sample(kind,expected):
    evaluated,wrapper,sectors,raw = scenario(kind)
    context = run(evaluated,wrapper,sectors,raw)
    result = context["records"]["T0"]["sector_relative_financial_resilience"]
    assert result["status"] == "AVAILABLE" and result["assessment"] == expected
    assert result["qualified_metric_comparisons"] == 3
    assert result["qualified_interval_comparisons"] == 6
    comparison = result["metric_comparisons"]["cash_to_assets"]
    assert comparison["peer_count"] == 6 and comparison["peer_count_includes_subject"]
    assert comparison["periods"] == PERIODS
    assert len(comparison["member_window_evidence_sha256"]) == 6
    assert result["is_actionable"] is False
    if kind == "resilient":
        assert comparison["intervals"][0]["subject_value"] == pytest.approx(.1)
        assert comparison["intervals"][0]["peer_median_ratio_point_change"] == pytest.approx(-.1)
        assert comparison["intervals"][0]["percentile"] == pytest.approx(5.5/6)
        assert result["valuation_relationship"] == "DISCOUNT_WITH_RESILIENCE_COUNTERTHESIS"


@pytest.mark.parametrize("count,available", [(4,False),(5,True)])
def test_standing_peer_minimum_is_reused_without_lowering_it(count,available):
    e,w,s,r = scenario(count=count)
    result = run(e,w,s,r)["records"]["T0"]["sector_relative_financial_resilience"]
    assert (result["status"] == "AVAILABLE") == available
    assert result["metric_comparisons"]["cash_to_assets"]["minimum_peer_count"] == valuation.MIN_COHORT_MEMBERS


@pytest.mark.parametrize("field,value", [("currency","USD"),("scale","different"),
    ("statement_family","different"),("statement_scope","standalone"),("provider","KBS")])
def test_incompatible_series_cannot_join_a_sector_pool(field,value):
    e,w,s,r = scenario()
    rows = run(e,w,s,r)["records"]
    subject = rows["T0"]
    for fid in ("cash_to_assets","debt_to_assets","debt_to_equity"):
        metric = subject["financial_measures"][fid]
        t = subject["multi_period_financial_context"]["metric_trajectories"][fid]
        t["series_identity"][field] = value
        if field == "statement_scope":
            metric["source_feature_context"]["scope"] = [value]
        if field == "provider":
            for p in metric["source_feature_context"]["source_fact_refs"]:
                p["provider"] = value
            for o in t["observations"]:
                for p in o["source_provenance"]:
                    p["provider"] = value
    valuation.attach_sector_trajectory_peers(rows,decision_session=SESSION)
    assert subject["sector_relative_financial_resilience"]["status"] == "UNKNOWN"
    assert subject["multi_period_financial_context"]["status"] == "AVAILABLE"


@pytest.mark.parametrize("mutation", ["sector","method","period","cadence","missing_change","provenance","value","semantic"])
def test_unknown_or_incompatible_evidence_only_narrows_dependent_research(mutation):
    e,w,s,r = scenario()
    rows = run(e,w,s,r)["records"]
    subject = rows["T0"]
    if mutation == "sector":
        subject["valuation"]["cohort_id"] = "ENTITY_CLASS:corporate"
    for fid in ("cash_to_assets","debt_to_assets","debt_to_equity"):
        source = subject["financial_measures"][fid]["source_feature_context"]
        t = subject["multi_period_financial_context"]["metric_trajectories"][fid]
        if mutation == "method":
            source["method"] = "other method"
        if mutation == "period":
            t["contiguous_periods"] = ["2025-Q2","2025-Q3","2025-Q4"]
        if mutation == "cadence":
            t["contiguous_periods"] = ["2025-Q2","2025-Q4","2026-Q1"]
        if mutation == "missing_change":
            t["sequential_changes"].pop()
        if mutation == "provenance":
            t["observations"][-1]["source_provenance"][0]["source_sha256"] = None
        if mutation == "value":
            t["observations"][-1]["value"] = 999
        if mutation == "semantic":
            t["period_semantic"] = "YEAR_TO_DATE"
    saved = copy.deepcopy(subject["multi_period_financial_context"])
    valuation.attach_sector_trajectory_peers(rows,decision_session=SESSION)
    assert subject["sector_relative_financial_resilience"]["status"] == "UNKNOWN"
    assert subject["multi_period_financial_context"] == saved


@pytest.mark.parametrize("issuer", ["bank","securities","insurance"])
def test_specialists_cannot_inherit_corporate_resilience(issuer):
    e,w,s,r = fixture(issuer=issuer)
    context = run(e,w,s,r)
    assert context["records"]["T0"]["sector_relative_financial_resilience"]["status"] == "NOT_APPLICABLE"


def test_ties_and_input_order_use_existing_percentile_semantics():
    e,w,s,r = scenario("shared")
    rows = run(e,w,s,r)["records"]
    comparison = rows["T0"]["sector_relative_financial_resilience"]["metric_comparisons"]["cash_to_assets"]
    assert comparison["intervals"][0]["percentile"] == .5
    saved = copy.deepcopy(rows)
    valuation.attach_sector_trajectory_peers(dict(reversed(list(rows.items()))),decision_session=SESSION)
    assert rows == saved


def test_material_findings_reach_actual_decision_card_and_ai_without_policy_change():
    e,w,s,r = scenario()
    run(e,w,s,r)
    before = copy.deepcopy(e)
    context = before[valuation.DIVERGENCE_MEMBER]
    for record in context["records"].values():
        record.pop("sector_relative_financial_resilience")
    context.update(valuation._research_identity(context,valuation.DIVERGENCE_CONTRACT))
    before.update(material._identity(before))
    kwargs = dict(session=SESSION,requested_at="fixed",technical_structure_artifact={"records":{}},
        financial_analysis_artifact=w["financial_analysis_product"],financial_peer_materialization_artifact=w)
    old = decision.build_artifact(**kwargs,current_valuation_artifact=before)
    new = decision.build_artifact(**kwargs,current_valuation_artifact=e)
    result = new["records"]["T0"]
    expected = result["valuation_balance_sheet_divergence"]
    assert expected["sector_relative_financial_resilience"]["assessment"] == "RESILIENCE_AGAINST_WEAK_PEERS"
    for field in ("research_action_posture","fundamental_state","fundamental_synthesis","valuation_methods","evidence_axis_coherence"):
        assert old["records"]["T0"][field] == result[field]
    assert project_integrated_decision_for_ai_delivery(result)["valuation_balance_sheet_divergence"] == expected
    assert result["current_research_decision_input"]["dimensions"]["VALUATION"]["balance_sheet_divergence"] == expected
    assert _decision_card("T0",result,None,source_session=SESSION)["valuation"]["balance_sheet_divergence"] == expected
