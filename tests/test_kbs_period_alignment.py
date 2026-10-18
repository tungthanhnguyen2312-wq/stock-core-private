"""KBS payloads with repeated period heads never supply standalone-quarter flows."""
import copy

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
