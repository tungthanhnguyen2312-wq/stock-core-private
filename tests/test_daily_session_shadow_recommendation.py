from __future__ import annotations

import copy
import inspect
import json
import unittest
from pathlib import Path

import action_instrumentation
import daily_session_shadow_recommendation
import fundamental_thesis_invalidation_precision
import shadow_action_readiness
import shadow_security_recommendation
import thesis_catalyst_downside_research_cases
from daily_session_shadow_recommendation import DailySessionShadowRecommendationError, build

ROOT = Path(__file__).resolve().parents[1]

PATHS_27 = {
    "market": "operations-review/market-wide-current-descriptive-research-v1-20260827/market_wide_current_descriptive_research_artifact.json",
    "tactical": "operations-review/watchlist-tactical-entry-decision-v1-20260827/watchlist_tactical_entry_classifier_artifact.json",
}
PATHS_28 = {
    "market": "operations-review/market-wide-current-descriptive-research-v1-20260828/market_wide_current_descriptive_research_artifact.json",
    "tactical": "operations-review/watchlist-tactical-entry-decision-v1-20260828/watchlist_tactical_entry_classifier_artifact.json",
}
SHARED_PATHS = {
    "fundamental": "operations-review/fundamental-cross-sectional-scoring-and-ranking-v1-20260828/artifact.json",
    "valuation": "operations-review/current-valuation-research-proxy-and-relative-value-axis-v1-20260828/artifact.json",
    "events": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "ttm": "operations-review/financial-flow-semantics-and-ttm-bridge-foundation-v1-20260828/artifact.json",
    "risk_research": "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json",
    "a1_temporal": "operations-review/a1-bitemporal-semantic-contract-v1-20260828/artifact.json",
    "a2_temporal": "operations-review/a2-provider-publication-first-seen-retention-v1-20260829/artifact.json",
}
RECOMMENDATION_LABELS = {
    "INITIATE_RESEARCH_CANDIDATE", "ACCUMULATE_RESEARCH_CANDIDATE", "WAIT_FOR_CONFIRMATION",
    "HIGH_RISK_SPECULATION_ONLY", "AVOID_NEW_ENTRY", "INSUFFICIENT_EVIDENCE",
}


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def session_inputs(session_paths: dict[str, str]) -> dict:
    inputs = {key: _load(path) for key, path in {**session_paths, **SHARED_PATHS}.items()}
    # shadow_security_recommendation's optional enrichment param reuses the same retained
    # valuation-research-proxy artifact the ranking stage already consumes as `valuation`.
    inputs["valuation_research"] = inputs["valuation"]
    return inputs


class DailySessionShadowRecommendationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs_27 = session_inputs(PATHS_27)
        cls.inputs_28 = session_inputs(PATHS_28)
        cls.result_27 = build(**cls.inputs_27)
        cls.result_28 = build(**cls.inputs_28)

    def test_target_session_identity_preserved(self):
        self.assertEqual(self.result_27["session"], "2026-08-27")
        self.assertEqual(self.result_27["shadow_security_recommendation"]["metadata"]["as_of_session"], "2026-08-27")
        self.assertEqual(self.result_28["session"], "2026-08-28")
        self.assertEqual(self.result_28["shadow_security_recommendation"]["metadata"]["as_of_session"], "2026-08-28")

    def test_contract_versions_match_the_standalone_engines_exactly(self):
        self.assertEqual(self.result_27["shadow_security_recommendation"]["contract_version"], shadow_security_recommendation.CONTRACT_VERSION)
        self.assertEqual(self.result_27["fundamental_thesis_invalidation_precision"]["contract_version"], fundamental_thesis_invalidation_precision.CONTRACT_VERSION)
        self.assertEqual(self.result_27["research_cases"]["contract_version"], thesis_catalyst_downside_research_cases.CONTRACT_VERSION)
        self.assertEqual(self.result_27["shadow_action_readiness"]["contract_version"], shadow_action_readiness.CONTRACT_VERSION)
        self.assertEqual(self.result_27["action_instrumentation"]["contract_version"], action_instrumentation.CONTRACT_VERSION)

    def test_orchestration_is_a_faithful_passthrough_not_a_reimplementation(self):
        """Calling shadow_security_recommendation.build_artifact() directly with this
        module's own intermediate outputs must reproduce the exact same final artifact --
        proving the orchestration adds no recommendation logic of its own."""
        direct = shadow_security_recommendation.build_artifact(
            research_cases=self.result_27["research_cases"],
            shadow_readiness=self.result_27["shadow_action_readiness"],
            action_instrumentation=self.result_27["action_instrumentation"],
            fundamental_invalidation=self.result_27["fundamental_thesis_invalidation_precision"],
            risk_research=self.inputs_27["risk_research"],
            valuation_research=self.inputs_27["valuation_research"],
            a1_temporal=self.inputs_27["a1_temporal"],
            a2_temporal=self.inputs_27["a2_temporal"],
        )
        self.assertEqual(direct, self.result_27["shadow_security_recommendation"])

    def test_ticker_denominator_is_generic_not_frozen_to_a_prior_cohort_size(self):
        """The denominator is a property of the fundamental input's own coverage (a
        governed eligible research set), never a hardcoded constant in this orchestration."""
        fundamental_coverage = len(self.inputs_27["fundamental"].get("records") or {})
        self.assertGreater(fundamental_coverage, 0)
        self.assertEqual(self.result_27["denominator_by_stage"]["shadow_security_recommendation"], self.result_27["shadow_security_recommendation"]["denominator"])
        self.assertEqual(self.result_27["shadow_security_recommendation"]["denominator"], fundamental_coverage)
        self.assertEqual(self.result_27["shadow_security_recommendation"]["residual"], 0)

    def test_no_recommendation_invented_for_not_ready_cases(self):
        for record in self.result_27["shadow_security_recommendation"]["records"].values():
            if record["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_NOT_READY":
                self.assertEqual(record["recommendation"]["recommendation_label"], "INSUFFICIENT_EVIDENCE")

    def test_labels_stay_within_the_existing_vocabulary_never_buy_sell_hold(self):
        labels = {record["recommendation"]["recommendation_label"] for record in self.result_27["shadow_security_recommendation"]["records"].values()}
        self.assertTrue(labels.issubset(RECOMMENDATION_LABELS))
        self.assertFalse(labels & {"BUY", "SELL", "HOLD"})

    def test_deterministic_output(self):
        repeat = build(**self.inputs_27)
        self.assertEqual(self.result_27, repeat)
        self.assertEqual(self.result_27["artifact_sha256"], repeat["artifact_sha256"])

    def test_session_mismatch_between_market_and_tactical_fails_closed(self):
        with self.assertRaises(DailySessionShadowRecommendationError):
            build(**{**self.inputs_27, "tactical": self.inputs_28["tactical"]})

    def test_missing_market_session_fails_closed(self):
        malformed_market = copy.deepcopy(self.inputs_27["market"])
        malformed_market.pop("session", None)
        with self.assertRaises(DailySessionShadowRecommendationError):
            build(**{**self.inputs_27, "market": malformed_market})

    def test_stale_upstream_evidence_cannot_be_relabeled_as_current(self):
        """A same-session recommendation is not obtained by relabeling an older session's
        market/tactical snapshot; the produced as_of_session always matches the real input."""
        self.assertNotEqual(self.result_27["session"], "2026-08-25")
        stale_session_marker = json.dumps(self.result_27["shadow_security_recommendation"])
        self.assertNotIn('"as_of_session": "2026-08-25"', stale_session_marker)

    def test_two_real_sessions_produce_genuinely_different_results_not_the_same_numbers_twice(self):
        self.assertNotEqual(
            self.result_27["shadow_security_recommendation"]["validation"]["recommendation_counts"],
            self.result_28["shadow_security_recommendation"]["validation"]["recommendation_counts"],
        )

    def test_no_hidden_file_or_clock_io_no_future_leakage_possible(self):
        """Pure in-memory orchestration over its explicit arguments only: no read_text/open/
        Path/datetime call exists in the module, so it cannot pick up a later date's data by
        itself -- every input is exactly what the caller passed in."""
        source = inspect.getsource(daily_session_shadow_recommendation)
        for forbidden in ("datetime", ".now(", "open(", "read_text", "read_bytes", "Path("):
            self.assertNotIn(forbidden, source, f"unexpected {forbidden!r} in daily_session_shadow_recommendation.py")

    def test_research_only_authority_boundaries_preserved(self):
        for result in (self.result_27, self.result_28):
            self.assertFalse(result["is_actionable"])
            self.assertEqual(result["authority_effect"], "NONE")
            boundary = result["shadow_security_recommendation"]["authority_boundaries"]
            self.assertTrue(boundary["shadow_research_recommendation_only"])
            self.assertTrue(boundary["no_buy_sell_hold_vocabulary"])
            self.assertTrue(boundary["no_portfolio_weights_or_sizing"])
