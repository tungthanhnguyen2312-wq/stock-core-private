"""Unit tests for Phase 2 / P2-A: Multi-Period Financial Fact Panel & Sector Applicability Contract."""

from __future__ import annotations

import copy
import json
import unittest

from multi_period_financial_panel import (
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    ARTIFACT_TYPE,
    ApplicabilityState,
    PeriodType,
    QualificationState,
    SectorArchetype,
    StatementFamily,
    StatementScope,
    TemporalNature,
    build_issuer_multi_period_panel,
    build_multi_period_financial_panel,
    construct_financial_fact,
    evaluate_sector_applicability,
)


class TestMultiPeriodFinancialPanel(unittest.TestCase):

    def setUp(self):
        # Sample verified citations for HPG across 3 fiscal years (VND)
        self.hpg_citations = [
            # 2022
            {
                "ticker": "HPG", "metric": "net_income", "reporting_period": "2022",
                "value": 8444429054516, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ni_2022",
                "evidence_id": "e_hpg_2022", "published_at": "2023-03-30",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "operating_cash_flow", "reporting_period": "2022",
                "value": 12277636676507, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ocf_2022",
                "evidence_id": "e_hpg_2022", "published_at": "2023-03-30",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "shareholders_equity", "reporting_period": "2022",
                "value": 96112939615783, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_eq_2022",
                "evidence_id": "e_hpg_2022", "published_at": "2023-03-30",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "total_interest_bearing_debt", "reporting_period": "2022",
                "value": 57900321604873, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_debt_2022",
                "evidence_id": "e_hpg_2022", "published_at": "2023-03-30",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "cash_and_equivalents", "reporting_period": "2022",
                "value": 8324588920227, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_cash_2022",
                "evidence_id": "e_hpg_2022", "published_at": "2023-03-30",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            # 2023
            {
                "ticker": "HPG", "metric": "net_income", "reporting_period": "2023",
                "value": 6800388315081, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ni_2023",
                "evidence_id": "e_hpg_2023", "published_at": "2024-03-28",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "operating_cash_flow", "reporting_period": "2023",
                "value": 8643030777026, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ocf_2023",
                "evidence_id": "e_hpg_2023", "published_at": "2024-03-28",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "shareholders_equity", "reporting_period": "2023",
                "value": 102836419239379, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_eq_2023",
                "evidence_id": "e_hpg_2023", "published_at": "2024-03-28",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "total_interest_bearing_debt", "reporting_period": "2023",
                "value": 65381002473117, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_debt_2023",
                "evidence_id": "e_hpg_2023", "published_at": "2024-03-28",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "cash_and_equivalents", "reporting_period": "2023",
                "value": 12252001160884, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_cash_2023",
                "evidence_id": "e_hpg_2023", "published_at": "2024-03-28",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            # 2024
            {
                "ticker": "HPG", "metric": "net_income", "reporting_period": "2024",
                "value": 11986478931123, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ni_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "operating_cash_flow", "reporting_period": "2024",
                "value": 14500000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_ocf_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "shareholders_equity", "reporting_period": "2024",
                "value": 115000000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_eq_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "total_interest_bearing_debt", "reporting_period": "2024",
                "value": 70000000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_debt_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "HPG", "metric": "cash_and_equivalents", "reporting_period": "2024",
                "value": 15000000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_hpg_cash_2024",
                "evidence_id": "e_hpg_2024", "published_at": "2025-03-24",
                "verified_at": "2026-08-09T00:00:00Z",
            },
        ]

        # PVD citations in USD
        self.pvd_citations = [
            {
                "ticker": "PVD", "metric": "net_income", "reporting_period": "2023",
                "value": 23061808, "currency": "USD", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_pvd_ni_2023",
                "evidence_id": "e_pvd_2023", "published_at": "2024-03-25",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "PVD", "metric": "shareholders_equity", "reporting_period": "2023",
                "value": 618694250, "currency": "USD", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_pvd_eq_2023",
                "evidence_id": "e_pvd_2023", "published_at": "2024-03-25",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "PVD", "metric": "total_interest_bearing_debt", "reporting_period": "2023",
                "value": 138747285, "currency": "USD", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_pvd_debt_2023",
                "evidence_id": "e_pvd_2023", "published_at": "2024-03-25",
                "verified_at": "2026-08-09T00:00:00Z",
            },
        ]

        self.entity_profiles = {
            "HPG": "corporate",
            "PVD": "corporate",
            "VCB": "bank",
            "SSI": "securities",
        }

    def test_deterministic_panel_ordering_and_hash(self):
        """Panel generation must be pure, sorted, and produce byte-identical SHA-256 hashes."""
        p1 = build_multi_period_financial_panel(
            issuers=["PVD", "HPG"],
            citations=self.hpg_citations + self.pvd_citations,
            entity_profiles=self.entity_profiles,
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T14:00:00Z",
        )
        p2 = build_multi_period_financial_panel(
            issuers=["HPG", "PVD"],  # Inverted order
            citations=self.pvd_citations + self.hpg_citations,  # Inverted citations
            entity_profiles=self.entity_profiles,
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T14:00:00Z",
        )
        self.assertEqual(p1["content_hash"], p2["content_hash"])
        self.assertEqual(p1["issuers_represented"], ["HPG", "PVD"])

    def test_annual_vs_quarterly_distinction(self):
        """Annual periods are flagged as annual, quarterly as quarterly."""
        f_annual = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation=self.hpg_citations[-5],
            entity_type="corporate",
        )
        self.assertEqual(f_annual.period_type, PeriodType.ANNUAL.value)
        self.assertEqual(f_annual.period_start, "2024-01-01")
        self.assertEqual(f_annual.period_end, "2024-12-31")

        f_quarter = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024-Q3",
            raw_citation={"value": 3000000000000, "period_start": "2024-07-01", "period_end": "2024-09-30"},
            entity_type="corporate",
        )
        self.assertEqual(f_quarter.period_type, PeriodType.QUARTERLY.value)
        self.assertEqual(f_quarter.period_start, "2024-07-01")
        self.assertEqual(f_quarter.period_end, "2024-09-30")

    def test_instant_vs_duration_distinction(self):
        """Balance sheet items must be INSTANT; income statement & cash flow must be DURATION."""
        f_bs = construct_financial_fact(
            ticker="HPG",
            metric="cash_and_equivalents",
            reporting_period="2024",
            raw_citation=self.hpg_citations[-1],
            entity_type="corporate",
        )
        self.assertEqual(f_bs.temporal_nature, TemporalNature.INSTANT.value)
        self.assertEqual(f_bs.statement_family, StatementFamily.BALANCE_SHEET.value)

        f_is = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation=self.hpg_citations[-5],
            entity_type="corporate",
        )
        self.assertEqual(f_is.temporal_nature, TemporalNature.DURATION.value)
        self.assertEqual(f_is.statement_family, StatementFamily.INCOME_STATEMENT.value)

    def test_consolidated_vs_separate_isolation(self):
        """Statement scope is explicitly preserved and not mixed."""
        f_cons = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation={"value": 100, "statement_scope": "consolidated"},
            entity_type="corporate",
        )
        self.assertEqual(f_cons.statement_scope, StatementScope.CONSOLIDATED.value)

        f_sep = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation={"value": 80, "statement_scope": "separate"},
            entity_type="corporate",
        )
        self.assertEqual(f_sep.statement_scope, StatementScope.SEPARATE.value)

    def test_currency_preservation_and_no_mixing(self):
        """Currencies are preserved per issuer and cannot be silently mixed in calculations."""
        panel_hpg = build_issuer_multi_period_panel(
            ticker="HPG",
            citations=self.hpg_citations,
            entity_type="corporate",
        )
        panel_pvd = build_issuer_multi_period_panel(
            ticker="PVD",
            citations=self.pvd_citations,
            entity_type="corporate",
        )

        hpg_curr = next(f["currency"] for f in panel_hpg["facts"] if f["canonical_metric"] == "net_income")
        pvd_curr = next(f["currency"] for f in panel_pvd["facts"] if f["canonical_metric"] == "net_income")
        self.assertEqual(hpg_curr, "VND")
        self.assertEqual(pvd_curr, "USD")

        # PVD net debt is computed in USD
        pvd_derived_2023 = panel_pvd["derived_metrics"]["2023"]
        self.assertIn("debt_to_equity", pvd_derived_2023)
        self.assertEqual(pvd_derived_2023["debt_to_equity"]["status"], "QUALIFIED")

    def test_no_silent_forward_fill(self):
        """Missing period facts remain MISSING and are not silently carried forward."""
        panel = build_issuer_multi_period_panel(
            ticker="PVD",
            citations=self.pvd_citations,
            entity_type="corporate",
            target_periods=["2022", "2023"],  # 2022 has no citations in sample
        )
        # 2022 facts must be MISSING
        facts_2022 = [f for f in panel["facts"] if f["reporting_period"] == "2022"]
        for f in facts_2022:
            self.assertEqual(f["qualification_state"], QualificationState.MISSING.value)
            self.assertIsNone(f["value"])
            self.assertEqual(f["temporal_envelope"]["freshness_status"], "missing")

    def test_temporal_safety_and_lookahead_rejection(self):
        """Facts published after reference_at must be flagged as LOOKAHEAD_VIOLATION and not pit_eligible."""
        f_safe = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation=self.hpg_citations[-5],  # Published 2025-03-24
            entity_type="corporate",
            reference_at="2025-04-01T00:00:00Z",  # Evaluated after publication
        )
        self.assertTrue(f_safe.temporal_envelope["pit_eligible"])
        self.assertEqual(f_safe.temporal_envelope["pit_status"], "QUALIFIED")

        f_lookahead = construct_financial_fact(
            ticker="HPG",
            metric="net_income",
            reporting_period="2024",
            raw_citation=self.hpg_citations[-5],  # Published 2025-03-24
            entity_type="corporate",
            reference_at="2025-01-15T00:00:00Z",  # Evaluated BEFORE publication -> Lookahead!
        )
        self.assertFalse(f_lookahead.temporal_envelope["pit_eligible"])
        self.assertEqual(f_lookahead.temporal_envelope["pit_status"], "LOOKAHEAD_VIOLATION")
        self.assertIn("LOOKAHEAD_VIOLATION_PUBLISHED_AFTER_REFERENCE", f_lookahead.reason_codes)

    def test_sector_applicability_corporate_vs_bank_vs_securities(self):
        """Corporate debt ratios are APPLICABLE for corporate, NOT_APPLICABLE for bank and broker."""
        # Corporate (HPG)
        app_corp, reasons_corp = evaluate_sector_applicability(
            ticker="HPG",
            entity_type="corporate",
            canonical_metric="debt_to_equity",
        )
        self.assertEqual(app_corp, ApplicabilityState.APPLICABLE)
        self.assertIn("CORPORATE_DEBT_RATIO_APPLICABLE", reasons_corp)

        # Bank (VCB)
        app_bank, reasons_bank = evaluate_sector_applicability(
            ticker="VCB",
            entity_type="bank",
            canonical_metric="debt_to_equity",
        )
        self.assertEqual(app_bank, ApplicabilityState.NOT_APPLICABLE)
        self.assertIn("SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO", reasons_bank)

        # Broker (SSI)
        app_sec, reasons_sec = evaluate_sector_applicability(
            ticker="SSI",
            entity_type="securities",
            canonical_metric="debt_to_equity",
        )
        self.assertEqual(app_sec, ApplicabilityState.NOT_APPLICABLE)
        self.assertIn("SECTOR_INAPPROPRIATE_FINANCIAL_INTERMEDIARY_DEBT_RATIO", reasons_sec)

    def test_bank_derived_metrics_fail_closed(self):
        """Bank issuers have corporate debt metrics marked as NOT_APPLICABLE in derived metrics."""
        vcb_citations = [
            {
                "ticker": "VCB", "metric": "net_income", "reporting_period": "2024",
                "value": 33000000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_vcb_ni",
                "evidence_id": "e_vcb", "published_at": "2025-04-20",
                "verified_at": "2026-08-09T00:00:00Z",
            },
            {
                "ticker": "VCB", "metric": "shareholders_equity", "reporting_period": "2024",
                "value": 170000000000000, "currency": "VND", "unit_scale": 1,
                "statement_scope": "consolidated", "citation_id": "c_vcb_eq",
                "evidence_id": "e_vcb", "published_at": "2025-04-20",
                "verified_at": "2026-08-09T00:00:00Z",
            },
        ]
        panel = build_issuer_multi_period_panel(
            ticker="VCB",
            citations=vcb_citations,
            entity_type="bank",
        )
        d_2024 = panel["derived_metrics"]["2024"]
        self.assertEqual(d_2024["debt_to_equity"]["status"], "NOT_APPLICABLE")
        self.assertEqual(d_2024["net_debt"]["status"], "NOT_APPLICABLE")
        self.assertEqual(d_2024["roe_proxy"]["status"], "QUALIFIED")

    def test_missing_fact_isolation_blocks_only_dependent_metric(self):
        """Missing OCF blocks cash flow coverage and OCF growth, but Net Income growth and D/E remain qualified."""
        # Citation set with missing OCF in 2024
        citations = [c for c in self.hpg_citations if not (c["reporting_period"] == "2024" and c["metric"] == "operating_cash_flow")]
        panel = build_issuer_multi_period_panel(
            ticker="HPG",
            citations=citations,
            entity_type="corporate",
        )
        d_2024 = panel["derived_metrics"]["2024"]

        # Net income growth remains qualified
        self.assertIn("net_income_growth_yoy", d_2024)
        self.assertEqual(d_2024["net_income_growth_yoy"]["status"], "QUALIFIED")

        # Debt to equity remains qualified
        self.assertIn("debt_to_equity", d_2024)
        self.assertEqual(d_2024["debt_to_equity"]["status"], "QUALIFIED")

        # OCF metrics are blocked / absent
        self.assertNotIn("cash_flow_to_net_income", d_2024)
        self.assertNotIn("operating_cash_flow_growth_yoy", d_2024)

    def test_blocked_governance_capabilities(self):
        """Valuation, DCF, intrinsic value, and strategy ranking must be strictly BLOCKED."""
        panel = build_issuer_multi_period_panel(
            ticker="HPG",
            citations=self.hpg_citations,
            entity_type="corporate",
        )
        blocked = panel["blocked_capabilities"]
        self.assertEqual(blocked["valuation"]["status"], "BLOCKED")
        self.assertEqual(blocked["intrinsic_value"]["status"], "BLOCKED")
        self.assertEqual(blocked["cross_sectional_ranking"]["status"], "BLOCKED")
        self.assertEqual(blocked["execution_sizing"]["status"], "BLOCKED")

    def test_multi_period_growth_calculation_precision(self):
        """HPG Net Income YoY growth from 2022 to 2023 and 2023 to 2024 is mathematically exact."""
        panel = build_issuer_multi_period_panel(
            ticker="HPG",
            citations=self.hpg_citations,
            entity_type="corporate",
            target_periods=["2022", "2023", "2024"],
        )
        # 2022 has no prior period
        self.assertNotIn("net_income_growth_yoy", panel["derived_metrics"]["2022"])

        # 2023 YoY: (6,800,388,315,081 - 8,444,429,054,516) / 8,444,429,054,516 = -0.1947 (-19.47%)
        g_2023 = panel["derived_metrics"]["2023"]["net_income_growth_yoy"]
        self.assertEqual(g_2023["status"], "QUALIFIED")
        self.assertAlmostEqual(g_2023["value"], -0.1947, places=3)

        # 2024 YoY: (11,986,478,931,123 - 6,800,388,315,081) / 6,800,388,315,081 = +0.7626 (+76.26%)
        g_2024 = panel["derived_metrics"]["2024"]["net_income_growth_yoy"]
        self.assertEqual(g_2024["status"], "QUALIFIED")
        self.assertAlmostEqual(g_2024["value"], 0.7626, places=3)


if __name__ == "__main__":
    unittest.main()
