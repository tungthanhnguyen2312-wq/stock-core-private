"""KBS payloads with repeated period heads never supply standalone-quarter flows."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from stocklookup_core.financial import financial_flow_semantics_ttm_bridge as bridge


def row(ticker, label, metric="revenue", *, conflict=False, source_file=None, provider="KBS", family="income_statement",
        state="STANDALONE_QUARTER"):
    return {"ticker": ticker, "canonical_metric": metric, "native_period_label": label, "statement_family": family,
            "period_semantic_state": state, "research_semantic_state": "RESEARCH_SEMANTIC_READY", "metric_nature": "FLOW_DURATION",
            "normalized_candidate_value": 1.0, "blocker_reason_codes": [],
            "source_conflicts": [{"kind": "restated_period_column_disagrees", "period_variant_index": 1}] if conflict else [],
            "source_lineage": {"provider": provider, "source_file": source_file or f"{ticker}_income_statement_quarter.parquet"}}


def test_every_column_of_a_duplicate_head_payload_loses_its_duration_claim_but_keeps_values():
    rows = [row("HPG", "2026-Q1"), row("HPG", "2025-Q4", conflict=True), row("HPG", "2025-Q3", "net_income"),
            row("FPT", "2026-Q1"), row("FPT", "2025-Q4")]
    saved = copy.deepcopy(rows)
    gated, summary = bridge.gate_kbs_period_alignment(rows)
    assert rows == saved  # retained facts are not mutated
    hpg = [r for r in gated if r["ticker"] == "HPG"]
    assert all(r["period_semantic_state"] == "UNKNOWN_DURATION" for r in hpg)
    assert all(bridge.KBS_PERIOD_ALIGNMENT_BLOCKER in r["blocker_reason_codes"] for r in hpg)
    assert all(r["period_alignment_gate"]["original_period_semantic_state"] == "STANDALONE_QUARTER" for r in hpg)
    assert [r["normalized_candidate_value"] for r in hpg] == [1.0, 1.0, 1.0]
    assert all(r["period_semantic_state"] == "STANDALONE_QUARTER" for r in gated if r["ticker"] == "FPT")
    assert summary["misaligned_tickers"] == ["HPG"] and summary["gated_rows_by_metric"] == {"net_income": 1, "revenue": 2}


def test_other_providers_families_and_payload_files_are_untouched():
    rows = [row("HPG", "2025-Q4", conflict=True, source_file="HPG_income_statement_quarter.parquet"),
            row("HPG", "2026-Q1", source_file="HPG_other_payload.parquet"),
            row("HPG", "2026-Q1", "cash_and_cash_equivalents", family="balance_sheet", state="POINT_IN_TIME_BALANCE_SHEET"),
            row("HPG", "2026-Q1", "operating_cash_flow", family="cash_flow"),
            row("VNM", "2025-Q4", conflict=True, provider="VCI", state="UNKNOWN_DURATION")]
    gated, summary = bridge.gate_kbs_period_alignment(rows)
    assert [r["period_semantic_state"] for r in gated] == ["UNKNOWN_DURATION", "STANDALONE_QUARTER", "POINT_IN_TIME_BALANCE_SHEET",
                                                         "STANDALONE_QUARTER", "UNKNOWN_DURATION"]
    assert summary["misaligned_payloads"] == 1


def test_gated_flows_cannot_build_quarters_or_ttm():
    facts = {"HPG": [row("HPG", q, conflict=(q == "2025-Q4")) for q in ("2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1")]}
    gated, _ = bridge.gate_kbs_period_alignment(facts["HPG"])
    assert all(r["period_semantic_state"] != "STANDALONE_QUARTER" for r in gated)
    assert not any(r["period_semantic_state"] == "STANDALONE_QUARTER" for r in gated if r["canonical_metric"] == "revenue")


def test_scaleout_adapters_and_feature_store_cannot_restore_tainted_flows():
    from stocklookup_core.financial import market_wide_financial_analysis_v2_scaleout as scaleout
    from tests.test_market_wide_financial_analysis_v2_scaleout import _semantic_row, _store
    rows = [_semantic_row(metric, value, label) for label in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")
            for metric, value in (("revenue", 100), ("net_income", 10))]
    for r in rows:
        r["qualified_normalized_period"] = r["native_period_label"]
        r["period_normalization"] = "EXISTING_NORMALIZATION_MUST_NOT_BYPASS_GATE"
    store = {"AAA": _store()}
    stale = scaleout.build_qualified_flow_artifact(semantic_rows=rows, feature_records=store, requested_at="t")
    rows[0]["source_conflicts"] = [{"kind": "restated_period_column_disagrees"}]
    original = copy.deepcopy(rows)
    qualified = scaleout.build_qualified_flow_artifact(semantic_rows=rows, feature_records=store, requested_at="t")
    assert qualified["records"]["AAA"]["ttm"] == {}
    assert qualified["records"]["AAA"]["standalone_quarters"] == []
    for artifact in (None, qualified):
        result = scaleout.build_scaleout(semantic_rows=rows, feature_records=store,
            feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1",
            requested_at="t", qualified_flow_artifact=artifact)
        for feature in ("net_margin", "net_income_sign", "revenue_ttm", "net_income_ttm", "same_provider_roe", "mixed_provider_roa_proxy"):
            assert result["records"]["AAA"]["features"][feature]["value"] is None
    with pytest.raises(scaleout.FinancialAnalysisScaleoutError, match="QUALIFIED_FLOW_RETAINS_MISALIGNED"):
        scaleout.build_scaleout(semantic_rows=rows, feature_records=store,
            feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1",
            requested_at="t", qualified_flow_artifact=stale)
    gated, _ = bridge.gate_kbs_period_alignment(rows)
    assert bridge.gate_kbs_period_alignment(gated)[0] == gated
    adapted = bridge.facts_from_structured_semantic_rows(gated)["AAA"]
    assert all(bridge.flow_semantics(f)["reason"] == bridge.KBS_PERIOD_ALIGNMENT_BLOCKER for f in adapted)
    assert rows == original


def test_taint_has_precedence_over_explicit_flow_basis_and_proven_hpg_normalization():
    facts = [{"ticker": "HPG", "provider": "KBS", "statement_family": "income_statement",
              "canonical_metric": "revenue", "reporting_period": label, "value": value,
              "ttm_blocker": bridge.KBS_PERIOD_ALIGNMENT_BLOCKER, "flow_period_basis": "STANDALONE_QUARTER"}
             for label, value in zip(bridge.HPG_KBS_FY2025_RAW_TO_NORMALIZED, (1, 2, 3, 156116094618476))]
    assert all(not f.get("qualified_normalized_period") for f in bridge.qualify_proven_kbs_income_period(facts))
    assert all(bridge.flow_semantics(f)["flow_period_basis"] == "UNKNOWN" for f in facts)


@pytest.mark.retained_evidence("operations-review/market-wide-structured-financial-period-semantics-v1-20260905",
                               "operations-review/market-wide-fundamental-feature-store-v1-20260831",
                               "operations-review/market-wide-financial-entity-classification-scaleout-v1-20260901")
def test_retained_kbs_payload_gate_and_scaleout_acceptance_preserve_pinned_evidence():
    from stocklookup_core.financial import financial_v2_current_input_authority as authority
    from stocklookup_core.financial import market_wide_financial_analysis_v2_scaleout as scaleout
    from tests.test_market_wide_financial_analysis_v2_scaleout import _store
    pin = authority.resolve(Path(__file__).resolve().parents[1])
    before = hashlib.sha256(pin.semantics_facts_path.read_bytes()).hexdigest()
    with gzip.open(pin.semantics_facts_path, "rt", encoding="utf-8") as handle:
        raw = [json.loads(line) for line in handle if line.strip()]
    gated, summary = bridge.gate_kbs_period_alignment(raw)
    assert len(raw) == len(gated) == 261360
    assert summary["misaligned_payloads"] == 1114
    assert sum(summary["gated_rows_by_metric"].values()) == 18869
    assert {"HPG", "NVL", "PVD"}.issubset(summary["misaligned_tickers"])
    bad = bridge.misaligned_kbs_income_payloads(raw)
    for original, qualified in zip(raw, gated):
        assert original.get("reported_value") == qualified.get("reported_value")
        assert original.get("source_lineage") == qualified.get("source_lineage")
        if bridge._kbs_income_payload(original) not in bad:
            assert original == qualified
    tickers = {"HPG", "NVL", "PVD"}
    subset = [r for r in raw if r.get("ticker") in tickers and r.get("statement_family") == "income_statement"]
    records = {ticker: _store(ticker) for ticker in tickers}
    flow = scaleout.build_qualified_flow_artifact(semantic_rows=subset, feature_records=records, requested_at="retained-acceptance")
    result = scaleout.build_scaleout(semantic_rows=subset, feature_records=records, feature_store_artifact={"artifact_identity": "fixture"},
        period_semantics_identity=pin.expected_semantics_identity, requested_at="retained-acceptance", qualified_flow_artifact=flow)
    for ticker in tickers:
        assert flow["records"][ticker]["ttm"] == {}
        for feature in ("net_income_sign", "net_margin", "revenue_ttm", "net_income_ttm", "same_provider_roe"):
            assert result["records"][ticker]["features"][feature]["value"] is None
    assert hashlib.sha256(pin.semantics_facts_path.read_bytes()).hexdigest() == before
