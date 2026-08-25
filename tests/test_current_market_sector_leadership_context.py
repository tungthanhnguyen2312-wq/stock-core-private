"""Contract regressions for the current official-universe leadership context."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import current_official_market_universe as official
import current_market_sector_leadership_context as leadership
import export_ai_bundle as bundle
from current_market_screening_opportunity_comparison_foundation import content_identity as screening_identity
from market_wide_current_descriptive_research import content_identity as descriptive_identity


SESSION = "2026-08-24"


def _signed_descriptive(records: dict) -> dict:
    artifact = {"contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION, "records": records}
    artifact.update(descriptive_identity(artifact))
    return artifact


def _signed_screening(tickers: list[str], descriptive: dict, *, session: str = SESSION) -> dict:
    artifact = {
        "contract_version": "current_market_screening_and_opportunity_comparison_foundation/v1",
        "session": session,
        "input_lineage": {"current_descriptive_artifact_identity": descriptive["artifact_identity"]},
        "records": {ticker: {"ticker": ticker} for ticker in tickers},
    }
    artifact.update(screening_identity(artifact))
    return artifact


def _signed_official(tickers: list[str]) -> dict:
    artifact = {
        "contract_version": "current_official_market_universe/v1",
        "records": {ticker: {"ticker": ticker, "stocklookup_candidate": True,
                               "current_universe_status": official.OFFICIAL_CURRENT_EXCHANGE_SECURITY} for ticker in tickers},
        "reconciliation": {"official_total_match": len(tickers)},
    }
    artifact.update(official._identity(artifact))
    return artifact


def _record(ticker: str, daily_return: float | None, momentum: float | None, trend: str | None, sector: str | None) -> dict:
    record = {"ticker": ticker}
    if daily_return is not None:
        record.update({
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True,
                                   "values": {"return_1d": daily_return, "momentum_20d": momentum}},
            "trend_state": trend,
        })
    if sector is not None:
        record["sector_classification"] = {
            "classification_authority": "QUALIFIED_CLASSIFICATION",
            "classification_namespace": "QUALIFIED_ENTITY_CLASS",
            "entity_class": sector,
        }
    return record


def _fixture_inputs() -> tuple[dict, dict, dict]:
    records = {
        "A1": _record("A1", .05, .60, "ABOVE_MA20", "ALPHA"),
        "A2": _record("A2", .04, .60, "ABOVE_MA20", "ALPHA"),
        "A3": _record("A3", .03, .40, "ABOVE_MA20", "ALPHA"),
        "A4": _record("A4", .02, .30, "ABOVE_MA20", "ALPHA"),
        "A5": _record("A5", .01, .20, "ABOVE_MA20", "ALPHA"),
        "B1": _record("B1", -.05, -.60, "AT_OR_BELOW_MA20", "BETA"),
        "B2": _record("B2", -.04, -.50, "AT_OR_BELOW_MA20", "BETA"),
        "B3": _record("B3", -.03, -.40, "AT_OR_BELOW_MA20", "BETA"),
        "B4": _record("B4", -.02, -.30, "AT_OR_BELOW_MA20", "BETA"),
        "B5": _record("B5", -.01, -.20, "AT_OR_BELOW_MA20", "BETA"),
        "C1": _record("C1", .01, .10, "ABOVE_MA20", "TINY"),
        "UNK": _record("UNK", .01, .10, "ABOVE_MA20", None),
        "MISS": _record("MISS", None, None, None, "ALPHA"),
    }
    descriptive = _signed_descriptive(records)
    return descriptive, _signed_screening(sorted(records), descriptive), _signed_official(sorted(records))


class CurrentMarketSectorLeadershipContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptive, self.screening, self.official = _fixture_inputs()
        self.artifact = leadership.build_artifact(
            current_descriptive=self.descriptive, current_screening=self.screening,
            current_official_universe=self.official,
        )

    def test_exact_session_denominator_and_missing_coverage_are_separate(self) -> None:
        market = self.artifact["market"]
        self.assertEqual((market["official_universe_count"], market["exact_session_observed_count"], market["missing_current_session_count"]), (13, 12, 1))
        self.assertEqual(market["advancing"] + market["declining"] + market["unchanged"], 12)
        self.assertEqual(market["unchanged"], 0)
        self.assertIn("MISSING_CURRENT_SESSION_BARS_ARE_COVERAGE_GAPS_NOT_UNCHANGED_OR_ZERO_RETURNS", market["warnings"])

    def test_group_states_relative_ties_unknown_and_data_limited_are_explicit(self) -> None:
        groups = self.artifact["groups"]["records"]
        alpha = next(row for row in groups.values() if row["group_identity"] == "ALPHA")
        beta = next(row for row in groups.values() if row["group_identity"] == "BETA")
        tiny = next(row for row in groups.values() if row["group_identity"] == "TINY")
        self.assertEqual(alpha["leadership_state"], "LEADING")
        self.assertEqual(beta["leadership_state"], "WEAKENING")
        self.assertEqual(tiny["leadership_state"], "DATA_LIMITED")
        a1, a2 = self.artifact["ticker_contexts"]["A1"], self.artifact["ticker_contexts"]["A2"]
        self.assertEqual(a1["sector_relative_momentum"]["momentum_percentile_descriptive"], a2["sector_relative_momentum"]["momentum_percentile_descriptive"])
        self.assertEqual(self.artifact["ticker_contexts"]["UNK"]["sector_relative_momentum"]["reason"], "SECTOR_IDENTITY_UNKNOWN")
        self.assertEqual(self.artifact["ticker_contexts"]["MISS"]["status"], "DATA_LIMITED")

    def test_session_or_lineage_mismatch_fails_closed(self) -> None:
        bad = _signed_screening(sorted(self.descriptive["records"]), self.descriptive, session="2026-08-21")
        with self.assertRaisesRegex(leadership.CurrentMarketSectorLeadershipContextError, "SCREENING_SESSION_MISMATCH"):
            leadership.build_artifact(current_descriptive=self.descriptive, current_screening=bad, current_official_universe=self.official)
        bad = copy.deepcopy(self.official)
        bad["reconciliation"]["official_total_match"] = 99
        bad.update(official._identity(bad))
        with self.assertRaisesRegex(leadership.CurrentMarketSectorLeadershipContextError, "OFFICIAL_UNIVERSE_DENOMINATOR_MISMATCH"):
            leadership.build_artifact(current_descriptive=self.descriptive, current_screening=self.screening, current_official_universe=bad)

    def test_replay_is_deterministic_and_authority_is_descriptive_only(self) -> None:
        again = leadership.build_artifact(current_descriptive=self.descriptive, current_screening=self.screening, current_official_universe=self.official)
        self.assertEqual(self.artifact["artifact_identity"], again["artifact_identity"])
        leadership.replay(self.artifact)
        self.assertFalse(self.artifact["authority_boundary"]["is_actionable"])
        self.assertEqual(self.artifact["blocked_outputs"]["strategy_eligibility"], "NOT_MODIFIED")
        self.assertEqual(self.artifact["blocked_outputs"]["research_priority"], "NOT_MODIFIED")
        self.assertEqual(self.artifact["blocked_outputs"]["entry_action"], "NOT_MODIFIED")
        inspectable = copy.deepcopy(self.artifact)
        inspectable.pop("blocked_outputs")
        serialized = json.dumps(inspectable)
        self.assertNotIn("target_price", serialized)
        self.assertNotIn("recommendation", serialized)


class ExportAttachmentTests(unittest.TestCase):
    def test_opt_in_attachment_is_verified_pass_through_and_preserves_existing_decisions(self) -> None:
        descriptive, screening, official_artifact = _fixture_inputs()
        artifact = leadership.build_artifact(current_descriptive=descriptive, current_screening=screening, current_official_universe=official_artifact)
        entries = {"A1": {"strategy_eligibility": "existing", "research_priority": "existing", "entry_action": "existing"}}
        untouched = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_market_sector_leadership_context(entries, False, "not-read.json"), untouched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leadership.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = bundle.attach_current_market_sector_leadership_context(entries, True, str(path))
            attached = result["A1"]["current_market_sector_leadership_context"]
            self.assertFalse(attached["is_actionable"])
            self.assertEqual(attached["ticker_context"], artifact["ticker_contexts"]["A1"])
            self.assertEqual(result["A1"]["strategy_eligibility"], "existing")
            self.assertEqual(result["A1"]["research_priority"], "existing")
            self.assertEqual(result["A1"]["entry_action"], "existing")
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["market"]["advancing"] = 999
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn("current_market_sector_leadership_context", bundle.attach_current_market_sector_leadership_context({"A1": {}}, True, str(path))["A1"])


if __name__ == "__main__":
    unittest.main()
