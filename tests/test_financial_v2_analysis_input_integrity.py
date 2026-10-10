"""FINANCIAL_V2_ANALYSIS_INPUT_INTEGRITY_V1: semantic observation identity for Financial V2 inputs."""
from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import date
from pathlib import Path
import random
import re

import pytest

import stocklookup_core.decision.current_research_decision_input as decision_input
import stocklookup_core.valuation.current_research_valuation_context as valuation
import stocklookup_core.financial.financial_analysis_engine_v2 as engine
import stocklookup_core.financial.financial_flow_semantics_ttm_bridge as bridge
import stocklookup_core.financial.market_wide_financial_analysis_v2_scaleout as scaleout
from stocklookup_core.decision.opportunity_axis_freshness import (CURRENT, STALE_BUT_RESEARCH_USABLE, UNAVAILABLE,
                                        classify_financial_period_freshness)
import provider_financial_monetary_basis_verdict as pin
import monetary_basis_contract as basis

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-24"
_END = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"), 3: ("07-01", "09-30"), 4: ("10-01", "12-31")}


def sem(metric, value, period="2026-Q1", *, ticker="AAA", provider="KBS", family="income_statement",
        semantic="STANDALONE_QUARTER", scope="consolidated", currency="unknown", scale="unknown", source=None,
        sha=None, status="provider_reported", cumulative="period_only", observations=None, **changes):
    """A retained `market_wide_structured_financial_period_semantics/v1` row."""
    start, end = _END[int(period[-1])]
    row = {"ticker": ticker, "canonical_metric": metric, "reported_value": value, "native_period_label": period,
           "native_period_type": "quarterly", "period_start": f"{period[:4]}-{start}", "period_end": f"{period[:4]}-{end}",
           "period_semantic_state": semantic, "source_status": status, "lineage_complete": True, "source_conflicts": [],
           "statement_family": family, "statement_scope": scope, "reported_cumulative_state": cumulative,
           "normalized_candidate_unit": {"currency": currency, "scale": scale}, "source_warnings": [],
           "missing_lineage_fields": [],
           "source_lineage": {"provider": provider, "source_file": source or f"{ticker}_{family}_quarter.parquet",
                              "source_sha256": sha or f"sha-{ticker}-{family}", "fact_id": f"{ticker}-{metric}-{period}-{provider}",
                              "source_observation_ids": observations if observations is not None else [f"o-{ticker}-{metric}-{period}"]}}
    row.update(changes)
    return row


def store(ticker="AAA", entity="corporate"):
    return {"ticker": ticker, "entity_type": entity, "entity_applicability": "ENTITY_SPECIFIC", "features": {}}


def build(rows, *, entity="corporate", ticker="AAA"):
    records = {ticker: store(ticker, entity)}
    qualified = scaleout.build_qualified_flow_artifact(semantic_rows=rows, feature_records=records, requested_at="t")
    artifact = scaleout.build_scaleout(semantic_rows=rows, feature_records=records, feature_store_artifact={"artifact_identity": "store:1"},
                                       period_semantics_identity="sem:1", requested_at="t", qualified_flow_artifact=qualified)
    return artifact, artifact["records"][ticker]


def debt_rows(*, total=100, observations=("o-s", "o-l"), long_sha=None, long_status="provider_reported", scope="consolidated"):
    bs = dict(provider="VCI", family="balance_sheet", semantic="POINT_IN_TIME_BALANCE_SHEET", scope=scope)
    composed = sem("total_interest_bearing_debt", total, observations=sorted(observations), **bs)
    composed.update({"lineage_complete": False, "missing_lineage_fields": ["provider", "source_sha256", "source_file"],
                     "source_warnings": ["currency_unknown", "derived_metric", "unit_scale_unknown"]})
    composed["source_lineage"].update({"provider": None, "source_file": None, "source_sha256": None})
    long = sem("long_term_interest_bearing_debt", 40, observations=["o-l"], status=long_status, **bs)
    if long_sha:
        long["source_lineage"]["source_sha256"] = long_sha
    return [sem("short_term_interest_bearing_debt", 60, observations=["o-s"], **bs), long, composed,
            sem("shareholders_equity", 500, **bs), sem("total_assets", 1000, **bs)]


# -- Semantic join ---------------------------------------------------------------------------------

