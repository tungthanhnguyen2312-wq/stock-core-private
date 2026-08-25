"""Hardening tests for frozen current_research_decision_packet/v1."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import current_research_decision_packet as packet
import export_ai_bundle as bundle
from current_corporate_event_context import content_identity as event_identity
from current_evidence_bound_scenario import content_identity as scenario_identity
from current_financial_momentum_context import content_identity as financial_identity
from current_market_sector_leadership_context import content_identity as leadership_identity
from current_opportunity_prioritization import content_identity as opportunity_identity
from current_research_risk_register import content_identity as risk_identity
from market_wide_current_valuation_input_scaleout import content_identity as valuation_identity
from market_wide_historical_research_context import content_identity as historical_identity

ROOT = Path(__file__).resolve().parents[1]
OPTIONAL = tuple(packet.SPECS)
PATHS = {
    "opportunity": ROOT / "operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    "scenario": ROOT / "operations-review/current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
    "risk_register": ROOT / "operations-review/current-research-risk-register-v1/current_research_risk_register_artifact.json",
    "market_sector": ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json",
    "financial_momentum": ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json",
    "corporate_event": ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "valuation": ROOT / "operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json",
    "historical": ROOT / "operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json",
}
FROZEN_IDENTITY_PATHS = [
    ROOT / "operations-review/current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
    ROOT / "operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    ROOT / "operations-review/watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    ROOT / "operations-review/polymorphic-current-strategy-classification-v1-20260824/polymorphic_current_strategy_classification_artifact.json",
    ROOT / "operations-review/current-daily-decision-research-product-v2-20260824/current_daily_decision_research_product_artifact.json",
]
SOURCE_MATRIX = (
    ("opportunity", "current_opportunity_prioritization/v1", opportunity_identity),
    ("scenario", "current_evidence_bound_scenario/v1", scenario_identity),
    ("risk_register", "current_research_risk_register/v1", risk_identity),
    ("market_sector", "current_market_sector_leadership_context/v1", leadership_identity),
    ("financial_momentum", "current_financial_momentum_context/v1", financial_identity),
    ("corporate_event", "current_corporate_event_context/v1", event_identity),
    ("valuation", "market_wide_current_valuation/v1", valuation_identity),
    ("historical", "market_wide_historical_research_context/v1", historical_identity),
)
COMPONENT_PAYLOAD = {
    "scenario": "scenario_context", "risk_register": "risk_register",
    "market_sector": "market_sector_context", "financial_momentum": "financial_momentum_context",
    "corporate_event": "corporate_event_context", "valuation": "valuation_context",
    "historical": "historical_research_context",
}


def _sign(payload: dict, identity) -> dict:
    artifact = copy.deepcopy(payload)
    artifact.update(identity(artifact))
    return artifact


def _decision(ticker: str = "AAA", **overrides) -> dict:
    row = {
        "ticker": ticker, "priority_tier": "MONITOR", "entry_action": "WAIT",
        "eligible_strategies": ["TREND_MOMENTUM"], "lane_priority": {"TREND_MOMENTUM": "MONITOR"},
        "tactical_state": "UPTREND_CONFIRMED", "scenario_status": "SCENARIO_READY",
        "blocking_reasons": [], "invalidation_or_context_warnings": [],
        "source_input_identities": {"tactical": "t:1"},
    }
    row.update(overrides)
    return row


def _opportunity(records: dict, session: str = "2026-08-21") -> dict:
    return _sign({
        "schema_version": "1.0.0", "contract_version": "current_opportunity_prioritization/v1",
        "research_session": session, "records": records,
    }, opportunity_identity)


def _optional_artifacts() -> dict:
    ticker = "AAA"
    return {
        "scenario": _sign({
            "contract_version": "current_evidence_bound_scenario/v1", "session": "2025-01-01",
            "records": {ticker: {
                "scenario_disposition": "SCENARIO_READY", "current_state": {"entry_state": "UPTREND_CONFIRMED"},
                "bear_case": {"probability_status": "UNKNOWN_UNCALIBRATED"},
                "base_case": {"probability_status": "UNKNOWN_UNCALIBRATED"},
                "bull_case": {"probability_status": "UNKNOWN_UNCALIBRATED"},
                "authority_limitations": ["passthrough"], "entry_action": "SHOULD_NOT_OVERRIDE",
            }},
        }, scenario_identity),
        "risk_register": _sign({
            "contract_version": "current_research_risk_register/v1",
            "records": {ticker: {
                "ticker": ticker, "material_risks": [{"risk_type": "FINANCIAL_STRESS", "source_as_of": "FY2024"}],
                "watch_risks": [{"risk_type": "SECTOR_HEADWIND", "source_as_of": "2026-08-25"}],
                "data_authority_limitations": [{"risk_type": "EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE", "source_as_of": "2026-08-24"}],
                "unresolved_conflicts": [], "risk_register_status": "MATERIAL_RISKS_ESTABLISHED",
                "entry_action": "SHOULD_NOT_OVERRIDE",
            }},
            "source_contexts": {"historical": {"as_of": "2026-08-24"}, "valuation": {"as_of": "2026-08-21"}},
        }, risk_identity),
        "market_sector": _sign({
            "contract_version": "current_market_sector_leadership_context/v1", "session": "2024-01-01",
            "market": {"current_breadth_state": "MIXED_BREADTH", "exact_session_observed_count": 1},
            "ticker_contexts": {ticker: {
                "ticker": ticker, "status": "PARTIAL",
                "coverage_limitations": ["NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"],
                "sector_leadership_context": {"status": "AVAILABLE", "leadership_state": "MIXED"},
            }},
        }, leadership_identity),
        "financial_momentum": _sign({
            "contract_version": "current_financial_momentum_context/v1", "session": "2020-01-01",
            "records": {ticker: {
                "as_of_financial_period": "FY2025", "financial_momentum_state": "EARNINGS_IMPROVING",
                "coverage_status": "PARTIAL", "evidence_tier": "PROVIDER_RESEARCH",
                "components": {"earnings_growth": {"status": "AVAILABLE"}}, "blockers": [], "warnings": ["provider_research_is_not_official_qualified"],
            }},
        }, financial_identity),
        "corporate_event": _sign({
            "contract_version": "current_corporate_event_context/v1", "research_session": "2023-01-01",
            "records": {ticker: {
                "qualified_event_count": 2, "planned_unresolved_count": 1, "temporal_incomplete_count": 0,
                "data_limited_count": 0, "conflicting_count": 0, "research_session": "2023-01-01",
                "events": [
                    {"event_id": "e1", "event_status": "PLANNED_NOT_EXECUTED", "event_type": "BONUS_OR_STOCK_DIVIDEND",
                     "known_at": "2023-02-01", "published_at": "2023-02-02", "record_date": "2023-06-01",
                     "ex_date": "2023-05-30", "effective_date": "2023-06-15", "execution_date": None,
                     "temporal_completeness": "COMPLETE", "evidence_tier": "OFFICIAL_QUALIFIED"},
                    {"event_id": "e2", "event_status": "EXECUTED", "event_type": "CASH_DIVIDEND",
                     "known_at": "2022-01-01", "published_at": "2022-01-02", "record_date": "2022-03-01",
                     "ex_date": "2022-02-27", "effective_date": "2022-03-10", "execution_date": "2022-03-20",
                     "temporal_completeness": "COMPLETE", "evidence_tier": "OFFICIAL_QUALIFIED"},
                ],
            }},
        }, event_identity),
        "valuation": _sign({
            "contract_version": "market_wide_current_valuation/v1", "valuation_session": "2021-01-01",
            "records": {ticker: {
                "price_input": {"session": "2021-01-01"}, "share_basis_input": {"status": "PROVIDER_REPORTED_LAGGED"},
                "metrics": {
                    "P/E": {"status": "RESEARCH_USABLE", "blocked_reasons": [], "price_session": "2021-01-01", "authority_tier": "RESEARCH_USABLE"},
                    "P/B": {"status": "BLOCKED", "blocked_reasons": ["SHARE_BASIS"], "price_session": "2021-01-01"},
                    "P/S": {"status": "NOT_APPLICABLE"},
                    "market_cap": {"status": "READY", "price_session": "2021-01-01"},
                },
                "value_strategy": {"status": "BLOCKED"},
            }},
        }, valuation_identity),
        "historical": _sign({
            "contract_version": "market_wide_historical_research_context/v1", "session": "2022-01-01",
            "authority_boundary": {
                "price_basis": "ADJUSTED_RETROSPECTIVE", "RAW_AS_TRADED": "NOT_PROMOTED", "PIT": "BLOCKED",
            },
            "records": {ticker: {
                "as_of_session": "2022-01-01", "context_status": "AVAILABLE",
                "structural_state": {"value": "TREND_CONTINUATION"},
                "volatility_regime": {"regime": "LOW"}, "momentum": {"sign": "POSITIVE"},
                "drawdown": {"status": "AVAILABLE", "current_drawdown": -0.1},
            }},
        }, historical_identity),
    }


def _break(artifact: dict) -> dict:
    broken = copy.deepcopy(artifact)
    broken["coverage"] = {"tampered": True}
    return broken


def _build(**overrides):
    components = _optional_artifacts()
    components.update(overrides)
    return packet.build_artifact(opportunity=_opportunity({"AAA": _decision()}), **components)


class ComponentIsolationTests(unittest.TestCase):
    def test_valid_absent_and_malformed_are_local_and_do_not_fail_the_packet(self) -> None:
        present = _build()
        self.assertEqual([present["component_manifest"][name]["status"] for name in OPTIONAL], ["PRESENT"] * 7)
        self.assertEqual(present["records"]["AAA"]["packet_status"], "COMPLETE_FOR_AVAILABLE_COMPONENTS")
        self.assertEqual(present["records"]["AAA"]["unresolved_components"], [])
        for name in OPTIONAL:
            absent = _build(**{name: None})
            self.assertEqual(absent["component_manifest"][name]["status"], "ABSENT")
            self.assertEqual(absent["component_manifest"][name]["authority_use_status"], "OPTIONAL_NOT_SUPPLIED")
            self.assertIsNone(absent["component_manifest"][name]["source_artifact_identity"])
            self.assertNotIn(COMPONENT_PAYLOAD[name], absent["records"]["AAA"]["components"])
            self.assertIn(name, absent["records"]["AAA"]["unresolved_components"])
            self.assertEqual(absent["records"]["AAA"]["packet_status"], "PARTIAL")
            self.assertEqual(absent["records"]["AAA"]["current_decision_context"]["entry_action"], "WAIT")
            for other in OPTIONAL:
                if other != name:
                    self.assertEqual(absent["component_manifest"][other]["status"], "PRESENT")
                    self.assertIn(COMPONENT_PAYLOAD[other], absent["records"]["AAA"]["components"])
            malformed = _build(**{name: _break(_optional_artifacts()[name])})
            row = malformed["component_manifest"][name]
            self.assertEqual(row["status"], "MALFORMED")
            self.assertEqual(row["authority_use_status"], "FAIL_CLOSED_LOCALLY")
            self.assertIsNone(row["source_as_of"])
            self.assertNotEqual(row["status"], "PRESENT")
            self.assertNotIn(COMPONENT_PAYLOAD[name], malformed["records"]["AAA"]["components"])
            self.assertEqual(malformed["records"]["AAA"]["current_decision_context"]["entry_action"], "WAIT")
            for other in OPTIONAL:
                if other != name:
                    self.assertEqual(malformed["component_manifest"][other]["status"], "PRESENT")
                    self.assertIn(COMPONENT_PAYLOAD[other], malformed["records"]["AAA"]["components"])

    def test_invalid_opportunity_fails_closed_without_a_packet(self) -> None:
        with self.assertRaises(packet.CurrentResearchDecisionPacketError):
            packet.build_artifact(opportunity={"contract_version": "current_opportunity_prioritization/v1", "records": {}})


class DecisionImmutabilityTests(unittest.TestCase):
    def test_packet_quotes_opportunity_and_ignores_scenario_risk_overrides(self) -> None:
        opportunity = _opportunity({"AAA": _decision(entry_action="EARLY_ENTRY", priority_tier="PRIORITY_NOW", eligible_strategies=["EARLY_REVERSAL"])})
        before = copy.deepcopy(opportunity)
        artifact = packet.build_artifact(opportunity=opportunity, **_optional_artifacts())
        ctx = artifact["records"]["AAA"]["current_decision_context"]
        self.assertEqual(ctx["entry_action"], "EARLY_ENTRY")
        self.assertEqual(ctx["priority_tier"], "PRIORITY_NOW")
        self.assertEqual(ctx["eligible_strategies"], ["EARLY_REVERSAL"])
        self.assertEqual(ctx["tactical_state"], "UPTREND_CONFIRMED")
        self.assertNotEqual(ctx["entry_action"], artifact["records"]["AAA"]["components"]["scenario_context"].get("entry_action"))
        self.assertEqual(opportunity, before)
        opportunity["records"]["AAA"]["entry_action"] = "AVOID"
        self.assertEqual(artifact["records"]["AAA"]["current_decision_context"]["entry_action"], "EARLY_ENTRY")


class ComponentAuthorityTests(unittest.TestCase):
    def test_passthrough_preserves_component_authority_and_does_not_unify_dates(self) -> None:
        artifact = _build()
        packet.replay(artifact)
        self.assertEqual(artifact["research_session"], "2026-08-21")
        manifest = artifact["component_manifest"]
        self.assertEqual(list(manifest), list(OPTIONAL))
        self.assertEqual(manifest["scenario"]["source_as_of"], "2025-01-01")
        self.assertEqual(manifest["market_sector"]["source_as_of"], "2024-01-01")
        self.assertEqual(manifest["financial_momentum"]["source_as_of"], "2020-01-01")
        self.assertEqual(manifest["corporate_event"]["source_as_of"], "2023-01-01")
        self.assertEqual(manifest["valuation"]["source_as_of"], "2021-01-01")
        self.assertEqual(manifest["historical"]["source_as_of"], "2022-01-01")
        self.assertIsNone(manifest["risk_register"]["source_as_of"])
        row = artifact["records"]["AAA"]["components"]
        self.assertEqual(row["scenario_context"]["scenario_disposition"], "SCENARIO_READY")
        self.assertIn("bear_case", row["scenario_context"])
        self.assertNotIn("probability", row["scenario_context"])
        self.assertNotIn("entry_action", row["scenario_context"])
        risk = row["risk_register"]
        self.assertEqual([item["risk_type"] for item in risk["material_risks"]], ["FINANCIAL_STRESS"])
        self.assertEqual([item["risk_type"] for item in risk["watch_risks"]], ["SECTOR_HEADWIND"])
        self.assertEqual([item["risk_type"] for item in risk["data_authority_limitations"]], ["EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE"])
        self.assertEqual(risk["unresolved_conflicts"], [])
        self.assertEqual(risk["material_risks"][0]["source_as_of"], "FY2024")
        self.assertEqual(row["financial_momentum_context"]["evidence_tier"], "PROVIDER_RESEARCH")
        self.assertEqual(row["financial_momentum_context"]["as_of_financial_period"], "FY2025")
        self.assertNotEqual(row["financial_momentum_context"]["as_of_financial_period"], artifact["research_session"])
        metrics = row["valuation_context"]["metrics"]
        self.assertEqual(metrics["market_cap"]["status"], "READY")
        self.assertEqual(metrics["P/E"]["status"], "RESEARCH_USABLE")
        self.assertEqual(metrics["P/B"]["status"], "BLOCKED")
        self.assertEqual(metrics["P/S"]["status"], "NOT_APPLICABLE")
        self.assertEqual(row["valuation_context"]["valuation_session"], "2021-01-01")
        events = row["corporate_event_context"]["events"]
        source_event = _optional_artifacts()["corporate_event"]["records"]["AAA"]["events"][0]
        self.assertEqual(events[0]["ex_date"], source_event["ex_date"])
        self.assertNotEqual(events[0]["ex_date"], source_event["record_date"])
        self.assertEqual(events[0]["event_status"], "PLANNED_NOT_EXECUTED")
        self.assertIsNone(events[0]["execution_date"])
        self.assertEqual(events[1]["event_status"], "EXECUTED")
        self.assertEqual(events[1]["execution_date"], "2022-03-20")
        self.assertEqual({events[0]["known_at"], events[0]["published_at"], events[0]["effective_date"], events[0]["execution_date"]},
                         {"2023-02-01", "2023-02-02", "2023-06-15", None})
        hist = row["historical_research_context"]
        self.assertEqual(hist["as_of_session"], "2022-01-01")
        self.assertEqual(hist["authority_boundary"]["price_basis"], "ADJUSTED_RETROSPECTIVE")
        self.assertEqual(hist["authority_boundary"]["RAW_AS_TRADED"], "NOT_PROMOTED")
        self.assertEqual(hist["authority_boundary"]["PIT"], "BLOCKED")
        self.assertIn("NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT", row["market_sector_context"]["ticker_context"]["coverage_limitations"])


class IdentityAndForbiddenTests(unittest.TestCase):
    def test_canonical_identity_changes_with_material_input_not_with_dict_order(self) -> None:
        first = _build()
        same = _build()
        self.assertEqual(first["artifact_sha256"], same["artifact_sha256"])
        opt = _optional_artifacts()
        ordered = packet.build_artifact(opportunity=_opportunity({"AAA": _decision(), "BBB": _decision("BBB")}), **opt)
        reversed_opp = packet.build_artifact(opportunity=_opportunity({"BBB": _decision("BBB"), "AAA": _decision()}), **opt)
        self.assertEqual(ordered["artifact_sha256"], reversed_opp["artifact_sha256"])
        without_hist = _build(historical=None)
        self.assertNotEqual(first["artifact_sha256"], without_hist["artifact_sha256"])
        packet.replay(first)
        self.assertNotIn("generated_at", first)
        self.assertNotIn("created_at", first)

    def test_no_newly_derived_forbidden_outputs_including_nested_shapes(self) -> None:
        artifact = _build()
        row = artifact["records"]["AAA"]
        forbidden = {
            "recommendation", "probability", "expected_return", "target_price", "position_size",
            "sizing", "confidence", "global_authority_score", "participation", "capacity",
        }
        self.assertTrue(forbidden.isdisjoint(row))
        self.assertTrue(forbidden.isdisjoint(row["current_decision_context"]))
        self.assertTrue(forbidden.isdisjoint(artifact["authority_boundary"]))
        self.assertNotIn(row["current_decision_context"]["entry_action"], {"BUY", "SELL", "HOLD"})
        self.assertFalse(artifact["authority_boundary"]["is_actionable"])
        self.assertTrue(artifact["authority_boundary"]["no_global_authority_score"])
        nested = json.dumps(row["components"]["scenario_context"])
        self.assertNotRegex(nested, r'"probability"\s*:\s*[0-9]')
        self.assertNotIn("BUY", json.dumps(row["current_decision_context"]))


class ExportFailClosedTests(unittest.TestCase):
    def test_attach_default_off_hash_ticker_and_malformed_paths(self) -> None:
        artifact = _build()
        entries = {"AAA": {"research_priority": "keep", "entry_action": "keep", "strategy_eligibility": "keep"}}
        self.assertEqual(bundle.attach_current_research_decision_packet(entries, False, "x.json"), entries)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            ok = bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path))
            self.assertIn("current_research_decision_packet", ok["AAA"])
            self.assertEqual(ok["AAA"]["entry_action"], "keep")
            self.assertEqual(ok["AAA"]["research_priority"], "keep")
            self.assertEqual(ok["AAA"]["strategy_eligibility"], "keep")
            self.assertFalse(ok["AAA"]["current_research_decision_packet"]["is_actionable"])
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["coverage"]["valid_packet_count"] = -1
            path.write_text(json.dumps(tampered), encoding="utf-8")
            rejected = bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path))
            self.assertNotIn("current_research_decision_packet", rejected["AAA"])
            path.write_text("{not json", encoding="utf-8")
            malformed = bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path))
            self.assertNotIn("current_research_decision_packet", malformed["AAA"])
            path.write_text(json.dumps(artifact), encoding="utf-8")
            wrong = bundle.attach_current_research_decision_packet({"ZZZ": {"entry_action": "keep"}}, True, str(path))
            self.assertNotIn("current_research_decision_packet", wrong["ZZZ"])


class MarketWideReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in FROZEN_IDENTITY_PATHS if path.exists()}
        cls.loaded = {}
        cls.matrix = []
        for name, contract, identity in SOURCE_MATRIX:
            path = PATHS[name]
            if not path.exists():
                cls.matrix.append({"name": name, "status": "ENVIRONMENTAL_FIXTURE_ABSENT", "path": str(path)})
                continue
            artifact = json.loads(path.read_bytes().decode("utf-8"))
            cls.loaded[name] = artifact
            ok = artifact.get("contract_version") == contract and artifact.get("artifact_sha256") == identity(artifact).get("artifact_sha256")
            cls.matrix.append({"name": name, "status": "VERIFIED" if ok else "IDENTITY_MISMATCH", "contract": contract})
        if set(PATHS) - set(cls.loaded):
            cls.artifact = None
            return
        cls.inputs = copy.deepcopy(cls.loaded)
        cls.artifact = packet.build_artifact(**cls.loaded)
        cls.frozen_after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in FROZEN_IDENTITY_PATHS if path.exists()}

    def test_bounded_source_contract_matrix(self) -> None:
        self.assertTrue(self.matrix)
        self.assertFalse(any(row["status"] == "IDENTITY_MISMATCH" for row in self.matrix))
        verified = [row["name"] for row in self.matrix if row["status"] == "VERIFIED"]
        absent = [row["name"] for row in self.matrix if row["status"] == "ENVIRONMENTAL_FIXTURE_ABSENT"]
        self.assertEqual(set(verified) | set(absent), {name for name, _, _ in SOURCE_MATRIX})
        if absent:
            self.skipTest("environmental fixtures absent: " + ",".join(absent))

    def test_market_wide_replay_reconciles_and_preserves_decisions(self) -> None:
        if self.artifact is None:
            self.skipTest("retained packet inputs incomplete: " + ",".join(sorted(set(PATHS) - set(self.loaded))))
        packet.replay(self.artifact)
        rebuilt = packet.build_artifact(**self.inputs)
        self.assertEqual(self.artifact["artifact_identity"], rebuilt["artifact_identity"])
        cov = self.artifact["coverage"]
        residual = cov["universe_denominator"] - cov["valid_packet_count"] - cov["partial_count"]
        self.assertEqual(residual, 0)
        self.assertEqual(cov["universe_denominator"], 1507)
        self.assertEqual(cov["universe_denominator"], len(self.artifact["records"]))
        self.assertEqual(set(self.artifact["records"]), set(self.inputs["opportunity"]["records"]))
        self.assertEqual(list(self.artifact["component_manifest"]), list(OPTIONAL))
        self.assertTrue(all(self.artifact["component_manifest"][name]["status"] == "PRESENT" for name in OPTIONAL))
        self.assertEqual(self.artifact["component_manifest"]["historical"]["source_as_of"], "2026-08-24")
        self.assertEqual(self.artifact["component_manifest"]["valuation"]["source_as_of"], "2026-08-21")
        self.assertNotEqual(self.artifact["component_manifest"]["historical"]["source_as_of"], self.artifact["component_manifest"]["valuation"]["source_as_of"])
        for ticker, row in self.artifact["records"].items():
            source = self.inputs["opportunity"]["records"][ticker]
            ctx = row["current_decision_context"]
            self.assertEqual(ctx["priority_tier"], source["priority_tier"])
            self.assertEqual(ctx["entry_action"], source["entry_action"])
            self.assertEqual(ctx["eligible_strategies"], source["eligible_strategies"])
            self.assertEqual(ctx["tactical_state"], source["tactical_state"])
            self.assertFalse(row["is_actionable"])
        aaa = self.artifact["records"]["AAA"]
        self.assertEqual(aaa["components"]["scenario_context"]["scenario_disposition"], self.inputs["scenario"]["records"]["AAA"]["scenario_disposition"])
        self.assertEqual(aaa["components"]["risk_register"]["risk_register_status"], self.inputs["risk_register"]["records"]["AAA"]["risk_register_status"])
        self.assertEqual(aaa["components"]["valuation_context"]["metrics"]["market_cap"]["status"], self.inputs["valuation"]["records"]["AAA"]["metrics"]["market_cap"]["status"])
        self.assertEqual(self.frozen_before, self.frozen_after)
        self.assertGreaterEqual(cov["packets_with_scenario_risk_and_blocked_valuation"], 1)
        self.assertGreaterEqual(cov["packets_with_no_current_technical_coverage"], 1)

    def test_opt_in_attachment_on_retained_artifact(self) -> None:
        if self.artifact is None:
            self.skipTest("retained packet inputs incomplete")
        entries = {"AAA": {"research_priority": "keep", "entry_action": "keep", "strategy_eligibility": "keep"}}
        original = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_research_decision_packet(entries, False, "x"), original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(self.artifact), encoding="utf-8")
            out = bundle.attach_current_research_decision_packet(entries, True, str(path))
            self.assertFalse(out["AAA"]["current_research_decision_packet"]["is_actionable"])
            self.assertEqual(out["AAA"]["entry_action"], "keep")


if __name__ == "__main__":
    unittest.main()
