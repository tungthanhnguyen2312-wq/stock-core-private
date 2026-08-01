# ==========================================================================
# Focused tests for Phase 5D distribution_evidence.py + the income_defensive gate it
# feeds in analysis_lane_eligibility.py. Pure unit tests against synthetic temp-dir
# evidence stores (same fixture idiom as tests/test_corporate_action_ledger.py and
# tests/test_cash_dividend_qualification.py) -- no real data, no database, no bundle.
# Run: `python -m unittest tests.test_distribution_evidence` from the repo root.
# ==========================================================================

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analysis_lane_eligibility as ale  # noqa: E402
import distribution_evidence as de  # noqa: E402
import export_ai_bundle as bundle_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors tests/test_corporate_action_ledger.py exactly, so the
# hashing/identity scheme matches semantic_evidence_bridge.py's real expectations).
# ---------------------------------------------------------------------------

def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence_id(sha256, ticker):
    return _hash({"authority_domain": "issuer.example", "source_url": "u", "sha256": sha256, "ticker": ticker,
        "reporting_period": "2024", "evidence_type": "audited_consolidated_financial_statements"})


def _evidence_record(evidence_id, filename, sha256, ticker):
    return {"evidence_id": evidence_id, "authority": "KPMG Vietnam", "authority_domain": "issuer.example", "ticker": ticker,
        "issuer": f"{ticker} Issuer Co.", "evidence_type": "audited_consolidated_financial_statements",
        "source_url": "https://issuer.example/" + filename, "document_title": f"{ticker} Annual Report",
        "reporting_period": "2024", "publication_date": "2025-02-28", "retrieved_at": "2026-07-28T13:42:50Z",
        "content_type": "application/pdf", "language": "en", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "official_ir_portal", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _cash_citation(ticker, res_num, decl_date, cash_amt, pay_date, evidence_id, rec_date=None, ex_date=None,
                    status="completed", currency="VND", event_type="cash_dividend", citation_id=None):
    citation_id = citation_id or _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": res_num,
        "declaration_date": decl_date, "cash_amount": cash_amt, "payment_date": pay_date,
        "event_status": status, "evidence_id": evidence_id,
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_dividend_date": ex_date, "payment_date": pay_date, "cash_amount": cash_amt,
        "currency": currency, "event_status": status, "supersedes_citation_ids": [],
        "evidence_id": evidence_id, "citation": {"note_number": "Annual Report p. 33"},
        "verified_at": "2026-07-29T11:04:07Z", "schema_version": "1.0.0",
    }


def _non_cash_citation(ticker, event_type, res_num, decl_date, num, den, evidence_id,
                        rec_date=None, ex_date=None, dist_date=None, funding="undistributed_earnings",
                        status="completed"):
    citation_id = _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": res_num,
        "declaration_date": decl_date, "ratio_numerator": num, "ratio_denominator": den,
        "ex_rights_date": ex_date, "event_status": status, "evidence_id": evidence_id,
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": res_num, "declaration_date": decl_date, "record_date": rec_date,
        "ex_rights_date": ex_date, "distribution_date": dist_date, "ratio_numerator": num,
        "ratio_denominator": den, "funding_source": funding, "event_status": status,
        "supersedes_citation_ids": [], "evidence_id": evidence_id,
        "citation": {"note_number": "Annual Report p. 33"},
        "verified_at": "2026-07-29T11:04:07Z", "schema_version": "1.0.0",
    }