def test_bridge_quarter_and_raw_quarter_of_one_statement_join_with_provenance_intact():
    _, record = build([sem("revenue", 1000), sem("gross_profit", 300)])
    feature = record["features"]["gross_margin"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.3)
    raw, bridged = feature["provider_source_provenance"]
    assert raw["source_file"] == bridged["source_file"] == "AAA_income_statement_quarter.parquet"
    assert raw["source_sha256"] == bridged["source_sha256"] == "sha-AAA-income_statement"
    assert "lineage_method" not in raw
    assert bridged["lineage_method"] == f"{bridge.CONTRACT_VERSION}:DIRECT_STANDALONE_QUARTER"
    assert bridged["operand_fact_ids"] == ["AAA-revenue-2026-Q1-KBS"]
    assert record["input_integrity"]["source_file_role"] == "PROVENANCE_ONLY"


def test_fcf_proxy_joins_bridged_operating_cash_flow_with_raw_capex():
    cash = dict(provider="VCI", family="cash_flow")
    _, record = build([sem("operating_cash_flow", 100, **cash), sem("capital_expenditure", -40, **cash)])
    feature = record["features"]["free_cash_flow_proxy"]
    assert feature["fitness"] == "READY" and feature["value"] == 60
    assert {item["source_file"] for item in feature["provider_source_provenance"]} == {"AAA_cash_flow_quarter.parquet"}


def test_semantic_join_succeeds_across_valid_different_source_files():
    rows = [sem("revenue", 1000, source="AAA_income_a.parquet", sha="sha-a"),
            sem("gross_profit", 250, source="AAA_income_b.parquet", sha="sha-b")]
    feature = engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})["features"]["gross_margin"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.25)
    assert sorted(item["source_file"] for item in feature["provider_source_provenance"]) == ["AAA_income_a.parquet", "AAA_income_b.parquet"]


@pytest.mark.parametrize("change", [
    {"period": "2025-Q4"},
    {"scope": "unknown"},
    {"currency": "USD"},
    {"scale": "thousands"},
    {"provider": "VCI"},
    {"family": "cash_flow"},
    {"semantic": "UNKNOWN_DURATION"},
])
def test_false_joins_fail_closed(change):
    base = dict(currency="VND", scale="units")
    rows = [sem("revenue", 1000, **base), sem("gross_profit", 250, **{**base, **change})]
    feature = engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})["features"]["gross_margin"]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_different_issuers_never_join():
    artifact = engine.build_artifact(tickers=["AAA", "BBB"], rows=[sem("revenue", 1000), sem("gross_profit", 250, ticker="BBB")],
                                     issuer_types={"AAA": "corporate", "BBB": "corporate"}, source_identities={}, requested_at="t")
    assert {t: r["features"]["gross_margin"]["fitness"] for t, r in artifact["records"].items()} == {
        "AAA": "BLOCKED_BY_EVIDENCE", "BBB": "BLOCKED_BY_EVIDENCE"}


