"""Build the KBS trading-value coverage inventory from retained evidence. Offline only.

Reads the six raw payloads retained at commit ``4a07141`` and the read-only production
database (for an independent session list), and writes derived coverage artifacts under
``operations-review/kbs-trading-value-coverage-20260804/``.

No network request. No database write. The immutable raw payloads are read and never
rewritten.

    python tools/build_kbs_trading_value_coverage.py
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kbs_empirical_basis as kbs  # noqa: E402
import kbs_trading_value_coverage as coverage  # noqa: E402

EVIDENCE_DIR = ROOT / "operations-review" / "kbs-empirical-basis-20260804"
OUT_DIR = ROOT / "operations-review" / "kbs-trading-value-coverage-20260804"
CURRENT_DB = Path("C:/Projects/StockLookup/dashboard-runtime/vn_stock.db")

#: Where the independent session list comes from. Named because the provider publishes no
#: trading calendar, so "which sessions should have come back" is an outside input and a
#: reader is entitled to know whose.
EXPECTED_SESSION_SOURCE = (
    "dashboard-runtime/vn_stock.db:ohlcv[source=VCI] session dates, read-only; used only to "
    "detect a dropped row, never to supply a value"
)


def vci_sessions(ticker: str, start: str, end: str) -> list[str]:
    conn = sqlite3.connect(f"file:{CURRENT_DB.as_posix()}?mode=ro", uri=True)
    try:
        return sorted(
            row[0]
            for row in conn.execute(
                "SELECT date FROM ohlcv WHERE ticker=? AND source='VCI' AND date BETWEEN ? AND ?",
                (ticker, start, end),
            )
        )
    finally:
        conn.close()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    observations = json.loads(
        (EVIDENCE_DIR / "observations.json").read_text(encoding="utf-8")
    )["observations"]

    windows: list[dict] = []
    rows_detail: list[dict] = []
    totals: Counter[str] = Counter()

    for observation in observations:
        raw = (EVIDENCE_DIR / observation["artifact"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != observation["raw_response_sha256"]:
            raise SystemExit(f"artifact hash mismatch: {observation['artifact']}")

        parsed = kbs.parse_daily_payload(json.loads(raw.decode("utf-8")), symbol=observation["ticker"])
        normalized = kbs.normalize_daily(parsed)["rows"]
        lattice = {
            item["session_date"]: item["all_fields_on_lattice"]
            for item in kbs.lattice_profile(normalized)["sessions"]
        }

        records = []
        for row in normalized:
            on_lattice = lattice[row["kbs.session_date"]]
            record = coverage.row_coverage_from_normalized(
                row,
                # The row group is a *description* of where the row sits, not an
                # explanation of anything about va.
                price_basis_row_group=(
                    "on_lattice_tested_rows" if on_lattice else "empirically_adjusted_off_lattice_rows"
                ),
            )
            records.append(record)
            totals[record["trading_value_field_state"]] += 1
            rows_detail.append(
                {
                    **record,
                    "ticker": observation["ticker"],
                    "window_id": observation["window_id"],
                    "raw_artifact": observation["artifact"],
                    "raw_artifact_sha256": digest,
                    "raw_value": row.get(coverage.FIELD),
                    "normalized_field_state": row.get("kbs.observed_daily_trading_value_state"),
                    "usable_in_retained_unit_test": bool(
                        record["trading_value_usable_for_row_statistics"]
                        and row.get("kbs.observed_daily_volume")
                    ),
                }
            )

        start, end = observation["requested_date_range"]
        window = coverage.window_coverage(
            ticker=observation["ticker"],
            requested_window=[start, end],
            row_records=records,
            expected_sessions=vci_sessions(observation["ticker"], start, end),
            expected_session_source=EXPECTED_SESSION_SOURCE,
        )
        window["window_id"] = observation["window_id"]
        window["raw_artifact"] = observation["artifact"]
        window["raw_artifact_sha256"] = digest
        windows.append(window)

    dataset = coverage.dataset_coverage_contract(windows)
    coverage.assert_no_causal_claim(dataset)
    snapshot = coverage.assert_contract_fail_closed(coverage.contract_snapshot(windows))

    inventory = {
        "schema_version": coverage.VERSION,
        "provider": coverage.PROVIDER,
        "source_evidence": "operations-review/kbs-empirical-basis-20260804",
        "expected_session_source": EXPECTED_SESSION_SOURCE,
        "totals": {state: totals.get(state, 0) for state in coverage.ROW_STATES},
        "windows": windows,
        "rows": rows_detail,
        "dataset": dataset,
    }
    (OUT_DIR / "coverage_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (OUT_DIR / "coverage_contract.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    print(json.dumps({
        "totals": inventory["totals"],
        "windows": {
            w["window_id"]: {
                "ticker": w["ticker"],
                "coverage_state": w["coverage_state"],
                "coverage_ratio": w["coverage_ratio"],
                "usable": w["usable_count"],
                "requested": w["requested_session_count"],
            }
            for w in windows
        },
        "cross_window_comparability": dataset["cross_window_comparability"],
        "causal_explanation": dataset["causal_explanation"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
