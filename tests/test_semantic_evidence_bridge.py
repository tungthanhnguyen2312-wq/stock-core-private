import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import semantic_evidence_bridge as bridge
from financial_observations import append_observations, canonical_records, observations_from_frame, store_path


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


HPG_ROWS = [
    ("balance_sheet", "cash_and_cash_equivalents", 6887646139852),
    ("balance_sheet", "short_term_borrowings", 55882686213459),
    ("balance_sheet", "long_term_borrowings", 27080443256096),
    ("income_statement", "interest_expenses", -2287360810880),
    ("income_statement", "attributable_to_parent_company", 12021443836074),
    ("cash_flow", "net_cash_inflows_outflows_from_operating_activities", 6608320655215),
    ("cash_flow", "net_cash_inflows_outflows_from_investing_activities", -29788138252448),
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets", -35495026797327),
    ("cash_flow", "net_cash_inflows_outflows_from_financing_activities", 17814697586944),
]
# The official consolidated statement presents interest_expenses as an unsigned
# breakdown line; every other item is presented with the same sign VCI stores.
OFFICIAL_VALUES = {item_id: (abs(value) if item_id == "interest_expenses" else value) for _, item_id, value in HPG_ROWS}


def _make_observations(ticker="HPG", period="2024"):
    by_method = {}
    for method, item_id, value in HPG_ROWS:
        by_method.setdefault(method, []).append({"item_id": item_id, "item": item_id, "item_en": item_id, period: value})
    observations = []
    for method, rows in by_method.items():
        frame = pd.DataFrame(rows)
        observations += observations_from_frame(frame, ticker=ticker, entity_type="corporate", method=method,
            requested_frequency="year", retrieved_at="2026-07-26T00:00:00+00:00", version="4.0.4")
    return observations


