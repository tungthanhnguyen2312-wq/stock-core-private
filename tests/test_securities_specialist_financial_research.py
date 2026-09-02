from __future__ import annotations

import pytest

import securities_financial_research_component as securities_component
import financial_analysis_engine_v2 as engine
import financial_analysis_product_projection as projection


def component(metric_id, value, *, year=2026, quarter=1, ticker="SSI", provider="VCI",
             statement_family=securities_component.BALANCE_SHEET,
             fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT,
             period_semantics_status=securities_component.DOCUMENTED_PROVIDER_CONTRACT,
             currency=None, scale=None, source_identity=None, limitations=()):
    return securities_component.build_observation(
        provider=provider, ticker=ticker, entity_type="securities", year=year, quarter=quarter,
        period_kind=securities_component.QUARTER, period_semantics_status=period_semantics_status,
        statement_family=statement_family, metric_id=metric_id, raw_value=value, currency=currency, scale=scale,
        source_identity=source_identity or f"{provider}-data_bctc-20260902",
        retrieved_at="2026-09-02T00:00:00+07:00", fitness=fitness, limitations=limitations,
    )


def context(components, *, entity="securities", ticker="SSI"):
    return engine.build_ticker_context(ticker, [], issuer_type=entity, source_identities={"semantics": "x"},
                                       securities_components=components)


def row(metric, value, period="2026-Q1", *, ticker="AAA", provider="KBS", source=None,
       semantic="STANDALONE_QUARTER", scope="consolidated", sha="sha-1"):
    """Minimal canonical-facts row for the generic corporate path, mirroring the
    bank specialist test's own local helper (kept local, no cross-test-module dep)."""
    source = source or f"{ticker}_{provider}_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {
        "ticker": ticker, "canonical_metric": metric, "reported_value": value,
        "native_period_label": period, "period_end": period, "period_semantic_state": semantic,
        "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
        "statement_scope": scope, "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
        "source_lineage": {"provider": provider, "source_file": source, "source_sha256": sha,
                           "fact_id": f"{metric}-{period}-{provider}"},
    }


def _bs_pair(fvtpl=4200.0, total_assets=9300.0, loans=3700.0, loans_limitations=(), **kw):
    return [component("fvtpl_financial_assets", fvtpl, **kw), component("total_assets", total_assets, **kw),
            component("margin_lending_receivable", loans, limitations=loans_limitations, **kw)]


# --- Governed securities ticker selection / non-securities rejected -----------

def test_securities_applicability_computes_features_when_components_present():
    result = context(_bs_pair())
    assert result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "READY"
    assert result["issuer_type"] == "securities"
    assert result["securities_specialist_contract_version"] == securities_component.CONTRACT_VERSION


@pytest.mark.parametrize("entity", ["corporate", "bank", "insurance", "finance_company", "unknown", None])
def test_non_securities_ticker_is_not_applicable_even_with_components_present(entity):
    components = _bs_pair(ticker="AAA")
    result = context(components, entity=entity, ticker="AAA")
    for feature_id in engine.SECURITIES_FEATURE_IDS:
        assert result["features"][feature_id]["fitness"] == "NOT_APPLICABLE"
        assert result["features"][feature_id]["reason_codes"] == ["ISSUER_NOT_SECURITIES"]
    for state_name in engine.SECURITIES_STATE_NAMES:
        assert result["states"][state_name] == "NOT_APPLICABLE"
    assert result["securities_specialist_contract_version"] is None


# --- Generic corporate feature applicability unchanged / additive only --------

def test_securities_ticker_generic_corporate_features_remain_not_applicable():
    result = context(_bs_pair(), entity="securities")
    assert result["analysis_family"] == engine.LIMITED
    assert result["features"]["gross_margin"]["fitness"] == "NOT_APPLICABLE"
    assert result["features"]["current_ratio"]["fitness"] == "NOT_APPLICABLE"


def test_securities_context_never_sets_current_research_ready():
    """No readiness inflation by side effect: family stays LIMITED regardless of
    how many securities-specialist features go READY."""
    result = context(_bs_pair())
    assert result["current_research_ready"] is False


# --- Exact formula values -------------------------------------------------------

def test_fvtpl_asset_intensity_exact_value():
    result = context(_bs_pair(fvtpl=4000.0, total_assets=10000.0))
    feature = result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.4)


def test_margin_lending_asset_intensity_exact_value():
    result = context(_bs_pair(loans=3000.0, total_assets=10000.0))
    feature = result["features"][engine.SECURITIES_MARGIN_LENDING_ASSET_INTENSITY]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.3)


def test_margin_lending_component_limitation_propagates_to_feature():
    components = _bs_pair(
        loans_limitations=("NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS",))
    result = context(components)
    feature = result["features"][engine.SECURITIES_MARGIN_LENDING_ASSET_INTENSITY]
    assert "NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS" in feature["limitations"]


