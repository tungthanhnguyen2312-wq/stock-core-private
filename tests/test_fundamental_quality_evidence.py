# ==========================================================================
# Focused tests for Phase 6A fundamental_quality_evidence.py (the sole qualifying
# candidate model: single-period earnings quality / cash conversion) and its opt-in
# wiring in export_ai_bundle.py. Pure unit tests against synthetic canonical-record
# dicts, plus one real-data cross-check against the already-generated Phase 5D bundle.
# Run: `python -m unittest tests.test_fundamental_quality_evidence` from the repo root.
# ==========================================================================

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export_ai_bundle as bundle_mod  # noqa: E402
import fundamental_quality_evidence as fqe  # noqa: E402


def _record(metric, value, period="2024", scope="consolidated", currency="VND", scale=1,
            period_type="annual", quality_state="available", derivation_status="direct",
            observation_ids=None, citation_id="cit-1", evidence_id="ev-1"):
    return {
        "canonical_metric": metric, "value": value,
        "period_identity": {"period": period, "period_type": period_type},
        "statement_scope": scope, "currency": currency, "unit_scale": scale,
        "quality_state": quality_state, "derivation_status": derivation_status,
        "observation_ids": observation_ids if observation_ids is not None else [f"obs-{metric}-{period}"],
        "evidence": {"citation_id": citation_id, "evidence_id": evidence_id},
    }


def _write_manifest(root: Path, evidence_id: str, sha256: str) -> None:
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0.0", "records": [{"evidence_id": evidence_id, "sha256": sha256}]}),
        encoding="utf-8",
    )


_VERIFIED_FPC_2024 = {"ticker": "TEST", "latest_verified_period": "2024", "is_actionable": False}
_CAPITAL_FRESHNESS_2024 = {
    "financial_period_end": "2024-12-31", "source_publication_timestamp": "2025-03-01T00:00:00+00:00",
    "publication_timestamp_qualified": True,
}


def _derived_record(metric, value, components, **kwargs):
    record = _record(metric, value, derivation_status="derived", **kwargs)
    record["evidence"] = {"components": components}
    return record


def _capital_records(cash=200, debt=100, equity=500, minority=20, **kwargs):
    short, long = debt * 3 // 5, debt - (debt * 3 // 5)
    records = [
        _record("cash_and_equivalents", cash, **kwargs),
        _record("short_term_borrowings", short, **kwargs),
        _record("long_term_borrowings", long, **kwargs),
        _record("total_equity", equity + minority, **kwargs),
        _record("minority_interest_equity", minority, **kwargs),
    ]
    records.append(_derived_record("total_debt", debt, [
        {**records[1], "evidence_id": "ev-1", "citation_id": "cit-short"},
        {**records[2], "evidence_id": "ev-1", "citation_id": "cit-long"},
    ], **kwargs))
    records.append(_derived_record("shareholders_equity", equity, [
        {**records[3], "evidence_id": "ev-1", "citation_id": "cit-total-equity"},
        {**records[4], "evidence_id": "ev-1", "citation_id": "cit-minority"},
    ], **kwargs))
    return {"records": records}


class InputQualificationAndFormulaTests(unittest.TestCase):
    def test_qualified_inputs_and_correct_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "deadbeef" * 8)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "available")
            self.assertEqual(result["reporting_period"], "2024")
            self.assertEqual(result["statement_scope"], "consolidated")
            self.assertEqual(result["metrics"]["cash_conversion_ratio"], 2.5)
            self.assertEqual(result["metrics"]["operating_cash_flow_less_net_income"], 600)
            for entry in result["inputs"]:
                self.assertEqual(entry["qualification_status"], "qualified")
                self.assertEqual(entry["source_hash"], "deadbeef" * 8)
                self.assertIsNotNone(entry["citation_id"])
                self.assertIsNotNone(entry["evidence_id"])
                self.assertTrue(entry["observation_id"])
                self.assertEqual(entry["currency"], "VND")
                self.assertEqual(entry["scale"], 1)
                self.assertEqual(entry["reporting_frequency"], "annual")

    def test_zero_denominator_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "cafebabe" * 8)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 0, evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertIn("net_income_zero_denominator", result["blocking_reasons"])
            self.assertEqual(result["metrics"], {})


