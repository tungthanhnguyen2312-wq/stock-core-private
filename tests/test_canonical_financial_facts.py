# ==========================================================================
# Tests for pillar A layer 3 -- canonical financial facts:
#   canonical_financial_resolvers.py     -- scope/sign/scale/basis, evidence-only
#   canonical_financial_facts.py         -- raw observations -> canonical facts
#   canonical_fact_store.py              -- incremental, byte-deterministic shards
#   market_wide_calculation_readiness.py -- EBITDA/EV/EV-EBITDA/PE/PB/ROE gating
#
# Synthetic observations for everything structural; the production-data
# assertions at the bottom skip when the runtime store has not been generated.
# Run: `python -m unittest tests.test_canonical_financial_facts`
# ==========================================================================

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import canonical_fact_store as fact_store  # noqa: E402
import canonical_financial_facts as facts  # noqa: E402
import canonical_financial_resolvers as resolvers  # noqa: E402
import market_wide_calculation_readiness as readiness  # noqa: E402
from _runtime_root import runtime_path  # noqa: E402


def _observation(**overrides):
    """One layer-1 shaped observation. Only the fields layer 3 reads are populated."""
    record = {
        "schema_version": "1.0.0",
        "ticker": "TST",
        "provider": "VCI",
        "statement_family": "balance_sheet",
        "reporting_frequency": "quarter",
        "reporting_period": "2025-Q4",
        "period_type": "quarterly",
        "period_variant_index": 0,
        "period_column": "2025-Q4",
        "raw_item_id": "total_assets",
        "item_id_occurrence": 1,
        "row_ordinal": 0,
        "identity_key": "k",
        "observation_id": "o",
        "raw_label_vi": None,
        "raw_label_en": None,
        "raw_value": 1000,
        "scraped_at": "2026-07-21 19:31",
        "source_file": "TST_balance_sheet_quarter.parquet",
        "source_sha256": "deadbeef",
        "warnings": [],
    }
    record.update(overrides)
    record["observation_id"] = (
        f"{record['statement_family']}|{record['reporting_period']}|"
        f"{record['period_variant_index']}|{record['raw_item_id']}|"
        f"{record['item_id_occurrence']}")
    return record


def _balanced_sheet(period="2025-Q4", variant=0, **extra):
    """A balance sheet whose identity holds, with a non-zero minority interest."""
    rows = {"total_assets": 1000, "liabilities": 400, "owners_equity": 600,
            "minority_interests": 50, "cash_and_cash_equivalents": 100,
            "undistributed_earnings": 250, "short_term_borrowings": 120,
            "long_term_borrowings": 80}
    rows.update(extra)
    return [_observation(statement_family="balance_sheet", reporting_period=period,
                         period_variant_index=variant, raw_item_id=item, raw_value=value)
            for item, value in rows.items()]


def _income(period="2025-Q4", variant=0, dialect="vci_a", **extra):
    if dialect == "vci_a":
        rows = {"revenue": 900, "cost_of_goods_sold": 500, "gross_profit": 400,
                "profit_before_tax": 300, "net_profit": 240, "of_which_interest_expense": 30,
                "profit_after_tax_for_shareholders_of_parent_company": 220,
                "admin_expenses": 20}
    else:
        rows = {"net_sales": 900, "cost_of_sales": 500, "gross_profit": 400,
                "net_accounting_profit_loss_before_tax": 300,
                "net_profit_loss_after_tax": 240, "interest_expenses": 30,
                "attributable_to_parent_company": 220}
    rows.update(extra)
    return [_observation(statement_family="income_statement", reporting_period=period,
                         period_variant_index=variant, raw_item_id=item, raw_value=value)
            for item, value in rows.items()]


