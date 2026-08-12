from __future__ import annotations
import json
import unittest
import pandas as pd

from market_phase2_foundation import (FinancialPitFact, canonical_instrument_identity, evaluate_quality,
    expand_raw_ohlc, financial_facts_visible_as_of, phase1_provider_exceptions, semantic_registry)


def raw(symbol="AAA", payload=None):
    payload = payload or {"t": [1783908000, 1783994400], "o": [10, 10], "h": [11, 11], "l": [9, 9], "c": [10, 10], "v": [100, 110]}
    return {"provider":"DNSE", "dataset":"ohlc", "instrument":symbol, "retrieved_at":"2026-08-11T00:00:00+07:00",
            "request_identity":"req", "raw_payload_hash":"hash", "schema_version":"1", "observation_id":f"obs-{symbol}",
            "raw_payload_json":json.dumps(payload), "raw_file":"raw.parquet"}

class Phase2FoundationTests(unittest.TestCase):
    def test_identity_preserves_unknown_exchange_and_st_equity(self):
        identity = canonical_instrument_identity("DNSE", "AAA", {"exchange_raw":"UPX", "raw_security_group_id":"ST", "instrument_class":"EQUITY"})
        self.assertEqual("DNSE:AAA", identity["canonical_instrument_id"])
        self.assertEqual("UPX", identity["exchange_raw"])
        self.assertEqual("UNKNOWN", identity["canonical_exchange"])
        self.assertEqual("EQUITY", identity["instrument_class"])

    def test_unknown_group_is_not_promoted(self):
        identity = canonical_instrument_identity("DNSE", "EW1", {"exchange_raw":"STO", "raw_security_group_id":"EW", "instrument_class":"UNKNOWN_SECURITY_GROUP"})
        self.assertEqual("UNKNOWN_SECURITY_GROUP", identity["instrument_class"])
        self.assertEqual("UNKNOWN", identity["identity_status"])

    def test_expansion_preserves_raw_lineage(self):
        frame = expand_raw_ohlc([raw()], {"AAA":{"exchange_raw":"STO", "raw_security_group_id":"ST", "instrument_class":"EQUITY"}})
        self.assertEqual(2, len(frame)); self.assertEqual("obs-AAA", frame.iloc[0]["raw_observation_id"])
        self.assertEqual("UNKNOWN", frame.iloc[0]["price_basis_status"])
        self.assertEqual("HISTORICAL_ONLY", frame.iloc[0]["pit_status"])

    def test_empty_success_payload_remains_an_explicit_unresolved_row(self):
        payload = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
        frame = expand_raw_ohlc([raw(payload=payload)], {"AAA":{"instrument_class":"EQUITY"}})
        canonical, exceptions = evaluate_quality(frame)
        self.assertEqual(1, len(canonical)); self.assertEqual("SUSPECT", canonical.iloc[0]["quality_status"])
        self.assertIn("malformed_payload_schema", set(exceptions.quality_rule))

    def test_quality_flags_duplicate_impossible_negative_and_retains_input(self):
        frame = expand_raw_ohlc([raw("AAA", {"t":[1783908000],"o":[10],"h":[9],"l":[11],"c":[10],"v":[-1]}), raw("AAA", {"t":[1783908000],"o":[10],"h":[9],"l":[11],"c":[10],"v":[-1]})], {"AAA":{"instrument_class":"EQUITY"}})
        before = frame.copy(deep=True); canonical, exceptions = evaluate_quality(frame)
        self.assertTrue(frame.equals(before)); self.assertTrue((canonical.quality_status == "SUSPECT").all())
        self.assertTrue({"duplicate_logical_observation", "impossible_ohlc_relation", "negative_volume"}.issubset(set(exceptions.quality_rule)))
        self.assertTrue((exceptions.disposition == "UNRESOLVED").all())

    def test_extreme_return_and_insufficient_window_are_deterministic(self):
        payload = {"t":[1783908000+i*86400 for i in range(6)], "o":[10]*6,"h":[20]*6,"l":[9]*6,"c":[10,10,10,10,10,20],"v":[100]*6}
        canonical, exceptions = evaluate_quality(expand_raw_ohlc([raw(payload=payload)], {"AAA":{"instrument_class":"EQUITY"}}))
        self.assertIn("extreme_log_return", set(exceptions.quality_rule)); self.assertEqual(6, len(canonical))

    def test_provider_http400_is_preserved_without_message(self):
        queue = phase1_provider_exceptions(["AAA", "BBB"], {"AAA":{"exchange_raw":"UPX"},"BBB":{}}, "scope")
        self.assertEqual(2, len(queue)); self.assertTrue((queue.quality_rule == "http_status_400").all())
        self.assertTrue((queue.disposition == "UNRESOLVED").all())

    def test_semantic_registry_has_known_boards_and_unknown_volume(self):
        entries = semantic_registry(); lookup = {entry["raw_code"]:entry for entry in entries if entry["raw_code"]}
        self.assertEqual("ROUND_LOT", lookup["G1"]["normalized_meaning"])
        self.assertTrue(any(x["semantic_key"] == "DNSE.volume_basis" and x["status"] == "UNKNOWN" for x in entries))

    def test_financial_pit_no_lookahead_and_revision(self):
        first = FinancialPitFact("revenue", "AAA", 10, "2026-06-30", "2026-07-20", "2026-07-20", "2026-07-20", None, "first", "CONSOLIDATED", "AUDITED")
        revision = FinancialPitFact("revenue", "AAA", 11, "2026-06-30", "2026-07-20", "2026-08-10", "2026-07-20", "2026-08-10", "revision", "CONSOLIDATED", "AUDITED", "first")
        self.assertEqual([], financial_facts_visible_as_of([first, revision], "2026-07-01"))
        self.assertEqual(10, financial_facts_visible_as_of([first, revision], "2026-07-21")[0].value)
        self.assertEqual(11, financial_facts_visible_as_of([first, revision], "2026-08-10")[0].value)
