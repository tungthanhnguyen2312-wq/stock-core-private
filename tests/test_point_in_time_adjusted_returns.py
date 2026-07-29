import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import point_in_time_adjusted_returns as pit_ret
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
        "verified_at": "2026-07-29T11:23:53Z", "schema_version": "1.0.0"
    }


def _write_ret_runtime(root, non_cash_citations, price_rows, pdf_bytes=b"%PDF-1.4 test ret"):
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

    price_cits = []
    db_path = root / "vn_stock.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")

    for pdate, pval in price_rows:
        cit_id = _hash({"ticker": "VNM", "trading_date": pdate, "price_field": "close", "value": float(pval), "provider": "SSI"})
        price_cits.append({
            "citation_id": cit_id, "ticker": "VNM", "trading_date": pdate,
            "price_field": "close", "value": float(pval), "currency": "VND",
            "adjustment_status": "raw_as_quoted_no_adjustment_applied", "provider": "SSI", "schema_version": "1.0.0"
        })
        conn.execute("INSERT INTO ohlcv VALUES ('VNM', ?, ?, ?, ?, ?, 1000000.0, 'SSI')", (pdate, float(pval), float(pval)+500, float(pval)-500, float(pval)))

    conn.commit()
    conn.close()

    with (evidence_dir / "market_price_citations.jsonl").open("w", encoding="utf-8") as fh:
        for pc in price_cits:
            fh.write(json.dumps(pc, ensure_ascii=False) + "\n")

    return evidence_id


class PointInTimeAdjustedReturnsTests(unittest.TestCase):
    def test_full_pit_adjusted_returns_derivation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test return derivation"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            non_cash_cits = [
                _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")
            ]
            # 3 price rows: 2021-07-01, 2021-07-02, 2021-07-05
            price_rows = [
                ("2021-07-01", 100000.0),
                ("2021-07-02", 102000.0),
                ("2021-07-05", 101000.0),
            ]

            _write_ret_runtime(root, non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            res = pit_ret.build_point_in_time_adjusted_returns(root, ticker="VNM")
            self.assertEqual(res["status"], "available")
            self.assertEqual(res["return_type"], "simple_price_return")
            self.assertEqual(res["total_row_count"], 3)
            self.assertEqual(res["valid_return_count"], 2)
            self.assertEqual(res["unavailable_return_count"], 1)

            series = res["return_series"]

            # First row behavior (row 0)
            row0 = series[0]
            self.assertEqual(row0["trading_date"], "2021-07-01")
            self.assertIsNone(row0["return_value"])
            self.assertIsNone(row0["previous_trading_date"])
            self.assertEqual(row0["unavailable_reason"], "no_previous_eligible_session")

            # Second row behavior (row 1): (102000 / 100000) - 1 = 0.02
            row1 = series[1]
            self.assertEqual(row1["trading_date"], "2021-07-02")
            self.assertEqual(row1["previous_trading_date"], "2021-07-01")
            self.assertAlmostEqual(row1["return_value"], 0.02, places=6)
            self.assertIsNone(row1["unavailable_reason"])

            # Third row behavior (row 2): (101000 / 102000) - 1 = -0.0098039...
            row2 = series[2]
            self.assertEqual(row2["trading_date"], "2021-07-05")
            self.assertEqual(row2["previous_trading_date"], "2021-07-02")
            self.assertAlmostEqual(row2["return_value"], (101000.0 / 102000.0) - 1.0, places=6)

    def test_byte_identical_repeated_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test return determinism"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")]
            price_rows = [("2021-07-01", 100000.0), ("2021-07-02", 102000.0)]
            _write_ret_runtime(root, non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            run1 = pit_ret.build_point_in_time_adjusted_returns(root, ticker="VNM")
            run2 = pit_ret.build_point_in_time_adjusted_returns(root, ticker="VNM")
            self.assertEqual(run1, run2)

    def test_zero_benchmark_beta_correlation_backtest_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test return safety"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")]
            price_rows = [("2021-07-01", 100000.0), ("2021-07-02", 102000.0)]
            _write_ret_runtime(root, non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            res = pit_ret.build_point_in_time_adjusted_returns(root, ticker="VNM")
            self.assertNotIn("benchmark_returns", res)
            self.assertNotIn("beta", res)
            self.assertNotIn("correlation", res)
            self.assertNotIn("backtest_metrics", res)
            for r in res["return_series"]:
                self.assertNotIn("benchmark_return", r)
                self.assertNotIn("beta", r)
                self.assertNotIn("correlation", r)


if __name__ == "__main__":
    unittest.main()
