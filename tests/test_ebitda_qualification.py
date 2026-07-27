import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import semantic_evidence_bridge as bridge
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


def _ebitda_citation(ticker, metric, period, value, evidence_id, frequency="annual", scope="consolidated",
                      currency="VND", scale=1, note="test"):
    citation_id = _hash({"ticker": ticker, "metric": metric, "reporting_period": period,
                          "evidence_id": evidence_id, "value": value})
    return {"schema_version": "1.0.0", "citation_id": citation_id, "evidence_id": evidence_id, "ticker": ticker,
            "metric": metric, "reporting_frequency": frequency, "reporting_period": period,
            "statement_scope": scope, "currency": currency, "unit_scale": scale, "value": value,
            "citation": {"note": note}, "verified_at": "2026-07-27T10:00:00+07:00"}


def _write_runtime(root, citations, pdf_bytes=b"%PDF-1.4 test ebitda evidence", filename="hpg.pdf"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256)
    (evidence_dir / filename).write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, filename, sha256)]}), encoding="utf-8")
    with (evidence_dir / "ebitda_component_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return evidence_id


# The three real, currently-retained HPG FY2024 figures (audited consolidated statements,
# form B02-DN/HN income statement and B03-DN/HN cash flow statement):
#   profit_before_tax (mã số 50)            13,693,502,261,178
#   interest_expense (mã số 23, "Chi phí đi vay")  2,287,360,810,880
#   depreciation_and_amortization (mã số 02, "Khấu hao và phân bổ")  6,915,671,331,197
# Excluded: operating_profit (mã số 30) 13,267,005,585,330 -- audited but not used, because
# it already nets financial income/expense. Goodwill amortization ("Phân bổ lợi thế
# thương mại") 12,295,891,969 -- a distinct, non-operating addback, never folded in.
PBT, INTEREST, DA = 13693502261178, 2287360810880, 6915671331197
EXPECTED_EBITDA = PBT + INTEREST + DA  # 22,896,534,403,255


def _real_hpg_runtime(root, **overrides):
    pdf_bytes = b"%PDF-1.4 test ebitda evidence"
    evidence_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest())
    values = {"profit_before_tax": PBT, "interest_expense": INTEREST, "depreciation_and_amortization": DA}
    fields = {"profit_before_tax": {}, "interest_expense": {}, "depreciation_and_amortization": {}}
    for metric, patch in overrides.items():
        fields[metric] = patch
    citations = [_ebitda_citation("HPG", metric, fields[metric].get("period", "2024"), values[metric], evidence_id,
                                   scope=fields[metric].get("scope", "consolidated"),
                                   currency=fields[metric].get("currency", "VND"),
                                   scale=fields[metric].get("scale", 1))
                 for metric in values]
    _write_runtime(root, citations, pdf_bytes)
    return evidence_id


