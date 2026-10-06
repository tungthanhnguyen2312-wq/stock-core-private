"""Generic acceptance cases for valuation denominator integrity.

The cases describe situations. They do not special-case issuer symbols.
"""
from __future__ import annotations

import current_valuation_denominator_integrity as integrity


def test_consistent_multiple_keeps_the_provider_value():
    row = integrity.diagnose_multiple({
        "method_id": "P/E", "provider_multiple": 10.0, "price": 100.0, "denominator": 10.0,
        "price_unit": "VND", "denominator_unit": "VND",
        "price_currency": "VND", "denominator_currency": "VND",
        "price_share_basis": "outstanding", "denominator_share_basis": "outstanding",
        "price_period": "2026Q2", "denominator_period": "2026Q2",
        "entity_class": "industrial", "method_applicable": True,
        "earnings_quality": {"recurring_decomposition_qualified": True},
    })
    assert row["status"] == integrity.CONSISTENT
    assert row["provider_multiple"] == 10.0
    assert row["arithmetic_multiple"] == 10.0
    assert row["provider_multiple_replaced"] is False
    assert row["strict_valuation_use"] == integrity.STRICT_ALLOWED


def test_arithmetic_disagreement_does_not_replace_the_provider_multiple():
    row = integrity.diagnose_multiple({
        "method_id": "P/B", "provider_multiple": 0.4, "price": 100.0, "denominator": 50.0,
        "price_unit": "VND", "denominator_unit": "VND",
        "price_currency": "VND", "denominator_currency": "VND",
        "price_share_basis": "outstanding", "denominator_share_basis": "outstanding",
        "price_period": "2026Q2", "denominator_period": "2026Q2",
        "method_applicable": True,
    })
    assert row["status"] == integrity.INCONSISTENT_DENOMINATOR
    assert row["provider_multiple"] == 0.4
    assert row["arithmetic_multiple"] == 2.0
    assert row["strict_valuation_use"] == integrity.STRICT_QUARANTINED


def test_period_share_basis_and_pending_action_fail_closed_separately():
    common = {"method_id": "P/E", "provider_multiple": 8, "price": 80, "denominator": 10,
              "price_unit": "VND", "denominator_unit": "VND", "price_currency": "VND", "denominator_currency": "VND",
              "method_applicable": True, "earnings_quality": {"recurring_decomposition_qualified": True}}
    period = integrity.diagnose_multiple({**common, "price_share_basis": "outstanding", "denominator_share_basis": "outstanding",
                                          "price_period": "2026Q2", "denominator_period": "2024Q4"})
    shares = integrity.diagnose_multiple({**common, "price_share_basis": "outstanding", "denominator_share_basis": "weighted_average",
                                          "price_period": "2026Q2", "denominator_period": "2026Q2"})
    pending = integrity.diagnose_multiple({**common, "price_share_basis": "outstanding", "denominator_share_basis": "outstanding",
                                           "price_period": "2026Q2", "denominator_period": "2026Q2",
                                           "corporate_action_lifecycle": "PENDING"})
    assert period["status"] == integrity.PERIOD_MISMATCH
    assert shares["status"] == integrity.SHARE_BASIS_MISMATCH
    assert pending["status"] == integrity.CORPORATE_ACTION_PENDING


def test_disposal_gain_flag_quarantines_a_cheap_looking_multiple_without_inventing_recurring_earnings():
    quality = integrity.classify_earnings_quality({
        "component_flags": ["disposal_gain"], "provenance": ["statement_note:other_income"],
    })
    assert quality["status"] == integrity.NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE
    assert quality["recurring_earnings"] is None
    row = integrity.diagnose_multiple({
        "method_id": "P/E", "provider_multiple": 4.0, "price": 40.0, "denominator": 10.0,
        "price_unit": "VND", "denominator_unit": "VND", "price_currency": "VND", "denominator_currency": "VND",
        "price_share_basis": "outstanding", "denominator_share_basis": "outstanding",
        "price_period": "2026Q2", "denominator_period": "2026Q2", "method_applicable": True,
        "earnings_quality": {"component_flags": ["disposal_gain"], "provenance": ["statement_note:other_income"]},
    })
    assert row["status"] == integrity.CONSISTENT
    assert row["strict_valuation_use"] == integrity.STRICT_QUARANTINED
    assert integrity.NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE in row["reason_codes"]


def test_provision_shock_without_decomposition_stays_unqualified():
    quality = integrity.classify_earnings_quality({"component_flags": ["unusual_provision"], "provenance": ["income_statement:provision"]})
    assert quality["status"] == integrity.NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE
    assert quality["strict_recurring_multiple_allowed"] is False


