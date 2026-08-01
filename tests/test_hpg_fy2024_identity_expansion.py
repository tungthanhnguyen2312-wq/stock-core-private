# ==========================================================================
# Focused tests for Phase 6E: HPG FY2024 missing financial identity retention
# (current_liabilities, retained_earnings via undistributed_earnings, profit_before_tax)
# and the derived ebit identity, through the real citation/observation qualification
# pipeline (financial_observations.py + semantic_evidence_bridge.py). Synthetic
# temp-dir fixtures only -- no real data, no dashboard-runtime access.
# Run: `python -m unittest tests.test_hpg_fy2024_identity_expansion` from the repo root.
# ==========================================================================

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import semantic_evidence_bridge as bridge  # noqa: E402
from financial_observations import _hash as fo_hash, store_path, append_observations, canonical_records  # noqa: E402


def _manifest_and_pdf(root: Path, ticker: str = "HPG") -> tuple[str, bytes]:
    pdf_bytes = b"%PDF-1.4 test HPG FY2024 consolidated evidence"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = fo_hash({"filename": "hpg.pdf", "sha256": sha256, "ticker": ticker})
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "hpg.pdf").write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [
        {"evidence_id": evidence_id, "filename": "hpg.pdf", "sha256": sha256, "ticker": ticker,
         "qualification_state": "qualified"},
    ]}), encoding="utf-8")
    return evidence_id, pdf_bytes


def _observation(ticker, raw_item_id, statement_type, value, period="2024") -> dict:
    identity = {"ticker": ticker, "provider": "VCI", "method": statement_type, "parameters": {"period": "year"},
                "statement_type": statement_type, "period": period, "source_header": period, "raw_item_id": raw_item_id}
    fingerprint = fo_hash(["item_id", "item", period])
    source_record_hash = fo_hash({"ticker": ticker, "raw_item_id": raw_item_id, "period": period, "value": value})
    obs = {"schema_version": "1.0.0", "identity_key": fo_hash(identity), "ticker": ticker, "issuer_identity": ticker,
           "provider": "VCI", "library": "vnstock", "library_version": "4.0.4", "source_method": statement_type,
           "parameters": {"period": "year"}, "retrieved_at": "2026-08-01T00:00:00+00:00",
           "raw_statement_type": statement_type, "requested_reporting_frequency": "year",
           "reporting_frequency": "annual", "reporting_period": period, "source_header": period,
           "raw_item_id": raw_item_id, "raw_label_vi": raw_item_id, "raw_label_en": raw_item_id,
           "raw_value": value, "raw_currency": None, "raw_scale": None, "statement_scope": "unknown",
           "cumulative_state": "unknown", "schema_fingerprint": fingerprint, "source_record_hash": source_record_hash,
           "qualification_state": "retained_exact_item_id", "warnings": ["statement_scope_unknown", "currency_and_scale_unknown"]}
    obs["observation_id"] = fo_hash({**identity, "source_record_hash": source_record_hash, "raw_value": value, "schema_fingerprint": fingerprint})
    return obs


def _citation(observation: dict, evidence_id: str, official_value, *, scope="consolidated", currency="VND", scale=1) -> dict:
    citation = {
        "observation_id": observation["observation_id"], "evidence_id": evidence_id, "ticker": observation["ticker"],
        "reporting_frequency": observation["reporting_frequency"], "reporting_period": observation["reporting_period"],
        "raw_statement_type": observation["raw_statement_type"], "raw_item_id": observation["raw_item_id"],
        "raw_value": observation["raw_value"], "official_value": official_value,
        "statement_scope": scope, "currency": currency, "unit_scale": scale,
        "match_method": "exact_numeric_match", "match_result": "exact", "schema_version": "1.0.0",
        "verified_at": "2026-08-01T00:00:00+07:00",
    }
    citation["citation_id"] = bridge._hash({"observation_id": citation["observation_id"], "evidence_id": citation["evidence_id"],
                                             "raw_item_id": citation["raw_item_id"], "matched_value": citation["official_value"]})
    return citation


def _write(root: Path, observations: list[dict], citations: list[dict]) -> None:
    append_observations(store_path(root), observations)
    with (root / "data" / "official-evidence" / "qualification_citations.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")


class SuccessfulQualificationTests(unittest.TestCase):
    def test_three_new_identities_qualify_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [
                _observation("HPG", "current_liabilities", "balance_sheet", 75225243262689),
                _observation("HPG", "undistributed_earnings", "balance_sheet", 49599124109203),
                _observation("HPG", "profit_before_tax", "income_statement", 13693502261178),
            ]
            cits = [_citation(o, evidence_id, o["raw_value"]) for o in obs]
            _write(root, obs, cits)

            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])

            canon = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.reconcile_metric_identities(bridge.enrich_canonical_records(canon, root))
            by_metric = {r["canonical_metric"]: r for r in enriched["HPG"] if r.get("quality_state") == "available"}
            self.assertEqual(by_metric["current_liabilities"]["value"], 75225243262689)
            self.assertEqual(by_metric["retained_earnings"]["value"], 49599124109203)
            self.assertEqual(by_metric["profit_before_tax"]["value"], 13693502261178)

    def test_deterministic_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            cits = [_citation(o, evidence_id, o["raw_value"]) for o in obs]
            _write(root, obs, cits)
            first = bridge.load_verified_citations(root)
            second = bridge.load_verified_citations(root)
            self.assertEqual(first, second)


class FailClosedTests(unittest.TestCase):
    def test_missing_citation_leaves_observation_unqualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            append_observations(store_path(root), obs)  # no citation written
            (root / "data" / "official-evidence" / "qualification_citations.jsonl").write_text("", encoding="utf-8")
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "unavailable")
            canon = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.reconcile_metric_identities(bridge.enrich_canonical_records(canon, root))
            record = next(r for r in enriched["HPG"] if r["canonical_metric"] == "current_liabilities")
            self.assertNotEqual(record.get("quality_state"), "available")

    def test_scope_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            cits = [_citation(obs[0], evidence_id, obs[0]["raw_value"], scope="separate")]
            _write(root, obs, cits)
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "unavailable")
            self.assertTrue(any(r["reason"] == "unsupported_scope" for r in verified["rejected"]))

    def test_duplicate_conflicting_observation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            cit_a = _citation(obs[0], evidence_id, obs[0]["raw_value"])
            cit_b = dict(cit_a)
            cit_b["official_value"] = 1  # conflicting content, same observation_id
            _write(root, obs, [cit_a, cit_b])
            verified = bridge.load_verified_citations(root)
            self.assertTrue(any(r["reason"] == "conflicting_citations" for r in verified["rejected"]))

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            cits = [_citation(o, evidence_id, o["raw_value"]) for o in obs]
            _write(root, obs, cits)
            (root / "data" / "official-evidence" / "hpg.pdf").write_bytes(b"tampered")
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "unavailable")
            self.assertTrue(any(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_no_cross_ticker_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, _ = _manifest_and_pdf(root)
            obs = [_observation("HPG", "current_liabilities", "balance_sheet", 75225243262689)]
            cits = [_citation(o, evidence_id, o["raw_value"]) for o in obs]
            _write(root, obs, cits)
            canon = canonical_records(store_path(root), {"HPG": "corporate", "VNM": "corporate"})
            enriched = bridge.reconcile_metric_identities(bridge.enrich_canonical_records(canon, root))
            self.assertFalse(any(r.get("quality_state") == "available" for r in enriched.get("VNM", [])))


if __name__ == "__main__":
    unittest.main()
