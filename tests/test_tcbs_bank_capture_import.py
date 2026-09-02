from __future__ import annotations

import hashlib
import json

import pytest

import financial_analysis_engine_v2 as engine
import tcbs_bank_capture_import as importer


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def capture(tool="getBalanceSheetForBank", *, raw=None, ticker="MBB"):
    raw = raw if raw is not None else {"result": [{"ticker": ticker, "year": 2026, "quarter": 2, "customerLoan": 1000, "deposit": 800, "nonPerformingLoan": 50, "provision": 100}]}
    return {"provider": "TCBS", "tool_name": tool, "ticker": ticker, "captured_at": "2026-09-02T00:00:00+07:00", "raw_response": raw, "raw_response_sha256": digest(raw)}


def bundle(*captures, contract=importer.SOURCE_CAPTURE_CONTRACT):
    value = {"capture_contract": contract, "captures": list(captures), "tickers": ["MBB"]}
    value["bundle_sha256"] = digest(value)
    return value


def test_valid_capture_maps_balance_and_unknown_basis_deterministically():
    first = importer.import_capture_bundle(bundle(capture()))
    second = importer.import_capture_bundle(bundle(capture()))
    assert first == second
    values = {x["metric_id"]: x for x in first["observations"]}
    assert set(values) >= {"customer_loan", "deposit", "non_performing_loan", "provision"}
    assert values["customer_loan"]["currency_status"] == values["customer_loan"]["scale_status"] == "UNKNOWN"
    assert values["customer_loan"]["source_identity"].startswith("TCBS_MCP_CAPTURE:getBalanceSheetForBank:MBB:")


@pytest.mark.parametrize("bad", ["wrong/v1", None])
def test_wrong_capture_contract_rejected(bad):
    with pytest.raises(importer.TCBSBankCaptureImportError, match="UNSUPPORTED_CAPTURE_CONTRACT"):
        importer.import_capture_bundle(bundle(capture(), contract=bad))


def test_hash_mismatch_and_malformed_envelope_fail_capture_not_silently():
    broken = capture(); broken["raw_response_sha256"] = "0" * 64
    malformed = capture(raw={"not_result": []})
    result = importer.import_capture_bundle(bundle(broken, malformed))
    assert result["captures_failed"] == 2
    assert {x["code"] for x in result["diagnostics"]} >= {"CAPTURE_INTEGRITY_FAILED", "MALFORMED_RESULT_ENVELOPE"}


def test_unsupported_tool_and_ticker_mismatch_are_skipped():
    unsupported = capture("getPersonalPortfolio")
    mismatch = capture(raw={"result": [{"ticker": "VCB", "year": 2026, "quarter": 2, "customerLoan": 1}]})
    result = importer.import_capture_bundle(bundle(unsupported, mismatch))
    assert not result["observations"]
    assert {x["code"] for x in result["diagnostics"]} >= {"SKIP_UNSUPPORTED_TOOL", "ROW_TICKER_MISMATCH"}


def test_null_and_bool_are_not_zero_or_numeric():
    result = importer.import_capture_bundle(bundle(capture(raw={"result": [{"ticker": "MBB", "year": 2026, "quarter": 2, "customerLoan": None, "deposit": True}]})))
    assert not result["observations"]
    assert {x["code"] for x in result["diagnostics"]} >= {"MISSING_VALUE", "NON_NUMERIC_VALUE"}


def test_income_and_nim_mapping_and_provider_ratios_not_promoted():
    income = capture("getIncomeStatementForBank", raw={"result": [{"ticker": "MBB", "year": 2026, "quarter": 2, "operationExpense": -20, "totalOperationIncome": 100, "postTaxProfit": 40}]})
    ratio = capture("getFinancialRatioForBank", raw={"result": [{"ticker": "MBB", "year": 2026, "quarter": 2, "netInterestMargin": .03, "costToIncome": .2, "loanOnDeposit": .8, "nonPerformingLoans": .01}]})
    result = importer.import_capture_bundle(bundle(income, ratio))
    values = {x["metric_id"]: x for x in result["observations"]}
    assert {"operation_expense", "total_operation_income", "post_tax_profit", "net_interest_margin"} <= set(values)
    assert values["net_interest_margin"]["fitness"] == "PROVIDER_DERIVED_RESEARCH_PROXY"
    assert "cost_to_income" not in values and "loan_on_deposit" not in values


def test_q1_to_q4_and_q5_semantics_are_scoped():
    raw = {"result": [{"ticker": "MBB", "year": 2026, "quarter": 1, "customerLoan": 1}, {"ticker": "MBB", "year": 2026, "quarter": 5, "customerLoan": 2}]}
    result = importer.import_capture_bundle(bundle(capture(raw=raw)))
    q1, q5 = result["observations"]
    assert q1["period_kind"] == "QUARTER" and q5["period_kind"] == "FISCAL_YEAR"
    assert q5["quarter"] == 5 and "TCBS_QUARTER_5_EMPIRICAL_FY_BEHAVIOR_NOT_DECLARED_CONTRACT" in q5["limitations"]


@pytest.mark.parametrize("private_key", ["accountNumber", "personal_asset_allocation", "nestedToken"])
def test_nested_private_fields_fail_closed_without_value_in_error(private_key):
    key = "access_token" if private_key == "nestedToken" else private_key
    raw = {"result": [{"ticker": "MBB", "year": 2026, "quarter": 2, "customerLoan": 1}], "nested": [{key: "do-not-echo"}]}
    with pytest.raises(importer.TCBSBankCapturePrivacyError) as exc:
        importer.import_capture_bundle(bundle(capture(raw=raw)))
    assert "do-not-echo" not in str(exc.value)
    assert "PRIVATE_FIELD_REJECTED" in str(exc.value)


def test_exact_duplicate_dedupes_and_conflict_blocks_ready_replay():
    one = capture(); duplicate = dict(one)
    result = importer.import_capture_bundle(bundle(one, duplicate))
    assert len(result["observations"]) == 4
    assert any(x["code"] == "DUPLICATE_CAPTURE_IDENTITY" for x in result["diagnostics"])
    conflicting = capture(raw={"result": [{"ticker": "MBB", "year": 2026, "quarter": 2, "customerLoan": 1100}]})
    result = importer.import_capture_bundle(bundle(one, conflicting))
    assert result["conflicts"]
    context = engine.build_ticker_context("MBB", [], issuer_type="bank", source_identities={"x": "x"}, bank_components=result["observations"])
    assert context["features"][engine.BANK_LDR]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_q5_never_becomes_loan_growth_and_nim_is_proxy():
    raw = {"result": [{"ticker": "MBB", "year": 2025, "quarter": 5, "customerLoan": 100}, {"ticker": "MBB", "year": 2026, "quarter": 5, "customerLoan": 110}]}
    ratio = capture("getFinancialRatioForBank", raw={"result": [{"ticker": "MBB", "year": 2026, "quarter": 5, "netInterestMargin": .03}]})
    result = importer.import_capture_bundle(bundle(capture(raw=raw), ratio))
    context = engine.build_ticker_context("MBB", [], issuer_type="bank", source_identities={"x": "x"}, bank_components=result["observations"])
    assert context["features"][engine.BANK_LOAN_GROWTH]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert context["features"][engine.BANK_NIM_PROVIDER_PROXY]["fitness"] == "RESEARCH_PROXY"
