from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

import private_portfolio_context as portfolio_context
from private_portfolio_context import (
    CURRENT_COST_BASIS_METHOD,
    LIFETIME_BREAKEVEN_METHOD,
    PortfolioImportError,
    import_workbook,
    portfolio_status,
)
from stocklookup import main


def _workbook(path: Path, *, inconsistent: bool = False, reopened: bool = False, account_policy: bool = False) -> Path:
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Price", "Fee", "Tax"])
    if reopened:
        trade.append(["2026-01-01", "AAA", "BUY", 1, 10, 0, 0])
        trade.append(["2026-01-02", "AAA", "SELL", 1, 11, 0, 0])
        trade.append(["2026-01-03", "AAA", "BUY", 2, 12, 0, 0])
    else:
        trade.append(["2026-01-01", "AAA", "BUY", 10, 100, 1, 0])
        trade.append(["2026-01-02", "AAA", "SELL", 4, 120, 1, 2])
        trade.append(["2026-01-03", "AAA", "BUY", 2, 90, 0, 0])
        if inconsistent:
            trade.append(["2026-01-04", "AAA", "SELL", 20, 100, 0, 0])

    dividend = workbook.create_sheet("Dividend")
    dividend.append(["Date", "Ticker", "Type", "Cash Amount", "Stock Quantity"])
    if not reopened:
        dividend.append(["2026-01-04", "AAA", "cash dividend", 20, None])
        dividend.append(["2026-01-05", "AAA", "stock dividend", None, 2])

    money = workbook.create_sheet("Money")
    money.append(["Date", "Ticker", "Type", "Amount"])
    if not reopened:
        money.append(["2026-01-06", "AAA", "tax", 5])

    margin = workbook.create_sheet("margin")
    margin.append(["Date", "Ticker", "Type", "Amount"])
    if not reopened:
        margin.append(["2026-01-06", "AAA", "interest", 3])
        margin.append(["2026-01-06", None, "interest", 7])

    total = workbook.create_sheet("Total")
    total.append(["Ticker", "Quantity"])
    total.append(["AAA", 1 if inconsistent else 10 if not reopened else 2])

    if account_policy:
        account = workbook.create_sheet("AccountSnapshot")
        account.append(["As Of Date", "Currency", "Cash Available", "Margin Debt", "Net Asset Value"])
        account.append(["2026-01-06", "VND", 1000, 200, 5000])
        policy = workbook.create_sheet("PortfolioPolicy")
        policy.append(["As Of Date", "Currency", "Max Single Position Weight", "Max Margin Debt To NAV"])
        policy.append(["2026-01-06", "VND", 0.25, 0.2])

    workbook.save(path)
    return path


def _position(result: dict, ticker: str = "AAA") -> dict:
    return next(row for row in result["snapshot"]["positions"] if row["ticker"] == ticker)


def test_trade_dividend_margin_and_cost_semantics_are_deterministic(tmp_path: Path):
    result = import_workbook(workbook_path=_workbook(tmp_path / "synthetic.xlsx"), portfolio_root=tmp_path / "private")
    position = _position(result)

    assert position["current_quantity"] == "10"
    assert position["position_episode_holding_days"] == 5
    assert position["current_position_carrying_cost"] == "780.6"
    assert position["current_position_cost_basis_per_share"] == "78.06"
    assert position["current_position_cost_basis_method"] == CURRENT_COST_BASIS_METHOD
    assert position["purchase_count"] == 2
    assert position["sale_count"] == 1
    assert position["cash_dividends"] == "20"
    assert position["stock_distribution_quantity"] == "2"
    assert position["ticker_financing_cost"] == "3"
    assert position["ticker_fee_or_tax_cashflow"] == "5"
    assert position["lifetime_net_cash_outflow"] == "692"
    assert position["lifetime_cash_recovery_breakeven"] == "69.2"
    assert position["lifetime_cash_recovery_breakeven_method"] == LIFETIME_BREAKEVEN_METHOD
    assert position["realized_pnl"] == "76.6"
    assert position["unrealized_pnl"] is None
    assert result["snapshot"]["account_level_unallocated_margin_cost"] == "7"


