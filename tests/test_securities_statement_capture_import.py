from __future__ import annotations

import securities_financial_research_component as securities_component
import securities_statement_capture_import as importer


def _raw(*, statement_family="balance_sheet", provider="VCI", raw_item_id="financial_assets_at_fair_value_through_profit_or_loss_fvtpl",
        raw_value=1000.0, reporting_period="2026-Q1", period_type="quarterly", period_variant_index=0,
        ticker="SSI", source_file="SSI_balance_sheet_quarter.parquet", source_sha256="a" * 64, scraped_at="2026-07-21 22:15"):
    return {
        "ticker": ticker, "provider": provider, "statement_family": statement_family,
        "reporting_period": reporting_period, "period_type": period_type,
        "period_variant_index": period_variant_index, "raw_item_id": raw_item_id, "raw_value": raw_value,
        "raw_currency": None, "raw_scale": None, "source_file": source_file, "source_sha256": source_sha256,
        "scraped_at": scraped_at,
    }


# --- Exact native field mapping ----------------------------------------------

def test_balance_sheet_fvtpl_financial_assets_maps_exactly():
    built = importer.securities_component_from_raw_observation(_raw())
    assert built is not None
    assert built["metric_id"] == "fvtpl_financial_assets"
    assert built["statement_family"] == securities_component.BALANCE_SHEET
    assert built["raw_value"] == 1000.0
    assert built["year"] == 2026 and built["quarter"] == 1


def test_balance_sheet_loans_maps_to_margin_lending_receivable_with_limitation():
    built = importer.securities_component_from_raw_observation(_raw(raw_item_id="loans", raw_value=37000.0))
    assert built["metric_id"] == "margin_lending_receivable"
    assert "NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS" in built["limitations"]


def test_income_statement_brokerage_revenue_maps_exactly():
    built = importer.securities_component_from_raw_observation(
        _raw(statement_family="income_statement", provider="KBS", raw_item_id="revenue_from_brokerage_services",
            raw_value=628450800.0, source_file="SSI_income_statement_quarter.parquet"))
    assert built["metric_id"] == "brokerage_revenue"
    assert built["statement_family"] == securities_component.INCOME_STATEMENT
    assert built["period_semantics_status"] == securities_component.DOCUMENTED_PROVIDER_CONTRACT


def test_income_statement_total_securities_operating_income_maps_exactly():
    built = importer.securities_component_from_raw_observation(
        _raw(statement_family="income_statement", provider="KBS", raw_item_id="revenue_from_securities_business_01_11",
            raw_value=3601760000.0, source_file="SSI_income_statement_quarter.parquet"))
    assert built["metric_id"] == "total_securities_operating_income"


# --- Unknown native field skipped ---------------------------------------------

def test_unknown_native_item_id_is_skipped():
    built = importer.securities_component_from_raw_observation(_raw(raw_item_id="some_unmapped_line_item"))
    assert built is None


def test_unrecognized_statement_family_is_skipped():
    built = importer.securities_component_from_raw_observation(_raw(statement_family="cash_flow", raw_item_id="loans"))
    assert built is None


# --- Provenance retained -------------------------------------------------------

def test_provenance_source_identity_carries_file_and_sha():
    built = importer.securities_component_from_raw_observation(_raw(source_file="SSI_balance_sheet_quarter.parquet", source_sha256="b" * 64))
    assert built["source_identity"] == "SSI_balance_sheet_quarter.parquet#" + "b" * 64


def test_provenance_retrieved_at_falls_back_to_scraped_at():
    built = importer.securities_component_from_raw_observation(_raw(scraped_at="2026-07-21 22:15"))
    assert built["retrieved_at"] == "2026-07-21 22:15"


def test_explicit_retrieved_at_overrides_scraped_at():
    built = importer.securities_component_from_raw_observation(_raw(), retrieved_at="2026-09-02T00:00:00+07:00")
    assert built["retrieved_at"] == "2026-09-02T00:00:00+07:00"


# --- Point-in-time balance-sheet component accepted regardless of provider ----

def test_point_in_time_balance_sheet_accepted_for_vci_provider():
    built = importer.securities_component_from_raw_observation(_raw(statement_family="balance_sheet", provider="VCI"))
    assert built is not None
    assert built["period_semantics_status"] == securities_component.DOCUMENTED_PROVIDER_CONTRACT


def test_point_in_time_balance_sheet_accepted_for_kbs_provider_too():
    """Balance-sheet PIT classification is provider-agnostic -- unlike the
    income-statement duration route, it never gates on which provider filed it."""
    built = importer.securities_component_from_raw_observation(_raw(statement_family="balance_sheet", provider="KBS"))
    assert built is not None


# --- KBS standalone-quarter income-statement flow accepted only if qualified --

def test_kbs_income_statement_quarterly_flow_accepted():
    built = importer.securities_component_from_raw_observation(
        _raw(statement_family="income_statement", provider="KBS", raw_item_id="revenue_from_brokerage_services"))
    assert built is not None
    assert built["period_kind"] == securities_component.QUARTER


def test_vci_income_statement_flow_blocked_unknown_duration():
    """VCI_PERIOD_DURATION_REMAINS_UNKNOWN: an income-statement row from any
    provider other than KBS must never be built, regardless of item id."""
    built = importer.securities_component_from_raw_observation(
        _raw(statement_family="income_statement", provider="VCI", raw_item_id="revenue_from_brokerage_services"))
    assert built is None


def test_non_quarterly_period_type_blocked():
    built = importer.securities_component_from_raw_observation(
        _raw(statement_family="income_statement", provider="KBS", raw_item_id="revenue_from_brokerage_services",
            period_type="annual", reporting_period="2026"))
    assert built is None


# --- Duplicate/restated period column never silently preferred ----------------

def test_duplicate_period_variant_column_is_skipped():
    built = importer.securities_component_from_raw_observation(_raw(period_variant_index=1))
    assert built is None


def test_primary_period_variant_column_is_accepted():
    built = importer.securities_component_from_raw_observation(_raw(period_variant_index=0))
    assert built is not None


# --- Bulk import summary -------------------------------------------------------

def test_import_raw_observations_reports_scope_split():
    raw_rows = [
        _raw(raw_item_id="financial_assets_at_fair_value_through_profit_or_loss_fvtpl"),
        _raw(raw_item_id="unmapped_line_item"),
        _raw(statement_family="income_statement", provider="VCI", raw_item_id="revenue_from_brokerage_services"),
    ]
    result = importer.import_raw_observations(raw_rows, retrieved_at="2026-09-02T00:00:00+07:00")
    assert result["raw_observations_seen"] == 3
    assert result["observations_built"] == 1
    assert result["skipped_out_of_scope"] == 2
    assert result["observations"][0]["metric_id"] == "fvtpl_financial_assets"


def test_non_finite_raw_value_is_skipped_not_raised():
    """Real extract_payload() output never carries NaN/inf (upstream already drops
    it), but the importer must fail closed rather than raise if one ever appears."""
    assert importer.securities_component_from_raw_observation(_raw(raw_value=float("nan"))) is None
    assert importer.securities_component_from_raw_observation(_raw(raw_value=float("inf"))) is None


def test_non_numeric_string_raw_value_is_skipped():
    assert importer.securities_component_from_raw_observation(_raw(raw_value="not_a_number")) is None
