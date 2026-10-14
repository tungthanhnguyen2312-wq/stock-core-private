"""Refusal and preservation tests for the disjoint offline acceptance runner."""
from copy import deepcopy
import csv
import json

import pytest

from tools import validate_producer_financial_home_completion as validation


def operands():
    sha = "a" * 64
    asset = {"canonical_metric": "total_assets", "reporting_period": "2026-H1",
             "currency": "VND", "unit_scale": 1_000_000,
             "source_lineage": {"document_sha256": sha,
                                "statement_scope_evidence": {"statement_scope": "consolidated"}}}
    income = {"canonical_metric": "net_income", "document_sha256": sha, "statement_scope": "consolidated",
              "currency": "VND", "source_unit_scale": 1_000_000, "unit_scale": 1, "already_normalized": True,
              "reporting_period": "2026-H1", "period_start": "2026-01-01", "period_end": "2026-06-30",
              "temporal_nature": "duration", "knowledge_available_at": "2026-09-29T11:31:14Z",
              "value": 10, "citation_id": "income:test", "assurance_evidence": {"state": "QUALIFIED",
                  "document_sha256": sha, "scope_of_assurance": "consolidated_interim_statements"}}
    record = {"sha256": sha, "observed_at": "2026-09-29T11:31:14Z"}
    return asset, income, record


def test_semantic_check_never_calculates_return_or_mutates_operands():
    asset, income, record = operands()
    before = deepcopy((asset, income, record))
    result = validation.compatible_income(asset, income, record, "2026-10-14")
    assert result["calculation_performed"] is False
    assert result["historical_pit_authority"] is False
    assert result["publication_time_qualified"] is False
    assert (asset, income, record) == before


@pytest.mark.parametrize("changes,reason", [
    ({"canonical_metric": "parent_net_income"}, "ASSETS_REQUIRE_TOTAL_NET_INCOME"),
    ({"document_sha256": "b" * 64}, "INCOME_ASSETS_DOCUMENT_MISMATCH"),
    ({"statement_scope": "separate"}, "INCOME_ASSETS_SCOPE_MISMATCH"),
    ({"currency": "USD"}, "INCOME_ASSETS_CURRENCY_SCALE_MISMATCH"),
    ({"source_unit_scale": 1}, "INCOME_ASSETS_CURRENCY_SCALE_MISMATCH"),
    ({"already_normalized": False}, "INCOME_ASSETS_CURRENCY_SCALE_MISMATCH"),
    ({"period_end": "2026-12-31"}, "INCOME_ASSETS_PERIOD_MISMATCH"),
    ({"temporal_nature": "instant"}, "INCOME_ASSETS_PERIOD_MISMATCH"),
    ({"knowledge_available_at": "2026-10-15T11:31:14Z"}, "INPUT_NOT_KNOWN_BY_SESSION"),
    ({"assurance_evidence": {}}, "SAME_DOCUMENT_CONSOLIDATED_ASSURANCE_REQUIRED"),
])
def test_incompatible_income_refused(changes, reason):
    asset, income, record = operands()
    income.update(changes)
    with pytest.raises(ValueError, match=reason):
        validation.compatible_income(asset, income, record, "2026-10-14")


def test_known_later_fact_refused_at_earlier_session():
    with pytest.raises(ValueError, match="INPUT_NOT_KNOWN_BY_SESSION"):
        validation.compatible_income(*operands(), "2026-09-28")


def test_snapshot_detects_same_size_byte_change(tmp_path):
    path = tmp_path / "sealed.json"
    path.write_bytes(b'{"x":1}')
    before = validation.snapshot([path])
    path.write_bytes(b'{"x":2}')
    with pytest.raises(ValueError, match="PROTECTED_INPUT_CHANGED"):
        validation.compare_snapshot(before)


def test_snapshot_detects_missing_protected_file(tmp_path):
    path = tmp_path / "sealed.json"
    path.write_bytes(b"original")
    before = validation.snapshot([path])
    path.unlink()
    with pytest.raises(FileNotFoundError):
        validation.compare_snapshot(before)


