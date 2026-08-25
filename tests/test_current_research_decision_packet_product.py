"""Shadow/opt-in dashboard surfacing of current_research_decision_packet/v1."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from current_daily_decision_research_product import build as build_product, markdown as product_markdown
from current_research_decision_packet_product import (
    AUTHORITY_PRESENTATION,
    CONSERVATIVE_BASE_SPECULATIVE_LENS,
    SCENARIO_LENS,
    attach_shadow_to_daily_product,
    load_verified_packet,
    markdown,
    project_ticker,
    project_shadow_panel,
    validate_market_wide,
    verified_packet,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_current_research_decision_packet import (  # noqa: E402
    PATHS,
    _break,
    _build,
    _decision,
    _opportunity,
    _optional_artifacts,
)

OPERATIONS = ROOT / "operations-review"
PACKET_PATH = OPERATIONS / "current-research-decision-packet-v1/current_research_decision_packet_artifact.json"
PRODUCT_INPUTS = {
    "descriptive": "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
    "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
    "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
    "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
    "scenario": "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
    "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
}


def _product_inputs():
    return {name: json.loads((OPERATIONS / path).read_text(encoding="utf-8")) for name, path in PRODUCT_INPUTS.items()}


class ShadowGatingTests(unittest.TestCase):
    def test_disabled_attach_leaves_bundle_byte_identical(self) -> None:
        entries = {"AAA": {"research_priority": "keep", "entry_action": "WAIT", "strategy_eligibility": "keep"}}
        original = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_research_decision_packet(entries, False, "missing.json"), original)
        self.assertEqual(entries, original)

    def test_malformed_and_missing_packet_fail_closed(self) -> None:
        entries = {"AAA": {"entry_action": "keep"}}
        original = copy.deepcopy(entries)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path)), original)
            path.write_text(json.dumps({"contract_version": "current_research_decision_packet/v1", "artifact_sha256": "nope", "records": {}}), encoding="utf-8")
            self.assertEqual(bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path)), original)
            self.assertIsNone(load_verified_packet(path))
            self.assertIsNone(verified_packet({"contract_version": "nope"}))
            self.assertIsNone(project_shadow_panel({"contract_version": "nope"}))

    def test_daily_product_default_identity_unchanged_without_packet(self) -> None:
        if not all((OPERATIONS / path).is_file() for path in PRODUCT_INPUTS.values()):
            self.skipTest("retained daily product inputs unavailable")
        inputs = _product_inputs()
        baseline = build_product(**inputs)
        again = build_product(**inputs, current_research_decision_packet=None)
        self.assertEqual(baseline["artifact_sha256"], again["artifact_sha256"])
        self.assertNotIn("current_research_decision_packet_shadow", baseline)
        self.assertTrue(all("current_research_decision_packet" not in card for card in baseline["detailed_research_cards"].values()))
        malformed = attach_shadow_to_daily_product(copy.deepcopy(baseline), {"contract_version": "current_research_decision_packet/v1"})
        self.assertEqual(malformed["artifact_sha256"], baseline["artifact_sha256"])
        self.assertNotIn("current_research_decision_packet_shadow", malformed)


class RepresentativePacketSurfaceTests(unittest.TestCase):
    def test_valid_full_packet_organizes_facts_without_reinterpretation(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        self.assertEqual(view["ticker"], "AAA")
        self.assertEqual(view["shadow_mode"], "SHADOW_OPT_IN")
        self.assertFalse(view["is_actionable"])
        self.assertEqual(view["packet_status"], "COMPLETE_FOR_AVAILABLE_COMPONENTS")
        self.assertTrue(view["ticker_usable"])
        self.assertEqual(view["current_decision_context"]["entry_action"], "WAIT")
        self.assertEqual(view["current_decision_context"]["priority_tier"], "MONITOR")
        self.assertEqual(view["scenario_research_context"]["research_lens"]["id"], "EVIDENCE_BOUND_BEAR_BASE_BULL")
        self.assertEqual(view["scenario_research_context"]["scenario_disposition"], "SCENARIO_READY")
        self.assertEqual(view["provenance"]["packet_identity"], artifact["artifact_identity"])
        self.assertEqual(set(view["authority_presentation"]), set(AUTHORITY_PRESENTATION))

    def test_technical_coverage_gap_is_local(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        types = [item["risk_type"] for item in view["risk_register"]["data_authority_limitations"]]
        self.assertIn("EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE", types)
        self.assertEqual(view["current_decision_context"]["entry_action"], "WAIT")
        self.assertTrue(view["ticker_usable"])

    def test_blocked_valuation_is_not_authoritative_ready(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        self.assertIn("P/B", view["valuation_context"]["blocked_metrics"])
        self.assertIn("P/E", view["valuation_context"]["research_usable_metrics"])
        self.assertTrue(view["valuation_context"]["research_usable_is_not_authoritative_ready"])
        self.assertNotEqual(view["valuation_context"]["metric_statuses"]["P/E"], "READY")

    def test_material_risk_is_listed_not_scored(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        self.assertEqual(view["risk_register"]["risk_register_status"], "MATERIAL_RISKS_ESTABLISHED")
        self.assertEqual([item["risk_type"] for item in view["risk_register"]["material_risks"]], ["FINANCIAL_STRESS"])
        self.assertNotIn("risk_score", view["risk_register"])
        self.assertTrue(view["risk_register"]["no_material_risk_established_is_not_low_risk"])

    def test_no_material_risk_established_is_not_low_risk(self) -> None:
        opt = _optional_artifacts()
        opt["risk_register"]["records"]["AAA"]["material_risks"] = []
        opt["risk_register"]["records"]["AAA"]["risk_register_status"] = "NO_MATERIAL_RISK_ESTABLISHED_FROM_AVAILABLE_EVIDENCE"
        from current_research_risk_register import content_identity as risk_identity
        signed = copy.deepcopy(opt["risk_register"])
        signed.pop("artifact_sha256", None); signed.pop("artifact_identity", None)
        signed.update(risk_identity(signed))
        artifact = _build(risk_register=signed)
        view = project_ticker(artifact["records"]["AAA"], artifact)
        self.assertEqual(view["risk_register"]["risk_register_status"], "NO_MATERIAL_RISK_ESTABLISHED_FROM_AVAILABLE_EVIDENCE")
        self.assertTrue(view["risk_register"]["absence_is_not_low_risk"])
        self.assertNotEqual(view["risk_register"]["risk_register_status"], "LOW_RISK")
        self.assertTrue(view["ticker_usable"])

    def test_financial_data_insufficient_stays_local(self) -> None:
        opt = _optional_artifacts()
        opt["financial_momentum"]["records"]["AAA"]["coverage_status"] = "INSUFFICIENT"
        opt["financial_momentum"]["records"]["AAA"]["financial_momentum_state"] = "INSUFFICIENT_COMPARABLE_DATA"
        from current_financial_momentum_context import content_identity as financial_identity
        signed = copy.deepcopy(opt["financial_momentum"])
        signed.pop("artifact_sha256", None); signed.pop("artifact_identity", None)
        signed.update(financial_identity(signed))
        artifact = _build(financial_momentum=signed)
        view = project_ticker(artifact["records"]["AAA"], artifact)
        self.assertEqual(view["financial_momentum_context"]["payload"]["coverage_status"], "INSUFFICIENT")
        self.assertEqual(view["current_decision_context"]["entry_action"], "WAIT")
        self.assertTrue(view["ticker_usable"])

    def test_planned_corporate_event_is_not_executed_and_record_date_is_not_ex_date(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        events = view["corporate_event_context"]["events"]
        planned = next(event for event in events if event["event_status"] == "PLANNED_NOT_EXECUTED")
        self.assertIsNone(planned["execution_date"])
        self.assertNotEqual(planned["record_date"], planned["ex_date"])
        self.assertTrue(view["corporate_event_context"]["planned_or_approved_is_not_executed"])
        self.assertTrue(view["corporate_event_context"]["record_date_is_not_ex_date"])
        executed = next(event for event in events if event["event_status"] == "EXECUTED")
        self.assertEqual(executed["execution_date"], "2022-03-20")

    def test_historical_adjusted_retrospective_is_not_raw_or_pit(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        hist = view["historical_research_context"]
        self.assertEqual(hist["price_basis"], "ADJUSTED_RETROSPECTIVE")
        self.assertEqual(hist["raw_as_traded"], "NOT_PROMOTED")
        self.assertEqual(hist["pit"], "BLOCKED")
        self.assertTrue(hist["adjusted_retrospective_is_not_raw_as_traded"])
        self.assertTrue(hist["retrospective_history_is_not_pit"])

    def test_absent_and_malformed_optional_component_remain_local(self) -> None:
        absent = _build(scenario=None)
        view = project_ticker(absent["records"]["AAA"], absent)
        self.assertEqual(view["packet_status"], "PARTIAL")
        self.assertEqual(view["scenario_research_context"]["status"], "ABSENT_OR_UNRESOLVED")
        self.assertIn("scenario", view["unresolved_components"])
        self.assertEqual(view["risk_register"]["status"], "PRESENT")
        self.assertTrue(view["ticker_usable"])
        self.assertEqual(view["current_decision_context"]["entry_action"], "WAIT")
        malformed = _build(valuation=_break(_optional_artifacts()["valuation"]))
        broken = project_ticker(malformed["records"]["AAA"], malformed)
        self.assertEqual(broken["valuation_context"]["status"], "ABSENT_OR_UNRESOLVED")
        self.assertEqual(broken["risk_register"]["status"], "PRESENT")
        self.assertTrue(broken["ticker_usable"])

    def test_packet_scenario_is_independent_from_conservative_base_speculative(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        lens = view["scenario_research_context"]["research_lens"]
        self.assertEqual(lens["axes"], ["BEAR", "BASE", "BULL"])
        self.assertTrue(lens["not_the_conservative_base_speculative_framework"])
        self.assertTrue(view["scenario_research_context"]["independent_from_conservative_base_speculative_framework"])
        other = view["conservative_base_speculative_lens"]
        self.assertEqual(other["id"], "CONSERVATIVE_BASE_SPECULATIVE")
        self.assertEqual(other["axes"], ["CONSERVATIVE", "BASE", "SPECULATIVE"])
        self.assertNotEqual(lens["id"], other["id"])
        dumped = json.dumps(view["scenario_research_context"])
        self.assertNotIn("CONSERVATIVE", dumped)
        self.assertNotIn("SPECULATIVE", dumped)
        self.assertEqual(view["priority_lens"]["contract"], "current_opportunity_prioritization/v1")
        self.assertTrue(view["priority_lens"]["distinct_from_daily_opportunity_decision_queue"])
        self.assertNotEqual(view["current_decision_context"]["priority_tier"], view["current_decision_context"]["entry_action"])

    def test_provenance_and_authority_limitations_are_visible_in_json_and_markdown(self) -> None:
        artifact = _build()
        view = project_ticker(artifact["records"]["AAA"], artifact)
        panel = project_shadow_panel(artifact, ["AAA"])
        text = markdown(panel)
        self.assertEqual(view["provenance"]["packet_identity"], artifact["artifact_identity"])
        self.assertEqual(view["provenance"]["current_decision_source_input_identities"], {"tactical": "t:1"})
        for item in AUTHORITY_PRESENTATION:
            self.assertIn(item, view["authority_presentation"])
        self.assertIn("Evidence-bound Bear/Base/Bull", text)
        self.assertIn("not CONSERVATIVE/BASE/SPECULATIVE", text)
        self.assertIn("NO_MATERIAL_RISK_ESTABLISHED is not LOW_RISK", text)
        self.assertIn("RESEARCH_USABLE is not authoritative READY", text)
        self.assertIn("ADJUSTED_RETROSPECTIVE is not RAW_AS_TRADED", text)
        self.assertIn("record date is not ex-date", text)
        self.assertIn("shadow / opt-in", text.lower())
        self.assertNotIn("BUY", text)
        self.assertNotIn("most likely", text.lower())


class DailyProductShadowAttachTests(unittest.TestCase):
    def test_opt_in_packet_appears_on_existing_product_cards(self) -> None:
        if not all((OPERATIONS / path).is_file() for path in PRODUCT_INPUTS.values()):
            self.skipTest("retained daily product inputs unavailable")
        if not PACKET_PATH.is_file():
            self.skipTest("retained packet unavailable")
        inputs = _product_inputs()
        baseline = build_product(**inputs)
        packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
        shadowed = build_product(**inputs, current_research_decision_packet=packet)
        self.assertNotEqual(baseline["artifact_sha256"], shadowed["artifact_sha256"])
        self.assertEqual(baseline["session"], shadowed["session"])
        self.assertEqual(baseline["watchlist"], shadowed["watchlist"])
        self.assertEqual(set(baseline["detailed_research_cards"]), set(shadowed["detailed_research_cards"]))
        self.assertEqual(shadowed["current_research_decision_packet_shadow"]["shadow_mode"], "SHADOW_OPT_IN")
        hpg = shadowed["detailed_research_cards"]["HPG"]
        packet_card = hpg["current_research_decision_packet"]
        self.assertEqual(packet_card["scenario_research_context"]["research_lens"]["id"], SCENARIO_LENS["id"])
        self.assertNotEqual(packet_card["scenario_research_context"]["research_lens"]["id"], CONSERVATIVE_BASE_SPECULATIVE_LENS["id"])
        self.assertIn("bear_case", packet_card["scenario_research_context"])
        self.assertNotIn("CONSERVATIVE", json.dumps(packet_card["scenario_research_context"]))
        self.assertTrue(packet_card["valuation_context"]["research_usable_is_not_authoritative_ready"])
        self.assertEqual(hpg["current_decision_state"]["entry_action"], baseline["detailed_research_cards"]["HPG"]["current_decision_state"]["entry_action"])
        self.assertNotEqual(packet_card["current_decision_context"]["priority_tier"], packet_card["current_decision_context"]["entry_action"])
        brief = product_markdown(shadowed)
        self.assertIn("Current research decision packet (shadow / opt-in)", brief)
        self.assertIn("Evidence-bound Bear/Base/Bull", brief)
        self.assertNotIn("Current research decision packet (shadow / opt-in)", product_markdown(baseline))

    def test_opt_in_bundle_attach_includes_product_surface(self) -> None:
        artifact = _build()
        entries = {"AAA": {"entry_action": "keep", "research_priority": "keep"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            out = bundle.attach_current_research_decision_packet(copy.deepcopy(entries), True, str(path))
        attached = out["AAA"]["current_research_decision_packet"]
        self.assertEqual(out["AAA"]["entry_action"], "keep")
        self.assertFalse(attached["is_actionable"])
        self.assertEqual(attached["shadow_mode"], "SHADOW_OPT_IN")
        self.assertEqual(attached["product_surface"]["scenario_research_context"]["research_lens"]["axes"], ["BEAR", "BASE", "BULL"])
        self.assertTrue(attached["product_surface"]["risk_register"]["no_material_risk_established_is_not_low_risk"])


class MarketWideRetainedValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = json.loads(PACKET_PATH.read_text(encoding="utf-8")) if PACKET_PATH.is_file() else None

    def test_market_wide_render_has_no_unexplained_residual(self) -> None:
        if self.packet is None:
            self.skipTest("retained packet unavailable")
        report = validate_market_wide(self.packet)
        self.assertIsNotNone(report)
        self.assertEqual(report["universe_denominator"], 1507)
        self.assertEqual(report["coverage_universe_denominator"], 1507)
        self.assertEqual(report["unexplained_ticker_residual"], 0)
        self.assertEqual(report["malformed_product_payload_count"], 0)
        self.assertEqual(report["forbidden_product_hits"], 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["complete_count"] + report["partial_packets_remain_usable"], 1507)
        self.assertGreaterEqual(report["technical_coverage_gap_count"], 1)
        self.assertGreaterEqual(report["blocked_valuation_count"], 1)
        self.assertGreaterEqual(report["no_material_risk_established_count"] + report["material_risk_count"], 1)
        self.assertGreaterEqual(report["financial_insufficient_count"], 1)
        self.assertGreaterEqual(report["adjusted_retrospective_count"], 1)
        hpg = project_ticker(self.packet["records"]["HPG"], self.packet)
        self.assertEqual(hpg["packet_status"], "COMPLETE_FOR_AVAILABLE_COMPONENTS")
        self.assertTrue(hpg["ticker_usable"])
        self.assertEqual(hpg["scenario_research_context"]["research_lens"]["id"], "EVIDENCE_BOUND_BEAR_BASE_BULL")
        self.assertIn("RESEARCH_USABLE", hpg["valuation_context"]["metric_statuses"].values())
        self.assertTrue(hpg["valuation_context"]["research_usable_is_not_authoritative_ready"])
        vcb = project_ticker(self.packet["records"]["VCB"], self.packet)
        self.assertTrue(vcb["ticker_usable"])
        statuses = {event["event_status"] for event in vcb["corporate_event_context"]["events"]}
        self.assertTrue(statuses)
        self.assertTrue(vcb["corporate_event_context"]["planned_or_approved_is_not_executed"])


if __name__ == "__main__":
    unittest.main()