def test_reopened_position_has_new_episode_without_rewriting_lifetime_history(tmp_path: Path):
    result = import_workbook(workbook_path=_workbook(tmp_path / "reopened.xlsx", reopened=True), portfolio_root=tmp_path / "private")
    position = _position(result)

    assert position["current_quantity"] == "2"
    assert position["position_episode_start_date"] == "2026-01-03"
    assert position["position_episode_holding_days"] == 0
    assert position["first_acquisition_date"] == "2026-01-01"
    assert position["last_acquisition_date"] == "2026-01-03"
    assert position["purchase_count"] == 2
    assert position["sale_count"] == 1


def test_inconsistent_quantity_is_a_warning_not_a_silent_repair(tmp_path: Path):
    result = import_workbook(workbook_path=_workbook(tmp_path / "inconsistent.xlsx", inconsistent=True), portfolio_root=tmp_path / "private")
    position = _position(result)

    assert position["current_quantity"] == "10"
    assert position["realized_pnl"] is None
    assert position["realized_pnl_status"] == "UNRESOLVED_RECONCILIATION_WARNING"
    codes = result["snapshot"]["reconciliation"]["warning_counts"]
    assert codes["SELL_QUANTITY_EXCEEDS_DERIVED_HOLDING"] == 1
    assert codes["TOTAL_VIEW_HINT_QUANTITY_MISMATCH"] == 1


def test_absent_account_and_policy_are_explicit_not_zero_filled(tmp_path: Path):
    result = import_workbook(workbook_path=_workbook(tmp_path / "absent.xlsx"), portfolio_root=tmp_path / "private")

    assert result["account_snapshot"]["status"] == "NOT_PROVIDED"
    assert set(result["account_snapshot"]["fields"].values()) == {None}
    assert result["policy"]["status"] == "SYSTEM_DEFAULTS_APPLIED"
    assert result["policy"]["owner_policy_status"] == "NOT_PROVIDED"
    assert result["policy"]["owner_supplied_fields"]["max_single_position_weight"] is None
    assert result["policy"]["effective_fields"]["max_single_position_weight"] == "0.30"
    assert result["policy"]["field_provenance"]["max_single_position_weight"]["effective_source"] == "SYSTEM_DEFAULT_POLICY_V1"
    assert result["system_default_policy"]["policy_version"] == "SYSTEM_DEFAULT_POLICY_V1"
    assert result["system_default_policy"]["default_fields"] == {
        "risk_budget_per_investment_decision_to_nav": "0.01",
        "max_single_position_weight": "0.30",
        "max_sector_weight": "0.45",
        "max_gross_exposure_to_nav": "1.15",
        "max_margin_debt_to_nav": "0.15",
        "minimum_cash_reserve_to_nav": "0.05",
        "max_margin_rate_percent_for_new_leveraged_exposure": "15.0",
    }


def test_account_snapshot_and_policy_are_optional_private_contracts(tmp_path: Path):
    result = import_workbook(workbook_path=_workbook(tmp_path / "policy.xlsx", account_policy=True), portfolio_root=tmp_path / "private")

    assert result["account_snapshot"]["status"] == "PROVIDED"
    assert result["account_snapshot"]["fields"]["cash_available"] == "1000"
    assert result["policy"]["status"] == "MIXED_OWNER_AND_SYSTEM_DEFAULTS"
    assert result["policy"]["fields"]["max_single_position_weight"] == "0.25"
    assert result["policy"]["field_provenance"]["max_single_position_weight"]["effective_source"] == "OWNER_WORKBOOK"
    assert result["policy"]["fields"]["minimum_cash_reserve_to_nav"] == "0.05"


def test_account_snapshot_retains_distinct_margin_availability_and_rate_without_debt_inference(tmp_path: Path):
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Price"])
    trade.append(["2026-01-01", "AAA", "BUY", 1, 100])
    account = workbook.create_sheet("AccountSnapshot")
    account.append(["As Of Date", "Cash Available", "Net Asset Value", "Margin Available Minimum", "Margin Available Maximum", "Annual Margin Rate Percent"])
    account.append(["2026-01-02", 5000000, 10000000, 1000000, 7000000, 13.5])
    # The workbook leaves all monetary cells unformatted (the Excel default).
    assert account["B2"].number_format == "General"
    path = tmp_path / "margin-account.xlsx"
    workbook.save(path)

    result = import_workbook(workbook_path=path, portfolio_root=tmp_path / "private")
    fields = result["account_snapshot"]["fields"]

    assert fields["cash_available"] == "5000000"
    assert fields["margin_available_minimum"] == "1000000"
    assert fields["margin_available_maximum"] == "7000000"
    assert fields["annual_margin_rate_percent"] == "13.5"
    assert fields["margin_debt"] is None
    assert result["account_snapshot"]["field_semantics"]["annual_margin_rate_percent"]["unit_or_format"] == "PERCENT_PER_ANNUM_NUMBER"
    assert result["account_snapshot"]["field_semantics"]["margin_debt"]["unit_or_format"] == "VND"


