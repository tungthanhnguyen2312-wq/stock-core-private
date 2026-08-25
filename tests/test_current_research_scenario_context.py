"""Regression tests for the additive CONSERVATIVE/BASE/SPECULATIVE research scenario framework."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import current_research_risk_register as register
import current_research_scenario_context as scenario
import export_ai_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "current_official_universe": ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json",
    "tactical": ROOT / "operations-review/watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "opportunity": ROOT / "operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    "historical_context": ROOT / "operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json",
    "leadership_context": ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json",
    "financial_context": ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json",
    "corporate_event_context": ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "valuation_context": ROOT / "operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json",
}
FROZEN_IDENTITY_PATHS = [
    ROOT / "operations-review/current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
    ROOT / "operations-review/polymorphic-current-strategy-classification-v1-20260824/polymorphic_current_strategy_classification_artifact.json",
    ROOT / "operations-review/current-daily-decision-research-product-v2-20260824/current_daily_decision_research_product_artifact.json",
    ROOT / "operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    ROOT / "operations-review/watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
]
SOURCE_IDS = {name: name for name in (
    "tactical", "historical", "leadership", "financial", "event", "valuation",
)}


def _inputs() -> dict:
    return {name: json.loads(path.read_bytes().decode("utf-8")) for name, path in PATHS.items()}


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(**overrides) -> dict:
    evidence = {
        "ticker": "T",
        "classified": True,
        "entry_state": "UPTREND_CONFIRMED",
        "entry_action": "WAIT",
        "research_priority": "SETUP_WATCH",
        "eligible_strategy_lanes": ["TREND_MOMENTUM"],
        "existing_evidence_bound_scenario_disposition": "SCENARIO_READY",
        "supporting_conditions": [],
        "opposing_conditions": [],
        "confirmation_conditions": [{"status": "AVAILABLE", "reason": "REUSED", "text": "continue above MA20", "invented": False}],
        "invalidation_conditions": [{"status": "AVAILABLE", "reason": "REUSED", "text": "momentum turns negative", "invented": False}],
        "material_risks": [],
        "authority_limitations": [],
        "unresolved_questions": [],
        "current_state_evidence": True,
        "explicit_speculative_evidence": False,
        "weak_sector": False,
        "sector_state": "LEADING",
        "financial_state": "INSUFFICIENT_COMPARABLE_DATA",
        "financial_tier": "UNAVAILABLE",
        "valuation_status_counts": {"BLOCKED": 6},
        "confirmation_available": True,
        "invalidation_available": True,
        "liquidity_status": "ELIGIBLE",
    }
    evidence.update(overrides)
    return evidence


def _collect(**kwargs):
    tactical = kwargs.get("tactical") or {
        "entry_state": "SIDEWAYS_NEUTRAL", "entry_action": "WAIT",
        "confirmation_trigger": "quoted confirmation", "invalidation": "quoted invalidation",
        "data_quality": {"technical_eligible": True, "liquidity_status": "ELIGIBLE"},
        "position_sizing_status": "NOT_EVALUATED",
    }
    opportunity = kwargs.get("opportunity") or {
        "entry_action": "WAIT", "priority_tier": "MONITOR", "eligible_strategies": [],
        "scenario_status": "SCENARIO_PARTIAL",
    }
    return scenario.collect_evidence(
        ticker=kwargs.get("ticker", "T"),
        tactical=tactical,
        opportunity=opportunity,
        historical=kwargs.get("historical") or {},
        leadership=kwargs.get("leadership") or {"sector_leadership_context": {"status": "UNAVAILABLE", "reason": "SECTOR_IDENTITY_UNKNOWN"}, "sector_relative_momentum": {}},
        market=kwargs.get("market") or {"current_breadth_state": "MIXED_BREADTH"},
        financial=kwargs.get("financial") or {"financial_momentum_state": "INSUFFICIENT_COMPARABLE_DATA", "evidence_tier": "UNAVAILABLE", "price_momentum_context": {}},
        event=kwargs.get("event") or {},
        valuation=kwargs.get("valuation") or {"metrics": {"P/E": {"status": "BLOCKED"}, "P/B": {"status": "BLOCKED"}}},
        risk_row=kwargs.get("risk_row") or {"material_risks": [], "data_authority_limitations": [], "unresolved_conflicts": []},
        source_ids=SOURCE_IDS,
    )


class ScenarioRuleTests(unittest.TestCase):
    def test_axes_are_orthogonal_to_strategy_lanes(self) -> None:
        self.assertEqual(scenario.SCENARIO_AXES, ("CONSERVATIVE", "BASE", "SPECULATIVE"))
        for lane in scenario.STRATEGY_LANES:
            self.assertNotIn(lane, scenario.SCENARIO_AXES)
        status, rule, _ = scenario.conservative_status(_evidence(eligible_strategy_lanes=["EARLY_REVERSAL"]))
        self.assertEqual(status, "SUPPORTED")
        self.assertNotEqual(rule, "EARLY_REVERSAL")

    def test_base_is_not_probability_or_most_likely(self) -> None:
        status, rule, reasons = scenario.base_status(_evidence())
        self.assertEqual(status, "SUPPORTED")
        self.assertIn("BASE_IS_CURRENT_STATE_INTERPRETATION_NOT_MOST_LIKELY", reasons)
        self.assertNotIn("MOST_LIKELY", rule)
        self.assertNotIn("probability", rule.lower())

    def test_speculative_does_not_lower_evidence_authority(self) -> None:
        evidence = _collect(tactical={
            "entry_state": None, "entry_action": "WAIT", "confirmation_trigger": "Await features",
            "invalidation": None, "data_quality": {"technical_eligible": False, "liquidity_status": "UNAVAILABLE"},
        }, event={"planned_unresolved_count": 1, "executed_count": 0},
           financial={"financial_momentum_state": "INSUFFICIENT_COMPARABLE_DATA", "evidence_tier": "PROVIDER_RESEARCH", "price_momentum_context": {}})
        status, _, reasons = scenario.speculative_status(evidence)
        self.assertEqual(status, "SUPPORTED")
        self.assertIn("SPECULATIVE_DOES_NOT_LOWER_EVIDENCE_AUTHORITY", reasons)
        self.assertEqual(evidence["confirmation_conditions"][0]["status"], "UNAVAILABLE")
        self.assertEqual(evidence["invalidation_conditions"][0]["status"], "UNAVAILABLE")
        self.assertEqual(evidence["financial_tier"], "PROVIDER_RESEARCH")
        self.assertFalse(any(item.get("invented") for item in evidence["confirmation_conditions"]))

    def test_conservative_requires_stronger_confirmation(self) -> None:
        supported, _, _ = scenario.conservative_status(_evidence())
        self.assertEqual(supported, "SUPPORTED")
        early, rule, _ = scenario.conservative_status(_evidence(
            entry_state="EARLY_REVERSAL_CANDIDATE", explicit_speculative_evidence=True,
        ))
        self.assertEqual(early, "NOT_SUPPORTED")
        self.assertEqual(rule, "CONSERVATIVE_CONFIRMATION_BAR_NOT_MET")
        breakout, _, _ = scenario.conservative_status(_evidence(entry_state="BREAKOUT_READY"))
        self.assertEqual(breakout, "CONDITIONALLY_SUPPORTED")

    def test_value_blocked_does_not_globally_block_other_axes(self) -> None:
        evidence = _collect(valuation={"metrics": {"P/E": {"status": "BLOCKED"}, "market_cap": {"status": "BLOCKED"}}})
        self.assertEqual(scenario.base_status(evidence)[0], "SUPPORTED")
        self.assertTrue(any(
            item["code"] == "VALUATION_BLOCKED_OR_NOT_READY_DOES_NOT_BLOCK_OTHER_AXES"
            for item in evidence["authority_limitations"]
        ))

    def test_data_limitation_is_not_automatically_bearish_risk(self) -> None:
        evidence = _collect(tactical={
            "entry_state": None, "entry_action": "WAIT", "confirmation_trigger": "Await features",
            "invalidation": None, "data_quality": {"technical_eligible": False, "liquidity_status": "UNAVAILABLE"},
        })
        self.assertEqual(scenario.base_status(evidence)[0], "DATA_LIMITED")
        self.assertFalse(evidence["material_risks"])
        self.assertTrue(any(item["polarity"] == "LIMITATION" for item in evidence["authority_limitations"]))
        self.assertFalse(any(item["polarity"] == "OPPOSE" and item["domain"] == "DATA_AUTHORITY" for item in evidence["opposing_conditions"]))

    def test_material_risk_rule_is_transparent(self) -> None:
        with_risk = _evidence(material_risks=[{"risk_type": "FINANCIAL_STRESS"}])
        self.assertEqual(scenario.conservative_status(with_risk)[0], "CONDITIONALLY_SUPPORTED")
        self.assertEqual(scenario.conservative_status(with_risk)[1], scenario.MATERIAL_RISK_BLOCKS_CONSERVATIVE_SUPPORTED)
        self.assertEqual(scenario.base_status(with_risk)[0], "SUPPORTED")
        self.assertEqual(scenario.speculative_status(_evidence(
            explicit_speculative_evidence=True, material_risks=[{"risk_type": "FINANCIAL_STRESS"}],
        ))[0], "SUPPORTED")

    def test_market_sector_evidence_cannot_alter_action(self) -> None:
        evidence = _collect(
            opportunity={"entry_action": "WAIT", "priority_tier": "PRIORITY_NOW", "eligible_strategies": ["TREND_MOMENTUM"]},
            leadership={"sector_leadership_context": {"status": "AVAILABLE", "leadership_state": "LAGGING"},
                        "sector_relative_momentum": {"momentum_bucket": "LOWER_QUARTILE"}},
        )
        self.assertEqual(evidence["entry_action"], "WAIT")
        self.assertEqual(evidence["research_priority"], "PRIORITY_NOW")
        self.assertTrue(evidence["weak_sector"])

    def test_financial_evidence_tier_is_preserved(self) -> None:
        evidence = _collect(financial={
            "financial_momentum_state": "EARNINGS_IMPROVING", "evidence_tier": "PROVIDER_RESEARCH",
            "state_rule": "PROVIDER_EARNINGS", "coverage_status": "PARTIAL",
            "price_momentum_context": {"contrast": "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM"},
        })
        self.assertEqual(evidence["financial_tier"], "PROVIDER_RESEARCH")
        self.assertTrue(any(item["facts"].get("provider_research_is_not_official") for item in evidence["supporting_conditions"] if item["domain"] == "FINANCIAL"))

    def test_planned_event_does_not_become_executed(self) -> None:
        evidence = _collect(event={"planned_unresolved_count": 1, "executed_count": 0, "confirmed_upcoming_count": 0})
        planned = [item for item in evidence["supporting_conditions"] if item["code"] == "PLANNED_NOT_EXECUTED_PRESERVED"]
        self.assertEqual(len(planned), 1)
        self.assertTrue(planned[0]["facts"]["planned_is_not_executed"])
        self.assertEqual(planned[0]["facts"]["executed_count"], 0)
        self.assertTrue(evidence["explicit_speculative_evidence"])

    def test_historical_context_does_not_create_backtest_probability(self) -> None:
        evidence = _collect(historical={
            "is_current_session": True, "context_status": "AVAILABLE",
            "structural_state": {"value": "EARLY_REVERSAL"},
            "technical_state_frequency": {"rarity_bucket": "RARE", "probability_claim": "NONE"},
            "volatility_regime": {"regime": "HIGH"}, "momentum": {"sign": "POSITIVE"},
        })
        hist = [item for item in evidence["supporting_conditions"] if item["domain"] == "HISTORICAL"]
        self.assertTrue(hist)
        self.assertTrue(all(item["facts"].get("probability_claim", "NONE") == "NONE" or "probability_claim" not in item["facts"] or item["code"] == "HISTORICAL_EARLY_REVERSAL_NOT_BACKTEST_PROBABILITY" for item in hist))
        self.assertTrue(any(item["code"] == "HISTORICAL_EARLY_REVERSAL_NOT_BACKTEST_PROBABILITY" for item in hist))

    def test_confirmation_and_invalidation_unavailable_remain_unavailable(self) -> None:
        evidence = _collect(tactical={
            "entry_state": None, "entry_action": "WAIT", "confirmation_trigger": "Await same-session technical-feature availability before any tactical classification.",
            "invalidation": None, "data_quality": {"technical_eligible": False, "liquidity_status": "UNAVAILABLE"},
        })
        self.assertEqual(evidence["confirmation_conditions"][0]["status"], "UNAVAILABLE")
        self.assertEqual(evidence["invalidation_conditions"][0]["status"], "UNAVAILABLE")
        self.assertIsNone(evidence["confirmation_conditions"][0]["text"])
        self.assertFalse(evidence["confirmation_conditions"][0]["invented"])
        self.assertFalse(evidence["invalidation_conditions"][0]["invented"])


class CurrentScenarioArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_before = {str(path): _file_digest(path) for path in FROZEN_IDENTITY_PATHS if path.exists()}
        cls.inputs = _inputs()
        cls.risk = register.build_artifact(
            current_official_universe=cls.inputs["current_official_universe"],
            historical_context=cls.inputs["historical_context"],
            leadership_context=cls.inputs["leadership_context"],
            financial_context=cls.inputs["financial_context"],
            corporate_event_context=cls.inputs["corporate_event_context"],
            valuation_context=cls.inputs["valuation_context"],
        )
        cls.artifact = scenario.build_artifact(risk_register=cls.risk, **cls.inputs)
        cls.frozen_after = {str(path): _file_digest(path) for path in FROZEN_IDENTITY_PATHS if path.exists()}

    def test_deterministic_replay_and_content_identity(self) -> None:
        before = copy.deepcopy(self.inputs)
        rebuilt = scenario.build_artifact(risk_register=self.risk, **self.inputs)
        self.assertEqual(self.artifact["artifact_identity"], rebuilt["artifact_identity"])
        self.assertEqual(self.inputs, before)
        scenario.replay(self.artifact)
        self.assertEqual(self.artifact["official_universe_denominator"], 1507)
        self.assertEqual(self.artifact["coverage"]["ticker_coverage"], 1507)
        self.assertEqual(self.artifact["coverage"]["scenario_record_count"], 4521)

    def test_cannot_alter_priority_strategy_or_entry_action(self) -> None:
        for ticker, record in self.artifact["records"].items():
            opportunity = self.inputs["opportunity"]["records"][ticker]
            context = record["current_decision_context"]
            self.assertEqual(context["research_priority"], opportunity.get("priority_tier"))
            self.assertEqual(context["entry_action"], opportunity.get("entry_action"))
            self.assertEqual(list(context["eligible_strategy_lanes"]), list(opportunity.get("eligible_strategies") or []))
            self.assertTrue(context["quoted_not_modified"])
            for axis in scenario.SCENARIO_AXES:
                self.assertTrue(record["axes"][axis]["does_not_modify_research_priority"])
                self.assertTrue(record["axes"][axis]["does_not_modify_strategy_eligibility"])
                self.assertTrue(record["axes"][axis]["does_not_modify_entry_action"])
        self.assertTrue(self.artifact["authority_boundary"]["does_not_modify_daily_decision_queue"])

    def test_no_target_expected_return_probability_or_sizing(self) -> None:
        boundary = self.artifact["authority_boundary"]
        self.assertTrue(boundary["no_probability"])
        self.assertTrue(boundary["no_expected_return"])
        self.assertTrue(boundary["no_target_price"])
        self.assertTrue(boundary["no_sizing"])
        for key in ("probability", "expected_return", "target_price", "position_size", "sizing"):
            self.assertEqual(self.artifact["blocked_outputs"][key], "NOT_EMITTED_OR_MODIFIED")
        for record in self.artifact["records"].values():
            for axis in record["axes"].values():
                self.assertNotIn("probability", axis)
                self.assertNotIn("expected_return", axis)
                self.assertNotIn("target_price", axis)
                self.assertNotIn("position_size", axis)

    def test_frozen_identities_unchanged(self) -> None:
        self.assertEqual(self.frozen_before, self.frozen_after)
        self.assertTrue(self.artifact["orthogonality"]["existing_bear_base_bull_overlay_is_not_replaced"])
        self.assertTrue(self.artifact["authority_boundary"]["does_not_replace_evidence_bound_bear_base_bull"])

    def test_representative_real_cases(self) -> None:
        cases = self.artifact["validation"]["representative_cases"]
        records = self.artifact["records"]
        self.assertEqual(records["AAM"]["axes"]["CONSERVATIVE"]["scenario_status"], "SUPPORTED")
        self.assertEqual(records["AAM"]["axes"]["BASE"]["scenario_status"], "SUPPORTED")
        self.assertEqual(records["HPG"]["axes"]["SPECULATIVE"]["scenario_status"], "SUPPORTED")
        self.assertEqual(records["ACE"]["axes"]["BASE"]["scenario_status"], "SUPPORTED")
        self.assertEqual(records["ACE"]["current_decision_context"]["entry_action"], "WAIT")
        self.assertEqual(records["ACE"]["current_decision_context"]["research_priority"], "PRIORITY_NOW")
        self.assertEqual(records["ABB"]["axes"]["SPECULATIVE"]["scenario_status"], "SUPPORTED")
        self.assertTrue(records["ABB"]["axes"]["SPECULATIVE"]["material_risks"])
        self.assertEqual(records["ABB"]["current_decision_context"]["entry_action"], "EARLY_ENTRY")
        self.assertEqual(records["ABB"]["axes"]["CONSERVATIVE"]["scenario_status"], "NOT_SUPPORTED")
        self.assertEqual(records["GIC"]["current_decision_context"]["entry_state"], "UPTREND_CONFIRMED")
        self.assertTrue(any(item["condition_id"] in {"SECTOR_NOT_LEADING", "SECTOR_RELATIVE_WEAK"} for item in records["GIC"]["axes"]["BASE"]["opposing_conditions"]))
        self.assertTrue(any(item["code"] == "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM" for item in records["HPG"]["axes"]["BASE"]["supporting_conditions"]))
        self.assertEqual(records["HPG"]["axes"]["BASE"]["current_decision_context"]["entry_action"], "WAIT")
        self.assertTrue(any(item["code"] == "PLANNED_NOT_EXECUTED_PRESERVED" for item in records["VCB"]["axes"]["SPECULATIVE"]["supporting_conditions"]))
        self.assertFalse(any(item["facts"].get("planned_is_not_executed") is False for item in records["VCB"]["axes"]["SPECULATIVE"]["supporting_conditions"]))
        self.assertIn("VALUE", records["AAA"]["axes"]["BASE"]["prohibited_uses"])
        self.assertNotIn("VALUE", records["AAA"]["current_decision_context"]["eligible_strategy_lanes"])
        self.assertIn(records["AAA"]["axes"]["BASE"]["scenario_status"], {"SUPPORTED", "CONDITIONALLY_SUPPORTED"})
        self.assertEqual(records["ANI"]["axes"]["BASE"]["scenario_status"], "DATA_LIMITED")
        self.assertEqual(records["ANI"]["axes"]["CONSERVATIVE"]["scenario_status"], "DATA_LIMITED")
        self.assertTrue(cases["conservative_supported"]["present"])
        self.assertTrue(cases["base_supported_while_wait"]["present"])
        self.assertTrue(cases["planned_event_not_executed"]["present"])
        self.assertTrue(cases["data_limited"]["present"])

    def test_opt_in_bundle_attachment_verifies_and_preserves_decisions(self) -> None:
        entries = {"AAA": {"strategy_eligibility": "keep", "research_priority": "keep", "entry_action": "keep"}}
        original = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_research_scenario_context(entries, False, "not-read.json"), original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text(json.dumps(self.artifact), encoding="utf-8")
            result = bundle.attach_current_research_scenario_context(entries, True, str(path))
            self.assertFalse(result["AAA"]["current_research_scenario_context"]["is_actionable"])
            self.assertEqual(result["AAA"]["strategy_eligibility"], "keep")
            self.assertEqual(result["AAA"]["research_priority"], "keep")
            self.assertEqual(result["AAA"]["entry_action"], "keep")
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["coverage"]["ticker_coverage"] += 1
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn(
                "current_research_scenario_context",
                bundle.attach_current_research_scenario_context({"AAA": {}}, True, str(path))["AAA"],
            )


if __name__ == "__main__":
    unittest.main()
