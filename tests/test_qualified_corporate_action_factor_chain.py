"""Tests for qualified_corporate_action_factor_chain.py.

All ledger-entry fixtures here are SYNTHETIC (ticker "TST") and built through the real
``official_corporate_action_ledger.build_ledger()`` machinery so the ledger's own fail-closed
rules (executed lifecycle, explicit ex-date, share-count corroboration) are exercised for real --
only the *evidence values* are synthetic, not the adapter logic under test. One test
(``RealEvidenceCeilingTests``) uses real field values frozen from retained evidence instead.
"""
import unittest

import official_corporate_action_ledger as ledger
import qualified_corporate_action_factor_chain as factor_chain


def _observation(event_type="stock_dividend", **overrides):
    record = {
        "observation_id": "o1", "ticker": "TST", "event_type": event_type,
        "lifecycle_state": "executed", "document_id": "d1", "document_type": "listing_change_notice",
        "source_authority": "HNX", "source_url": "https://www.hnx.vn/a",
        "content_sha256": "a" * 64, "announcement_date": "2026-07-07",
        "ex_date": None, "record_date": None, "payment_or_execution_date": "2026-07-02",
        "trading_date": "2026-07-15", "shares_before": None, "shares_issued": 767_498_665,
        "shares_after": 8_442_964_520, "cash_amount_per_share": None,
        "stock_ratio": 0.0999937567, "ratio_basis": "new_shares_per_existing_share",
        "rights_ratio": None, "subscription_price": None, "approval_date": None,
        "citations": [], "absent_fields": {}, "warnings": [],
    }
    record.update(overrides)
    return record


def _entry(**overrides):
    return ledger.build_ledger([_observation(**overrides)])["entries"][0]


class ClassificationTests(unittest.TestCase):
    def test_explicit_ex_date_is_accepted(self):
        classification, reasons = factor_chain.classify_ledger_entry(_entry(ex_date="2026-06-20"))
        self.assertEqual(classification, factor_chain.CLASSIFICATION_FACTOR_CHAIN_QUALIFIED)
        self.assertEqual(reasons, [])

    def test_record_date_cannot_substitute_for_ex_date(self):
        entry = _entry(record_date="2026-06-18")
        self.assertIsNone(entry["ex_date"])
        classification, reasons = factor_chain.classify_ledger_entry(entry)
        self.assertEqual(classification, factor_chain.CLASSIFICATION_MISSING_EXPLICIT_EX_DATE)
        self.assertIn(factor_chain.REASON_RECORD_DATE_NOT_EX_DATE, reasons)
        self.assertIn(factor_chain.REASON_MISSING_EXPLICIT_EX_DATE, reasons)
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        self.assertEqual(built["status"], factor_chain.STATUS_NOT_QUALIFIED)
        self.assertIsNone(built["identity"])

    def test_planned_issuance_is_not_executed(self):
        entry = _entry(ex_date="2026-06-20", lifecycle_state="announced")
        classification, _ = factor_chain.classify_ledger_entry(entry)
        self.assertEqual(classification, factor_chain.CLASSIFICATION_NOT_EXECUTED)
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        self.assertEqual(built["status"], factor_chain.STATUS_NOT_QUALIFIED)

    def test_conflicting_documents_block_qualification(self):
        issuer = _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                              shares_after=9_000_000_000, ex_date="2026-06-20")
        built = ledger.build_ledger([_observation(ex_date="2026-06-20"), issuer])
        entry = built["entries"][0]
        self.assertEqual(entry["conflict_status"], "conflicted")
        classification, _ = factor_chain.classify_ledger_entry(entry)
        self.assertEqual(classification, factor_chain.CLASSIFICATION_CONFLICTING)

    def test_cash_dividend_is_factor_not_applicable(self):
        entry = _entry(event_type="cash_dividend", ex_date="2026-06-20")
        classification, _ = factor_chain.classify_ledger_entry(entry)
        self.assertEqual(classification, factor_chain.CLASSIFICATION_FACTOR_NOT_APPLICABLE)

    def test_missing_stock_ratio_is_other_evidence_gap(self):
        entry = _entry(ex_date="2026-06-20", stock_ratio=None)
        self.assertEqual(entry["adjustment_factor_status"], ledger.FACTOR_NOT_READY)
        classification, reasons = factor_chain.classify_ledger_entry(entry)
        self.assertEqual(classification, factor_chain.CLASSIFICATION_OTHER_EVIDENCE_GAP)
        self.assertIn("missing_stock_ratio", reasons)