def _write_runtime(root, ticker, cash_citations=(), non_cash_citations=(), pdf_bytes=None):
    pdf_bytes = pdf_bytes if pdf_bytes is not None else f"%PDF-1.4 test {ticker} evidence".encode()
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker)
    filename = f"{ticker.lower()}.pdf"
    (evidence_dir / filename).write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, filename, sha256, ticker)]}),
        encoding="utf-8",
    )
    with (evidence_dir / "cash_dividend_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in cash_citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (evidence_dir / "non_cash_event_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in non_cash_citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return evidence_id


def _vnm_two_period_runtime(root):
    """Synthetic fixture shaped after the real retained VNM evidence closeout
    (operations-review/vnm-2024-cash-dividend-official-evidence: VND 500/share, record
    2024-12-27, payment 2025-02-28) plus a second, distinct-year qualified event -- real
    retained data covers only one period, so a second synthetic period is required here to
    exercise the >=2-distinct-period recurring-history path. Also carries one stock-dividend
    and one bonus-share non-cash event for the cash/non-cash separation checks."""
    pdf_bytes = b"%PDF-1.4 test VNM distribution evidence"
    evidence_id = _write_runtime(
        root, "VNM",
        cash_citations=[
            _cash_citation("VNM", "15/NQ-CTS.HĐQT/2024", "2024-12-05", 500, "2025-02-28",
                            _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM"),
                            rec_date="2024-12-27"),
            _cash_citation("VNM", "07/NQ-CTS.HĐQT/2023", "2023-08-10", 1500, "2023-10-20",
                            _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM"),
                            rec_date="2023-09-05"),
        ],
        non_cash_citations=[
            _non_cash_citation("VNM", "stock_dividend", "05/NQ-CTS.HĐQT/2021", "2021-06-15", 1, 10,
                                _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM"),
                                rec_date="2021-07-20"),
            _non_cash_citation("VNM", "bonus_share", "08/NQ-CTS.HĐQT/2022", "2022-05-18", 1, 5,
                                _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM"),
                                rec_date="2022-06-22"),
        ],
        pdf_bytes=pdf_bytes,
    )
    return evidence_id


# ---------------------------------------------------------------------------
# 1. Generic event qualification (no ticker-specific branch)
# ---------------------------------------------------------------------------

class GenericQualificationTests(unittest.TestCase):
    def test_arbitrary_ticker_not_named_vnm_or_hpg_qualifies_through_the_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test PNJ evidence"
            ev_id = _write_runtime(
                root, "PNJ",
                cash_citations=[
                    _cash_citation("PNJ", "01/2024", "2024-03-01", 3000, "2024-04-01",
                                    _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "PNJ"), rec_date="2024-03-15"),
                    _cash_citation("PNJ", "01/2023", "2023-03-01", 3000, "2023-04-01",
                                    _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "PNJ"), rec_date="2023-03-15"),
                ],
                pdf_bytes=pdf_bytes,
            )
            result = de.build_distribution_evidence_for_ticker(root, "PNJ")
            self.assertEqual(result["coverage_status"], "available")
            self.assertEqual(result["ticker"], "PNJ")
            self.assertEqual(result["qualified_cash_event_count"], 2)
            self.assertEqual(result["history_status"], "multi_period_available")

    def test_no_ticker_literal_present_in_module_source(self):
        source = (ROOT / "distribution_evidence.py").read_text(encoding="utf-8")
        for literal in ('"VNM"', "'VNM'", '"HPG"', "'HPG'"):
            self.assertNotIn(literal, source)


# ---------------------------------------------------------------------------
# 2. Cash / non-cash separation
# ---------------------------------------------------------------------------

class CashNonCashSeparationTests(unittest.TestCase):
    def test_cash_and_non_cash_events_are_kept_in_separate_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")

            self.assertEqual(len(result["cash_distributions"]), 2)
            self.assertEqual(len(result["non_cash_distributions"]), 2)
            self.assertTrue(all(e["distribution_type"] == "cash_distribution" for e in result["cash_distributions"]))
            self.assertEqual(
                sorted(e["distribution_type"] for e in result["non_cash_distributions"]),
                ["bonus_share", "stock_dividend"],
            )
            # No non-cash event leaks amount/currency/cash fields, and vice versa.
            for entry in result["non_cash_distributions"]:
                self.assertNotIn("amount", entry)
                self.assertNotIn("currency", entry)
            for entry in result["cash_distributions"]:
                self.assertNotIn("entitlement_ratio", entry)

    def test_non_cash_events_never_counted_toward_qualified_cash_event_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["qualified_cash_event_count"], len(result["cash_distributions"]))
            self.assertEqual(result["qualified_cash_event_count"], 2)


