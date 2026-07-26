import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import semantic_evidence_bridge as bridge
from export_ai_bundle import _financial_input
from financial_observations import append_observations, canonical_records, observations_from_frame, read_observations, store_path


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


# (statement, raw_item_id, raw_value) -- HPG FY2024 annual, exact provider values.
# official_value equals raw_value for every one of these (no sign-presentation rule needed).
ORIGINAL_ROWS = [
    ("balance_sheet", "cash_and_cash_equivalents", 6887646139852),
    ("balance_sheet", "short_term_borrowings", 55882686213459),
    ("balance_sheet", "long_term_borrowings", 27080443256096),
    ("income_statement", "interest_expenses", -2287360810880),  # sign-presentation rule: official unsigned
    ("income_statement", "attributable_to_parent_company", 12021443836074),
    ("cash_flow", "net_cash_inflows_outflows_from_operating_activities", 6608320655215),
    ("cash_flow", "net_cash_inflows_outflows_from_investing_activities", -29788138252448),
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets", -35495026797327),
    ("cash_flow", "net_cash_inflows_outflows_from_financing_activities", 17814697586944),
]
NEW_CORE_ROWS = [
    ("balance_sheet", "total_assets", 224489707553981),
    ("balance_sheet", "owners_equity", 114647457983699),
    ("balance_sheet", "minority_interests", 290990632368),
    ("balance_sheet", "current_assets", 86674276272995),
    ("balance_sheet", "accounts_receivable", 7647800286988),
    ("balance_sheet", "inventories_net", 46091222189472),
    ("balance_sheet", "liabilities", 109842249570282),
    ("income_statement", "net_sales", 138855112131387),
    ("income_statement", "net_profit_loss_after_tax", 12020023621271),
]
ALL_ROWS = ORIGINAL_ROWS + NEW_CORE_ROWS
OFFICIAL_VALUES = {item_id: (abs(value) if item_id == "interest_expenses" else value) for _, item_id, value in ALL_ROWS}
# minority_interests appears once per statement with distinct values in the real filing;
# ORIGINAL_ROWS/NEW_CORE_ROWS never repeat an item_id within the same statement here except
# this one deliberately-omitted case, so a single dict is safe for every other lookup.
NET_INCOME_ATTRIBUTABLE_ITEM = "attributable_to_parent_company"
NET_PROFIT_TOTAL_ITEM = "net_profit_loss_after_tax"


def _make_observations(rows, ticker="HPG", period="2024"):
    by_method = {}
    for statement, item_id, value in rows:
        by_method.setdefault(statement, []).append({"item_id": item_id, "item": item_id, "item_en": item_id, period: value})
    observations = []
    for method, method_rows in by_method.items():
        frame = pd.DataFrame(method_rows)
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


def _full_runtime(tmp, rows=ALL_ROWS):
    root = Path(tmp)
    observations = _make_observations(rows)
    pdf_bytes = b"%PDF-1.4 test consolidated evidence document"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256)
    citations = [_citation_for(obs, OFFICIAL_VALUES[obs["raw_item_id"]], evidence_id) for obs in observations]
    _write_runtime(root, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], citations, {"hpg.pdf": pdf_bytes})
    return root, observations


def _projection(root):
    canonical = canonical_records(store_path(root), {"HPG": "corporate"})
    enriched = bridge.enrich_canonical_records(canonical, root)
    return bridge.reconcile_metric_identities(enriched)["HPG"]


