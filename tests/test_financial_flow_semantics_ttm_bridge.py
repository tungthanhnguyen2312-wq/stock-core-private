from __future__ import annotations

import financial_flow_semantics_ttm_bridge as bridge


def _fact(period: str, value: float, *, provider: str = "KBS", metric: str = "revenue",
          basis: str | None = None, family: str = "income_statement") -> dict:
    fact = {
        "ticker": "AAA", "canonical_metric": metric, "provider": provider,
        "statement_family": family, "reporting_period": period, "period_type": "quarterly",
        "value": value, "status": "provider_reported", "statement_scope": "consolidated",
        "currency": "unknown", "scale": "unknown", "source_sha256": "source-1", "fact_id": period,
    }
    if basis:
        fact["flow_period_basis"] = basis
    return fact


def test_kbs_income_statement_contract_is_direct_standalone_quarter() -> None:
    fact = _fact("2025-Q2", 20)
    semantic = bridge.flow_semantics(fact)
    assert semantic["flow_period_basis"] == "STANDALONE_QUARTER"
    assert semantic["method"] == "DIRECT_KBS_KQKD_QUARTER"
    assert semantic["duration_months"] == 3
    assert fact["period_type"] == "quarterly"  # no repurposing of the existing field


def test_explicit_raw_flow_metadata_propagates_without_guessing() -> None:
    fact = _fact("2025-Q2", 20, provider="TEST", basis="CUMULATIVE_YTD")
    fact["flow_period_basis_evidence"] = "raw_header_duration"
    fact["duration_months"] = 6
    semantic = bridge.flow_semantics(fact)
    assert semantic["flow_period_basis"] == "CUMULATIVE_YTD"
    assert semantic["duration_months"] == 6
    assert semantic["evidence"] == "raw_header_duration"


def test_vci_quarter_label_alone_remains_unknown() -> None:
    semantic = bridge.flow_semantics(_fact("2025-Q2", 20, provider="VCI"))
    assert semantic["flow_period_basis"] == "UNKNOWN"
    assert semantic["reason"] == "VCI_PERIOD_DURATION_REMAINS_UNKNOWN"


def test_vci_period_metadata_cannot_be_repurposed_as_duration_proof() -> None:
    fact = _fact("2025-Q2", 20, provider="VCI")
    fact.update({"flow_period_basis": "STANDALONE_QUARTER", "yearReport": 2025, "lengthReport": 3})
    semantic = bridge.flow_semantics(fact)
    assert semantic["flow_period_basis"] == "UNKNOWN"
    assert semantic["reason"] == "VCI_PERIOD_DURATION_REMAINS_UNKNOWN"


def test_vci_ocf_needs_the_existing_resolver_then_is_accepted() -> None:
    fact = _fact("2025-Q2", 20, provider="VCI", metric="operating_cash_flow", family="cash_flow")
    assert bridge.flow_semantics(fact)["reason"] == "VCI_OPERATING_CASH_FLOW_RESOLVER_EVIDENCE_REQUIRED"
    fact.update({"cumulative_state": "period_only", "period_start": "2025-04-01", "period_end": "2025-06-30"})
    semantic = bridge.flow_semantics(fact)
    assert semantic["flow_period_basis"] == "STANDALONE_QUARTER"
    assert semantic["method"] == "DIRECT_RETAINED_CASH_FLOW_RESOLVER"


def test_exact_ytd_subtractions_construct_q1_to_q4_and_ttm() -> None:
    facts = [
        _fact("2025-Q1", 10, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q2", 30, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q3", 60, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-FY", 100, provider="TEST", basis="FULL_YEAR"),
    ]
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    quarters = record["standalone_quarters"]
    assert [row["value"] for row in quarters] == [10.0, 20.0, 30.0, 40.0]
    assert [row["derivation_method"] for row in quarters] == [
        "Q1_YTD_AS_Q1_STANDALONE", "Q2_YTD_MINUS_Q1_YTD", "Q3_YTD_MINUS_H1_YTD",
        "Q4_FULL_YEAR_MINUS_9M_YTD",
    ]
    assert record["ttm"]["revenue"]["value"] == 100.0


def test_incompatible_ytd_inputs_fail_closed() -> None:
    q1 = _fact("2025-Q1", 10, provider="TEST", basis="CUMULATIVE_YTD")
    q2 = _fact("2025-Q2", 30, provider="TEST", basis="CUMULATIVE_YTD")
    q2["statement_scope"] = "separate"
    quarters, blockers = bridge.standalone_quarters([q1, q2])
    assert len(quarters) == 1
    assert blockers["YTD_SUBTRACTION_INPUTS_INCOMPATIBLE_OR_MISSING"] == 1


def test_ytd_bridge_requires_matching_same_period_and_uses_formula() -> None:
    facts = [
        _fact("2026-Q2", 30, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q2", 20, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-FY", 100, provider="TEST", basis="FULL_YEAR"),
    ]
    bridge_ttm = bridge.ytd_bridge_ttm(facts)["revenue"]
    assert bridge_ttm["value"] == 110.0
    assert bridge_ttm["method"] == "TTM_YTD_BRIDGE"


def test_ytd_bridge_does_not_use_mismatched_prior_period() -> None:
    facts = [
        _fact("2026-Q2", 30, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q3", 20, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-FY", 100, provider="TEST", basis="FULL_YEAR"),
    ]
    assert bridge.ytd_bridge_ttm(facts) == {}


def test_rolling_and_ytd_bridge_agree_for_equivalent_fixture() -> None:
    rolling = [_fact(f"2026-Q{q}", 25, provider="TEST", basis="STANDALONE_QUARTER") for q in range(1, 5)]
    bridged = [
        _fact("2026-Q2", 50, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q2", 50, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-FY", 100, provider="TEST", basis="FULL_YEAR"),
    ]
    rolling_value = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=rolling)["ttm"]["revenue"]["value"]
    bridge_value = bridge.ytd_bridge_ttm(bridged)["revenue"]["value"]
    assert rolling_value == bridge_value == 100.0