def test_output_never_overwrites_existing_or_source_tree(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for output in (source, source / "generated", tmp_path):
        with pytest.raises(ValueError, match="OUTPUT_OVERLAPS_INPUT"):
            validation.check_output(output, [source])
    old = tmp_path / "old-report"
    old.mkdir()
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        validation.check_output(old, [source])


def test_relative_source_path_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="INPUT_PATH_ESCAPES_ROOT"):
        validation.safe_input(tmp_path, "../outside.pdf")


def test_coverage_counts_zero_value_and_preserves_refusals(tmp_path):
    path = tmp_path / "matrix.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["ticker", "metric", "value", "fitness", "blockers"])
        writer.writeheader()
        writer.writerows([
            {"ticker": "A", "metric": "ROA", "value": "0.0", "fitness": "RESEARCH_PROXY", "blockers": "[]"},
            {"ticker": "B", "metric": "ROA", "value": "", "fitness": "BLOCKED_BY_EVIDENCE",
             "blockers": json.dumps(["MISSING_ASSETS", "SCOPE_MISMATCH"])},
        ])
    result = validation.coverage(path)["ROA"]
    assert result["available"] == 1
    assert result["refusal_reasons"] == {"MISSING_ASSETS": 1, "SCOPE_MISMATCH": 1}


def test_duplicate_matrix_rows_refused(tmp_path):
    path = tmp_path / "matrix.csv"
    path.write_text("ticker,metric,value,fitness,blockers\nA,ROA,,BLOCKED,[]\nA,ROA,,BLOCKED,[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_METRIC_ROW"):
        validation.coverage(path)


def card_fixture():
    import dashboard_home_summary as home
    cards = {ticker: {"ticker": ticker, "as_of_session": "2026-10-14",
                       "research_action_posture": "EARLY_WATCH", "entry_state": "BASE_BUILDING",
                       "evidence_currency": "CURRENT_SESSION", "position_context": {"status": "UNKNOWN"},
                       "why": {"deterministic_reasons": [ticker + ":retained"]},
                       "reference_trigger": {"trigger_level": None}, "counter_thesis": {"key_counter_thesis": []}}
             for ticker in ("Z", "B", "A", "D", "E")}
    index = {"contract_version": "workspace_index/v1", "as_of_session": "2026-10-14",
             "source_artifact_identity": "workspace:test", "cards": cards}
    summary = {"as_of_session": "2026-10-14", "notable_cards": {
        "contract_version": "dashboard_home_notable_cards/v1", "as_of_session": "2026-10-14",
        "source_contract_version": "workspace_index/v1", "source_artifact_identity": "workspace:test",
        "selection": "PUBLISHED_INSERTION_ORDER_NOTABLE_MEMBERSHIP_V1", "selection_limit": 4,
        "cards": [deepcopy(cards[t]) for t in ("Z", "B", "A", "D")]}}
    summary.update(home.content_identity(summary))
    return summary, index


def test_card_audit_uses_insertion_order_and_all_nine_fields():
    summary, index = card_fixture()
    assert validation.card_parity(summary, index) == ["Z", "B", "A", "D"]


@pytest.mark.parametrize("defect,reason", [
    ("reason", "VERBATIM_CARD_ORDER_OR_FIELD_MISMATCH"),
    ("order", "VERBATIM_CARD_ORDER_OR_FIELD_MISMATCH"),
    ("source", "CARD_SOURCE_BINDING_MISMATCH"),
    ("selection", "CARD_CONTRACT_MISMATCH"),
])
def test_card_audit_rejects_rehashed_semantic_tampering(defect, reason):
    import dashboard_home_summary as home
    summary, index = card_fixture()
    block = summary["notable_cards"]
    if defect == "reason":
        block["cards"][0]["why"]["deterministic_reasons"] = ["invented"]
    elif defect == "order":
        block["cards"].reverse()
    elif defect == "source":
        block["source_artifact_identity"] = "workspace:other"
    else:
        block["selection_limit"] = 5
    summary.update(home.content_identity(summary))
    with pytest.raises(ValueError, match=reason):
        validation.card_parity(summary, index)
