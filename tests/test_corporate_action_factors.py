import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import corporate_action_factors as factors
import corporate_action_ledger as ledger
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
        "verified_at": "2026-07-29T11:07:39Z", "schema_version": "1.0.0"
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
        "verified_at": "2026-07-29T11:07:39Z", "schema_version": "1.0.0"
    }


def _write_factor_runtime(root, cash_citations, non_cash_citations, pdf_bytes=b"%PDF-1.4 test factors"):
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

    return evidence_id


class CorporateActionFactorTests(unittest.TestCase):
    def test_stock_dividend_and_bonus_share_factor_derivation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test factor derivation"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)

            non_cash_cits = [
                _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id, rec_date="2021-07-20", ex_date="2021-07-19"),
                _non_cash_citation("VNM", "bonus_share", "08/NQ-CTS.HĐQT/2022", "2022-05-18", 1, 5, ev_id, rec_date="2022-06-22", ex_date="2022-06-21"),
            ]
            cash_cits = [
                _cash_citation("VNM", "13/NQ-CTS.HĐQT/2024", "2024-03-18", 1500, "2024-04-26", ev_id)
            ]

            _write_factor_runtime(root, cash_cits, non_cash_cits, pdf_bytes=pdf_bytes)

            res = factors.derive_non_cash_adjustment_factors(root, ticker="VNM")
            self.assertEqual(res["status"], "available")
            self.assertEqual(len(res["individual_factors"]), 2)

            counts = res["factor_counts"]
            self.assertEqual(counts["stock_dividend"], 1)
            self.assertEqual(counts["bonus_share"], 1)
            self.assertEqual(counts["cash_dividend_unavailable"], 1)

            # Stock Dividend Factor assertions (1:10 ratio)
            f_sd = next(f for f in res["individual_factors"] if f["event_type"] == "stock_dividend")
            self.assertEqual(f_sd["share_quantity_multiplier"], 1.1)
            self.assertAlmostEqual(f_sd["theoretical_price_multiplier"], 10.0 / 11.0, places=9)

            # Bonus Share Factor assertions (1:5 ratio)
            f_bs = next(f for f in res["individual_factors"] if f["event_type"] == "bonus_share")
            self.assertEqual(f_bs["share_quantity_multiplier"], 1.2)
            self.assertAlmostEqual(f_bs["theoretical_price_multiplier"], 5.0 / 6.0, places=9)

            # Cumulative Factor assertions (1.1 * 1.2 = 1.32)
            cum = res["cumulative_factor"]
            self.assertIsNotNone(cum)
            self.assertAlmostEqual(cum["cumulative_share_quantity_multiplier"], 1.32, places=6)
            self.assertAlmostEqual(cum["cumulative_theoretical_price_multiplier"], (10.0 / 11.0) * (5.0 / 6.0), places=6)

    def test_cash_dividend_returns_explicit_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test cash factor unavailable"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            cash_cits = [_cash_citation("VNM", "13/NQ-CTS.HĐQT/2024", "2024-03-18", 1500, "2024-04-26", ev_id)]
            _write_factor_runtime(root, cash_cits, [], pdf_bytes=pdf_bytes)

            res = factors.derive_non_cash_adjustment_factors(root, ticker="VNM")
            self.assertEqual(res["factor_counts"]["cash_dividend_unavailable"], 1)
            unsupported = res["unsupported_entries"]
            self.assertTrue(any(u["reason"] == "cash_dividend_price_basis_not_qualified" for u in unsupported))

    def test_byte_identical_repeated_factor_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test factor determinism"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id)]
            _write_factor_runtime(root, [], non_cash_cits, pdf_bytes=pdf_bytes)

            run1 = factors.derive_non_cash_adjustment_factors(root, ticker="VNM")
            run2 = factors.derive_non_cash_adjustment_factors(root, ticker="VNM")
            self.assertEqual(run1, run2)

    def test_zero_adjusted_prices_or_returns_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test factor safety"
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            ev_id = _evidence_id(sha256)
            non_cash_cits = [_non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, ev_id)]
            _write_factor_runtime(root, [], non_cash_cits, pdf_bytes=pdf_bytes)

            res = factors.derive_non_cash_adjustment_factors(root, ticker="VNM")
            for f in res["individual_factors"]:
                self.assertNotIn("adjusted_price", f)
                self.assertNotIn("adjusted_return", f)
                self.assertNotIn("price_series", f)


if __name__ == "__main__":
    unittest.main()
