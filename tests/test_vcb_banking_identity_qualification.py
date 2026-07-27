"""VCB FY2024 banking archetype pilot: identity qualification, evidence linkage,
and model applicability. Entity-type-driven throughout -- no ticker-specific
condition anywhere in the source this exercises (see test_no_ticker_specific_branch).
See docs/vcb_fy2024_banking_identity_qualification.md for the cited figures.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import semantic_evidence_bridge as bridge
from financial_observations import append_observations, canonical_records, observations_from_frame, read_observations, store_path
from intrinsic_valuation import evaluate_intrinsic_valuation
from relative_valuation import evaluate_relative_valuation


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


# Real VCB FY2024 consolidated figures (VND), Circular 49/2014/TT-NHNN template,
# cited to the audited statements (Ernst & Young Vietnam Limited, unqualified
# opinion). See docs/vcb_fy2024_banking_identity_qualification.md.
INTEREST_INCOME = 93654841000000
INTEREST_EXPENSE = 38249106000000
NET_INTEREST_INCOME = 55405735000000
OPERATING_EXPENSES = 23027363000000
OPERATING_PROFIT_BEFORE_PROVISION = 45551133000000
TOTAL_OPERATING_INCOME = OPERATING_PROFIT_BEFORE_PROVISION + OPERATING_EXPENSES
PROVISION_FOR_CREDIT_LOSSES = 3314998000000
PROFIT_BEFORE_TAX = 42236135000000
NET_PROFIT_TOTAL = 33853117000000
NET_PROFIT_PARENT = 33831386000000
TOTAL_ASSETS = 2085873522000000
TOTAL_LIABILITIES = 1889664354000000
TOTAL_EQUITY = 196209168000000
MINORITY_INTEREST = 96261000000
PARENT_EQUITY = TOTAL_EQUITY - MINORITY_INTEREST
CUSTOMER_DEPOSITS = 1514664850000000
CUSTOMER_LOANS_NET = 1418015724000000
PERIOD_END_SHARES = 5589091262
WEIGHTED_AVG_SHARES = 5589091262
PRICE_2024_12_31 = 60560.0

BALANCE_ROWS = [
    ("total_assets", TOTAL_ASSETS), ("total_liabilities", TOTAL_LIABILITIES),
    ("owners_equity", TOTAL_EQUITY), ("minority_interest", MINORITY_INTEREST),
    ("deposits_from_customers", CUSTOMER_DEPOSITS),
    ("loans_and_advances_to_customers_net", CUSTOMER_LOANS_NET),
]
INCOME_ROWS = [
    ("interest_income_and_similar_income", INTEREST_INCOME),
    ("interest_expense_and_similar_expenses", INTEREST_EXPENSE),
    ("net_interest_income", NET_INTEREST_INCOME),
    ("operating_profit_before_provision_for_credit_losses", OPERATING_PROFIT_BEFORE_PROVISION),
    ("operating_expenses", OPERATING_EXPENSES),
    ("provision_for_credit_losses", PROVISION_FOR_CREDIT_LOSSES),
    ("profit_before_tax", PROFIT_BEFORE_TAX),
    ("net_profit", NET_PROFIT_TOTAL),
    ("net_profit_atttributable_to_the_equity_holders_of_the_bank", NET_PROFIT_PARENT),
]
# income-statement lines printed in parentheses (subtraction terms) though KBS's
# raw_value is a plain positive magnitude -- must cite the negative, per the
# sign rules added to semantic_evidence_bridge.py for this milestone.
_NEGATIVE_ON_STATEMENT = {"interest_expense_and_similar_expenses", "operating_expenses", "provision_for_credit_losses"}


def _vcb_observations(retrieved_at="2026-07-27T12:23:00+00:00", version="4.0.4"):
    balance = pd.DataFrame([{"item_id": code, "item": code, "2024": value} for code, value in BALANCE_ROWS])
    income = pd.DataFrame([{"item_id": code, "item": code, "2024": value} for code, value in INCOME_ROWS])
    obs = observations_from_frame(balance, ticker="VCB", entity_type="bank", method="balance_sheet",
                                   requested_frequency="year", retrieved_at=retrieved_at, version=version)
    obs += observations_from_frame(income, ticker="VCB", entity_type="bank", method="income_statement",
                                    requested_frequency="year", retrieved_at=retrieved_at, version=version)
    return obs


def _evidence_id(sha256):
    return _hash({"authority_domain": "vietcombank.com.vn", "source_url": "https://example.test/vcb.pdf",
                  "sha256": sha256, "ticker": "VCB", "reporting_period": "2024",
                  "evidence_type": "audited_consolidated_financial_statements"})


def _evidence_record(evidence_id, filename, sha256):
    return {"evidence_id": evidence_id, "authority": "Test Authority", "authority_domain": "vietcombank.com.vn", "ticker": "VCB",
        "issuer": "Test Authority", "evidence_type": "audited_consolidated_financial_statements", "source_url": "https://example.test/" + filename,
        "document_title": "Test statement", "reporting_period": "2024", "publication_date": "2025-03-28", "retrieved_at": "2026-07-27T00:00:00+07:00",
        "content_type": "application/pdf", "language": "vi", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "test", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _citation_for(observation, evidence_id):
    official_value = -observation["raw_value"] if observation["raw_item_id"] in _NEGATIVE_ON_STATEMENT else observation["raw_value"]
    citation_id = _hash({"observation_id": observation["observation_id"], "evidence_id": evidence_id,
                          "raw_item_id": observation["raw_item_id"], "matched_value": official_value})
    return {"schema_version": "1.0.0", "citation_id": citation_id, "observation_id": observation["observation_id"],
            "evidence_id": evidence_id, "ticker": "VCB", "raw_statement_type": observation["raw_statement_type"],
            "raw_item_id": observation["raw_item_id"], "reporting_frequency": observation["reporting_frequency"],
            "reporting_period": observation["reporting_period"], "raw_value": observation["raw_value"],
            "official_value": official_value, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1,
            "citation": {"form_code": "B02/B03-TCTD-HN", "pdf_page": 9, "printed_page": 6, "line_label_vi": "test"},
            "verified_at": "2026-07-27T12:34:00+07:00"}


def _share_citation(evidence_id, identity_type, value):
    citation_id = _hash({"ticker": "VCB", "identity_type": identity_type, "reporting_period": "2024",
                          "evidence_id": evidence_id, "value": value})
    return {"citation": {"form_code": "B05/TCTD-HN", "note_number": "22" if "period_end" in identity_type else "34",
             "par_value_vnd": 10000, "pdf_page": 59, "printed_page": 56},
            "citation_id": citation_id, "evidence_id": evidence_id, "identity_type": identity_type,
            "reporting_frequency": "annual", "reporting_period": "2024", "schema_version": "1.0.0",
            "share_class": "common_outstanding", "ticker": "VCB", "unit": "shares", "value": value,
            "verified_at": "2026-07-27T12:34:00+07:00"}


def _write_vcb_runtime(root, observations=None, skip_raw_item_ids=frozenset()):
    """Full, self-consistent VCB runtime: observations + manifest + qualification
    citations + share-basis citations, mirroring the real evidence built for this
    milestone. skip_raw_item_ids lets a test drop specific citations to exercise
    fail-closed behavior without touching the rest."""
    observations = observations if observations is not None else _vcb_observations()
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = b"%PDF-1.4 test vcb evidence"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256)
    (evidence_dir / "vcb.pdf").write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, "vcb.pdf", sha256)]}), encoding="utf-8")
    append_observations(store_path(root), observations)
    citations = [_citation_for(o, evidence_id) for o in observations if o["raw_item_id"] not in skip_raw_item_ids]
    with (evidence_dir / "qualification_citations.jsonl").open("w", encoding="utf-8") as fh:
        for row in citations:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    share_rows = [
        _share_citation(evidence_id, "period_end_shares_outstanding", PERIOD_END_SHARES),
        _share_citation(evidence_id, "weighted_average_basic_shares_outstanding", WEIGHTED_AVG_SHARES),
    ]
    with (evidence_dir / "share_basis_citations.jsonl").open("w", encoding="utf-8") as fh:
        for row in share_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return evidence_id, observations


def _canonical_vcb(root):
    canonical = canonical_records(store_path(root), {"VCB": "bank"})
    enriched = bridge.enrich_canonical_records(canonical, root)
    return bridge.reconcile_metric_identities(enriched)["VCB"]


def _by_metric(records):
    return {r["canonical_metric"]: r for r in records if r.get("quality_state") == "available"}


class VcbBankingIdentityTests(unittest.TestCase):
    # 1. VCB banking identities exact-match the qualified evidence.
    def test_banking_identities_exact_match_qualified_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            by_metric = _by_metric(_canonical_vcb(root))
            self.assertEqual(by_metric["interest_income"]["value"], INTEREST_INCOME)
            self.assertEqual(by_metric["interest_expense"]["value"], INTEREST_EXPENSE)
            self.assertEqual(by_metric["net_interest_income"]["value"], NET_INTEREST_INCOME)
            self.assertEqual(by_metric["profit_before_tax"]["value"], PROFIT_BEFORE_TAX)
            self.assertEqual(by_metric["total_assets"]["value"], TOTAL_ASSETS)
            self.assertEqual(by_metric["customer_deposits"]["value"], CUSTOMER_DEPOSITS)
            self.assertEqual(by_metric["customer_loans_net"]["value"], CUSTOMER_LOANS_NET)
            self.assertEqual(by_metric["total_operating_income"]["value"], TOTAL_OPERATING_INCOME)
            for metric in ("interest_income", "interest_expense", "net_interest_income", "profit_before_tax",
                           "total_assets", "customer_deposits", "customer_loans_net"):
                self.assertEqual(by_metric[metric]["statement_scope"], "consolidated")
                self.assertIn("evidence", by_metric[metric])

    # 2. Parent profit and total profit remain distinct.
    def test_parent_profit_and_total_profit_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            by_metric = _by_metric(_canonical_vcb(root))
            self.assertEqual(by_metric["net_profit_after_tax_total"]["value"], NET_PROFIT_TOTAL)
            self.assertEqual(by_metric["net_income_attributable_to_parent"]["value"], NET_PROFIT_PARENT)
            self.assertNotEqual(by_metric["net_profit_after_tax_total"]["value"], by_metric["net_income_attributable_to_parent"]["value"])
            # the existing downstream reconciliation exposes it as net_income too (P/E denominator) -- same value, still not net_profit_after_tax_total
            self.assertEqual(by_metric["net_income"]["value"], NET_PROFIT_PARENT)

    # 3. Total equity and parent shareholders' equity remain distinct.
    def test_total_equity_and_parent_shareholders_equity_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            by_metric = _by_metric(_canonical_vcb(root))
            self.assertEqual(by_metric["total_equity"]["value"], TOTAL_EQUITY)
            self.assertEqual(by_metric["shareholders_equity"]["value"], PARENT_EQUITY)
            self.assertNotEqual(by_metric["total_equity"]["value"], by_metric["shareholders_equity"]["value"])
            self.assertEqual(by_metric["minority_interest_equity"]["value"], MINORITY_INTEREST)
            self.assertEqual(by_metric["shareholders_equity"]["derivation_status"], "derived")

    # 4. Customer deposits are not mapped to corporate debt.
    def test_customer_deposits_not_mapped_to_corporate_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            records = _canonical_vcb(root)
            metrics = {r["canonical_metric"] for r in records}
            self.assertIn("customer_deposits", metrics)
            self.assertNotIn("total_debt", metrics)
            self.assertNotIn("total_interest_bearing_debt", metrics)
            by_metric = _by_metric(records)
            self.assertEqual(by_metric["customer_deposits"]["value"], CUSTOMER_DEPOSITS)

    # 5. Total liabilities are not mapped to interest-bearing debt.
    def test_total_liabilities_not_mapped_to_interest_bearing_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            by_metric = _by_metric(_canonical_vcb(root))
            self.assertEqual(by_metric["total_liabilities"]["value"], TOTAL_LIABILITIES)
            self.assertNotIn("total_debt", by_metric)
            self.assertNotEqual(by_metric["total_liabilities"]["value"], by_metric.get("shareholders_equity", {}).get("value"))

    # 6. Banking income identities are not blindly mapped to corporate revenue.
    def test_banking_income_not_blindly_mapped_to_corporate_revenue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            records = _canonical_vcb(root)
            metrics = {r["canonical_metric"] for r in records}
            self.assertIn("interest_income", metrics)
            self.assertIn("net_interest_income", metrics)
            self.assertIn("total_operating_income", metrics)
            self.assertNotIn("revenue", metrics)

    # 7. Period-end and weighted-average shares remain separate.
    def test_period_end_and_weighted_average_shares_remain_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            verified = bridge.load_verified_share_basis(root)
            self.assertEqual(verified["status"], "available")
            period_end = bridge.latest_share_basis(verified["by_identity"], "VCB", "period_end_shares_outstanding")
            weighted = bridge.latest_share_basis(verified["by_identity"], "VCB", "weighted_average_basic_shares_outstanding")
            self.assertIsNotNone(period_end); self.assertIsNotNone(weighted)
            self.assertEqual(period_end["value"], PERIOD_END_SHARES)
            self.assertEqual(weighted["value"], WEIGHTED_AVG_SHARES)
            self.assertIsNone(bridge.latest_share_basis(verified["by_identity"], "VCB", "weighted_average_diluted_shares_outstanding"))

    def _relative_valuation_inputs(self, root):
        verified_price = bridge.load_verified_market_price(root)
        price_entry = {"value": PRICE_2024_12_31, "as_of_date": "2024-12-31", "financial_period": "2024",
                        "source": "VCI:ohlcv", "is_actionable": True}
        by_metric = _by_metric(_canonical_vcb(root))
        share_basis = bridge.load_verified_share_basis(root)
        pe_shares = bridge.latest_share_basis(share_basis["by_identity"], "VCB", "weighted_average_basic_shares_outstanding")
        pb_shares = bridge.latest_share_basis(share_basis["by_identity"], "VCB", "period_end_shares_outstanding")
        return {
            "entity_type": "bank", "current_price": price_entry,
            "share_count_weighted_average_basic": {"value": pe_shares["value"], "semantics": "weighted_average_basic",
                "period_identity": {"period": "2024", "period_type": "annual"}},
            "share_count_period_end": {"value": pb_shares["value"], "semantics": "period_end",
                "period_identity": {"period": "2024", "period_type": "annual"}},
            "financial": by_metric,
        }

    # 8. P/B uses the qualified equity identity and appropriate share basis.
    def test_pb_uses_qualified_parent_equity_and_period_end_shares(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            result = evaluate_relative_valuation(self._relative_valuation_inputs(root), reference_at="2026-07-27T00:00:00+07:00")
            pb = result["methods"]["pb"]
            self.assertEqual(pb["state"], "available")
            self.assertEqual(pb["denominator_identity"], "shareholders_equity")
            expected = (PRICE_2024_12_31 * PERIOD_END_SHARES) / PARENT_EQUITY
            self.assertAlmostEqual(pb["observed_multiple"], expected)

    # 9. P/E uses the qualified earnings identity and appropriate share basis.
    def test_pe_uses_qualified_parent_earnings_and_weighted_average_shares(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            result = evaluate_relative_valuation(self._relative_valuation_inputs(root), reference_at="2026-07-27T00:00:00+07:00")
            pe = result["methods"]["pe"]
            self.assertEqual(pe["state"], "available")
            self.assertEqual(pe["denominator_identity"], "net_income")
            expected = (PRICE_2024_12_31 * WEIGHTED_AVG_SHARES) / NET_PROFIT_PARENT
            self.assertAlmostEqual(pe["observed_multiple"], expected)

    # 10 & 11. EV/EBITDA and EV/Sales are inapplicable, not fabricated.
    def test_ev_ebitda_and_ev_sales_inapplicable_for_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            result = evaluate_relative_valuation(self._relative_valuation_inputs(root), reference_at="2026-07-27T00:00:00+07:00")
            for name in ("ev_ebitda", "ev_sales"):
                method = result["methods"][name]
                self.assertEqual(method["state"], "inapplicable")
                self.assertIsNone(method["observed_multiple"])
                self.assertNotIn(method["observed_multiple"], (0, 0.0))

    # 12. Corporate Net-Net is inapplicable.
    def test_net_net_inapplicable_for_bank(self):
        result = evaluate_intrinsic_valuation({"entity_type": "bank", "financial": {}}, reference_at="2026-07-27T00:00:00+07:00")
        net_net = result["methods"]["net_net"]
        self.assertEqual(net_net["state"], "inapplicable")
        self.assertIsNone(net_net["equity_value"])
        self.assertIsNone(net_net["per_share_value"])

    # 13. Corporate FCFF is inapplicable (or otherwise fail-closed) for a bank.
    def test_fcff_inapplicable_for_bank(self):
        result = evaluate_intrinsic_valuation({"entity_type": "bank", "financial": {}}, reference_at="2026-07-27T00:00:00+07:00")
        fcff = result["methods"]["fcff_dcf"]
        self.assertEqual(fcff["state"], "inapplicable")
        self.assertFalse(fcff["is_actionable"])
        self.assertIsNone(fcff["enterprise_value"])

    # Corporate entity_type is unaffected by the bank gate (net_net/fcff still evaluate normally).
    def test_corporate_entity_type_unaffected_by_bank_gate(self):
        result = evaluate_intrinsic_valuation({"entity_type": "corporate", "financial": {}}, reference_at="2026-07-27T00:00:00+07:00")
        self.assertEqual(result["methods"]["net_net"]["state"], "unavailable")
        self.assertEqual(result["methods"]["fcff_dcf"]["state"], "unavailable")
        self.assertNotEqual(result["methods"]["net_net"]["state"], "inapplicable")

    # 14. Missing evidence leaves individual metrics fail-closed without blocking unrelated qualified metrics.
    def test_missing_evidence_fails_closed_per_metric_not_globally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Drop the citation for profit_before_tax only; every other metric must stay qualified.
            _write_vcb_runtime(root, skip_raw_item_ids={"profit_before_tax"})
            by_metric = _by_metric(_canonical_vcb(root))
            self.assertNotIn("profit_before_tax", by_metric)
            self.assertEqual(by_metric["total_assets"]["value"], TOTAL_ASSETS)
            self.assertEqual(by_metric["customer_deposits"]["value"], CUSTOMER_DEPOSITS)
            self.assertEqual(by_metric["net_interest_income"]["value"], NET_INTEREST_INCOME)
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "available")  # other citations still qualify
            pbt_observation_ids = {o["observation_id"] for o in _vcb_observations() if o["raw_item_id"] == "profit_before_tax"}
            self.assertTrue(pbt_observation_ids.isdisjoint(verified["by_observation_id"]))

    def test_tampered_pdf_fails_closed_without_blocking_other_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_vcb_runtime(root)
            (root / "data" / "official-evidence" / "vcb.pdf").write_bytes(b"tampered")
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["by_observation_id"], {})
            self.assertTrue(verified["rejected"] and all(r["reason"] == "evidence_missing_or_hash_mismatch" for r in verified["rejected"]))

    # 15. No ticker-specific VCB branch exists in the source this milestone touched.
    def test_no_ticker_specific_branch_in_touched_source(self):
        root = Path(__file__).resolve().parents[1]
        touched = ["cash_flow_debt_mapping.py", "financial_observations.py", "semantic_evidence_bridge.py",
                   "relative_valuation.py", "intrinsic_valuation.py"]
        for filename in touched:
            text = (root / filename).read_text(encoding="utf-8")
            self.assertNotIn('"VCB"', text, f"{filename} contains a literal VCB ticker check")
            self.assertNotIn("'VCB'", text, f"{filename} contains a literal VCB ticker check")

    # 16. Append-only and citation idempotence hold.
    def test_append_only_and_citation_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_id, observations = _write_vcb_runtime(root)
            path = store_path(root)
            before = read_observations(path)
            result = append_observations(path, observations)  # re-append the exact same rows
            after = read_observations(path)
            self.assertEqual(len(before), len(after))
            self.assertEqual(result["added"], 0)
            first = bridge.load_verified_citations(root)
            second = bridge.load_verified_citations(root)
            self.assertEqual(first, second)
            first_canonical = _canonical_vcb(root)
            second_canonical = _canonical_vcb(root)
            self.assertEqual(first_canonical, second_canonical)


if __name__ == "__main__":
    unittest.main()
