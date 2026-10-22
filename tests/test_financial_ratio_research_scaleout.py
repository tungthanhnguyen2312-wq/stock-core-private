"""Financial ratio analysis: exact historical operands, independent peer eligibility, delivery."""
import copy

import pytest

from tests.test_financial_analysis_engine_v2 import row, context
from tests.test_financial_peer_decision_integration import build
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import financial_analysis_product_projection as projection
from stocklookup_core.valuation import current_research_valuation_context as valuation
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


PERIODS = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]


def ratio_rows(fid, periods=PERIODS, *, provider="KBS", scope="consolidated", values=None):
    numerator, denominator, semantic = engine.EXTENDED_RATIO_HISTORY_INPUTS[fid]
    rows = []
    for i, period in enumerate(periods):
        for metric, value in [(numerator, (values or [10, 20, 30, 40, 50, 60, 70])[i]), (denominator, 100)]:
            rows.append(row(metric, value, period, provider=provider, semantic=semantic, scope=scope))
    return rows


@pytest.mark.parametrize("fid", engine.EXTENDED_RATIO_HISTORY_INPUTS)
def test_ratio_history_actual_computation_and_source_parity(fid):
    rows = ratio_rows(fid)
    saved = copy.deepcopy(rows)
    result = context(rows)
    feature, history = result["features"][fid], result["history_context"][fid]
    assert rows == saved
    assert feature["value"] == pytest.approx(.7)
    assert history["subject_value"] == feature["value"]
    assert history["sample_count"] == 6 and history["status"] == "AVAILABLE"
    assert history["percentile"] == 1 and history["range_min"] == .1
    assert history["range_max"] == .6
    assert context(list(reversed(rows)))["history_context"][fid] == history


@pytest.mark.parametrize("dimension", ["provider", "scope"])
def test_history_anchors_actual_subject_even_when_competing_long_series_shares_period(dimension):
    # Both sources include Q1. Only the longer competing source includes Q2;
    # subject is the newer KBS consolidated Q2, whose three priors are retained.
    rows = ratio_rows("cash_to_assets", PERIODS[-4:])
    alternate = {dimension: "VCI" if dimension == "provider" else "standalone"}
    rows += ratio_rows("cash_to_assets", PERIODS[:-1], values=[90]*6, **alternate)
    result = context(rows)
    history = result["history_context"]["cash_to_assets"]
    assert history["status"] == "PARTIAL" and history["sample_count"] == 3
    assert history["range_max"] == .3
    assert history["subject_value"] == .4


def test_same_label_competing_provider_cannot_supply_history():
    rows = ratio_rows("cash_to_assets", PERIODS[-1:])
    rows += ratio_rows("cash_to_assets", PERIODS, provider="VCI", values=[90]*7)
    feature = engine._ratio("cash_to_assets", (rows[0], rows[1]), method="test")
    series = engine._ratio_series(rows, "cash_and_cash_equivalents", engine.PIT,
        "total_assets", engine.PIT, subject_feature=feature)
    assert series == {"2026-Q2": .1}


def test_history_excludes_future_observations_relative_to_bound_subject():
    rows = ratio_rows("cash_to_assets")
    feature = engine._ratio("cash_to_assets", (rows[6], rows[7]), method="test")
    series = engine._ratio_series(rows, "cash_and_cash_equivalents", engine.PIT,
        "total_assets", engine.PIT, subject_feature=feature)
    assert max(series) == "2025-Q3" and len(series) == 4


