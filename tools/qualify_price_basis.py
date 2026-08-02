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
from price_basis_events import project_price_test_events

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
    has_lineage = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ohlcv_lineage'"
    ).fetchone() is not None
    if has_lineage:
        rows = conn.execute(
            """SELECT o.date, o.close, o.source, l.provider_version, l.adapter_schema_version,
                      l.endpoint, l.canonical_field, l.retrieved_at, l.source_record_hash, l.unit_scale
               FROM ohlcv o LEFT JOIN ohlcv_lineage l
                 ON l.ticker=o.ticker AND l.trading_session_date=o.date
               WHERE o.ticker=? ORDER BY o.date""", (ticker,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT date, close, source FROM ohlcv WHERE ticker=? ORDER BY date", (ticker,)).fetchall()
    result = []
    for row in rows:
        if row[1] is None:
            continue
        result.append({
            "date": row[0], "close": float(row[1]), "provider": row[2],
            "provider_version": row[3] if has_lineage and row[3] else "legacy_version_unknown",
            "adapter_schema_version": row[4] if has_lineage and row[4] else "legacy_lineage_unknown",
            "endpoint": row[5] if has_lineage and row[5] else None,
            "canonical_field": row[6] if has_lineage and row[6] else "ohlcv.close",
            "retrieved_at": row[7] if has_lineage and row[7] else None,
            "source_record_hash": row[8] if has_lineage and row[8] else None,
            "unit_scale": row[9] if has_lineage and row[9] else None,
        })
    return result


def analyze_event(event: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    ratio = _ratio(event.get("entitlement_ratio"))
    ex_date = event.get("ex_date") or event.get("effective_date")
    event_id = event.get("canonical_event_id")
    base = {"event_id": event_id, "ticker": event.get("ticker"), "ex_date": ex_date, "ratio": ratio,
            "event_type": event.get("event_type"), "status": "excluded"}
    qualified = event.get("qualified_for_price_basis_test") or event.get("qualification_state") == "qualified"
    if not qualified or event.get("event_type") not in {"stock_dividend", "bonus_share", "stock_split"}:
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
        adapter_versions: set[str] = set()
        provider_names: set[str] = set()
        for ticker in ("HPG", "VNM"):
            ledger = build_corporate_action_ledger(evidence_root, ticker)
            rows = _series(conn, ticker)
            providers = {row["provider"] for row in rows}
            versions = {row["provider_version"] for row in rows}
            adapters = {row["adapter_schema_version"] for row in rows}
            if providers != {"VCI"}:
                excluded.append({"ticker": ticker, "reason": "mixed_or_noncanonical_ohlcv_provider", "providers": sorted(providers)})
                continue
            if len(versions) != 1 or "legacy_version_unknown" in versions:
                excluded.append({"ticker": ticker, "reason": "legacy_or_mixed_ohlcv_provider_version", "provider_versions": sorted(versions)})
                continue
            provider_names.update(providers)
            provider_versions.update(versions)
            adapter_versions.update(adapters)
            projection = project_price_test_events(ledger.get("ledger_entries", []))
            excluded.extend(projection["excluded"])
            if ledger.get("status") != "available" and not projection["excluded"]:
                excluded.append({"ticker": ticker, "reason": "no_qualified_retained_corporate_action_events"})
            for event in projection["accepted"]:
                if event["provider"] != next(iter(providers)) or event["provider_version"] != next(iter(versions)):
                    excluded.append({"event_id": event.get("event_id"), "ticker": ticker, "reason": "event_provider_version_not_active_ohlcv_path"})
                    continue
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
        provider_version = next(iter(provider_versions)) if len(provider_versions) == 1 else "legacy_version_unknown"
        adapter_version = next(iter(adapter_versions)) if len(adapter_versions) == 1 else "legacy_lineage_unknown"
        if len(events) < MIN_EVENTS:
            status, value = "INCONCLUSIVE", "unknown"
        elif contradictions or agreement < MIN_AGREEMENT:
            status, value = "MIXED_OR_VERSION_DEPENDENT", "unknown"
        elif provider_version == "legacy_version_unknown":
            status, value = "MIXED_OR_VERSION_DEPENDENT", "unknown"
        else:
            status = "DETERMINED_EMPIRICALLY_RAW" if dominant == "raw" else "DETERMINED_EMPIRICALLY_ADJUSTED"
            value = dominant
        manifest = evidence_root / "data" / "official-evidence" / "manifest.json"
        return {
            "schema_version": VERSION, "status": status, "value": value, "provider": next(iter(provider_names), "VCI"),
            "provider_version": provider_version, "adapter_schema_version": adapter_version,
            "canonical_data_path": "dashboard-runtime/vn_stock.db:ohlcv.close -> export_ai_bundle.load_ohlcv_recent",
            "method": "empirical_corporate_action_continuity", "accepted_events": events,
            "excluded_events": excluded, "event_diagnostics": diagnostics, "agreement_rate": agreement,
            "contradictory_events": contradictions, "tested_at": tested_at,
            "input_data_hash": _sha256([db_path, manifest]), "retest_after": "eight qualified retained stock-action events and one retained active-path provider version",
            "limitations": ["Only the VCI rows in the current ohlcv table are in scope.", "Legacy OHLCV rows without ohlcv_lineage remain provider-version unknown.", "Volume basis and current shares are independent unqualified blockers.", "Cash-dividend test not run: no qualified retained compatible cash-dividend events."],
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
