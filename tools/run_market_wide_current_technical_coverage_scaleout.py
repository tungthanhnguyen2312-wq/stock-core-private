"""Foreground-resumable DNSE extended-history recovery for current technical coverage."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_access import CREDENTIAL_ENV_PAIRS, credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
from dnse_secrets_env import ensure_credentials_loaded
from market_wide_current_technical_coverage_scaleout import (
    build_recovery_artifact,
    recovery_candidates,
    recovery_record,
)
from mva_exact_session_snapshot import EXACT_SESSION_OHLC_LOOKBACK_CALENDAR_DAYS


BASELINE = ROOT / "operations-review/market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json"
SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json"
OUT = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823"
VN_TZ = timezone(timedelta(hours=7))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _batch_path(out: Path, batch: int) -> Path:
    return out / "batches" / f"batch-{batch:03d}.json"


def run_batch(*, baseline: Mapping, snapshot: Mapping, out: Path, batch: int, batch_size: int) -> None:
    candidates = recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot)
    start_at, end_at = batch * batch_size, (batch + 1) * batch_size
    tickers = candidates[start_at:end_at]
    if not tickers:
        raise ValueError("BATCH_OUT_OF_RANGE")
    path = _batch_path(out, batch)
    if path.exists():
        print(f"REUSED {path}")
        return
    target = datetime.fromisoformat(snapshot["resolved_completed_session"]).replace(tzinfo=VN_TZ)
    start = target - timedelta(days=EXACT_SESSION_OHLC_LOOKBACK_CALENDAR_DAYS)
    end = target + timedelta(days=1) - timedelta(seconds=1)
    original = {key: os.environ.get(key) for pair in CREDENTIAL_ENV_PAIRS for key in pair}
    try:
        ensure_credentials_loaded()
        credentials = credentials_for_request()
        if not credentials:
            raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
        records = []
        for ticker in tickers:
            query = {"symbol": ticker, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}
            response = fetch_capability_raw("ohlc", api_key=credentials[0], api_secret=credentials[1], query=query)
            record = recovery_record(
                ticker=ticker, response=response, target_session=snapshot["resolved_completed_session"],
                query=query, retrieved_at=datetime.now(VN_TZ).isoformat(),
            )
            records.append({**record, "raw_response_body": response.get("body") if response.get("ok") else None})
        payload = {
            "batch": batch, "batch_size": batch_size, "target_session": snapshot["resolved_completed_session"],
            "source_snapshot_identity": snapshot.get("snapshot_identity"), "records": records,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(path)
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def consolidate(*, baseline: Mapping, snapshot: Mapping, out: Path, batch_size: int) -> None:
    candidates = recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot)
    expected = (len(candidates) + batch_size - 1) // batch_size
    batches = []
    for batch in range(expected):
        path = _batch_path(out, batch)
        if not path.exists():
            raise ValueError(f"MISSING_RECOVERY_BATCH:{batch}")
        batches.append(_load(path))
    artifact = build_recovery_artifact(baseline_artifact=baseline, p3f9b_snapshot=snapshot, batch_records=batches)
    output = out / "market_wide_current_technical_coverage_recovery_artifact.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--snapshot", default=str(SNAPSHOT))
    parser.add_argument("--out-dir", default=str(OUT))
    parser.add_argument("--batch", type=int)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--consolidate", action="store_true")
    args = parser.parse_args(argv)
    if (args.batch is None) == (not args.consolidate):
        parser.error("choose exactly one of --batch or --consolidate")
    baseline, snapshot, out = _load(Path(args.baseline)), _load(Path(args.snapshot)), Path(args.out_dir)
    if args.consolidate:
        consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=args.batch_size)
    else:
        run_batch(baseline=baseline, snapshot=snapshot, out=out, batch=args.batch, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