def _cash_flow(period="2025-Q4", dialect="vci_a", end_cash=100, **extra):
    if dialect == "vci_a":
        rows = {"depreciation_of_fixed_assets_and_investment_properties": 70,
                "operating_cash_flow": 150, "borrowing_costs": 30,
                "payment_for_fixed_assets_constructions_and_other_long_term_assets": 60}
    else:
        rows = {"depreciation_and_amortization": 70,
                "net_cash_inflows_outflows_from_operating_activities": 150,
                "interest_paid": 30,
                "purchases_of_fixed_assets_and_other_long_term_assets": 60}
    rows["cash_and_cash_equivalents_at_the_end_of_the_period"] = end_cash
    rows.update(extra)
    return [_observation(statement_family="cash_flow", reporting_period=period,
                         raw_item_id=item, raw_value=value)
            for item, value in rows.items()]


class ResolverEvidenceTests(unittest.TestCase):
    """Every resolver returns `unknown` unless the payload actually evidences the answer."""

    def test_non_zero_minority_interest_grants_consolidated(self):
        verdict = resolvers.resolve_statement_scope({"minority_interests": 50})
        self.assertEqual(verdict["statement_scope"], "consolidated")

    def test_zero_minority_interest_grants_nothing(self):
        verdict = resolvers.resolve_statement_scope({"minority_interests": 0})
        self.assertEqual(verdict["statement_scope"], resolvers.UNKNOWN)

    def test_absent_minority_interest_grants_nothing(self):
        self.assertEqual(
            resolvers.resolve_statement_scope({})["statement_scope"], resolvers.UNKNOWN)

    def test_sign_convention_from_gross_profit_identity(self):
        positive = resolvers.resolve_sign_convention(
            {"revenue": 900, "cost_of_goods_sold": 500, "gross_profit": 400})
        self.assertEqual(positive["sign_convention"], "expenses_positive")
        negative = resolvers.resolve_sign_convention(
            {"revenue": 900, "cost_of_goods_sold": -500, "gross_profit": 400})
        self.assertEqual(negative["sign_convention"], "expenses_negative")

    def test_sign_convention_unknown_when_identity_does_not_reconcile(self):
        verdict = resolvers.resolve_sign_convention(
            {"revenue": 900, "cost_of_goods_sold": 500, "gross_profit": 111})
        self.assertEqual(verdict["sign_convention"], resolvers.UNKNOWN)

    def test_sign_convention_unknown_when_a_term_is_missing(self):
        verdict = resolvers.resolve_sign_convention({"revenue": 900, "gross_profit": 400})
        self.assertEqual(verdict["sign_convention"], resolvers.UNKNOWN)

    def test_balance_identity_violation_is_reported(self):
        self.assertEqual(
            resolvers.resolve_balance_identity(
                {"total_assets": 1000, "liabilities": 400, "owners_equity": 599}
            )["balance_identity"], "violated")

    def test_cross_statement_scale_states(self):
        coherent = resolvers.resolve_cross_statement_scale(
            {"cash_and_cash_equivalents": 100},
            {"cash_and_cash_equivalents_at_the_end_of_the_period": 100})
        self.assertEqual(coherent["cross_statement_scale"], "coherent")
        rounded = resolvers.resolve_cross_statement_scale(
            {"cash_and_cash_equivalents": 100_500},
            {"cash_and_cash_equivalents_at_the_end_of_the_period": 101_000})
        self.assertEqual(rounded["cross_statement_scale"], "coherent_thousand_rounded")
        divergent = resolvers.resolve_cross_statement_scale(
            {"cash_and_cash_equivalents": 100_000},
            {"cash_and_cash_equivalents_at_the_end_of_the_period": 250_000})
        self.assertEqual(divergent["cross_statement_scale"], "divergent")

    def test_cross_statement_scale_unknown_without_both_lines(self):
        self.assertEqual(
            resolvers.resolve_cross_statement_scale({}, {})["cross_statement_scale"],
            resolvers.UNKNOWN)

    def test_cumulative_state_from_beginning_cash(self):
        ytd = resolvers.resolve_cumulative_state({
            "2025-Q1": {"cash_and_cash_equivalents_at_beginning_of_the_period": 10},
            "2025-Q2": {"cash_and_cash_equivalents_at_beginning_of_the_period": 10}})
        self.assertEqual(ytd["cumulative_state"], "cumulative_ytd")
        discrete = resolvers.resolve_cumulative_state({
            "2025-Q1": {"cash_and_cash_equivalents_at_beginning_of_the_period": 10},
            "2025-Q2": {"cash_and_cash_equivalents_at_beginning_of_the_period": 25}})
        self.assertEqual(discrete["cumulative_state"], "period_only")

    def test_cumulative_state_unknown_with_one_quarter(self):
        verdict = resolvers.resolve_cumulative_state({
            "2025-Q1": {"cash_and_cash_equivalents_at_beginning_of_the_period": 10}})
        self.assertEqual(verdict["cumulative_state"], resolvers.UNKNOWN)

    def test_currency_and_scale_need_an_official_citation(self):
        without = resolvers.resolve_currency_and_scale(None)
        self.assertEqual(without["currency"], resolvers.UNKNOWN)
        self.assertEqual(without["scale"], resolvers.UNKNOWN)
        with_citation = resolvers.resolve_currency_and_scale(
            {"agrees": True, "currency": "VND", "scale": "units", "citation_id": "c1"})
        self.assertEqual(with_citation["currency"], "VND")
        self.assertEqual(with_citation["authority"], "official_citation_agreement")

    def test_period_start_depends_on_the_cumulative_basis(self):
        self.assertEqual(resolvers.period_bounds("2025-Q3", "cumulative_ytd")["period_start"],
                         "2025-01-01")
        self.assertEqual(resolvers.period_bounds("2025-Q3", "period_only")["period_start"],
                         "2025-07-01")
        self.assertIsNone(resolvers.period_bounds("2025-Q3", "unknown")["period_start"])
        self.assertEqual(resolvers.period_bounds("2025-Q3", "unknown")["period_end"],
                         "2025-09-30")


