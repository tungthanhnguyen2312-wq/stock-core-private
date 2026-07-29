import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import corporate_action_factors as factors
import corporate_action_ledger as ledger
import point_in_time_adjusted_prices as pit
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


def _cash_citation(ticker, res_num, decl_date, cash_amt, pay_date, evidence_id, rec_date=None, ex_date=None, status="completed"):
    citation_id = _hash({
        "ticker": ticker, "event_type": "cash_dividend", "resolution_number": res_num,
        "declaration_date": decl_date, "cash_amount": cash_amt, "payment_date": pay_date,
        "event_status": status, "evidence_id": evidence_id
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": "cash_dividend",
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_dividend_date": ex_date, "payment_date": pay_date, "cash_amount": cash_amt,
        "currency": "VND", "event_status": status, "supersedes_citation_ids": [],
        "evidence_id": evidence_id, "citation": {"note_number": "Annual Report p. 33"},
        "verified_at": "2026-07-29T11:19:55Z", "schema_version": "1.0.0"
    }


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
        "verified_at": "2026-07-29T11:19:55Z", "schema_version": "1.0.0"
    }


def _write_pit_runtime(root, cash_citations, non_cash_citations, price_rows, pdf_bytes=b"%PDF-1.4 test pit"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    (evidence_dir / "vnm.pdf").write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, "vnm.pdf", sha256)]}), encoding="utf-8")

    with (evidence_dir / "cash_dividend_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in cash_citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

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


class PointInTimeAdjustedPricesTests(unittest.TestCase):
    def test_full_pit_adjusted_prices_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test pit construction"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            non_cash_cits = [
                _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, rec_date="2021-07-20", ex_date="2021-07-19"),
                _non_cash_citation("VNM", "bonus_share", "08/NQ-CTS.HĐQT/2022", "2022-05-18", 1, 5, ev_id, rec_date="2022-06-22", ex_date="2022-06-21"),
            ]
            cash_cits = [
                _cash_citation("VNM", "13/NQ-CTS.HĐQT/2024", "2024-03-18", 1500, "2024-04-26", ev_id, rec_date="2024-04-12", ex_date="2024-04-11")
            ]
            price_rows = [
                ("2021-07-01", 100000.0), # Before 2021-07-19 stock div (1:10), 2022 bonus (1:5), 2024 cash (1500)
                ("2021-08-01", 100000.0), # After 2021 stock div, before 2022 bonus & 2024 cash
                ("2024-04-10", 67500.0),  # Pre-cash dividend reference session
                ("2024-04-12", 66000.0),  # After 2024-04-11 cash dividend
            ]

            _write_pit_runtime(root, cash_cits, non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            res = pit.build_point_in_time_adjusted_prices(root, ticker="VNM")
            self.assertEqual(res["status"], "available")
            self.assertEqual(res["raw_row_count"], 4)
            self.assertEqual(res["adjusted_row_count"], 4)

            series = {r["trading_date"]: r for r in res["adjusted_series"]}

            # Anchor Invariance: latest date (2024-04-12) adjusted close == raw close
            r_latest = series["2024-04-12"]
            self.assertEqual(r_latest["adjusted_close"], r_latest["raw_close"])
            self.assertEqual(r_latest["cumulative_multiplier"], 1.0)

            # Pre-2024-04-11 date receives cash dividend multiplier (66000 / 67500)
            r_cash_pre = series["2024-04-10"]
            self.assertAlmostEqual(r_cash_pre["cumulative_multiplier"], 66000.0 / 67500.0, places=6)

            # Pre-2021-07-19 date receives cumulative multiplier (10/11 * 5/6 * 66000/67500)
            r_old = series["2021-07-01"]
            expected_mult = (10.0 / 11.0) * (5.0 / 6.0) * (66000.0 / 67500.0)
            self.assertAlmostEqual(r_old["cumulative_multiplier"], expected_mult, places=6)
            self.assertAlmostEqual(r_old["adjusted_close"], 100000.0 * expected_mult, places=4)

    def test_knowledge_cutoff_vintage_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test pit cutoff"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            non_cash_cits = [
                _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, rec_date="2021-07-20", ex_date="2021-07-19"),
                _non_cash_citation("VNM", "bonus_share", "08/NQ-CTS.HĐQT/2022", "2022-05-18", 1, 5, ev_id, rec_date="2022-06-22", ex_date="2022-06-21"),
            ]
            cash_cits = [
                _cash_citation("VNM", "13/NQ-CTS.HĐQT/2024", "2024-03-18", 1500, "2024-04-26", ev_id, rec_date="2024-04-12", ex_date="2024-04-11")
            ]
            price_rows = [("2021-07-01", 100000.0), ("2024-04-10", 67500.0)]

            _write_pit_runtime(root, cash_cits, non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            # Vintage 1: cutoff before 2022 events -> includes only 2021 stock dividend
            v1 = pit.build_point_in_time_adjusted_prices(root, ticker="VNM", knowledge_cutoff="2021-12-31")
            summary1 = v1["applied_factors_summary"]
            self.assertEqual(summary1["total_eligible_factors"], 1)
            self.assertEqual(summary1["stock_dividend_factors"], 1)
            self.assertEqual(summary1["bonus_share_factors"], 0)
            self.assertEqual(summary1["cash_dividend_factors"], 0)

            # Vintage 2: cutoff after all events -> includes 2021 stock div, 2022 bonus, 2024 cash div
            v2 = pit.build_point_in_time_adjusted_prices(root, ticker="VNM", knowledge_cutoff="2025-01-01")
            summary2 = v2["applied_factors_summary"]
            self.assertEqual(summary2["total_eligible_factors"], 3)
            self.assertEqual(summary2["stock_dividend_factors"], 1)
            self.assertEqual(summary2["bonus_share_factors"], 1)
            self.assertEqual(summary2["cash_dividend_factors"], 1)

    def test_byte_identical_repeated_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test pit determinism"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")]
            price_rows = [("2021-07-01", 100000.0)]
            _write_pit_runtime(root, [], non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            run1 = pit.build_point_in_time_adjusted_prices(root, ticker="VNM")
            run2 = pit.build_point_in_time_adjusted_prices(root, ticker="VNM")
            self.assertEqual(run1, run2)

    def test_zero_adjusted_returns_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test pit safety"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, ex_date="2021-07-19")]
            price_rows = [("2021-07-01", 100000.0)]
            _write_pit_runtime(root, [], non_cash_cits, price_rows, pdf_bytes=pdf_bytes)

            res = pit.build_point_in_time_adjusted_prices(root, ticker="VNM")
            for r in res["adjusted_series"]:
                self.assertNotIn("adjusted_return", r)
                self.assertNotIn("return_series", r)


if __name__ == "__main__":
    unittest.main()
