"""CLI: bounded, checkpointed bulk raw DNSE OHLC ingestion across many symbols.

Dataset v1 is OHLC (``dnse_bulk_market_data`` capability ``"ohlc"``, family
``"ohlc_history"``) -- the one dataset every equity/index instrument shares
and the direct input shape ``market_feature_store.REQUIRED_MARKET_COLUMNS``
already expects. ``resolution="1D"`` is hardcoded, not a flag: the plain
``"D"`` token is a known-broken alternative (returns null/empty; see
``tools/dnse_market_data_probe.py``'s own documented finding from the
2026-08-10 qualification pass) and this milestone was explicitly told to
reuse already-established first-party mappings rather than let a caller
rediscover that the hard way.

Symbols come from ``--symbols`` (explicit, comma-separated) or
``--universe-snapshot`` (a Parquet file written by
``tools/discover_market_universe.py``) -- never a hardcoded ticker list.
For the current ``type=STOCK`` OHLC contract, snapshot mode selects only
records classified from the directly observed DNSE ``securityGroupId="ST"``
mapping as ``EQUITY``. Unknown groups stay retained in the security master
and coverage metadata; they are not guessed to be eligible stock symbols.

CHECKPOINT / RESTART
    ``run_scope_id`` is a deterministic hash of (dataset, sorted symbols,
    date range, resolution): the same logical request always maps to the
    same checkpoint, so re-running it after an interruption resumes -- units
    already ``"success"`` are never re-fetched. A different symbol set or
    date range is a different scope and starts its own checkpoint, never
    silently mixed with another request's state. ``run_id`` (a fresh
    timestamp per invocation) only names *this invocation's* raw-file
    directory; the checkpoint itself is keyed by the stable ``run_scope_id``.

FAILURE HANDLING
    ``authentication_failed`` aborts the entire run immediately (matches
    ``tools/dnse_market_data_probe.py``'s established convention -- retrying
    with the same rejected credentials cannot succeed). A rate-limited or
    transport failure is retried with bounded exponential backoff
    (``--max-retries``, ``--backoff-seconds``). Any other failure (e.g. an
    unknown symbol) is recorded against that one unit and the run continues
    -- one bad symbol must never stop the rest of the universe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credential_status, credentials_for_request  # noqa: E402
from dnse_bulk_market_data import fetch_capability_raw, is_retryable  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
import market_raw_lake as lake  # noqa: E402
from market_data_contracts import RawObservation  # noqa: E402
from market_wide_coverage_report import build_coverage_report, save_coverage_report  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402
import vn_time  # noqa: E402

CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"
PROVIDER = "DNSE"
DATASET = "ohlc"
RESOLUTION = "1D"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_REQUEST_DELAY_SECONDS = 0.2


class RunScopeLockedError(RuntimeError):
    """A different process is already writing this deterministic run scope."""


def _run_scope_lock_path(runtime_root: Path, run_scope_id: str) -> Path:
    return lake.checkpoint_path(runtime_root, PROVIDER, DATASET, run_scope_id).with_suffix(".lock")


@contextmanager
def _exclusive_run_scope_lock(runtime_root: Path, run_scope_id: str):
    """Fail closed when another process owns the same checkpoint scope."""
    path = _run_scope_lock_path(runtime_root, run_scope_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise RunScopeLockedError(f"run scope is already active: {run_scope_id}") from exc
    try:
        os.write(fd, f"run_scope_id={run_scope_id}\n".encode("utf-8"))
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def date_window_epoch(date_from: str, date_to: str) -> tuple[int, int]:
    """[00:00 date_from, 23:59:59 date_to] Asia/Ho_Chi_Minh, as epoch seconds --
    the multi-day window shape already proven to work for ohlc's
    resolution="1D" token (see tools/dnse_market_data_probe.py)."""
    start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=vn_time.VN_TZ)
    end = (datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=vn_time.VN_TZ)
          + timedelta(days=1) - timedelta(seconds=1))
    return _epoch(start), _epoch(end)


def default_date_range(lookback_days: int) -> tuple[str, str]:
    today = vn_time.vn_now().date()
    return (today - timedelta(days=lookback_days)).isoformat(), today.isoformat()


def compute_run_scope_id(*, dataset: str, symbols: Sequence[str], date_from: str, date_to: str,
                         resolution: str, instrument_type: str) -> str:
    identity = _canonical_json({
        "dataset": dataset, "symbols": sorted(set(symbols)), "from": date_from, "to": date_to,
        "resolution": resolution, "type": instrument_type,
    })
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def load_symbols_from_universe_snapshot(path: Path, *, instrument_type: str = "STOCK") -> list[str]:
    import pandas as pd

    frame = pd.read_parquet(path)
    if "symbol" not in frame.columns:
        raise ValueError(f"universe snapshot {path} has no 'symbol' column")
    if instrument_type == "STOCK":
        if "instrument_class" not in frame.columns:
            raise ValueError(f"universe snapshot {path} has no 'instrument_class' for STOCK selection")
        frame = frame[frame["instrument_class"].eq("EQUITY")]
    symbols = sorted(frame["symbol"].astype(str).str.upper().unique())
    if not symbols:
        raise ValueError(f"universe snapshot {path} has no symbols eligible for {instrument_type}")
    return symbols


def load_universe_context(path: Path | None, *, selected_symbols: Sequence[str] | None = None) -> dict[str, Any]:
    """Best-effort universe context for the coverage report. Absent a
    snapshot, the "universe" is just whatever symbols were explicitly
    requested -- a smaller, still-honest context, clearly not a full sweep."""
    if path is None:
        return {}
    import pandas as pd

    frame = pd.read_parquet(path)
    by_exchange = frame["exchange_raw"].fillna("unknown").value_counts().to_dict() if "exchange_raw" in frame else {}
    by_class = (frame["instrument_class"].value_counts().to_dict()
               if "instrument_class" in frame else {})
    all_symbols = sorted(frame["symbol"].astype(str).str.upper().unique())
    selected = sorted({symbol.upper() for symbol in (selected_symbols or all_symbols)})
    return {
        "universe_symbols": selected,
        "security_master_discovered_count": len(all_symbols),
        "universe_by_exchange": {str(k): int(v) for k, v in by_exchange.items()},
        "universe_by_instrument_class": {str(k): int(v) for k, v in by_class.items()},
    }


def _ohlc_observation(symbol: str, response: dict[str, Any], *, retrieved_at: str) -> RawObservation:
    body = response.get("body") or {}
    payload_json = _canonical_json(body)
    return RawObservation(
        provider=PROVIDER, dataset=DATASET, instrument=symbol, retrieved_at=retrieved_at,
        request_identity=_canonical_json(response.get("query_sent") or {}),
        raw_payload_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        schema_version="1.0.0", raw_payload=body,
        provenance={"endpoint": response.get("endpoint"), "http_status": response.get("http_status"),
                    "elapsed_ms": response.get("elapsed_ms")},
    )


def _fetch_with_retry(symbol: str, query: dict[str, Any], *, api_key: str, api_secret: str,
                      max_retries: int, backoff_seconds: float,
                      request_get: Callable[..., Any] | None,
                      sleep: Callable[[float], None]) -> dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        response = fetch_capability_raw("ohlc", api_key=api_key, api_secret=api_secret, symbol=None,
                                        query=query, request_get=request_get)
        response["attempts"] = attempt
        if response.get("ok") or response.get("error_code") == "authentication_failed":
            return response
        if not is_retryable(response) or attempt > max_retries:
            return response
        sleep(backoff_seconds * (2 ** (attempt - 1)))


def run(*, runtime_root: Path, api_key: str, api_secret: str, symbols: Sequence[str],
       date_from: str, date_to: str, instrument_type: str = "STOCK", run_id: str,
       max_retries: int = DEFAULT_MAX_RETRIES, backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
       request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
       request_get: Callable[..., Any] | None = None,
       sleep: Callable[[float], None] = time.sleep,
       universe_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Acquire exclusive ownership before checkpointed bulk OHLC ingestion."""
    normalized_symbols = sorted({symbol.upper() for symbol in symbols})
    run_scope_id = compute_run_scope_id(
        dataset=DATASET, symbols=normalized_symbols, date_from=date_from, date_to=date_to,
        resolution=RESOLUTION, instrument_type=instrument_type,
    )
    with _exclusive_run_scope_lock(runtime_root, run_scope_id):
        return _run_unlocked(
            runtime_root=runtime_root, api_key=api_key, api_secret=api_secret,
            symbols=normalized_symbols, date_from=date_from, date_to=date_to,
            instrument_type=instrument_type, run_id=run_id, max_retries=max_retries,
            backoff_seconds=backoff_seconds, request_delay_seconds=request_delay_seconds,
            request_get=request_get, sleep=sleep, universe_context=universe_context,
        )


