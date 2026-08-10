from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import dnse_market_risk_evidence_store as store


def _raw_ohlc(n: int = 3) -> dict:
    return {
        "o": [24.0 + i for i in range(n)], "h": [24.5 + i for i in range(n)],
        "l": [23.5 + i for i in range(n)], "c": [24.2 + i for i in range(n)],
        "t": [1783994400 + i * 86400 for i in range(n)],
        "v": [1_000_000 + i for i in range(n)],  # must never be persisted
        "nextTime": 999999999,  # must never be persisted
    }


class PathHelperTests(unittest.TestCase):
    def test_stock_path_uppercases_and_namespaces_by_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = store.stock_ohlc_path(tmp, "hpg")
        self.assertTrue(str(p).endswith("stock-ohlc\\HPG.json") or str(p).endswith("stock-ohlc/HPG.json"))

    def test_benchmark_path_uppercases_and_namespaces_by_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = store.benchmark_ohlc_path(tmp, "vnindex")
        self.assertTrue(str(p).endswith("benchmark-ohlc\\VNINDEX.json") or str(p).endswith("benchmark-ohlc/VNINDEX.json"))

    def test_stock_and_benchmark_paths_never_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(store.stock_ohlc_path(tmp, "VNINDEX"), store.benchmark_ohlc_path(tmp, "VNINDEX"))


class WriteReadRoundTripTests(unittest.TestCase):
    def test_stock_round_trip_preserves_exact_ohlc_values(self):
        raw = _raw_ohlc(5)
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", raw, provenance={"materialized_from": "x"})
            record = store.read_stock_ohlc(tmp, "HPG")
        self.assertEqual(raw["o"], record["raw_ohlc"]["o"])
        self.assertEqual(raw["h"], record["raw_ohlc"]["h"])
        self.assertEqual(raw["l"], record["raw_ohlc"]["l"])
        self.assertEqual(raw["c"], record["raw_ohlc"]["c"])
        self.assertEqual(raw["t"], record["raw_ohlc"]["t"])
        self.assertEqual(5, record["session_count"])
        self.assertEqual("HPG", record["symbol"])
        self.assertEqual("stock", record["kind"])

    def test_benchmark_round_trip_preserves_exact_ohlc_values(self):
        raw = _raw_ohlc(5)
        with tempfile.TemporaryDirectory() as tmp:
            store.write_benchmark_ohlc(tmp, "VNINDEX", raw, provenance={"materialized_from": "x"})
            record = store.read_benchmark_ohlc(tmp, "VNINDEX")
        self.assertEqual(raw["c"], record["raw_ohlc"]["c"])
        self.assertEqual("VNINDEX", record["symbol"])
        self.assertEqual("benchmark", record["kind"])

    def test_volume_and_pagination_cursor_are_never_persisted(self):
        raw = _raw_ohlc(3)
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", raw, provenance={})
            on_disk = store.stock_ohlc_path(tmp, "HPG").read_text(encoding="utf-8")
        self.assertNotIn('"v"', on_disk)
        self.assertNotIn("nextTime", on_disk)
        self.assertNotIn("1000000", on_disk)  # a volume value, not a price/timestamp

    def test_missing_record_returns_none_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(store.read_stock_ohlc(tmp, "HPG"))
            self.assertIsNone(store.read_benchmark_ohlc(tmp, "VNINDEX"))

    def test_provenance_is_retained_verbatim(self):
        raw = _raw_ohlc(2)
        provenance = {"materialized_from": "evidence.json", "endpoint": "/price/ohlc",
                     "query_sent": {"symbol": "HPG"}}
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", raw, provenance=provenance)
            record = store.read_stock_ohlc(tmp, "HPG")
        self.assertEqual(provenance, record["provenance"])


class SanitizationFailClosedTests(unittest.TestCase):
    def test_missing_required_field_rejected(self):
        raw = _raw_ohlc(3)
        del raw["c"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(store.DnseMarketRiskEvidenceStoreError):
                store.write_stock_ohlc(tmp, "HPG", raw, provenance={})

    def test_length_mismatch_rejected(self):
        raw = _raw_ohlc(3)
        raw["c"] = raw["c"][:-1]  # one shorter than the rest
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(store.DnseMarketRiskEvidenceStoreError):
                store.write_stock_ohlc(tmp, "HPG", raw, provenance={})

    def test_non_list_field_rejected(self):
        raw = _raw_ohlc(3)
        raw["t"] = "not-a-list"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(store.DnseMarketRiskEvidenceStoreError):
                store.write_stock_ohlc(tmp, "HPG", raw, provenance={})


class ReplayIdempotencyTests(unittest.TestCase):
    def test_writing_the_same_input_twice_produces_a_byte_identical_file(self):
        raw = _raw_ohlc(4)
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", raw, provenance={"materialized_from": "x", "materialized_at": "fixed"})
            first = store.stock_ohlc_path(tmp, "HPG").read_text(encoding="utf-8")
            store.write_stock_ohlc(tmp, "HPG", raw, provenance={"materialized_from": "x", "materialized_at": "fixed"})
            second = store.stock_ohlc_path(tmp, "HPG").read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_re_ingesting_overwrites_rather_than_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", _raw_ohlc(3), provenance={})
            store.write_stock_ohlc(tmp, "HPG", _raw_ohlc(7), provenance={})
            record = store.read_stock_ohlc(tmp, "HPG")
        self.assertEqual(7, record["session_count"])  # not 3 + 7


class NoSecretsInStoreTests(unittest.TestCase):
    def test_serialized_store_file_never_contains_credential_shaped_values(self):
        raw = _raw_ohlc(3)
        provenance = {"materialized_from": "x", "endpoint": "/price/ohlc", "query_sent": {"symbol": "HPG"}}
        with tempfile.TemporaryDirectory() as tmp:
            store.write_stock_ohlc(tmp, "HPG", raw, provenance=provenance)
            on_disk = store.stock_ohlc_path(tmp, "HPG").read_text(encoding="utf-8").lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key", "cookie",
                          "api_key", "api_secret", "bearer", "password"):
            self.assertNotIn(forbidden, on_disk)


if __name__ == "__main__":
    unittest.main()