def test_securities_and_finance_are_not_forced_through_industrial_ev_ebitda():
    securities = integrity.diagnose_multiple({
        "method_id": "EV/EBITDA", "entity_class": "securities", "provider_multiple": 6,
        "price": 60, "denominator": 10, "price_unit": "VND", "denominator_unit": "VND",
        "price_currency": "VND", "denominator_currency": "VND",
    })
    finance = integrity.diagnose_multiple({
        "method_id": "EV/EBITDA", "entity_class": "finance_company", "provider_multiple": 6,
        "price": 60, "denominator": 10,
    })
    assert securities["status"] == integrity.NOT_COMPARABLE
    assert finance["status"] == integrity.NOT_COMPARABLE


def test_planned_issuance_does_not_become_executed_shares_or_an_inferred_ex_date():
    binding = integrity.project_corporate_event_binding({
        "event_type": "ISSUANCE", "event_status": "PLANNED", "known_at": "2026-10-01",
        "event_date": "2026-11-01", "record_date": "2026-10-20", "share_delta": 1_000_000,
        "dilution_status": "DILUTION_POSSIBLE", "freshness": "CURRENT",
        "evidence_tier": "OFFICIAL_QUALIFIED",
    })
    assert binding["ex_date"] is None
    assert binding["ex_date_inferred"] is False
    assert binding["executed_share_delta"] is None
    assert binding["planned_shares_converted_to_executed"] is False
    assert binding["lifecycle"] == "PLANNED"
    assert binding["issuer_route_promoted"] is False


def test_missing_claim_blocks_only_the_dependent_use():
    assert integrity.classify_claim(None) == integrity.CLAIM_MISSING
    assert integrity.classify_claim({"conflict": True, "value": 1}) == integrity.CLAIM_CONFLICT
    assert integrity.classify_claim({"stale": True, "value": 1}) == integrity.CLAIM_STALE
    assert integrity.classify_claim({"proxy": True, "value": 1}) == integrity.CLAIM_PROXY
    assert integrity.classify_claim({"warning": True, "value": 1}) == integrity.CLAIM_DATA_WARNING
    assert integrity.classify_claim({"inference": True, "value": 1}) == integrity.CLAIM_INFERENCE
    assert integrity.classify_claim({"value": 12}) == integrity.CLAIM_FACT
    assert integrity.dependent_use_blocked(integrity.CLAIM_MISSING, use_requires_field=True) is True
    assert integrity.dependent_use_blocked(integrity.CLAIM_MISSING, use_requires_field=False) is False
    assert integrity.dependent_use_blocked(integrity.CLAIM_FACT, use_requires_field=True) is False


def test_coverage_keeps_the_full_denominator_and_does_not_hide_gaps():
    rows = [
        {"ticker": "A", "fundamentals": "QUALIFIED_CURRENT", "valuation": "USABLE", "corporate_intelligence": "CURRENT", "corporate_action": "NOT_RELEVANT"},
        {"ticker": "B", "fundamentals": "RETAINED_STALE", "valuation": "QUARANTINED", "corporate_intelligence": "HISTORICAL", "corporate_action": "RELEVANT", "sector_specialist_required": True},
        {"ticker": "C", "fundamentals": "NO_EVIDENCE", "valuation": "UNAVAILABLE", "corporate_intelligence": "NO_EVIDENCE"},
    ]
    summary = integrity.summarize_coverage(rows, universe_denominator=1683)
    assert summary["universe_denominator"] == 1683
    assert summary["classified_rows"] == 3
    assert summary["unclassified_universe_members"] == 1680
    assert summary["counts"]["no_evidence"] == 1681
    assert summary["counts"]["valuation_QUARANTINED"] == 1
    assert summary["counts"]["fundamentals_RETAINED_STALE"] == 1
    assert summary["low_coverage_visible"] is True


def test_focus_situations_are_representable_without_ticker_branches():
    """The nine live names are situations, not hard-coded symbols."""
    situations = {
        "strong_fundamentals_weak_chart": {"fundamentals": "QUALIFIED_CURRENT", "valuation": "USABLE", "corporate_intelligence": "CURRENT"},
        "non_recurring_earnings": {"fundamentals": "QUALIFIED_CURRENT", "valuation": "QUARANTINED"},
        "capital_intensive_catalyst": {"fundamentals": "QUALIFIED_CURRENT", "valuation": "USABLE", "corporate_action": "RELEVANT"},
        "securities_semantics": {"sector_specialist_required": True, "valuation": "QUARANTINED"},
        "finance_company_semantics": {"sector_specialist_required": True, "valuation": "QUARANTINED"},
        "share_issuance": {"corporate_action": "RELEVANT", "valuation": "QUARANTINED"},
        "rights_dilution": {"corporate_action": "RELEVANT", "valuation": "QUARANTINED"},
        "provision_impairment": {"fundamentals": "QUALIFIED_CURRENT", "valuation": "QUARANTINED"},
        "established_uptrend": {"fundamentals": "QUALIFIED_CURRENT", "valuation": "USABLE"},
    }
    assert len(situations) == 9
    classified = [integrity.classify_coverage_row({"ticker": name, **fields}) for name, fields in situations.items()]
    assert sum(row["valuation"] == "QUARANTINED" for row in classified) >= 5
    assert any(row["sector_specialist_required"] for row in classified)
