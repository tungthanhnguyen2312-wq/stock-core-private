# ==========================================================================
# End-to-end tests for tools/shadow_taxonomy_qualification.py::run().
#
# These deliberately exercise the SAME aggregation and overlay path the real
# tool uses, rather than calling evaluate_altman_applicability() directly.
# The 7-versus-70 inconsistency this milestone fixed was invisible to
# direct-call unit tests: applicability was correct in isolation, while the
# shadow overlay discarded every non-corporate taxonomy before reaching it.
#
# Only the three I/O seams are patched (manual profiles, industries, and the
# per-period classification); all resolution, overlay, bucketing and
# reconciliation logic under test is the real implementation.
# Run: `python -m unittest tests.test_shadow_taxonomy_integration`
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import shadow_taxonomy_qualification as shadow  # noqa: E402

_MANUFACTURING = "Tài nguyên Cơ bản"
_NON_MANUFACTURING = "Bất động sản"


def _periods(ticker: str, taxonomy: str, count: int = 3):
    """Minimal per-period classification records, matching the classifier's shape."""
    return [{"ticker": ticker, "statement_taxonomy": taxonomy,
             "classification_status": "observed" if taxonomy in {
                 "corporate_vas", "credit_institution", "securities_company"} else "abstained",
             "reporting_period": f"2025-Q{index + 1}"} for index in range(count)]


class ShadowTaxonomyIntegrationTests(unittest.TestCase):
    def _run(self, per_ticker, manual=None, industries=None):
        classified = {ticker: _periods(ticker, taxonomy) for ticker, taxonomy in per_ticker.items()}
        with patch.object(shadow, "_manual_profiles", return_value=dict(manual or {})), \
             patch.object(shadow, "_industries", return_value=dict(industries or {})), \
             patch.object(shadow, "_classify_every_period", return_value=classified):
            return shadow.run(Path("unused"))

    def test_credit_institution_ticker_counts_as_not_applicable(self):
        report = self._run({"AAA": "credit_institution"}, industries={"AAA": _MANUFACTURING})
        after = report["altman_applicability_measured"]["after_shadow_overlay"]
        self.assertEqual(after.get("not_applicable"), 1)
        self.assertNotIn("eligible", after)

    def test_securities_company_ticker_counts_as_not_applicable(self):
        report = self._run({"BBB": "securities_company"}, industries={"BBB": _MANUFACTURING})
        self.assertEqual(
            report["altman_applicability_measured"]["after_shadow_overlay"].get("not_applicable"), 1)

    def test_explicitly_financial_but_ambiguous_ticker_counts_as_not_applicable(self):
        """BVH's shape: specialized financial vocabulary that names no single template.
        It is still positive evidence of a financial filing, so the corporate model is
        withheld rather than reported as merely missing evidence."""
        report = self._run({"CCC": "financial_specialized_ambiguous"}, industries={"CCC": _MANUFACTURING})
        self.assertEqual(
            report["altman_applicability_measured"]["after_shadow_overlay"].get("not_applicable"), 1)

    def test_genuinely_unresolved_ticker_stays_insufficient_evidence(self):
        """`unknown` is absence of evidence, not evidence of a financial filer."""
        report = self._run({"DDD": "unknown"}, industries={"DDD": _MANUFACTURING})
        after = report["altman_applicability_measured"]["after_shadow_overlay"]
        self.assertEqual(after.get("insufficient_evidence"), 1)
        self.assertNotIn("not_applicable", after)

    def test_manual_profile_overrides_generated_taxonomy(self):
        """A ticker whose statements read corporate_vas but which is hand-labelled a bank
        must follow the manual authority, not the generated overlay."""
        report = self._run({"EEE": "corporate_vas"}, manual={"EEE": "bank"},
                            industries={"EEE": _MANUFACTURING})
        after = report["altman_applicability_measured"]["after_shadow_overlay"]
        self.assertEqual(after.get("not_applicable"), 1)
        self.assertNotIn("eligible", after)

    def test_corporate_taxonomy_needs_manufacturing_industry_to_become_eligible(self):
        eligible = self._run({"FFF": "corporate_vas"}, industries={"FFF": _MANUFACTURING})
        blocked = self._run({"GGG": "corporate_vas"}, industries={"GGG": _NON_MANUFACTURING})
        self.assertEqual(
            eligible["altman_applicability_measured"]["after_shadow_overlay"].get("eligible"), 1)
        self.assertEqual(
            blocked["altman_applicability_measured"]["after_shadow_overlay"].get("insufficient_evidence"), 1)

    def test_every_ticker_lands_in_exactly_one_bucket(self):
        report = self._run(
            {"AAA": "credit_institution", "BBB": "securities_company",
             "CCC": "financial_specialized_ambiguous", "DDD": "unknown",
             "EEE": "corporate_vas", "FFF": "corporate_vas"},
            manual={"EEE": "bank"},
            industries={t: _MANUFACTURING for t in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")})
        rec = report["reconciliation"]
        self.assertEqual(rec["classified_tickers"], 6)
        self.assertTrue(rec["taxonomy_buckets_sum_to_universe"])
        self.assertTrue(rec["before_buckets_sum_to_universe"])
        self.assertTrue(rec["after_buckets_sum_to_universe"])
        self.assertTrue(rec["block_reasons_plus_eligible_sum_to_universe"])
        after = report["altman_applicability_measured"]["after_shadow_overlay"]
        self.assertEqual(sum(after.values()), 6)
        self.assertEqual(after.get("not_applicable"), 4, "3 financial taxonomies + 1 manual bank")
        self.assertEqual(after.get("eligible"), 1, "only the unlabelled corporate_vas manufacturer")
        self.assertEqual(after.get("insufficient_evidence"), 1, "the unknown taxonomy")

    def test_eligible_and_available_score_counts_stay_distinct(self):
        """Applicability is not a score: the report must never present eligibility as a
        produced Z' value."""
        report = self._run({"FFF": "corporate_vas"}, industries={"FFF": _MANUFACTURING})
        self.assertIn("eligible", report["altman_applicability_measured"]["after_shadow_overlay"])
        self.assertNotIn("available_scores", report["altman_applicability_measured"])
        self.assertNotIn("scores", report["altman_applicability_measured"])

    def test_shadow_integration_never_writes_the_canonical_profile(self):
        before = shadow.PROFILES.read_bytes()
        self._run({"AAA": "credit_institution", "FFF": "corporate_vas"},
                   industries={"AAA": _MANUFACTURING, "FFF": _MANUFACTURING})
        self.assertEqual(shadow.PROFILES.read_bytes(), before)

    def test_run_is_deterministic(self):
        arguments = ({"AAA": "credit_institution", "FFF": "corporate_vas"},)
        keywords = {"industries": {"AAA": _MANUFACTURING, "FFF": _MANUFACTURING}}
        self.assertEqual(self._run(*arguments, **keywords), self._run(*arguments, **keywords))


if __name__ == "__main__":
    unittest.main()