# ---------------------------------------------------------------------------
# 3. VNM exact-evidence qualification (positive vertical slice)
# ---------------------------------------------------------------------------

class VNMQualificationTests(unittest.TestCase):
    def test_vnm_two_period_cash_history_qualifies_available_multi_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")

            self.assertEqual(result["coverage_status"], "available")
            self.assertEqual(result["history_status"], "multi_period_available")
            self.assertEqual(result["covered_periods"], ["2023", "2024"])
            self.assertEqual(result["blocking_reasons"], [])
            self.assertIs(result["is_actionable"], False)

            latest = result["latest_cash_distribution"]
            self.assertEqual(latest["record_date"], "2024-12-27")
            self.assertEqual(latest["amount"], 500)
            self.assertEqual(latest["currency"], "VND")
            self.assertEqual(latest["unit"], "per_share")
            self.assertIsNotNone(latest["per_share_basis"])

    def test_vnm_single_period_only_does_not_claim_recurring_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test VNM single period"
            ev_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM")
            _write_runtime(root, "VNM", cash_citations=[
                _cash_citation("VNM", "15/NQ-CTS.HĐQT/2024", "2024-12-05", 500, "2025-02-28", ev_id, rec_date="2024-12-27"),
            ], pdf_bytes=pdf_bytes)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "available")
            self.assertEqual(result["history_status"], "single_period_only")
            self.assertTrue(any("fewer than two" in lim for lim in result["limitations"]))

    def test_vnm_with_no_retained_citations_emits_fail_closed_missing_contract(self):
        """If retained VNM data does not support qualified cash history, the contract must
        emit the fail-closed shape -- never force availability."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "missing")
            self.assertEqual(result["cash_distributions"], [])
            self.assertEqual(result["non_cash_distributions"], [])
            self.assertIsNone(result["latest_cash_distribution"])
            self.assertEqual(result["qualified_cash_event_count"], 0)
            self.assertEqual(result["history_status"], "no_qualified_events")
            self.assertIs(result["is_actionable"], False)


# ---------------------------------------------------------------------------
# 4. HPG negative / control behavior
# ---------------------------------------------------------------------------

class HPGControlTests(unittest.TestCase):
    def test_hpg_with_no_retained_distribution_evidence_stays_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = de.build_distribution_evidence_for_ticker(root, "HPG")
            self.assertEqual(result["coverage_status"], "missing")
            self.assertEqual(result["qualified_cash_event_count"], 0)
            self.assertIs(result["is_actionable"], False)

    def test_hpg_stays_missing_even_when_vnm_has_qualified_evidence_in_same_store(self):
        """No cross-ticker leakage: HPG must not inherit VNM's qualified events."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            hpg_result = de.build_distribution_evidence_for_ticker(root, "HPG")
            self.assertEqual(hpg_result["coverage_status"], "missing")
            self.assertEqual(hpg_result["cash_distributions"], [])
            self.assertEqual(hpg_result["non_cash_distributions"], [])


# ---------------------------------------------------------------------------
# 5. Hash / identity / unit / type conflicts fail closed
# ---------------------------------------------------------------------------

