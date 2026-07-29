import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import semantic_evidence_bridge as bridge
from export_ai_bundle import _net_net_share_count
from intrinsic_valuation import evaluate_intrinsic_valuation
from relative_valuation import evaluate_relative_valuation


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence_id(sha256, ticker="HPG"):
    return _hash({"authority_domain": "example.test", "source_url": "u", "sha256": sha256, "ticker": ticker,
        "reporting_period": "2024", "evidence_type": "audited_consolidated_financial_statements"})


def _evidence_record(evidence_id, filename, sha256, ticker="HPG"):
    return {"evidence_id": evidence_id, "authority": "Test Authority", "authority_domain": "example.test", "ticker": ticker,
        "issuer": "Test Authority", "evidence_type": "audited_consolidated_financial_statements", "source_url": "https://example.test/" + filename,
        "document_title": "Test statement", "reporting_period": "2024", "publication_date": "2025-03-24", "retrieved_at": "2026-07-26T00:00:00+07:00",
        "content_type": "application/pdf", "language": "vi", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "test", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _share_citation(ticker, identity_type, period, value, evidence_id, frequency="annual", note="27"):
    citation_id = _hash({"ticker": ticker, "identity_type": identity_type, "reporting_period": period,
                          "evidence_id": evidence_id, "value": value})
    return {"citation_id": citation_id, "ticker": ticker, "identity_type": identity_type,
            "reporting_frequency": frequency, "reporting_period": period, "value": value, "unit": "shares",
            "evidence_id": evidence_id, "citation": {"note_number": note}, "verified_at": "2026-07-26T23:00:00+07:00",
            "schema_version": "1.0.0"}


def _write_runtime(root, citations, pdf_bytes=b"%PDF-1.4 test share basis evidence", filename="hpg.pdf", ticker="HPG"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker=ticker)
    (evidence_dir / filename).write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, filename, sha256, ticker=ticker)]}), encoding="utf-8")
    with (evidence_dir / "share_basis_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return evidence_id


def _real_hpg_runtime(root):
    """The two real, currently-retained HPG FY2024 share-basis facts."""
    pdf_bytes = b"%PDF-1.4 test share basis evidence"
    evidence_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), ticker="HPG")
    citations = [
        _share_citation("HPG", "period_end_shares_outstanding", "2024", 6396250200, evidence_id, note="27"),
        _share_citation("HPG", "weighted_average_basic_shares_outstanding", "2024", 6396250200, evidence_id, note="40.1"),
    ]
    _write_runtime(root, citations, pdf_bytes, filename="hpg.pdf", ticker="HPG")


def _real_vnm_runtime(root):
    """The three real, qualified VNM FY2024 share-basis facts."""
    pdf_bytes = b"%PDF-1.4 test VNM share basis evidence"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    citations = [
        _share_citation("VNM", "period_end_shares_outstanding", "2024", 2089955445, evidence_id, note="printed p. 32"),
        _share_citation("VNM", "weighted_average_basic_shares_outstanding", "2024", 2089955445, evidence_id, note="printed p. 185"),
        _share_citation("VNM", "treasury_shares_outstanding", "2024", 0, evidence_id, note="printed p. 32"),
    ]
    _write_runtime(root, citations, pdf_bytes, filename="vnm.pdf", ticker="VNM")


def _financial_net_net_inputs(period="2024"):
    def r(m, v):
        return {"canonical_metric": m, "value": v, "quality_state": "available", "statement_scope": "consolidated",
                "period_identity": {"period": period, "period_type": "annual"}}
    return {m: r(m, v) for m, v in {"current_assets": 86674276272995, "cash_and_equivalents": 6887646139852,
            "receivables": 7647800286988, "inventory": 46091222189472, "total_liabilities": 109842249570282}.items()}


