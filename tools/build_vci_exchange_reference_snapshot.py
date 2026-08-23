"""Freeze the retained ``metadata.exchange`` reference into a hashed snapshot artifact.

Read-only against ``vn_stock.db``: opens with ``mode=ro`` and ``PRAGMA query_only = ON``, one
``SELECT``, connection closed immediately after. No write, no long-running scan -- safe under
this project's single-writer SQLite discipline.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_paths import runtime_root as resolve_runtime_root
from vci_exchange_reference_snapshot import build_snapshot

VN_TZ = timezone(timedelta(hours=7))
DEFAULT_OUTPUT = ROOT / "operations-review/vci-exchange-reference-snapshot-v1-20260823/vci_exchange_reference_snapshot_artifact.json"


def _read_metadata_rows(database: Path) -> list[dict[str, object]]:
    if not database.is_file():
        raise FileNotFoundError(f"runtime_database_missing:{database}")
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute("SELECT ticker, exchange, updated FROM metadata ORDER BY ticker")
        return [{"ticker": row[0], "exchange": row[1], "updated": row[2]} for row in cursor.fetchall()]
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None, help="Directory containing vn_stock.db (defaults via STOCK_LOOKUP_RUNTIME_ROOT)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--retrieved-at", default=None, help="ISO timestamp override (defaults to current time)")
    args = parser.parse_args(argv)

    runtime = resolve_runtime_root(args.runtime_root)
    rows = _read_metadata_rows(runtime / "vn_stock.db")
    retrieved_at = args.retrieved_at or datetime.now(VN_TZ).isoformat()

    snapshot = build_snapshot(rows=rows, retrieved_at=retrieved_at)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(snapshot["snapshot_identity"])
    print(f"row_count={snapshot['row_count']} by_exchange={snapshot['by_exchange']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
