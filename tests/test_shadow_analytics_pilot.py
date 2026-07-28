from __future__ import annotations

import tempfile
from decimal import Decimal
import unittest
from pathlib import Path

import shadow_analytics_pilot as pilot


class ScopeQualificationTests(unittest.TestCase):
    def _record(self, **overrides):
        record = {
            "canonical_metric": "revenue",
            "value": 100,
            "period_identity": {"period": "2024", "period_type": "annual"},
            "statement_scope": "consolidated",
            "currency": "VND",
            "unit_scale": 1,
            "quality_state": "available",
            "derivation_status": "direct",
            "observation_ids": ["observation-1"],
            "evidence": {"citation_id": "citation-1", "evidence_id": "evidence-1"},
            "source": "financial_observation_store",
            "source_field": "net_sales",
            "source_statement": "income_statement",
        }
        record.update(overrides)
        return record

    def test_scope_identity_requires_explicit_scope_and_lineage(self):
        qualified, rejected = pilot.qualify_fy2024_scoped_records([self._record()], "HPG")
        self.assertEqual(qualified[0]["statement_scope"], "consolidated")
        self.assertEqual(qualified[0]["observation_id"], "observation-1")
        self.assertEqual(qualified[0]["citation_id"], "citation-1")
        self.assertFalse(rejected)

    def test_conflicting_scope_fails_closed(self):
        separate = self._record(statement_scope="separate", observation_ids=["observation-2"], evidence={"citation_id": "citation-2", "evidence_id": "evidence-2"})
        with self.assertRaises(pilot.ShadowPilotError):
            pilot.qualify_fy2024_scoped_records([self._record(), separate], "HPG")

    def test_missing_scope_or_citation_cannot_promote(self):
        missing_scope = self._record(statement_scope="unknown")
        missing_citation = self._record(canonical_metric="gross_profit", evidence={"citation_id": "", "evidence_id": "evidence-2"})
        qualified, rejected = pilot.qualify_fy2024_scoped_records([missing_scope, missing_citation], "HPG")
        self.assertEqual(qualified, [])
        self.assertEqual(len(rejected), 2)
        self.assertIn("scope", rejected[0]["reason"])
        self.assertIn("citation_lineage", rejected[1]["reason"])

    def test_partial_ticker_availability_is_explicit(self):
        hpg, _ = pilot.qualify_fy2024_scoped_records([self._record()], "HPG")
        vcb, _ = pilot.qualify_fy2024_scoped_records([self._record(canonical_metric="total_assets")], "VCB")
        vnm, rejected = pilot.qualify_fy2024_scoped_records([self._record(statement_scope=None)], "VNM")
        self.assertEqual({item["ticker"] for item in hpg + vcb}, {"HPG", "VCB"})
        self.assertEqual(vnm, [])
        self.assertTrue(rejected)


    def test_qualified_bridge_records_round_trip_through_explicit_schema(self):
        hpg, _ = pilot.qualify_fy2024_scoped_records([self._record(value=138855112131387)], "HPG")
        vnm, _ = pilot.qualify_fy2024_scoped_records([self._record(value=None, observation_ids=["observation-2"], evidence={"citation_id": "citation-2", "evidence_id": "evidence-2"})], "VNM")
        vcb, _ = pilot.qualify_fy2024_scoped_records([self._record(canonical_metric="provision_for_credit_losses", value=-123, observation_ids=["observation-3"], evidence={"citation_id": "citation-3", "evidence_id": "evidence-3"})], "VCB")
        financial = hpg + vnm + vcb
        ohlcv = [
            {"ticker": "HPG", "date": "2024-12-31", "open": 8060.000000000001, "high": 8060.000000000001, "low": 8060.000000000001, "close": 8060.000000000001, "volume": 1, "source": "test"},
            {"ticker": "VNM", "date": "2024-12-31", "open": None, "high": None, "low": None, "close": None, "volume": None, "source": "test"},
            {"ticker": "VCB", "date": "2024-12-31", "open": -1.0, "high": -1.0, "low": -1.0, "close": -1.0, "volume": 2, "source": "test"},
        ]
        duckdb = pilot.require_duckdb()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); con = duckdb.connect(":memory:")
            try:
                pilot._write_partitioned(con, financial, root, "financial_metrics")
                pilot._write_partitioned(con, ohlcv, root, "ohlcv")
                financial_shadow = pilot._read_parquet(con, root, "financial_metrics")
                ohlcv_shadow = pilot._read_parquet(con, root, "ohlcv")
            finally:
                con.close()
        financial_fields = tuple(name for name, _ in pilot.PARQUET_SCHEMAS["financial_metrics"])
        ohlcv_fields = tuple(name for name, _ in pilot.PARQUET_SCHEMAS["ohlcv"])
        self.assertEqual(pilot._assert_parity("financial", financial, financial_shadow, financial_fields)["rows"], 3)
        self.assertEqual(pilot._assert_parity("ohlcv", ohlcv, ohlcv_shadow, ohlcv_fields)["rows"], 3)
        self.assertEqual({row["entity_type"] for row in financial_shadow}, {"corporate", "bank"})
        self.assertEqual(next(row for row in financial_shadow if row["ticker"] == "VCB")["canonical_metric"], "provision_for_credit_losses")


