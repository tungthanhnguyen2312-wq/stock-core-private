from pathlib import Path
import pandas as pd

import annual_provider_financial_recovery as annual


def _frame(source="KBS", annual_value=100):
    return pd.DataFrame([{ "ticker": "AAA", "report_type": "income_statement", "source": source,
        "scraped_at": "2026-07-27 12:00", "item": "Doanh thu", "item_en": "Revenue",
        "item_id": "revenue", "2024": annual_value, "2024-Q4": 25 }])


def test_annual_payload_filter_keeps_quarterly_separate(tmp_path):
    _frame().to_parquet(tmp_path / "AAA_income_statement_year.parquet", index=False)
    _frame().to_parquet(tmp_path / "AAA_income_statement_quarter.parquet", index=False)
    assert [p.name for p in annual.annual_payload_paths(tmp_path)] == ["AAA_income_statement_year.parquet"]


def test_replay_is_deterministic_and_does_not_write_source(tmp_path):
    path = tmp_path / "AAA_income_statement_year.parquet"
    _frame().to_parquet(path, index=False)
    before = path.read_bytes()
    one = annual.replay_annual_payloads(tmp_path, official_citations={})
    two = annual.replay_annual_payloads(tmp_path, official_citations={})
    assert one["replay_identity"] == two["replay_identity"]
    assert path.read_bytes() == before
    assert all(row["reporting_period"] == "2024" for row in one["observations"])


def test_metadata_is_not_fabricated_and_provider_value_is_preserved(tmp_path):
    _frame().to_parquet(tmp_path / "AAA_income_statement_year.parquet", index=False)
    row = annual.replay_annual_payloads(tmp_path, official_citations={})["observations"][0]
    assert row["provider_native_value"] == 100
    assert row["report_date"] is None and row["audit_review_metadata"] is None
    assert row["transform_method"].startswith("vnstock_kbs")


def test_reconciliation_requires_same_year_and_known_scope():
    fact = {"ticker": "AAA", "canonical_metric": "revenue", "reporting_period": "2024",
            "provider": "KBS", "statement_family": "income_statement", "value": 100,
            "statement_scope": "unknown", "currency": "VND", "scale": "units"}
    citations = {("AAA", "revenue", "2024"): {"value": 100, "currency": "VND", "scale": "units"},
                 ("AAA", "revenue", "2023"): {"value": 90, "currency": "VND", "scale": "units"}}
    output = annual.reconcile_annual_facts([fact], citations)
    assert output["counts"]["NOT_COMPARABLE"] == 1
    assert output["counts"]["MISSING_PROVIDER_ANNUAL"] == 1
    assert output["residual_zero"]


def test_request_plan_is_bounded_distinct_and_has_no_retry_contract():
    plan = annual.request_plan(["BBB", "AAA", "AAA"])
    assert len(plan) == 6
    assert [(x["ticker"], x["statement_family"]) for x in plan] == [
        ("AAA", "income_statement"), ("AAA", "cash_flow"), ("AAA", "balance_sheet"),
        ("BBB", "income_statement"), ("BBB", "cash_flow"), ("BBB", "balance_sheet")]


def test_kbs_vietnamese_annual_column_is_retained_as_an_annual_observation(tmp_path):
    frame = _frame().rename(columns={"2024": "2024-Năm"})
    frame.to_parquet(tmp_path / "AAA_income_statement_year.parquet", index=False)
    replay = annual.replay_annual_payloads(tmp_path, official_citations={})
    assert replay["annual_observation_count"] == 1
    assert replay["observations"][0]["reporting_period"] == "2024"
