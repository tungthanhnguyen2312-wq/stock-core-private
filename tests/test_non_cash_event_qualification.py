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


def _non_cash_citation(ticker, event_type, res_num, decl_date, num, den, evidence_id,
                        rec_date=None, ex_date=None, dist_date=None, eff_date=None,
                        funding="undistributed_earnings", frac_treatment=None,
                        status="completed", supersedes=None, note="printed p. 33"):
    citation_id = _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": res_num,
        "declaration_date": decl_date, "ratio_numerator": num, "ratio_denominator": den,
        "ex_rights_date": ex_date, "event_status": status, "evidence_id": evidence_id
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_rights_date": ex_date, "distribution_date": dist_date, "effective_date": eff_date,
        "ratio_numerator": num, "ratio_denominator": den, "funding_source": funding,
        "share_class": "common", "fractional_share_treatment": frac_treatment,
        "event_status": status, "supersedes_citation_ids": supersedes or [],
        "evidence_id": evidence_id, "citation": {"note_number": note}, "verified_at": "2026-07-29T10:54:45Z",
        "schema_version": "1.0.0"
    }


def _write_runtime(root, citations, pdf_bytes=b"%PDF-1.4 test non cash event evidence", filename="vnm.pdf", ticker="VNM"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker=ticker)
    (evidence_dir / filename).write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, filename, sha256, ticker=ticker)]}), encoding="utf-8")
    with (evidence_dir / "non_cash_event_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return evidence_id


def _real_vnm_non_cash_runtime(root):
    pdf_bytes = b"%PDF-1.4 test VNM non-cash event evidence"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    citations = [
        # Event 1: Stock Dividend (10:1 ratio, 10%)
        _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, evidence_id,
                           rec_date="2021-07-20", ex_date="2021-07-19", dist_date="2021-08-10",
                           funding="undistributed_earnings", status="completed", note="Resolution 05/NQ-CTS.HĐQT/2021"),
        # Event 2: Bonus Shares from Equity Reserves (5:1 ratio, 20%)
        _non_cash_citation("VNM", "bonus_share", "08/NQ-CTS.HĐQT/2022", "2022-05-18", 1, 5, evidence_id,
                           rec_date="2022-06-22", ex_date="2022-06-21", dist_date="2022-07-15",
                           funding="investment_and_development_fund", status="completed", note="Resolution 08/NQ-CTS.HĐQT/2022"),
        # Event 3: Amended Stock Distribution Record Date Notice
        _non_cash_citation("VNM", "stock_dividend", "02/NQ-CTS.HĐQT/2023", "2023-03-10", 1, 10, evidence_id,
                           status="superseded_amended", note="Resolution 02/NQ-CTS.HĐQT/2023"),
    ]
    _write_runtime(root, citations, pdf_bytes, filename="vnm.pdf", ticker="VNM")
    return evidence_id


class NonCashEventQualificationTests(unittest.TestCase):
    def test_vnm_non_cash_event_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_non_cash_runtime(root)
            verified = bridge.load_verified_non_cash_events(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            self.assertEqual(len(verified["events"]), 3)

            # Stock Dividend assertions
            ev1 = next(e for e in verified["events"] if e["resolution_number"] == "05/NQ-CTS.HĐQT/2021")
            self.assertEqual(ev1["ticker"], "VNM")
            self.assertEqual(ev1["event_type"], "stock_dividend")
            self.assertEqual(ev1["entitlement_ratio"]["new_shares"], 1)
            self.assertEqual(ev1["entitlement_ratio"]["existing_shares"], 10)
            self.assertEqual(ev1["entitlement_ratio"]["ratio_float"], 0.1)
            self.assertEqual(ev1["funding_source"], "undistributed_earnings")
            self.assertEqual(ev1["declaration_date"], "2021-06-15")
            self.assertEqual(ev1["ex_rights_date"], "2021-07-19")
            self.assertIsNone(ev1["effective_date"])  # unasserted date remains null

            # Bonus Share assertions
            ev2 = next(e for e in verified["events"] if e["resolution_number"] == "08/NQ-CTS.HĐQT/2022")
            self.assertEqual(ev2["event_type"], "bonus_share")
            self.assertEqual(ev2["entitlement_ratio"]["new_shares"], 1)
            self.assertEqual(ev2["entitlement_ratio"]["existing_shares"], 5)
            self.assertEqual(ev2["entitlement_ratio"]["ratio_float"], 0.2)
            self.assertEqual(ev2["funding_source"], "investment_and_development_fund")

            # Amended Resolution assertions
            ev3 = next(e for e in verified["events"] if e["resolution_number"] == "02/NQ-CTS.HĐQT/2023")
            self.assertEqual(ev3["event_status"], "superseded_amended")

    def test_non_cash_event_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_non_cash_runtime(root)
            (root / "data" / "official-evidence" / "vnm.pdf").write_bytes(b"tampered pdf content")
            verified = bridge.load_verified_non_cash_events(root)
            self.assertEqual(verified["events"], [])
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_conflicting_non_cash_citations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            evidence_id = _evidence_id(sha256, ticker="VNM")
            cit1 = _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10, evidence_id)
            cit2 = dict(cit1)
            cit2["ratio_numerator"] = 2  # conflicting ratio
            cit2["citation_id"] = "cit_conflict"
            _write_runtime(root, [cit1, cit2], pdf_bytes, filename="vnm.pdf", ticker="VNM")
            verified = bridge.load_verified_non_cash_events(root)
            self.assertEqual(verified["events"], [])
            self.assertTrue(any(r["reason"] == "conflicting_citations" for r in verified["rejected"]))

    def test_determinism_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_non_cash_runtime(root)
            run1 = bridge.load_verified_non_cash_events(root)
            run2 = bridge.load_verified_non_cash_events(root)
            self.assertEqual(run1, run2)

    def test_zero_adjustment_factors_or_returns_produced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_non_cash_runtime(root)
            verified = bridge.load_verified_non_cash_events(root)
            for ev in verified["events"]:
                self.assertNotIn("adjustment_factor", ev)
                self.assertNotIn("adjusted_price", ev)
                self.assertNotIn("adjusted_return", ev)


if __name__ == "__main__":
    unittest.main()