class ShadowPilotContractTests(unittest.TestCase):
    def test_rejects_production_or_nonempty_lake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prod = root / "runtime"; prod.mkdir()
            with self.assertRaises(pilot.ShadowPilotError):
                pilot.require_isolated_lake(prod, prod)
            lake = root / "lake"; lake.mkdir(); (lake / "old").write_text("x")
            with self.assertRaises(pilot.ShadowPilotError):
                pilot.require_isolated_lake(lake, prod)

    def test_preflight_only_evidence_is_safe_and_unexpected_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); evidence = root / "evidence"; evidence.mkdir()
            (evidence / "01_preflight.json").write_text("{}", encoding="utf-8")
            self.assertFalse({path.name for path in evidence.iterdir()} - {"01_preflight.json"})
            (evidence / "unexpected").write_text("x", encoding="utf-8")
            self.assertTrue({path.name for path in evidence.iterdir()} - {"01_preflight.json"})
    def test_bank_corporate_metric_separation_fails_closed(self):
        pilot.require_supported_metric("HPG", "total_debt")
        pilot.require_supported_metric("VCB", "total_assets")
        with self.assertRaises(pilot.ShadowPilotError):
            pilot.require_supported_metric("VCB", "total_debt")
        with self.assertRaises(pilot.ShadowPilotError):
            pilot.require_supported_metric("VCB", "ev_ebitda")

    def test_semantic_fingerprint_is_deterministic_and_null_preserving(self):
        first = [{"ticker": "HPG", "value": None}, {"ticker": "VCB", "value": 1}]
        self.assertEqual(pilot.semantic_fingerprint(first), pilot.semantic_fingerprint(list(reversed(first))))
        self.assertNotEqual(pilot.semantic_fingerprint(first), pilot.semantic_fingerprint([{ "ticker":"HPG", "value":0 }, {"ticker":"VCB", "value":1}]))

    def test_parity_rejects_missing_row(self):
        with self.assertRaises(pilot.ShadowPilotError):
            pilot._assert_parity("synthetic", [{"ticker":"HPG", "value":None}], [], ("ticker","value"))

    def test_partitioning_creates_one_isolated_file_per_ticker(self):
        duckdb = pilot.require_duckdb()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); con = duckdb.connect(":memory:")
            try:
                rows = [{"ticker": ticker, "date": "2024-12-31", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1, "source": "test"} for ticker in pilot.TICKERS]
                files = pilot._write_partitioned(con, rows, root, "ohlcv")
            finally:
                con.close()
            self.assertEqual([p.parent.name for p in files], ["ticker=HPG", "ticker=VNM", "ticker=VCB"])
            self.assertTrue(all(p.is_file() for p in files))


class NumericPrecisionContractTests(unittest.TestCase):
    def _ohlcv_rows(self):
        return [
            {"ticker": "HPG", "date": "2024-12-31", "open": 0.1, "high": 8060.000000000001, "low": -1.25, "close": None, "volume": 0, "source": "test"},
            {"ticker": "VNM", "date": "2024-12-31", "open": 1.0, "high": 2.0, "low": 1.0, "close": 2.0, "volume": 922337203685477, "source": "test"},
            {"ticker": "VCB", "date": "2024-12-31", "open": None, "high": None, "low": None, "close": None, "volume": None, "source": "test"},
        ]

    def _financial_row(self, ticker="HPG", value=138855112131387):
        return {"ticker": ticker, "entity_type": pilot.ENTITY_TYPES[ticker], "canonical_metric": "revenue",
                "value": value, "period": "2024", "period_end": None, "statement_scope": "consolidated",
                "currency": "VND", "unit_scale": 1, "source": "test", "observation_id": "obs",
                "citation_id": "cit", "evidence_id": "ev", "provenance_json": "{}"}

    def test_ohlcv_double_and_bigint_round_trip_without_tolerance(self):
        duckdb = pilot.require_duckdb()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); con = duckdb.connect(":memory:")
            try:
                source = self._ohlcv_rows()
                pilot._write_partitioned(con, source, root, "ohlcv")
                shadow = pilot._read_parquet(con, root, "ohlcv")
            finally:
                con.close()
        fields = ("ticker", "date", "open", "high", "low", "close", "volume", "source")
        self.assertEqual(pilot._assert_parity("ohlcv", source, shadow, fields)["rows"], 3)
        self.assertEqual(shadow[0]["high"], 8060.000000000001)
        self.assertEqual(shadow[0]["low"], -1.25)

    def test_large_financial_integer_round_trip_and_null_preservation(self):
        duckdb = pilot.require_duckdb()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); con = duckdb.connect(":memory:")
            try:
                source = [self._financial_row("HPG"), self._financial_row("VNM", 0), self._financial_row("VCB", None)]
                pilot._write_partitioned(con, source, root, "financial_metrics")
                shadow = pilot._read_parquet(con, root, "financial_metrics")
            finally:
                con.close()
        fields = tuple(name for name, _ in pilot.PARQUET_SCHEMAS["financial_metrics"])
        self.assertEqual(pilot._assert_parity("financial", source, shadow, fields)["rows"], 3)
        self.assertEqual(shadow[0]["value"], 138855112131387)

    def test_nonexact_numeric_sources_fail_closed(self):
        with self.assertRaises(pilot.ShadowPilotError):
            pilot._validate_numeric_contract("financial_metrics", [self._financial_row(value=Decimal("1.01"))])
        bad = self._ohlcv_rows(); bad[0]["volume"] = 1.5
        with self.assertRaises(pilot.ShadowPilotError):
            pilot._validate_numeric_contract("ohlcv", bad)

    def test_fingerprint_distinguishes_numeric_contract_boundaries(self):
        exact = [{"ticker": "HPG", "price": 8060.000000000001, "value": None}]
        rounded = [{"ticker": "HPG", "price": 8060.0, "value": None}]
        self.assertNotEqual(pilot.semantic_fingerprint(exact), pilot.semantic_fingerprint(rounded))


if __name__ == "__main__":
    unittest.main()
