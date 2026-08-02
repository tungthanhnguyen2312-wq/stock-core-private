"""Empirically qualify the exact bundle OHLCV close path without mutating market data."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)
from corporate_action_ledger import build_corporate_action_ledger

VERSION = "1.0.0"
MIN_EVENTS = 8
MIN_AGREEMENT = 0.80
HOSE_PRICE_BAND = 0.07


def _sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({path.resolve() for path in paths if path.exists()}, key=str):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _ratio(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value >= 0.10:
        return float(value)
    if isinstance(value, Mapping):
        numerator, denominator = value.get("numerator"), value.get("denominator")
        if isinstance(numerator, (int, float)) and isinstance(denominator, (int, float)) and denominator > 0:
            result = numerator / denominator
            return result if result >= 0.10 else None
    return None


def _series(conn: sqlite3.Connection, ticker: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT date, close, source FROM ohlcv WHERE ticker=? ORDER BY date", (ticker,)
    ).fetchall()
    return [{"date": row[0], "close": float(row[1]), "provider": row[2]} for row in rows if row[1] is not None]


def analyze_event(event: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    ratio = _ratio(event.get("entitlement_ratio"))
    ex_date = event.get("ex_date") or event.get("effective_date")
    event_id = event.get("canonical_event_id")
    base = {"event_id": event_id, "ticker": event.get("ticker"), "ex_date": ex_date, "ratio": ratio,
            "event_type": event.get("event_type"), "status": "excluded"}
    if event.get("qualification_state") != "qualified" or event.get("event_type") not in {"stock_dividend", "bonus_share"}:
        return {**base, "reason": "event_type_or_evidence_unqualified"}
    if not ex_date or ratio is None:
        return {**base, "reason": "missing_qualified_ex_date_or_ratio"}
    before = [row["close"] for row in rows if row["date"] < ex_date][-3:]
    after = [row["close"] for row in rows if row["date"] >= ex_date][:3]
    if len(before) < 3 or len(after) < 3:
        return {**base, "reason": "insufficient_pre_or_post_sessions"}
    pre, post = median(before), median(after)
    observed = post / pre - 1
    expected_raw = 1 / (1 + ratio) - 1
    raw_distance, adjusted_distance = abs(observed - expected_raw), abs(observed)
    # HOSE's normal daily price-band allowance is retained as an explicit tolerance rather
    # than treating a one-day move as mechanically exact.
    tolerance = max(0.03, HOSE_PRICE_BAND * 0.8)
    label = "raw" if raw_distance <= tolerance and raw_distance < adjusted_distance else "adjusted" if adjusted_distance <= tolerance and adjusted_distance < raw_distance else "inconclusive"
    return {**base, "status": "accepted" if label != "inconclusive" else "excluded", "classification": label,
            "pre_prices": before, "post_prices": after, "pre_median": pre, "post_median": post,
            "observed_discontinuity": observed, "expected_raw_discontinuity": expected_raw,
            "raw_distance": raw_distance, "adjusted_distance": adjusted_distance,
            "hose_price_band_allowance": HOSE_PRICE_BAND,
            **({} if label != "inconclusive" else {"reason": "continuity_not_distinct_within_price_band_allowance"})}


def build_contract(db_path: Path, evidence_root: Path, tested_at: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        events: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        provider_versions: set[str] = set()
        for ticker in ("HPG", "VNM"):
            ledger = build_corporate_action_ledger(evidence_root, ticker)
            if ledger.get("status") != "available":
                excluded.append({"ticker": ticker, "reason": "no_qualified_retained_corporate_action_events"})
                continue
            rows = _series(conn, ticker)
            providers = {row["provider"] for row in rows}
            if providers != {"VCI"}:
                excluded.append({"ticker": ticker, "reason": "mixed_or_noncanonical_ohlcv_provider", "providers": sorted(providers)})
                continue
            for event in ledger.get("ledger_entries", []):
                item = analyze_event(event, rows)
                diagnostics.append(item)
                if item["status"] == "accepted":
                    events.append(item)
                else:
                    excluded.append({"event_id": item.get("event_id"), "ticker": ticker, "reason": item.get("reason")})
        counts = Counter(item.get("classification") for item in events)
        dominant, dominant_count = (counts.most_common(1)[0] if counts else (None, 0))
        agreement = dominant_count / len(events) if events else 0.0
        contradictions = [item["event_id"] for item in events if item.get("classification") != dominant]
        # The schema has no retained library/provider version. It is a required qualifier,
        # so it prevents a determined result even if future event continuity is consistent.
        provider_version = "unretained_in_ohlcv_schema"
        if len(events) < MIN_EVENTS:
            status, value = "INCONCLUSIVE", "unknown"
        elif contradictions or agreement < MIN_AGREEMENT:
            status, value = "MIXED_OR_VERSION_DEPENDENT", "unknown"
        elif provider_version == "unretained_in_ohlcv_schema":
            status, value = "MIXED_OR_VERSION_DEPENDENT", "unknown"
        else:
            status = "DETERMINED_EMPIRICALLY_RAW" if dominant == "raw" else "DETERMINED_EMPIRICALLY_ADJUSTED"
            value = dominant
        manifest = evidence_root / "data" / "official-evidence" / "manifest.json"
        return {
            "schema_version": VERSION, "status": status, "value": value, "provider": "VCI",
            "provider_version": provider_version, "canonical_data_path": "dashboard-runtime/vn_stock.db:ohlcv.close -> export_ai_bundle.load_ohlcv_recent",
            "method": "empirical_corporate_action_continuity", "accepted_events": events,
            "excluded_events": excluded, "event_diagnostics": diagnostics, "agreement_rate": agreement,
            "contradictory_events": contradictions, "tested_at": tested_at,
            "input_data_hash": _sha256([db_path, manifest]), "retest_after": "qualified retained stock-dividend/bonus event set reaches eight non-overlapping events and source version is retained",
            "limitations": ["Only the VCI rows in the current ohlcv table are in scope.", "Provider/library version is not retained in the active ohlcv schema.", "Volume basis and current shares are independent unqualified blockers.", "Cash-dividend test not run: no qualified retained compatible cash-dividend events."],
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tested-at", required=True)
    args = parser.parse_args(argv)
    contract = build_contract(args.db, args.evidence_root, args.tested_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