def test_missing_debt_zero_and_conflicting_denominators_never_become_comparisons():
    rows = ratio_rows("debt_to_equity")
    for r in rows:
        if r["canonical_metric"] == "shareholders_equity":
            r["reported_value"] = 0
    result = context(rows)
    assert result["features"]["debt_to_equity"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["history_context"]["debt_to_equity"]["status"] == "UNAVAILABLE"
    # Total/current liabilities cannot stand in for explicit interest-bearing debt.
    no_debt = [row("total_assets", 100, semantic=engine.PIT),
               row("current_liabilities", 80, semantic=engine.PIT)]
    assert context(no_debt)["features"]["debt_to_assets"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    rows = ratio_rows("debt_to_assets", PERIODS[-1:])
    rows.append({**rows[-1], "reported_value": 200})
    assert context(rows)["history_context"]["debt_to_assets"]["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("fid", engine.EXTENDED_RATIO_HISTORY_INPUTS)
def test_peer_medians_comparability_and_decision_ai_survival(fid):
    records = {f"T{i}": context(ratio_rows(fid, values=[10+i]*7)) for i in range(6)}
    artifact = {"contract_version": engine.CONTRACT_VERSION, "records": records}
    artifact.update(engine.content_identity(artifact))
    compact = projection.build_product_projection(financial_context=artifact, product_tickers=list(records), requested_at="fixed")
    peers = valuation.attach_engine_fundamental_peers(records, industry_by_ticker={t: "retained sector" for t in records})
    wrapper = {"contract_version": "canonical_daily_financial_v2_materialization/v1", "decision_session": "2026-10-16",
        "financial_analysis_product": compact, "financial_content_identity": compact["artifact_identity"],
        "financial_v2_engine_identity": artifact["artifact_identity"], "engine_fundamental_peer_context": peers}
    wrapper.update(projection._identity(wrapper))
    joined = projection.financial_peer_contexts(materialization=wrapper, product=compact, session="2026-10-16")
    metric = joined["T0"]["metrics"][fid]
    assert metric["status"] == "READY_RESEARCH_ONLY"
    assert metric["peer_count"] == 6 and metric["peer_median"] == pytest.approx(.125)
    assert metric["percentile"] == pytest.approx(.5/6)
    assert metric["relative_position"] == "BELOW_PEER_MEDIAN"
    before = build(compact["records"]["T0"])
    after = build(compact["records"]["T0"], joined["T0"])
    assert before["research_action_posture"] == after["research_action_posture"]
    delivered = project_integrated_decision_for_ai_delivery(after)
    assert delivered["financial_peer_context"] == joined["T0"]
    assert delivered["financial_peer_context"]["metrics"][fid]["own_history_context"] == compact["records"]["T0"]["history_context"][fid]
    assert delivered["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["financial_peer_context"] == joined["T0"]
    assert compact["records"]["T0"]["history_context"][fid]["status"] == "AVAILABLE"
    for incompatible in ("method", "scope", "currency", "period_semantics"):
        changed = copy.deepcopy(records)
        feature = changed["T5"]["features"][fid]
        feature[incompatible] = ["other"] if isinstance(feature[incompatible], list) else "other"
        peer = valuation.attach_engine_fundamental_peers(changed)["T5"][fid]
        assert peer["status"] != "READY_RESEARCH_ONLY"


def test_small_peer_cohort_does_not_erase_legitimate_own_history():
    record = context(ratio_rows("cash_to_assets"))
    artifact = {"contract_version": engine.CONTRACT_VERSION, "records": {"T0": record}}
    artifact.update(engine.content_identity(artifact))
    compact = projection.build_product_projection(financial_context=artifact, product_tickers=["T0"], requested_at="fixed")
    wrapper = {"contract_version": "canonical_daily_financial_v2_materialization/v1", "decision_session": "2026-10-16",
        "financial_analysis_product": compact, "financial_content_identity": compact["artifact_identity"],
        "financial_v2_engine_identity": artifact["artifact_identity"],
        "engine_fundamental_peer_context": valuation.attach_engine_fundamental_peers(artifact["records"])}
    wrapper.update(projection._identity(wrapper))
    joined = projection.financial_peer_contexts(materialization=wrapper, product=compact, session="2026-10-16")
    metric = joined["T0"]["metrics"]["cash_to_assets"]
    assert metric["status"] == "INSUFFICIENT_PEER_COUNT"
    assert metric["own_history_context"]["status"] == "AVAILABLE"
    delivered = project_integrated_decision_for_ai_delivery(build(compact["records"]["T0"], joined["T0"]))
    assert delivered["financial_peer_context"]["metrics"]["cash_to_assets"] == metric
    # Stale historical research stays descriptive; a future or unresolved subject
    # cannot arrive at AI as an available independent history observation.
    wrapper["decision_session"] = "2025-10-16"
    wrapper.update(projection._identity(wrapper))
    future = projection.financial_peer_contexts(materialization=wrapper, product=compact, session="2025-10-16")
    history = future["T0"]["metrics"]["cash_to_assets"]["own_history_context"]
    assert history["status"] == "UNAVAILABLE" and "subject_value" not in history
    wrapper["decision_session"] = "2028-10-16"
    wrapper.update(projection._identity(wrapper))
    stale = projection.financial_peer_contexts(materialization=wrapper, product=compact, session="2028-10-16")
    assert stale["T0"]["metrics"]["cash_to_assets"]["own_history_context"]["status"] == "AVAILABLE"
    assert stale["T0"]["metrics"]["cash_to_assets"]["freshness"]["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"


@pytest.mark.parametrize("issuer", ["bank", "securities", "insurance", "finance_company", "unknown"])
def test_corporate_ratios_never_expand_specialist_applicability(issuer):
    record = context(ratio_rows("cash_to_assets"), entity=issuer)
    peers = valuation.attach_engine_fundamental_peers({"T0": record})["T0"]
    for fid in engine.EXTENDED_RATIO_HISTORY_INPUTS:
        assert record["history_context"][fid]["status"] == "NOT_APPLICABLE"
        assert peers[fid]["status"] == "NOT_COMPARABLE"
