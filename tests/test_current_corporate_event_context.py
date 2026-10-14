"""Contract regressions for current corporate event research context."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import current_corporate_event_context as events
import current_official_event_context as official_events
from stocklookup_core.evidence import current_official_market_universe as official
import export_ai_bundle as bundle
import polymorphic_current_strategy_classification as strategy


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "daily_research_session_input_registry.json"
FROZEN_20260821 = "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a"
FROZEN_20260824 = "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388"
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


def _build(raw_events: list[dict], tickers: list[str] | None = None,
           supplemental: list[dict] | None = None, session: str = SESSION,
           cutoff: str | None = None) -> dict:
    tickers = tickers or sorted({event["ticker"] for event in raw_events} | {item["ticker"] for item in (supplemental or [])})
    return events.build_artifact(
        official_universe=_signed_official(tickers),
        official_event_context=_signed_event_context(raw_events, session),
        supplemental_events=supplemental,
        research_session=session,
        knowledge_cutoff=cutoff,
    )


class CurrentCorporateEventContextTests(unittest.TestCase):
    def test_known_at_after_as_of_is_excluded(self) -> None:
        artifact = _build([
            _raw(published_at="2026-08-22", known_at="2026-08-22"),
            _raw(ticker="BBB", event_id="official-b", source_identity="src-b",
                 published_at="2026-08-10", known_at="2026-08-10"),
        ], tickers=["AAA", "BBB"])
        self.assertEqual(artifact["records"]["AAA"]["events"], [])
        self.assertEqual(len(artifact["records"]["BBB"]["events"]), 1)

    def test_known_upcoming_event_is_accepted(self) -> None:
        artifact = _build([_raw()])
        row = artifact["records"]["AAA"]["events"][0]
        self.assertEqual(row["event_status"], events.CONFIRMED_UPCOMING)
        self.assertEqual(row["known_at"], "2026-08-10")
        self.assertLessEqual(row["known_at"], SESSION)

    def test_record_date_is_never_inferred_as_ex_date(self) -> None:
        artifact = _build([_raw(ex_date=None, record_date="2026-07-21", execution_date=None,
                                event_state="DATE_INCOMPLETE", qualification="MISSING_EX_DATE")])
        row = artifact["records"]["AAA"]["events"][0]
        self.assertIsNone(row["ex_date"])
        self.assertEqual(row["record_date"], "2026-07-21")
        self.assertEqual(row["event_status"], events.TEMPORAL_DETAILS_INCOMPLETE)
        self.assertIn("RECORD_DATE_IS_NOT_EX_DATE", row["warnings"])
        self.assertIn("EX_DATE_NOT_INFERRED", row["blockers"])

    def test_planned_issuance_is_not_executed(self) -> None:
        supplemental = [{
            "ticker": "VCB", "event_type": "BONUS_OR_STOCK_DIVIDEND", "status": "APPROVED",
            "announcement_date": "2026-07-01", "record_date": "2026-07-15", "ex_date": None,
            "effective_date": None, "payment_date": None, "authority_tier": "OFFICIAL_QUALIFIED",
            "source_authority": "ISSUER_IR", "evidence_identity": "vcb-approved",
            "retrieved_at": "2026-08-20", "event_id": "ci-vcb", "limitations": ["Record date is not an ex-date."],
        }]
        artifact = _build([], tickers=["VCB"], supplemental=supplemental)
        row = artifact["records"]["VCB"]["events"][0]
        self.assertEqual(row["event_status"], events.PLANNED_NOT_EXECUTED)
        self.assertIsNone(row["ex_date"])
        self.assertIsNone(row["execution_date"])

    def test_executed_event_requires_execution_evidence(self) -> None:
        past = _build([_raw(ex_date="2026-06-01", record_date="2026-06-02", execution_date=None,
                            event_state="PAST")])
        self.assertEqual(past["records"]["AAA"]["events"][0]["event_status"], events.DATA_LIMITED)
        executed = _build([_raw(ex_date="2026-06-01", record_date="2026-06-02",
                                execution_date="2026-06-20", event_state="PAST")])
        self.assertEqual(executed["records"]["AAA"]["events"][0]["event_status"], events.DATA_LIMITED)

    def test_conflicting_dates_fail_closed(self) -> None:
        artifact = _build([
            _raw(ex_date="2026-08-28", record_date="2026-09-03", source="hnx_official_rights_event_index/v1",
                 source_identity="hnx-1", event_id="e1"),
            _raw(ex_date="2026-08-29", record_date="2026-09-03", source="hose_public_event_hpg/v1",
                 source_identity="hose-1", event_id="e2", source_record_identity="hose-1"),
        ])
        statuses = {row["event_status"] for row in artifact["records"]["AAA"]["events"]}
        self.assertEqual(statuses, {events.CONFLICTING_EVIDENCE})

    def test_multi_source_exact_identity_is_deduplicated(self) -> None:
        artifact = _build([
            _raw(source="hnx_official_rights_event_index/v1", source_identity="hnx-1", event_id="e1"),
            _raw(source="hose_public_event_hpg/v1", source_identity="hose-1", event_id="e2",
                 source_record_identity="hose-1"),
        ])
        self.assertEqual(len(artifact["records"]["AAA"]["events"]), 1)
        self.assertGreaterEqual(len(artifact["records"]["AAA"]["events"][0]["source_identities"]), 2)

    def test_near_duplicate_distinct_events_remain_distinct(self) -> None:
        artifact = _build([
            _raw(record_date="2026-09-03", ex_date="2026-08-28", source_identity="a", event_id="e1"),
            _raw(record_date="2026-09-04", ex_date="2026-08-29", source_identity="b", event_id="e2",
                 source_record_identity="src-b"),
        ])
        self.assertEqual(len(artifact["records"]["AAA"]["events"]), 2)

    def test_official_versus_lower_tier_evidence_preserved(self) -> None:
        artifact = _build([
            _raw(qualification="EX_DATE_OFFICIAL_QUALIFIED"),
            _raw(ticker="BBB", event_id="b", source_identity="src-b",
                 qualification="PUBLIC_EVENT_INDEX_ONLY_NO_PRICE_OR_SHARE_MUTATION",
                 event_type="CASH_DIVIDEND"),
        ], tickers=["AAA", "BBB"])
        self.assertEqual(artifact["records"]["AAA"]["events"][0]["evidence_tier"], "OFFICIAL_QUALIFIED")
        self.assertEqual(artifact["records"]["BBB"]["events"][0]["evidence_tier"], "OFFICIAL_SOURCE_TEMPORALLY_INCOMPLETE")

    def test_missing_event_does_not_fabricate_a_neutral_event(self) -> None:
        artifact = _build([_raw()], tickers=["AAA", "ZZZ"])
        self.assertEqual(artifact["records"]["ZZZ"]["events"], [])
        self.assertFalse(artifact["records"]["ZZZ"]["has_qualified_event"])
        self.assertEqual(artifact["records"]["ZZZ"]["confirmed_upcoming_count"], 0)

    def test_event_context_does_not_enable_event_driven_or_change_priority_entry(self) -> None:
        artifact = _build([_raw(event_type="AGM", materiality_status="INFORMATIONAL_GOVERNANCE")])
        self.assertTrue(artifact["records"]["AAA"]["events"][0]["insufficient_for_event_driven"])
        self.assertTrue(artifact["records"]["AAA"]["does_not_enable_event_driven"])
        self.assertEqual(artifact["blocked_outputs"]["event_driven_strategy"], "NOT_ENABLED_BY_THIS_CONTEXT")
        self.assertEqual(artifact["blocked_outputs"]["research_priority"], "NOT_MODIFIED")
        self.assertEqual(artifact["blocked_outputs"]["entry_action"], "NOT_MODIFIED")
        ci_row = {"catalyst_research": {"recent_material_events": []}}
        requirement = strategy._event_requirement(ci_row)
        self.assertEqual(requirement["status"], "MISSING")

    def test_no_price_impact_probability_or_recommendation_fields(self) -> None:
        artifact = _build([_raw()])
        for row in artifact["records"].values():
            self.assertNotIn("price_impact", row)
            self.assertNotIn("probability", row)
            self.assertNotIn("recommendation", row)
            for event in row["events"]:
                self.assertNotIn("price_impact", event)
                self.assertNotIn("bullish", json.dumps(event))
        self.assertFalse(artifact["authority_boundary"]["is_actionable"])
        self.assertTrue(artifact["authority_boundary"]["ex_date_not_inferred"])

    def test_replay_and_frozen_identities(self) -> None:
        artifact = _build([_raw()])
        again = _build([_raw()])
        self.assertEqual(artifact["artifact_identity"], again["artifact_identity"])
        events.replay(artifact)
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["sessions"]["2026-08-21"]["valuation"]["artifact_identity"], FROZEN_20260821)
        self.assertEqual(registry["sessions"]["2026-08-24"]["valuation"]["artifact_identity"], FROZEN_20260824)

    def test_classify_helpers_are_explicit(self) -> None:
        as_of = date.fromisoformat(SESSION)
        self.assertEqual(events.classify_event_status({"ex_date": "2026-08-28"}, as_of=as_of)[0], events.CONFIRMED_UPCOMING)
        self.assertFalse(events.known_at_ok(known_at="2026-08-22", published_at="2026-08-22", as_of=as_of))
        self.assertTrue(events.known_at_ok(known_at="2026-08-10", published_at="2026-08-10", as_of=as_of))


class QualificationAndKnowledgeTimeCorrectiveTests(unittest.TestCase):
    def supplemental(self, **changes) -> dict:
        event = dict(ticker="AAA", event_type="CASH_DIVIDEND", status="ANNOUNCED",
                     ex_date="2026-08-28", announcement_date="2026-08-10",
                     evidence_identity="retained-issuer-record", source_authority="ISSUER_IR")
        event.update(changes)
        return event

    def test_missing_and_unqualified_tiers_preserve_context_without_qualification(self):
        for tier in (None, "", "UNKNOWN", "RESEARCH_ONLY", "OFFICIAL_SOURCE_TEMPORALLY_INCOMPLETE"):
            with self.subTest(tier=tier):
                raw = self.supplemental(authority_tier=tier)
                original = copy.deepcopy(raw)
                artifact = _build([], supplemental=[raw])
                row = artifact["records"]["AAA"]
                self.assertEqual(raw, original)
                self.assertEqual(len(row["events"]), 1)
                self.assertEqual(row["events"][0]["evidence_tier"], tier or "UNKNOWN")
                self.assertEqual(row["qualified_event_count"], 0)
                self.assertFalse(row["has_qualified_event"])
                self.assertEqual(artifact["coverage"]["tickers_with_qualified_event"], 0)
                self.assertEqual(artifact["coverage"]["tickers_with_no_qualified_event"], 1)
                if not tier:
                    self.assertIn("AUTHORITY_TIER_UNSPECIFIED", row["events"][0]["warnings"])

    def test_qualified_historical_source_evidence_keeps_its_tier_and_eligibility(self):
        artifact = _build([_raw()], tickers=["AAA", "BBB", "ZZZ"], supplemental=[
            self.supplemental(ticker="BBB", authority_tier="OFFICIAL_QUALIFIED")])
        for ticker in ("AAA", "BBB"):
            row = artifact["records"][ticker]
            self.assertTrue(row["has_qualified_event"])
            self.assertEqual(row["qualified_event_count"], 1)
            self.assertTrue(row["events"][0]["historical_known_at_eligible"])
        self.assertEqual(artifact["coverage"]["tickers_with_qualified_event"], 2)
        self.assertEqual(artifact["coverage"]["tickers_with_no_qualified_event"], 1)

    def test_missing_invalid_and_same_day_date_only_proof_is_explicit_context(self):
        cases = [(None, None, "KNOWLEDGE_TIME_MISSING"),
                 ("malformed", None, "KNOWLEDGE_TIME_INVALID_OR_UNZONED"),
                 (None, "2026-08-10garbage", "KNOWLEDGE_TIME_INVALID_OR_UNZONED"),
                 (None, "2026-08-10T10:00:00", "KNOWLEDGE_TIME_INVALID_OR_UNZONED"),
                 (None, "2026-08-21", "DATE_ONLY_CUTOFF_UNPROVEN"),
                 ("malformed", "2026-08-10", "KNOWLEDGE_TIME_INVALID_OR_UNZONED"),
                 ("2026-08-10", "malformed", "KNOWLEDGE_TIME_INVALID_OR_UNZONED")]
        for known, publication, expected in cases:
            with self.subTest(known=known, publication=publication):
                self.assertFalse(events.known_at_ok(known_at=known, published_at=publication,
                                                    as_of=date.fromisoformat(SESSION)))
                official = _raw(known_at=known, published_at=publication)
                supplemental = self.supplemental(known_at=known, published_at=publication,
                                                announcement_date=None, authority_tier="OFFICIAL_QUALIFIED")
                for artifact in (_build([official]), _build([], supplemental=[supplemental])):
                    row = artifact["records"]["AAA"]["events"][0]
                    self.assertEqual(row["knowledge_time_qualification"], expected)
                    self.assertFalse(row["historical_known_at_eligible"])
                    self.assertIn("HISTORICAL_KNOWN_AT_NOT_ESTABLISHED", row["blockers"])
                    # Source qualification is retained; missing clocks cannot repair T0.
                    self.assertEqual(row["evidence_tier"], "OFFICIAL_QUALIFIED")
                    self.assertIn("current_research_context", row["allowed_uses"])
                    self.assertEqual(artifact["records"]["AAA"]["historical_known_at_eligible_event_count"], 0)
                    self.assertEqual(artifact["authority_boundary"]["pit"], "BLOCKED")

    def test_same_session_before_equal_after_cutoff_and_equivalent_timezones(self):
        for publication, accepted in [("2026-08-21T14:59:59+07:00", True),
                                      ("2026-08-21T15:00:00+07:00", True),
                                      ("2026-08-21T08:00:00Z", True),
                                      ("2026-08-21T15:00:00.000001+07:00", False),
                                      ("2026-08-21T08:00:01Z", False),
                                      ("2026-08-20T23:30:00-10:00", False)]:
            with self.subTest(publication=publication):
                self.assertEqual(events.known_at_ok(known_at=None, published_at=publication,
                                                   as_of=date.fromisoformat(SESSION)), accepted)
                artifact = _build([_raw(known_at=None, published_at=publication)])
                self.assertEqual(len(artifact["records"]["AAA"]["events"]), int(accepted))
                self.assertEqual(artifact["knowledge_cutoff"], "2026-08-21T15:00:00+07:00")

    def test_explicit_later_clock_cannot_hide_behind_earlier_clock(self):
        for known, publication in [("2026-08-10", "2026-08-21T16:00:00+07:00"),
                                   ("2026-08-21T16:00:00+07:00", "2026-08-10"),
                                   ("invalid", "2026-08-22"),
                                   ("2026-08-22", "invalid")]:
            with self.subTest(known=known, publication=publication):
                self.assertEqual(_build([_raw(known_at=known, published_at=publication)])
                                 ["records"]["AAA"]["events"], [])

    def test_precise_supplemental_publication_is_not_masked_by_announcement_date(self):
        artifact = _build([], supplemental=[self.supplemental(
            announcement_date="2026-08-21", published_at="2026-08-21T14:00:00+07:00")])
        row = artifact["records"]["AAA"]["events"][0]
        self.assertTrue(row["historical_known_at_eligible"])
        self.assertEqual(row["announcement_date"], "2026-08-21")
        self.assertEqual(row["published_at"], "2026-08-21T14:00:00+07:00")
        later = _build([], supplemental=[self.supplemental(
            announcement_date="2026-08-10", published_at="2026-08-21T16:00:00+07:00")])
        self.assertEqual(later["records"]["AAA"]["events"], [])

    def test_falsey_malformed_clocks_cannot_be_replaced_by_valid_fallbacks(self):
        for malformed in (0, False, [], {}):
            with self.subTest(malformed=malformed):
                for field in ("published_at", "known_at"):
                    raw = self.supplemental(**{field: malformed})
                    row = _build([], supplemental=[raw])["records"]["AAA"]["events"][0]
                    self.assertFalse(row["historical_known_at_eligible"])
                    self.assertEqual(row[field], malformed)
                    self.assertEqual(row["knowledge_time_qualification"], "KNOWLEDGE_TIME_INVALID_OR_UNZONED")

    def test_date_only_prior_day_is_proof_but_same_day_never_infers_midnight(self):
        as_of = date.fromisoformat(SESSION)
        self.assertTrue(events.known_at_ok(known_at=None, published_at="2026-08-20", as_of=as_of))
        self.assertFalse(events.known_at_ok(known_at="2026-08-21", published_at=None, as_of=as_of))
        self.assertFalse(events.known_at_ok(known_at="2026-08-21", published_at="2026-08-21T14:00:00+07:00", as_of=as_of))

    def test_explicit_earlier_cutoff_is_honored_and_cannot_widen_session_boundary(self):
        artifact = _build([_raw(known_at="2026-08-21T14:00:00+07:00", published_at=None)],
                          cutoff="2026-08-21T13:00:00+07:00")
        self.assertEqual(artifact["records"]["AAA"]["events"], [])
        for cutoff in ("invalid", "2026-08-21", "2026-08-21T15:00:00", "2026-08-22T14:00:00+07:00",
                       "2026-08-21T16:00:00+07:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(events.CurrentCorporateEventContextError):
                _build([_raw()], cutoff=cutoff)
        with self.assertRaises(events.CurrentCorporateEventContextError):
            events.known_at_ok(known_at="2026-08-10", published_at=None,
                              as_of=datetime(2026, 8, 21, 15))

    def test_deduplication_cannot_transfer_lower_tier_clock_proof_to_qualified_source(self):
        lower = self.supplemental(authority_tier="RESEARCH_ONLY", status=None,
                                  record_date="2026-09-03", payment_date="2026-09-15")
        official = _raw(known_at=None, published_at=None)
        artifact = _build([official], supplemental=[lower])
        row = artifact["records"]["AAA"]
        self.assertEqual(len(row["events"]), 1)
        self.assertEqual(row["qualified_event_count"], 1)
        self.assertFalse(row["events"][0]["historical_known_at_eligible"])
        support = row["events"][0]["supporting_evidence"]
        self.assertEqual({item["evidence_tier"] for item in support}, {"OFFICIAL_QUALIFIED", "RESEARCH_ONLY"})
        self.assertEqual({item["historical_known_at_eligible"] for item in support}, {True, False})

    def test_lower_tier_duplicate_first_does_not_hide_real_qualified_evidence(self):
        artifact = _build([], supplemental=[
            self.supplemental(authority_tier="RESEARCH_ONLY", source_authority="THIRD_PARTY"),
            self.supplemental(authority_tier="OFFICIAL_QUALIFIED", source_authority="ISSUER_IR")])
        self.assertEqual(artifact["records"]["AAA"]["qualified_event_count"], 1)
        self.assertEqual(len(artifact["records"]["AAA"]["events"]), 1)

    def test_pnj_fpt_unqualified_candidate_context_does_not_become_admission(self):
        # Candidate-shaped research records exercise the boundary, not factual admission.
        artifact = _build([], tickers=["PNJ", "FPT"], session="2026-10-14", supplemental=[
            self.supplemental(ticker=ticker, authority_tier="CANDIDATE_UNADMITTED",
                              announcement_date=None, published_at=None)
            for ticker in ("PNJ", "FPT")])
        for row in artifact["records"].values():
            self.assertFalse(row["has_qualified_event"])
            self.assertFalse(row["events"][0]["historical_known_at_eligible"])
        self.assertEqual(artifact["coverage"]["tickers_with_qualified_event"], 0)
        self.assertEqual(artifact["coverage"]["tickers_with_no_qualified_event"], 2)
        self.assertEqual(artifact["blocked_outputs"]["research_priority"], "NOT_MODIFIED")
        self.assertEqual(artifact["blocked_outputs"]["entry_action"], "NOT_MODIFIED")

    def test_existing_v1_artifacts_replay_without_new_temporal_fields(self):
        historical = _build([_raw()])
        for key in ("knowledge_cutoff", "knowledge_time_policy"):
            historical.pop(key)
        for row in historical["records"].values():
            row.pop("historical_known_at_eligible_event_count")
            for event in row["events"]:
                event.pop("knowledge_time_qualification")
                event.pop("historical_known_at_eligible")
        historical.update(events.content_identity(historical))
        original = copy.deepcopy(historical)
        events.replay(historical)
        self.assertEqual(historical, original)


class ExportAttachmentTests(unittest.TestCase):
    def test_opt_in_attachment_is_default_off_and_preserves_decisions(self) -> None:
        artifact = _build([_raw()])
        entries = {"AAA": {"strategy_eligibility": "existing", "research_priority": "existing", "entry_action": "existing"}}
        untouched = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_corporate_event_context(entries, False, "missing.json"), untouched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = bundle.attach_current_corporate_event_context(entries, True, str(path))
            attached = result["AAA"]["current_corporate_event_context"]
            self.assertFalse(attached["is_actionable"])
            self.assertEqual(attached["ticker_context"]["confirmed_upcoming_count"], 1)
            self.assertEqual(result["AAA"]["strategy_eligibility"], "existing")
            self.assertEqual(result["AAA"]["research_priority"], "existing")
            self.assertEqual(result["AAA"]["entry_action"], "existing")
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["coverage"]["universe_denominator"] = 0
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn(
                "current_corporate_event_context",
                bundle.attach_current_corporate_event_context({"AAA": {}}, True, str(path))["AAA"],
            )


class LedgerBoundaryTests(unittest.TestCase):
    """CORPORATE_EVENT_CANONICAL_DATA_REFRESH_AND_LEDGER_CONSOLIDATION_V1 Section 2:
    corporate_action_ledger.py and official_corporate_action_ledger.py are legitimately distinct
    PIT/price-adjustment-authority ledgers (different upstream evidence, different consumers --
    see ledger_reconciliation.json), not the current-research canonical event boundary. Neither
    is imported here; this module's own current_official_event_context / market_wide_current_
    corporate_intelligence inputs remain the one canonical projection for Current Research."""

    def test_canonical_event_boundary_does_not_import_either_pit_ledger(self) -> None:
        source = (ROOT / "current_corporate_event_context.py").read_text(encoding="utf-8")
        self.assertNotIn("corporate_action_ledger", source)
        self.assertNotIn("official_corporate_action_ledger", source)


if __name__ == "__main__":
    unittest.main()


class ScheduledDateLifecycleTests(unittest.TestCase):
    def test_past_schedule_never_proves_execution(self):
        from datetime import date
        for lifecycle in ('PLANNED', 'APPROVED', ''):
            with self.subTest(lifecycle=lifecycle):
                status, _ = events.classify_event_status(dict(status=lifecycle, execution_date='2026-09-01', ex_date='2026-09-02'), as_of=date(2026,10,2))
                self.assertNotEqual(status, events.EXECUTED)

    def test_explicit_source_lifecycle_still_passes(self):
        from datetime import date
        status, _ = events.classify_event_status(dict(status='EXECUTED', execution_date='2026-09-01'), as_of=date(2026,10,2))
        self.assertEqual(status, events.EXECUTED)