class DialectTests(unittest.TestCase):
    """Dialect comes from the vocabulary, not from the payload's `source` column."""

    def test_both_cash_flow_dialects_map_to_the_same_canonical_metrics(self):
        wanted = ("depreciation_and_amortization", "operating_cash_flow",
                  "capital_expenditure", "interest_expense")
        resolved = {}
        for dialect in ("vci_a", "kbs_b"):
            built = facts.build_facts(
                "TST", [*_balanced_sheet(), *_income(dialect=dialect),
                        *_cash_flow(dialect=dialect)])
            resolved[dialect] = {
                fact["canonical_metric"]: fact["status"] for fact in built["facts"]
                if fact["canonical_metric"] in wanted
                and fact["status"] != facts.STATUS_UNAVAILABLE}
        for dialect in ("vci_a", "kbs_b"):
            for metric in wanted:
                self.assertIn(metric, resolved[dialect],
                              f"{metric} unresolved in dialect {dialect}")

    def test_dialect_detected_from_vocabulary_not_provider(self):
        # HPG's real shape: a payload whose `source` is KBS written in the VCI vocabulary.
        observations = _income(dialect="vci_a")
        for record in observations:
            record["provider"] = "KBS"
        self.assertEqual(
            facts.detect_dialect("income_statement",
                                 [record["raw_item_id"] for record in observations]),
            facts.DIALECT_VCI)
        built = facts.build_facts("TST", [*_balanced_sheet(), *observations])
        revenue = next(fact for fact in built["facts"]
                       if fact["canonical_metric"] == "revenue")
        self.assertNotEqual(revenue["status"], facts.STATUS_UNAVAILABLE)

    def test_mixed_vocabulary_is_reported(self):
        self.assertEqual(
            facts.detect_dialect("cash_flow",
                                 ["operating_cash_flow", "interest_paid"]), "mixed")