def test_repeated_observation_collapses_deterministically_and_a_revision_fails_closed():
    duplicate = [sem("revenue", 1000, source="a.parquet"), sem("revenue", 1000, source="b.parquet"), sem("net_income", 100)]
    duplicate[1]["source_lineage"]["fact_id"] = "AAA-revenue-alt"
    forward = engine.build_ticker_context("AAA", duplicate, issuer_type="corporate", source_identities={})
    backward = engine.build_ticker_context("AAA", list(reversed(duplicate)), issuer_type="corporate", source_identities={})
    assert forward == backward
    assert forward["features"]["net_margin"]["value"] == pytest.approx(0.1)
    assert forward["input_integrity"]["duplicate_observations_collapsed"] == 1
    revised = deepcopy(duplicate)
    revised[1]["reported_value"] = 1200
    result = engine.build_ticker_context("AAA", revised, issuer_type="corporate", source_identities={})
    assert result["features"]["net_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["input_integrity"]["conflicting_observations_excluded"] == 1
    assert result["input_integrity"]["conflicts"][0]["reason_code"] == "SEMANTIC_OBSERVATION_VALUE_CONFLICT_UNRECONCILED"


def test_engine_identity_is_independent_of_row_order():
    rows = [sem("revenue", 100 + i, f"202{5 + (i // 4)}-Q{i % 4 + 1}") for i in range(6)]
    rows += [sem("gross_profit", 30 + i, f"202{5 + (i // 4)}-Q{i % 4 + 1}") for i in range(6)]
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    first = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"}, source_identities={}, requested_at="t")
    second = engine.build_artifact(tickers=["AAA"], rows=shuffled, issuer_types={"AAA": "corporate"}, source_identities={}, requested_at="u")
    assert first["artifact_identity"] == second["artifact_identity"]


# -- Source status carried through the bridge ------------------------------------------------------

def test_partial_operand_stays_partial_through_the_bridge_and_is_not_engine_ready():
    cash = dict(provider="VCI", family="cash_flow")
    rows = [sem("operating_cash_flow", 100, status="partial", **cash), sem("net_income", 10)]
    artifact, record = build(rows)
    quarters = bridge.build_artifact(tickers=["AAA"], facts_by_ticker={"AAA": [scaleout._bridge_fact(r) for r in rows]},
                                     entity_type_by_ticker={"AAA": "corporate"}, requested_at="t")["records"]["AAA"]["standalone_quarters"]
    assert {q["canonical_metric"]: q["source_status"] for q in quarters}["operating_cash_flow"] == "partial"
    assert record["features"]["operating_cash_flow_sign"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert record["features"]["cfo_to_net_income"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_derived_quarter_takes_the_weakest_operand_status():
    assert bridge._combined_status([{"status": "provider_reported"}, {"status": "partial"}]) == "partial"
    assert bridge._combined_status([{"status": "provider_reported"}]) == "provider_reported"


# -- Composed fact lineage -------------------------------------------------------------------------

def test_composed_debt_binds_lineage_by_exact_component_linkage():
    _, record = build(debt_rows())
    feature = record["features"]["debt_to_equity"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.2)
    debt = feature["provider_source_provenance"][0]
    assert debt["provider"] == "VCI" and debt["source_file"] == "AAA_balance_sheet_quarter.parquet"
    assert debt["lineage_method"] == scaleout.COMPOSED_LINEAGE_METHOD
    assert debt["operand_fact_ids"] == ["AAA-short_term_interest_bearing_debt-2026-Q1-VCI",
                                        "AAA-long_term_interest_bearing_debt-2026-Q1-VCI"]
    assert record["leverage_basis"] == "EXPLICIT_SAME_PROVIDER_SHORT_AND_LONG_TERM_BORROWINGS"


@pytest.mark.parametrize("kwargs,outcome", [
    ({"observations": ("o-s", "o-x")}, "COMPOSED_FACT_OBSERVATION_LINKAGE_NOT_EXACT"),
    ({"total": 101}, "COMPOSED_FACT_VALUE_NOT_REPRODUCED_BY_COMPONENTS"),
    ({"long_sha": "sha-other-payload"}, "COMPOSED_FACT_COMPONENTS_NOT_ONE_REPRESENTATION"),
    ({"long_status": "partial"}, "COMPOSED_FACT_COMPONENT_NOT_USABLE"),
])
def test_composed_debt_stays_unbound_without_exact_linkage(kwargs, outcome):
    rows, summary = scaleout.bind_composed_fact_lineage(debt_rows(**kwargs))
    assert summary["outcomes"] == {outcome: 1}
    composed = next(row for row in rows if row["canonical_metric"] == "total_interest_bearing_debt")
    assert composed["lineage_complete"] is False and composed["source_lineage"]["provider"] is None
    _, record = build(debt_rows(**kwargs))
    assert record["features"]["debt_to_equity"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_composed_scope_must_match_its_components():
    rows = debt_rows()
    next(row for row in rows if row["canonical_metric"] == "total_interest_bearing_debt")["statement_scope"] = "unknown"
    assert scaleout.bind_composed_fact_lineage(rows)[1]["outcomes"] == {"COMPOSED_FACT_REPRESENTATION_DIFFERS_FROM_COMPONENTS": 1}


def test_composed_binding_never_touches_non_composed_rows():
    rows = debt_rows()
    bound, _ = scaleout.bind_composed_fact_lineage(rows)
    assert [row for row in bound if row["canonical_metric"] != "total_interest_bearing_debt"] == \
           [row for row in rows if row["canonical_metric"] != "total_interest_bearing_debt"]


# -- Entity applicability --------------------------------------------------------------------------

@pytest.mark.parametrize("entity", ["bank", "securities", "insurance", "finance_company", "unknown"])
def test_financial_entities_never_receive_industrial_margin_fcf_or_leverage(entity):
    rows = [sem("revenue", 1000), sem("gross_profit", 300), *debt_rows()]
    _, record = build(rows, entity=entity)
    for feature in ("gross_margin", "free_cash_flow_proxy", "debt_to_equity", "debt_to_assets"):
        assert record["features"][feature]["fitness"] == "NOT_APPLICABLE"


# -- Period semantics and blocked features ---------------------------------------------------------

def test_no_ytd_rows_keeps_ytd_growth_blocked_and_no_ttm_is_manufactured():
    rows = [sem("revenue", 100, "2025-Q1"), sem("revenue", 120, "2026-Q1"), sem("net_income", 10, "2026-Q1")]
    _, record = build(rows)
    assert record["features"]["revenue_ytd_yoy"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert record["features"]["revenue_ttm"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert record["features"]["revenue_same_quarter_yoy"]["fitness"] == "READY"


# -- Freshness -------------------------------------------------------------------------------------

@pytest.mark.parametrize("period,status,lag,behind,reason", [
    ("2026-Q2", CURRENT, 1, 0, None),
    ("2025-Q3", CURRENT, 4, 3, None),
    ("2025-Q2", STALE_BUT_RESEARCH_USABLE, 5, 4, "FINANCIAL_PERIOD_BEYOND_MAXIMUM_COMPLETED_QUARTER_LAG"),
    ("2016-Q3", STALE_BUT_RESEARCH_USABLE, 40, 39, "FINANCIAL_PERIOD_BEYOND_MAXIMUM_COMPLETED_QUARTER_LAG"),
    ("2026-Q3", UNAVAILABLE, None, None, "FINANCIAL_PERIOD_AFTER_DECISION_SESSION"),
    ("2025-FY", UNAVAILABLE, None, None, "FINANCIAL_SOURCE_PERIOD_UNRESOLVED"),
    (None, UNAVAILABLE, None, None, "FINANCIAL_SOURCE_PERIOD_ABSENT"),
])
def test_financial_period_freshness_uses_the_governed_completed_quarter_window(period, status, lag, behind, reason):
    envelope = classify_financial_period_freshness(source_period=period, decision_session=SESSION, maximum_completed_quarter_lag=4)
    assert (envelope["freshness_status"], envelope["completed_quarter_lag"], envelope["quarters_behind_last_completed_quarter"]) == (status, lag, behind)
    assert envelope["reason_codes"] == ([reason] if reason else [])
    assert envelope["rewritten_as_current"] is False


def test_readiness_period_blocker_is_unchanged_after_delegation():
    def legacy(period, session):
        match = re.fullmatch(r"(\d{4})-Q([1-4])", str(period or ""))
        if not match:
            return "CALCULATION_READINESS_PERIOD_UNRESOLVED"
        index = int(match[1]) * 4 + int(match[2])
        day = date.fromisoformat(session)
        quarter = (day.month - 1) // 3 + 1
        session_index = day.year * 4 + quarter
        last = session_index if day >= date(day.year, quarter * 3, calendar.monthrange(day.year, quarter * 3)[1]) else session_index - 1
        if index > last:
            return "CALCULATION_READINESS_PERIOD_AFTER_DECISION_SESSION"
        return "CALCULATION_READINESS_PERIOD_STALE" if session_index - index > 4 else None
    for session in ("2026-09-24", "2026-09-30", "2026-12-31", "2027-01-02"):
        for period in [f"{y}-Q{q}" for y in range(2024, 2028) for q in range(1, 5)] + ["2026", None, "bad"]:
            assert valuation.readiness_period_blocker(period, session) == legacy(period, session)


def test_stale_valid_fundamental_evidence_is_labelled_not_dropped():
    record = {"fundamental_state": "STABLE", "evidence_axes": {"FUNDAMENTAL": {"method": "financial_analysis_product_integration/v1"}}}
    financial = {"status": "AVAILABLE", "current_research_ready": True, "as_of_financial_period": "2016-Q3",
                 "feature_fitness": {"net_margin": {"fitness": "READY", "reason_codes": [], "as_of_period": "2016-Q3"},
                                     "gross_margin": {"fitness": "BLOCKED_BY_EVIDENCE", "reason_codes": ["X"]}}}
    dimension = decision_input._fundamental(record, financial, None, {"applicability_status": "RESOLVED"}, SESSION)
    assert dimension["state"] == "AVAILABLE" and dimension["metrics"]["qualified"] == ["net_margin"]
    assert dimension["freshness"]["freshness_status"] == STALE_BUT_RESEARCH_USABLE
    assert dimension["freshness"]["source_period"] == "2016-Q3"
    assert dimension["freshness"]["stale_but_research_usable_metrics"] == ["net_margin"]
    current = deepcopy(financial)
    current["as_of_financial_period"] = "2026-Q1"
    current["feature_fitness"]["net_margin"]["as_of_period"] = "2026-Q1"
    fresh = decision_input._fundamental(record, current, None, {"applicability_status": "RESOLVED"}, SESSION)
    assert fresh["freshness"]["freshness_status"] == CURRENT and fresh["freshness"]["stale_but_research_usable_metrics"] == []


def test_compact_feature_fitness_names_each_computed_feature_period():
    artifact, _ = build([sem("revenue", 1000), sem("gross_profit", 300)])
    import stocklookup_core.financial.financial_analysis_product_projection as projection
    compact = projection.build_product_projection(financial_context=artifact, product_tickers=["AAA"], requested_at="t")
    fitness = compact["records"]["AAA"]["feature_fitness"]
    assert fitness["gross_margin"]["as_of_period"] == "2026-Q1"
    assert "as_of_period" not in fitness["debt_to_equity"]


def test_decision_input_coverage_names_its_denominator():
    coverage = decision_input.coverage({"AAA": {"current_research_decision_input": {}}})
    assert coverage["denominator"] == "ATTEMPTED_COHORT" and coverage["denominator_count"] == 1


# -- Peer statement scope and P/B regression -------------------------------------------------------

def _pb(scope: str) -> dict:
    envelope = basis.build_basis(currency="VND", scale="units", basis_source="DNSE contract * shares",
                                 basis_status=basis.RESEARCH_CONTRACT_QUALIFIED, multiplier_to_vnd=1, normalized_unit="VND")
    equity = {"ticker": "AAA", "canonical_metric": "shareholders_equity", "native_period_label": "2026-Q1", "period_end": "2026-03-31",
              "period_semantic_state": "POINT_IN_TIME_BALANCE_SHEET", "reported_value": 1_000_000, "source_status": "provider_reported",
              "lineage_complete": True, "source_conflicts": [], "statement_scope": scope,
              "source_lineage": {"provider": "VCI", "source_file": "AAA_balance_sheet_quarter.parquet", "source_sha256": "fixture"}}
    return valuation._book_value_method(ticker="AAA", entity="corporate", share_class="CURRENT_SHARE_RESEARCH_PROXY",
                                        market_cap={"status": "RESEARCH_USABLE", "value": 2_000_000, "monetary_basis": envelope},
                                        equity_rows=[equity], decision_session=SESSION, verdict=pin.resolve(ROOT))


def test_unknown_statement_scope_pb_is_research_usable_but_not_peer_comparable():
    rows = {}
    for scope in ("consolidated", "unknown"):
        method = _pb(scope)
        assert method["status"] == "RESEARCH_USABLE" and "NCI_NOT_DEDUCTED" in method["limitations"]
        for i in range(6):
            rows[f"{scope[:1].upper()}{i}"] = {"entity_class": "corporate", "usable_relative_method_count": 1,
                                                "methods": {valuation.PB_CURRENT_RESEARCH: {**method, "value": i + 1}}}
    peers = valuation.attach_peer_relative(deepcopy(rows))
    consolidated = peers["C0"]["peer_relative"][valuation.PB_CURRENT_RESEARCH]
    unknown = peers["U0"]["peer_relative"][valuation.PB_CURRENT_RESEARCH]
    assert consolidated["status"] == "READY_RESEARCH_ONLY" and consolidated["peer_count"] == 6
    assert unknown["status"] == "NOT_COMPARABLE" and unknown["reason"] == valuation.SCOPE_NOT_PEER_COMPARABLE
    assert peers["U0"]["relative_research_state"] == "ABSOLUTE_RESEARCH_ONLY"
    assert peers["U0"]["methods"][valuation.PB_CURRENT_RESEARCH] == rows["U0"]["methods"][valuation.PB_CURRENT_RESEARCH]


def test_engine_fundamental_peers_exclude_unproven_statement_scope():
    records = {}
    for scope in ("consolidated", "unknown"):
        for i in range(6):
            rows = [sem("revenue", 1000, scope=scope, ticker=f"{scope[0]}{i}"), sem("net_income", 10 * (i + 1), scope=scope, ticker=f"{scope[0]}{i}")]
            records[f"{scope[0]}{i}"] = engine.build_ticker_context(f"{scope[0]}{i}", rows, issuer_type="corporate", source_identities={})
    peers = valuation.attach_engine_fundamental_peers(records)
    assert peers["c0"]["net_margin"]["status"] == "READY_RESEARCH_ONLY"
    assert peers["u0"]["net_margin"] == {**peers["u0"]["net_margin"], "status": "NOT_COMPARABLE",
                                         "reason": [valuation.SCOPE_NOT_PEER_COMPARABLE]}