class FailClosedConflictTests(unittest.TestCase):
    def test_tampered_evidence_document_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            (root / "data" / "official-evidence" / "vnm.pdf").write_bytes(b"tampered pdf content")
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "conflict")
            self.assertIn("evidence_missing_or_hash_mismatch", result["blocking_reasons"])
            self.assertEqual(result["cash_distributions"], [])

    def test_conflicting_citations_same_identity_different_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"
            ev_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM")
            cit1 = _cash_citation("VNM", "13/2024", "2024-08-22", 1500, "2024-10-24", ev_id, rec_date="2024-09-25")
            cit2 = dict(cit1)
            cit2["payment_date"] = "2099-01-01"
            cit2["citation_id"] = "cit_conflict"
            _write_runtime(root, "VNM", cash_citations=[cit1, cit2], pdf_bytes=pdf_bytes)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "conflict")
            self.assertIn("conflicting_citations", result["blocking_reasons"])

    def test_unsupported_currency_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"
            ev_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM")
            cit = _cash_citation("VNM", "13/2024", "2024-08-22", 1500, "2024-10-24", ev_id, rec_date="2024-09-25", currency="USD")
            _write_runtime(root, "VNM", cash_citations=[cit], pdf_bytes=pdf_bytes)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "conflict")
            self.assertIn("unsupported_currency", result["blocking_reasons"])
            self.assertEqual(result["cash_distributions"], [])

    def test_unsupported_event_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"
            ev_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM")
            cit = _cash_citation("VNM", "13/2024", "2024-08-22", 1500, "2024-10-24", ev_id,
                                  rec_date="2024-09-25", event_type="special_dividend")
            _write_runtime(root, "VNM", cash_citations=[cit], pdf_bytes=pdf_bytes)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "conflict")
            self.assertIn("unsupported_event_type", result["blocking_reasons"])

    def test_invalid_entitlement_ratio_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test"
            ev_id = _evidence_id(hashlib.sha256(pdf_bytes).hexdigest(), "VNM")
            cit = _non_cash_citation("VNM", "stock_dividend", "05/2021", "2021-06-15", 1, 0, ev_id, rec_date="2021-07-20")
            _write_runtime(root, "VNM", non_cash_citations=[cit], pdf_bytes=pdf_bytes)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(result["coverage_status"], "conflict")
            self.assertIn("invalid_entitlement_ratio", result["blocking_reasons"])


# ---------------------------------------------------------------------------
# 6. No yield / payout / CAGR / return is derived
# ---------------------------------------------------------------------------