class FactStatusTests(unittest.TestCase):
    def test_provider_reported_is_the_ceiling_without_an_official_citation(self):
        built = facts.build_facts("TST", _balanced_sheet())
        total = next(f for f in built["facts"] if f["canonical_metric"] == "total_assets")
        self.assertEqual(total["status"], facts.STATUS_PROVIDER_REPORTED)
        self.assertEqual(total["currency"], resolvers.UNKNOWN)
        self.assertIn("currency_unknown", total["warnings"])

    def test_official_citation_agreement_promotes_to_qualified(self):
        built = facts.build_facts(
            "TST", _balanced_sheet(),
            official_citations={("TST", "total_assets", "2025-Q4"): {
                "citation_id": "c1", "value": 1000, "currency": "VND", "scale": "units"}})
        total = next(f for f in built["facts"] if f["canonical_metric"] == "total_assets")
        self.assertEqual(total["status"], facts.STATUS_QUALIFIED)
        self.assertEqual(total["currency"], "VND")
        self.assertEqual(total["unit_authority"], "official_citation_agreement")

    def test_official_citation_disagreement_is_a_conflict_not_an_override(self):
        built = facts.build_facts(
            "TST", _balanced_sheet(),
            official_citations={("TST", "total_assets", "2025-Q4"): {
                "citation_id": "c1", "value": 999, "currency": "VND", "scale": "units"}})
        total = next(f for f in built["facts"] if f["canonical_metric"] == "total_assets")
        self.assertEqual(total["status"], facts.STATUS_CONFLICTED)
        self.assertEqual(total["conflicts"][0]["kind"], "official_citation_disagrees")

    def test_label_match_alone_never_upgrades_a_status(self):
        built = facts.build_facts("TST", _balanced_sheet())
        for fact in built["facts"]:
            if fact["status"] == facts.STATUS_QUALIFIED:
                self.fail("a label match produced `qualified` with no official citation")

    def test_restated_period_column_disagreement_is_a_conflict(self):
        primary = _balanced_sheet()
        restated = _balanced_sheet(variant=1, total_assets=1234)
        built = facts.build_facts("TST", [*primary, *restated])
        total = next(f for f in built["facts"] if f["canonical_metric"] == "total_assets")
        self.assertEqual(total["status"], facts.STATUS_CONFLICTED)
        self.assertEqual(total["conflicts"][0]["kind"], "restated_period_column_disagrees")

    def test_balance_identity_violation_conflicts_balance_sheet_metrics(self):
        rows = _balanced_sheet(owners_equity=599)
        built = facts.build_facts("TST", rows)
        total = next(f for f in built["facts"] if f["canonical_metric"] == "total_assets")
        self.assertEqual(total["status"], facts.STATUS_CONFLICTED)

    def test_cash_flow_period_attribution_gate(self):
        # Balance-sheet cash and cash-flow end cash disagree: the cash-flow payload's period
        # label is not confirmed, so its facts are conflicted rather than blended.
        built = facts.build_facts(
            "TST", [*_balanced_sheet(), *_income(), *_cash_flow(end_cash=999_999)])
        depreciation = next(f for f in built["facts"]
                            if f["canonical_metric"] == "depreciation")
        self.assertEqual(depreciation["status"], facts.STATUS_CONFLICTED)
        self.assertEqual(depreciation["conflicts"][0]["kind"],
                         "cash_flow_period_attribution_unverified")

    def test_unverifiable_cash_flow_attribution_caps_at_partial(self):
        cash_flow = [record for record in _cash_flow()
                     if "at_the_end_of_the_period" not in record["raw_item_id"]]
        built = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *cash_flow])
        depreciation = next(f for f in built["facts"]
                            if f["canonical_metric"] == "depreciation")
        self.assertEqual(depreciation["status"], facts.STATUS_PARTIAL)
        self.assertIn("cash_flow_period_attribution_unverifiable", depreciation["warnings"])

    def test_concept_substitution_forces_partial(self):
        income = [record for record in _income()
                  if record["raw_item_id"] != "of_which_interest_expense"]
        built = facts.build_facts("TST", [*_balanced_sheet(), *income, *_cash_flow()])
        interest = next(f for f in built["facts"]
                        if f["canonical_metric"] == "interest_expense")
        self.assertEqual(interest["status"], facts.STATUS_PARTIAL)
        self.assertIn("concept_substitution", interest["warnings"])

    def test_shares_outstanding_is_unavailable_with_a_stated_reason(self):
        built = facts.build_facts("TST", _balanced_sheet())
        shares = next(f for f in built["facts"]
                      if f["canonical_metric"] == "shares_outstanding")
        self.assertEqual(shares["status"], facts.STATUS_UNAVAILABLE)
        self.assertIn("par value", shares["reason"])

    def test_derived_total_debt_sums_its_components(self):
        built = facts.build_facts("TST", _balanced_sheet())
        total = next(f for f in built["facts"]
                     if f["canonical_metric"] == "total_interest_bearing_debt")
        self.assertEqual(total["value"], 200)
        self.assertEqual(total["derived_from"],
                         ["short_term_interest_bearing_debt",
                          "long_term_interest_bearing_debt"])

    def test_derivation_blocked_when_a_component_is_missing(self):
        rows = [record for record in _balanced_sheet()
                if record["raw_item_id"] != "long_term_borrowings"]
        built = facts.build_facts("TST", rows)
        total = next(f for f in built["facts"]
                     if f["canonical_metric"] == "total_interest_bearing_debt")
        self.assertEqual(total["status"], facts.STATUS_UNAVAILABLE)
        self.assertIn("long_term_interest_bearing_debt", total["reason"])

    def test_revenue_resolves_to_the_reconciling_net_line(self):
        rows = [
            _observation(statement_family="income_statement", raw_item_id="revenue",
                         item_id_occurrence=1, row_ordinal=0, raw_value=1000),
            _observation(statement_family="income_statement",
                         raw_item_id="deduction_from_revenue", row_ordinal=1, raw_value=100),
            _observation(statement_family="income_statement", raw_item_id="revenue",
                         item_id_occurrence=2, row_ordinal=2, raw_value=900),
        ]
        built = facts.build_facts("TST", [*_balanced_sheet(), *rows])
        revenue = next(f for f in built["facts"] if f["canonical_metric"] == "revenue")
        self.assertEqual(revenue["value"], 900)
        self.assertIn("revenue_net_of_deductions_reconciled", revenue["warnings"])

    def test_revenue_derived_when_no_net_line_is_retained(self):
        rows = [
            _observation(statement_family="income_statement", raw_item_id="revenue",
                         item_id_occurrence=1, row_ordinal=0, raw_value=1000),
            _observation(statement_family="income_statement",
                         raw_item_id="deduction_from_revenue", row_ordinal=1, raw_value=100),
        ]
        built = facts.build_facts("TST", [*_balanced_sheet(), *rows])
        revenue = next(f for f in built["facts"] if f["canonical_metric"] == "revenue")
        self.assertEqual(revenue["value"], 900)
        self.assertEqual(revenue["status"], facts.STATUS_PARTIAL)


