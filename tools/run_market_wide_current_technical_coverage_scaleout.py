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
from historical_series_failover import (
    build_provider_series,
    recovery_record_from_selection,
    select_feature_safe_series,
    snapshot_target_close,
    vnstock_provider_series,
)
from vnstock_rate_governor import VnstockRateGovernor, set_active_governor
from vn_stock_pipeline import fetch_single_source


BASELINE = ROOT / "operations-review/market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json"
SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json"
OUT = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823"
VN_TZ = timezone(timedelta(hours=7))
MAX_TRANSIENT_TRANSPORT_ATTEMPTS = 3
# A full current-universe fallback can require two Vnstock provider attempts per candidate.
# At the governed 45 RPM ceiling, 952 candidates remain below this bounded window.  The
# limit is an operational guard, not a source-quality verdict.
HISTORICAL_FALLBACK_RUNTIME_BUDGET_SECONDS = 45 * 60

# ``fetch_capability_raw`` represents request transport exceptions with these stable error-code
# suffixes. Keep this list narrower than its generic ``is_retryable`` helper: this recovery path
# must not reissue rate-limited, authentication, HTTP, or provider-semantic responses.
TRANSIENT_TRANSPORT_ERROR_CODES = frozenset({
    "request_failed_ConnectionError",
    "request_failed_ConnectTimeout",
    "request_failed_ReadTimeout",
    "request_failed_Timeout",
    "request_failed_TimeoutError",
})


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _batch_path(out: Path, batch: int) -> Path:
    return out / "batches" / f"batch-{batch:03d}.json"


def _dnse_series(*, record: Mapping, ticker: str, target_session: str, retrieved_at: str, start: str, end: str) -> dict:
    success = record.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    return build_provider_series(
        ticker=ticker, provider="DNSE", target_session=target_session, requested_at=retrieved_at,
        requested_start=start, requested_end=end, rows=record.get("observations") or [],
        retrieval_identity=record.get("payload_sha256"), request_attempts=int(record.get("attempt_count") or 0),
        native_representation="DNSE_PROVIDER_NATIVE_RAW", price_representation="DNSE_PROVIDER_NATIVE_RAW",
        price_basis="CURRENT_RESEARCH_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
        volume_basis="DNSE_PROVIDER_NATIVE_VOLUME_SEMANTICS_UNQUALIFIED",
        status="SUCCESS" if success else "DNSE_RECOVERY_UNAVAILABLE", reason=record.get("reason"),
    )


def _feature_safe_record(*, ticker: str, dnse_record: Mapping, snapshot_record: Mapping,
                         target_session: str, retrieved_at: str, start: str, end: str) -> dict:
    """Keep DNSE primary; call KBS then VCI only when a compatible close history is absent.

    A clean KBS no-data result deliberately stops here: retained qualification treats it as no
    incremental historical yield, not a reason to burn VCI traffic. Transport/malformed/target-
    close-mismatch outcomes can still justify VCI because they are not a clean capability miss.
    """
    series = {
        "DNSE": _dnse_series(record=dnse_record, ticker=ticker, target_session=target_session,
                              retrieved_at=retrieved_at, start=start, end=end),
    }
    # A malformed/minimal snapshot fixture (or a real target-session record missing its close)
    # cannot prove cross-provider compatibility.  Keep the established DNSE record intact and
    # do not spend a secondary-provider request merely to obtain a series we must reject.
    if snapshot_target_close(snapshot_record, target_session) is None:
        return {
            **dict(dnse_record), "historical_series": series["DNSE"],
            "attempted_provider_series": series,
            "selection": {
                "ticker": ticker, "target_session": target_session,
                "feature_family": "TECHNICAL_CLOSE_HISTORY", "selected_provider": None,
                "fitness": "BLOCKED", "blocked_reason": "EXACT_SESSION_TARGET_CLOSE_MISSING",
            },
        }
    selection = select_feature_safe_series(
        ticker=ticker, target_session=target_session, feature_family="TECHNICAL_CLOSE_HISTORY",
        snapshot_record=snapshot_record, provider_series=series,
    )
    if selection.get("fitness") != "READY":
        series["KBS"] = vnstock_provider_series(
            ticker=ticker, provider="KBS", target_session=target_session, requested_at=retrieved_at,
            requested_start=start, requested_end=end, fetch=fetch_single_source,
        )
        selection = select_feature_safe_series(
            ticker=ticker, target_session=target_session, feature_family="TECHNICAL_CLOSE_HISTORY",
            snapshot_record=snapshot_record, provider_series=series,
        )
        if selection.get("fitness") != "READY" and series["KBS"].get("reason") != "CLEAN_MISSING":
            series["VCI"] = vnstock_provider_series(
                ticker=ticker, provider="VCI", target_session=target_session, requested_at=retrieved_at,
                requested_start=start, requested_end=end, fetch=fetch_single_source,
            )
            selection = select_feature_safe_series(
                ticker=ticker, target_session=target_session, feature_family="TECHNICAL_CLOSE_HISTORY",
                snapshot_record=snapshot_record, provider_series=series,
            )
        elif selection.get("fitness") != "READY":
            selection = {**selection, "blocked_reason": "KBS_CLEAN_MISSING_NO_INCREMENTAL_VCI_FALLBACK"}
    return recovery_record_from_selection(selection=selection, provider_series=series)