class HistoricalCapitalStructureTests(unittest.TestCase):
    def _build(self, canonical, freshness=_CAPITAL_FRESHNESS_2024):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            return fqe.build_historical_capital_structure_analysis(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, freshness, root,
            )

    def test_aligned_inputs_derive_metrics_and_preserve_market_blockers(self):
        result = self._build(_capital_records())
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["metrics"]["gross_debt"]["value"], 100)
        self.assertEqual(result["metrics"]["net_debt"]["value"], -100)
        self.assertEqual(result["metrics"]["debt_to_equity"]["value"], 0.2)
        self.assertEqual(result["metrics"]["cash_to_debt"]["value"], 2)
        self.assertEqual(result["metrics"]["minority_interest_to_equity"]["value"], 0.04)
        self.assertTrue(result["historical_only"])
        self.assertFalse(result["market_dependent"])
        self.assertIn("price_basis_unknown_or_unverified", result["data_warnings"])
        self.assertIn("volume_basis_unknown_or_unverified", result["data_warnings"])
        self.assertTrue(next(item for item in result["inputs"] if item["canonical_field_identity"] == "total_debt")["component_provenance"])

    def test_missing_cash_and_debt_component_block_only_affected_metrics(self):
        canonical = _capital_records()
        canonical["records"] = [record for record in canonical["records"] if record["canonical_metric"] != "cash_and_equivalents"]
        result = self._build(canonical)
        self.assertEqual(result["metrics"]["gross_debt"]["qualification_status"], "qualified")
        self.assertEqual(result["metrics"]["cash"]["qualification_status"], "unavailable")
        self.assertEqual(result["metrics"]["debt_to_equity"]["qualification_status"], "qualified")
        canonical = _capital_records()
        debt = next(record for record in canonical["records"] if record["canonical_metric"] == "total_debt")
        debt["evidence"]["components"] = debt["evidence"]["components"][:1]
        result = self._build(canonical)
        self.assertEqual(result["metrics"]["gross_debt"]["qualification_status"], "unavailable")
        self.assertEqual(result["metrics"]["cash"]["qualification_status"], "qualified")

    def test_period_scope_currency_and_scale_mismatches_fail_closed(self):
        for kwargs in ({"period": "2023"}, {"scope": "separate"}, {"currency": "USD"}, {"scale": 1000}):
            canonical = _capital_records()
            target = next(record for record in canonical["records"] if record["canonical_metric"] == "cash_and_equivalents")
            if "period" in kwargs:
                target["period_identity"]["period"] = kwargs["period"]
            if "scope" in kwargs:
                target["statement_scope"] = kwargs["scope"]
            if "currency" in kwargs:
                target["currency"] = kwargs["currency"]
            if "scale" in kwargs:
                target["unit_scale"] = kwargs["scale"]
            result = self._build(canonical)
            self.assertEqual(result["metrics"]["cash"]["qualification_status"], "unavailable" if "period" in kwargs or "scope" in kwargs else "qualified")
            self.assertEqual(result["status"], "partial")
            if "currency" in kwargs or "scale" in kwargs:
                self.assertEqual(result["metrics"]["net_debt"]["qualification_status"], "unavailable")
                self.assertEqual(result["metrics"]["cash_to_debt"]["qualification_status"], "unavailable")

    def test_nonpositive_equity_and_missing_minority_are_explicit(self):
        canonical = _capital_records(equity=0)
        result = self._build(canonical)
        self.assertEqual(result["metrics"]["debt_to_equity"]["qualification_status"], "unavailable")
        self.assertIn("shareholders_equity_nonpositive_or_unqualified", result["blocking_reasons"])
        canonical = _capital_records()
        canonical["records"] = [record for record in canonical["records"] if record["canonical_metric"] != "minority_interest_equity"]
        result = self._build(canonical)
        self.assertEqual(result["metrics"]["minority_interest_to_equity"]["qualification_status"], "unavailable")

    def test_deterministic_and_publication_timestamp_required(self):
        canonical = _capital_records()
        first = self._build(copy.deepcopy(canonical))
        second = self._build(copy.deepcopy(canonical))
        self.assertEqual(first, second)
        result = self._build(canonical, {})
        self.assertIn("financial_publication_timestamp_unqualified", result["blocking_reasons"])


