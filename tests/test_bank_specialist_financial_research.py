from __future__ import annotations

import pytest

import bank_financial_research_component as bank_component
import financial_analysis_engine_v2 as engine
import financial_analysis_product_projection as projection


def component(metric_id, value, *, year=2026, quarter=2, ticker="MBB", provider="TCBS",
             fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT,
             period_semantics_status=bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS,
             currency=None, scale=None, source_identity=None):
    return bank_component.build_observation(
        provider=provider, ticker=ticker, entity_type="bank", year=year, quarter=quarter,
        period_kind=bank_component.QUARTER, period_semantics_status=period_semantics_status,
        metric_id=metric_id, raw_value=value, currency=currency, scale=scale,
        source_identity=source_identity or f"{provider}-mcp-probe-20260901",
        retrieved_at="2026-09-01T00:00:00+07:00", fitness=fitness,
    )


def context(components, *, entity="bank", ticker="MBB"):
    return engine.build_ticker_context(ticker, [], issuer_type=entity, source_identities={"semantics": "x"},
                                       bank_components=components)


def row(metric, value, period="2026-Q2", *, ticker="AAA", provider="KBS", source=None,
       semantic="STANDALONE_QUARTER", scope="consolidated", sha="sha-1"):
    """Minimal canonical-facts row, mirroring tests/test_financial_analysis_engine_v2.py's
    helper, kept local so this file has no cross-test-module dependency."""
    source = source or f"{ticker}_{provider}_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {
        "ticker": ticker, "canonical_metric": metric, "reported_value": value,
        "native_period_label": period, "period_end": period, "period_semantic_state": semantic,
        "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
        "statement_scope": scope, "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
        "source_lineage": {"provider": provider, "source_file": source, "source_sha256": sha,
                           "fact_id": f"{metric}-{period}-{provider}"},
    }


# --- Bank applicability -----------------------------------------------------

def test_bank_applicability_computes_features_when_components_present():
    result = context([component("non_performing_loan", 50), component("customer_loan", 1000)])
    assert result["features"][engine.BANK_NPL_RATIO]["fitness"] == "READY"
    assert result["issuer_type"] == "bank"
    assert result["bank_specialist_contract_version"] == bank_component.CONTRACT_VERSION


@pytest.mark.parametrize("entity", ["corporate", "securities", "insurance", "finance_company", "unknown", None])
def test_non_bank_ticker_is_not_applicable_even_with_components_present(entity):
    components = [component("non_performing_loan", 50, ticker="AAA"), component("customer_loan", 1000, ticker="AAA")]
    result = context(components, entity=entity, ticker="AAA")
    for feature_id in engine.BANK_FEATURE_IDS:
        assert result["features"][feature_id]["fitness"] == "NOT_APPLICABLE"
        assert result["features"][feature_id]["reason_codes"] == ["ISSUER_NOT_BANK"]
    for state_name in engine.BANK_STATE_NAMES:
        assert result["states"][state_name] == "NOT_APPLICABLE"
    assert result["bank_specialist_contract_version"] is None


# --- Exact formula values ----------------------------------------------------

def test_npl_ratio_exact_value():
    result = context([component("non_performing_loan", 50), component("customer_loan", 1000)])
    feature = result["features"][engine.BANK_NPL_RATIO]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.05)


def test_ldr_exact_value():
    result = context([component("customer_loan", 800), component("deposit", 1000)])
    feature = result["features"][engine.BANK_LDR]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.8)


def test_cir_applies_abs_to_negative_operation_expense():
    result = context([component("operation_expense", -300), component("total_operation_income", 600)])
    feature = result["features"][engine.BANK_CIR]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.5)


def test_provision_coverage_exact_value():
    result = context([component("provision", 120), component("non_performing_loan", 100)])
    feature = result["features"][engine.BANK_PROVISION_COVERAGE]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(1.2)


def test_loan_growth_yoy_exact_value():
    components = [component("customer_loan", 1000, year=2025, quarter=2), component("customer_loan", 1100, year=2026, quarter=2)]
    result = context(components)
    feature = result["features"][engine.BANK_LOAN_GROWTH]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.1)


# --- Blocking behaviour -------------------------------------------------------

def test_zero_denominator_blocks_ldr():
    result = context([component("customer_loan", 800), component("deposit", 0)])
    feature = result["features"][engine.BANK_LDR]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "ZERO_DENOMINATOR" in feature["reason_codes"]