def _run_unlocked(*, runtime_root: Path, api_key: str, api_secret: str, symbols: Sequence[str],
       date_from: str, date_to: str, instrument_type: str = "STOCK", run_id: str,
       max_retries: int = DEFAULT_MAX_RETRIES, backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
       request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
       request_get: Callable[..., Any] | None = None,
       sleep: Callable[[float], None] = time.sleep,
       universe_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Checkpointed bulk OHLC ingestion. Assumes valid credentials are
    already resolved by the caller -- this function performs no credential
    lookup, keeping it fully injectable for tests."""
    started_at = vn_time.vn_now_iso()
    symbols = sorted({s.upper() for s in symbols})
    run_scope_id = compute_run_scope_id(dataset=DATASET, symbols=symbols, date_from=date_from,
                                        date_to=date_to, resolution=RESOLUTION, instrument_type=instrument_type)
    checkpoint = lake.load_checkpoint(runtime_root, PROVIDER, DATASET, run_scope_id)

    from_ts, to_ts = date_window_epoch(date_from, date_to)

    attempted: list[str] = []
    successful: list[str] = []
    failed: list[dict[str, Any]] = []
    skipped: list[str] = []
    auth_aborted = False

    for symbol in symbols:
        if lake.unit_status(checkpoint, symbol) == "success":
            skipped.append(symbol)
            continue
        if auth_aborted:
            skipped.append(symbol)
            continue

        attempted.append(symbol)
        query = {"type": instrument_type, "symbol": symbol, "resolution": RESOLUTION,
                 "from": from_ts, "to": to_ts}
        response = _fetch_with_retry(symbol, query, api_key=api_key, api_secret=api_secret,
                                     max_retries=max_retries, backoff_seconds=backoff_seconds,
                                     request_get=request_get, sleep=sleep)

        if response.get("error_code") == "authentication_failed":
            auth_aborted = True
            failed.append({"unit_id": symbol, "error_code": "authentication_failed"})
            checkpoint = lake.record_unit_result(checkpoint, symbol, status="failed",
                                                 error_code="authentication_failed")
            lake.save_checkpoint(runtime_root, checkpoint)
            continue

        if response.get("ok"):
            retrieved_at = vn_time.vn_now_iso()
            observation = _ohlc_observation(symbol, response, retrieved_at=retrieved_at)
            write_result = lake.write_raw_observation(runtime_root, observation, run_id=run_id)
            checkpoint = lake.record_unit_result(checkpoint, symbol, status="success",
                                                 raw_file=write_result["path"],
                                                 observation_id=observation.observation_id)
            lake.save_checkpoint(runtime_root, checkpoint)
            successful.append(symbol)
        else:
            error_code = str(response.get("error_code"))
            failed.append({"unit_id": symbol, "error_code": error_code,
                           "attempts": response.get("attempts", 1)})
            checkpoint = lake.record_unit_result(checkpoint, symbol, status="failed", error_code=error_code)
            lake.save_checkpoint(runtime_root, checkpoint)

        if request_delay_seconds > 0:
            sleep(request_delay_seconds)

    ended_at = vn_time.vn_now_iso()
    output_dir = str(lake.raw_run_dir(runtime_root, PROVIDER, DATASET, run_id))
    checkpoint_file = str(lake.checkpoint_path(runtime_root, PROVIDER, DATASET, run_scope_id))

    # successful/failed reflect the *current cumulative* state of this run_scope
    # (i.e. including units completed by an earlier invocation and left untouched
    # this time), not just what this one invocation freshly did -- attempted/
    # skipped stay per-invocation, matching this milestone's "successful/failed/
    # skipped-and-resumed instruments" manifest requirement read as describing
    # where the logical run currently stands, not a diff.
    cumulative_successful = sorted(lake.completed_units(checkpoint))
    cumulative_failed = sorted(
        ({"unit_id": unit_id, "error_code": checkpoint["units"][unit_id].get("error_code")}
         for unit_id in lake.units_with_status(checkpoint, "failed")),
        key=lambda item: item["unit_id"],
    )
    manifest = lake.build_manifest(
        provider=PROVIDER, dataset=DATASET, run_id=run_id, run_scope_id=run_scope_id,
        started_at=started_at, ended_at=ended_at, requested_units=symbols, attempted_units=attempted,
        successful_units=cumulative_successful, failed_units=cumulative_failed, skipped_units=skipped,
        output_dir=output_dir, checkpoint_file=checkpoint_file,
        extra={"date_from": date_from, "date_to": date_to, "resolution": RESOLUTION,
              "instrument_type": instrument_type, "auth_aborted": auth_aborted,
              "attempted_this_run_successful": sorted(successful), "attempted_this_run_failed": failed},
    )
    lake.save_manifest(runtime_root, manifest)

    status = ("AUTHENTICATION_FAILED_MID_RUN" if auth_aborted
             else "COMPLETE" if not failed else "COMPLETE_WITH_FAILURES")

    result: dict[str, Any] = {"status": status, "manifest": manifest, "run_scope_id": run_scope_id}
    context = universe_context or {}
    if context.get("universe_symbols"):
        coverage = build_coverage_report(
            generated_at=ended_at, universe_status="EXTERNAL_SNAPSHOT",
            universe_declared_total=len(context["universe_symbols"]),
            universe_discovered_count=len(context["universe_symbols"]),
            universe_by_exchange=context.get("universe_by_exchange", {}),
            universe_by_instrument_class=context.get("universe_by_instrument_class", {}),
            universe_symbols=context["universe_symbols"], dataset_manifests=[manifest],
            security_master_discovered_count=context.get("security_master_discovered_count"),
        )
        coverage_path = save_coverage_report(
            runtime_root, provider=PROVIDER, dataset=DATASET, run_id=run_id, report=coverage,
        )
        manifest["coverage_report_path"] = str(coverage_path)
        lake.save_manifest(runtime_root, manifest)
        result["coverage_report"] = coverage
        result["coverage_report_path"] = str(coverage_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                         help="Actually call the network. Without this, only the run plan is printed.")
    parser.add_argument("--runtime-root", default=None, help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--secrets-file", default=None,
                         help="Defaults to STOCK_LOOKUP_SECRETS_FILE, else the owner-approved local path.")
    parser.add_argument("--symbols", default=None, help="Comma-separated explicit symbol list.")
    parser.add_argument("--universe-snapshot", default=None,
                         help="Path to a Parquet universe snapshot written by discover_market_universe.py.")
    parser.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD.")
    parser.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD.")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                         help="Used only when --from/--to are not both given.")
    parser.add_argument("--instrument-type", default="STOCK", choices=("STOCK", "INDEX"))
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff-seconds", type=float, default=DEFAULT_BACKOFF_SECONDS)
    parser.add_argument("--request-delay-seconds", type=float, default=DEFAULT_REQUEST_DELAY_SECONDS)
    parser.add_argument("--run-id", default=None, help="Defaults to a timestamp-derived id.")
    args = parser.parse_args(argv)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        universe_context: dict[str, Any] = {}
    elif args.universe_snapshot:
        symbols = load_symbols_from_universe_snapshot(Path(args.universe_snapshot),
                                                       instrument_type=args.instrument_type)
        universe_context = load_universe_context(Path(args.universe_snapshot), selected_symbols=symbols)
    else:
        print(json.dumps({"status": "SYMBOL_SOURCE_REQUIRED",
                          "reason": "pass --symbols or --universe-snapshot; no default ticker list exists"}))
        return 2

    date_from, date_to = args.date_from, args.date_to
    if not (date_from and date_to):
        date_from, date_to = default_date_range(args.lookback_days)

    if not args.live:
        print(json.dumps({
            "dry_run": True, "capability": "ohlc", "endpoint": "/price/ohlc",
            "requested_unit_count": len(symbols), "symbols_sample": symbols[:10],
            "date_from": date_from, "date_to": date_to, "resolution": RESOLUTION,
            "instrument_type": args.instrument_type,
        }, indent=2, sort_keys=True))
        return 0

    ensure_credentials_loaded(args.secrets_file)
    if credential_status()["configured"] is False:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2
    api_key, api_secret = credentials_for_request()

    runtime_root = resolve_runtime_root(args.runtime_root)
    run_id = args.run_id or vn_time.vn_now().strftime("run-%Y%m%dT%H%M%S")
    try:
        result = run(runtime_root=runtime_root, api_key=api_key, api_secret=api_secret, symbols=symbols,
                     date_from=date_from, date_to=date_to, instrument_type=args.instrument_type, run_id=run_id,
                     max_retries=args.max_retries, backoff_seconds=args.backoff_seconds,
                     request_delay_seconds=args.request_delay_seconds, universe_context=universe_context)
    except RunScopeLockedError as exc:
        print(json.dumps({"status": "RUN_SCOPE_LOCKED", "reason": str(exc)}))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if result["status"] == "AUTHENTICATION_FAILED_MID_RUN":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
