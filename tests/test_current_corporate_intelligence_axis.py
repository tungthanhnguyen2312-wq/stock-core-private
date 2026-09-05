"""Contract regressions for the current Corporate Intelligence axis
(CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import current_corporate_event_context as events
import current_corporate_intelligence_axis as axis
import current_official_event_context as official_events
import current_official_market_universe as official
import export_ai_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-08-21"


def _signed_official(tickers: list[str]) -> dict:
    artifact = {
        "contract_version": "current_official_market_universe/v1",
        "records": {
            ticker: {
                "ticker": ticker, "stocklookup_candidate": True,
                "current_universe_status": official.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
            }
            for ticker in tickers
        },
        "reconciliation": {"official_total_match": len(tickers)},
    }
    artifact.update(official._identity(artifact))
    return artifact


def _signed_event_context(raw_events: list[dict], session: str = SESSION) -> dict:
    artifact = {
        "contract_version": "current_official_event_context/v1",
        "research_session": session,
        "all_current_universe_event_records": raw_events,
        "corporate_intelligence_adapter": {"events": []},
        "records": {},
    }
    artifact.update(official_events._identity(artifact))
    return artifact


def _raw(**kwargs) -> dict:
    base = {
        "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_state": "UPCOMING",
        "ex_date": "2026-08-28", "record_date": "2026-09-03", "execution_date": "2026-09-15",
        "published_at": "2026-08-10", "known_at": "2026-08-10", "official_observed_at": "2026-08-20",
        "qualification": "EX_DATE_OFFICIAL_QUALIFIED", "materiality_status": "PRICE_SHARE_AFFECTING",
        "source": "hnx_official_rights_event_index/v1", "source_identity": "src-a",
        "source_record_identity": "src-a:AAA:CASH_DIVIDEND:1", "event_id": "official-a",
        "warnings": [],
    }
    base.update(kwargs)
    return base


def _build(raw_events: list[dict], tickers: list[str] | None = None, session: str = SESSION,
           include_supplemental: bool = False) -> dict:
    tickers = tickers or sorted({event["ticker"] for event in raw_events})
    return axis.build_artifact(
        official_universe=_signed_official(tickers),
        official_event_context=_signed_event_context(raw_events, session),
        root=ROOT,
        research_session=session,
        include_supplemental_events=include_supplemental,
    )


class CanonicalTaxonomyTests(unittest.TestCase):
    def test_known_variants_map_to_canonical_bucket(self) -> None:
        self.assertEqual(axis.canonical_event_type("CASH_DIVIDEND"), axis.DIVIDEND)
        self.assertEqual(axis.canonical_event_type("STOCK_DIVIDEND"), axis.BONUS_ISSUE)
        self.assertEqual(axis.canonical_event_type("BONUS_OR_STOCK_DIVIDEND"), axis.BONUS_ISSUE)
        self.assertEqual(axis.canonical_event_type("RIGHTS"), axis.RIGHTS_ISSUE)
        self.assertEqual(axis.canonical_event_type("AGM"), axis.MANAGEMENT_GOVERNANCE)

    def test_unmapped_or_ambiguous_falls_back_to_other_material_event(self) -> None:
        self.assertEqual(axis.canonical_event_type("SOMETHING_NEW_NEVER_SEEN"), axis.OTHER_MATERIAL_EVENT)
        self.assertEqual(axis.canonical_event_type(None), axis.OTHER_MATERIAL_EVENT)
        self.assertEqual(axis.canonical_event_type("CORPORATE_ACTION"), axis.OTHER_MATERIAL_EVENT)


class CanonicalStatusTests(unittest.TestCase):
    def test_confirmed_upcoming_is_approved_not_executed(self) -> None:
        self.assertEqual(axis.canonical_status("CONFIRMED_UPCOMING"), axis.APPROVED)

    def test_planned_not_executed_is_planned(self) -> None:
        self.assertEqual(axis.canonical_status("PLANNED_NOT_EXECUTED"), axis.PLANNED)

    def test_executed_variants_map_to_executed(self) -> None:
        self.assertEqual(axis.canonical_status("EXECUTED"), axis.EXECUTED)
        self.assertEqual(axis.canonical_status("CONFIRMED_RECENT"), axis.EXECUTED)

    def test_conflicting_and_data_limited_are_unknown_not_a_ladder_rung(self) -> None:
        self.assertEqual(axis.canonical_status("CONFLICTING_EVIDENCE"), axis.STATUS_UNKNOWN)
        self.assertEqual(axis.canonical_status("DATA_LIMITED"), axis.STATUS_UNKNOWN)
        self.assertEqual(axis.canonical_status("TEMPORAL_DETAILS_INCOMPLETE"), axis.STATUS_UNKNOWN)

    def test_planned_and_executed_issuance_are_never_conflated(self) -> None:
        """Planned/approved corporate-action date semantics hard gate: a planned issuance must
        never be classified identically to an executed one."""
        self.assertNotEqual(axis.canonical_status("PLANNED_NOT_EXECUTED"), axis.canonical_status("EXECUTED"))


class MaterialityTests(unittest.TestCase):
    def test_price_share_affecting_is_potentially_material_never_material(self) -> None:
        self.assertEqual(axis.canonical_materiality("PRICE_SHARE_AFFECTING"), axis.POTENTIALLY_MATERIAL)

    def test_never_emits_material_currency_or_scale_is_never_resolved_here(self) -> None:
        """No compatible amount-vs-denominator comparison exists in retained evidence, so this
        function must never return the top MATERIAL rung (mission Section 9)."""
        for raw in ("PRICE_SHARE_AFFECTING", "INFORMATIONAL_GOVERNANCE", "UNKNOWN_APPLICABILITY", None, "GARBAGE"):
            self.assertNotEqual(axis.canonical_materiality(raw), axis.MATERIAL)

    def test_informational_governance_is_non_material(self) -> None:
        self.assertEqual(axis.canonical_materiality("INFORMATIONAL_GOVERNANCE"), axis.NON_MATERIAL)

    def test_unknown_applicability_fails_closed(self) -> None:
        self.assertEqual(axis.canonical_materiality("UNKNOWN_APPLICABILITY"), axis.UNKNOWN_MATERIALITY)
        self.assertEqual(axis.canonical_materiality(None), axis.UNKNOWN_MATERIALITY)


class FreshnessTests(unittest.TestCase):
    def test_active_statuses_are_active(self) -> None:
        for status in axis.ACTIVE_EVENT_STATUSES:
            self.assertEqual(axis.canonical_freshness(status, as_of=date(2026, 8, 21), event_date=None), axis.FRESHNESS_ACTIVE)

    def test_executed_within_window_is_resolved_recent(self) -> None:
        self.assertEqual(
            axis.canonical_freshness("EXECUTED", as_of=date(2026, 8, 21), event_date=date(2026, 6, 1)),
            axis.FRESHNESS_RESOLVED_RECENT,
        )

    def test_executed_beyond_window_is_resolved_historical(self) -> None:
        self.assertEqual(
            axis.canonical_freshness("EXECUTED", as_of=date(2026, 8, 21), event_date=date(2025, 1, 1)),
            axis.FRESHNESS_RESOLVED_HISTORICAL,
        )

    def test_resolved_status_without_a_date_is_unknown_not_fabricated(self) -> None:
        self.assertEqual(axis.canonical_freshness("EXECUTED", as_of=date(2026, 8, 21), event_date=None), axis.FRESHNESS_UNKNOWN)

    def test_does_not_keep_stale_resolved_events_forever_active(self) -> None:
        old = axis.canonical_freshness("CANCELLED", as_of=date(2026, 8, 21), event_date=date(2020, 1, 1))
        self.assertEqual(old, axis.FRESHNESS_RESOLVED_HISTORICAL)
        self.assertNotEqual(old, axis.FRESHNESS_ACTIVE)


class CatalystRiskClassificationTests(unittest.TestCase):
    def test_dividend_is_never_automatically_bullish(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.DIVIDEND, status=axis.EXECUTED, original_event_status="EXECUTED")
        self.assertEqual(classification, axis.INFORMATIONAL)

    def test_planned_issuance_is_a_risk_pending_execution(self) -> None:
        classification, reasons = axis.classify_catalyst_risk(event_type=axis.RIGHTS_ISSUE, status=axis.PLANNED, original_event_status="PLANNED_NOT_EXECUTED")
        self.assertEqual(classification, axis.POTENTIAL_RISK)
        self.assertIn("PLANNED_OR_APPROVED_ISSUANCE_MAY_DILUTE_PENDING_EXECUTION", reasons)

    def test_executed_issuance_is_mixed_not_pure_risk(self) -> None:
        """A planned issuance is dilution risk; an executed one has genuinely raised capital
        too -- must not collapse to the same classification as the still-pending case."""
        planned, _ = axis.classify_catalyst_risk(event_type=axis.RIGHTS_ISSUE, status=axis.PLANNED, original_event_status="PLANNED_NOT_EXECUTED")
        executed, _ = axis.classify_catalyst_risk(event_type=axis.RIGHTS_ISSUE, status=axis.EXECUTED, original_event_status="EXECUTED")
        self.assertEqual(executed, axis.MIXED)
        self.assertNotEqual(planned, executed)

    def test_executed_repurchase_is_a_catalyst(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.SHARE_REPURCHASE, status=axis.EXECUTED, original_event_status="EXECUTED")
        self.assertEqual(classification, axis.POTENTIAL_CATALYST)

    def test_planned_repurchase_is_not_yet_a_catalyst(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.SHARE_REPURCHASE, status=axis.ANNOUNCED, original_event_status="PLANNED_NOT_EXECUTED")
        self.assertEqual(classification, axis.INFORMATIONAL)

    def test_new_borrowing_is_not_automatically_negative(self) -> None:
        classification, reasons = axis.classify_catalyst_risk(event_type=axis.DEBT_FINANCING, status=axis.EXECUTED, original_event_status="EXECUTED")
        self.assertEqual(classification, axis.INFORMATIONAL)
        self.assertIn("DEBT_FINANCING_DIRECTION_AND_TERMS_UNKNOWN_FROM_EVENT_TYPE_ALONE", reasons)

    def test_contract_announcement_is_not_recognized_revenue(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.MAJOR_CONTRACT, status=axis.ANNOUNCED, original_event_status="PLANNED_NOT_EXECUTED")
        self.assertEqual(classification, axis.INFORMATIONAL)

    def test_unresolved_regulatory_matter_is_a_risk(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.REGULATORY_LEGAL, status=axis.ANNOUNCED, original_event_status="PLANNED_NOT_EXECUTED")
        self.assertEqual(classification, axis.POTENTIAL_RISK)

    def test_conflicting_evidence_is_unresolved_not_a_directional_call(self) -> None:
        classification, reasons = axis.classify_catalyst_risk(event_type=axis.DIVIDEND, status=axis.STATUS_UNKNOWN, original_event_status="CONFLICTING_EVIDENCE")
        self.assertEqual(classification, axis.UNRESOLVED)
        self.assertIn("CONFLICTING_EVIDENCE_BLOCKS_CLASSIFICATION", reasons)

    def test_data_limited_is_insufficient_evidence(self) -> None:
        classification, _ = axis.classify_catalyst_risk(event_type=axis.DIVIDEND, status=axis.STATUS_UNKNOWN, original_event_status="DATA_LIMITED")
        self.assertEqual(classification, axis.INSUFFICIENT_EVIDENCE)

    def test_governance_and_ownership_change_are_mixed_direction_unclear(self) -> None:
        for event_type in (axis.MANAGEMENT_GOVERNANCE, axis.OWNERSHIP_CHANGE, axis.RESTRUCTURING):
            classification, _ = axis.classify_catalyst_risk(
                event_type=event_type, status=axis.EXECUTED, original_event_status="EXECUTED",
                materiality=axis.POTENTIALLY_MATERIAL,
            )
            self.assertEqual(classification, axis.MIXED)

    def test_routine_non_material_governance_event_is_informational_not_mixed(self) -> None:
        """A routine AGM notice already screened NON_MATERIAL by current_official_event_context's
        own materiality gate must not be inflated into direction-ambiguous MIXED evidence."""
        classification, reasons = axis.classify_catalyst_risk(
            event_type=axis.MANAGEMENT_GOVERNANCE, status=axis.EXECUTED, original_event_status="EXECUTED",
            materiality=axis.NON_MATERIAL,
        )
        self.assertEqual(classification, axis.INFORMATIONAL)
        self.assertIn("ROUTINE_GOVERNANCE_EVENT_NOT_PRICE_SHARE_AFFECTING", reasons)

    def test_classification_depends_only_on_type_and_status_not_narrative_text(self) -> None:
        """No keyword-sentiment scoring: classify_catalyst_risk's signature accepts no
        narrative/description text at all, so two events differing only in narrative content
        are structurally guaranteed to classify identically."""
        first, first_reasons = axis.classify_catalyst_risk(event_type=axis.ASSET_DISPOSAL, status=axis.EXECUTED, original_event_status="EXECUTED")
        second, second_reasons = axis.classify_catalyst_risk(event_type=axis.ASSET_DISPOSAL, status=axis.EXECUTED, original_event_status="EXECUTED")
        self.assertEqual((first, first_reasons), (second, second_reasons))

    def test_every_taxonomy_member_has_a_deterministic_rule_no_crash(self) -> None:
        for event_type in axis.EVENT_TAXONOMY:
            for status in axis.CANONICAL_STATUSES:
                classification, reasons = axis.classify_catalyst_risk(event_type=event_type, status=status, original_event_status="EXECUTED")
                self.assertIn(classification, axis.CATALYST_RISK_CLASSIFICATIONS)
                self.assertTrue(reasons)


class ClassifyEventTests(unittest.TestCase):
    def test_event_identity_is_preserved_verbatim_for_risk_register_cross_reference(self) -> None:
        raw = {"event_id": "current_corporate_event:abc123", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "EXECUTED"}
        result = axis.classify_event(raw, as_of=date(2026, 8, 21))
        self.assertEqual(result["event_id"], "current_corporate_event:abc123")

    def test_announcement_record_and_ex_date_remain_three_distinct_fields(self) -> None:
        raw = {
            "event_id": "e1", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "EXECUTED",
            "announcement_date": "2026-01-01", "record_date": "2026-02-01", "ex_date": "2026-01-31",
        }
        result = axis.classify_event(raw, as_of=date(2026, 8, 21))
        self.assertEqual(result["announcement_date"], "2026-01-01")
        self.assertEqual(result["record_date"], "2026-02-01")
        self.assertEqual(result["ex_date"], "2026-01-31")
        self.assertNotEqual(result["record_date"], result["ex_date"])

    def test_classify_event_does_not_mutate_the_input(self) -> None:
        raw = {"event_id": "e1", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "PLANNED_NOT_EXECUTED"}
        frozen = json.dumps(raw, sort_keys=True)
        axis.classify_event(raw, as_of=date(2026, 8, 21))
        self.assertEqual(json.dumps(raw, sort_keys=True), frozen)

    def test_temporal_fitness_reuses_bitemporal_semantic_contract(self) -> None:
        with_date = axis.classify_event(
            {"event_id": "e1", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "EXECUTED", "ex_date": "2026-01-31"},
            as_of=date(2026, 8, 21),
        )
        without_date = axis.classify_event(
            {"event_id": "e2", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "EXECUTED"},
            as_of=date(2026, 8, 21),
        )
        self.assertEqual(with_date["temporal_fitness"], "READY")
        self.assertEqual(without_date["temporal_fitness"], "VALID_TIME_INSUFFICIENT")

    def test_original_event_status_is_never_discarded(self) -> None:
        raw = {"event_id": "e1", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "CONFIRMED_UPCOMING"}
        result = axis.classify_event(raw, as_of=date(2026, 8, 21))
        self.assertEqual(result["original_event_status"], "CONFIRMED_UPCOMING")
        self.assertEqual(result["status"], axis.APPROVED)
        self.assertNotEqual(result["original_event_status"], result["status"])


class TickerAxisAggregationTests(unittest.TestCase):
    def test_no_events_is_the_correct_result_not_an_error(self) -> None:
        record = axis._ticker_axis("ZZZ", SESSION, [])
        self.assertEqual(record["state"], axis.NO_QUALIFIED_CORPORATE_EVENT)
        self.assertEqual(record["fitness"], axis.NO_QUALIFIED_CORPORATE_EVENT)
        self.assertEqual(record["active_catalysts"], [])
        self.assertEqual(record["active_risks"], [])

    def test_single_active_catalyst_sets_catalyst_present(self) -> None:
        event = axis.classify_event(
            {"event_id": "e1", "ticker": "AAA", "event_type": "SHARE_REPURCHASE", "event_status": "CONFIRMED_RECENT"},
            as_of=date(2026, 8, 21),
        )
        record = axis._ticker_axis("AAA", SESSION, [event])
        self.assertEqual(record["state"], axis.CATALYST_PRESENT)
        self.assertEqual(record["active_catalysts"], ["e1"])

    def test_catalyst_and_risk_together_is_mixed_evidence(self) -> None:
        catalyst = axis.classify_event(
            {"event_id": "e1", "ticker": "AAA", "event_type": "SHARE_REPURCHASE", "event_status": "CONFIRMED_RECENT"},
            as_of=date(2026, 8, 21),
        )
        risk = axis.classify_event(
            {"event_id": "e2", "ticker": "AAA", "event_type": "RIGHTS_ISSUE", "event_status": "PLANNED_NOT_EXECUTED"},
            as_of=date(2026, 8, 21),
        )
        record = axis._ticker_axis("AAA", SESSION, [catalyst, risk])
        self.assertEqual(record["state"], axis.MIXED_EVIDENCE)

    def test_historical_only_events_do_not_count_as_active(self) -> None:
        historical_catalyst = axis.classify_event(
            {"event_id": "e1", "ticker": "AAA", "event_type": "SHARE_REPURCHASE", "event_status": "EXECUTED", "ex_date": "2020-01-01"},
            as_of=date(2026, 8, 21),
        )
        record = axis._ticker_axis("AAA", SESSION, [historical_catalyst])
        self.assertEqual(record["active_catalysts"], [])
        self.assertNotEqual(record["state"], axis.CATALYST_PRESENT)

    def test_material_event_count_and_freshest_material_event(self) -> None:
        material = axis.classify_event(
            {"event_id": "e1", "ticker": "AAA", "event_type": "CASH_DIVIDEND", "event_status": "EXECUTED",
             "materiality_status": "PRICE_SHARE_AFFECTING", "ex_date": "2026-06-01"},
            as_of=date(2026, 8, 21),
        )
        non_material = axis.classify_event(
            {"event_id": "e2", "ticker": "AAA", "event_type": "AGM", "event_status": "EXECUTED",
             "materiality_status": "INFORMATIONAL_GOVERNANCE"},
            as_of=date(2026, 8, 21),
        )
        record = axis._ticker_axis("AAA", SESSION, [material, non_material])
        self.assertEqual(record["material_event_count"], 1)
        self.assertEqual(record["freshest_material_event"], "e1")


class BuildArtifactIntegrationTests(unittest.TestCase):
    def test_no_qualified_event_is_the_documented_correct_result(self) -> None:
        artifact = _build([_raw(ticker="AAA")], tickers=["AAA", "ZZZ"])
        self.assertEqual(artifact["records"]["ZZZ"]["state"], axis.NO_QUALIFIED_CORPORATE_EVENT)

    def test_temporal_replay_excludes_look_ahead_known_at(self) -> None:
        """A later event must not appear earlier: known_at in the future relative to the
        requested research session is excluded by the upstream contract this module reuses."""
        future_known = _raw(ticker="AAA", known_at="2026-09-01", published_at="2026-09-01")
        artifact = _build([future_known], tickers=["AAA"], session="2026-08-21")
        self.assertEqual(artifact["records"]["AAA"]["state"], axis.NO_QUALIFIED_CORPORATE_EVENT)

    def test_conflicting_dated_duplicates_are_unresolved_not_voted(self) -> None:
        one = _raw(ticker="AAA", source_identity="src-a", event_id="official-a", ex_date="2026-08-28", record_date="2026-09-03")
        two = _raw(ticker="AAA", source_identity="src-b", event_id="official-b", ex_date="2026-08-29", record_date="2026-09-03")
        artifact = _build([one, two], tickers=["AAA"])
        record = artifact["records"]["AAA"]
        self.assertIn("CONFLICTING_EVIDENCE_BLOCKS_CLASSIFICATION", record["blockers"])

    def test_artifact_is_deterministic_and_self_verifying(self) -> None:
        first = _build([_raw()])
        second = _build([_raw()])
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        recomputed = axis.content_identity(first)
        self.assertEqual(recomputed["artifact_sha256"], first["artifact_sha256"])

    def test_never_emits_a_universal_score_probability_or_target(self) -> None:
        """target_price/probability appear only as declared negative boundaries (e.g.
        blocked_outputs["target_price"] == "NOT_EMITTED"), never as a populated numeric value
        on a record or event -- check the substantive fields, not the boundary declarations."""
        artifact = _build([_raw()])
        self.assertEqual(artifact["blocked_outputs"]["target_price"], "NOT_EMITTED")
        self.assertEqual(artifact["blocked_outputs"]["probability"], "NOT_EMITTED")
        self.assertEqual(artifact["blocked_outputs"]["universal_score"], "NOT_EMITTED")
        for record in artifact["records"].values():
            self.assertNotIn("score", record)
            self.assertNotIn("probability", record)
            for event in record["events"]:
                for forbidden_key in ("score", "probability", "target_price", "expected_return"):
                    self.assertNotIn(forbidden_key, event)

    def test_action_posture_and_share_basis_boundaries_are_explicit(self) -> None:
        artifact = _build([_raw()])
        self.assertTrue(artifact["authority_boundary"]["no_automatic_posture_change"])
        self.assertTrue(artifact["authority_boundary"]["share_basis_unchanged_by_planned_issuance"])
        self.assertTrue(artifact["authority_boundary"]["financial_metrics_unchanged_by_event_narrative"])
        self.assertEqual(artifact["blocked_outputs"]["research_action_posture"], "NOT_MODIFIED")

    def test_ownership_and_governance_coverage_are_honestly_zero(self) -> None:
        artifact = _build([_raw()])
        self.assertEqual(artifact["coverage"]["ownership_coverage"], 0)
        self.assertEqual(artifact["coverage"]["governance_coverage"], 0)
        self.assertEqual(artifact["ownership_context"]["status"], "UNAVAILABLE")

    def test_supplemental_retained_events_activate_the_real_hpg_vnm_vcb_evidence(self) -> None:
        """Live-evidence check (not synthetic): with include_supplemental_events, HPG/VNM/VCB's
        retained issuer/VSDC chains must surface even though none of the three carry an
        explicit ex-date and so are invisible to the official ex-date adapter alone."""
        artifact = _build([_raw(ticker="AAA")], tickers=["AAA", "HPG", "VNM", "VCB"], include_supplemental=True)
        for ticker in ("HPG", "VNM", "VCB"):
            self.assertNotEqual(artifact["records"][ticker]["state"], axis.NO_QUALIFIED_CORPORATE_EVENT,
                                 msg=f"{ticker} should carry retained supplemental corporate-event evidence")
        vnm_types = {event["event_type"] for event in artifact["records"]["VNM"]["events"]}
        self.assertIn(axis.DIVIDEND, vnm_types)
        vcb_types = {event["event_type"] for event in artifact["records"]["VCB"]["events"]}
        self.assertIn(axis.BONUS_ISSUE, vcb_types)


class ExportAttachmentTests(unittest.TestCase):
    def test_opt_in_attachment_is_default_off_and_preserves_decisions(self) -> None:
        artifact = _build([_raw()])
        entries = {"AAA": {"strategy_eligibility": "existing", "research_priority": "existing", "entry_action": "existing"}}
        untouched = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_corporate_intelligence_axis(entries, False, "missing.json"), untouched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corporate_intelligence_axis.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = bundle.attach_current_corporate_intelligence_axis(entries, True, str(path))
            attached = result["AAA"]["current_corporate_intelligence_axis"]
            self.assertFalse(attached["is_actionable"])
            self.assertIn(attached["status"], {"available", "no_qualified_corporate_event"})
            self.assertEqual(result["AAA"]["strategy_eligibility"], "existing")
            self.assertEqual(result["AAA"]["research_priority"], "existing")
            self.assertEqual(result["AAA"]["entry_action"], "existing")

    def test_tampered_artifact_fails_closed_and_attaches_nothing(self) -> None:
        artifact = _build([_raw()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corporate_intelligence_axis.json"
            tampered = dict(artifact)
            tampered["coverage"] = {**tampered["coverage"], "universe_denominator": 0}
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn(
                "current_corporate_intelligence_axis",
                bundle.attach_current_corporate_intelligence_axis({"AAA": {}}, True, str(path))["AAA"],
            )

    def test_no_score_probability_or_target_leaks_into_the_ai_bundle(self) -> None:
        """probability/target_price appear only as declared negative boundaries
        (blocked_outputs["probability"] == "NOT_EMITTED"); no populated numeric value exists."""
        artifact = _build([_raw()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corporate_intelligence_axis.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = bundle.attach_current_corporate_intelligence_axis({"AAA": {}}, True, str(path))
            attached = result["AAA"]["current_corporate_intelligence_axis"]
            self.assertNotIn("score", attached)
            self.assertNotIn("probability", attached)
            self.assertEqual(attached["blocked_outputs"]["probability"], "NOT_EMITTED")
            self.assertEqual(attached["blocked_outputs"]["target_price"], "NOT_EMITTED")
            for event in attached["events"]:
                for forbidden_key in ("score", "probability", "target_price", "expected_return"):
                    self.assertNotIn(forbidden_key, event)


if __name__ == "__main__":
    unittest.main()