class HistoricalFundamentalBriefTests(unittest.TestCase):
    def _brief(self, capital=None, earnings=None):
        capital = capital or {"reporting_period": "2024", "publication_timestamp": "2025-03-01", "statement_scope": "consolidated", "currency": "VND", "scale": 1, "data_warnings": [], "metrics": {
            "net_debt": {"value": 25, "qualification_status": "qualified", "numerator_identity": "total_debt_less_cash_and_equivalents", "denominator_identity": None},
            "cash": {"value": 75, "qualification_status": "qualified", "numerator_identity": "cash_and_equivalents", "denominator_identity": None},
            "gross_debt": {"value": 100, "qualification_status": "qualified", "numerator_identity": "total_debt", "denominator_identity": None},
            "cash_to_debt": {"value": .75, "qualification_status": "qualified", "numerator_identity": "cash_and_equivalents", "denominator_identity": "total_debt"},
        }}
        earnings = earnings if earnings is not None else {"status": "available", "metrics": {"cash_conversion_ratio": 1.2}}
        return fqe.build_historical_fundamental_brief("TEST", earnings, capital)

    def test_qualified_facts_are_deterministic_and_historical_only(self):
        first, second = self._brief(), self._brief()
        self.assertEqual(first, second)
        self.assertTrue(first["historical_only"])
        self.assertFalse(first["market_dependent"])
        self.assertEqual(first["hypotheses"], [])
        self.assertIn("cash_to_debt", {fact["identity"] for fact in first["facts"]})
        self.assertIn("Net debt was positive", first["supported_inferences"][0]["statement"])

    def test_missing_metric_is_excluded_warned_and_market_blockers_remain(self):
        capital = self._brief()["facts"]
        brief = self._brief({"metrics": {"net_debt": {"value": None, "qualification_status": "unavailable", "blocking_reason": "cash_unqualified"}}})
        self.assertNotIn("net_debt", {fact["identity"] for fact in brief["facts"]})
        self.assertIn("net_debt:cash_unqualified", brief["data_warnings"])
        for warning in ("price_basis_unknown_or_unverified", "volume_basis_unknown_or_unverified", "current_shares_unqualified"):
            self.assertIn(warning, brief["data_warnings"])

    def test_no_scoring_or_recommendation_fields(self):
        brief = self._brief()
        serialized = json.dumps(brief).lower()
        for forbidden in ("score", "rank", "recommendation", "target_price"):
            self.assertNotIn(f'"{forbidden}', serialized)


class RealRetainedEvidenceTests(unittest.TestCase):
    """Requirement 6: HPG and VNM results must follow their real retained evidence."""

    _BUNDLE_PATH = ROOT / "operations-review" / "phase_5d_distribution_evidence_20260801T104910Z" / "bundle_output" / "analysis_bundle.json"
    _RUNTIME_ROOT = ROOT.parent / "dashboard-runtime"

    def _real_result(self, ticker: str) -> dict:
        with self._BUNDLE_PATH.open(encoding="utf-8") as handle:
            bundle = json.load(handle)
        entry = bundle["tickers"][ticker]
        return fqe.build_fundamental_quality_evidence_for_ticker(
            ticker, entry.get("entity_type"), entry.get("financial_canonical"),
            entry.get("financial_period_coverage"), self._RUNTIME_ROOT,
        )

    def test_hpg_qualifies_from_real_retained_fy2024_evidence(self):
        result = self._real_result("HPG")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["reporting_period"], "2024")
        self.assertAlmostEqual(result["metrics"]["cash_conversion_ratio"], 6608320655215 / 12021443836074)
        self.assertEqual(result["metrics"]["operating_cash_flow_less_net_income"], 6608320655215 - 12021443836074)
        self.assertEqual(result["blocking_reasons"], [])

    def test_vnm_qualifies_from_real_retained_fy2024_evidence(self):
        result = self._real_result("VNM")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["reporting_period"], "2024")
        self.assertAlmostEqual(result["metrics"]["cash_conversion_ratio"], 9685937539346 / 9392310356250)
        self.assertEqual(result["metrics"]["operating_cash_flow_less_net_income"], 9685937539346 - 9392310356250)
        self.assertEqual(result["blocking_reasons"], [])

    def test_real_source_hash_matches_retained_manifest(self):
        manifest = json.loads((self._RUNTIME_ROOT / "data" / "official-evidence" / "manifest.json").read_text(encoding="utf-8"))
        by_id = {r["evidence_id"]: r["sha256"] for r in manifest["records"]}
        for ticker in ("HPG", "VNM"):
            result = self._real_result(ticker)
            for entry in result["inputs"]:
                self.assertEqual(entry["source_hash"], by_id[entry["evidence_id"]])


