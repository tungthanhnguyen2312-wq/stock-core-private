"""Contract regressions for current corporate event research context."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import current_corporate_event_context as events
import current_official_event_context as official_events
import current_official_market_universe as official
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
           supplemental: list[dict] | None = None, session: str = SESSION) -> dict:
    tickers = tickers or sorted({event["ticker"] for event in raw_events} | {item["ticker"] for item in (supplemental or [])})
    return events.build_artifact(
        official_universe=_signed_official(tickers),
        official_event_context=_signed_event_context(raw_events, session),
        supplemental_events=supplemental,
        research_session=session,
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
        self.assertEqual(executed["records"]["AAA"]["events"][0]["event_status"], events.EXECUTED)

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


if __name__ == "__main__":
    unittest.main()
