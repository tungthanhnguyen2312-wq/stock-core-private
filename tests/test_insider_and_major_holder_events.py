"""State derivation never infers an executed volume from a registered one, and vice versa."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import insider_and_major_holder_events as events  # noqa: E402


def _shares(value: float) -> dict:
    return {"raw": f"{value:g} CP", "shares": value}


class DeriveTransactionState(unittest.TestCase):
    def test_registered_only_is_registered_buy(self):
        state, reason = events.derive_transaction_state({"registered_buy_volume": _shares(100_000.0)})
        self.assertEqual(state, events.REGISTERED_BUY)

    def test_registered_sell_only_is_registered_sell(self):
        state, _ = events.derive_transaction_state({"registered_sell_volume": _shares(200_000.0)})
        self.assertEqual(state, events.REGISTERED_SELL)

    def test_executed_zero_is_not_executed_never_dropped(self):
        state, reason = events.derive_transaction_state({
            "registered_buy_volume": _shares(1_000_000.0), "executed_buy_volume": _shares(0.0)})
        self.assertEqual(state, events.NOT_EXECUTED)
        self.assertIn("0", reason)

    def test_partial_execution(self):
        state, _ = events.derive_transaction_state({
            "registered_buy_volume": _shares(1_000_000.0), "executed_buy_volume": _shares(400_000.0)})
        self.assertEqual(state, events.PARTIALLY_EXECUTED)

    def test_full_execution(self):
        state, _ = events.derive_transaction_state({
            "registered_sell_volume": _shares(200_000.0), "executed_sell_volume": _shares(200_000.0)})
        self.assertEqual(state, events.EXECUTED_SELL)

    def test_executed_without_registered_context_still_reports_executed(self):
        """A standalone result notice with no registered figure of its own is not blocked --
        but it must not silently invent a registered figure to compare against."""
        state, reason = events.derive_transaction_state({"executed_buy_volume": _shares(50_000.0)})
        self.assertEqual(state, events.EXECUTED_BUY)
        self.assertIn("no registered volume", reason)

    def test_neither_field_is_unknown_not_zero(self):
        state, _ = events.derive_transaction_state({})
        self.assertEqual(state, events.UNKNOWN)

    def test_never_derives_executed_from_registered(self):
        """Registered alone, with no executed field present at all, must never become an
        executed state merely because a registered volume exists."""
        state, _ = events.derive_transaction_state({"registered_buy_volume": _shares(1.0)})
        self.assertNotIn("EXECUTED", state)


class DeriveMajorHolderState(unittest.TestCase):
    def test_ceased(self):
        state, _ = events.derive_major_holder_state(
            {"ceased_major_holder_date": {"raw": "14/08/2026", "iso_date": "2026-08-14"}})
        self.assertEqual(state, events.CEASED_MAJOR_HOLDER)

    def test_became(self):
        state, _ = events.derive_major_holder_state(
            {"became_major_holder_date": {"raw": "01/01/2026", "iso_date": "2026-01-01"}})
        self.assertEqual(state, events.BECAME_MAJOR_HOLDER)

    def test_neither_is_unknown(self):
        state, _ = events.derive_major_holder_state({})
        self.assertEqual(state, events.UNKNOWN_MAJOR_HOLDER_EVENT)


class BuildObservations(unittest.TestCase):
    def test_insider_observation_carries_citation_and_related_persons(self):
        detail = {
            "title": "T", "published_at_raw": "15:15 22/08/2026", "ticker": "VNF",
            "fields": {"actor_entity_name": "Co X", "executed_buy_volume": _shares(0.0),
                      "registered_buy_volume": _shares(1_000_000.0)},
            "related_persons": [{"name": "A", "shares_held": _shares(10.0)}],
            "citations": {"actor_entity_name": "- Ten to chuc: Co X"},
            "unparsed_fields": [], "extraction_complete": True,
        }
        obs = events.build_insider_transaction_observation(
            document_id="D1", content_sha256="S1", source_url="https://www.hnx.vn/x.html",
            published_at="15:15 22/08/2026", detail=detail)
        self.assertEqual(obs["state"], events.NOT_EXECUTED)
        self.assertEqual(obs["ticker"], "VNF")
        self.assertEqual(len(obs["related_persons"]), 1)
        self.assertEqual(obs["warnings"], [])

    def test_missing_ticker_is_warned_not_silent(self):
        detail = {"title": "T", "published_at_raw": None, "ticker": None, "fields": {},
                  "related_persons": [], "citations": {}, "unparsed_fields": [], "extraction_complete": True}
        obs = events.build_major_holder_observation(
            document_id="D2", content_sha256="S2", source_url="https://www.hnx.vn/y.html",
            published_at=None, detail=detail)
        self.assertIn("ticker_not_recognised_in_this_document", obs["warnings"])


if __name__ == "__main__":
    unittest.main()
