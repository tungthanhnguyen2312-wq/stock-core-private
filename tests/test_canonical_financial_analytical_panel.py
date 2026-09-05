"""Boundary tests for canonical_financial_analytical_panel/v1
(FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1).

This panel is a deterministic join over structured_financial_period_semantics.py,
bitemporal_semantic_contract.py, and financial_flow_semantics_ttm_bridge.py -- it must never
recompute what those modules already own. Fixtures here therefore build a real
structured_financial_period_semantics row rather than a hand-shaped dict, so a drift in that
module's output shape breaks this test suite instead of silently going unnoticed.
"""
from __future__ import annotations

import structured_financial_period_semantics as sem
import canonical_financial_analytical_panel as panel


def _fact(**overrides):
    row = {
        "ticker": "AAA", "canonical_metric": "revenue", "provider": "KBS",
        "statement_family": "income_statement", "statement_scope": "consolidated",
        "reporting_period": "2025-Q2", "period_type": "quarterly",
        "period_start": "2025-04-01", "period_end": "2025-06-30", "source_sha256": "a" * 64,
        "source_file": "AAA_income_statement_quarter.parquet", "fact_id": "f-1",
        "source_observation_ids": ["o-1"], "status": "provider_reported",
        "qualification_state": "provider_reported", "value": 100.0, "currency": "VND", "scale": 1,
        "observed_at": "2025-08-01T09:00:00+07:00", "conflicts": [], "warnings": [],
        "cumulative_state": "period_only",
    }
    row.update(overrides)
    return sem.project_fact(row)


def test_panel_record_never_overrides_an_existing_semantics_field():
    row = _fact()
    record = panel.build_panel_record(row)
    for key, value in row.items():
        assert record[key] == value


def test_entity_type_join_overrides_the_unset_passthrough():
    row = _fact()
    assert row.get("entity_type") is None
    record = panel.build_panel_record(row, entity_type="corporate")
    assert record["entity_type"] == "corporate"


def test_temporal_envelope_uses_flow_domain_for_income_statement():
    record = panel.build_panel_record(_fact())
    assert record["temporal_envelope"]["valid_time"]["domain"] == "FINANCIAL_FLOW_FACT"


def test_temporal_envelope_uses_stock_domain_for_balance_sheet():
    row = _fact(statement_family="balance_sheet", canonical_metric="total_assets")
    record = panel.build_panel_record(row)
    assert record["temporal_envelope"]["valid_time"]["domain"] == "FINANCIAL_STOCK_FACT"


def test_no_evidence_placeholder_resolves_knowledge_unknown_not_fabricated():
    row = _fact(status="unavailable", value=None, provider=None, source_sha256=None,
               source_observation_ids=[], observed_at=None, fact_id=None)
    record = panel.build_panel_record(row)
    assert record["temporal_envelope"]["knowledge_resolution"]["knowledge_time_status"] == "KNOWLEDGE_UNKNOWN"
    assert record["temporal_envelope"]["knowledge_resolution"]["knowledge_available_at"] is None


def test_real_observation_resolves_first_observed_conservative_knowledge():
    record = panel.build_panel_record(_fact())
    resolution = record["temporal_envelope"]["knowledge_resolution"]
    assert resolution["knowledge_time_status"] == "KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE"
    assert resolution["knowledge_available_at"] == "2025-08-01T09:00:00+07:00"


def test_feature_fitness_families_point_at_the_real_registry():
    import feature_input_fitness_contract as fitness
    record = panel.build_panel_record(_fact())
    for family in record["feature_fitness_families"]:
        fitness.describe(family)  # raises FeatureInputFitnessError if the name is unknown


def test_derived_ttm_records_are_explicitly_marked_and_linked():
    bridge_artifact = {
        "artifact_identity": "bridge:1",
        "records": {"AAA": {"ttm": {"revenue": {"value": 400.0, "source_fact_ids": ["f-1", "f-2", "f-3", "f-4"]}}}},
    }
    derived = panel.build_derived_ttm_records(bridge_artifact)
    assert len(derived) == 1
    row = derived[0]
    assert row["panel_record_kind"] == "DERIVED_TTM"
    assert row["authority_state"] == "DERIVED_PROXY_NOT_AUTHORITATIVE"
    assert row["is_actionable"] is False
    assert row["derived_from"] == ["f-1", "f-2", "f-3", "f-4"]


def test_derived_ttm_records_empty_without_a_bridge_artifact():
    assert panel.build_derived_ttm_records(None) == []
    assert panel.build_derived_ttm_records({}) == []


def test_artifact_coverage_and_deterministic_identity():
    rows = [_fact(), _fact(ticker="BBB", provider="VCI")]
    first = panel.build_artifact(semantic_rows=rows, requested_at="one")
    second = panel.build_artifact(semantic_rows=rows, requested_at="two")
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["coverage"]["record_count"] == 2
    assert first["authority_boundary"]["pit_or_raw_as_traded_promoted"] is False


def test_artifact_merges_observed_and_derived_records():
    bridge_artifact = {"artifact_identity": "bridge:1",
                       "records": {"AAA": {"ttm": {"revenue": {"value": 400.0, "source_fact_ids": ["f-1"]}}}}}
    art = panel.build_artifact(semantic_rows=[_fact()], qualified_flow_artifact=bridge_artifact, requested_at="t")
    assert art["coverage"]["kind_distribution"] == {"DERIVED_TTM": 1, "OBSERVED": 1}