def test_missing_component_blocks_ldr():
    result = context([component("customer_loan", 800)])
    feature = result["features"][engine.BANK_LDR]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_SAME_PROVIDER_TICKER_PERIOD_BANK_COMPONENT_PAIR" in feature["reason_codes"]


def test_same_provider_requirement_blocks_cross_provider_pair():
    components = [component("customer_loan", 800, provider="TCBS"), component("deposit", 1000, provider="OTHER_PROVIDER")]
    result = context(components)
    feature = result["features"][engine.BANK_LDR]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_incompatible_period_growth_blocked_for_quarter_five():
    """quarter=5 (empirically FY-shaped) rows must never silently form a growth
    pair, even when both years are present and exactly one year apart."""
    components = [component("customer_loan", 1000, year=2025, quarter=5), component("customer_loan", 1100, year=2026, quarter=5)]
    result = context(components)
    feature = result["features"][engine.BANK_LOAN_GROWTH]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_COMPATIBLE_SAME_QUARTER_PRIOR_YEAR_LOAN_BALANCE" in feature["reason_codes"]


def test_loan_growth_zero_denominator_blocked():
    components = [component("customer_loan", 0, year=2025, quarter=2), component("customer_loan", 1100, year=2026, quarter=2)]
    result = context(components)
    assert result["features"][engine.BANK_LOAN_GROWTH]["fitness"] == "BLOCKED_BY_EVIDENCE"


# --- Empirical period status never becomes authority -------------------------

def test_empirically_verified_period_status_does_not_become_authority():
    components = [component("non_performing_loan", 50, period_semantics_status=bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS),
                  component("customer_loan", 1000, period_semantics_status=bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS)]
    result = context(components)
    feature = result["features"][engine.BANK_NPL_RATIO]
    assert feature["fitness"] == "READY"
    assert feature["period_semantics_status"] == [bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS]
    assert feature["is_actionable"] is False
    assert result["pit_authority"] == "NOT_GRANTED"
    assert result["authority_boundary"]["financial_authority_promoted"] is False


# --- NIM stays a proxy, never computed ---------------------------------------

def test_nim_provider_proxy_remains_proxy_never_ready():
    components = [component("net_interest_margin", 0.032, fitness=bank_component.PROVIDER_DERIVED_RESEARCH_PROXY)]
    result = context(components)
    feature = result["features"][engine.BANK_NIM_PROVIDER_PROXY]
    assert feature["fitness"] == "RESEARCH_PROXY"
    assert feature["value"] == pytest.approx(0.032)


def test_no_synthetic_nim_calculation_from_raw_components():
    """net_interest_income and total_asset alone must never produce a NIM
    value; only a verbatim PROVIDER_DERIVED_RESEARCH_PROXY net_interest_margin
    observation can."""
    components = [component("net_interest_income", 500), component("total_asset", 20000)]
    result = context(components)
    feature = result["features"][engine.BANK_NIM_PROVIDER_PROXY]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_PROVIDER_DERIVED_NET_INTEREST_MARGIN_OBSERVATION" in feature["reason_codes"]


def test_structured_component_tagged_nim_is_not_used_as_a_proxy():
    """A net_interest_margin value tagged STRUCTURED_RESEARCH_COMPONENT (the
    wrong tier for a provider-precomputed ratio) must not be treated as a
    valid provider-derived proxy either -- the fitness *tier* is the gate."""
    components = [component("net_interest_margin", 0.032, fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)]
    result = context(components)
    assert result["features"][engine.BANK_NIM_PROVIDER_PROXY]["fitness"] == "BLOCKED_BY_EVIDENCE"


# --- Monetary basis boundary --------------------------------------------------

def test_unknown_monetary_scale_allowed_for_same_row_dimensionless_ratio():
    components = [component("non_performing_loan", 50, currency=None, scale=None), component("customer_loan", 1000, currency=None, scale=None)]
    result = context(components)
    feature = result["features"][engine.BANK_NPL_RATIO]
    assert feature["fitness"] == "READY"
    assert feature["component_currency_status"] == ["UNKNOWN"]
    assert feature["component_scale_status"] == ["UNKNOWN"]


# --- States: trajectory required, never fabricated from one period ----------

def test_asset_quality_state_available_without_trajectory():
    result = context([component("non_performing_loan", 50), component("customer_loan", 1000)])
    assert result["states"][engine.BANK_ASSET_QUALITY_STATE] == "AVAILABLE"