def _recover_records(*, snapshot: Mapping, tickers: list[str]) -> tuple[list[dict], dict]:
    """Fetch a cohort under one invocation-scoped Vnstock governor.

    DNSE remains the primary request.  KBS and VCI are called only by the feature-safe
    selector, and therefore never contribute a mixed-provider series or a volume feature.
    """
    target = datetime.fromisoformat(snapshot["resolved_completed_session"]).replace(tzinfo=VN_TZ)
    start = target - timedelta(days=EXACT_SESSION_OHLC_LOOKBACK_CALENDAR_DAYS)
    end = target + timedelta(days=1) - timedelta(seconds=1)
    original = {key: os.environ.get(key) for pair in CREDENTIAL_ENV_PAIRS for key in pair}
    governor = VnstockRateGovernor()
    previous_governor = set_active_governor(governor)
    try:
        ensure_credentials_loaded()
        credentials = credentials_for_request()
        if not credentials:
            raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
        records: list[dict] = []
        for ticker in tickers:
            query = {"symbol": ticker, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}
            for attempt_count in range(1, MAX_TRANSIENT_TRANSPORT_ATTEMPTS + 1):
                response = fetch_capability_raw("ohlc", api_key=credentials[0], api_secret=credentials[1], query=query)
                if (str(response.get("error_code", "")) not in TRANSIENT_TRANSPORT_ERROR_CODES
                        or attempt_count == MAX_TRANSIENT_TRANSPORT_ATTEMPTS):
                    break
            dnse_record = recovery_record(
                ticker=ticker, response=response, target_session=snapshot["resolved_completed_session"],
                query=query, retrieved_at=datetime.now(VN_TZ).isoformat(), attempt_count=attempt_count,
            )
            retrieved_at = datetime.now(VN_TZ).isoformat()
            record = _feature_safe_record(
                ticker=ticker, dnse_record=dnse_record,
                snapshot_record=(snapshot.get("records") or {}).get(ticker) or {},
                target_session=snapshot["resolved_completed_session"], retrieved_at=retrieved_at,
                start=start.date().isoformat(), end=target.date().isoformat(),
            )
            records.append({**record, "raw_response_body": response.get("body") if response.get("ok") else None})
        diagnostic = governor.diagnostic()
        diagnostic.update({
            "scope": "ONE_HISTORICAL_RECOVERY_INVOCATION",
            "runtime_budget_seconds": HISTORICAL_FALLBACK_RUNTIME_BUDGET_SECONDS,
            "projected_maximum_governor_seconds": round(
                governor.estimated_minimum_seconds_for(len(tickers) * 2), 3
            ),
        })
        return records, diagnostic
    finally:
        set_active_governor(previous_governor)
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    records, diagnostic = _recover_records(snapshot=snapshot, tickers=tickers)
    payload = {
        "batch": batch, "batch_size": batch_size, "target_session": snapshot["resolved_completed_session"],
        "source_snapshot_identity": snapshot.get("snapshot_identity"), "records": records,
        "history_rate_governor": diagnostic,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(path)


def run_all(*, baseline: Mapping, snapshot: Mapping, out: Path) -> None:
    """Materialize all recovery candidates in a single governed process.

    Daily uses this rather than launching one process per ten tickers.  It makes the rate
    governor genuinely global for every KBS/VCI outbound call in the recovery invocation.
    """
    output = out / "market_wide_current_technical_coverage_recovery_artifact.json"
    if output.exists():
        print(f"REUSED {output}")
        return
    candidates = recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot)
    if not candidates:
        records, diagnostic = [], {
            "contract_version": "vnstock_rate_governor/v1", "scope": "ONE_HISTORICAL_RECOVERY_INVOCATION",
            "attempts": 0, "cache_hits": 0, "runtime_budget_seconds": HISTORICAL_FALLBACK_RUNTIME_BUDGET_SECONDS,
            "projected_maximum_governor_seconds": 0.0,
        }
    else:
        records, diagnostic = _recover_records(snapshot=snapshot, tickers=candidates)
    artifact = build_recovery_artifact(
        baseline_artifact=baseline, p3f9b_snapshot=snapshot,
        batch_records=[{"records": records, "history_rate_governor": diagnostic}],
    )
    artifact["operational_summary"]["HISTORY_RECOVERY_RUNTIME"] = diagnostic
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(output)


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
    # Zero recovery candidates means run_batch() never ran, so `out` itself was never created (its
    # only creator today is run_batch()'s own mkdir(parents=True) for the sibling batches/
    # directory). A legitimate zero-candidate recovery cohort must still consolidate to the real
    # empty artifact build_recovery_artifact already produces, not crash with FileNotFoundError.
    output.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--all", action="store_true", help="Recover all candidates under one Vnstock governor.")
    args = parser.parse_args(argv)
    actions = int(args.batch is not None) + int(args.consolidate) + int(args.all)
    if actions != 1:
        parser.error("choose exactly one of --batch, --consolidate, or --all")
    baseline, snapshot, out = _load(Path(args.baseline)), _load(Path(args.snapshot)), Path(args.out_dir)
    if args.consolidate:
        consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=args.batch_size)
    elif args.all:
        run_all(baseline=baseline, snapshot=snapshot, out=out)
    else:
        run_batch(baseline=baseline, snapshot=snapshot, out=out, batch=args.batch, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
