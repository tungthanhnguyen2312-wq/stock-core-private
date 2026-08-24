"""Materialize the retained-only Historical Matched Traded Value Authority V1 artifact.

The tool performs no network request.  It reads the final retained DNSE Trades
corpus and the already-retained FHSC market-composition artifact, discovers
their exact overlap, verifies complete page chains, and writes a narrow G1
matched-value dataset only for exact independent anchors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_matched_traded_value_authority import (  # noqa: E402
    CONTRACT_VERSION,
    adv20_status,
    qualify_anchor_rows,
    summarize_complete_trade_session,
)


COMPOSITION_ARTIFACT = ROOT / "operations-review" / "dnse-fhsc-market-composition-scaleout-v1-20260821" / "dnse_fhsc_market_composition_scaleout_artifact.json"
CURRENT_UNIVERSE_ARTIFACT = ROOT / "operations-review" / "market-wide-current-liquidity-research-v1-20260823-resumable" / "market_wide_current_liquidity_research_artifact.json"
FINAL_CORPUS_CHECKPOINT = WORKSPACE / "operations-review" / "trades-final-composite-corpus-checkpoint-v1-20260815" / "final_composite_corpus_checkpoint.json"
REPAIR_INDEX = WORKSPACE / "operations-review" / "dnse-trades-targeted-repair-live-v1-20260815" / "repair_result_index.json"
ORIGINAL_RAW_ROOT = WORKSPACE / "operations-review" / "dnse-market-wide-trades-multi-session-v1-20260812"
REPAIR_RAW_ROOT = WORKSPACE / "operations-review" / "dnse-trades-targeted-repair-live-v1-20260815"
FINAL_SESSION_MANIFEST = ORIGINAL_RAW_ROOT / "session=2026-08-11" / "data" / "market_raw_lake" / "manifests" / "DNSE__trades_history__market-wide-trades-40sessions-ending-20260811-v1__20260811.json"
DEFAULT_OUT_DIR = ROOT / "operations-review" / "historical-matched-traded-value-and-adv-authority-v1-20260824"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_decimal(value: str) -> dict[str, Any]:
    return json.loads(value, parse_float=Decimal, parse_int=Decimal)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _page_files(root: Path, session: str, ticker: str) -> list[Path]:
    pattern = f"session={session}/data/market_raw_lake/raw/DNSE/trades_history/**/{ticker}__*.parquet"
    return sorted(root.glob(pattern))


def _load_pages(paths: Iterable[Path], *, ticker: str, session: str) -> tuple[list[dict[str, Any]], list[str]]:
    pages: list[dict[str, Any]] = []
    hashes: list[str] = []
    for path in paths:
        table = pq.ParquetFile(path).read()
        for record in table.to_pylist():
            if record["provider"] != "DNSE" or record["dataset"] != "trades_history" or record["instrument"] != ticker:
                raise RuntimeError(f"unexpected_raw_page_identity:{path}")
            if record["source_event_time"] != session:
                raise RuntimeError(f"unexpected_raw_page_session:{path}")
            body = _json_decimal(record["raw_payload_json"])
            request = _json_decimal(record["request_identity"])
            provenance = _json_decimal(record["provenance_json"])
            pages.append({
                "page_index": int(request["page_index"]),
                "page_cursor": request.get("cursor"),
                "next_page_token": body.get("nextPageToken"),
                "trades": body.get("trades"),
                "source_page_identity": record["observation_id"],
                "request_identity": record["request_identity"],
                "provenance_page_index": int(provenance["page_index"]),
            })
            hashes.append(record["raw_payload_hash"])
    if not pages:
        raise RuntimeError(f"no_retained_pages:{ticker}:{session}")
    if any(page["page_index"] != page["provenance_page_index"] for page in pages):
        raise RuntimeError(f"page_index_lineage_mismatch:{ticker}:{session}")
    return pages, hashes


def _anchor_rows(composition: dict[str, Any], final_sessions: set[str]) -> list[dict[str, Any]]:
    values = {
        (row["ticker"], row["session"]): row
        for row in composition["traded_value"]["matrix"]
        if row.get("fhsc_value_availability") == "OBSERVED" and row.get("fhsc_identity_retained_exact")
    }
    volumes = {
        (row["ticker"], row["session"]): row
        for row in composition["volume"]["volume_matrix"]
        if row.get("fhsc_identity_retained_exact")
    }
    rows: list[dict[str, Any]] = []
    for key in sorted(values.keys() & volumes.keys()):
        value, volume = values[key], volumes[key]
        if value["session"] not in final_sessions:
            continue
        rows.append({
            "ticker": value["ticker"], "session": value["session"],
            "fhsc_identity_retained_exact": True,
            "fhsc_matched_volume": volume["fhsc_matched_volume"],
            "fhsc_matched_value": value["fhsc_matched_value"],
            "fhsc_put_through_value": value["fhsc_put_through_value"],
            "fhsc_total_value": value["fhsc_total_value"],
            "exchange": volume.get("exchange"),
            "volume_classification": volume.get("classification"),
        })
    return rows


def _final_trades_universe() -> set[str]:
    """Use the original 2026-08-11 requested-unit denominator, not repair rows.

    The repair index intentionally lists only units it attempted.  It is not a
    universe manifest and omits a bounded subset of the original 1,660 names.
    """
    manifest = _read_json(FINAL_SESSION_MANIFEST)
    suffix = "__20260811__ALL_BOARDS"
    tickers = {
        unit[: -len(suffix)] for unit in manifest["requested_units"]
        if isinstance(unit, str) and unit.endswith(suffix)
    }
    if len(tickers) != 1660:
        raise RuntimeError(f"unexpected_final_trades_universe_size:{len(tickers)}")
    return tickers


def _content_identity(value: dict[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"historical_matched_traded_value_authority:{digest}"}


def build_artifact() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    composition = _read_json(COMPOSITION_ARTIFACT)
    corpus = _read_json(FINAL_CORPUS_CHECKPOINT)
    universe = _read_json(CURRENT_UNIVERSE_ARTIFACT)
    repair_index = _read_json(REPAIR_INDEX)
    final_sessions = set(corpus["universe"]["sessions"])
    anchors = _anchor_rows(composition, final_sessions)
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    source_selection: list[dict[str, Any]] = []
    for anchor in anchors:
        ticker, session = anchor["ticker"], anchor["session"]
        repaired = _page_files(REPAIR_RAW_ROOT, session, ticker)
        original = _page_files(ORIGINAL_RAW_ROOT, session, ticker)
        if repaired and original:
            raise RuntimeError(f"ambiguous_raw_source:{ticker}:{session}")
        source, paths = ("TARGETED_REPAIR", repaired) if repaired else ("ORIGINAL", original)
        pages, hashes = _load_pages(paths, ticker=ticker, session=session)
        candidate = summarize_complete_trade_session(
            ticker=ticker, session=session, pages=pages, raw_payload_hashes=hashes,
        )
        source_selection.append({
            "ticker": ticker, "session": session, "source": source,
            "raw_page_count": len(pages), "raw_payload_hash_count": len(set(hashes)),
        })
        candidates.append((candidate, anchor))
    qualification = qualify_anchor_rows(candidates)
    qualified = qualification["qualified_rows"]
    qualified_tickers = {row["ticker"] for row in qualified}
    retained_trades_tickers = _final_trades_universe()
    universe_tickers = sorted(universe["records"].keys())
    ledger = []
    for ticker in universe_tickers:
        status = (
            "MATCHED_VALUE_QUALIFIED" if ticker in qualified_tickers
            else "SEMANTIC_BLOCKED_NO_FHSC_VALUE_ANCHOR_SCOPE" if ticker in retained_trades_tickers
            else "MISSING_FROM_RETAINED_TRADES_CORPUS"
        )
        ledger.append({"ticker": ticker, "status": status})
    coverage = corpus["final_review"]["quality_summary"]
    adv = adv20_status(qualified)
    artifact: dict[str, Any] = {
        "artifact_type": "historical_matched_traded_value_authority/v1",
        "contract_version": CONTRACT_VERSION,
        "status": "COMPLETE_LOCAL__QUALIFIED_EMPIRICAL_MATCHED_VALUE_SCOPE__ADV20_NOT_READY",
        "existing_prior_art_reused": {
            "trades_final_composite_corpus": _relative(FINAL_CORPUS_CHECKPOINT),
            "fhsc_market_composition": _relative(COMPOSITION_ARTIFACT),
            "current_1683_candidate_universe": _relative(CURRENT_UNIVERSE_ARTIFACT),
            "targeted_repair_index": _relative(REPAIR_INDEX),
        },
        "trades_source_contract": {
            "provider": "DNSE", "dataset": "trades_history", "raw_retention": "FINAL_COMPOSITE_CORPUS_CHECKPOINT_V1",
            "session_completeness": "PER_TICKER_PAGE_CHAIN_TERMINAL_TOKEN_REQUIRED",
            "no_session_phase_assumption": True,
            "historical_earliest_session": min(final_sessions), "historical_latest_session": max(final_sessions),
            "historical_distinct_sessions": len(final_sessions),
            "historical_distinct_tickers": corpus["universe"]["instrument_count"],
            "historical_ticker_session_rows": coverage["final_logical_success"],
            "complete_ticker_session_rows": coverage["final_logical_success"],
            "remaining_failed_ticker_session_rows": coverage["final_logical_failure"],
        },
        "fhsc_reconciliation_contract": {
            "provider_role": "SHADOW_REFERENCE_PROVIDER", "comparison": "INDEPENDENT_EXACT_MATCHED_VOLUME_AND_VALUE",
            "no_provider_averaging": True, "anchor_overlap_count": len(anchors),
            "reconciliation_counts": qualification["reconciliation_counts"],
        },
        "matched_value_schema": {
            "status": qualification["formula_status"], "formula": qualification["formula"],
            "price_native_unit": qualification["price_native_unit"], "quantity_contract": qualification["quantity_contract"],
            "value_unit": "VND", "qualified_board": "G1", "excluded_boards_preserved": ["G4", "T1", "T3", "T4", "T6"],
        },
        "board_composition_result": {
            "status": "ACTUAL_RETAINED_BOARD_COMPOSITION_REPORTED_PER_TICKER_SESSION",
            "unsupported_boards": "RETAINED_NOT_ZERO_FILLED_AND_NOT_INCLUDED_IN_MATCHED_VALUE",
        },
        "source_selection": source_selection,
        "qualified_rows": qualified,
        "universe_ledger": ledger,
        "universe_summary": {
            "current_candidate_denominator": len(universe_tickers),
            "retained_trades_universe_denominator": len(retained_trades_tickers),
            "exact_identifier_intersection": len(set(universe_tickers) & retained_trades_tickers),
            "matched_value_qualified_tickers": len(qualified_tickers),
            "matched_value_qualified_ticker_sessions": len(qualified),
            "semantic_blocked": sum(row["status"].startswith("SEMANTIC_BLOCKED") for row in ledger),
            "missing_from_retained_trades_corpus": sum(row["status"] == "MISSING_FROM_RETAINED_TRADES_CORPUS" for row in ledger),
            "conflicting": sum(row["qualification_status"] == "CONFLICTING" for row in qualification["rows"]),
        },
        "adv20": {
            "status": "NOT_READY", "expected_complete_sessions": 20, "per_qualified_ticker": adv,
            "ready_count": 0, "reason": "ONLY_THREE_QUALIFIED_COMPLETE_MATCHED_VALUE_SESSIONS_PER_TICKER",
        },
        "cohort_intersections": {
            "watchlist_11": "NOT_RESOLVED__NO_NAMED_11_MEMBER_COHORT_CONTRACT_IN_THIS_DATA_ARTIFACT",
            "preopen_47": "NOT_RESOLVED__NO_NAMED_47_MEMBER_COHORT_CONTRACT_IN_THIS_DATA_ARTIFACT",
            "entry_relevant_90": "NOT_RESOLVED__NO_NAMED_90_MEMBER_COHORT_CONTRACT_IN_THIS_DATA_ARTIFACT",
        },
        "authority_boundary": {
            "authority_result": "NARROW_HISTORICAL_MATCHED_VALUE_OBSERVATION_QUALIFIED_FOR_12_EXACT_ANCHOR_ROWS_ONLY",
            "adv20": "NOT_READY", "liquidity_authority": False, "portfolio_risk_dependency": "NOT_SATISFIED",
            "position_sizing_status": "BLOCKED", "execution_capacity": "BLOCKED", "pit_backtest": "BLOCKED",
            "raw_as_traded": "NOT_PROMOTED", "valuation": "OUT_OF_SCOPE",
        },
        "lane_terminal_status": "OUTCOME_C__NARROW_MATCHED_VALUE_UNLOCK__ADV20_INSUFFICIENT_HISTORY",
        "next_real_data_gate": "OBTAIN_20_EXPECTED_COMPLETE_SESSIONS_WITH_SAME_EXACT_G1_FHSC_VALUE_RECONCILIATION_CONTRACT",
    }
    artifact.update(_content_identity(artifact))
    return artifact, qualified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    artifact, qualified = build_artifact()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    dataset = args.out_dir / "historical_matched_value_qualified_rows.json"
    artifact_path = args.out_dir / "historical_matched_traded_value_authority_artifact.json"
    dataset.write_text(json.dumps(qualified, indent=2, sort_keys=True, default=str), encoding="utf-8")
    artifact["dataset_path"] = _relative(dataset)
    artifact.update(_content_identity(artifact))
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"status": artifact["status"], "artifact": str(artifact_path), "dataset": str(dataset), "identity": artifact["artifact_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
