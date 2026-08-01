# ==========================================================================
# Focused tests for Phase 6B legacy fundamental_quality.py hardening: explicit
# partial/unavailable states for dupont_roe and piotroski_f_score, unchanged
# altman_z_score/beneish_m_score verdicts, and cross-contract reconciliation of
# earnings_quality against fundamental_quality_evidence (Phase 6A). Pure unit tests
# against synthetic canonical-record dicts, plus real-data cross-checks against the
# already-generated Phase 5D/6A bundles.
# Run: `python -m unittest tests.test_fundamental_quality_hardening` from the repo root.
# ==========================================================================

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export_ai_bundle as bundle_mod  # noqa: E402
import fundamental_quality as fq  # noqa: E402
import fundamental_quality_evidence as fqe  # noqa: E402

_ORIGINAL_MODEL_KEYS = frozenset({
    "model_name", "model_version", "applicability_state", "result_state", "score_or_value",
    "component_results", "input_periods", "statement_scope", "required_inputs", "used_inputs",
    "used_input_facts", "input_classification", "missing_inputs", "provenance", "warnings",
    "interpretation_limits", "is_actionable",
})


def _record(metric, value, period="2024", scope="consolidated", currency="VND", scale=1,
            period_type="annual", quality_state="available", derivation_status="direct",
            observation_ids=None, citation_id="cit-1", evidence_id="ev-1"):
    return {
        "canonical_metric": metric, "value": value,
        "period_identity": {"period": period, "period_type": period_type},
        "statement_scope": scope, "currency": currency, "unit_scale": scale,
        "quality_state": quality_state, "derivation_status": derivation_status,
        "observation_ids": observation_ids if observation_ids is not None else [f"obs-{metric}-{period}"],
        "evidence": {"citation_id": citation_id, "evidence_id": evidence_id},
    }


_ONE_PERIOD_CORPORATE_RECORDS = [
    _record("net_income", 400),
    _record("revenue", 2000),
    _record("total_assets", 5000),
    _record("shareholders_equity", 2500),
    _record("operating_cash_flow", 1000),
    _record("total_debt", 1200),
    _record("cash_and_equivalents", 300),
]

_TWO_PERIOD_CORPORATE_RECORDS = _ONE_PERIOD_CORPORATE_RECORDS + [
    _record("net_income", 350, period="2023"),
    _record("revenue", 1800, period="2023"),
]


def _real_bundle_entry(ticker: str) -> dict:
    path = ROOT / "operations-review" / "phase_5d_distribution_evidence_20260801T104910Z" / "bundle_output" / "analysis_bundle.json"
    with path.open(encoding="utf-8") as handle:
        bundle = json.load(handle)
    return bundle["tickers"][ticker]


class RealDataClassificationTests(unittest.TestCase):
    """Requirement 1: HPG and VNM legacy outputs are classified correctly."""

    def _assert_real_ticker_classification(self, ticker: str):
        entry = _real_bundle_entry(ticker)
        result = fq.evaluate_fundamental_quality(entry.get("financial_canonical"), entry.get("entity_type"))
        models = result["models"]

        self.assertEqual(models["growth_profitability"]["result_state"], "available")
        self.assertFalse(models["growth_profitability"]["is_partial"])

        self.assertEqual(models["dupont_roe"]["result_state"], "partial")
        self.assertTrue(models["dupont_roe"]["is_partial"])
        self.assertIsNotNone(models["dupont_roe"]["score_or_value"])

        self.assertEqual(models["earnings_quality"]["result_state"], "available")

        self.assertEqual(models["piotroski_f_score"]["result_state"], "partial")
        self.assertTrue(models["piotroski_f_score"]["is_partial"])
        self.assertIsNone(models["piotroski_f_score"]["score_or_value"])
        self.assertIn("non_comparative_criteria_met", models["piotroski_f_score"]["component_results"])

        self.assertEqual(models["altman_z_score"]["result_state"], "inapplicable")
        self.assertEqual(models["beneish_m_score"]["result_state"], "unavailable")
        self.assertEqual(models["bank_financial_quality"]["result_state"], "inapplicable")

    def test_hpg_real_classification(self):
        self._assert_real_ticker_classification("HPG")

    def test_vnm_real_classification(self):
        self._assert_real_ticker_classification("VNM")


