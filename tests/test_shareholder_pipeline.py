"""Phase 6 shareholder source-chain tests; all fixtures are offline."""

from __future__ import annotations

import sys
import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shareholder_pipeline import (  # noqa: E402
    DONE,
    MANUAL_OVERRIDE,
    NETWORK_FAILED,
    NOT_QUERIED,
    PARSE_FAILED,
    SOURCE_EMPTY,
    STALE,
    UNSUPPORTED,
    NetworkSourceError,
    ShareholderRecord,
    ShareholderSourceAdapter,
    UnsupportedSourceError,
    build_shareholder_summary,
    deduplicate_records,
    load_manual_overrides,
    provider_parser,
    run_source_chain,
)


NOW = datetime(2026, 7, 13, 3, 0, tzinfo=timezone.utc)


def adapter(name, fetcher):
    return ShareholderSourceAdapter(
        source_name=name,
        fetcher=fetcher,
        parser=provider_parser(name),
        source_reference=f"fixture://{name.lower()}",
    )


def valid_vci(as_of="2026-06-30", name="Holder A", shares=100, pct=0.25):
    return [{"share_holder": name, "quantity": shares, "share_own_percent": pct, "update_date": as_of}]


def valid_kbs(as_of="2026-06-30", name="Holder B", shares=50, pct=5):
    return [{"name": name, "shares_owned": shares, "ownership_percentage": pct, "update_date": as_of}]


