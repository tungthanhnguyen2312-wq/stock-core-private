import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import point_in_time_benchmark as pit_bmk
import semantic_evidence_bridge as bridge


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence_id(sha256, ticker="VNM"):
    return _hash({"authority_domain": "vinamilk.com.vn", "source_url": "u", "sha256": sha256, "ticker": ticker,
        "reporting_period": "2024", "evidence_type": "audited_consolidated_financial_statements"})


def _evidence_record(evidence_id, filename, sha256, ticker="VNM"):
    return {"evidence_id": evidence_id, "authority": "KPMG Vietnam", "authority_domain": "vinamilk.com.vn", "ticker": ticker,
        "issuer": "Vietnam Dairy Products Joint Stock Company", "evidence_type": "audited_consolidated_financial_statements",
        "source_url": "https://vinamilk.com.vn/" + filename, "document_title": "Vinamilk 2024 Annual Report",
        "reporting_period": "2024", "publication_date": "2025-02-28", "retrieved_at": "2026-07-28T13:42:50Z",
        "content_type": "application/pdf", "language": "en", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "official_ir_portal", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _non_cash_citation(ticker, event_type, res_num, decl_date, num, den, evidence_id,
                        rec_date=None, ex_date=None, dist_date=None, funding="undistributed_earnings",
                        status="completed"):
    citation_id = _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": res_num,
        "declaration_date": decl_date, "ratio_numerator": num, "ratio_denominator": den,
        "ex_rights_date": ex_date, "event_status": status, "evidence_id": evidence_id
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_rights_date": ex_date, "distribution_date": dist_date, "ratio_numerator": num,
        "ratio_denominator": den, "funding_source": funding, "event_status": status,
        "supersedes_citation_ids": [], "evidence_id": evidence_id,
        "citation": {"note_number": "Annual Report p. 33"},
        "verified_at": "2026-07-29T11:29:51Z", "schema_version": "1.0.0"
    }


def _write_bmk_runtime(root, non_cash_citations, vnm_prices, bmk_prices, pdf_bytes=b"%PDF-1.4 test bmk"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    (evidence_dir / "vnm.pdf").write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, "vnm.pdf", sha256)]}), encoding="utf-8")

    with (evidence_dir / "cash_dividend_citations.jsonl").open("w", encoding="utf-8") as fh:
        pass

    with (evidence_dir / "non_cash_event_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in non_cash_citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    vnm_cits = []
    db_path = root / "vn_stock.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")

    for pdate, pval in vnm_prices:
        cit_id = _hash({"ticker": "VNM", "trading_date": pdate, "price_field": "close", "value": float(pval), "provider": "SSI"})
        vnm_cits.append({
            "citation_id": cit_id, "ticker": "VNM", "trading_date": pdate,
            "price_field": "close", "value": float(pval), "currency": "VND",
            "adjustment_status": "raw_as_quoted_no_adjustment_applied", "provider": "SSI", "schema_version": "1.0.0"
        })
        conn.execute("INSERT INTO ohlcv VALUES ('VNM', ?, ?, ?, ?, ?, 1000000.0, 'SSI')", (pdate, float(pval), float(pval)+500, float(pval)-500, float(pval)))

    for pdate, pval in bmk_prices:
        conn.execute("INSERT INTO ohlcv VALUES ('VNINDEX', ?, ?, ?, ?, ?, 1000000.0, 'SSI')", (pdate, float(pval), float(pval)+500, float(pval)-500, float(pval)))

    conn.commit()
    conn.close()

    with (evidence_dir / "market_price_citations.jsonl").open("w", encoding="utf-8") as fh:
        for pc in vnm_cits:
            fh.write(json.dumps(pc, ensure_ascii=False) + "\n")

    return evidence_id


class PointInTimeBenchmarkTests(unittest.TestCase):
    def test_benchmark_returns_derivation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test benchmark"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            bmk_prices = [("2021-07-01", 1400.0), ("2021-07-02", 1420.0)]
            _write_bmk_runtime(root, [], [], bmk_prices, pdf_bytes=pdf_bytes)

            res = pit_bmk.build_point_in_time_benchmark_returns(root, symbol="VNINDEX")
            self.assertEqual(res["status"], "available")
            self.assertEqual(res["symbol"], "VNINDEX")
            self.assertEqual(res["benchmark_row_count"], 2)
            self.assertEqual(res["valid_return_count"], 1)

            series = res["benchmark_series"]
            self.assertIsNone(series[0]["return_value"])
            self.assertAlmostEqual(series[1]["return_value"], (1420.0 / 1400.0) - 1.0, places=6)

    def test_vnm_and_benchmark_exact_date_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test alignment"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")]
            vnm_prices = [("2021-07-01", 100000.0), ("2021-07-02", 102000.0), ("2021-07-05", 101000.0)]
            bmk_prices = [("2021-07-01", 1400.0), ("2021-07-02", 1420.0), ("2021-07-06", 1410.0)] # 2021-07-05 unmatched in bmk, 2021-07-06 unmatched in VNM

            _write_bmk_runtime(root, non_cash_cits, vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            align_res = pit_bmk.align_vnm_and_benchmark_returns(root, ticker="VNM", benchmark_symbol="VNINDEX")
            self.assertEqual(align_res["status"], "available")
            self.assertEqual(align_res["aligned_pair_count"], 2) # 2021-07-01 and 2021-07-02 matched
            self.assertEqual(align_res["unmatched_vnm_dates_count"], 1) # 2021-07-05
            self.assertEqual(align_res["unmatched_benchmark_dates_count"], 1) # 2021-07-06

            pairs = align_res["aligned_pairs"]
            # Row 0: 2021-07-01 null returns for first session
            p0 = pairs[0]
            self.assertEqual(p0["trading_date"], "2021-07-01")
            self.assertIsNone(p0["vnm_return_value"])
            self.assertIsNone(p0["benchmark_return_value"])

            # Row 1: 2021-07-02 matched valid returns
            p1 = pairs[1]
            self.assertEqual(p1["trading_date"], "2021-07-02")
            self.assertAlmostEqual(p1["vnm_return_value"], 0.02, places=6)
            self.assertAlmostEqual(p1["benchmark_return_value"], (1420.0 / 1400.0) - 1.0, places=6)

    def test_byte_identical_repeated_alignment_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test alignment determinism"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            vnm_prices = [("2021-07-01", 100000.0), ("2021-07-02", 102000.0)]
            bmk_prices = [("2021-07-01", 1400.0), ("2021-07-02", 1420.0)]
            _write_bmk_runtime(root, [], vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            run1 = pit_bmk.align_vnm_and_benchmark_returns(root, ticker="VNM", benchmark_symbol="VNINDEX")
            run2 = pit_bmk.align_vnm_and_benchmark_returns(root, ticker="VNM", benchmark_symbol="VNINDEX")
            self.assertEqual(run1, run2)

    def test_zero_beta_correlation_backtest_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test benchmark safety"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            vnm_prices = [("2021-07-01", 100000.0), ("2021-07-02", 102000.0)]
            bmk_prices = [("2021-07-01", 1400.0), ("2021-07-02", 1420.0)]
            _write_bmk_runtime(root, [], vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            align_res = pit_bmk.align_vnm_and_benchmark_returns(root, ticker="VNM", benchmark_symbol="VNINDEX")
            self.assertNotIn("beta", align_res)
            self.assertNotIn("correlation", align_res)
            self.assertNotIn("backtest", align_res)
            for p in align_res["aligned_pairs"]:
                self.assertNotIn("beta", p)
                self.assertNotIn("correlation", p)


if __name__ == "__main__":
    unittest.main()