class NoStandardComparativeScoreTests(unittest.TestCase):
    """Requirement 2: unverified/absent comparative periods must not produce a standard
    Piotroski or Beneish result -- and, since this implementation never computes the
    year-over-year criteria at all, this holds even when a second period IS present."""

    def test_single_period_piotroski_has_no_score(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        piotroski = result["models"]["piotroski_f_score"]
        self.assertIsNone(piotroski["score_or_value"])
        self.assertEqual(piotroski["result_state"], "partial")
        self.assertTrue(any("no_verified_comparative_annual_period" in r for r in piotroski["blocking_reasons"]))

    def test_two_period_piotroski_still_has_no_standard_score(self):
        """A second available annual period does not unlock a standard 0-9 score -- this
        module never implements the 6 comparative criteria."""
        result = fq.evaluate_fundamental_quality({"records": _TWO_PERIOD_CORPORATE_RECORDS}, "corporate")
        piotroski = result["models"]["piotroski_f_score"]
        self.assertIsNone(piotroski["score_or_value"])
        self.assertEqual(piotroski["result_state"], "partial")
        self.assertTrue(any("only_3_of_9" in r for r in piotroski["blocking_reasons"]))
        self.assertFalse(any("no_verified_comparative_annual_period" in r for r in piotroski["blocking_reasons"]))

    def test_beneish_m_score_always_unavailable(self):
        for records in (_ONE_PERIOD_CORPORATE_RECORDS, _TWO_PERIOD_CORPORATE_RECORDS):
            result = fq.evaluate_fundamental_quality({"records": records}, "corporate")
            self.assertEqual(result["models"]["beneish_m_score"]["result_state"], "unavailable")
            self.assertIsNone(result["models"]["beneish_m_score"]["score_or_value"])


class DuPontPartialLabelTests(unittest.TestCase):
    """Requirement 3: missing average-balance semantics must prevent a standard DuPont
    claim, without deleting the period-end approximation."""

    def test_dupont_is_partial_with_explicit_limitation_but_keeps_its_value(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        dupont = result["models"]["dupont_roe"]
        self.assertEqual(dupont["result_state"], "partial")
        self.assertEqual(dupont["status"], "partial")
        self.assertTrue(dupont["is_partial"])
        self.assertIsNotNone(dupont["score_or_value"])
        self.assertTrue(any("average" in lim.lower() for lim in dupont["limitations"]))
        self.assertTrue(any("not the standard" in lim.lower() for lim in dupont["limitations"]))


class AltmanFailsClosedTests(unittest.TestCase):
    """Requirement 4: missing Altman identities must fail closed, unconditionally."""

    def test_altman_inapplicable_regardless_of_other_available_inputs(self):
        for records in (_ONE_PERIOD_CORPORATE_RECORDS, _TWO_PERIOD_CORPORATE_RECORDS):
            result = fq.evaluate_fundamental_quality({"records": records}, "corporate")
            altman = result["models"]["altman_z_score"]
            self.assertEqual(altman["result_state"], "inapplicable")
            self.assertIsNone(altman["score_or_value"])
            self.assertTrue(altman["blocking_reasons"])


class PartialProxiesExplicitlyLabeledTests(unittest.TestCase):
    """Requirement 5: partial proxies must be explicitly labeled partial."""

    def test_dupont_and_piotroski_are_flagged_partial(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        for name in ("dupont_roe", "piotroski_f_score"):
            model = result["models"][name]
            self.assertEqual(model["result_state"], "partial")
            self.assertTrue(model["is_partial"])

    def test_non_partial_models_are_not_mislabeled_partial(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        for name in ("growth_profitability", "earnings_quality", "financial_strength"):
            self.assertFalse(result["models"][name]["is_partial"])


class NonActionableTests(unittest.TestCase):
    """Requirement 6: all submodels remain non-actionable, in every state."""

    def test_is_actionable_false_for_every_model_every_state(self):
        for canonical, entity_type in (
            ({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate"),
            ({"records": _TWO_PERIOD_CORPORATE_RECORDS}, "corporate"),
            ({"records": []}, "corporate"),
            (None, "corporate"),
            ({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "bank"),
            ({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "unknown"),
        ):
            result = fq.evaluate_fundamental_quality(canonical, entity_type)
            for name, model in result["models"].items():
                self.assertIs(model["is_actionable"], False, f"{entity_type}/{name}")


class EarningsQualityConsistencyTests(unittest.TestCase):
    """Requirement 7: legacy earnings_quality must not contradict qualified evidence."""

    def _legacy_earnings_quality(self, records):
        result = fq.evaluate_fundamental_quality({"records": records}, "corporate")
        return result["models"]["earnings_quality"]

    def test_matching_qualified_evidence_is_marked_comparable_and_kept(self):
        earnings_quality = self._legacy_earnings_quality(_ONE_PERIOD_CORPORATE_RECORDS)
        qualified_evidence = {
            "status": "available", "reporting_period": "2024", "statement_scope": "consolidated",
            "metrics": {"operating_cash_flow_less_net_income": 1000 - 400},
        }
        fq.reconcile_earnings_quality_with_qualified_evidence(earnings_quality, qualified_evidence)
        self.assertEqual(earnings_quality["result_state"], "available")
        self.assertEqual(earnings_quality["score_or_value"], 600)
        self.assertIn("comparable_to_qualified_evidence", earnings_quality["warnings"])

    def test_diverging_qualified_evidence_supersedes_the_legacy_value(self):
        earnings_quality = self._legacy_earnings_quality(_ONE_PERIOD_CORPORATE_RECORDS)
        qualified_evidence = {
            "status": "available", "reporting_period": "2024", "statement_scope": "consolidated",
            "metrics": {"operating_cash_flow_less_net_income": 999999},
        }
        fq.reconcile_earnings_quality_with_qualified_evidence(earnings_quality, qualified_evidence)
        self.assertEqual(earnings_quality["result_state"], "unavailable")
        self.assertIsNone(earnings_quality["score_or_value"])
        self.assertTrue(any("superseded" in r for r in earnings_quality["blocking_reasons"]))

    def test_qualified_evidence_absent_leaves_legacy_value_unchanged_but_annotated(self):
        earnings_quality = self._legacy_earnings_quality(_ONE_PERIOD_CORPORATE_RECORDS)
        original_value = earnings_quality["score_or_value"]
        fq.reconcile_earnings_quality_with_qualified_evidence(earnings_quality, None)
        self.assertEqual(earnings_quality["result_state"], "available")
        self.assertEqual(earnings_quality["score_or_value"], original_value)
        self.assertTrue(any("not cross-checked" in lim.lower() for lim in earnings_quality["limitations"]))

    def test_real_hpg_and_vnm_earnings_quality_matches_real_qualified_evidence(self):
        runtime_root = ROOT.parent / "dashboard-runtime"
        for ticker in ("HPG", "VNM"):
            entry = _real_bundle_entry(ticker)
            legacy = fq.evaluate_fundamental_quality(entry.get("financial_canonical"), entry.get("entity_type"))
            qualified = fqe.build_fundamental_quality_evidence_for_ticker(
                ticker, entry.get("entity_type"), entry.get("financial_canonical"),
                entry.get("financial_period_coverage"), runtime_root,
            )
            fake_entry = {"fundamental_quality": legacy, "fundamental_quality_evidence": qualified}
            fq.reconcile_legacy_fundamental_quality_with_qualified_evidence(fake_entry)
            earnings_quality = fake_entry["fundamental_quality"]["models"]["earnings_quality"]
            self.assertEqual(earnings_quality["result_state"], "available")
            self.assertIn("comparable_to_qualified_evidence", earnings_quality["warnings"])
            self.assertEqual(earnings_quality["score_or_value"], qualified["metrics"]["operating_cash_flow_less_net_income"])


class DefaultBundleCompatibilityTests(unittest.TestCase):
    """Requirement 8: default bundle compatibility is preserved -- same top-level shape,
    same MODEL_NAMES, no existing key removed from any submodel (additive only)."""

    def test_top_level_shape_unchanged(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        self.assertEqual(set(result.keys()), {"schema_version", "entity_type", "models"})
        self.assertEqual(set(result["models"].keys()), set(fq.MODEL_NAMES))

    def test_no_original_key_removed_from_any_submodel(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        for name, model in result["models"].items():
            missing = _ORIGINAL_MODEL_KEYS - set(model.keys())
            self.assertFalse(missing, f"{name} lost keys: {missing}")

    def test_wiring_call_site_signature_unchanged(self):
        """evaluate_fundamental_quality(canonical, entity_type) must still work with
        exactly its original two positional/keyword arguments -- no new required parameter."""
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, entity_type="corporate")
        self.assertIn("models", result)

    def test_reconciliation_disabled_by_default_leaves_entries_without_qualified_evidence_untouched_in_value(self):
        entries = {"HPG": {
            "fundamental_quality": fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate"),
        }}
        original_score = entries["HPG"]["fundamental_quality"]["models"]["earnings_quality"]["score_or_value"]
        bundle_mod.reconcile_legacy_fundamental_quality_with_qualified_evidence(entries["HPG"])
        self.assertEqual(entries["HPG"]["fundamental_quality"]["models"]["earnings_quality"]["score_or_value"], original_score)
        self.assertNotIn("fundamental_quality_evidence", entries["HPG"])


class NoRankingOrRecommendationTests(unittest.TestCase):
    """Requirement 9: no ranking, rating, recommendation, or target is added. score_or_value
    is a pre-existing per-model field (not a new composite/universal score) and is excluded
    from this scan; the check is that nothing NEW resembling a composite score is added."""

    _FORBIDDEN = ("rank", "recommendation", "rating", "target", "composite", "overall_score", "universal")

    def _scan(self, node):
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered != "score_or_value":
                    words = set(lowered.split("_"))
                    for forbidden in self._FORBIDDEN:
                        if set(forbidden.split("_")) <= words:
                            found.append(key)
                found.extend(self._scan(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(self._scan(item))
        return found

    def test_no_forbidden_keys_anywhere_in_result(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        self.assertEqual(self._scan(result), [])

    def test_no_new_top_level_composite_score_key(self):
        result = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")
        self.assertEqual(set(result.keys()), {"schema_version", "entity_type", "models"})


class DeterminismTests(unittest.TestCase):
    def test_repeated_calls_are_deterministic(self):
        first = fq.evaluate_fundamental_quality({"records": copy.deepcopy(_TWO_PERIOD_CORPORATE_RECORDS)}, "corporate")
        second = fq.evaluate_fundamental_quality({"records": copy.deepcopy(_TWO_PERIOD_CORPORATE_RECORDS)}, "corporate")
        self.assertEqual(first, second)

    def test_reconciliation_is_deterministic(self):
        qualified_evidence = {
            "status": "available", "reporting_period": "2024", "statement_scope": "consolidated",
            "metrics": {"operating_cash_flow_less_net_income": 600},
        }
        eq1 = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")["models"]["earnings_quality"]
        eq2 = fq.evaluate_fundamental_quality({"records": _ONE_PERIOD_CORPORATE_RECORDS}, "corporate")["models"]["earnings_quality"]
        fq.reconcile_earnings_quality_with_qualified_evidence(eq1, copy.deepcopy(qualified_evidence))
        fq.reconcile_earnings_quality_with_qualified_evidence(eq2, copy.deepcopy(qualified_evidence))
        self.assertEqual(eq1, eq2)


if __name__ == "__main__":
    unittest.main()
