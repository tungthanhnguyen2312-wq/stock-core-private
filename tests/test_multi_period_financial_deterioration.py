"""Repeated financial observations, accounting boundaries, and actual research delivery."""
import copy

import pytest

from tests.test_financial_analysis_engine_v2 import context, row
from tests.test_financial_ratio_research_scaleout import ratio_rows
from tests.test_valuation_balance_sheet_divergence import fixture, run, SESSION
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import financial_analysis_product_projection as projection
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.decision import integrated_investment_decision_product as decision
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery, _decision_card
import canonical_daily_financial_v2_materialization as material


PERIODS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]


def trajectory(fid="cash_to_assets", values=(50,40,30,20,10), periods=PERIODS, **kwargs):
    rows = ratio_rows(fid, periods, values=values, **kwargs)
    return context(rows)["history_context"][fid]["trajectory"]


@pytest.mark.parametrize("fid,values,expected", [
    ("cash_to_assets", (50,40,30,20,10), "PERSISTENT_DETERIORATION"),
    ("debt_to_assets", (10,20,30,40,50), "PERSISTENT_DETERIORATION"),
    ("debt_to_equity", (50,40,30,20,10), "SUCCESSIVE_IMPROVEMENT"),
    ("cash_to_assets", (50,40,20,30,40), "RECOVERY"),
    ("cash_to_assets", (50,40,20,30,25), "MIXED_OR_ONE_PERIOD_FLUCTUATION"),
    ("cash_to_assets", (20,20,20,20,20), "STABLE"),
    ("pbt_margin", (50,40,30,20,10), "PERSISTENT_DETERIORATION"),
])
def test_real_ratios_establish_repeated_direction_and_evidence(fid, values, expected):
    t = trajectory(fid, values)
    assert t["status"] == "AVAILABLE" and t["assessment"] == expected
    assert len(t["observations"]) == 5 and len(t["sequential_changes"]) == 4
    assert len(t["yoy_changes"]) == 1
    assert t["observations"][-1]["value"] == pytest.approx(values[-1]/100)
    assert all(len(o["source_provenance"]) == 2 for o in t["observations"])
    assert t["yoy_changes"][0]["comparison_basis"] == "SAME_QUARTER_YOY"
    assert t["is_actionable"] is False


def test_recovery_keeps_contradicting_yoy_instead_of_overwriting_it():
    t = trajectory(values=(50,40,20,30,40))
    assert t["assessment"] == "RECOVERY"
    assert t["seasonal_confirmation"] == "CONTRADICTS_RECENT_DIRECTION"
    assert t["yoy_changes"][0]["ratio_point_change"] == pytest.approx(-.1)


def test_gap_is_not_bridged_and_one_change_is_not_persistence():
    t = trajectory(values=(50,40,30,20), periods=["2025-Q1", "2025-Q2", "2025-Q4", "2026-Q1"])
    assert t["status"] == "UNKNOWN"
    assert t["contiguous_periods"] == ["2025-Q4", "2026-Q1"]
    assert len(t["sequential_changes"]) == 2