class NoDerivedMetricsTests(unittest.TestCase):
    _FORBIDDEN_SUBSTRINGS = ("yield", "payout", "cagr", "total_return", "adjusted_return", "adjusted_price")

    def _assert_no_forbidden_keys(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                for forbidden in self._FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(forbidden, lowered, f"forbidden derived-metric key found: {key!r}")
                self._assert_no_forbidden_keys(value)
        elif isinstance(node, list):
            for item in node:
                self._assert_no_forbidden_keys(item)

    def test_qualified_vnm_contract_carries_no_derived_investment_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            result = de.build_distribution_evidence_for_ticker(root, "VNM")
            self._assert_no_forbidden_keys(result)


# ---------------------------------------------------------------------------
# 7 & 8. income_defensive gate: blocked without qualified history, eligible only with it
# ---------------------------------------------------------------------------

_VERIFIED_FPC = {
    "ticker": "TEST", "latest_raw_period": "2024", "latest_calendar_eligible_period": "2024",
    "latest_verified_period": "2024", "latest_complete_period": None,
    "coverage_status": "verified_only", "limitations": [], "is_actionable": False,
}
_NOT_OBSERVED_ANOMALY = {"status": "not_observed", "explanation_status": None, "limitations": [], "is_actionable": False}
_AVAILABLE_DISTRIBUTION_EVIDENCE = {
    "schema_version": "1.0.0", "ticker": "TEST", "coverage_status": "available",
    "cash_distributions": [{"event_id": "e1"}], "non_cash_distributions": [],
    "latest_cash_distribution": {"event_id": "e1"}, "qualified_cash_event_count": 1,
    "covered_periods": ["2023", "2024"], "history_status": "multi_period_available",
    "blocking_reasons": [], "limitations": [], "provenance": {}, "is_actionable": False,
}


class IncomeDefensiveGateTests(unittest.TestCase):
    def test_default_call_without_distribution_evidence_stays_insufficient_evidence(self):
        """Backward compatibility: omitting distribution_evidence entirely must not crash
        and must behave the same as before Phase 5D wired this in."""
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None,
            share_basis_identities=None, financial_period_coverage=_VERIFIED_FPC,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("distribution_evidence_unavailable", result["blocking_reasons"])
        self.assertFalse(result["eligible"])

    def test_missing_coverage_status_blocks_eligibility(self):
        missing = {**_AVAILABLE_DISTRIBUTION_EVIDENCE, "coverage_status": "missing", "history_status": "no_qualified_events", "cash_distributions": [], "qualified_cash_event_count": 0}
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=missing,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["eligible"])

    def test_single_period_history_is_not_sufficient_for_eligibility(self):
        single = {**_AVAILABLE_DISTRIBUTION_EVIDENCE, "history_status": "single_period_only", "covered_periods": ["2024"]}
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=single,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["eligible"])

    def test_conflict_coverage_status_blocks_the_lane(self):
        conflict = {**_AVAILABLE_DISTRIBUTION_EVIDENCE, "coverage_status": "conflict", "blocking_reasons": ["evidence_missing_or_hash_mismatch"]}
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=conflict,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("evidence_missing_or_hash_mismatch" in r for r in result["blocking_reasons"]))

    def test_malformed_distribution_evidence_blocks_the_lane(self):
        malformed = {"coverage_status": "not_a_real_state", "blocking_reasons": "not_a_list"}
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=malformed,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("distribution_evidence_malformed", result["blocking_reasons"])

    def test_unresolved_earnings_anomaly_blocks_the_lane_even_with_full_distribution_evidence(self):
        anomaly = {"status": "anomaly_observed", "explanation_status": "insufficient_statement_detail", "limitations": [], "is_actionable": False}
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=anomaly,
            distribution_evidence=_AVAILABLE_DISTRIBUTION_EVIDENCE,
        )
        self.assertEqual(result["status"], "blocked")

    def test_fully_evidenced_synthetic_input_reaches_eligible_for_analysis(self):
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=_AVAILABLE_DISTRIBUTION_EVIDENCE,
        )
        self.assertEqual(result["status"], "eligible_for_analysis")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["blocking_reasons"], [])
        self.assertIs(result["is_actionable"], False)

    def test_is_actionable_always_false_regardless_of_eligibility(self):
        for result in (
            ale.evaluate_income_defensive("TEST", entity_type=None, risk_semantics=None, share_basis_identities=None, financial_period_coverage=None),
            ale.evaluate_income_defensive("TEST", entity_type="corporate", risk_semantics=None, share_basis_identities=None, financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY, distribution_evidence=_AVAILABLE_DISTRIBUTION_EVIDENCE),
        ):
            self.assertIs(result["is_actionable"], False)

    def test_real_vnm_fixture_contract_reaches_eligible_for_analysis_via_lane(self):
        """End-to-end: the real distribution_evidence.py builder output (from the VNM
        two-period fixture) is accepted as-is by the lane evaluator with no adaptation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            contract = de.build_distribution_evidence_for_ticker(root, "VNM")
        result = ale.evaluate_income_defensive(
            "VNM", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=contract,
        )
        self.assertEqual(result["status"], "eligible_for_analysis")

    def test_real_hpg_fixture_contract_stays_blocked_via_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = de.build_distribution_evidence_for_ticker(root, "HPG")
        result = ale.evaluate_income_defensive(
            "HPG", entity_type="corporate", risk_semantics=None, share_basis_identities=None,
            financial_period_coverage=_VERIFIED_FPC, earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            distribution_evidence=contract,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["eligible"])


# ---------------------------------------------------------------------------
# 9. Other lanes are unchanged by distribution_evidence
# ---------------------------------------------------------------------------

class OtherLanesUnchangedTests(unittest.TestCase):
    def test_other_four_lanes_byte_identical_with_and_without_distribution_evidence(self):
        common_kwargs = dict(
            entity_type="corporate",
            financial_period_coverage=_VERIFIED_FPC,
            valuation_namespaces=None,
            share_basis_identities=None,
            earnings_anomaly=_NOT_OBSERVED_ANOMALY,
            risk_semantics=None,
            opportunity_ranking=None,
            ta_signal_semantics=None,
            news_window_semantics=None,
            price_basis_provenance=None,
        )
        without = ale.evaluate_ticker_lanes("TEST", **copy.deepcopy(common_kwargs))
        with_evidence = ale.evaluate_ticker_lanes(
            "TEST", distribution_evidence=copy.deepcopy(_AVAILABLE_DISTRIBUTION_EVIDENCE), **copy.deepcopy(common_kwargs)
        )

        other_lanes = ("quality_growth", "structural_catalyst", "distressed_high_risk", "blocked_avoid")
        by_lane_without = {r["lane"]: r for r in without}
        by_lane_with = {r["lane"]: r for r in with_evidence}
        for lane in other_lanes:
            self.assertEqual(by_lane_without[lane], by_lane_with[lane], f"lane {lane!r} changed by distribution_evidence")

        self.assertNotEqual(by_lane_without["income_defensive"], by_lane_with["income_defensive"])
        self.assertEqual(by_lane_with["income_defensive"]["status"], "eligible_for_analysis")


# ---------------------------------------------------------------------------
# 10. Determinism
# ---------------------------------------------------------------------------

class DeterminismTests(unittest.TestCase):
    def test_build_distribution_evidence_for_ticker_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            first = de.build_distribution_evidence_for_ticker(root, "VNM")
            second = de.build_distribution_evidence_for_ticker(root, "VNM")
            self.assertEqual(first, second)

    def test_evaluate_ticker_lanes_with_distribution_evidence_is_deterministic(self):
        kwargs = dict(
            entity_type="corporate", financial_period_coverage=_VERIFIED_FPC,
            earnings_anomaly=_NOT_OBSERVED_ANOMALY, distribution_evidence=_AVAILABLE_DISTRIBUTION_EVIDENCE,
        )
        first = ale.evaluate_ticker_lanes("VNM", **copy.deepcopy(kwargs))
        second = ale.evaluate_ticker_lanes("VNM", **copy.deepcopy(kwargs))
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# Bonus: Producer opt-in wiring (export_ai_bundle.py) stays disabled by default
# ---------------------------------------------------------------------------

class ProducerOptInWiringTests(unittest.TestCase):
    def test_disabled_by_default_attaches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            entries = {"VNM": {"ticker": "VNM"}}
            bundle_mod.attach_distribution_evidence(entries, root, include=False)
            self.assertNotIn("distribution_evidence", entries["VNM"])

    def test_enabled_attaches_the_full_contract_per_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            entries = {"VNM": {"ticker": "VNM"}, "HPG": {"ticker": "HPG"}}
            bundle_mod.attach_distribution_evidence(entries, root, include=True)
            self.assertEqual(entries["VNM"]["distribution_evidence"]["coverage_status"], "available")
            self.assertEqual(entries["HPG"]["distribution_evidence"]["coverage_status"], "missing")

    def test_lane_eligibility_wrapper_consumes_the_attached_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _vnm_two_period_runtime(root)
            entry = {
                "ticker": "VNM", "entity_type": "corporate",
                "financial_period_coverage": _VERIFIED_FPC,
                "earnings_anomaly": _NOT_OBSERVED_ANOMALY,
                "distribution_evidence": de.build_distribution_evidence_for_ticker(root, "VNM"),
            }
            results = bundle_mod.build_analysis_lane_eligibility_for_ticker("VNM", entry, price_basis_provenance=None)
            income_defensive = next(r for r in results if r["lane"] == "income_defensive")
            self.assertEqual(income_defensive["status"], "eligible_for_analysis")


if __name__ == "__main__":
    unittest.main()