def test_legacy_margin_sheet_fields_are_reused_without_duplicate_account_snapshot_input(tmp_path: Path):
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Price"])
    trade.append(["2026-01-01", "AAA", "BUY", 1, 100])
    margin = workbook.create_sheet("margin")
    margin.append(["Field", "Value"])
    margin.append(["Margin Available Minimum", 1000000])
    margin.append(["Margin Available Maximum", 7000000])
    margin.append(["Annual Margin Rate Percent", 13.5])
    path = tmp_path / "legacy-margin-fields.xlsx"
    workbook.save(path)

    result = import_workbook(workbook_path=path, portfolio_root=tmp_path / "private")
    fields = result["account_snapshot"]["fields"]

    assert result["account_snapshot"]["source"] == {"sheets": ["margin"]}
    assert fields["margin_available_minimum"] == "1000000"
    assert fields["margin_available_maximum"] == "7000000"
    assert fields["annual_margin_rate_percent"] == "13.5"
    assert fields["margin_debt"] is None
    assert result["account_snapshot"]["field_provenance"]["margin_available_minimum"] == {"selected_source": "margin", "value_origin": "OWNER_WORKBOOK_FIELD"}
    assert result["account_snapshot"]["authority_boundary"]["margin_availability_is_not_margin_debt"] is True


def test_money_amount_is_vnd_by_field_identity_without_format_or_magnitude_inference(tmp_path: Path):
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Price"])
    trade.append(["2026-01-01", "AAA", "BUY", 1, 100])
    money = workbook.create_sheet("Money")
    money.append(["Date", "Type", "Amount"])
    money.append(["2026-01-02", "cash transfer", 1234567])
    assert money["C2"].number_format == "General"
    path = tmp_path / "unformatted-vnd.xlsx"
    workbook.save(path)

    result = import_workbook(workbook_path=path, portfolio_root=tmp_path / "private")
    movement = next(event for event in result["ledger"]["events"] if event["event_type"] == "MONEY_MOVEMENT")

    assert movement["gross_amount"] == "1234567"
    assert movement["monetary_currency"] == "VND"
    assert movement["monetary_unit_basis"] == "WORKBOOK_FIELD_IDENTITY_VND_NO_FORMAT_OR_MAGNITUDE_INFERENCE"
    assert result["ledger"]["authority_boundary"]["money_and_margin_currency_inference_from_cell_format_or_magnitude"] == "PROHIBITED"


def test_partial_owner_policy_override_keeps_source_effective_values_and_provenance(tmp_path: Path):
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Price"])
    trade.append(["2026-01-01", "AAA", "BUY", 1, 100])
    policy = workbook.create_sheet("PortfolioPolicy")
    policy.append(["Max Single Position Weight"])
    policy.append([0.22])
    path = tmp_path / "partial-policy.xlsx"
    workbook.save(path)

    result = import_workbook(workbook_path=path, portfolio_root=tmp_path / "private")
    policy_result = result["policy"]

    assert policy_result["status"] == "MIXED_OWNER_AND_SYSTEM_DEFAULTS"
    assert policy_result["owner_supplied_fields"]["max_single_position_weight"] == "0.22"
    assert policy_result["effective_fields"]["max_single_position_weight"] == "0.22"
    assert policy_result["field_provenance"]["max_single_position_weight"]["effective_source"] == "OWNER_WORKBOOK"
    assert policy_result["owner_supplied_fields"]["max_margin_debt_to_nav"] is None
    assert policy_result["effective_fields"]["max_margin_debt_to_nav"] == "0.15"
    assert policy_result["field_provenance"]["max_margin_debt_to_nav"]["effective_source"] == "SYSTEM_DEFAULT_POLICY_V1"
    assert policy_result["effective_fields"]["max_margin_rate_percent_for_new_leveraged_exposure"] == "15.0"
    assert policy_result["authority_boundary"]["existing_positions_above_policy_caps_are_not_automatic_sell_instructions"] is True