class CoreFinancialObservationExpansionTests(unittest.TestCase):
    def test_append_only_retention_of_new_core_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            path = store_path(root)
            before = path.read_text(encoding="utf-8")
            new_item_ids = {item_id for _, item_id, _ in NEW_CORE_ROWS}
            retained_new = [o for o in observations if o["raw_item_id"] in new_item_ids]
            self.assertEqual(len(retained_new), len(NEW_CORE_ROWS))
            result = append_observations(path, observations)  # re-submit everything, including the new items
            self.assertEqual(result["added"], 0)
            after = path.read_text(encoding="utf-8")
            self.assertEqual(before, after)  # append-only: resubmitting existing rows changes nothing

    def test_exact_evidence_linkage_for_new_core_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            self.assertEqual(len(verified["by_observation_id"]), len(ALL_ROWS))
            new_item_ids = {item_id for _, item_id, _ in NEW_CORE_ROWS}
            new_ids = {o["observation_id"] for o in observations if o["raw_item_id"] in new_item_ids}
            self.assertTrue(new_ids.issubset(verified["by_observation_id"]))
            for obs_id in new_ids:
                entry = verified["by_observation_id"][obs_id]
                self.assertEqual((entry["statement_scope"], entry["currency"], entry["unit_scale"]), ("consolidated", "VND", 1))

    def test_total_versus_attributable_net_income_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            records = _projection(root)
            total = next(r for r in records if r["canonical_metric"] == "net_profit_after_tax_total")
            attributable = next(r for r in records if r["canonical_metric"] == "net_income_attributable_to_parent")
            self.assertNotEqual(total["value"], attributable["value"])
            self.assertEqual(total["value"], OFFICIAL_VALUES[NET_PROFIT_TOTAL_ITEM])
            self.assertEqual(attributable["value"], OFFICIAL_VALUES[NET_INCOME_ATTRIBUTABLE_ITEM])
            reconciled_net_income = next(r for r in records if r["canonical_metric"] == "net_income")
            self.assertEqual(reconciled_net_income["value"], attributable["value"])
            self.assertEqual(reconciled_net_income["identity_reconciliation"]["reconciled_from"], "net_income_attributable_to_parent")
            # the total figure must never be reconciled into the "net_income" downstream slot
            self.assertFalse(any(r["canonical_metric"] == "net_income" and r["value"] == total["value"] for r in records))

    def test_total_equity_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            records = _projection(root)
            total_equity = next(r for r in records if r["canonical_metric"] == "total_equity")
            minority = next(r for r in records if r["canonical_metric"] == "minority_interest_equity")
            shareholders_equity = next(r for r in records if r["canonical_metric"] == "shareholders_equity")
            self.assertEqual(shareholders_equity["value"], total_equity["value"] - minority["value"])
            self.assertEqual(shareholders_equity["quality_state"], "available")
            self.assertEqual(set(shareholders_equity["observation_ids"]), {total_equity["observation_ids"][0], minority["observation_ids"][0]})

    def test_debt_semantic_compatibility_and_incompatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            records = _projection(root)
            total_debt = next(r for r in records if r["canonical_metric"] == "total_debt")
            total_interest_bearing = next(r for r in records if r["canonical_metric"] == "total_interest_bearing_debt")
            self.assertEqual(total_debt["value"], total_interest_bearing["value"])
            self.assertEqual(total_debt["quality_state"], "available")
            self.assertEqual(total_debt["identity_reconciliation"]["reconciled_from"], "total_interest_bearing_debt")
        with tempfile.TemporaryDirectory() as tmp2:
            # Only short_term_borrowings cited -> incompatible/incomplete component set ->
            # total_interest_bearing_debt must stay unqualified and total_debt must not exist at all.
            root2 = Path(tmp2)
            observations = _make_observations(ORIGINAL_ROWS)
            short_term = next(o for o in observations if o["raw_item_id"] == "short_term_borrowings")
            pdf_bytes = b"evidence"; sha256 = hashlib.sha256(pdf_bytes).hexdigest(); evidence_id = _evidence_id(sha256)
            citation = _citation_for(short_term, OFFICIAL_VALUES["short_term_borrowings"], evidence_id)
            _write_runtime(root2, observations, [_evidence_record(evidence_id, "hpg.pdf", sha256)], [citation], {"hpg.pdf": pdf_bytes})
            records2 = _projection(root2)
            derived = next(r for r in records2 if r["canonical_metric"] == "total_interest_bearing_debt")
            self.assertEqual(derived["quality_state"], "unknown")
            self.assertFalse(any(r["canonical_metric"] == "total_debt" for r in records2))

    def test_citation_hash_mismatch_for_new_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            (root / "data" / "official-evidence" / "hpg.pdf").write_bytes(b"tampered, does not match manifest sha256")
            records = _projection(root)
            total_assets = next(r for r in records if r["canonical_metric"] == "total_assets")
            self.assertEqual(total_assets["quality_state"], "unknown")
            self.assertEqual(total_assets["statement_scope"], "unknown")
            self.assertNotIn("evidence", total_assets)
            verified = bridge.load_verified_citations(root)
            self.assertEqual(verified["by_observation_id"], {})

    def test_conflicting_metric_identities(self):
        # A record already exists under the reconciliation TARGET name ("total_debt") with a
        # different value than what reconciling total_interest_bearing_debt would produce.
        # reconcile_metric_identities must not delete or silently overwrite the pre-existing
        # fact; both must remain visible so no information is lost to a name collision.
        by_ticker = {"HPG": [
            {"canonical_metric": "total_debt", "value": 999, "quality_state": "available",
             "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1,
             "period_identity": {"period": "2024", "period_type": "annual"}, "observation_ids": ["pre-existing"]},
            {"canonical_metric": "total_interest_bearing_debt", "value": 82963129469555, "quality_state": "available",
             "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1,
             "period_identity": {"period": "2024", "period_type": "annual"}, "observation_ids": ["short", "long"],
             "evidence": {"components": []}},
        ]}
        reconciled = bridge.reconcile_metric_identities(by_ticker)["HPG"]
        total_debt_records = [r for r in reconciled if r["canonical_metric"] == "total_debt"]
        self.assertEqual(len(total_debt_records), 2)
        self.assertEqual({r["value"] for r in total_debt_records}, {999, 82963129469555})

    def test_unchanged_prior_observation_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_observations = _make_observations(ORIGINAL_ROWS)
            append_observations(store_path(root), original_observations)
            before_text = store_path(root).read_text(encoding="utf-8")
            original_ids = {o["observation_id"] for o in original_observations}
            new_observations = _make_observations(NEW_CORE_ROWS)
            result = append_observations(store_path(root), new_observations)
            self.assertEqual(result["added"], len(NEW_CORE_ROWS))
            after_text = store_path(root).read_text(encoding="utf-8")
            self.assertTrue(after_text.startswith(before_text))  # prior bytes untouched, only appended to
            remaining_ids = {row["observation_id"] for row in read_observations(store_path(root))}
            self.assertTrue(original_ids.issubset(remaining_ids))

    def test_idempotent_repeated_ingestion_and_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, observations = _full_runtime(tmp)
            result_a = append_observations(store_path(root), observations)
            result_b = append_observations(store_path(root), observations)
            self.assertEqual(result_a["added"], 0)  # already written by _full_runtime
            self.assertEqual(result_b["added"], 0)
            first = _projection(root)
            second = _projection(root)
            self.assertEqual(first, second)

    def test_legacy_behavior_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = _make_observations(ALL_ROWS)
            append_observations(store_path(root), observations)  # no data/official-evidence directory at all
            canonical = canonical_records(store_path(root), {"HPG": "corporate"})
            enriched = bridge.enrich_canonical_records(canonical, root)
            reconciled = bridge.reconcile_metric_identities(enriched)
            self.assertEqual(enriched, canonical)
            self.assertEqual(reconciled, enriched)  # nothing to reconcile without any evidence-qualified record
            self.assertTrue(all(r["quality_state"] == "unknown" for r in reconciled["HPG"] if r["derivation_status"] == "direct"))

    def test_financial_input_prefers_observation_store_over_narrative_bridge_on_period_collision(self):
        # Two "available" records compete for the same canonical_metric name (e.g. this
        # milestone's exact, per-item-cited FY2024 revenue vs. official_evidence.py's
        # narrative annual-report bridge for a different period). _financial_input must
        # deterministically prefer the observation-store record, not whichever happened
        # to sort first -- otherwise a ratio could silently mix two different periods.
        narrative_bridge = {"canonical_metric": "revenue", "value": 158332000000000, "quality_state": "available",
            "statement_scope": "consolidated", "period_identity": {"period": "2025", "period_type": "annual"}, "source": "official_evidence"}
        observation_store = {"canonical_metric": "revenue", "value": 138855112131387, "quality_state": "available",
            "statement_scope": "consolidated", "period_identity": {"period": "2024", "period_type": "annual"}, "source": "financial_observation_store"}
        for ordering in ([narrative_bridge, observation_store], [observation_store, narrative_bridge]):
            picked = _financial_input({"records": ordering})
            self.assertEqual(picked["revenue"]["value"], 138855112131387)
            self.assertEqual(picked["revenue"]["period_identity"]["period"], "2024")
        # A placeholder with no value or no real period identity must never be selected,
        # and must not crash the pure reshape even when it is the only candidate.
        placeholder = {"canonical_metric": "revenue", "value": None, "quality_state": "unavailable",
            "statement_scope": "unknown", "period_identity": None, "source": "financial_snapshot"}
        self.assertEqual(_financial_input({"records": [placeholder]}), {})


if __name__ == "__main__":
    unittest.main()