class MalformedInputTests(unittest.TestCase):
    def test_empty_observation_set_yields_no_facts(self):
        built = facts.build_facts("TST", [])
        self.assertEqual(built["facts"], [])
        self.assertEqual(built["reporting_periods"], [])

    def test_non_numeric_value_does_not_raise(self):
        rows = _balanced_sheet()
        rows[0]["raw_value"] = "not-a-number"
        built = facts.build_facts("TST", rows)
        self.assertTrue(built["facts"])

    def test_unknown_period_label_yields_no_period_start(self):
        bounds = resolvers.period_bounds("not-a-period", "period_only")
        self.assertIsNone(bounds["period_start"])
        self.assertIsNone(bounds["period_end"])

    def test_vietnamese_number_parser_rejects_damaged_grouping(self):
        from corporate_action_events import parse_vietnamese_number
        self.assertEqual(parse_vietnamese_number("767.498.665"), 767498665.0)
        self.assertIsNone(parse_vietnamese_number("8.M2.964.520"))
        self.assertIsNone(parse_vietnamese_number("2.96"))
        self.assertIsNone(parse_vietnamese_number(""))


class ApplicabilityTests(unittest.TestCase):
    def test_bank_receives_not_applicable_for_ebitda(self):
        applicability = {"metric_applicability": {
            "ebitda": {"status": "not_applicable", "authority": "manual_profile",
                       "reason": "issuer is a bank", "substitute_metrics": ["p_b", "roe"]}}}
        verdict = readiness.evaluate_ebitda({}, "2025-Q4", applicability)
        self.assertEqual(verdict["readiness"], readiness.NOT_APPLICABLE)
        self.assertEqual(verdict["status"], facts.STATUS_NOT_APPLICABLE)

    def test_ev_ebitda_inherits_not_applicable(self):
        applicability = {"metric_applicability": {
            "ebitda": {"status": "not_applicable", "authority": "manual_profile",
                       "reason": "issuer is a bank", "substitute_metrics": []}}}
        ebitda = readiness.evaluate_ebitda({}, "2025-Q4", applicability)
        market_cap = readiness.evaluate_market_capitalisation("2025-Q4")
        enterprise = readiness.evaluate_enterprise_value({}, "2025-Q4", market_cap)
        verdict = readiness.evaluate_ev_ebitda(ebitda, enterprise, "2025-Q4")
        self.assertEqual(verdict["readiness"], readiness.NOT_APPLICABLE)


