"""Tests for watchlist_tactical_entry_classifier.py.

Builds a small synthetic descriptive-research artifact by hand (same convention as
test_current_market_screening_opportunity_comparison_foundation.py's _source() helper), feeds it
through the REAL current_market_screening_opportunity_comparison_foundation.build_artifact() to get
a real, schema-faithful screening artifact (no hand-duplication of that module's own logic), and
hand-builds a small fundamental-research artifact (its shape is simple enough not to need the full
P3-F10/P3-F13 join machinery). Nine tickers are deliberately engineered, one per entry_state, plus
one insufficient-data ticker and several fundamental-cohort-absent tickers.
"""
from __future__ import annotations

import copy
import json
import unittest

import current_market_screening_opportunity_comparison_foundation as screening_module
import market_wide_current_descriptive_research as descriptive_module
import market_wide_current_fundamental_research as fundamental_module
import watchlist_tactical_entry_classifier as classifier

SESSION = "2026-08-21"
VOLATILITY_MEDIAN = 0.02


def _technical(*, close, ma20, momentum, return_1d, volatility, relative_volume, current=True):
    return {
        "status": "SHADOW_ONLY",
        "is_current_session": current,
        "feature_as_of_session": SESSION if current else "2026-08-20",
        "values": {
            "close": close, "ma_3": close, "ma_5": close, "ma_20": ma20,
            "momentum_20d": momentum, "return_1d": return_1d, "volatility_20d": volatility,
            "relative_volume_provider_scoped": relative_volume,
        },
    }


def _liquidity(*, eligible=True):
    if not eligible:
        return {"status": "UNAVAILABLE", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}
    return {
        "status": "ELIGIBLE", "session": SESSION, "board_composition": {"MATCHED_ROUND_LOT": {}},
        "g1_v_reconciliation": {"verdict": "EXACT_MATCH"},
        "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
    }


# ticker: (close, ma20, momentum, return_1d, volatility, relative_volume, liquidity_eligible)
_TICKER_SPECS = {
    "BRK": (115.0, 100.0, 0.15, 0.02, 0.01, 2.0, True),    # BREAKOUT_READY
    "UPT": (105.0, 100.0, 0.05, 0.005, 0.02, 0.8, True),   # UPTREND_CONFIRMED (default, volume not elevated)
    "DST": (110.0, 100.0, -0.05, 0.005, 0.02, 1.0, False), # DISTRIBUTION_RISK
    "BRD": (90.0, 100.0, -0.20, -0.03, 0.02, 2.5, True),   # BREAKDOWN_RISK
    "REV": (92.0, 100.0, 0.01, 0.005, 0.02, 1.0, True),    # EARLY_REVERSAL_CANDIDATE
    "BAS": (94.0, 100.0, -0.02, 0.005, 0.01, 0.9, False),  # BASE_BUILDING
    "EAS": (95.0, 100.0, -0.01, 0.01, 0.03, 1.0, True),    # SELLING_PRESSURE_EASING
    "DWN": (88.0, 100.0, -0.08, -0.01, 0.03, 0.9, True),   # DOWNTREND
    "NEU": (100.5, 100.0, 0.001, 0.005, 0.02, 1.0, True),  # SIDEWAYS_NEUTRAL (near MA20)
}
_STALE_TICKER = "THN"  # insufficient-data: stale (not current session)

_EXPECTED_ENTRY_STATE = {
    "BRK": "BREAKOUT_READY", "UPT": "UPTREND_CONFIRMED", "DST": "DISTRIBUTION_RISK",
    "BRD": "BREAKDOWN_RISK", "REV": "EARLY_REVERSAL_CANDIDATE", "BAS": "BASE_BUILDING",
    "EAS": "SELLING_PRESSURE_EASING", "DWN": "DOWNTREND", "NEU": "SIDEWAYS_NEUTRAL",
}

# Fundamental cohort: only BRK/UPT/DST/BRD/NEU are present; REV/BAS/EAS/DWN are deliberately absent.
_FUNDAMENTAL_TIER = {
    "BRK": ("OFFICIAL_QUALIFIED", "READY"),
    "UPT": ("PROVIDER_RESEARCH", None),
    "DST": ("BLOCKED", None),
    "BRD": ("OFFICIAL_QUALIFIED", "PARTIAL"),
    "NEU": ("PROVIDER_RESEARCH", None),
}


