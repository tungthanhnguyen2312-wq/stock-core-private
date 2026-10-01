from datetime import datetime, timezone
import unittest

from freshness_history import RULES, freshness_envelope


REF = datetime(2026, 7, 26, 12, tzinfo=timezone.utc)


class FreshnessHistoryTests(unittest.TestCase):
    def test_future_observations_fail_closed_across_domain_cadences(self):
        for domain in RULES:
            with self.subTest(domain=domain):
                result = freshness_envelope(
                    domain=domain, as_of_date="2026-07-27", generated_at="2026-07-26",
                    source="test", reference_at=REF, completeness="complete",
                )
                self.assertEqual(result["freshness_status"], "unknown")
                self.assertEqual(result["stale_reason"], "source_date_after_reference_anchor")
                self.assertEqual(result["as_of_date"], "2026-07-27")
                self.assertFalse(result["is_actionable"])

    def test_market_date_after_completed_session_is_not_current(self):
        reference = datetime.fromisoformat("2026-10-01T07:00:00+07:00")
        for domain in ("daily_market", "technical", "screening", "valuation", "market_flow", "integrated_decision"):
            result = freshness_envelope(
                domain=domain, as_of_date="2026-10-01", generated_at=reference,
                source="test", reference_at=reference,
            )
            self.assertEqual(result["freshness_status"], "unknown")
            self.assertFalse(result["is_actionable"])

    def test_daily_weekend_and_determinism(self):
        one = freshness_envelope(domain="daily_market", as_of_date="2026-07-24", generated_at="2026-07-24", source="test", reference_at=REF)
        two = freshness_envelope(domain="daily_market", as_of_date="2026-07-24", generated_at="2026-07-24", source="test", reference_at=REF)
        self.assertEqual(one, two)
        self.assertEqual(one["freshness_status"], "current")

    def test_cadence_financial_and_missing_fail_closed(self):
        monthly = freshness_envelope(domain="macro_monthly", as_of_date="2026-06-30", generated_at="2026-06-30", source="macro", reference_at=REF)
        financial = freshness_envelope(domain="financial_quarterly", as_of_date="2026-03-31", generated_at="2026-03-31", source="financial", reference_at=REF)
        missing = freshness_envelope(domain="daily_market", as_of_date=None, generated_at=None, source="market", reference_at=REF)
        self.assertEqual(monthly["freshness_status"], "current")
        self.assertEqual(financial["freshness_status"], "historical")
        self.assertFalse(financial["is_actionable"])
        self.assertEqual(missing["freshness_status"], "missing")
        self.assertFalse(missing["is_actionable"])

    def test_partial_events_and_snapshot_are_not_actionable(self):
        for domain, coverage in (("corporate_events", "partial_unqualified_50_row_cap"), ("corporate_snapshot", "partial")):
            result = freshness_envelope(domain=domain, as_of_date="2026-07-25", generated_at="2026-07-25", source="VCI", reference_at=REF, completeness=coverage)
            self.assertFalse(result["is_actionable"])
            self.assertIn("coverage", result["stale_reason"])

    def test_null_is_not_zero(self):
        unknown = freshness_envelope(domain="macro_daily", as_of_date=None, generated_at="2026-07-25", source="macro", reference_at=REF)
        current = freshness_envelope(domain="macro_daily", as_of_date="2026-07-25", generated_at="2026-07-25", source="macro", reference_at=REF)
        self.assertEqual(unknown["as_of_date"], None)
        self.assertEqual(current["as_of_date"], "2026-07-25")


if __name__ == "__main__":
    unittest.main()
