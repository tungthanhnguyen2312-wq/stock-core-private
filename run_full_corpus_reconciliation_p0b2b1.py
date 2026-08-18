"""Full-corpus reconciliation runner — P0-B.2B1 (C5 / SCALED_G1 validation).

Runs the complete retained 40-session population and reports exact metrics.
Run twice with --determinism-check to verify content-identity hash stability.

Usage
-----
    python run_full_corpus_reconciliation_p0b2b1.py [--determinism-check]

Output
------
Prints a compact machine-readable summary to stdout.
Does NOT write output rows to Git (large corpus data stays outside VCS).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

# Allow running from the worktree root without installation
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from dnse_volume_composition_reconciliation import (
    C5_CANDIDATE,
    CANONICAL_TRADES_LINEAGE_STATUS,
    CANONICAL_TRADES_SOURCE_COMMIT,
    ResidualClass,
    extract_ohlc_daily_v,
    load_canonical_trades,
    reconcile_volume,
)

# ---------------------------------------------------------------------------
# Corpus paths — update if the retained artifacts move
# ---------------------------------------------------------------------------
TRADES_DIR = Path(
    r"C:\Projects\StockLookup\operations-review"
    r"\task-160-canonical-materialization-v1-20260817"
    r"\shadow\canonical\provider=DNSE\dataset=trades_history"
)
OHLC_DIR = Path(
    r"C:\Projects\StockLookup\operations-review"
    r"\dnse-market-data-lake-v2-20260812\data\market_raw_lake\raw\DNSE\ohlc"
)


def _content_hash(df: pd.DataFrame) -> str:
    """Deterministic hash of a DataFrame (sorted, excluding timestamp/run-id columns)."""
    drop_cols = [c for c in df.columns if "run_id" in c or "timestamp" in c]
    stable = df.drop(columns=drop_cols, errors="ignore")
    stable = stable.sort_values(by=list(stable.columns)).reset_index(drop=True)
    return hashlib.sha256(stable.to_json(orient="records").encode()).hexdigest()


def _fmt(n: int, d: int) -> str:
    pct = n / d * 100 if d else 0.0
    return f"{n}/{d} ({pct:.4f}%)"


def run_reconciliation() -> tuple[pd.DataFrame, str]:
    """Process session-by-session to avoid OOM on the full 18M-row concat."""
    print("Loading OHLC daily v (all dates)...", flush=True)
    ohlc_df = extract_ohlc_daily_v(OHLC_DIR)
    print(f"  OHLC (symbol, date) pairs: {len(ohlc_df):,}", flush=True)

    sessions = sorted(TRADES_DIR.glob("session_date=*"))
    print(f"  Session-date partitions: {len(sessions)}", flush=True)

    all_chunks: list[pd.DataFrame] = []
    for i, session_dir in enumerate(sessions, 1):
        parquet = session_dir / "part-00000.parquet"
        if not parquet.exists():
            continue
        trades_chunk = pd.read_parquet(parquet)
        session_date = session_dir.name.split("=", 1)[1]
        ohlc_chunk = ohlc_df[ohlc_df["session_date"] == session_date].copy()
        if ohlc_chunk.empty:
            continue
        chunk_result = reconcile_volume(trades_chunk, ohlc_chunk)
        if not chunk_result.empty:
            all_chunks.append(chunk_result)
        if i % 10 == 0:
            print(f"  Processed {i}/{len(sessions)} sessions...", flush=True)

    print("Concatenating session results...", flush=True)
    if not all_chunks:
        result_df = pd.DataFrame()
    else:
        result_df = pd.concat(all_chunks, ignore_index=True)

    content_id = _content_hash(result_df)
    return result_df, content_id


def print_report(df: pd.DataFrame, content_id: str, run_n: int = 1) -> None:
    eligible = len(df)
    complete = int((df["completeness"] == "COMPLETE").sum())
    incomplete = eligible - complete
    discriminating = int(df["discriminating_session"].sum())
    g4_active = int((df["board_G4"] > 0).sum())
    t1t3_active = int(((df["board_T1"] > 0) | (df["board_T3"] > 0)).sum())
    t4t6_active = int(((df["board_T4"] > 0) | (df["board_T6"] > 0)).sum())

    print(f"\n{'='*60}")
    print(f"RUN {run_n} — CONTENT HASH: {content_id}")
    print(f"{'='*60}")

    print("\n--- CORPUS METRICS ---")
    print(f"eligible symbol-sessions : {eligible:,}")
    print(f"complete                 : {complete:,}")
    print(f"incomplete/unavailable   : {incomplete:,}")
    print(f"discriminating           : {discriminating:,}")
    print(f"G4-active                : {g4_active:,}")
    print(f"T1/T3-active             : {t1t3_active:,}")
    print(f"T4/T6-active             : {t4t6_active:,}")

    print("\n--- CANDIDATES (C1-C4, preserving failures) ---")
    for c in ["C1", "C2", "C3", "C4"]:
        exact = int(df[f"exact_match_{c}"].sum())
        delta = df[f"delta_{c}"]
        print(
            f"[{c}] exact={_fmt(exact, eligible)}"
            f"  delta>0={(delta > 0).sum():,}  delta<0={(delta < 0).sum():,}  delta=0={exact:,}"
        )

    print("\n--- C5 (SCALED_G1 shadow) ---")
    exact5 = int(df["exact_match_C5"].sum())
    delta5 = df["delta_C5"]
    mismatch5 = eligible - exact5
    print(f"scale             : {C5_CANDIDATE.empirical_scale}")
    print(f"scale_status      : {C5_CANDIDATE.scale_status.value}")
    print(f"semantic_unit     : {C5_CANDIDATE.semantic_unit_interpretation}")
    print(f"exact match       : {_fmt(exact5, eligible)}")
    print(f"mismatches        : {mismatch5:,}")
    print(f"delta>0           : {(delta5 > 0).sum():,}")
    print(f"delta<0           : {(delta5 < 0).sum():,}")
    print(f"delta=0           : {exact5:,}")
    print(f"delta abs mean    : {delta5.abs().mean():.4f}")
    print(f"delta abs max     : {delta5.abs().max():.1f}")

    print("\n--- C5 RESIDUAL CLASSIFICATION ---")
    rc = df["residual_class_C5"].value_counts().to_dict()
    for cls in ResidualClass:
        n = rc.get(cls.value, 0)
        print(f"  {cls.value:<40} : {n:,}")

    # Residual detail: symbols
    residuals = df[~df["exact_match_C5"]]
    print(f"\n  Total residuals: {len(residuals):,}")
    print(f"  Residual symbols: {sorted(residuals['symbol'].unique())[:20]}")

    # Delta -4 detail
    minus4 = residuals[residuals["delta_C5"] == -4.0]
    if not minus4.empty:
        print(f"\n  delta=-4 rows: {len(minus4)}")
        print(f"  delta=-4 symbols: {sorted(minus4['symbol'].unique())}")
        print(f"  delta=-4 dates: {sorted(minus4['session_date'].unique())}")

    # Positive multiple-of-100 detail
    pos_mult = residuals[
        (residuals["delta_C5"] > 0) & (residuals["delta_C5"] % 100 == 0)
    ]
    if not pos_mult.empty:
        print(f"\n  Positive multiple-of-100 rows: {len(pos_mult)}")
        print(f"  Unique symbols: {len(pos_mult['symbol'].unique())}")
        delta_dist = pos_mult["delta_C5"].value_counts().head(10).to_dict()
        print(f"  Top delta values: {delta_dist}")

    print("\n--- C5 STABILITY (by board activity) ---")
    subsets = {
        "G1-only (no other board)": df[
            (df["board_G4"] == 0)
            & (df["board_T1"] == 0)
            & (df["board_T3"] == 0)
            & (df["board_T4"] == 0)
            & (df["board_T6"] == 0)
        ],
        "G4-active": df[df["board_G4"] > 0],
        "T1/T3-active": df[(df["board_T1"] > 0) | (df["board_T3"] > 0)],
        "T4/T6-active": df[(df["board_T4"] > 0) | (df["board_T6"] > 0)],
        "discriminating": df[df["discriminating_session"]],
        "non-discriminating": df[~df["discriminating_session"]],
    }
    for label, sub in subsets.items():
        if len(sub) == 0:
            continue
        ex = int(sub["exact_match_C5"].sum())
        print(f"  {label:<35} : {_fmt(ex, len(sub))}")

    print("\n--- VERDICTS (C1–C4) ---")
    vcs = df["verdict_c1_c4"].value_counts().to_dict()
    for v, n in sorted(vcs.items(), key=lambda x: -x[1]):
        print(f"  {v:<45} : {n:,}")

    print("\n--- PROVENANCE ---")
    print(f"  canonical_trades_source_commit : {CANONICAL_TRADES_SOURCE_COMMIT}")
    print(f"  lineage_status                 : {CANONICAL_TRADES_LINEAGE_STATUS}")
    print(f"  in_current_main_ancestry       : NO")
    print(f"  qualified_liquidity_inputs     : {bool(df['qualified_liquidity_inputs'].any())}")
    print(f"  p0_b_authority_promoted        : NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--determinism-check",
        action="store_true",
        help="Run twice and verify content-identity hashes are identical.",
    )
    args = parser.parse_args()

    print("=== P0-B.2B1: Full-Corpus Reconciliation ===", flush=True)
    df1, h1 = run_reconciliation()
    print_report(df1, h1, run_n=1)

    if args.determinism_check:
        print("\n\n=== DETERMINISM CHECK (run 2) ===", flush=True)
        df2, h2 = run_reconciliation()
        print_report(df2, h2, run_n=2)
        print("\n--- DETERMINISM VERDICT ---")
        print(f"  Run 1 hash : {h1}")
        print(f"  Run 2 hash : {h2}")
        identical = h1 == h2
        print(f"  Identical  : {identical}")
        if not identical:
            print("ERROR: non-deterministic output detected!", file=sys.stderr)
            sys.exit(1)
        else:
            print("PASS: both runs produce identical content.")

    print("\n=== END ===")


if __name__ == "__main__":
    main()