@pytest.mark.parametrize("dimension", ["provider", "statement_scope", "currency", "scale"])
def test_different_accounting_representation_cannot_fill_missing_period(dimension):
    rows = ratio_rows("cash_to_assets", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        if r["native_period_label"] == "2025-Q4":
            if dimension == "provider":
                r["source_lineage"]["provider"] = "VCI"
            elif dimension == "statement_scope":
                r[dimension] = "standalone"
            else:
                r["normalized_candidate_unit"][dimension] = "different"
    t = context(rows)["history_context"]["cash_to_assets"]["trajectory"]
    assert t["status"] == "UNKNOWN" and t["contiguous_periods"] == ["2026-Q1"]


@pytest.mark.parametrize("bad", [0, -1])
def test_nonpositive_equity_does_not_create_improving_leverage(bad):
    rows = ratio_rows("debt_to_equity", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        if r["canonical_metric"] == "shareholders_equity" and r["native_period_label"] == "2025-Q4":
            r["reported_value"] = bad
    t = context(rows)["history_context"]["debt_to_equity"]["trajectory"]
    assert t["status"] == "UNKNOWN"


def test_conflicting_revision_breaks_continuity_and_order_does_not_matter():
    rows = ratio_rows("cash_to_assets", PERIODS, values=[50,40,30,20,10])
    rows.append({**copy.deepcopy(rows[-4]), "reported_value": 999})
    a = context(rows)["history_context"]["cash_to_assets"]["trajectory"]
    assert a["status"] == "UNKNOWN"
    assert a == context(list(reversed(rows)))["history_context"]["cash_to_assets"]["trajectory"]


def test_raw_cumulative_margin_is_not_a_sequential_quarter():
    rows = ratio_rows("pbt_margin", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        r["period_semantic_state"] = "YEAR_TO_DATE"
    t = context(rows)["history_context"]["pbt_margin"]["trajectory"]
    assert t["status"] == "UNKNOWN"
    assert t["observations"] == []


@pytest.mark.parametrize("end", ["2025-11-30", "2025-09-30"])
def test_supplied_incompatible_end_cannot_fill_a_calendar_quarter(end):
    rows = ratio_rows("cash_to_assets", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        if r["native_period_label"] == "2025-Q4":
            r["period_end"] = end
    t = context(rows)["history_context"]["cash_to_assets"]["trajectory"]
    assert t["status"] == "UNKNOWN" and t["contiguous_periods"] == ["2026-Q1"]
    assert "CONFLICTING_OR_NONCALENDAR_PERIOD_END_EXCLUDED" in t["reason_codes"]


def test_missing_fact_dates_are_preserved_without_inference():
    rows = ratio_rows("cash_to_assets", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        r.pop("period_end")
    t = context(rows)["history_context"]["cash_to_assets"]["trajectory"]
    assert t["status"] == "AVAILABLE"
    assert all(o["period_end"] == [None,None] for o in t["observations"])


def test_bridge_period_label_and_equivalent_reported_date_are_compatible():
    rows = ratio_rows("pbt_margin", PERIODS, values=[50,40,30,20,10])
    for r in rows:
        if r["canonical_metric"] == "revenue":
            year, quarter = engine._quarter(r["native_period_label"])
            r["period_end"] = f"{year}-{('03-31','06-30','09-30','12-31')[quarter-1]}"
    t = context(rows)["history_context"]["pbt_margin"]["trajectory"]
    assert t["assessment"] == "PERSISTENT_DETERIORATION"
    assert t["observations"][-1]["period_end"] == ["2026-Q1", "2026-03-31"]


def test_subject_anchor_excludes_future_and_competing_longer_provider():
    rows = ratio_rows("cash_to_assets", PERIODS, values=[50,40,30,20,10])
    feature = engine._ratio("cash_to_assets", (rows[4], rows[5]), method="test")
    rows += ratio_rows("cash_to_assets", PERIODS, values=[1,2,3,4,5], provider="VCI")
    t = engine.build_ratio_trajectories(rows, {"cash_to_assets": feature})["cash_to_assets"]
    assert t["assessment"] == "PERSISTENT_DETERIORATION"
    assert t["subject_period"] == "2025-Q3" and len(t["observations"]) == 3


def test_specialist_corporate_rules_remain_not_applicable():
    evaluated, wrapper, sectors, raw = fixture(issuer="bank")
    t = run(evaluated, wrapper, sectors, raw)["records"]["T0"]["multi_period_financial_context"]
    assert t["status"] == "NOT_APPLICABLE" and not t["metric_trajectories"]


@pytest.mark.parametrize("cash,debt,expected", [
    ((50,40,30,20,10), (50,40,30,20,10), "MIXED"),
    ((10,20,30,40,50), (50,40,30,20,10), "SUCCESSIVE_IMPROVEMENT"),
    ((50,40,20,30,40), (10,20,40,30,20), "RECOVERY"),
    ((10,10,10,10,10), (20,20,20,20,20), "STABLE"),
])
def test_synthesis_preserves_conflicts_instead_of_counting_debt_twice(cash,debt,expected):
    metrics = {f:{"status":"UNKNOWN","reason_codes":["ABSENT"]} for f in valuation.DIVERGENCE_FEATURES}
    for fid,values in (("cash_to_assets",cash),("debt_to_assets",debt),("debt_to_equity",debt)):
        metrics[fid] = {"status":"AVAILABLE","reason_codes":[],
            "own_history_context":{"trajectory":trajectory(fid,values)}}
    t = valuation._multi_period_divergence(metrics,{"status":"READY_RESEARCH_ONLY","percentile":.1})
    assert t["assessment"] == expected and t["status"] == "AVAILABLE"
    if expected == "RECOVERY":
        assert any(e["observation"] == "SAME_QUARTER_YOY_CONTRADICTS_RECENT_DIRECTION" for e in t["contradicting_evidence"])
    metrics["cash_to_assets"]["status"] = "UNKNOWN"
    assert valuation._multi_period_divergence(metrics,{})["assessment"] == "INSUFFICIENT_EVIDENCE"


def test_real_trajectories_survive_all_delivery_paths_without_policy_change():
    evaluated, wrapper, sectors, raw = fixture()
    records = {}
    for ticker in evaluated["records"]:
        rows = []
        for i,period in enumerate(PERIODS):
            for metric,value in [("cash_and_cash_equivalents", 50-i*10), ("total_assets",100),
                                 ("total_interest_bearing_debt", 10+i*10), ("shareholders_equity",80)]:
                rows.append(row(metric,value,period,ticker=ticker,provider="VCI",sha="balance:sha",semantic=engine.PIT))
        records[ticker] = engine.build_ticker_context(ticker,rows,issuer_type="corporate",source_identities={})
    artifact = {"contract_version": engine.CONTRACT_VERSION,"records": records}
    artifact.update(engine.content_identity(artifact))
    compact = projection.build_product_projection(financial_context=artifact,product_tickers=list(records),requested_at="fixed")
    wrapper.update(financial_analysis_product=compact, financial_content_identity=compact["artifact_identity"],
        financial_v2_engine_identity=artifact["artifact_identity"],
        engine_fundamental_peer_context=valuation.attach_engine_fundamental_peers(records,industry_by_ticker=sectors))
    wrapper.update(material._identity(wrapper))
    evaluated["source_financial_v2_identity"] = artifact["artifact_identity"]
    evaluated.update(material._identity(evaluated))
    kwargs = dict(session=SESSION,requested_at="fixed",technical_structure_artifact={"records":{}},
        financial_analysis_artifact=compact,financial_peer_materialization_artifact=wrapper)
    before = decision.build_artifact(**kwargs,current_valuation_artifact=evaluated)
    run(evaluated,wrapper,sectors,raw)
    after = decision.build_artifact(**kwargs,current_valuation_artifact=evaluated)
    record = after["records"]["T0"]
    expected = record["valuation_balance_sheet_divergence"]
    assert expected["multi_period_financial_context"]["assessment"] == "PERSISTENT_DETERIORATION"
    assert expected["multi_period_financial_context"]["valuation_relationship"] == "DISCOUNT_WITH_PERSISTENT_DETERIORATION"
    for key in ("research_action_posture", "fundamental_state", "fundamental_synthesis", "evidence_axis_coherence"):
        assert before["records"]["T0"][key] == record[key]
    ai = project_integrated_decision_for_ai_delivery(record)
    assert ai["valuation_balance_sheet_divergence"] == expected
    assert ai["current_research_decision_input"]["dimensions"]["VALUATION"]["balance_sheet_divergence"] == expected
    assert _decision_card("T0",record,None,source_session=SESSION)["valuation"]["balance_sheet_divergence"] == expected