class CalculationReadinessTests(unittest.TestCase):
    def _facts_for(self, **kwargs):
        built = facts.build_facts(
            "TST", [*_balanced_sheet(), *_income(), *_cash_flow(**kwargs)])
        return {fact["canonical_metric"]: fact for fact in built["facts"]
                if fact["reporting_period"] == "2025-Q4"}

    def test_ebitda_ready_with_lineage(self):
        verdict = readiness.evaluate_ebitda(self._facts_for(), "2025-Q4", {})
        self.assertEqual(verdict["readiness"], readiness.READY)
        self.assertEqual(verdict["value"], 400)          # 300 + 30 + 70
        self.assertEqual(verdict["formula"], readiness.EBITDA_FORMULA)
        self.assertEqual(set(verdict["terms"]), set(readiness.EBITDA_TERMS))
        for term in verdict["terms"].values():
            self.assertTrue(term["fact_id"])
            self.assertTrue(term["source_observation_ids"])

    def test_ebitda_blocked_when_cash_flow_period_is_unattributable(self):
        verdict = readiness.evaluate_ebitda(self._facts_for(end_cash=999_999), "2025-Q4", {})
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertTrue(any("depreciation_and_amortization" in reason
                            for reason in verdict["blocked_by"]))

    def test_ebitda_blocked_when_the_sign_convention_is_unknown(self):
        income = [record for record in _income() if record["raw_item_id"] != "gross_profit"]
        built = facts.build_facts("TST", [*_balanced_sheet(), *income, *_cash_flow()])
        period_facts = {fact["canonical_metric"]: fact for fact in built["facts"]
                        if fact["reporting_period"] == "2025-Q4"}
        verdict = readiness.evaluate_ebitda(period_facts, "2025-Q4", {})
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertIn("sign_convention_unknown", verdict["blocked_by"])

    def test_market_capitalisation_names_both_blockers(self):
        verdict = readiness.evaluate_market_capitalisation("2025-Q4")
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertEqual(set(verdict["blocked_by"]), set(readiness.MARKET_CAP_BLOCKERS))

    def test_enterprise_value_blocked_but_components_reported(self):
        market_cap = readiness.evaluate_market_capitalisation("2025-Q4")
        verdict = readiness.evaluate_enterprise_value(self._facts_for(), "2025-Q4", market_cap)
        self.assertEqual(verdict["readiness"], readiness.BLOCKED)
        self.assertTrue(verdict["terms"]["balance_sheet_components_ready"])

    def test_roe_ready_and_never_annualised(self):
        verdict = readiness.evaluate_roe(self._facts_for(), "2025-Q4")
        self.assertEqual(verdict["readiness"], readiness.READY)
        self.assertAlmostEqual(verdict["value"], 240 / 600)
        self.assertIn("single_period_ratio_not_annualised", verdict["warnings"])

    def test_price_ratios_blocked_but_denominator_state_reported(self):
        period_facts = self._facts_for()
        market_cap = readiness.evaluate_market_capitalisation("2025-Q4")
        pb = readiness.evaluate_price_ratio("pb", period_facts.get("shareholders_equity"),
                                            "2025-Q4", market_cap, "shareholders_equity")
        self.assertEqual(pb["readiness"], readiness.BLOCKED)
        self.assertTrue(pb["terms"]["denominator_ready"])

    def test_snapshot_market_cap_would_not_unlock_series_capabilities(self):
        for capability in ("adjusted_return", "backtest", "beta", "volatility"):
            self.assertIn(capability, readiness.STILL_BLOCKED_BY_PRICE_BASIS)