def test_brokerage_revenue_mix_exact_value():
    components = [
        component("brokerage_revenue", 600.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
        component("total_securities_operating_income", 3000.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
    ]
    result = context(components)
    feature = result["features"][engine.SECURITIES_BROKERAGE_REVENUE_MIX]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.2)


def test_loan_interest_income_mix_exact_value():
    components = [
        component("loan_receivable_interest_income", 900.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
        component("total_securities_operating_income", 3000.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
    ]
    result = context(components)
    feature = result["features"][engine.SECURITIES_LOAN_INTEREST_INCOME_MIX]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(0.3)


def test_negative_fvtpl_asset_amount_not_abs_normalized():
    """A hypothetical negative FVTPL asset amount must flow through signed, not
    be silently made positive."""
    result = context(_bs_pair(fvtpl=-500.0, total_assets=10000.0))
    feature = result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(-0.05)


def test_negative_denominator_not_abs_normalized():
    components = [
        component("brokerage_revenue", 100.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
        component("total_securities_operating_income", -50.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
    ]
    result = context(components)
    feature = result["features"][engine.SECURITIES_BROKERAGE_REVENUE_MIX]
    assert feature["fitness"] == "READY"
    assert feature["value"] == pytest.approx(-2.0)


# --- Blocking behaviour ----------------------------------------------------------

def test_zero_denominator_blocked():
    result = context(_bs_pair(total_assets=0.0))
    feature = result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "ZERO_DENOMINATOR" in feature["reason_codes"]


def test_missing_component_blocked_not_zero():
    """missing != zero: a wholly absent denominator is a different reason code
    from an explicit zero denominator."""
    result = context([component("fvtpl_financial_assets", 4000.0)])
    feature = result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_SAME_PROVIDER_TICKER_PERIOD_SECURITIES_COMPONENT_PAIR" in feature["reason_codes"]


def test_cross_provider_pair_blocked():
    components = [component("fvtpl_financial_assets", 4000.0, provider="VCI"),
                 component("total_assets", 10000.0, provider="OTHER_PROVIDER")]
    result = context(components)
    feature = result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_cross_period_pair_blocked():
    components = [component("fvtpl_financial_assets", 4000.0, year=2026, quarter=1),
                 component("total_assets", 10000.0, year=2025, quarter=4)]
    result = context(components)
    assert result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_representation_incompatibility_blocked_cross_statement_family():
    """A hypothetical component pair tagged with mismatched statement_family
    values (e.g. a mistagged import) must never silently pair, even with the
    same ticker/provider/period."""
    components = [component("fvtpl_financial_assets", 4000.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS"),
                 component("total_assets", 10000.0, statement_family=securities_component.BALANCE_SHEET, provider="KBS")]
    result = context(components)
    assert result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_unusable_fitness_tier_never_used_as_input():
    """A RESEARCH_PROXY or UNKNOWN-fitness component must never be consumed as a
    STRUCTURED_RESEARCH_COMPONENT ratio input."""
    components = [component("fvtpl_financial_assets", 4000.0, fitness=securities_component.RESEARCH_PROXY),
                 component("total_assets", 10000.0)]
    result = context(components)
    assert result["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "BLOCKED_BY_EVIDENCE"


# --- States: trajectory required, never fabricated from one period ------------

def test_fvtpl_state_available_without_trajectory():
    result = context(_bs_pair())
    assert result["states"][engine.SECURITIES_FVTPL_ASSET_INTENSITY_STATE] == "AVAILABLE"


def test_fvtpl_state_rising_when_intensity_rises_yoy():
    components = _bs_pair(fvtpl=3000.0, total_assets=10000.0, year=2025, quarter=1) + \
                _bs_pair(fvtpl=4000.0, total_assets=10000.0, year=2026, quarter=1)
    result = context(components)
    assert result["states"][engine.SECURITIES_FVTPL_ASSET_INTENSITY_STATE] == "FVTPL_ASSET_INTENSITY_RISING"


def test_fvtpl_state_falling_when_intensity_falls_yoy():
    components = _bs_pair(fvtpl=5000.0, total_assets=10000.0, year=2025, quarter=1) + \
                _bs_pair(fvtpl=3000.0, total_assets=10000.0, year=2026, quarter=1)
    result = context(components)
    assert result["states"][engine.SECURITIES_FVTPL_ASSET_INTENSITY_STATE] == "FVTPL_ASSET_INTENSITY_FALLING"


def test_margin_lending_state_stable_when_intensity_unchanged_yoy():
    components = _bs_pair(loans=3000.0, total_assets=10000.0, year=2025, quarter=1) + \
                _bs_pair(loans=3000.0, total_assets=10000.0, year=2026, quarter=1)
    result = context(components)
    assert result["states"][engine.SECURITIES_MARGIN_LENDING_INTENSITY_STATE] == "MARGIN_LENDING_INTENSITY_STABLE"


def test_brokerage_mix_state_unavailable_when_ratio_not_ready():
    result = context([component("brokerage_revenue", 100.0, statement_family=securities_component.INCOME_STATEMENT, provider="KBS")])
    assert result["states"][engine.SECURITIES_BROKERAGE_MIX_STATE] == "UNAVAILABLE"


def test_no_thresholds_or_scoring_in_state_vocabulary():
    """States are pure sign-of-delta trajectory labels; never a healthy/risky verdict."""
    components = _bs_pair(year=2025, quarter=1) + _bs_pair(year=2026, quarter=1)
    result = context(components)
    for state_name in engine.SECURITIES_STATE_NAMES:
        assert result["states"][state_name] in {"AVAILABLE", "UNAVAILABLE",
            "FVTPL_ASSET_INTENSITY_RISING", "FVTPL_ASSET_INTENSITY_FALLING", "FVTPL_ASSET_INTENSITY_STABLE",
            "MARGIN_LENDING_INTENSITY_RISING", "MARGIN_LENDING_INTENSITY_FALLING", "MARGIN_LENDING_INTENSITY_STABLE",
            "BROKERAGE_MIX_RISING", "BROKERAGE_MIX_FALLING", "BROKERAGE_MIX_STABLE"}


# --- Artifact-level: denominator, zero drops, determinism, compact product ----

def test_denominator_preserved_and_zero_silent_drops_with_mixed_tickers():
    securities_components = _bs_pair(ticker="SSI")
    artifact = engine.build_artifact(
        tickers=["SSI", "AAA", "ZZZ"], rows=[row("revenue", 100), row("net_income", 10)],
        issuer_types={"SSI": "securities", "AAA": "corporate", "ZZZ": None},
        source_identities={"semantics": "x"}, requested_at="2026-09-02T00:00:00+07:00",
        securities_components=securities_components,
    )
    assert artifact["coverage"]["ticker_denominator"] == 3
    assert artifact["coverage"]["ticker_record_count"] == 3
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert artifact["records"]["SSI"]["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "READY"
    assert artifact["records"]["AAA"]["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "NOT_APPLICABLE"
    assert artifact["records"]["ZZZ"]["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "NOT_APPLICABLE"
    # Existing corporate feature set/denominator is untouched by the additive merge.
    assert artifact["records"]["AAA"]["features"]["net_margin"]["fitness"] == "READY"


def test_bank_and_securities_families_coexist_independently():
    import bank_financial_research_component as bank_component
    bank_components = [bank_component.build_observation(
        provider="TCBS", ticker="MBB", entity_type="bank", year=2026, quarter=2,
        period_kind=bank_component.QUARTER, period_semantics_status=bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS,
        metric_id="customer_loan", raw_value=1000.0, source_identity="tcbs", retrieved_at="x",
        fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT)]
    securities_components = _bs_pair(ticker="SSI")
    artifact = engine.build_artifact(
        tickers=["MBB", "SSI"], rows=[], issuer_types={"MBB": "bank", "SSI": "securities"},
        source_identities={}, requested_at="2026-09-02T00:00:00+07:00",
        bank_components=bank_components, securities_components=securities_components,
    )
    assert artifact["records"]["MBB"]["features"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "NOT_APPLICABLE"
    assert artifact["records"]["SSI"]["features"][engine.BANK_NPL_RATIO]["fitness"] == "NOT_APPLICABLE"
    assert artifact["records"]["MBB"]["bank_specialist_contract_version"] is not None
    assert artifact["records"]["MBB"]["securities_specialist_contract_version"] is None
    assert artifact["records"]["SSI"]["securities_specialist_contract_version"] is not None
    assert artifact["records"]["SSI"]["bank_specialist_contract_version"] is None


def test_deterministic_identity_same_securities_input_twice():
    components = _bs_pair()
    first = engine.build_ticker_context("SSI", [], issuer_type="securities", source_identities={"semantics": "x"}, securities_components=components)
    second = engine.build_ticker_context("SSI", [], issuer_type="securities", source_identities={"semantics": "x"}, securities_components=list(components))
    assert first == second


def test_compact_product_retains_securities_state_and_feature_fitness():
    securities_components = _bs_pair()
    artifact = engine.build_artifact(
        tickers=["SSI"], rows=[], issuer_types={"SSI": "securities"}, source_identities={"semantics": "x"},
        requested_at="2026-09-02T00:00:00+07:00", securities_components=securities_components,
    )
    product = projection.build_product_projection(financial_context=artifact, product_tickers=["SSI"],
                                                   requested_at="2026-09-02T00:00:00+07:00")
    record = product["records"]["SSI"]
    assert record["status"] == "AVAILABLE"
    assert record["fvtpl_asset_intensity_trajectory_state"] == "AVAILABLE"
    assert record["feature_fitness"][engine.SECURITIES_FVTPL_ASSET_INTENSITY]["fitness"] == "READY"
    assert record["is_actionable"] is False
    assert record["raw_engine_record_exposed"] is False
