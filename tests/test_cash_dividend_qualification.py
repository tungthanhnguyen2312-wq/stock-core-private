import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

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


def _cash_dividend_citation(ticker, event_type, res_num, decl_date, amount, evidence_id,
                             rec_date=None, ex_date=None, pay_date=None, eff_date=None,
                             rate_pct=None, status="completed", supersedes=None, note="printed p. 33"):
    citation_id = _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": res_num,
        "declaration_date": decl_date, "cash_amount": amount,
        "payment_date": pay_date, "event_status": status, "evidence_id": evidence_id
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_dividend_date": ex_date, "payment_date": pay_date, "effective_date": eff_date,
        "cash_amount": amount, "dividend_rate_pct": rate_pct, "currency": "VND", "unit": "VND_per_share",
        "share_class": "common", "event_status": status, "supersedes_citation_ids": supersedes or [],
        "evidence_id": evidence_id, "citation": {"note_number": note}, "verified_at": "2026-07-29T10:33:04Z",
        "schema_version": "1.0.0"
    }


def _write_runtime(root, citations, pdf_bytes=b"%PDF-1.4 test cash dividend evidence", filename="vnm.pdf", ticker="VNM"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker=ticker)
    (evidence_dir / filename).write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, filename, sha256, ticker=ticker)]}), encoding="utf-8")
    with (evidence_dir / "cash_dividend_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return evidence_id


def _real_vnm_dividend_runtime(root):
    pdf_bytes = b"%PDF-1.4 test VNM cash dividend evidence"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    citations = [
        _cash_dividend_citation("VNM", "cash_dividend", "13/NQ-CTS.HĐQT/2024", "2024-08-22", 1500, evidence_id,
                                rec_date="2024-09-25", pay_date="2024-10-24", rate_pct=15.0, status="completed", note="Resolution 13/NQ-CTS.HĐQT/2024"),
        _cash_dividend_citation("VNM", "cash_dividend", "15/NQ-CTS.HĐQT/2024", "2024-12-05", 500, evidence_id,
                                rec_date="2024-12-18", pay_date="2025-02-28", rate_pct=5.0, status="completed", note="Resolution 15/NQ-CTS.HĐQT/2024"),
        _cash_dividend_citation("VNM", "cash_dividend", "03/NQ-CTS.HĐQT/2024", "2024-02-27", 900, evidence_id,
                                status="superseded_amended", note="Resolution 03/NQ-CTS.HĐQT/2024"),
    ]
    _write_runtime(root, citations, pdf_bytes, filename="vnm.pdf", ticker="VNM")
    return evidence_id


class CashDividendQualificationTests(unittest.TestCase):
    def test_vnm_cash_dividend_event_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_dividend_runtime(root)
            verified = bridge.load_verified_cash_dividends(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            self.assertEqual(len(verified["events"]), 3)

            # Event 1 assertions
            ev1 = next(e for e in verified["events"] if e["resolution_number"] == "13/NQ-CTS.HĐQT/2024")
            self.assertEqual(ev1["ticker"], "VNM")
            self.assertEqual(ev1["cash_amount"], 1500.0)
            self.assertEqual(ev1["declaration_date"], "2024-08-22")
            self.assertEqual(ev1["record_date"], "2024-09-25")
            self.assertEqual(ev1["payment_date"], "2024-10-24")
            self.assertIsNone(ev1["ex_dividend_date"])  # unasserted date remains null
            self.assertIsNone(ev1["effective_date"])
            self.assertEqual(ev1["currency"], "VND")
            self.assertEqual(ev1["share_class"], "common")

            # Event 2 assertions
            ev2 = next(e for e in verified["events"] if e["resolution_number"] == "15/NQ-CTS.HĐQT/2024")
            self.assertEqual(ev2["cash_amount"], 500.0)
            self.assertEqual(ev2["declaration_date"], "2024-12-05")
            self.assertEqual(ev2["payment_date"], "2025-02-28")

            # Event 3 amendment / status assertion
            ev3 = next(e for e in verified["events"] if e["resolution_number"] == "03/NQ-CTS.HĐQT/2024")
            self.assertEqual(ev3["event_status"], "superseded_amended")

    def test_cash_dividend_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_dividend_runtime(root)
            (root / "data" / "official-evidence" / "vnm.pdf").write_bytes(b"tampered pdf content")
            verified = bridge.load_verified_cash_dividends(root)
            self.assertEqual(verified["events"], [])
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_conflicting_cash_dividend_citations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            evidence_id = _evidence_id(sha256, ticker="VNM")
            cit1 = _cash_dividend_citation("VNM", "cash_dividend", "13/NQ-CTS.HĐQT/2024", "2024-08-22", 1500, evidence_id)
            # Conflicting record with same key but different payload/fields
            cit2 = dict(cit1)
            cit2["payment_date"] = "2099-01-01"
            cit2["citation_id"] = "cit_conflict"
            _write_runtime(root, [cit1, cit2], pdf_bytes, filename="vnm.pdf", ticker="VNM")
            verified = bridge.load_verified_cash_dividends(root)
            self.assertEqual(verified["events"], [])
            self.assertTrue(any(r["reason"] == "conflicting_citations" for r in verified["rejected"]))

    def test_superseded_amendment_linkage_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            evidence_id = _evidence_id(sha256, ticker="VNM")
            cit_orig = _cash_dividend_citation("VNM", "cash_dividend", "13/NQ-CTS.HĐQT/2024", "2024-08-22", 1500, evidence_id, status="amended")
            cit_new = _cash_dividend_citation("VNM", "cash_dividend", "13/NQ-CTS.HĐQT/2024", "2024-08-22", 1500, evidence_id, pay_date="2024-10-24", status="completed", supersedes=[cit_orig["citation_id"]])
            _write_runtime(root, [cit_orig, cit_new], pdf_bytes, filename="vnm.pdf", ticker="VNM")
            verified = bridge.load_verified_cash_dividends(root)
            self.assertEqual(len(verified["events"]), 1)
            self.assertEqual(verified["events"][0]["payment_date"], "2024-10-24")

    def test_determinism_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_dividend_runtime(root)
            run1 = bridge.load_verified_cash_dividends(root)
            run2 = bridge.load_verified_cash_dividends(root)
            self.assertEqual(run1, run2)

    def test_zero_adjustment_factors_or_returns_produced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_dividend_runtime(root)
            verified = bridge.load_verified_cash_dividends(root)
            for ev in verified["events"]:
                self.assertNotIn("adjustment_factor", ev)
                self.assertNotIn("adjusted_price", ev)
                self.assertNotIn("adjusted_return", ev)


if __name__ == "__main__":
    unittest.main()
