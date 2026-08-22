"""tests/test_derive_qualified_liquidity_inputs_reconciliation.py — Unit tests for the Qualified
Liquidity Inputs Reconciliation V1 engine."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from dnse_fhsc_market_composition_scaleout import content_identity as market_composition_content_identity
from dnse_fhsc_volume_basis import content_identity as volume_basis_content_identity
from tools.derive_qualified_liquidity_inputs_reconciliation import (
    CONFLICTING,
    COVERAGE_RESTRICTED_RECONCILED,
    EXACT_RECONCILED,
    INSUFFICIENT_DISCRIMINATION,
    UNAVAILABLE,
    VERDICT_TAXONOMY,
    LiquidityInputIdentityError,
    _as_int,
    _is_exact_integer,
    _sha256_json,
    build_field_qualifications,
    build_qualified_liquidity_inputs_reconciliation,
    classify_combined_rows,
    combine_cross_provider_rows,
    evaluate_board_composition_conflict,
    evaluate_candidate_compositions,
    evaluate_fhsc_internal_identity_breadth,
    evaluate_liquidity_metric_eligibility,
    load_capability_research_digest,
    load_market_composition_scaleout,
    load_real_eod_new_session_rows,
    load_volume_basis_qualification,
)


def _trading_row(ticker, session, matched, put_through, total, *, source="A"):
    return {"ticker": ticker, "session": session, "dnse_v": matched, "matched_volume": matched,
            "put_through_volume": put_through, "total_volume": total, "row_status": "PARSED", "source": source}


def _finalize_a(matrix, exchange_summary=None):
    raw = {"artifact_type": "dnse_fhsc_market_composition_scaleout", "volume": {
        "volume_matrix": matrix,
        "exchange_specific_summary": exchange_summary or {"HOSE": {"unavailable_rows": 0}},
    }}
    identity = market_composition_content_identity(raw)
    return {**raw, **identity}


def _finalize_b(matrix):
    raw = {"artifact_type": "dnse_fhsc_volume_basis_qualification", "reconciliation": {"matrix": matrix}}
    identity = volume_basis_content_identity(raw)
    return {**raw, **identity}


def _finalize_d(records, session_date="2026-08-21"):
    raw = {"schema_version": "1.0.0", "session_date": session_date, "records": records}
    sha = _sha256_json(raw)
    return {**raw, "digest_sha256": sha, "digest_identity": f"capability_research_digest:{sha}"}


def _digest_record(ticker, matched_v, put_through_v, total_v, matched_vnd, put_through_vnd, total_vnd, *, status="ACQUIRED"):
    return {"ticker": ticker, "fhsc_value_volume_composition": {
        "status": status,
        "matched_volume_shares": matched_v, "put_through_volume_shares": put_through_v, "total_volume_shares": total_v,
        "matched_traded_value_vnd": matched_vnd, "put_through_traded_value_vnd": put_through_vnd, "total_traded_value_vnd": total_vnd,
    }}


def _dnse_ohlc_bytes(epoch: int, volume: int) -> bytes:
    return json.dumps({"t": [epoch], "o": [1.0], "h": [1.0], "l": [1.0], "c": [1.0], "v": [volume], "nextTime": 0}).encode("utf-8")


def _fhsc_trading_history_bytes(date: str, matched_vol: int, put_through_vol: int, total_vol: int) -> bytes:
    return json.dumps({"data": {"data": [{
        "date": date,
        "matched": {"volume": matched_vol, "value": matched_vol * 1000},
        "put_through": {"volume": put_through_vol, "value": put_through_vol * 1000},
        "total": {"volume": total_vol, "value": total_vol * 1000},
    }]}}).encode("utf-8")


class TestQualifiedLiquidityInputsReconciliation(unittest.TestCase):
    # -- Row classification: exact matched-component discrimination. ---------------------------
    def test_dnse_matched_candidate_is_the_unique_exact_component(self) -> None:
        rows = [
            _trading_row("AAA", "2026-08-01", 1000, 200, 1200),
            _trading_row("BBB", "2026-08-01", 500, 50, 550),
        ]
        classified = classify_combined_rows(rows)
        candidates = evaluate_candidate_compositions(classified)
        self.assertEqual(candidates["candidates"]["matched"]["exact_match_count"], 2)
        self.assertEqual(candidates["candidates"]["total"]["exact_match_count"], 0)
        self.assertEqual(candidates["candidates"]["put_through"]["exact_match_count"], 0)
        self.assertEqual(candidates["unique_exact_candidate_component"], "matched")
        self.assertEqual(candidates["dnse_v_semantic_verdict"], EXACT_RECONCILED)  # no UNAVAILABLE rows in this fixture

    # -- A row where DNSE v matches no retained component is CONFLICTING, never silently dropped. -
    def test_dnse_v_matching_no_component_is_conflicting(self) -> None:
        row = {"ticker": "CCC", "session": "2026-08-01", "dnse_v": 999, "matched_volume": 1000,
               "put_through_volume": 200, "total_volume": 1200, "row_status": "PARSED", "source": "A"}
        classified = classify_combined_rows([row])
        self.assertEqual(classified[0]["verdict"], CONFLICTING)
        candidates = evaluate_candidate_compositions(classified)
        self.assertEqual(candidates["conflicting_row_count"], 1)
        self.assertEqual(candidates["dnse_v_semantic_verdict"], CONFLICTING)

    # -- Zero put-through is indistinguishable, not a silent zero and not a match either. ---------
    def test_zero_put_through_row_is_insufficient_discrimination(self) -> None:
        row = _trading_row("DDD", "2026-08-01", 1000, 0, 1000)
        classified = classify_combined_rows([row])
        self.assertEqual(classified[0]["verdict"], INSUFFICIENT_DISCRIMINATION)
        candidates = evaluate_candidate_compositions(classified)
        self.assertEqual(candidates["non_discriminating_row_count"], 1)
        self.assertEqual(candidates["discriminating_row_count"], 0)

    # -- A known-incomplete/missing cell stays visible as UNAVAILABLE; never becomes zero. ---------
    def test_missing_cell_is_unavailable_never_zero(self) -> None:
        row = {"ticker": "EEE", "session": "2026-08-02", "source": "A", "row_status": "NOT_COMPARABLE"}
        classified = classify_combined_rows([row])
        self.assertEqual(classified[0]["verdict"], UNAVAILABLE)
        self.assertEqual(classified[0]["ticker"], "EEE")
        self.assertEqual(classified[0]["session"], "2026-08-02")
        self.assertNotIn("matched_volume", classified[0])

    # -- Two sources agreeing on the same cell: agreement recorded, both sources retained. --------
    def test_cross_artifact_agreement_when_identical(self) -> None:
        a_rows = [_trading_row("FFF", "2026-08-03", 1000, 100, 1100, source="A")]
        b_rows = [_trading_row("FFF", "2026-08-03", 1000, 100, 1100, source="B")]
        combo = combine_cross_provider_rows(a_rows, b_rows)
        self.assertEqual(combo["agreement_check_count"], 1)
        self.assertEqual(combo["disagreement_count"], 0)
        self.assertEqual(sorted(combo["combined_rows"][0]["sources"]), ["A", "B"])

    # -- Two sources disagreeing on the same cell: flagged, never silently resolved by picking one. -
    def test_cross_artifact_disagreement_is_flagged_not_resolved(self) -> None:
        a_rows = [_trading_row("GGG", "2026-08-03", 1000, 100, 1100, source="A")]
        b_rows = [_trading_row("GGG", "2026-08-03", 999, 100, 1099, source="B")]  # different matched_volume
        combo = combine_cross_provider_rows(a_rows, b_rows)
        self.assertEqual(combo["disagreement_count"], 1)
        classified = classify_combined_rows(combo["combined_rows"])
        self.assertEqual(classified[0]["verdict"], CONFLICTING)
        self.assertIn("disagreement_detail", classified[0])

    # -- Source C (new-session raw bytes) extends coverage with a genuinely new discriminating row. -
    def test_source_c_new_session_raw_bytes_add_discriminating_row(self, ) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "dnse_ohlc_HHH_abc123.json").write_bytes(_dnse_ohlc_bytes(1787277600, 1000))
            (raw_dir / "fhsc_trading_history_HHH_def456.json").write_bytes(
                _fhsc_trading_history_bytes("2026-08-21", 1000, 300, 1300)
            )
            rows = load_real_eod_new_session_rows(raw_dir, ["HHH"], "2026-08-21")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["row_status"], "PARSED")
        self.assertEqual(rows[0]["dnse_v"], 1000)
        self.assertEqual(rows[0]["matched_volume"], 1000)
        self.assertEqual(rows[0]["put_through_volume"], 300)
        classified = classify_combined_rows(rows)
        self.assertEqual(classified[0]["verdict"], EXACT_RECONCILED)
        self.assertEqual(classified[0]["matched_component"], "matched")

    # -- A ticker with no retained raw pair is reported, not fabricated as zero volume. -------------
    def test_source_c_missing_raw_pair_is_reported_not_fabricated(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rows = load_real_eod_new_session_rows(Path(tmp), ["III"], "2026-08-21")
        self.assertEqual(rows[0]["row_status"], "RAW_PAIR_MISSING")
        self.assertNotIn("dnse_v", rows[0])
        self.assertNotIn("matched_volume", rows[0])

    # -- FHSC-internal value+volume arithmetic identity: exact vs a real mismatch. -------------------
    def test_fhsc_internal_identity_breadth_detects_exact_and_mismatch(self) -> None:
        records = [
            _digest_record("JJJ", 1000, 200, 1200, 10_000, 2_000, 12_000),  # exact
            _digest_record("KKK", 1000, 200, 1199, 10_000, 2_000, 12_000),  # volume mismatch (off by one)
        ]
        digest = _finalize_d(records)
        breadth = evaluate_fhsc_internal_identity_breadth(digest)
        self.assertEqual(breadth["volume_identity"]["exact"], 1)
        self.assertEqual(breadth["volume_identity"]["mismatch"], 1)
        self.assertEqual(breadth["value_identity"]["exact"], 2)
        self.assertEqual(breadth["verdict"], CONFLICTING)  # any mismatch fails the whole breadth check closed

    def test_fhsc_internal_identity_breadth_exact_when_all_agree(self) -> None:
        records = [_digest_record("LLL", 1000, 200, 1200, 10_000, 2_000, 12_000)]
        digest = _finalize_d(records)
        breadth = evaluate_fhsc_internal_identity_breadth(digest)
        self.assertEqual(breadth["verdict"], EXACT_RECONCILED)
        self.assertEqual(breadth["discriminating_ticker_count"], 1)

    # -- Board mapping is canonical; numeric board aggregation remains unavailable. ------------------
    def test_board_composition_mapping_is_canonical_and_numeric_coverage_stays_unavailable(self) -> None:
        board = evaluate_board_composition_conflict()
        self.assertEqual(board["semantic_mapping_conflict"]["verdict"], EXACT_RECONCILED)
        self.assertEqual(board["semantic_mapping_conflict"]["mapping"]["G4"], "ODD_LOT")
        self.assertEqual(board["semantic_mapping_conflict"]["mapping"]["T4"], "PUT_THROUGH_ODD_LOT")
        self.assertEqual(board["underlying_data_access"]["verdict"], UNAVAILABLE)
        self.assertTrue(board["no_odd_lot_aggregate_anywhere_on_main"])

    # -- Liquidity eligibility never opens while odd-lot remains unresolved. -------------------------
    def test_liquidity_eligibility_stays_false(self) -> None:
        elig = evaluate_liquidity_metric_eligibility({})
        self.assertFalse(elig["adv_turnover_input_eligible"])
        self.assertIn("odd-lot", elig["position_sizing_still_blocked_by"][1].lower())

    # -- Exact-integer handling: a JSON-float-serialized integer is exact; a genuine fraction is not. -
    def test_exact_integer_handling_distinguishes_serialized_ints_from_real_fractions(self) -> None:
        self.assertTrue(_is_exact_integer(1000))
        self.assertTrue(_is_exact_integer(1000.0))
        self.assertFalse(_is_exact_integer(1000.5))
        self.assertFalse(_is_exact_integer(True))  # bool must never be treated as a volume/value integer
        self.assertFalse(_is_exact_integer(None))
        self.assertEqual(_as_int(1000.0), 1000)
        self.assertIsNone(_as_int(1000.5))

    def test_fhsc_internal_identity_breadth_flags_genuine_fraction_as_mismatch(self) -> None:
        records = [_digest_record("MMM", 1000.5, 200, 1200.5, 10_000, 2_000, 12_000)]
        digest = _finalize_d(records)
        breadth = evaluate_fhsc_internal_identity_breadth(digest)
        # 1000.5 + 200 == 1200.5 arithmetically, but 1000.5 is not a real share count -> must not
        # be silently accepted as an exact integer reconciliation.
        self.assertEqual(breadth["volume_identity"]["mismatch"], 1)
        self.assertEqual(breadth["volume_identity"]["exact"], 0)

    # -- Verdict taxonomy completeness (task-mandated). ------------------------------------------
    def test_verdict_taxonomy_has_required_five_values(self) -> None:
        self.assertEqual(set(VERDICT_TAXONOMY), {EXACT_RECONCILED, COVERAGE_RESTRICTED_RECONCILED, CONFLICTING, INSUFFICIENT_DISCRIMINATION, UNAVAILABLE})

    # -- Fail-closed identity validation on all three loaders. -------------------------------------
    def test_fails_closed_on_tampered_source_a(self) -> None:
        artifact = _finalize_a([])
        artifact["artifact_sha256"] = "0" * 64
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaises(LiquidityInputIdentityError):
                load_market_composition_scaleout(path)

    def test_fails_closed_on_tampered_source_b(self) -> None:
        artifact = _finalize_b([])
        artifact["artifact_sha256"] = "0" * 64
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaises(LiquidityInputIdentityError):
                load_volume_basis_qualification(path)

    def test_fails_closed_on_tampered_source_d(self) -> None:
        digest = _finalize_d([])
        digest["digest_sha256"] = "0" * 64
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            path.write_text(json.dumps(digest), encoding="utf-8")
            with self.assertRaises(LiquidityInputIdentityError):
                load_capability_research_digest(path)

    # -- End-to-end: a full synthetic multi-symbol/multi-session cohort with a genuine put-through
    #    component, reconciled deterministically, coverage-restricted because one ticker is unavailable.
    def test_end_to_end_multi_symbol_multi_session_reconciliation(self) -> None:
        matrix_a = [
            {"ticker": "AAA", "session": "2026-08-01", "dnse_ohlc_volume": 1000, "fhsc_matched_volume": 1000,
             "fhsc_put_through_volume": 100, "fhsc_total_volume": 1100, "classification": "DNSE_EQUALS_MATCHED"},
            {"ticker": "AAA", "session": "2026-08-02", "dnse_ohlc_volume": 900, "fhsc_matched_volume": 900,
             "fhsc_put_through_volume": 0, "fhsc_total_volume": 900, "classification": "NON_DISCRIMINATING_ZERO_PUT_THROUGH"},
            {"ticker": "BBB", "session": "2026-08-01", "dnse_ohlc_volume": 2000, "fhsc_matched_volume": 2000,
             "fhsc_put_through_volume": 50, "fhsc_total_volume": 2050, "classification": "DNSE_EQUALS_MATCHED"},
            {"ticker": "CCC", "session": "2026-08-01", "exchange": "UPCOM", "classification": "NOT_COMPARABLE",
             "unavailable_reason": "FHSC_TRADING_MISSING"},
        ]
        source_a = _finalize_a(matrix_a, exchange_summary={"HOSE": {"unavailable_rows": 0}, "UPCOM": {"unavailable_rows": 1}})
        source_b = _finalize_b([])  # no independent second-source coverage in this fixture
        source_c_rows = [_trading_row("AAA", "2026-08-03", 1200, 400, 1600, source="C")]  # genuinely new session
        digest_records = [
            _digest_record("AAA", 1000, 100, 1100, 10_000, 1_000, 11_000),
            _digest_record("BBB", 2000, 50, 2050, 20_000, 500, 20_500),
            _digest_record("DDD", 500, 0, 500, 5_000, 0, 5_000),
        ]
        digest = _finalize_d(digest_records)

        artifact = build_qualified_liquidity_inputs_reconciliation(source_a, source_b, source_c_rows, digest)

        self.assertEqual(artifact["candidate_compositions_evaluated"]["unique_exact_candidate_component"], "matched")
        self.assertEqual(artifact["candidate_compositions_evaluated"]["dnse_v_semantic_verdict"], COVERAGE_RESTRICTED_RECONCILED)
        self.assertEqual(artifact["tested_corpus"]["cross_provider_volume"]["discriminating_row_count"], 3)  # AAA/08-01, BBB/08-01, AAA/08-03
        self.assertEqual(artifact["tested_corpus"]["cross_provider_volume"]["non_discriminating_row_count"], 1)  # AAA/08-02
        self.assertEqual(artifact["tested_corpus"]["cross_provider_volume"]["unavailable_row_count"], 1)  # CCC
        self.assertEqual(artifact["fhsc_internal_identity_breadth"]["verdict"], EXACT_RECONCILED)
        self.assertEqual(artifact["board_composition"]["semantic_mapping_conflict"]["verdict"], EXACT_RECONCILED)
        self.assertFalse(artifact["liquidity_metric_eligibility"]["adv_turnover_input_eligible"])

        # Replay determinism (excluding execution_timestamp).
        replay = build_qualified_liquidity_inputs_reconciliation(source_a, source_b, source_c_rows, digest)
        self.assertEqual(artifact["artifact_sha256"], replay["artifact_sha256"])
        self.assertEqual(artifact["artifact_identity"], replay["artifact_identity"])

        # Lineage preserved end-to-end for every field.
        for field_id, field in artifact["field_qualifications"].items():
            self.assertIn("provider", field)
            self.assertIn("unit", field)
            self.assertIn("composition_semantics", field)
            self.assertIn("coverage_status", field)
            self.assertIn("evidence_lineage", field)
            self.assertIn("allowed_downstream_uses", field)
            self.assertIn("blockers", field)
            self.assertIn(field["verdict"], VERDICT_TAXONOMY, f"{field_id} verdict not in taxonomy")

    # -- A materially different composition (e.g. all-zero-put-through cohort) must not be silently
    #    reported the same as a genuinely discriminated one. ------------------------------------------
    def test_all_zero_put_through_cohort_yields_insufficient_discrimination_not_exact(self) -> None:
        source_a = _finalize_a([
            {"ticker": "NNN", "session": "2026-08-01", "dnse_ohlc_volume": 500, "fhsc_matched_volume": 500,
             "fhsc_put_through_volume": 0, "fhsc_total_volume": 500, "classification": "NON_DISCRIMINATING_ZERO_PUT_THROUGH"},
        ])
        source_b = _finalize_b([])
        digest = _finalize_d([])
        artifact = build_qualified_liquidity_inputs_reconciliation(source_a, source_b, [], digest)
        self.assertEqual(artifact["candidate_compositions_evaluated"]["dnse_v_semantic_verdict"], INSUFFICIENT_DISCRIMINATION)
        self.assertFalse(artifact["liquidity_metric_eligibility"]["adv_turnover_input_eligible"])

    # -- No position sizing / recommendation / leverage language anywhere in authored text. -----------
    def test_no_position_sizing_or_recommendation_language(self) -> None:
        source_a = _finalize_a([{
            "ticker": "OOO", "session": "2026-08-01", "dnse_ohlc_volume": 100, "fhsc_matched_volume": 100,
            "fhsc_put_through_volume": 10, "fhsc_total_volume": 110, "classification": "DNSE_EQUALS_MATCHED",
        }])
        source_b = _finalize_b([])
        digest = _finalize_d([_digest_record("OOO", 100, 10, 110, 1000, 100, 1100)])
        artifact = build_qualified_liquidity_inputs_reconciliation(source_a, source_b, [], digest)

        forbidden = ("position size", "position sizing", "target price", "price target", "recommend",
                     "buy rating", "sell rating", "leverage", "portfolio weight", "expected return", "days to liquidate")

        def _walk_strings(obj):
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from _walk_strings(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _walk_strings(v)

        for s in _walk_strings(artifact):
            low = s.lower()
            for token in forbidden:
                self.assertNotIn(token, low, f"forbidden language {token!r} found in: {s!r}")

    def test_py_compile_smoke(self) -> None:
        import py_compile
        import tools.derive_qualified_liquidity_inputs_reconciliation as mod
        py_compile.compile(mod.__file__, doraise=True)


if __name__ == "__main__":
    unittest.main()