class FactStoreTests(unittest.TestCase):
    def test_shard_bytes_are_deterministic(self):
        built = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *_cash_flow()])
        first = fact_store.encode_shard(built["facts"])
        second = fact_store.encode_shard(built["facts"])
        self.assertEqual(first, second)
        self.assertEqual(fact_store.decode_shard(first), built["facts"])

    def test_double_build_is_byte_identical(self):
        one = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *_cash_flow()])
        two = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *_cash_flow()])
        self.assertEqual(fact_store.encode_shard(one["facts"]),
                         fact_store.encode_shard(two["facts"]))

    def test_inputs_fingerprint_covers_the_mapper_version(self):
        applicability = {"archetype": {"template_family": None, "issuer_entity_type": None}}
        baseline = fact_store._inputs_fingerprint("abc", applicability)
        original = facts.MAPPER_VERSION
        try:
            fact_store.MAPPER_VERSION = "9.9.9"
            moved = fact_store._inputs_fingerprint("abc", applicability)
        finally:
            fact_store.MAPPER_VERSION = original
        self.assertNotEqual(baseline, moved,
                            "a mapper-version change must invalidate every shard")

    def test_queues_are_per_metric_never_per_ticker(self):
        built = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *_cash_flow()])
        rows = fact_store.build_unresolved_queue(built["facts"])
        for row in rows:
            self.assertIn("canonical_metric", row)
            self.assertIn(row["status"], fact_store.UNRESOLVED_STATUSES)
        self.assertNotIn("not_applicable", {row["status"] for row in rows})

    def test_conflict_queue_carries_both_values(self):
        built = facts.build_facts("TST", [*_balanced_sheet(),
                                          *_balanced_sheet(variant=1, total_assets=1234)])
        rows = fact_store.build_conflict_queue(built["facts"])
        self.assertTrue(rows)
        detail = rows[0]["detail"]
        self.assertIn("primary_value", detail)
        self.assertIn("variant_value", detail)

    def test_coverage_breaks_down_by_dialect(self):
        built = facts.build_facts("TST", [*_balanced_sheet(), *_income(), *_cash_flow()])
        coverage = fact_store.build_coverage(built["facts"], [])
        by_metric = {entry["canonical_metric"]: entry for entry in coverage["by_metric"]}
        self.assertTrue(by_metric["operating_cash_flow"]["by_dialect"])


class ProductionStoreTests(unittest.TestCase):
    """Assertions against the generated runtime store; skipped when it is absent."""

    def setUp(self):
        self.runtime_root = runtime_path("data/canonical-financial-facts/ingest_state.json")

    def test_store_state_is_self_consistent(self):
        state = json.loads(Path(self.runtime_root).read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], fact_store.STORE_SCHEMA_VERSION)
        self.assertEqual(state["ticker_count"], len(state["tickers"]))
        self.assertEqual(state["fact_count"],
                         sum(record["fact_count"] for record in state["tickers"]))

    def test_every_fact_carries_the_contract_dimensions(self):
        root = Path(self.runtime_root).parent
        required = ("ticker", "provider", "source_file", "source_sha256", "raw_item_id",
                    "statement_family", "reporting_period", "period_start", "period_end",
                    "reporting_frequency", "statement_scope", "currency", "scale",
                    "sign_convention", "cumulative_state", "observed_at", "mapper_version",
                    "contract_version", "confidence", "status", "reason", "warnings",
                    "conflicts")
        shard = next(iter(sorted((root / "facts").glob("*.jsonl.gz"))), None)
        if shard is None:
            self.skipTest("canonical fact store has not been generated")
        for record in fact_store.decode_shard(shard.read_bytes())[:50]:
            for field in required:
                self.assertIn(field, record)
            self.assertIn(record["status"], facts.SUPPORTED_STATUSES)


if __name__ == "__main__":
    unittest.main()