def test_negative_derived_quarter_is_retained() -> None:
    facts = [
        _fact("2025-Q1", 10, provider="TEST", basis="CUMULATIVE_YTD"),
        _fact("2025-Q2", 5, provider="TEST", basis="CUMULATIVE_YTD"),
    ]
    quarters, _ = bridge.standalone_quarters(facts)
    assert quarters[-1]["value"] == -5.0
    assert quarters[-1]["derived"] is True


def test_currency_or_scale_mismatch_blocks_ytd_subtraction() -> None:
    q1 = _fact("2025-Q1", 10, provider="TEST", basis="CUMULATIVE_YTD")
    q2 = _fact("2025-Q2", 20, provider="TEST", basis="CUMULATIVE_YTD")
    q2["currency"] = "VND"
    _, blockers = bridge.standalone_quarters([q1, q2])
    assert blockers["YTD_SUBTRACTION_INPUTS_INCOMPATIBLE_OR_MISSING"] == 1


def test_exact_ebitda_never_uses_a_proxy() -> None:
    facts = [_fact(f"2025-Q{q}", q) for q in range(1, 5)]
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    assert record["derived_metrics"]["ttm_ebitda"]["status"] == "BLOCKED"
    assert "EXACT_EBIT_IDENTITY_NOT_RETAINED" in record["derived_metrics"]["ttm_ebitda"]["blocker"]


def test_pbt_growth_ttm_margin_and_cfo_ni_need_matching_representation() -> None:
    facts = []
    for year, quarter in ((2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1)):
        period = f"{year}-Q{quarter}"
        facts.extend([_fact(period, 100, metric="revenue"), _fact(period, 10, metric="profit_before_tax"),
                      _fact(period, 8, metric="net_income"), _fact(period, 12, metric="operating_cash_flow", family="cash_flow")])
        facts[-1].update({"cumulative_state": "period_only", "period_start": "2025-01-01", "period_end": "2025-03-31"})
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    assert record["ttm"]["profit_before_tax"]["value"] == 40
    assert record["growth"]["profit_before_tax"]["qoq"]["status"] == "AVAILABLE"
    assert record["derived_metrics"]["ttm_pbt_margin"]["value"] == 0.1
    assert record["derived_metrics"]["ttm_cfo_to_net_income"]["value"] == 1.5


def test_missing_quarter_and_representation_mismatch_block_ttm() -> None:
    facts = [_fact("2025-Q1", 10), _fact("2025-Q2", 10), _fact("2025-Q4", 10), _fact("2026-Q1", 10)]
    facts[-1]["scale"] = "THOUSAND"
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    assert "revenue" not in record["ttm"]
    assert record["growth"]["revenue"]["qoq"]["status"] == "BLOCKED"


def test_full_universe_adapter_admits_only_qualified_rows_and_never_vci_income() -> None:
    base = {"ticker": "AAA", "canonical_metric": "revenue", "reported_value": 1, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated", "native_period_label": "2025-Q1",
            "native_period_type": "quarterly", "period_start": "2025-01-01", "period_end": "2025-03-31",
            "normalized_candidate_unit": {"currency": "VND", "scale": "ONE"}, "source_lineage": {"provider": "KBS", "source_file": "x", "source_sha256": "y", "fact_id": "z"},
            "statement_family": "income_statement"}
    vci = {**base, "ticker": "BBB", "source_lineage": {**base["source_lineage"], "provider": "VCI"}}
    bad = {**base, "ticker": "CCC", "lineage_complete": False}
    facts = bridge.facts_from_structured_semantic_rows([base, vci, bad])
    assert set(facts) == {"AAA", "BBB"}
    assert bridge.flow_semantics(facts["AAA"][0])["flow_period_basis"] == "STANDALONE_QUARTER"
    assert bridge.flow_semantics(facts["BBB"][0])["flow_period_basis"] == "UNKNOWN"


def test_non_corporate_cannot_receive_corporate_flow_metrics() -> None:
    record = bridge.build_ticker_record(ticker="VCB", entity_type="bank", facts=[_fact("2025-Q1", 1)])
    assert record["status"] == "BLOCKED"
    assert record["blocker"] == "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"


def test_content_identity_excludes_requested_at() -> None:
    payload = {"requested_at": "one", "records": {}, "coverage": {}}
    assert bridge.content_identity(payload) == bridge.content_identity({**payload, "requested_at": "two"})