class EbitdaQualificationTests(unittest.TestCase):
    def test_load_verified_components_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            self.assertEqual(len(verified["by_key"]), 3)
            pbt = bridge.latest_ebitda_component(verified["by_key"], "HPG", "profit_before_tax")
            self.assertEqual(pbt["value"], PBT)

    def test_legacy_behavior_without_ebitda_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no official-evidence directory at all
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified, {"status": "unavailable", "version": bridge.VERSION, "by_key": {}, "rejected": []})
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            (root / "data" / "official-evidence" / "hpg.pdf").write_bytes(b"tampered content")
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified["by_key"], {})
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    def test_conflicting_citations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation_a = _ebitda_citation("HPG", "profit_before_tax", "2024", PBT, evidence_id)
            citation_b = _ebitda_citation("HPG", "profit_before_tax", "2024", 999, evidence_id)
            _write_runtime(root, [citation_a, citation_b], pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified["by_key"], {})
            self.assertTrue(any(r["reason"] == "conflicting_citations" for r in verified["rejected"]))

    def test_unsupported_metric_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            bad = _ebitda_citation("HPG", "ebitda_margin_estimate", "2024", 123, evidence_id)
            _write_runtime(root, [bad], pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified["by_key"], {})
            self.assertEqual(verified["rejected"][0]["reason"], "unsupported_metric")

    def test_malformed_citation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"
            evidence_dir = root / "data" / "official-evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            (evidence_dir / "hpg.pdf").write_bytes(pdf_bytes)
            (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, "hpg.pdf", sha256)]}), encoding="utf-8")
            with (evidence_dir / "ebitda_component_citations.jsonl").open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"ticker": "HPG", "metric": "profit_before_tax"}) + "\n")  # missing required fields
            verified = bridge.load_verified_ebitda_components(root)
            self.assertEqual(verified["by_key"], {})
            self.assertEqual(verified["rejected"][0]["reason"], "malformed_citation")

    def test_derive_ebitda_formula_and_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            verified = bridge.load_verified_ebitda_components(root)
            record = bridge.derive_ebitda(verified["by_key"], "HPG")
            self.assertIsNotNone(record)
            self.assertEqual(record["canonical_metric"], "ebitda")
            self.assertEqual(record["value"], EXPECTED_EBITDA)
            self.assertEqual(record["value"], 22896534403255)
            self.assertEqual(record["quality_state"], "available")
            self.assertEqual(record["statement_scope"], "consolidated")
            self.assertEqual(record["currency"], "VND")
            self.assertEqual(record["unit_scale"], 1)
            self.assertEqual(record["period_identity"], {"period": "2024", "period_type": "annual"})
            # Formula-version enforcement: the version travels with the record at both levels.
            self.assertEqual(record["formula_version"], bridge.EBITDA_FORMULA_VERSION)
            self.assertEqual(record["derivation_lineage"]["formula_version"], bridge.EBITDA_FORMULA_VERSION)
            self.assertEqual(len(record["derivation_lineage"]["components"]), 3)

    def test_derive_ebitda_never_folds_in_operating_profit_or_goodwill_amortization(self):
        # A value that would result from double-counting or an alternate formulation
        # must not equal the qualified value -- guards against silent formula drift.
        operating_profit = 13267005585330
        goodwill_amortization = 12295891969
        alt_formula_value = operating_profit + DA  # the explicitly-rejected alternative
        double_counted_value = EXPECTED_EBITDA + goodwill_amortization
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            verified = bridge.load_verified_ebitda_components(root)
            record = bridge.derive_ebitda(verified["by_key"], "HPG")
            self.assertNotEqual(record["value"], alt_formula_value)
            self.assertNotEqual(record["value"], double_counted_value)
            excluded_text = " ".join(record["derivation_lineage"]["excluded"])
            self.assertIn("operating_profit", excluded_text)
            self.assertIn("goodwill", excluded_text.lower())

    def test_derive_ebitda_missing_component_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citations = [_ebitda_citation("HPG", "profit_before_tax", "2024", PBT, evidence_id),
                         _ebitda_citation("HPG", "interest_expense", "2024", INTEREST, evidence_id)]  # D&A missing
            _write_runtime(root, citations, pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_derive_ebitda_period_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citations = [_ebitda_citation("HPG", "profit_before_tax", "2023", PBT, evidence_id),  # different period
                         _ebitda_citation("HPG", "interest_expense", "2024", INTEREST, evidence_id),
                         _ebitda_citation("HPG", "depreciation_and_amortization", "2024", DA, evidence_id)]
            _write_runtime(root, citations, pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_derive_ebitda_scope_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citations = [_ebitda_citation("HPG", "profit_before_tax", "2024", PBT, evidence_id, scope="separate"),
                         _ebitda_citation("HPG", "interest_expense", "2024", INTEREST, evidence_id),
                         _ebitda_citation("HPG", "depreciation_and_amortization", "2024", DA, evidence_id)]
            _write_runtime(root, citations, pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_derive_ebitda_currency_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citations = [_ebitda_citation("HPG", "profit_before_tax", "2024", PBT, evidence_id, currency="USD"),
                         _ebitda_citation("HPG", "interest_expense", "2024", INTEREST, evidence_id),
                         _ebitda_citation("HPG", "depreciation_and_amortization", "2024", DA, evidence_id)]
            _write_runtime(root, citations, pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_derive_ebitda_scale_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citations = [_ebitda_citation("HPG", "profit_before_tax", "2024", PBT, evidence_id, scale=1000),
                         _ebitda_citation("HPG", "interest_expense", "2024", INTEREST, evidence_id),
                         _ebitda_citation("HPG", "depreciation_and_amortization", "2024", DA, evidence_id)]
            _write_runtime(root, citations, pdf_bytes)
            verified = bridge.load_verified_ebitda_components(root)
            self.assertIsNone(bridge.derive_ebitda(verified["by_key"], "HPG"))

    def test_deterministic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            path = root / "data" / "official-evidence" / "ebitda_component_citations.jsonl"
            before = path.read_bytes()
            first_verified = bridge.load_verified_ebitda_components(root)
            second_verified = bridge.load_verified_ebitda_components(root)
            after = path.read_bytes()
            self.assertEqual(before, after)  # verification never writes
            self.assertEqual(first_verified, second_verified)  # deterministic, repeatable
            first_record = bridge.derive_ebitda(first_verified["by_key"], "HPG")
            second_record = bridge.derive_ebitda(second_verified["by_key"], "HPG")
            self.assertEqual(first_record, second_record)

    def test_ev_ebitda_before_after(self):
        financial_without_ebitda = {"revenue": {"canonical_metric": "revenue", "value": 138855112131387, "quality_state": "available",
                        "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}},
                     "total_debt": {"canonical_metric": "total_debt", "value": 82963129469555, "quality_state": "available",
                        "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}},
                     "cash_and_equivalents": {"canonical_metric": "cash_and_equivalents", "value": 6887646139852, "quality_state": "available",
                        "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}}}
        price = {"value": 19830.0, "as_of_date": "2024-12-31", "financial_period": "2024", "source": "VCI:ohlcv", "is_actionable": True}
        share_period_end = {"value": 6396250200, "semantics": "period_end", "period_identity": {"period": "2024", "period_type": "annual"}}

        before = evaluate_relative_valuation({"entity_type": "corporate", "current_price": price,
            "share_count_period_end": share_period_end, "financial": financial_without_ebitda})
        self.assertEqual(before["methods"]["ev_ebitda"]["state"], "unavailable")
        self.assertIn("required_input_missing", before["methods"]["ev_ebitda"]["missing_inputs"])
        self.assertAlmostEqual(before["methods"]["ev_sales"]["observed_multiple"], 1.4613298832217516)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _real_hpg_runtime(root)
            verified = bridge.load_verified_ebitda_components(root)
            ebitda_record = bridge.derive_ebitda(verified["by_key"], "HPG")
        financial_with_ebitda = {**financial_without_ebitda, "ebitda": ebitda_record}
        after = evaluate_relative_valuation({"entity_type": "corporate", "current_price": price,
            "share_count_period_end": share_period_end, "financial": financial_with_ebitda})
        self.assertEqual(after["methods"]["ev_ebitda"]["state"], "available")
        expected_ev = 19830.0 * 6396250200 + 82963129469555 - 6887646139852
        self.assertAlmostEqual(after["methods"]["ev_ebitda"]["observed_multiple"], expected_ev / EXPECTED_EBITDA)
        self.assertAlmostEqual(after["methods"]["ev_ebitda"]["observed_multiple"], 8.862176311138887)
        # EV/Sales, unaffected by this milestone, is byte-identical before and after.
        self.assertEqual(before["methods"]["ev_sales"], after["methods"]["ev_sales"])


if __name__ == "__main__":
    unittest.main()
