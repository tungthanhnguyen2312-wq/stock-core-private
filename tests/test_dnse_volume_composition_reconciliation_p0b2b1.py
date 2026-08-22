"""Tests for P0-B.2B1 — SCALED_G1 candidate validation + residual classification.

Coverage requirements per milestone spec:
 1. C5 scale 10 exact match
 2. C5 configurable scale
 3. scale metadata preserved in output
 4. no semantic unit promotion from empirical scale
 5. C1–C4 behavior preserved
 6. positive delta multiple-of-100 residual classification
 7. delta -4 classification
 8. generic OTHER residual
 9. deterministic repeated result (same input → same output)
10. exchange/session lineage preserved
11. provenance records source-generation commit
12. divergent-source-generator ancestry status remains explicit
13. missing observations never become zero
14. no network/LLM dependency (module-level: all tests use synthetic data)
15. C5 does not output QUALIFIED_LIQUIDITY_INPUTS
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from dnse_volume_composition_reconciliation import (
    C5_CANDIDATE,
    CANDIDATE_DEFINITIONS,
    CANONICAL_TRADES_LINEAGE_STATUS,
    CANONICAL_TRADES_SOURCE_COMMIT,
    CandidateType,
    ResidualClass,
    ScaleStatus,
    ScaledG1Candidate,
    classify_c5_residual,
    reconcile_volume,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trades(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _ohlc(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _simple_trades(symbol: str, date: str, g1: float, g4: float = 0, t1: float = 0) -> pd.DataFrame:
    rows = [{"symbol": symbol, "session_date": date, "board_id": "G1", "quantity": g1}]
    if g4:
        rows.append({"symbol": symbol, "session_date": date, "board_id": "G4", "quantity": g4})
    if t1:
        rows.append({"symbol": symbol, "session_date": date, "board_id": "T1", "quantity": t1})
    return pd.DataFrame(rows)


def _simple_ohlc(symbol: str, date: str, daily_v: float) -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": symbol,
        "session_date": date,
        "daily_v": daily_v,
        "ohlc_observation_id": f"obs-{symbol}-{date}",
    }])


# ---------------------------------------------------------------------------
# 1. C5 scale 10 exact match
# ---------------------------------------------------------------------------

def test_c5_exact_match_scale_10():
    """G1=500, daily_v=5000 → C5=10×500=5000, exact match."""
    trades = _simple_trades("AAA", "2026-08-07", g1=500, g4=50, t1=10)
    ohlc = _simple_ohlc("AAA", "2026-08-07", 5000)
    result = reconcile_volume(trades, ohlc)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["C5"] == 5000.0
    assert row["delta_C5"] == 0.0
    assert bool(row["exact_match_C5"]) is True
    assert row["residual_class_C5"] == ResidualClass.EXACT_MATCH.value


# ---------------------------------------------------------------------------
# 2. C5 configurable scale
# ---------------------------------------------------------------------------

def test_c5_configurable_scale():
    """Custom scale=5 → C5=5×100=500, not 1000."""
    custom_c5 = ScaledG1Candidate(
        candidate_id="C5_custom",
        candidate_type=CandidateType.SCALED_G1,
        empirical_scale=5.0,
        scale_status=ScaleStatus.EMPIRICAL_CANDIDATE,
        semantic_unit_interpretation="UNKNOWN",
        evidence_source="test-custom-scale",
    )
    trades = _simple_trades("BBB", "2026-08-07", g1=100, g4=10, t1=5)
    ohlc = _simple_ohlc("BBB", "2026-08-07", 500)
    result = reconcile_volume(trades, ohlc, c5_candidate=custom_c5)
    row = result.iloc[0]
    assert row["C5"] == 500.0
    assert row["c5_empirical_scale"] == 5.0
    assert bool(row["exact_match_C5"]) is True


def test_c5_wrong_scale_does_not_match():
    """With scale=10 and daily_v=5000 from G1=600 → no match."""
    trades = _simple_trades("CCC", "2026-08-07", g1=600, g4=10, t1=5)
    ohlc = _simple_ohlc("CCC", "2026-08-07", 5000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    # C5 = 10*600 = 6000, delta = 5000-6000 = -1000
    assert row["C5"] == 6000.0
    assert row["delta_C5"] == -1000.0
    assert bool(row["exact_match_C5"]) is False


# ---------------------------------------------------------------------------
# 3. Scale metadata preserved in output
# ---------------------------------------------------------------------------

def test_c5_scale_metadata_preserved():
    """All C5 metadata columns are present and match the registered contract."""
    trades = _simple_trades("DDD", "2026-08-07", g1=100, g4=5, t1=2)
    ohlc = _simple_ohlc("DDD", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["c5_empirical_scale"] == 10.0
    assert row["c5_scale_status"] == ScaleStatus.EMPIRICAL_CANDIDATE.value
    assert row["c5_semantic_unit_interpretation"] == "UNKNOWN"
    assert row["c5_candidate_type"] == CandidateType.SCALED_G1.value


# ---------------------------------------------------------------------------
# 4. No semantic unit promotion from empirical scale
# ---------------------------------------------------------------------------

def test_c5_does_not_assert_trades_unit_as_shares():
    """semantic_unit_interpretation must remain UNKNOWN — never 'shares' or similar."""
    assert C5_CANDIDATE.semantic_unit_interpretation == "UNKNOWN"
    assert "lot" not in C5_CANDIDATE.semantic_unit_interpretation.lower()
    assert "share" not in C5_CANDIDATE.semantic_unit_interpretation.lower()


def test_c5_scale_status_is_empirical_not_promoted():
    """scale_status must be EMPIRICAL_CANDIDATE, not a promoted authority status."""
    assert C5_CANDIDATE.scale_status == ScaleStatus.EMPIRICAL_CANDIDATE
    # ScaleStatus must NOT have a QUALIFIED or AUTHORITY value
    status_values = {s.value for s in ScaleStatus}
    assert "QUALIFIED" not in status_values
    assert "AUTHORITY" not in status_values


# ---------------------------------------------------------------------------
# 5. C1–C4 behavior preserved
# ---------------------------------------------------------------------------

def test_c1_c4_not_retroactively_modified():
    """C1–C4 definition dict unchanged from P0-B.2A-B.2B."""
    assert CANDIDATE_DEFINITIONS["C1"] == ["G1"]
    assert CANDIDATE_DEFINITIONS["C2"] == ["G1", "G4"]
    assert CANDIDATE_DEFINITIONS["C3"] == ["G1", "T1", "T3"]
    assert CANDIDATE_DEFINITIONS["C4"] == ["G1", "G4", "T1", "T3", "T4", "T6"]


def test_c1_c4_failures_preserved_when_c5_matches():
    """When C5 matches but C1–C4 all fail, their failures are still recorded."""
    # G1=100, daily_v=1000=10×G1 → C5 exact match; C1=100≠1000 → fails
    trades = _simple_trades("EEE", "2026-08-07", g1=100, g4=50, t1=10)
    ohlc = _simple_ohlc("EEE", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert bool(row["exact_match_C1"]) is False
    assert bool(row["exact_match_C2"]) is False
    assert row["verdict_c1_c4"] == "CONFLICTING"
    assert bool(row["exact_match_C5"]) is True


def test_c1_exact_match_not_distorted_by_c5():
    """If C1 coincidentally matches (G1 == daily_v), C1 verdict is VALIDATED, C5 may differ."""
    trades = _simple_trades("FFF", "2026-08-07", g1=100, g4=50, t1=10)
    ohlc = _simple_ohlc("FFF", "2026-08-07", 100)  # matches C1 but not C5
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert bool(row["exact_match_C1"]) is True
    assert row["verdict_c1_c4"] == "VALIDATED_READY_FOR_P0_B2D_REVIEW"
    assert bool(row["exact_match_C5"]) is False


def test_reconcile_volume_insufficient_discrimination():
    """If no session has odd-lot/put-through (all continuous), verdict is INSUFFICIENT_DISCRIMINATION."""
    # Only G1 is populated; no G4, no T1-T6
    trades = _simple_trades("GGG", "2026-08-07", g1=100)
    ohlc = _simple_ohlc("GGG", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["verdict_c1_c4"] == "INSUFFICIENT_DISCRIMINATION"


def test_t4_is_put_through_odd_lot_under_the_canonical_board_contract():
    """T4 completes both the put-through and odd-lot discrimination dimensions."""
    trades = _trades(
        {"symbol": "G4T4", "session_date": "2026-08-07", "board_id": "G1", "quantity": 100},
        {"symbol": "G4T4", "session_date": "2026-08-07", "board_id": "G4", "quantity": 10},
        {"symbol": "G4T4", "session_date": "2026-08-07", "board_id": "T4", "quantity": 5},
    )
    ohlc = _simple_ohlc("G4T4", "2026-08-07", 115)
    row = reconcile_volume(trades, ohlc).iloc[0]
    assert bool(row["exact_match_C4"]) is True
    assert row["verdict_c1_c4"] == "VALIDATED_READY_FOR_P0_B2D_REVIEW"


# ---------------------------------------------------------------------------
# 6. Positive delta multiple-of-100 residual classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("delta", [100, 200, 500, 1000, 3800])
def test_positive_multiple_100_classification(delta: float):
    residual = classify_c5_residual(float(delta))
    assert residual == ResidualClass.POSITIVE_DELTA_MULTIPLE_OF_100


def test_positive_multiple_100_in_reconcile_output():
    """daily_v = 10×G1 + 200 → POSITIVE_DELTA_MULTIPLE_OF_100."""
    g1 = 300
    daily_v = 10 * g1 + 200  # delta = +200, divisible by 100
    trades = _simple_trades("GGG", "2026-08-07", g1=g1, g4=20, t1=5)
    ohlc = _simple_ohlc("GGG", "2026-08-07", daily_v)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["delta_C5"] == 200.0
    assert row["residual_class_C5"] == ResidualClass.POSITIVE_DELTA_MULTIPLE_OF_100.value


# ---------------------------------------------------------------------------
# 7. Delta -4 classification
# ---------------------------------------------------------------------------

def test_negative_delta_minus_4_classification():
    residual = classify_c5_residual(-4.0)
    assert residual == ResidualClass.NEGATIVE_DELTA_MINUS_4


def test_negative_delta_minus_4_in_reconcile_output():
    """daily_v = 10×G1 - 4 → NEGATIVE_DELTA_MINUS_4."""
    g1 = 500
    daily_v = 10 * g1 - 4
    trades = _simple_trades("SHB", "2026-08-07", g1=g1, g4=10, t1=3)
    ohlc = _simple_ohlc("SHB", "2026-08-07", daily_v)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["delta_C5"] == -4.0
    assert row["residual_class_C5"] == ResidualClass.NEGATIVE_DELTA_MINUS_4.value


# ---------------------------------------------------------------------------
# 8. Generic OTHER residual
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("delta", [-1.0, 50.0, 150.0, -4.5, 99.9])
def test_other_residual_classification(delta: float):
    residual = classify_c5_residual(delta)
    assert residual == ResidualClass.OTHER


def test_other_residual_in_reconcile_output():
    """daily_v = 10×G1 + 150 → delta=150, not divisible by 100 → OTHER."""
    g1 = 100
    daily_v = 10 * g1 + 150
    trades = _simple_trades("HHH", "2026-08-07", g1=g1, g4=5, t1=2)
    ohlc = _simple_ohlc("HHH", "2026-08-07", daily_v)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["delta_C5"] == 150.0
    assert row["residual_class_C5"] == ResidualClass.OTHER.value


# ---------------------------------------------------------------------------
# 9. Deterministic repeated result (same input → byte-identical output)
# ---------------------------------------------------------------------------

def _df_canonical_hash(df: pd.DataFrame) -> str:
    """Content hash of a DataFrame ignoring row order (sort all columns)."""
    sorted_df = df.sort_values(by=list(df.columns)).reset_index(drop=True)
    return hashlib.sha256(sorted_df.to_json().encode()).hexdigest()


def test_deterministic_repeat():
    """Running reconcile_volume twice on the same input gives identical results."""
    trades = _trades(
        {"symbol": "AAA", "session_date": "2026-08-07", "board_id": "G1", "quantity": 200},
        {"symbol": "AAA", "session_date": "2026-08-07", "board_id": "G4", "quantity": 30},
        {"symbol": "AAA", "session_date": "2026-08-07", "board_id": "T1", "quantity": 10},
        {"symbol": "BBB", "session_date": "2026-08-07", "board_id": "G1", "quantity": 400},
        {"symbol": "BBB", "session_date": "2026-08-07", "board_id": "G4", "quantity": 60},
    )
    ohlc = _ohlc(
        {"symbol": "AAA", "session_date": "2026-08-07", "daily_v": 2000, "ohlc_observation_id": "o1"},
        {"symbol": "BBB", "session_date": "2026-08-07", "daily_v": 4000, "ohlc_observation_id": "o2"},
    )
    r1 = reconcile_volume(trades, ohlc)
    r2 = reconcile_volume(trades, ohlc)
    assert _df_canonical_hash(r1) == _df_canonical_hash(r2)


# ---------------------------------------------------------------------------
# 10. Exchange/session lineage preserved
# ---------------------------------------------------------------------------

def test_session_lineage_columns_present():
    """Output always carries session_date, lineage_ohlc, and provenance columns."""
    trades = _simple_trades("III", "2026-08-07", g1=100, g4=5, t1=3)
    ohlc = _simple_ohlc("III", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["session_date"] == "2026-08-07"
    assert row["lineage_ohlc"] == "obs-III-2026-08-07"


# ---------------------------------------------------------------------------
# 11. Provenance records source-generation commit
# ---------------------------------------------------------------------------

def test_provenance_source_commit_recorded():
    """canonical_trades_source_commit must equal the registered constant."""
    trades = _simple_trades("JJJ", "2026-08-07", g1=100, g4=5, t1=3)
    ohlc = _simple_ohlc("JJJ", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["canonical_trades_source_commit"] == CANONICAL_TRADES_SOURCE_COMMIT
    assert CANONICAL_TRADES_SOURCE_COMMIT == "2b7b38772e16c434c8adf5288cbc46ef0f7f4c02"


# ---------------------------------------------------------------------------
# 12. Divergent-source-generator ancestry status remains explicit
# ---------------------------------------------------------------------------

def test_lineage_status_not_in_main_ancestry():
    """lineage_status must spell out SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY."""
    trades = _simple_trades("KKK", "2026-08-07", g1=100, g4=5, t1=3)
    ohlc = _simple_ohlc("KKK", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    row = result.iloc[0]
    assert row["canonical_trades_lineage_status"] == CANONICAL_TRADES_LINEAGE_STATUS
    assert CANONICAL_TRADES_LINEAGE_STATUS == "SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY"


# ---------------------------------------------------------------------------
# 13. Missing observations never become zero
# ---------------------------------------------------------------------------

def test_missing_ohlc_symbol_excluded_not_zero():
    """Symbol with Trades but no OHLC must be excluded from output (not zero-filled)."""
    trades = _trades(
        {"symbol": "LLL", "session_date": "2026-08-07", "board_id": "G1", "quantity": 100},
        {"symbol": "MMM", "session_date": "2026-08-07", "board_id": "G1", "quantity": 200},
    )
    ohlc = _ohlc(  # only LLL has OHLC
        {"symbol": "LLL", "session_date": "2026-08-07", "daily_v": 1000, "ohlc_observation_id": "o-lll"},
    )
    result = reconcile_volume(trades, ohlc)
    assert len(result) == 1
    assert result.iloc[0]["symbol"] == "LLL"


def test_missing_trades_symbol_excluded_not_zero():
    """Symbol with OHLC but no Trades must be excluded from output (not zero-filled)."""
    trades = _trades(
        {"symbol": "NNN", "session_date": "2026-08-07", "board_id": "G1", "quantity": 100},
    )
    ohlc = _ohlc(
        {"symbol": "NNN", "session_date": "2026-08-07", "daily_v": 1000, "ohlc_observation_id": "o-nnn"},
        {"symbol": "OOO", "session_date": "2026-08-07", "daily_v": 500, "ohlc_observation_id": "o-ooo"},
    )
    result = reconcile_volume(trades, ohlc)
    assert len(result) == 1
    assert result.iloc[0]["symbol"] == "NNN"


def test_empty_trades_returns_empty():
    trades = pd.DataFrame()
    ohlc = _simple_ohlc("PPP", "2026-08-07", 1000)
    result = reconcile_volume(trades, ohlc)
    assert result.empty


def test_empty_ohlc_returns_empty():
    trades = _simple_trades("QQQ", "2026-08-07", g1=100)
    ohlc = pd.DataFrame()
    result = reconcile_volume(trades, ohlc)
    assert result.empty


# ---------------------------------------------------------------------------
# 14. No network/LLM dependency — all tests above use synthetic data
# ---------------------------------------------------------------------------
# (No additional test needed — all fixtures above are in-memory DataFrames.)


# ---------------------------------------------------------------------------
# 15. C5 does not output QUALIFIED_LIQUIDITY_INPUTS
# ---------------------------------------------------------------------------

def test_c5_never_outputs_qualified_liquidity_inputs():
    """qualified_liquidity_inputs must be False in all rows regardless of exact-match status."""
    # Row where C5 exactly matches
    trades = _simple_trades("RRR", "2026-08-07", g1=500, g4=50, t1=10)
    ohlc = _simple_ohlc("RRR", "2026-08-07", 5000)
    result = reconcile_volume(trades, ohlc)
    for _, row in result.iterrows():
        assert bool(row["qualified_liquidity_inputs"]) is False


def test_qualified_liquidity_inputs_false_on_multiple_rows():
    """Even when every row is an exact C5 match, qualified_liquidity_inputs stays False."""
    trades = _trades(
        {"symbol": "SSS", "session_date": "2026-08-07", "board_id": "G1", "quantity": 100},
        {"symbol": "SSS", "session_date": "2026-08-07", "board_id": "G4", "quantity": 10},
        {"symbol": "TTT", "session_date": "2026-08-07", "board_id": "G1", "quantity": 200},
        {"symbol": "TTT", "session_date": "2026-08-07", "board_id": "G4", "quantity": 20},
    )
    ohlc = _ohlc(
        {"symbol": "SSS", "session_date": "2026-08-07", "daily_v": 1000, "ohlc_observation_id": "o1"},
        {"symbol": "TTT", "session_date": "2026-08-07", "daily_v": 2000, "ohlc_observation_id": "o2"},
    )
    result = reconcile_volume(trades, ohlc)
    assert len(result) == 2
    assert not any(result["qualified_liquidity_inputs"])


# ---------------------------------------------------------------------------
# Additional: classify_c5_residual boundary cases
# ---------------------------------------------------------------------------

def test_classify_zero_is_exact_match():
    assert classify_c5_residual(0.0) == ResidualClass.EXACT_MATCH


def test_classify_negative_100_is_other():
    # negative multiple of 100 is NOT POSITIVE_DELTA_MULTIPLE_OF_100
    assert classify_c5_residual(-100.0) == ResidualClass.OTHER


def test_c5_candidate_record():
    """ScaledG1Candidate.record() returns a serialisable dict."""
    rec = C5_CANDIDATE.record()
    assert rec["candidate_type"] == CandidateType.SCALED_G1.value
    assert rec["empirical_scale"] == 10.0
    assert rec["semantic_unit_interpretation"] == "UNKNOWN"
    # Must be JSON-serialisable (no exception)
    json.dumps(rec)
