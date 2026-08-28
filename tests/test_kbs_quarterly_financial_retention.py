from __future__ import annotations

import kbs_quarterly_financial_retention as kbs
import financial_flow_semantics_ttm_bridge as bridge


def _request(page: int = 1) -> dict:
    return kbs.plan_for_tickers(["AAA"])[page - 1]


def _head(year: int, quarter: int, *, united: str = "HN", currency: str | None = "VND") -> dict:
    row = {"YearPeriod": year, "TermName": f"Quý {quarter}", "TermNameEN": f"Quarter {quarter}",
           "PeriodBegin": f"{year}-{(quarter - 1) * 3 + 1:02d}-01",
           "PeriodEnd": f"{year}-{quarter * 3:02d}-28", "United": united,
           "ReportDate": f"{year}-04-01", "LastUpdate": f"{year}-04-02", "AuditedStatus": "A"}
    if currency is not None:
        row["Currency"] = currency
    return row


def _raw(heads: list[dict]) -> dict:
    return {"Unit": [{"UnitedCode": "HN", "UnitedName": "Hợp nhất"},
                     {"UnitedCode": "RL", "UnitedName": "Riêng lẻ"}],
            "Head": heads, "Content": {"Kết quả kinh doanh": []}}


def test_two_eight_period_pages_are_requested_but_not_presumed_distinct() -> None:
    plan = kbs.plan_for_tickers(kbs.PROOF_TICKERS)
    assert len(plan) == 10
    assert {row["params"]["pageSize"] for row in plan} == {8}
    assert {row["params"]["page"] for row in plan} == {1, 2}


def test_duplicate_provider_periods_do_not_count_as_distinct_quarters() -> None:
    heads = [_head(2025, q) for q in range(1, 5)] + [_head(2024, q) for q in range(1, 4)] + [_head(2025, 4)]
    metadata = kbs.metadata_rows(_request(), _raw(heads), raw_hash="raw")
    variants = kbs.classify_period_variants(metadata)
    summary = kbs.coverage(metadata, variants)
    assert len(metadata) == 8
    assert summary["distinct_quarters_by_ticker"]["AAA"] == 7
    assert summary["variant_dispositions"]["RESTATEMENT_VARIANTS_RETAINED"] == 1


def test_explicit_metadata_is_retained_and_normalized_without_value_inference() -> None:
    row = kbs.metadata_rows(_request(), _raw([_head(2025, 1)]), raw_hash="raw")[0]
    assert row["period_start"] == "2025-01-01"
    assert row["duration_months"] == 3
    assert row["flow_period_basis"] == "STANDALONE_QUARTER"
    assert row["statement_scope"] == "CONSOLIDATED"
    assert row["currency"] == "VND"
    assert row["unit_scale_factor"] == 1
    assert row["normalized_monetary_basis"] == "BASE_VND"


def test_missing_currency_and_unrecognized_scope_remain_unknown() -> None:
    row = kbs.metadata_rows(_request(), _raw([_head(2025, 1, united="X", currency=None)]), raw_hash="raw")[0]
    assert row["statement_scope"] == "UNKNOWN"
    assert row["currency"] == "UNKNOWN"
    assert row["normalized_monetary_basis"] == "UNKNOWN"


def test_compact_provider_period_bounds_remain_raw_when_calendar_alignment_is_not_proven() -> None:
    head = _head(2025, 1)
    head["PeriodBegin"], head["PeriodEnd"] = "202501", "202503"
    row = kbs.metadata_rows(_request(), _raw([head]), raw_hash="raw")[0]
    assert row["period_start"] is None
    assert row["period_end"] is None
    assert row["duration_months"] is None
    assert row["raw_head_fields"]["PeriodBegin"] == "202501"


def test_explicit_parent_scope_is_not_inferred_from_minority_interest() -> None:
    row = kbs.metadata_rows(_request(), _raw([_head(2025, 1, united="RL")]), raw_hash="raw")[0]
    assert row["statement_scope"] == "STANDALONE_PARENT"
    assert "minority" not in kbs.__file__.lower()


def test_equal_and_conflicting_restatement_values_are_both_explicit() -> None:
    base = {"ticker": "AAA", "raw_item_id": "revenue", "reporting_period": "2025-Q4"}
    equal = kbs.reconcile_value_variants([{**base, "period_variant_index": 0, "observation_id": "a", "raw_value": 1},
                                           {**base, "period_variant_index": 1, "observation_id": "b", "raw_value": 1}])
    conflict = kbs.reconcile_value_variants([{**base, "period_variant_index": 0, "observation_id": "a", "raw_value": 1},
                                              {**base, "period_variant_index": 1, "observation_id": "b", "raw_value": 2}])
    assert equal[0]["disposition"] == "EQUAL_RESTATEMENT_VARIANTS"
    assert conflict[0]["disposition"] == "CONFLICTING_RESTATEMENT_VARIANTS"


def test_kbs_contract_does_not_broaden_vci_duration() -> None:
    fact = {"ticker": "AAA", "canonical_metric": "revenue", "provider": "VCI",
            "statement_family": "income_statement", "reporting_period": "2025-Q1", "status": "provider_reported",
            "value": 1, "statement_scope": "UNKNOWN", "currency": "unknown", "scale": "unknown"}
    assert bridge.flow_semantics(fact)["flow_period_basis"] == "UNKNOWN"


def test_deepened_kbs_fixture_unlocks_rolling_four_quarters_but_ctd_missing_data_does_not() -> None:
    def fact(period: str, value: int) -> dict:
        return {"ticker": "CMG", "canonical_metric": "revenue", "provider": "KBS",
                "statement_family": "income_statement", "reporting_period": period, "period_type": "quarterly",
                "flow_period_basis": "STANDALONE_QUARTER", "value": value, "status": "provider_reported",
                "statement_scope": "CONSOLIDATED", "currency": "unknown", "scale": 1}
    unlocked = bridge.build_ticker_record(ticker="CMG", entity_type="corporate",
                                           facts=[fact(f"2025-Q{q}", q) for q in range(1, 5)])
    blocked = bridge.build_ticker_record(ticker="CTD", entity_type="corporate",
                                          facts=[fact(f"2025-Q{q}", q) for q in range(1, 4)])
    assert unlocked["ttm"]["revenue"]["value"] == 10.0
    assert blocked["status"] == "BLOCKED"