def _descriptive_source(*, breadth_descriptor="MARKET_BREADTH_MIXED", momentum_descriptor="MOMENTUM_BREADTH_MIXED"):
    records = {}
    for ticker, (close, ma20, momentum, return_1d, volatility, relvol, liq_ok) in _TICKER_SPECS.items():
        above = close > ma20
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(close=close, ma20=ma20, momentum=momentum, return_1d=return_1d,
                                             volatility=volatility, relative_volume=relvol),
            "trend_state": "ABOVE_MA20" if above else "AT_OR_BELOW_MA20",
            "liquidity": _liquidity(eligible=liq_ok), "sector_classification": {},
        }
    records[_STALE_TICKER] = {
        "ticker": _STALE_TICKER, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION",
        "technical_features": _technical(close=50.0, ma20=50.0, momentum=0.0, return_1d=0.0, volatility=0.02,
                                         relative_volume=1.0, current=False),
        "trend_state": None, "liquidity": {"status": "UNAVAILABLE", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"},
        "sector_classification": {},
    }
    source = {
        "schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION,
        "records": records,
        "market_breadth": {
            "breadth_descriptor": {"descriptor": breadth_descriptor},
            "momentum_descriptor": {"descriptor": momentum_descriptor},
            "advance_ratio": 0.5, "quality_state": "PARTIAL_COVERAGE_EXPLICIT",
            "volatility": {"median": VOLATILITY_MEDIAN},
        },
        "sector_breadth": {"sector_count_available": 0, "sector_count_insufficient_coverage": 0, "sectors": {}},
        "liquidity_features": {"reconciliation_warnings": []},
        "validation": {
            "coverage": {"current_active_equity_denominator": len(records), "observed_session_cohort": len(records)},
            "lineage": {"liquidity_artifact_identity": "fixture-liquidity"},
        },
    }
    return {**source, **descriptive_module.content_identity(source)}


def _screening_source(descriptive_source):
    return screening_module.build_artifact(descriptive_source)


def _fundamental_source():
    records = {}
    for ticker, (tier, readiness) in _FUNDAMENTAL_TIER.items():
        if tier == "OFFICIAL_QUALIFIED":
            records[ticker] = {
                "ticker": ticker, "authority_tier": tier, "sector": "corporate", "entity_class": "corporate",
                "fundamental_research_readiness": readiness, "metrics": [], "metric_family_states": {},
            }
        else:
            records[ticker] = {
                "ticker": ticker, "authority_tier": tier, "sector": "corporate",
                "disposition": "NO_APPROVED_ROUTE_FOUND" if tier == "PROVIDER_RESEARCH" else "SOURCE_MISSING",
                "allowed_uses": [], "forbidden_uses": [],
            }
    source = {"schema_version": "1.0.0", "contract_version": "market_wide_current_fundamental_research/v1", "records": records,
              "coverage": {"candidate_count": len(records)}}
    return {**source, **fundamental_module.content_identity(source)}


def _build(**breadth_kwargs):
    descriptive = _descriptive_source(**breadth_kwargs)
    screening = _screening_source(descriptive)
    fundamental = _fundamental_source()
    artifact = classifier.build_artifact(
        descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental,
        requested_at="2026-08-23T00:00:00+00:00",
    )
    return descriptive, screening, fundamental, artifact


class EntryStateClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        _, _, _, self.artifact = _build()
        self.records = self.artifact["records"]

    def test_all_nine_entry_states_reached_by_design(self) -> None:
        for ticker, expected in _EXPECTED_ENTRY_STATE.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(self.records[ticker]["entry_state"], expected)
        self.assertEqual(set(self.records[t]["entry_state"] for t in _EXPECTED_ENTRY_STATE), set(classifier.ENTRY_STATES))

    def test_action_matches_fixed_lookup(self) -> None:
        for ticker, expected_state in _EXPECTED_ENTRY_STATE.items():
            self.assertEqual(self.records[ticker]["action"], classifier.ACTION_BY_ENTRY_STATE[expected_state])

    def test_ticker_structure_state_matches_raw_posture(self) -> None:
        self.assertEqual(self.records["BRK"]["ticker_structure_state"], "ABOVE_MA20_MOMENTUM_POSITIVE")
        self.assertEqual(self.records["DST"]["ticker_structure_state"], "ABOVE_MA20_MOMENTUM_NEGATIVE")
        self.assertEqual(self.records["REV"]["ticker_structure_state"], "BELOW_MA20_MOMENTUM_POSITIVE")
        self.assertEqual(self.records["DWN"]["ticker_structure_state"], "BELOW_MA20_MOMENTUM_NEGATIVE")
        self.assertEqual(self.records["NEU"]["ticker_structure_state"], "NEAR_MA20_NEUTRAL")

    def test_insufficient_data_ticker(self) -> None:
        record = self.records["THN"]
        self.assertIsNone(record["entry_state"])
        self.assertEqual(record["ticker_structure_state"], "NOT_AVAILABLE")
        self.assertEqual(record["action"], "WAIT")
        self.assertFalse(record["is_full_position_ready"])
        self.assertIsNone(record["horizon"])
        self.assertEqual(record["data_quality"]["confidence"], "INSUFFICIENT")

    def test_fundamental_cohort_absence_reported_explicitly(self) -> None:
        for ticker in ("REV", "BAS", "EAS", "DWN"):
            with self.subTest(ticker=ticker):
                self.assertEqual(self.records[ticker]["fundamental_context"]["status"], "NOT_IN_FUNDAMENTAL_COHORT")

    def test_fundamental_tier_present_when_in_cohort(self) -> None:
        self.assertEqual(self.records["BRK"]["fundamental_context"]["authority_tier"], "OFFICIAL_QUALIFIED")
        self.assertEqual(self.records["UPT"]["fundamental_context"]["authority_tier"], "PROVIDER_RESEARCH")
        self.assertEqual(self.records["DST"]["fundamental_context"]["authority_tier"], "BLOCKED")

    def test_early_entry_action_only_from_early_reversal_candidate(self) -> None:
        early_entry_tickers = [t for t, r in self.records.items() if r["action"] == "EARLY_ENTRY"]
        self.assertEqual(early_entry_tickers, ["REV"])
        self.assertEqual(self.records["REV"]["entry_state"], "EARLY_REVERSAL_CANDIDATE")

    def test_early_entry_and_accumulate_never_full_position_ready(self) -> None:
        for ticker, record in self.records.items():
            if record["action"] in ("EARLY_ENTRY", "ACCUMULATE_IN_BASE"):
                with self.subTest(ticker=ticker):
                    self.assertFalse(record["is_full_position_ready"])

    def test_is_full_position_ready_true_only_for_fully_qualified_breakout(self) -> None:
        # BRK: BREAKOUT_READY, liquidity ELIGIBLE, OFFICIAL_QUALIFIED+READY fundamental, mixed (not risk-off) market.
        self.assertTrue(self.records["BRK"]["is_full_position_ready"])
        for ticker, record in self.records.items():
            if ticker != "BRK":
                with self.subTest(ticker=ticker):
                    self.assertFalse(record["is_full_position_ready"])

    def test_horizon_downgraded_when_fundamental_missing_or_blocked(self) -> None:
        # DST is DISTRIBUTION_RISK (base horizon SHORT_TERM_FEW_SESSIONS) with BLOCKED fundamental tier
        # -> downgraded to NEXT_SESSION_WATCH.
        self.assertEqual(classifier.HORIZON_BY_ENTRY_STATE["DISTRIBUTION_RISK"], "SHORT_TERM_FEW_SESSIONS")
        self.assertEqual(self.records["DST"]["horizon"], "NEXT_SESSION_WATCH")
        # BRD is BREAKDOWN_RISK (base horizon already NEXT_SESSION_WATCH) with an in-cohort OFFICIAL
        # tier -> stays at the base tier, not further downgraded.
        self.assertEqual(self.records["BRD"]["horizon"], "NEXT_SESSION_WATCH")
        # REV (EARLY_REVERSAL_CANDIDATE, base SHORT_TERM_FEW_SESSIONS) is outside the fundamental
        # cohort entirely (None tier) -> also downgraded.
        self.assertEqual(self.records["REV"]["horizon"], "NEXT_SESSION_WATCH")

    def test_evidence_for_and_against_cite_real_values_not_fabricated(self) -> None:
        record = self.records["BRK"]
        joined_for = " ".join(record["evidence_for"])
        self.assertIn("0.1500", joined_for)  # momentum_20d
        self.assertGreater(len(record["evidence_for"]), 0)
        record_dwn = self.records["DWN"]
        self.assertGreater(len(record_dwn["evidence_against"]), 0)

    def test_confirmation_trigger_and_invalidation_always_present_for_classified_tickers(self) -> None:
        for ticker in _EXPECTED_ENTRY_STATE:
            record = self.records[ticker]
            self.assertTrue(record["confirmation_trigger"])
            self.assertTrue(record["invalidation"])

    def test_no_confirmed_bottom_language_anywhere(self) -> None:
        blob = json.dumps(self.artifact).lower()
        for forbidden in ("confirmed bottom", "confirmed top", "bottom is in", "guaranteed"):
            self.assertNotIn(forbidden, blob)

    def test_no_fabricated_probability_or_target_price(self) -> None:
        # Field NAMES may legitimately name the prohibition (e.g. blocked_outputs' own
        # "probabilities_or_target_prices" key); no per-ticker RECORD may carry a populated
        # probability/target-price/expected-return VALUE.
        forbidden_keys = {"probability", "target_price", "expected_return_pct", "win_rate"}
        for ticker, record in self.records.items():
            with self.subTest(ticker=ticker):
                self.assertTrue(forbidden_keys.isdisjoint(record.keys()))
                self.assertTrue(forbidden_keys.isdisjoint(record.get("signals", {}).keys()))

    def test_no_portfolio_sizing_formula(self) -> None:
        forbidden_keys = {"position_size_pct", "shares_to_buy", "portfolio_weight", "kelly_fraction"}
        for ticker, record in self.records.items():
            with self.subTest(ticker=ticker):
                self.assertTrue(forbidden_keys.isdisjoint(record.keys()))

    def test_is_actionable_false_everywhere(self) -> None:
        self.assertFalse(self.artifact["authority_boundary"]["is_actionable"])
        for record in self.records.values():
            self.assertFalse(record["is_actionable"])


class MarketStateTests(unittest.TestCase):
    def test_risk_on_when_both_descriptors_positive(self) -> None:
        _, _, _, artifact = _build(breadth_descriptor="MARKET_BREADTH_POSITIVE", momentum_descriptor="MOMENTUM_BREADTH_POSITIVE")
        self.assertEqual(artifact["market_state"]["market_state"], "RISK_ON_BROAD_PARTICIPATION")

    def test_risk_off_when_both_descriptors_negative(self) -> None:
        _, _, _, artifact = _build(breadth_descriptor="MARKET_BREADTH_NEGATIVE", momentum_descriptor="MOMENTUM_BREADTH_NEGATIVE")
        self.assertEqual(artifact["market_state"]["market_state"], "RISK_OFF_BROAD_WEAKNESS")
        # Risk-off market context blocks is_full_position_ready even for an otherwise fully
        # qualified BREAKOUT_READY ticker (BRK).
        self.assertEqual(artifact["records"]["BRK"]["entry_state"], "BREAKOUT_READY")
        self.assertFalse(artifact["records"]["BRK"]["is_full_position_ready"])

    def test_mixed_when_descriptors_disagree(self) -> None:
        _, _, _, artifact = _build(breadth_descriptor="MARKET_BREADTH_POSITIVE", momentum_descriptor="MOMENTUM_BREADTH_NEGATIVE")
        self.assertEqual(artifact["market_state"]["market_state"], "MIXED_NO_CLEAR_MARKET_REGIME")

    def test_market_state_shared_by_every_ticker_same_build(self) -> None:
        _, _, _, artifact = _build()
        states = {record["market_state"] for record in artifact["records"].values()}
        self.assertEqual(states, {artifact["market_state"]["market_state"]})


class IdentityAndFailClosedTests(unittest.TestCase):
    def test_determinism_same_input_same_hash(self) -> None:
        descriptive = _descriptive_source()
        screening = _screening_source(descriptive)
        fundamental = _fundamental_source()
        a1 = classifier.build_artifact(descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental, requested_at="t")
        a2 = classifier.build_artifact(descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental, requested_at="t")
        self.assertEqual(a1["artifact_sha256"], a2["artifact_sha256"])
        self.assertEqual(json.dumps(a1, sort_keys=True), json.dumps(a2, sort_keys=True))

    def test_content_identity_recomputes_correctly(self) -> None:
        _, _, _, artifact = _build()
        recomputed = classifier.content_identity(artifact)
        self.assertEqual(recomputed["artifact_sha256"], artifact["artifact_sha256"])
        self.assertEqual(recomputed["artifact_identity"], artifact["artifact_identity"])

    def test_tampered_descriptive_source_fails_closed(self) -> None:
        descriptive = _descriptive_source()
        screening = _screening_source(descriptive)
        fundamental = _fundamental_source()
        tampered = copy.deepcopy(descriptive)
        tampered["records"]["BRK"]["technical_features"]["values"]["momentum_20d"] = 999.0
        with self.assertRaises(classifier.WatchlistTacticalEntryClassifierError):
            classifier.build_artifact(descriptive_source=tampered, screening_source=screening, fundamental_source=fundamental, requested_at="t")

    def test_tampered_screening_source_fails_closed(self) -> None:
        descriptive = _descriptive_source()
        screening = _screening_source(descriptive)
        fundamental = _fundamental_source()
        tampered = copy.deepcopy(screening)
        tampered["screen_membership_counts"]["TREND_AND_POSITIVE_MOMENTUM"] = 999
        with self.assertRaises(classifier.WatchlistTacticalEntryClassifierError):
            classifier.build_artifact(descriptive_source=descriptive, screening_source=tampered, fundamental_source=fundamental, requested_at="t")

    def test_tampered_fundamental_source_fails_closed(self) -> None:
        descriptive = _descriptive_source()
        screening = _screening_source(descriptive)
        fundamental = _fundamental_source()
        tampered = copy.deepcopy(fundamental)
        tampered["records"]["BRK"]["authority_tier"] = "TAMPERED"
        with self.assertRaises(classifier.WatchlistTacticalEntryClassifierError):
            classifier.build_artifact(descriptive_source=descriptive, screening_source=screening, fundamental_source=tampered, requested_at="t")

    def test_screening_built_from_a_different_descriptive_source_fails_closed(self) -> None:
        descriptive_a = _descriptive_source()
        descriptive_b = _descriptive_source(breadth_descriptor="MARKET_BREADTH_POSITIVE", momentum_descriptor="MOMENTUM_BREADTH_POSITIVE")
        screening_from_b = _screening_source(descriptive_b)
        fundamental = _fundamental_source()
        with self.assertRaises(classifier.WatchlistTacticalEntryClassifierError):
            classifier.build_artifact(descriptive_source=descriptive_a, screening_source=screening_from_b, fundamental_source=fundamental, requested_at="t")


class NoNewFeatureComputationTests(unittest.TestCase):
    """Ensures the classifier reads, never recomputes, upstream technical/screening values."""

    def test_momentum_value_copied_verbatim_into_signals(self) -> None:
        _, _, _, artifact = _build()
        self.assertEqual(artifact["records"]["BRK"]["signals"]["momentum_20d"], 0.15)
        self.assertEqual(artifact["records"]["BRD"]["signals"]["momentum_20d"], -0.20)

    def test_momentum_bucket_copied_from_screening_not_recomputed(self) -> None:
        descriptive = _descriptive_source()
        screening = _screening_source(descriptive)
        fundamental = _fundamental_source()
        artifact = classifier.build_artifact(descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental, requested_at="t")
        expected_bucket = screening["records"]["BRK"]["market_relative_comparison"]["momentum_bucket"]
        self.assertEqual(artifact["records"]["BRK"]["signals"]["momentum_bucket"], expected_bucket)


if __name__ == "__main__":
    unittest.main()