def test_asset_quality_state_improving_when_npl_ratio_falls_yoy():
    components = [
        component("non_performing_loan", 80, year=2025, quarter=2), component("customer_loan", 1000, year=2025, quarter=2),
        component("non_performing_loan", 50, year=2026, quarter=2), component("customer_loan", 1000, year=2026, quarter=2),
    ]
    result = context(components)
    assert result["states"][engine.BANK_ASSET_QUALITY_STATE] == "IMPROVING"


def test_asset_quality_state_worsening_when_npl_ratio_rises_yoy():
    components = [
        component("non_performing_loan", 30, year=2025, quarter=2), component("customer_loan", 1000, year=2025, quarter=2),
        component("non_performing_loan", 50, year=2026, quarter=2), component("customer_loan", 1000, year=2026, quarter=2),
    ]
    result = context(components)
    assert result["states"][engine.BANK_ASSET_QUALITY_STATE] == "WORSENING"


def test_funding_state_unavailable_when_ldr_not_ready():
    result = context([component("customer_loan", 800)])
    assert result["states"][engine.BANK_FUNDING_STATE] == "UNAVAILABLE"


def test_efficiency_state_stable_when_cir_unchanged_yoy():
    components = [
        component("operation_expense", -300, year=2025, quarter=2), component("total_operation_income", 600, year=2025, quarter=2),
        component("operation_expense", -300, year=2026, quarter=2), component("total_operation_income", 600, year=2026, quarter=2),
    ]
    result = context(components)
    assert result["states"][engine.BANK_EFFICIENCY_STATE] == "STABLE"


# --- Artifact-level: denominator, zero drops, determinism, compact product --

def test_denominator_preserved_and_zero_silent_drops_with_mixed_tickers():
    bank_components = [component("non_performing_loan", 50, ticker="MBB"), component("customer_loan", 1000, ticker="MBB")]
    artifact = engine.build_artifact(
        tickers=["MBB", "AAA", "ZZZ"], rows=[row("revenue", 100), row("net_income", 10)],
        issuer_types={"MBB": "bank", "AAA": "corporate", "ZZZ": None},
        source_identities={"semantics": "x"}, requested_at="2026-09-01T00:00:00+07:00",
        bank_components=bank_components,
    )
    assert artifact["coverage"]["ticker_denominator"] == 3
    assert artifact["coverage"]["ticker_record_count"] == 3
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert artifact["records"]["MBB"]["features"][engine.BANK_NPL_RATIO]["fitness"] == "READY"
    assert artifact["records"]["AAA"]["features"][engine.BANK_NPL_RATIO]["fitness"] == "NOT_APPLICABLE"
    assert artifact["records"]["ZZZ"]["features"][engine.BANK_NPL_RATIO]["fitness"] == "NOT_APPLICABLE"
    # Existing corporate feature set/denominator is untouched by the additive merge.
    assert artifact["records"]["AAA"]["features"]["net_margin"]["fitness"] == "READY"


def test_deterministic_identity_same_bank_input_twice():
    components = [component("non_performing_loan", 50), component("customer_loan", 1000)]
    first = engine.build_ticker_context("MBB", [], issuer_type="bank", source_identities={"semantics": "x"}, bank_components=components)
    second = engine.build_ticker_context("MBB", [], issuer_type="bank", source_identities={"semantics": "x"}, bank_components=list(components))
    assert first == second


def test_compact_product_retains_bank_state_and_feature_fitness():
    bank_components = [component("non_performing_loan", 50), component("customer_loan", 1000)]
    artifact = engine.build_artifact(
        tickers=["MBB"], rows=[], issuer_types={"MBB": "bank"}, source_identities={"semantics": "x"},
        requested_at="2026-09-01T00:00:00+07:00", bank_components=bank_components,
    )
    product = projection.build_product_projection(financial_context=artifact, product_tickers=["MBB"],
                                                   requested_at="2026-09-01T00:00:00+07:00")
    record = product["records"]["MBB"]
    assert record["status"] == "AVAILABLE"
    assert record["bank_asset_quality_state"] == "AVAILABLE"
    assert record["feature_fitness"][engine.BANK_NPL_RATIO]["fitness"] == "READY"
    assert record["is_actionable"] is False
    assert record["raw_engine_record_exposed"] is False
