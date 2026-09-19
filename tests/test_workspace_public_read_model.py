"""Unit coverage for the workspace public read-model split (index + detail shards).

See workspace_public_read_model.py's module docstring for why this split exists
(DASHBOARD_PAYLOAD_COMPACTION_AND_INVESTOR_FIRST_IA_V1).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import workspace_public_read_model as wprm  # noqa: E402


def _full_card(ticker: str, **overrides) -> dict:
    card = {
        "ticker": ticker,
        "sector": "STEEL",
        "as_of_session": "2026-09-18",
        "research_stance": "INITIATE_RESEARCH_CANDIDATE",
        "research_stance_readiness": "RESEARCH_READY_CONDITIONAL",
        "entry_state": "BREAKOUT_READY",
        "entry_action": "BUY_ON_CONFIRMATION",
        "setup_tags": ["BREAKOUT_CONFIRMED_BY_RULE"],
        "tactical": {"primary_entry_state": "BREAKOUT_READY"},
        "fundamental": {"state": "PROFITABLE", "trajectory": "PROFIT_GROWTH", "current_features": {"deep": True}},
        "valuation": {
            "relative_research_state": "ATTRACTIVE_RELATIVE_RESEARCH",
            "usable_relative_method_count": 2,
            "method_diagnostics": {"pe_ttm": {"status": "READY_RESEARCH_ONLY", "value": 8.1}},
        },
        "liquidity": {"readiness": "LIQUIDITY_RESEARCH_PROXY"},
        "catalyst": {"status": "WATCH_FOR_EXECUTION", "event_classifications": ["A", "B"]},
        "lineage": {"per_axis_freshness": {"tactical": "CURRENT"}, "blockers": []},
        "why": {
            "deterministic_reasons": ["R1", "R2", "R3", "R4"],
            "financial_analysis": {"compact": {"huge": "diagnostic payload"}},
        },
        "counter_thesis": {"key_counter_thesis": ["C1", "C2", "C3", "C4"], "warnings": []},
        "reference_trigger": {"trigger_level_exists": True, "trigger_level": 28.5},
        "invalidation": {
            "technical": {"boundary_type": "PRICE_BELOW", "status": "READY", "semantic": "X"},
            "fundamental": {"status": "UNAVAILABLE"},
        },
        "confirmation": {"status": "READY", "confirmation_trigger_state": "NOT_AVAILABLE"},
        "market_sector": {"breadth_regime": "RISK_ON", "sector_relative_context": {"leadership_state": "LEADER"}},
        "signal_velocity": {"overall_transition_state": "MIXED_TRANSITION", "evidence_quality": "COMPLETE_RETAINED_EVIDENCE"},
        "flow_price": {"relationship": "SUPPORTIVE", "cohort_membership": "IN_CURRENT_FLOW_RESEARCH_COHORT", "evidence_quality": "PARTIAL_RETAINED_EVIDENCE"},
        "official_research_scope": {"scope_bucket": "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"},
        "display_metrics": {"pe_ttm": {"display_state": "AVAILABLE", "value": 8.1}},
        "portfolio": {"evaluated": False, "status": "NOT_EVALUATED"},
    }
    card.update(overrides)
    return card


def _payload(cards: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "contract_version": "investment_decision_workspace_projection/v1",
        "as_of_session": "2026-09-18",
        "artifact_identity": "investment_decision_workspace_projection/v1:abc123",
        "cards": cards,
        "coverage": {"ticker_denominator": len(cards), "zero_silent_ticker_drops": True},
        "official_scope_coverage": {"workspace_denominator": len(cards)},
        "blocked_outputs": {"universal_score": "SCORING_PROHIBITED"},
        "authority_effect": "NONE / PRODUCT_WORKSPACE_ONLY",
        "display_metric_catalog": {"pe_ttm": {"label": "P/E"}},
        "milestone": "INVESTMENT_DECISION_WORKSPACE_V1",
        "source_artifacts": {"opportunity_context": "opportunity_context/v1:xyz"},
    }


class ShardKeyTests(unittest.TestCase):
    def test_alphabetic_ticker_buckets_by_first_letter(self):
        self.assertEqual(wprm.shard_key_for_ticker("HPG"), "H")
        self.assertEqual(wprm.shard_key_for_ticker("a32"), "A")

    def test_non_alphabetic_leading_character_falls_back(self):
        self.assertEqual(wprm.shard_key_for_ticker("32A"), "_")
        self.assertEqual(wprm.shard_key_for_ticker(""), "_")


class BuildPublicReadModelTests(unittest.TestCase):
    def setUp(self):
        self.cards = {"HPG": _full_card("HPG"), "HSG": _full_card("HSG"), "VNM": _full_card("VNM")}
        self.payload = _payload(self.cards)

    def test_zero_silent_drop_across_the_split(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        self.assertEqual(set(index_doc["cards"]), set(self.cards))
        rebuilt = {t for shard in shards.values() for t in shard["tickers"]}
        self.assertEqual(rebuilt, set(self.cards))
        self.assertEqual(sum(s["ticker_count"] for s in shards.values()), len(self.cards))

    def test_alphabetic_tickers_bucket_together(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        # HPG and HSG share the "H" bucket; VNM is alone in "V".
        self.assertEqual(set(shards.keys()), {"H", "V"})
        self.assertEqual(set(shards["H"]["tickers"]), {"HPG", "HSG"})
        self.assertEqual(set(shards["V"]["tickers"]), {"VNM"})

    def test_shard_reference_on_index_card_matches_actual_shard(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        for ticker, thin in index_doc["cards"].items():
            key = thin["detail_shard"]
            self.assertIn(ticker, shards[key]["tickers"])

    def test_shard_contains_full_unmodified_card(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        shard = shards["H"]
        self.assertEqual(shard["tickers"]["HPG"], self.cards["HPG"])
        self.assertIn("current_features", shard["tickers"]["HPG"]["fundamental"])
        self.assertIn("method_diagnostics", shard["tickers"]["HPG"]["valuation"])
        self.assertIn("compact", shard["tickers"]["HPG"]["why"]["financial_analysis"])

    def test_index_card_omits_deep_diagnostic_fields(self):
        index_doc, _shards = wprm.build_public_read_model(self.payload)
        thin = index_doc["cards"]["HPG"]
        self.assertNotIn("current_features", thin["fundamental"])
        self.assertNotIn("method_diagnostics", thin["valuation"])
        self.assertNotIn("financial_analysis", thin["why"])
        self.assertNotIn("display_metrics", thin)
        self.assertNotIn("portfolio", thin)

    def test_index_card_keeps_every_field_used_by_list_filter_and_search_views(self):
        index_doc, _shards = wprm.build_public_read_model(self.payload)
        thin = index_doc["cards"]["HPG"]
        self.assertEqual(thin["research_stance"], "INITIATE_RESEARCH_CANDIDATE")
        self.assertEqual(thin["entry_state"], "BREAKOUT_READY")
        self.assertEqual(thin["fundamental"]["state"], "PROFITABLE")
        self.assertEqual(thin["fundamental"]["trajectory"], "PROFIT_GROWTH")
        self.assertEqual(thin["valuation"]["relative_research_state"], "ATTRACTIVE_RELATIVE_RESEARCH")
        self.assertEqual(thin["liquidity"]["readiness"], "LIQUIDITY_RESEARCH_PROXY")
        self.assertEqual(thin["catalyst"]["status"], "WATCH_FOR_EXECUTION")
        self.assertEqual(thin["lineage"]["per_axis_freshness"], {"tactical": "CURRENT"})
        self.assertEqual(thin["why"]["deterministic_reasons"], ["R1", "R2", "R3"])  # capped at 3
        self.assertEqual(thin["reference_trigger"]["trigger_level"], 28.5)
        self.assertEqual(thin["invalidation"]["technical"]["boundary_type"], "PRICE_BELOW")
        self.assertEqual(thin["invalidation"]["fundamental"]["status"], "UNAVAILABLE")
        self.assertEqual(thin["signal_velocity"]["overall_transition_state"], "MIXED_TRANSITION")
        self.assertEqual(thin["flow_price"]["relationship"], "SUPPORTIVE")
        self.assertEqual(thin["official_research_scope"], {"scope_bucket": "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"})

    def test_index_and_shards_carry_same_session_and_identity_for_binding(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        self.assertEqual(index_doc["as_of_session"], "2026-09-18")
        self.assertEqual(index_doc["source_artifact_identity"], self.payload["artifact_identity"])
        for shard in shards.values():
            self.assertEqual(shard["as_of_session"], "2026-09-18")
            self.assertEqual(shard["source_artifact_identity"], self.payload["artifact_identity"])

    def test_shard_manifest_hash_matches_recomputed_shard_hash(self):
        index_doc, shards = wprm.build_public_read_model(self.payload)
        for key, entry in index_doc["shard_manifest"].items():
            self.assertEqual(entry["sha256"], wprm._sha256_of(shards[key]))
            self.assertEqual(entry["ticker_count"], shards[key]["ticker_count"])
            self.assertEqual(entry["path"], f"data/workspace_detail/{key}.json")

    def test_top_level_static_fields_pass_through_once(self):
        index_doc, _shards = wprm.build_public_read_model(self.payload)
        self.assertEqual(index_doc["display_metric_catalog"], {"pe_ttm": {"label": "P/E"}})
        self.assertEqual(index_doc["coverage"]["ticker_denominator"], 3)
        self.assertEqual(index_doc["contract_version"], "workspace_index/v1")
        self.assertEqual(index_doc["source_artifacts"], {"opportunity_context": "opportunity_context/v1:xyz"})

    def test_missing_cards_raises(self):
        with self.assertRaises(ValueError):
            wprm.build_public_read_model({"as_of_session": "2026-09-18"})

    def test_ticker_missing_optional_nested_axes_does_not_raise(self):
        sparse = {"HPG": {"ticker": "HPG"}}
        index_doc, shards = wprm.build_public_read_model(_payload(sparse))
        self.assertEqual(index_doc["cards"]["HPG"]["ticker"], "HPG")
        self.assertIsNone(index_doc["cards"]["HPG"]["official_research_scope"])
        self.assertEqual(shards["H"]["tickers"]["HPG"], {"ticker": "HPG"})


if __name__ == "__main__":
    unittest.main()