class ShareholderPipelineTests(unittest.TestCase):
    def test_source_empty_is_not_zero_shareholders(self):
        chain = run_source_chain("PAN", [adapter("VCI", lambda _: [])], NOW)
        summary = build_shareholder_summary(chain, today=date(2026, 7, 13))
        self.assertEqual(summary["status"], SOURCE_EMPTY)
        self.assertIsNone(summary["major_shareholders_count"])

    def test_source_empty_does_not_mean_no_major_shareholders(self):
        chain = run_source_chain("PAN", [adapter("VCI", lambda _: None)], NOW)
        summary = build_shareholder_summary(chain)
        self.assertEqual(summary["reason"], "configured_sources_returned_no_usable_records")
        self.assertNotEqual(summary["reason"], "company_has_no_major_shareholders")

    def test_source_fallback_order(self):
        calls = []

        def empty(_):
            calls.append("VCI")
            return []

        def good(_):
            calls.append("KBS")
            return valid_kbs()

        chain = run_source_chain("PAN", [adapter("VCI", empty), adapter("KBS", good)], NOW)
        self.assertEqual(calls, ["VCI", "KBS"])
        self.assertEqual([item.status for item in chain.attempts], [SOURCE_EMPTY, DONE])

    def test_valid_primary_source_stops_fallback(self):
        fallback_calls = []
        chain = run_source_chain(
            "PAN",
            [adapter("VCI", lambda _: valid_vci()), adapter("KBS", lambda _: fallback_calls.append(True))],
            NOW,
        )
        self.assertEqual(chain.final_status, DONE)
        self.assertEqual(fallback_calls, [])
        self.assertEqual(len(chain.attempts), 1)

    def test_parse_failed_differs_from_source_empty(self):
        parsed = run_source_chain("PAN", [adapter("VCI", lambda _: [{"unexpected": "payload"}])], NOW)
        empty = run_source_chain("PAN", [adapter("VCI", lambda _: [])], NOW)
        self.assertEqual(parsed.final_status, PARSE_FAILED)
        self.assertEqual(empty.final_status, SOURCE_EMPTY)

    def test_network_failed_differs_from_source_empty(self):
        def offline(_):
            raise NetworkSourceError("fixture timeout")

        failed = run_source_chain("PAN", [adapter("VCI", offline)], NOW)
        self.assertEqual(failed.final_status, NETWORK_FAILED)
        self.assertNotEqual(failed.final_status, SOURCE_EMPTY)

    def test_unsupported_source_is_recorded(self):
        def unsupported(_):
            raise UnsupportedSourceError("endpoint unavailable")

        chain = run_source_chain("PAN", [adapter("VCI", unsupported)], NOW)
        self.assertEqual(chain.final_status, UNSUPPORTED)
        self.assertEqual(chain.attempts[0].status, UNSUPPORTED)
        self.assertIn("endpoint unavailable", chain.attempts[0].error_reason)

    def test_manual_override_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manual.csv"
            path.write_text(
                "ticker,holder_name,shares,ownership_pct,as_of_date,source_name,source_reference,verified_at,note\n"
                "AAA,Verified Holder,100,,2026-06-30,Exchange filing,https://example.test/filing,2026-07-01T00:00:00Z,checked\n",
                encoding="utf-8",
            )
            manual = load_manual_overrides(path, "AAA")
        summary = build_shareholder_summary(run_source_chain("AAA", [], NOW), manual)
        self.assertEqual(summary["status"], MANUAL_OVERRIDE)
        self.assertEqual(summary["records"][0]["source_reference"], "https://example.test/filing")
        self.assertEqual(summary["records"][0]["record_origin"], "manual")

    def test_manual_override_does_not_delete_api_records(self):
        chain = run_source_chain("AAA", [adapter("VCI", lambda _: valid_vci(name="API Holder"))], NOW)
        manual = [
            ShareholderRecord(
                "AAA", "Manual Holder", 10, 2, "2026-06-30", "Exchange filing",
                "https://example.test/manual", "2026-07-01T00:00:00Z", record_origin="manual",
            )
        ]
        summary = build_shareholder_summary(chain, manual)
        self.assertEqual({item["record_origin"] for item in summary["records"]}, {"api", "manual"})

    def test_stale_shareholder_data_is_flagged(self):
        chain = run_source_chain("AAA", [adapter("VCI", lambda _: valid_vci(as_of="2025-01-01"))], NOW)
        summary = build_shareholder_summary(chain, freshness_threshold_days=180, today=date(2026, 7, 13))
        self.assertEqual(summary["status"], STALE)
        self.assertEqual(summary["freshness"]["status"], STALE)
        self.assertEqual(len(summary["records"]), 1)

    def test_missing_denominator_does_not_create_ownership_pct(self):
        payload = [{"share_holder": "Holder A", "quantity": 100, "update_date": "2026-06-30"}]
        chain = run_source_chain("AAA", [adapter("VCI", lambda _: payload)], NOW)
        self.assertIsNone(chain.records[0].ownership_pct)

    def test_shareholder_deduplication(self):
        records = [
            ShareholderRecord("AAA", "  Holder   A ", 100, 10, "2026-06-30", "VCI"),
            ShareholderRecord("AAA", "holder a", 100, 10, "2026-06-30", "KBS"),
        ]
        deduplicated = deduplicate_records(records)
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0].reconciliation_status, "matched_across_sources")
        self.assertEqual(len(deduplicated[0].provenance), 2)

    def test_pan_shareholder_summary_has_explicit_status(self):
        summary = build_shareholder_summary(run_source_chain("PAN", [], NOW))
        self.assertEqual(summary["status"], NOT_QUERIED)
        self.assertIsNotNone(summary["reason"])
        self.assertEqual(summary["attempts"], [])

    @unittest.skipUnless(importlib.util.find_spec("pandas"), "pandas is only required by the live sync wrapper")
    def test_persisted_empty_result_keeps_legacy_api_snapshot(self):
        import shareholders_sync as sync

        connection = sqlite3.connect(":memory:")
        sync.init_db(connection)
        connection.execute(
            "INSERT INTO shareholders VALUES(?,?,?,?,?,?,?)",
            ("AAA", "Existing Holder", 100, 10, None, "VCI", "2026-01-01"),
        )
        connection.commit()
        summary = build_shareholder_summary(run_source_chain("AAA", [adapter("VCI", lambda _: [])], NOW))
        self.assertTrue(sync.persist_summary(connection, summary))
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM shareholders WHERE ticker='AAA'").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT status FROM shareholders_progress WHERE ticker='AAA'").fetchone()[0], SOURCE_EMPTY)
        connection.close()



if __name__ == "__main__":
    unittest.main()