def test_reimport_is_content_addressed_and_status_does_not_reopen_workbook(tmp_path: Path):
    workbook = _workbook(tmp_path / "idempotent.xlsx")
    root = tmp_path / "private"
    first = import_workbook(workbook_path=workbook, portfolio_root=root)
    second = import_workbook(workbook_path=workbook, portfolio_root=root)
    status = portfolio_status(portfolio_root=root)

    assert first["status"] == "IMPORTED"
    assert second["status"] == "REUSED_IDENTICAL"
    assert first["manifest"]["artifact_identity"] == second["manifest"]["artifact_identity"]
    assert status["status"] == "READY"
    assert status["manifest"]["artifact_identity"] == first["manifest"]["artifact_identity"]
    assert json.loads((root / "latest_import.json").read_text(encoding="utf-8"))["workbook_sha256"] == first["manifest"]["workbook_sha256"]


def test_corrective_import_layout_preserves_a_prior_same_workbook_sha_artifact(tmp_path: Path):
    workbook = _workbook(tmp_path / "prior-layout.xlsx")
    root = tmp_path / "private"
    legacy_directory = root / "imports" / portfolio_context._sha256_file(workbook)
    legacy_directory.mkdir(parents=True)
    legacy_artifact = legacy_directory / "portfolio_event_ledger_v1.json"
    legacy_artifact.write_text('{"legacy":"immutable"}\n', encoding="utf-8")

    result = import_workbook(workbook_path=workbook, portfolio_root=root)

    assert result["status"] == "IMPORTED"
    assert result["private_artifact_directory"] != legacy_directory
    assert legacy_artifact.read_text(encoding="utf-8") == '{"legacy":"immutable"}\n'
    assert result["manifest"]["import_layout_version"] == "PORTFOLIO_CONTEXT_IMPORT_LAYOUT_V2"
    assert result["private_artifact_directory"].parent == legacy_directory


def test_owner_cli_portfolio_branch_uses_private_summary_without_daily_preflight(tmp_path: Path, capsys):
    workbook = _workbook(tmp_path / "cli.xlsx")
    root = tmp_path / "private"

    assert main(["portfolio", "import", "--workbook", str(workbook), "--portfolio-root", str(root)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["status"] == "IMPORTED"
    assert imported["provider_calls"] == "NOT_USED"
    assert imported["daily_run"] == "NOT_USED"
    assert "positions" not in imported
    assert "events" not in imported

    assert main(["portfolio", "status", "--portfolio-root", str(root)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "READY"
    assert status["import_manifest_identity"] == imported["import_manifest_identity"]


def test_workbook_inside_repository_boundary_is_refused_even_when_synthetic(tmp_path: Path, monkeypatch):
    synthetic_repository = tmp_path / "repository"
    synthetic_repository.mkdir()
    workbook = _workbook(synthetic_repository / "synthetic.xlsx")
    monkeypatch.setattr(portfolio_context, "REPOSITORY_ROOT", synthetic_repository)

    with pytest.raises(PortfolioImportError, match="MUST_LIVE_OUTSIDE_REPOSITORY"):
        import_workbook(workbook_path=workbook, portfolio_root=tmp_path / "private")


def test_labeled_net_trade_amount_does_not_double_count_fee_or_tax(tmp_path: Path):
    workbook = Workbook()
    trade = workbook.active
    trade.title = "Trade"
    trade.append(["Date", "Ticker", "Side", "Quantity", "Net Amount", "Fee", "Tax"])
    trade.append(["2026-01-01", "AAA", "BUY", 1, 105, 3, 2])
    trade.append(["2026-01-02", "AAA", "SELL", 1, 115, 3, 2])
    path = tmp_path / "net-amount.xlsx"
    workbook.save(path)

    result = import_workbook(workbook_path=path, portfolio_root=tmp_path / "private")
    events = result["ledger"]["events"]
    position = _position(result)
    assert [event["gross_amount"] for event in events] == ["100", "120"]
    assert position["realized_pnl"] == "10"
