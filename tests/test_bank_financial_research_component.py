from __future__ import annotations

import pytest

import bank_financial_research_component as bank_component
import monetary_basis_contract as basis_contract


def _kwargs(**overrides):
    base = dict(
        provider="TCBS", ticker="mbb", entity_type="bank", year=2026, quarter=2,
        period_kind=bank_component.QUARTER,
        period_semantics_status=bank_component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS,
        metric_id="customer_loan", raw_value=1000.0, source_identity="tcbs-mcp-probe-20260901",
        retrieved_at="2026-09-01T00:00:00+07:00", fitness=bank_component.STRUCTURED_RESEARCH_COMPONENT,
    )
    base.update(overrides)
    return base


def test_build_observation_normalizes_ticker_and_stamps_contract_version():
    observation = bank_component.build_observation(**_kwargs())
    assert observation["ticker"] == "MBB"
    assert observation["contract_version"] == bank_component.CONTRACT_VERSION
    assert observation["entity_type"] == "bank"


def test_deterministic_identity_same_input_twice():
    first = bank_component.build_observation(**_kwargs())
    second = bank_component.build_observation(**_kwargs())
    assert first == second
    assert first["component_sha256"] == second["component_sha256"]


def test_deterministic_identity_changes_with_value():
    first = bank_component.build_observation(**_kwargs(raw_value=1000.0))
    second = bank_component.build_observation(**_kwargs(raw_value=1000.01))
    assert first["component_sha256"] != second["component_sha256"]


def test_entity_type_must_be_bank():
    with pytest.raises(bank_component.BankResearchComponentError):
        bank_component.build_observation(**_kwargs(entity_type="securities"))


def test_fitness_must_be_a_declared_tier():
    with pytest.raises(bank_component.BankResearchComponentError):
        bank_component.build_observation(**_kwargs(fitness="READY"))


def test_period_kind_must_be_recognized():
    with pytest.raises(bank_component.BankResearchComponentError):
        bank_component.build_observation(**_kwargs(period_kind="MONTHLY"))


def test_raw_value_must_be_numeric():
    with pytest.raises(bank_component.BankResearchComponentError):
        bank_component.build_observation(**_kwargs(raw_value="1000"))


def test_quarter_5_is_accepted_verbatim_not_rejected_or_rewritten():
    """The contract retains what the provider actually sent; it never encodes
    quarter=5-means-FY as a universal rule (that belongs to formula-level
    eligibility, not ingestion -- see financial_analysis_engine_v2's loan-growth
    guard)."""
    observation = bank_component.build_observation(**_kwargs(quarter=5, period_kind=bank_component.QUARTER))
    assert observation["quarter"] == 5
    assert observation["period_kind"] == bank_component.QUARTER


def test_period_semantics_status_fails_closed_to_unknown():
    observation = bank_component.build_observation(**_kwargs(period_semantics_status="quarterly_reported"))
    assert observation["period_semantics_status"] == bank_component.UNKNOWN_PERIOD_SEMANTICS


def test_missing_currency_and_scale_yield_unknown_status():
    observation = bank_component.build_observation(**_kwargs(currency=None, scale=None))
    assert observation["currency_status"] == "UNKNOWN"
    assert observation["scale_status"] == "UNKNOWN"
    assert observation["monetary_basis"]["basis_status"] == basis_contract.UNKNOWN


def test_known_currency_and_scale_yield_known_status_and_research_contract_basis():
    observation = bank_component.build_observation(**_kwargs(currency="VND", scale="millions"))
    assert observation["currency_status"] == "KNOWN"
    assert observation["scale_status"] == "KNOWN"
    assert observation["monetary_basis"]["basis_status"] == basis_contract.RESEARCH_CONTRACT_QUALIFIED


def test_two_unknown_monetary_bases_are_never_compatible():
    """Reuses monetary_basis_contract directly: unknown scale must still block
    any absolute monetary comparison, even between two bank observations that
    both happen to be unknown in the same way."""
    first = bank_component.build_observation(**_kwargs(metric_id="total_asset", currency=None, scale=None, ticker="MBB"))
    second = bank_component.build_observation(**_kwargs(metric_id="total_asset", currency=None, scale=None, ticker="ACB"))
    compatible, reason = basis_contract.compatible(first["monetary_basis"], second["monetary_basis"])
    assert compatible is False
    assert reason == basis_contract.INCOMPATIBLE_REASON


def test_reject_private_fields_blocks_account_number():
    with pytest.raises(bank_component.BankResearchComponentPrivacyError):
        bank_component.build_observation(**_kwargs(source_payload={"account_number": "0123456789", "customerLoan": 1000}))


def test_reject_private_fields_blocks_oauth_and_session_tokens():
    with pytest.raises(bank_component.BankResearchComponentPrivacyError):
        bank_component.reject_private_fields({"oauth_token": "abc", "session_token": "xyz"})


def test_reject_private_fields_allows_clean_provider_payload():
    bank_component.reject_private_fields({"customerLoan": 1000, "deposit": 900, "ticker": "MBB"})


def test_source_payload_never_retained_on_observation():
    observation = bank_component.build_observation(**_kwargs(source_payload={"customerLoan": 1000}))
    assert "source_payload" not in observation