class FailClosedMismatchTests(unittest.TestCase):
    def test_period_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, period="2024", evidence_id="ev-1"),
                _record("net_income", 400, period="2023", evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["metrics"], {})

    def test_scope_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, scope="consolidated", evidence_id="ev-1"),
                _record("net_income", 400, scope="separate", evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["metrics"], {})

    def test_currency_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, currency="VND", evidence_id="ev-1"),
                _record("net_income", 400, currency="USD", evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "conflict")
            self.assertIn("currency_or_scale_mismatch_across_required_inputs", result["blocking_reasons"])
            self.assertEqual(result["metrics"], {})

    def test_scale_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, scale=1, evidence_id="ev-1"),
                _record("net_income", 400, scale=1000, evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "conflict")
            self.assertEqual(result["metrics"], {})


class MissingOrConflictingInputTests(unittest.TestCase):
    def test_missing_required_metric_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [_record("operating_cash_flow", 1000, evidence_id="ev-1")]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            net_income_input = next(e for e in result["inputs"] if e["canonical_field_identity"] == "net_income")
            self.assertEqual(net_income_input["rejection_reason"], "no_qualified_consolidated_annual_record_for_period")

    def test_conflicting_observations_same_period_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-1", citation_id="cit-a"),
                _record("net_income", 999, evidence_id="ev-1", citation_id="cit-b"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "conflict")
            net_income_input = next(e for e in result["inputs"] if e["canonical_field_identity"] == "net_income")
            self.assertEqual(net_income_input["rejection_reason"], "conflicting_observations_same_period")

    def test_missing_citation_lineage_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            record = _record("net_income", 400, evidence_id="ev-1")
            record["evidence"] = {"citation_id": None, "evidence_id": None}
            canonical = {"records": [_record("operating_cash_flow", 1000, evidence_id="ev-1"), record]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            net_income_input = next(e for e in result["inputs"] if e["canonical_field_identity"] == "net_income")
            self.assertEqual(net_income_input["rejection_reason"], "missing_citation_lineage")

    def test_unresolvable_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-not-in-manifest"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["status"], "unavailable")
            net_income_input = next(e for e in result["inputs"] if e["canonical_field_identity"] == "net_income")
            self.assertEqual(net_income_input["rejection_reason"], "evidence_hash_unresolvable_against_manifest")


class ApplicabilityTests(unittest.TestCase):
    def test_bank_entity_type_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fqe.build_fundamental_quality_evidence_for_ticker("VCB", "bank", {"records": []}, None, root)
            self.assertEqual(result["applicability"], "not_applicable")
            self.assertEqual(result["status"], "not_applicable")

    def test_unknown_entity_type_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fqe.build_fundamental_quality_evidence_for_ticker("TEST", None, {"records": []}, None, root)
            self.assertEqual(result["applicability"], "not_applicable")


class NoUnverifiedComparativePeriodTests(unittest.TestCase):
    def test_only_the_verified_period_is_used_even_when_other_periods_are_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, period="2024", evidence_id="ev-1"),
                _record("net_income", 400, period="2024", evidence_id="ev-1"),
                _record("operating_cash_flow", 5000, period="2023", evidence_id="ev-1"),
                _record("net_income", 2000, period="2023", evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, _VERIFIED_FPC_2024, root,
            )
            self.assertEqual(result["reporting_period"], "2024")
            self.assertEqual(result["metrics"]["cash_conversion_ratio"], 2.5)

    def test_no_verified_period_fails_closed_even_with_available_canonical_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-1"),
            ]}
            result = fqe.build_fundamental_quality_evidence_for_ticker(
                "TEST", "corporate", canonical, {"latest_verified_period": None}, root,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertIn("no_verified_financial_period", result["blocking_reasons"])
            self.assertEqual(result["metrics"], {})


class DeterminismTests(unittest.TestCase):
    def test_repeated_calls_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-1"),
            ]}
            first = fqe.build_fundamental_quality_evidence_for_ticker("TEST", "corporate", copy.deepcopy(canonical), _VERIFIED_FPC_2024, root)
            second = fqe.build_fundamental_quality_evidence_for_ticker("TEST", "corporate", copy.deepcopy(canonical), _VERIFIED_FPC_2024, root)
            self.assertEqual(first, second)