class FactorChainBuildTests(unittest.TestCase):
    def test_qualified_factor_retained_exactly(self):
        entry = _entry(ex_date="2026-06-20")
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        self.assertEqual(built["status"], factor_chain.STATUS_QUALIFIED)
        self.assertEqual(built["adjustment_factor"], entry["adjustment_factor"])
        self.assertAlmostEqual(built["adjustment_factor"], 1 / 1.0999937567, places=9)
        self.assertEqual(built["official_execution_status"], "EXECUTED")
        self.assertEqual(built["ex_date_status"], "EXPLICIT_OFFICIAL")
        self.assertEqual(built["event_types"], ["stock_dividend"])
        self.assertIsNotNone(built["identity"])
        self.assertEqual(built["identity"], built["factor_chain_identity"])

    def test_missing_knowledge_cutoff_blocks_qualification(self):
        entry = _entry(ex_date="2026-06-20")
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff=None)
        self.assertEqual(built["status"], factor_chain.STATUS_NOT_QUALIFIED)
        self.assertEqual(built["classification"], factor_chain.CLASSIFICATION_OTHER_EVIDENCE_GAP)
        self.assertIn(factor_chain.REASON_MISSING_KNOWLEDGE_CUTOFF, built["reason_codes"])
        self.assertIsNone(built["identity"])
        self.assertIsNone(built["adjustment_factor"])

    def test_identity_is_deterministic_and_distinguishes_events(self):
        entry = _entry(ex_date="2026-06-20")
        first = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        second = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        self.assertEqual(first["identity"], second["identity"])

        other_entry = _entry(ex_date="2026-07-01")
        third = factor_chain.build_factor_chain_entry(other_entry, knowledge_cutoff="2026-06-30T18:00:00+07:00")
        self.assertNotEqual(first["identity"], third["identity"])

    def test_idempotent_across_repeated_builds(self):
        entry = _entry(ex_date="2026-06-20")
        results = [factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
                  for _ in range(3)]
        self.assertTrue(all(result == results[0] for result in results))

    def test_price_series_context_consumes_qualified_chain_shape(self):
        import price_basis_feature_fitness as fitness
        entry = _entry(ex_date="2026-06-20")
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        context = fitness.price_series_context(
            ticker="TST", provider="DNSE", source_identity="synthetic_test_series",
            session_start="2026-06-01", session_end="2026-06-30",
            observed_basis=fitness.POINT_IN_TIME_ADJUSTED,
            basis_provenance=["synthetic_test_series"],
            adjustment_knowledge_cutoff=built["knowledge_cutoff"],
            factor_chain=built,
        )
        self.assertEqual(context["corporate_action_factor_chain"]["status"], "QUALIFIED")
        self.assertEqual(context["corporate_action_factor_chain"]["identity"], built["identity"])

    def test_unqualified_chain_leaves_pit_backtest_unqualified(self):
        import price_basis_feature_fitness as fitness
        entry = _entry(record_date="2026-06-18")  # missing explicit ex-date
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-06-19T18:00:00+07:00")
        context = fitness.price_series_context(
            ticker="TST", provider="DNSE", source_identity="synthetic_test_series",
            session_start="2026-06-01", session_end="2026-06-30",
            observed_basis=fitness.POINT_IN_TIME_ADJUSTED,
            basis_provenance=["synthetic_test_series"],
            factor_chain=built,
        )
        verdict = fitness.evaluate_feature_fitness(
            feature=fitness.PIT_BACKTEST, current_context=context, decision_as_of="2026-07-01")
        self.assertEqual(verdict["state"], fitness.POINT_IN_TIME_SEMANTICS_UNQUALIFIED)


class CohortTests(unittest.TestCase):
    def test_cohort_classifies_every_entry_without_preselecting_tickers(self):
        obs = [
            _observation(ex_date="2026-06-20"),
            _observation(observation_id="o2", document_id="d2", content_sha256="b" * 64,
                        ticker="TST2", event_type="cash_dividend", cash_amount_per_share=1000.0,
                        ex_date="2026-06-20"),
            _observation(observation_id="o3", document_id="d3", content_sha256="c" * 64,
                        ticker="TST3", record_date="2026-06-18", ex_date=None),
        ]
        built_ledger = ledger.build_ledger(obs)
        self.assertEqual(built_ledger["entry_count"], 3)

        def resolver(entry):
            if entry["ticker"] == "TST":
                return "2026-06-19T18:00:00+07:00", []
            return None, []

        cohort = factor_chain.build_factor_chain_cohort(built_ledger, knowledge_cutoff_resolver=resolver)
        self.assertEqual(cohort["cohort_size"], 3)
        self.assertEqual(cohort["classification_counts"][factor_chain.CLASSIFICATION_FACTOR_CHAIN_QUALIFIED], 1)
        self.assertEqual(cohort["classification_counts"][factor_chain.CLASSIFICATION_FACTOR_NOT_APPLICABLE], 1)
        self.assertEqual(cohort["classification_counts"][factor_chain.CLASSIFICATION_MISSING_EXPLICIT_EX_DATE], 1)
        self.assertEqual(cohort["qualified_count"], 1)


class RealEvidenceCeilingTests(unittest.TestCase):
    """Uses real field values frozen from retained evidence, not synthetic fixtures.

    Source: operations-review/current-official-event-context-integration-v1-20260824/
    current_official_event_context_artifact.json (real HNX official rights-event index,
    records['D11'], STOCK_DIVIDEND event, read 2026-09-15). That source has a real, official
    ex_date but -- being an event calendar, not a share-ratio ledger -- carries no stock_ratio
    and no ledger-grade executed-lifecycle evidence. This test proves the adapter honestly
    refuses to promote that real evidence to FACTOR_CHAIN_QUALIFIED rather than guessing.
    """

    def test_real_hnx_event_date_without_ledger_grade_evidence_stays_blocked(self):
        real_ex_date = "2026-08-21"  # real, from the retained HNX official rights-event index
        entry = _entry(ex_date=real_ex_date, lifecycle_state="announced", stock_ratio=None)
        classification, _ = factor_chain.classify_ledger_entry(entry)
        # NOT_EXECUTED takes priority because HNX's event-calendar 'execution_date' field is not
        # proven equivalent to the ledger's 'executed' lifecycle -- the honest, fail-closed read.
        self.assertEqual(classification, factor_chain.CLASSIFICATION_NOT_EXECUTED)
        built = factor_chain.build_factor_chain_entry(entry, knowledge_cutoff="2026-08-20T18:00:00+07:00")
        self.assertEqual(built["status"], factor_chain.STATUS_NOT_QUALIFIED)
        self.assertIsNone(built["identity"])


if __name__ == "__main__":
    unittest.main()
