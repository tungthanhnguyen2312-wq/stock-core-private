from __future__ import annotations

import pytest

import securities_financial_research_component as securities_component
import monetary_basis_contract as basis_contract


def _kwargs(**overrides):
    base = dict(
        provider="VCI", ticker="ssi", entity_type="securities", year=2026, quarter=1,
        period_kind=securities_component.QUARTER,
        period_semantics_status=securities_component.DOCUMENTED_PROVIDER_CONTRACT,
        statement_family=securities_component.BALANCE_SHEET,
        metric_id="fvtpl_financial_assets", raw_value=1000.0, source_identity="data_bctc-probe-20260902",
        retrieved_at="2026-09-02T00:00:00+07:00", fitness=securities_component.STRUCTURED_RESEARCH_COMPONENT,
    )
    base.update(overrides)
    return base


def test_build_observation_normalizes_ticker_and_stamps_contract_version():
    observation = securities_component.build_observation(**_kwargs())
    assert observation["ticker"] == "SSI"
    assert observation["contract_version"] == securities_component.CONTRACT_VERSION
    assert observation["entity_type"] == "securities"
    assert observation["statement_family"] == securities_component.BALANCE_SHEET


def test_deterministic_identity_same_input_twice():
    first = securities_component.build_observation(**_kwargs())
    second = securities_component.build_observation(**_kwargs())
    assert first == second
    assert first["component_sha256"] == second["component_sha256"]


def test_deterministic_identity_changes_with_value():
    first = securities_component.build_observation(**_kwargs(raw_value=1000.0))
    second = securities_component.build_observation(**_kwargs(raw_value=1000.01))
    assert first["component_sha256"] != second["component_sha256"]


def test_entity_type_must_be_securities():
    with pytest.raises(securities_component.SecuritiesResearchComponentError):
        securities_component.build_observation(**_kwargs(entity_type="bank"))


def test_fitness_must_be_a_declared_tier():
    with pytest.raises(securities_component.SecuritiesResearchComponentError):
        securities_component.build_observation(**_kwargs(fitness="READY"))


def test_period_kind_must_be_recognized():
    with pytest.raises(securities_component.SecuritiesResearchComponentError):
        securities_component.build_observation(**_kwargs(period_kind="MONTHLY"))


def test_statement_family_must_be_recognized():
    with pytest.raises(securities_component.SecuritiesResearchComponentError):
        securities_component.build_observation(**_kwargs(statement_family="cash_flow"))


def test_raw_value_must_be_numeric():
    with pytest.raises(securities_component.SecuritiesResearchComponentError):
        securities_component.build_observation(**_kwargs(raw_value="1000"))


def test_period_semantics_status_fails_closed_to_unknown():
    observation = securities_component.build_observation(**_kwargs(period_semantics_status="quarterly_reported"))
    assert observation["period_semantics_status"] == securities_component.UNKNOWN_PERIOD_SEMANTICS


def test_missing_currency_and_scale_yield_unknown_status():
    observation = securities_component.build_observation(**_kwargs(currency=None, scale=None))
    assert observation["currency_status"] == "UNKNOWN"
    assert observation["scale_status"] == "UNKNOWN"
    assert observation["monetary_basis"]["basis_status"] == basis_contract.UNKNOWN


def test_known_currency_and_scale_yield_known_status_and_research_contract_basis():
    observation = securities_component.build_observation(**_kwargs(currency="VND", scale="millions"))
    assert observation["currency_status"] == "KNOWN"
    assert observation["scale_status"] == "KNOWN"
    assert observation["monetary_basis"]["basis_status"] == basis_contract.RESEARCH_CONTRACT_QUALIFIED


def test_two_unknown_monetary_bases_are_never_compatible():
    first = securities_component.build_observation(**_kwargs(metric_id="total_assets", currency=None, scale=None, ticker="SSI"))
    second = securities_component.build_observation(**_kwargs(metric_id="total_assets", currency=None, scale=None, ticker="VND"))
    compatible, reason = basis_contract.compatible(first["monetary_basis"], second["monetary_basis"])
    assert compatible is False
    assert reason == basis_contract.INCOMPATIBLE_REASON


def test_reject_private_fields_blocks_account_number():
    with pytest.raises(securities_component.SecuritiesResearchComponentPrivacyError):
        securities_component.build_observation(**_kwargs(source_payload={"account_number": "0123456789", "loans": 1000}))


def test_reject_private_fields_blocks_oauth_and_session_tokens():
    with pytest.raises(securities_component.SecuritiesResearchComponentPrivacyError):
        securities_component.reject_private_fields({"oauth_token": "abc", "session_token": "xyz"})


def test_reject_private_fields_allows_clean_provider_payload():
    securities_component.reject_private_fields({"loans": 1000, "total_assets": 9000, "ticker": "SSI"})


def test_source_payload_never_retained_on_observation():
    observation = securities_component.build_observation(**_kwargs(source_payload={"loans": 1000}))
    assert "source_payload" not in observation


def test_limitations_are_retained_verbatim():
    observation = securities_component.build_observation(
        **_kwargs(metric_id="margin_lending_receivable",
                  limitations=["NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS"]))
    assert observation["limitations"] == ["NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS"]


def test_income_statement_family_accepted_shape():
    observation = securities_component.build_observation(
        **_kwargs(statement_family=securities_component.INCOME_STATEMENT, metric_id="brokerage_revenue", raw_value=500.0))
    assert observation["statement_family"] == securities_component.INCOME_STATEMENT
    assert observation["metric_id"] == "brokerage_revenue"


def test_negative_raw_value_is_retained_unmodified_never_abs():
    """Task boundary: a negative FVTPL-family amount must never be silently abs()'d."""
    observation = securities_component.build_observation(**_kwargs(metric_id="fvtpl_gain", raw_value=-2058426000.0))
    assert observation["raw_value"] == -2058426000.0
