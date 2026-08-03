"""B1.1 — an official executed event establishes a current share basis.

The ledger had stated HPG's share count outright since 2026-08-02 and nothing read it: the
resolver looked for official anchors in `share_basis_citations.jsonl`, which held only FY2024
period-end figures, so a published count sat one directory away while HPG resolved as
`provider_reported_lagged`. These tests cover the reader that closes that gap and the
promotion gate that decides whether an anchor is a *current* count.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_wide_current_shares_resolver as shares  # noqa: E402
import share_basis_event_promotion as promotion  # noqa: E402

RUNTIME = ROOT.parent / "dashboard-runtime"
SESSION = "2026-08-03"
HPG_SHARES = 8442964520


def ledger_entry(**overrides) -> dict:
    entry = {
        "event_id": "evt1", "ticker": "AAA", "event_type": "stock_dividend",
        "lifecycle_state": "executed", "execution_status": "executed",
        "qualification_state": "qualified", "shares_after": 2000,
        "payment_or_execution_date": "2026-07-02", "trading_date": "2026-07-15",
        "ex_date": None, "record_date": None,
        "source_document_ids": ["doc1"], "source_content_hashes": ["hash1"],
        "superseded_by": None,
    }
    entry.update(overrides)
    return entry


def write_ledger(root: Path, entries: list[dict], superseded: list[str] = ()) -> Path:
    target = root / promotion.LEDGER_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "entries": entries, "entry_count": len(entries),
        "superseded_entry_ids": list(superseded),
        "replay_fingerprint": "fingerprint",
    }), encoding="utf-8")
    return root


def write_runtime(root: Path, *, anchors: list[dict], shares_outstanding: int,
                  observed: str = "2026-07-30", events: list[tuple] = ()) -> Path:
    evidence = root / "data" / "official-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / "share_basis_citations.jsonl").open("w", encoding="utf-8") as handle:
        for anchor in anchors:
            handle.write(json.dumps(anchor) + "\n")
    connection = sqlite3.connect(root / "vn_stock.db")
    connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
    connection.execute("INSERT INTO metadata VALUES ('AAA', ?, ?)",
                       (float(shares_outstanding), f"{observed} 17:00"))
    connection.execute("CREATE TABLE corporate_event_records "
                       "(ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
    connection.executemany("INSERT INTO corporate_event_records VALUES (?, ?, ?, ?)", events)
    connection.commit()
    connection.close()
    return root


def event_anchor(**overrides) -> dict:
    anchor = {
        "citation_id": "cite1", "ticker": "AAA",
        "identity_type": "current_shares_outstanding_after_event",
        "value": 2000, "share_class": "common_outstanding", "unit": "shares",
        "effective_date": "2026-07-02", "event_id": "evt1", "event_type": "stock_dividend",
        "corroborated_value": 2000, "corroborated_source": "provider",
        "corroborated_on": "2026-07-30",
    }
    anchor.update(overrides)
    return anchor


def period_end_anchor(**overrides) -> dict:
    anchor = {
        "citation_id": "cite0", "ticker": "AAA",
        "identity_type": "period_end_shares_outstanding", "value": 1000,
        "reporting_period": "2024", "reporting_frequency": "annual",
        "share_class": "common_outstanding", "unit": "shares",
    }
    anchor.update(overrides)
    return anchor


class LedgerReaderTests(unittest.TestCase):
    def _verdicts(self, entry: dict, superseded: list[str] = ()) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_ledger(Path(tmp), [entry], superseded)
            return promotion.promotable_citations(root)

    def test_a_qualified_executed_event_becomes_a_citation(self) -> None:
        result = self._verdicts(ledger_entry())
        self.assertEqual(len(result["citations"]), 1)
        citation = result["citations"][0]
        self.assertEqual(citation["value"], 2000)
        self.assertEqual(citation["effective_date"], "2026-07-02")
        self.assertEqual(citation["identity_type"], "current_shares_outstanding_after_event")
        self.assertEqual(citation["source_content_hashes"], ["hash1"])

    def test_an_ex_date_is_not_required(self) -> None:
        """An ex-date places an action on the price timeline; a share count needs execution."""
        result = self._verdicts(ledger_entry(ex_date=None, record_date=None))
        self.assertEqual(len(result["citations"]), 1)

    def test_an_unexecuted_event_is_refused(self) -> None:
        for state in ("proposed", "approved", "announced"):
            result = self._verdicts(ledger_entry(lifecycle_state=state))
            self.assertEqual(result["rejected"][0]["reason"], "event_not_executed")

    def test_an_unqualified_ledger_verdict_is_refused(self) -> None:
        result = self._verdicts(ledger_entry(qualification_state="provisional"))
        self.assertEqual(result["rejected"][0]["reason"], "ledger_verdict_not_qualified")

    def test_a_superseded_or_cancelled_entry_is_refused(self) -> None:
        self.assertEqual(self._verdicts(ledger_entry(), ["evt1"])["rejected"][0]["reason"],
                         "entry_superseded")
        self.assertEqual(self._verdicts(ledger_entry(superseded_by="evt2"))["rejected"][0]["reason"],
                         "entry_superseded")
        self.assertIn("withdrawn_or_amended",
                      self._verdicts(ledger_entry(lifecycle_state="cancelled"))["rejected"][0]["reason"])

    def test_an_event_that_does_not_change_the_count_is_refused(self) -> None:
        result = self._verdicts(ledger_entry(event_type="cash_dividend"))
        self.assertEqual(result["rejected"][0]["reason"],
                         "event_type_does_not_change_share_count")

    def test_a_missing_execution_date_or_shares_after_is_refused(self) -> None:
        result = self._verdicts(ledger_entry(payment_or_execution_date=None, trading_date=None))
        self.assertEqual(result["rejected"][0]["reason"], "no_stated_execution_date")
        result = self._verdicts(ledger_entry(shares_after=None))
        self.assertEqual(result["rejected"][0]["reason"], "no_stated_shares_after")

    def test_a_contradicting_observation_refuses_rather_than_picks_a_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_ledger(Path(tmp), [ledger_entry()])
            result = promotion.promotable_citations(
                root, corroboration={"AAA": {"value": 1999, "source": "provider"}})
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["rejected"][0]["reason"],
                         "independent_observation_contradicts_stated_shares_after")

    def test_an_unreadable_ledger_raises_rather_than_reporting_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(promotion.LedgerUnavailable):
                promotion.promotable_citations(Path(tmp))


class PromotionGateTests(unittest.TestCase):
    def _resolve(self, **kwargs) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_runtime(Path(tmp), **kwargs)
            return shares.resolve_effective_shares("AAA", root, SESSION)

    def test_a_corroborated_event_anchor_qualifies(self) -> None:
        result = self._resolve(anchors=[event_anchor()], shares_outstanding=2000)
        self.assertEqual(result["authority"], "qualified_official")
        self.assertEqual(result["value"], 2000)
        self.assertEqual(result["share_concept"], "current_common_shares_outstanding")

    def test_a_period_end_anchor_alone_never_qualifies(self) -> None:
        result = self._resolve(anchors=[period_end_anchor()], shares_outstanding=1000)
        self.assertNotEqual(result["authority"], "qualified_official")
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "anchor_is_a_period_end_figure_not_a_dated_current_count")

    def test_an_event_anchor_outranks_a_period_end_anchor(self) -> None:
        result = self._resolve(anchors=[period_end_anchor(), event_anchor()],
                               shares_outstanding=2000)
        self.assertEqual(result["official_anchor_value"], 2000)
        self.assertEqual(result["authority"], "qualified_official")

    def test_an_anchor_effective_after_the_session_is_refused(self) -> None:
        result = self._resolve(anchors=[event_anchor(effective_date="2026-09-01")],
                               shares_outstanding=2000)
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "official_anchor_takes_effect_after_the_session")

    def test_an_uncorroborated_anchor_is_refused(self) -> None:
        result = self._resolve(anchors=[event_anchor(corroborated_value=None)],
                               shares_outstanding=2000)
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "no_independent_observation_corroborates_the_stated_count")

    def test_a_provider_that_has_since_moved_on_is_refused(self) -> None:
        result = self._resolve(anchors=[event_anchor()], shares_outstanding=2500)
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "retained_provider_observation_no_longer_matches_the_corroborated_count")

    def test_an_observation_predating_the_event_cannot_corroborate_it(self) -> None:
        result = self._resolve(anchors=[event_anchor()], shares_outstanding=2000,
                               observed="2026-06-01")
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "corroborating_observation_predates_the_event")

    def test_a_later_share_changing_event_reopens_the_question(self) -> None:
        result = self._resolve(
            anchors=[event_anchor()], shares_outstanding=2000,
            events=[("AAA", "ISS", "2026-07-20", "partial_unqualified_50_row_cap")])
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "a_later_share_changing_event_is_recorded_after_the_anchor")


class LiveRuntimeTests(unittest.TestCase):
    """What the retained evidence actually supports today."""

    def test_hpg_qualifies_from_its_own_notice(self) -> None:
        result = shares.resolve_effective_shares("HPG", RUNTIME, SESSION)
        self.assertEqual(result["authority"], "qualified_official")
        self.assertEqual(result["value"], HPG_SHARES)
        self.assertEqual(result["official_anchor_effective_date"], "2026-07-02")

    def test_vnm_and_vcb_stay_refused_for_a_named_reason(self) -> None:
        for ticker in ("VNM", "VCB"):
            result = shares.resolve_effective_shares(ticker, RUNTIME, SESSION)
            self.assertNotEqual(result["authority"], "qualified_official")
            self.assertEqual(result["official_anchor_not_promoted_because"],
                             "anchor_is_a_period_end_figure_not_a_dated_current_count")

    def test_exactly_one_ticker_is_qualified_market_wide(self) -> None:
        summary = shares.resolve_market_wide_shares(RUNTIME, SESSION)
        self.assertEqual(summary["counts"].get("qualified_official"), 1)
        self.assertTrue(summary["counts_reconcile"])


if __name__ == "__main__":
    unittest.main()
