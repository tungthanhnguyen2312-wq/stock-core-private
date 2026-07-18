#!/usr/bin/env python3
"""Read-only Phase 6 shareholder diagnostic; never calls a provider API."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shareholder_pipeline import load_config, load_manual_overrides  # noqa: E402


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _legacy_status(progress: sqlite3.Row | None, count: int) -> tuple[str, str]:
    if progress is None and count == 0:
        return "not_queried", "ticker_absent_from_shareholders_progress"
    if count:
        return "done", "legacy_shareholder_rows_found"
    status = progress["status"] if progress else None
    if status in {"empty", "source_empty"}:
        return "source_empty", "configured_sources_returned_no_usable_records"
    if status in {"failed", "network_failed"}:
        return "network_failed", "shareholder_source_attempt_failed"
    if status == "unsupported":
        return "unsupported", "configured_sources_do_not_support_shareholders"
    return "parse_failed", "progress_state_has_no_usable_records"


def build_diagnostic(ticker: str = "PAN", root: Path = ROOT) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    config = load_config(root / "config" / "shareholder_pipeline.json")
    manual_path = root / config.get("manual_override_path", "data/manual/shareholders_overrides.csv")
    manual = load_manual_overrides(manual_path, ticker=ticker)
    database_path = root / "vn_stock.db"
    attempts: list[dict[str, Any]] = []
    raw_count = parsed_count = deduplicated_count = 0
    latest_as_of = None
    freshness = {"status": "unknown", "threshold_days": config["freshness_threshold_days"], "age_days": None, "latest_as_of_date": None}
    if not database_path.exists():
        final_status, reason = "not_queried", "database_missing"
        raw_status = "not_queried"
    else:
        connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = _tables(connection)
            if "shareholder_sync_runs" in tables:
                run = connection.execute("SELECT * FROM shareholder_sync_runs WHERE ticker=?", (ticker,)).fetchone()
            else:
                run = None
            if run:
                final_status, reason = run["final_status"], run["reason"]
                raw_count = int(run["raw_record_count"])
                parsed_count = int(run["parsed_record_count"])
                deduplicated_count = int(run["deduplicated_record_count"])
                latest_as_of = run["latest_as_of_date"]
                freshness = json.loads(run["freshness_json"])
                raw_status = "done" if raw_count else final_status
                latest_request = connection.execute(
                    "SELECT MAX(request_timestamp) FROM shareholder_source_attempts WHERE ticker=?", (ticker,)
                ).fetchone()[0]
                if latest_request:
                    attempts = [
                        dict(row) for row in connection.execute(
                            """SELECT source,status,error,reason,error_reason,record_count,parsed_record_count,
                                      request_timestamp,latest_as_of_date
                               FROM shareholder_source_attempts
                               WHERE ticker=? AND request_timestamp=? ORDER BY id""",
                            (ticker, latest_request),
                        )
                    ]
            else:
                progress = connection.execute(
                    "SELECT status,rows,updated FROM shareholders_progress WHERE ticker=?", (ticker,)
                ).fetchone()
                raw_count = connection.execute(
                    "SELECT COUNT(*) FROM shareholders WHERE ticker=?", (ticker,)
                ).fetchone()[0]
                parsed_count = deduplicated_count = raw_count
                final_status, reason = _legacy_status(progress, raw_count)
                raw_status = final_status
        finally:
            connection.close()
    if manual and final_status == "not_queried":
        final_status = "manual_override"
        reason = "verified_manual_records_available_without_api_attempt"
        deduplicated_count = len(manual)
        latest_as_of = max(item.as_of_date for item in manual if item.as_of_date)
        age = (date.today() - date.fromisoformat(latest_as_of)).days
        freshness = {
            "status": "stale" if age > config["freshness_threshold_days"] else "fresh",
            "threshold_days": config["freshness_threshold_days"],
            "age_days": age,
            "latest_as_of_date": latest_as_of,
        }
    return {
        "schema_version": "1.0.0",
        "phase": 6,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "offline_read_only",
        "ticker": ticker,
        "configured_sources": [item["name"] for item in config["sources"] if item.get("enabled", True)],
        "attempts": attempts,
        "raw": {"status": raw_status, "record_count": raw_count},
        "parsed_record_count": parsed_count,
        "deduplicated_record_count": deduplicated_count,
        "latest_as_of_date": latest_as_of,
        "freshness": freshness,
        "manual_override_count": len(manual),
        "final_status": final_status,
        "reason": reason,
        "interpretation_guardrail": "source_empty or not_queried must not be interpreted as zero major shareholders.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an offline shareholder diagnostic")
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_diagnostic(args.ticker)
    output = args.output or ROOT / "reports" / f"shareholder_diagnostics_{args.ticker.lower()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