class ShareBasisQualificationTests(unittest.TestCase):
    def test_vnm_fy2024_share_basis_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_vnm_runtime(root)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            period_end = bridge.latest_share_basis(verified["by_identity"], "VNM", "period_end_shares_outstanding")
            weighted_avg = bridge.latest_share_basis(verified["by_identity"], "VNM", "weighted_average_basic_shares_outstanding")
            treasury = bridge.latest_share_basis(verified["by_identity"], "VNM", "treasury_shares_outstanding")
            valuation_date = bridge.latest_share_basis(verified["by_identity"], "VNM", "valuation_date_shares_outstanding")

            self.assertIsNotNone(period_end)
            self.assertEqual(period_end["value"], 2089955445)
            self.assertIsNotNone(weighted_avg)
            self.assertEqual(weighted_avg["value"], 2089955445)
            self.assertIsNotNone(treasury)
            self.assertEqual(treasury["value"], 0)
            self.assertIsNone(valuation_date)

            # All three citation IDs must be distinct despite value overlaps
            self.assertNotEqual(period_end["citation_id"], weighted_avg["citation_id"])
            self.assertNotEqual(period_end["citation_id"], treasury["citation_id"])

            # Determinism test
            second_read = bridge.load_verified_share_basis(root)
            self.assertEqual(verified, second_read)

    def test_identity_separation_never_conflates_three_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            period_end = bridge.latest_share_basis(verified["by_identity"], "HPG", "period_end_shares_outstanding")
            weighted_avg = bridge.latest_share_basis(verified["by_identity"], "HPG", "weighted_average_basic_shares_outstanding")
            valuation_date = bridge.latest_share_basis(verified["by_identity"], "HPG", "valuation_date_shares_outstanding")
            self.assertIsNotNone(period_end); self.assertIsNotNone(weighted_avg)
            self.assertIsNone(valuation_date)  # never falls back to a different identity when absent
            self.assertNotEqual(period_end["citation_id"], weighted_avg["citation_id"])  # distinct facts, even though numerically equal

    def test_as_of_date_alignment_correctness(self):
        # share_count declares a period that matches the balance-sheet components -> available.
        aligned = evaluate_intrinsic_valuation({"financial": _financial_net_net_inputs("2024"),
            "share_count": {"value": 6396250200, "semantics": "period_end", "period_identity": {"period": "2024", "period_type": "annual"}}})
        self.assertEqual(aligned["methods"]["net_net"]["state"], "available")
        # share_count declares a DIFFERENT period than the balance-sheet components -> fail closed, not merged.
        misaligned = evaluate_intrinsic_valuation({"financial": _financial_net_net_inputs("2024"),
            "share_count": {"value": 6396250200, "semantics": "period_end", "period_identity": {"period": "2025", "period_type": "annual"}}})
        self.assertEqual(misaligned["methods"]["net_net"]["state"], "unavailable")
        self.assertIn("qualified_share_count", misaligned["methods"]["net_net"]["missing_inputs"])

    def test_share_basis_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            (root / "data" / "official-evidence" / "hpg.pdf").write_bytes(b"tampered content")
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["by_identity"], {})
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_conflicting_identity_citations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation_a = _share_citation("HPG", "period_end_shares_outstanding", "2024", 6396250200, evidence_id)
            citation_b = _share_citation("HPG", "period_end_shares_outstanding", "2024", 9999999999, evidence_id)
            _write_runtime(root, [citation_a, citation_b], pdf_bytes)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["by_identity"], {})
            self.assertTrue(any(r["reason"] == "conflicting_citations" for r in verified["rejected"]))

    def test_unsupported_identity_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            bad = _share_citation("HPG", "shares_estimated_from_market_chatter", "2024", 6396250200, evidence_id)
            _write_runtime(root, [bad], pdf_bytes)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["by_identity"], {})
            self.assertEqual(verified["rejected"][0]["reason"], "unsupported_identity_type")

    def test_append_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            path = root / "data" / "official-evidence" / "share_basis_citations.jsonl"
            before = path.read_bytes()
            first = bridge.load_verified_share_basis(root)
            second = bridge.load_verified_share_basis(root)
            after = path.read_bytes()
            self.assertEqual(before, after)  # verification never writes
            self.assertEqual(first, second)  # deterministic, repeatable

    def test_legacy_behavior_without_share_basis_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified, {"status": "unavailable", "version": bridge.VERSION, "by_identity": {}, "rejected": []})
            result = evaluate_intrinsic_valuation({"financial": _financial_net_net_inputs(), "share_count": None})
            self.assertEqual(result["methods"]["net_net"]["state"], "unavailable")

    def test_net_net_before_after(self):
        before = evaluate_intrinsic_valuation({"financial": _financial_net_net_inputs(), "current_price_actionable": True})
        self.assertEqual(before["methods"]["net_net"]["state"], "unavailable")
        self.assertIn("qualified_share_count", before["methods"]["net_net"]["missing_inputs"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            with mock.patch.dict(os.environ, {"STOCK_LOOKUP_RUNTIME_ROOT": str(root)}):
                share_count = _net_net_share_count("HPG")
            self.assertIsNotNone(share_count)
            self.assertEqual(share_count["semantics"], "period_end")
            after = evaluate_intrinsic_valuation({"financial": _financial_net_net_inputs(), "share_count": share_count, "current_price_actionable": True})
            nn = after["methods"]["net_net"]
            self.assertEqual(nn["state"], "available")
            self.assertEqual(nn["equity_value"], -49215580953970)
            self.assertAlmostEqual(nn["per_share_value"], -49215580953970 / 6396250200)
            self.assertIn("share_count", nn["used_inputs"])

    def test_net_net_share_count_absent_without_citation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no official-evidence directory at all
            with mock.patch.dict(os.environ, {"STOCK_LOOKUP_RUNTIME_ROOT": str(root)}):
                self.assertIsNone(_net_net_share_count("HPG"))
                self.assertIsNone(_net_net_share_count("PAN"))  # generic: no ticker-specific fallback either

    def test_relative_valuation_before_after_stays_unavailable(self):
        financial = {"net_income": {"canonical_metric": "net_income", "value": 12021443836074, "quality_state": "available",
                        "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}},
                     "shareholders_equity": {"canonical_metric": "shareholders_equity", "value": 114356467351331, "quality_state": "available",
                        "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}}}
        before = evaluate_relative_valuation({"entity_type": "corporate", "financial": financial})
        after = evaluate_relative_valuation({"entity_type": "corporate", "financial": financial})  # no share_count/market_cap passed, same as the real exporter
        for result in (before, after):
            self.assertEqual(result["methods"]["pe"]["state"], "unavailable")
            self.assertEqual(result["methods"]["pb"]["state"], "unavailable")
            self.assertIn("qualified_weighted_average_share_count", result["methods"]["pe"]["missing_inputs"])
            self.assertIn("qualified_period_end_share_count", result["methods"]["pb"]["missing_inputs"])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