def _evidence_record(evidence_id, filename, sha256, ticker="HPG"):
    return {"evidence_id": evidence_id, "authority": "Test Authority", "authority_domain": "example.test", "ticker": ticker,
        "issuer": "Test Authority", "evidence_type": "audited_consolidated_financial_statements", "source_url": "https://example.test/" + filename,
        "document_title": "Test statement", "reporting_period": "2024", "publication_date": "2025-03-24", "retrieved_at": "2026-07-26T00:00:00+07:00",
        "content_type": "application/pdf", "language": "vi", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "test", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _evidence_id(sha256, ticker="HPG"):
    return _hash({"authority_domain": "example.test", "source_url": "u", "sha256": sha256, "ticker": ticker,
        "reporting_period": "2024", "evidence_type": "audited_consolidated_financial_statements"})


def _citation_for(observation, official_value, evidence_id):
    citation_id = _hash({"observation_id": observation["observation_id"], "evidence_id": evidence_id,
        "raw_item_id": observation["raw_item_id"], "matched_value": official_value})
    return {"citation_id": citation_id, "observation_id": observation["observation_id"], "identity_key": observation["identity_key"],
        "evidence_id": evidence_id, "ticker": observation["ticker"], "raw_statement_type": observation["raw_statement_type"],
        "raw_item_id": observation["raw_item_id"], "reporting_frequency": observation["reporting_frequency"],
        "reporting_period": observation["reporting_period"], "raw_value": observation["raw_value"], "official_value": official_value,
        "match_method": "exact_numeric_match", "match_result": "exact", "statement_scope": "consolidated", "currency": "VND",
        "unit_scale": 1, "citation": {"form_code": "B01/B02/B03-DN/HN", "pdf_page": 1, "printed_page": 1, "line_code_ma_so": "1", "line_label_vi": "test"},
        "disambiguation": "test", "verified_at": "2026-07-26T21:00:00+07:00", "schema_version": "1.0.0"}


def _write_runtime(root, observations, evidence_records=None, citation_dicts=None, pdf_bytes_by_filename=None):
    append_observations(store_path(root), observations)
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in (pdf_bytes_by_filename or {}).items():
        (evidence_dir / filename).write_bytes(content)
    if evidence_records is not None:
        (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": evidence_records}), encoding="utf-8")
    if citation_dicts is not None:
        with (evidence_dir / "qualification_citations.jsonl").open("w", encoding="utf-8") as fh:
            for row in citation_dicts:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class SemanticEvidenceBridgeTests(unittest.TestCase):
    def _valid_runtime(self, tmp):
        root = Path(tmp)
        observations = _make_observations()
        pdf_bytes = b"%PDF-1.4 test evidence document"
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        evidence_id = _evidence_id(sha256)
        citations = [_citation_for(obs, OFFICIAL_VALUES[obs["raw_item_id"]], evidence_id) for obs in observations]
        _write_runtime(root, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], citations, {"hpg.pdf": pdf_bytes})
        return root, observations

    def test_exact_nine_id_linkage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(len(verified["by_observation_id"]), 9)
            self.assertEqual({o["observation_id"] for o in observations}, set(verified["by_observation_id"]))
            for entry in verified["by_observation_id"].values():
                self.assertEqual((entry["statement_scope"], entry["currency"], entry["unit_scale"]), ("consolidated", "VND", 1))
            canonical = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.enrich_canonical_records(canonical, root)["HPG"]
            direct = [r for r in enriched if r["derivation_status"] == "direct"]
            self.assertEqual(len(direct), 9)
            self.assertTrue(all(r["quality_state"] == "available" and r["statement_scope"] == "consolidated" and "evidence" in r for r in direct))

    def test_unrelated_observation_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = _make_observations()
            pdf_bytes = b"evidence"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            fake = _citation_for(observations[0], OFFICIAL_VALUES[observations[0]["raw_item_id"]], evidence_id)
            fake = dict(fake, observation_id="observation-id-not-in-store")
            fake["citation_id"] = _hash({"observation_id": fake["observation_id"], "evidence_id": evidence_id,
                "raw_item_id": fake["raw_item_id"], "matched_value": fake["official_value"]})
            _write_runtime(root, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], [fake], {"hpg.pdf": pdf_bytes})
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["by_observation_id"], {})
            self.assertEqual(verified["rejected"][0]["reason"], "observation_id_not_found_in_current_store")

    def test_pdf_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            (root / "data" / "official-evidence" / "hpg.pdf").write_bytes(b"tampered content, different from manifest sha256")
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["by_observation_id"], {})
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_conflicting_citations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = _make_observations()
            target = observations[0]
            pdf_bytes = b"evidence"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation_a = _citation_for(target, OFFICIAL_VALUES[target["raw_item_id"]], evidence_id)
            citation_b = dict(citation_a, official_value=citation_a["official_value"] + 1)
            citation_b["citation_id"] = _hash({"observation_id": target["observation_id"], "evidence_id": evidence_id,
                "raw_item_id": target["raw_item_id"], "matched_value": citation_b["official_value"]})
            _write_runtime(root, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], [citation_a, citation_b], {"hpg.pdf": pdf_bytes})
            verified = bridge.load_verified_citations(root)
            self.assertNotIn(target["observation_id"], verified["by_observation_id"])
            self.assertTrue(any(r.get("reason") == "conflicting_citations" for r in verified["rejected"]))

    def test_hpg_only_applicability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, hpg_observations = self._valid_runtime(tmp)
            pan_observations = _make_observations(ticker="PAN")
            append_observations(store_path(root), pan_observations)  # no citations recorded for PAN
            canonical = canonical_records(store_path(root), {"HPG": "corporate", "PAN": "corporate"})
            enriched = bridge.enrich_canonical_records(canonical, root)
            self.assertTrue(all(r["quality_state"] == "available" for r in enriched["HPG"] if r["derivation_status"] == "direct"))
            self.assertTrue(all(r["quality_state"] == "unknown" and r["statement_scope"] == "unknown"
                                 for r in enriched["PAN"] if r["derivation_status"] == "direct"))

    def test_signed_value_presentation_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            verified = bridge.load_verified_citations(root)
            interest = next(o for o in observations if o["raw_item_id"] == "interest_expenses")
            self.assertIn(interest["observation_id"], verified["by_observation_id"])
            self.assertLess(interest["raw_value"], 0)  # raw stays negative -- never mutated to match presentation
            self.assertEqual(verified["by_observation_id"][interest["observation_id"]]["sign_rule_version"], "v1")
        with tempfile.TemporaryDirectory() as tmp2:
            # cash_and_cash_equivalents has no registered sign rule: an opposite-signed
            # "match" must be rejected outright, not silently accepted by |raw|==|official|.
            root2 = Path(tmp2)
            observations = _make_observations()
            cash = next(o for o in observations if o["raw_item_id"] == "cash_and_cash_equivalents")
            pdf_bytes = b"evidence"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation = _citation_for(cash, -cash["raw_value"], evidence_id)
            _write_runtime(root2, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], [citation], {"hpg.pdf": pdf_bytes})
            verified2 = bridge.load_verified_citations(root2)
            self.assertNotIn(cash["observation_id"], verified2["by_observation_id"])
            self.assertEqual(verified2["rejected"][0]["reason"], "value_mismatch_after_sign_rule")

    def test_derived_record_evidence_propagation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            canonical = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.enrich_canonical_records(canonical, root)["HPG"]
            derived = next(r for r in enriched if r["canonical_metric"] == "total_interest_bearing_debt")
            expected_ids = {next(o for o in observations if o["raw_item_id"] == "short_term_borrowings")["observation_id"],
                            next(o for o in observations if o["raw_item_id"] == "long_term_borrowings")["observation_id"]}
            self.assertEqual(set(derived["observation_ids"]), expected_ids)
            self.assertEqual(derived["quality_state"], "available")
            self.assertEqual(len(derived["evidence"]["components"]), 2)
        with tempfile.TemporaryDirectory() as tmp2:
            # Only one of the two required components cited -> derived record must NOT be upgraded.
            root2 = Path(tmp2)
            observations = _make_observations()
            short_term = next(o for o in observations if o["raw_item_id"] == "short_term_borrowings")
            pdf_bytes = b"evidence"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation = _citation_for(short_term, OFFICIAL_VALUES["short_term_borrowings"], evidence_id)
            _write_runtime(root2, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], [citation], {"hpg.pdf": pdf_bytes})
            canonical2 = canonical_records(store_path(root2), {"HPG": "corporate"})
            enriched2 = bridge.enrich_canonical_records(canonical2, root2)["HPG"]
            derived2 = next(r for r in enriched2 if r["canonical_metric"] == "total_interest_bearing_debt")
            self.assertEqual(derived2["quality_state"], "unknown")
            self.assertEqual(derived2.get("observation_ids"), [])

    def test_idempotent_repeated_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            canonical = canonical_records(store_path(root), {"HPG": "corporate"})
            first = bridge.enrich_canonical_records(canonical, root)
            second = bridge.enrich_canonical_records(canonical, root)
            self.assertEqual(first, second)

    def test_observations_file_never_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = self._valid_runtime(tmp)
            path = store_path(root)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            canonical = canonical_records(path, {"HPG": "corporate"})
            bridge.load_verified_citations(root)
            bridge.enrich_canonical_records(canonical, root)
            bridge.enrich_canonical_records(canonical, root)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before, after)

    def test_legacy_behavior_without_citation_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = _make_observations()
            append_observations(store_path(root), observations)  # no data/official-evidence directory at all
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified, {"status": "unavailable", "version": bridge.VERSION, "by_observation_id": {}, "rejected": []})
            canonical = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.enrich_canonical_records(canonical, root)
            self.assertEqual(enriched, canonical)


if __name__ == "__main__":
    unittest.main()