class NonActionableAndNoRankingTests(unittest.TestCase):
    _FORBIDDEN = ("score", "rank", "recommendation", "rating", "target_price", "expected_return")

    def _assert_no_forbidden_keys(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                words = set(str(key).lower().split("_"))
                for forbidden in self._FORBIDDEN:
                    self.assertFalse(
                        set(forbidden.split("_")) <= words,
                        f"forbidden key found: {key!r}",
                    )
                self._assert_no_forbidden_keys(value)
        elif isinstance(node, list):
            for item in node:
                self._assert_no_forbidden_keys(item)

    def test_is_actionable_false_and_no_forbidden_keys_on_success_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            canonical = {"records": [
                _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                _record("net_income", 400, evidence_id="ev-1"),
            ]}
            available = fqe.build_fundamental_quality_evidence_for_ticker("TEST", "corporate", canonical, _VERIFIED_FPC_2024, root)
            unavailable = fqe.build_fundamental_quality_evidence_for_ticker("TEST", "corporate", {"records": []}, _VERIFIED_FPC_2024, root)
            for result in (available, unavailable):
                self.assertIs(result["is_actionable"], False)
                self._assert_no_forbidden_keys(result)


class ProducerOptInWiringTests(unittest.TestCase):
    def test_disabled_by_default_attaches_nothing_and_leaves_old_field_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_fundamental_quality = {"schema_version": "1.2.0", "entity_type": "corporate", "models": {"dupont_roe": {"score_or_value": 0.1}}}
            entries = {"HPG": {"ticker": "HPG", "fundamental_quality": copy.deepcopy(old_fundamental_quality)}}
            bundle_mod.attach_fundamental_quality_evidence(entries, root, include=False)
            self.assertNotIn("fundamental_quality_evidence", entries["HPG"])
            self.assertEqual(entries["HPG"]["fundamental_quality"], old_fundamental_quality)

    def test_enabled_adds_new_key_without_disturbing_old_fundamental_quality_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root, "ev-1", "ab" * 32)
            old_fundamental_quality = {"schema_version": "1.2.0", "entity_type": "corporate", "models": {"dupont_roe": {"score_or_value": 0.1}}}
            entries = {"TEST": {
                "ticker": "TEST", "entity_type": "corporate",
                "fundamental_quality": copy.deepcopy(old_fundamental_quality),
                "financial_period_coverage": _VERIFIED_FPC_2024,
                "financial_canonical": {"records": [
                    _record("operating_cash_flow", 1000, evidence_id="ev-1"),
                    _record("net_income", 400, evidence_id="ev-1"),
                ]},
            }}
            bundle_mod.attach_fundamental_quality_evidence(entries, root, include=True)
            self.assertEqual(entries["TEST"]["fundamental_quality"], old_fundamental_quality)
            self.assertEqual(entries["TEST"]["fundamental_quality_evidence"]["status"], "available")


if __name__ == "__main__":
    unittest.main()
