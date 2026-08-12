"""Market-wide, restartable, raw-only DNSE foreign-trading ingestion.

The supported V1 provider window is exactly one Vietnam-local session.  Each
dynamic ST/EQUITY symbol is a planned root work unit; every returned cursor
page is separately retained and checkpointed before its continuation is
followed.  No raw field is normalized, aggregated, or granted authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from dnse_access import credential_status, credentials_for_request  # noqa: E402
from dnse_bulk_market_data import fetch_capability_raw, is_retryable  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
import dnse_foreign_trading_raw as contract  # noqa: E402
import market_raw_lake as lake  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402
import vn_time  # noqa: E402

PROVIDER = contract.PROVIDER
DATASET = contract.DATASET
CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_REQUEST_DELAY_SECONDS = 0.15


class RunScopeLockedError(RuntimeError):
    pass


def _lock_path(runtime_root: Path, scope: str) -> Path:
    return lake.checkpoint_path(runtime_root, PROVIDER, DATASET, scope).with_suffix(".lock")


@contextmanager
def _exclusive_lock(runtime_root: Path, scope: str):
    path = _lock_path(runtime_root, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise RunScopeLockedError(f"run scope is already active: {scope}") from exc
    try:
        os.write(fd, f"run_scope_id={scope}\npid={os.getpid()}\n".encode("utf-8"))
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def _fetch(query: Mapping[str, Any], *, symbol: str, api_key: str, api_secret: str,
           max_retries: int, backoff_seconds: float, request_get: Callable[..., Any] | None,
           sleep: Callable[[float], None]) -> dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        response = fetch_capability_raw(contract.CAPABILITY, api_key=api_key, api_secret=api_secret,
                                        symbol=symbol, query=query, request_get=request_get)
        response["attempts"] = attempt
        if response.get("ok") or response.get("error_code") == "authentication_failed":
            return response
        if not is_retryable(response) or attempt > max_retries:
            return response
        sleep(backoff_seconds * (2 ** (attempt - 1)))


def _root_state(checkpoint: Mapping[str, Any], root: str) -> str | None:
    return lake.unit_status(checkpoint, root)


def _mark_root(checkpoint: Mapping[str, Any], root: str, *, status: str,
               error_code: str | None = None, raw_file: str | None = None,
               observation_id: str | None = None) -> dict[str, Any]:
    return lake.record_unit_result(checkpoint, root, status=status, error_code=error_code,
                                   raw_file=raw_file, observation_id=observation_id)


def _coverage(*, symbols: Sequence[str], session_date: str, checkpoint: Mapping[str, Any],
              universe_context: Mapping[str, Any]) -> dict[str, Any]:
    states = checkpoint.get("foreign_pagination", {})
    roots = [contract.work_unit_id(symbol, session_date) for symbol in symbols]
    successful = [root for root in roots if _root_state(checkpoint, root) == "success"]
    failed = [root for root in roots if _root_state(checkpoint, root) == "failed"]
    untouched = [root for root in roots if _root_state(checkpoint, root) is None]
    success_symbols = [root.split("__", 1)[0] for root in successful]
    empty = [root.split("__", 1)[0] for root in successful
             if int((states.get(root) or {}).get("raw_record_count", 0)) == 0]
    page_states = [value for value in states.values() if isinstance(value, Mapping)]
    board_counter: Counter[str] = Counter()
    for state in page_states:
        board_counter.update(str(item) for item in state.get("board_ids", []) if item is not None)
    symbol_exchange = universe_context.get("symbol_exchange", {})
    error_counter = Counter(str(checkpoint["units"][root].get("error_code")) for root in failed)
    return {
        "schema_version": "1.0.0", "provider": PROVIDER, "dataset": DATASET,
        "session_date": session_date, "security_master_instruments": universe_context.get("security_master_count"),
        "dataset_applicable_instruments": len(symbols), "planned_work_units": len(roots),
        "attempted_work_units": len(successful) + len(failed), "successful_work_units": len(successful),
        "failed_work_units": len(failed), "untouched_work_units": len(untouched),
        "request_success_ratio": round(len(successful) / len(roots), 4) if roots else None,
        "retained_raw_files": sum(int(state.get("page_count", 0)) for state in page_states),
        "retained_raw_records": sum(int(state.get("raw_record_count", 0)) for state in page_states),
        "empty_successful_responses": len(empty), "empty_successful_symbols": sorted(empty),
        "earliest_source_session": session_date if successful else None,
        "latest_source_session": session_date if successful else None,
        "coverage_by_exchange_raw": dict(sorted(Counter(symbol_exchange.get(symbol, "UNKNOWN")
                                                           for symbol in success_symbols).items())),
        "coverage_by_board_raw": dict(sorted(board_counter.items())),
        "provider_error_distribution": dict(sorted(error_counter.items())),
        "raw_semantics": "PRESERVED_UNQUALIFIED", "foreign_flow_authority_changed": False,
    }


def _save_coverage(runtime_root: Path, *, run_id: str, report: Mapping[str, Any]) -> Path:
    canonical = contract.canonical_json(report)
    digest = __import__("hashlib").sha256(canonical.encode("utf-8")).hexdigest()[:16]
    path = runtime_root / "data" / "market_raw_lake" / "coverage" / f"DNSE__foreign_trading__{run_id}__{digest}.json"
    atomic_write_json(path, dict(report))
    return path


def _universe_context(snapshot_path: Path, symbols: Sequence[str]) -> dict[str, Any]:
    import pandas as pd

    frame = pd.read_parquet(snapshot_path)
    exchange = {str(row.symbol).upper(): str(row.exchange_raw) for row in frame.itertuples(index=False)}
    return {"security_master_count": int(len(frame)), "symbol_exchange": exchange,
            "applicable_instrument_class": contract.APPLICABLE_INSTRUMENT_CLASS,
            "unknown_class_count": int((frame["instrument_class"] == "UNKNOWN_SECURITY_GROUP").sum()),
            "selected_symbols": len(symbols)}


def run(*, runtime_root: Path, api_key: str, api_secret: str, symbols: Sequence[str], session_date: str,
        run_id: str, universe_context: Mapping[str, Any], limit: int = contract.DEFAULT_LIMIT,
        max_new_work_units: int | None = None, max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        request_get: Callable[..., Any] | None = None, sleep: Callable[[float], None] = time.sleep,
        retry_failed: bool = False) -> dict[str, Any]:
    symbols = sorted({symbol.upper() for symbol in symbols})
    scope = contract.compute_run_scope_id(symbols=symbols, session_date=session_date, limit=limit)
    with _exclusive_lock(runtime_root, scope):
        checkpoint = lake.load_checkpoint(runtime_root, PROVIDER, DATASET, scope)
        started = vn_time.vn_now_iso()
        attempted: list[str] = []
        skipped: list[str] = []
        auth_aborted = False
        new_started = 0
        for symbol in symbols:
            root = contract.work_unit_id(symbol, session_date)
            root_status = _root_state(checkpoint, root)
            if root_status == "success" or (root_status == "failed" and not retry_failed):
                skipped.append(root)
                continue
            state = contract.pagination_state(checkpoint, root)
            if not state:
                if max_new_work_units is not None and new_started >= max_new_work_units:
                    break
                new_started += 1
                attempted.append(root)
                state = {"page_count": 0, "raw_record_count": 0, "board_ids": [],
                         "seen_cursors": [contract.CURSOR_INITIAL], "page_fingerprints": []}
            if auth_aborted:
                break
            cursor = state.get("next_cursor")
            page_index = int(state.get("page_count", 0))
            while True:
                page_unit = contract.page_unit_id(root, cursor)
                if lake.unit_status(checkpoint, page_unit) == "success":
                    page_meta = contract.pagination_state(checkpoint, root)
                    cursor = page_meta.get("next_cursor")
                    if cursor is None:
                        checkpoint = _mark_root(checkpoint, root, status="success")
                        lake.save_checkpoint(runtime_root, checkpoint)
                        break
                    page_index = int(page_meta.get("page_count", page_index))
                    state = page_meta
                    continue
                if page_index >= contract.DEFAULT_MAX_PAGES_PER_WORK:
                    error = "max_pages_per_work_exceeded"
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=error)
                    checkpoint = _mark_root(checkpoint, root, status="failed", error_code=error)
                    lake.save_checkpoint(runtime_root, checkpoint)
                    break
                query = contract.request_query(symbol, session_date, limit=limit, cursor=cursor)
                response = _fetch(query, symbol=symbol, api_key=api_key, api_secret=api_secret,
                                  max_retries=max_retries, backoff_seconds=backoff_seconds,
                                  request_get=request_get, sleep=sleep)
                if not response.get("ok"):
                    error = str(response.get("error_code"))
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=error)
                    checkpoint = _mark_root(checkpoint, root, status="failed", error_code=error)
                    lake.save_checkpoint(runtime_root, checkpoint)
                    if error == "authentication_failed":
                        auth_aborted = True
                    break
                body = response.get("body") or {}
                try:
                    records = contract.extract_records(body)
                except ValueError as exc:
                    error = str(exc)
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=error)
                    checkpoint = _mark_root(checkpoint, root, status="failed", error_code=error)
                    lake.save_checkpoint(runtime_root, checkpoint)
                    break
                fingerprint = contract.page_fingerprint(body)
                next_cursor = body.get("nextPageToken")
                if not isinstance(next_cursor, str) or not next_cursor:
                    next_cursor = None
                seen_cursors = set(state.get("seen_cursors", []))
                if fingerprint in set(state.get("page_fingerprints", [])):
                    error = "repeated_page_payload"
                elif next_cursor is not None and next_cursor in seen_cursors:
                    error = "repeated_cursor"
                else:
                    error = None
                if error:
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=error)
                    checkpoint = _mark_root(checkpoint, root, status="failed", error_code=error)
                    lake.save_checkpoint(runtime_root, checkpoint)
                    break
                raw = contract.observation(symbol=symbol, session_date=session_date, response=response, cursor=cursor,
                                           page_index=page_index, run_id=run_id, run_scope_id=scope,
                                           page_unit=page_unit, records=records)
                write = lake.write_raw_observation(runtime_root, raw, run_id=run_id)
                checkpoint = lake.record_unit_result(checkpoint, page_unit, status="success",
                                                     raw_file=write["path"], observation_id=raw.observation_id)
                state = copy.deepcopy(state)
                state["page_count"] = page_index + 1
                state["raw_record_count"] = int(state.get("raw_record_count", 0)) + len(records)
                state["board_ids"] = sorted(set(state.get("board_ids", [])) | set(contract.board_ids(records)))
                state["page_fingerprints"] = list(state.get("page_fingerprints", [])) + [fingerprint]
                state["seen_cursors"] = list(state.get("seen_cursors", [])) + ([next_cursor] if next_cursor else [])
                state["next_cursor"] = next_cursor
                checkpoint = contract.with_pagination_state(checkpoint, root, state)
                if next_cursor is None:
                    checkpoint = _mark_root(checkpoint, root, status="success", raw_file=write["path"],
                                            observation_id=raw.observation_id)
                lake.save_checkpoint(runtime_root, checkpoint)
                if next_cursor is None:
                    break
                cursor, page_index = next_cursor, page_index + 1
                if request_delay_seconds > 0:
                    sleep(request_delay_seconds)
            if request_delay_seconds > 0:
                sleep(request_delay_seconds)
            if auth_aborted:
                break
        roots = [contract.work_unit_id(symbol, session_date) for symbol in symbols]
        successes = sorted(root for root in roots if _root_state(checkpoint, root) == "success")
        failures = [{"unit_id": root, "error_code": checkpoint["units"][root].get("error_code")}
                    for root in roots if _root_state(checkpoint, root) == "failed"]
        report = _coverage(symbols=symbols, session_date=session_date, checkpoint=checkpoint,
                           universe_context=universe_context)
        manifest = lake.build_manifest(
            provider=PROVIDER, dataset=DATASET, run_id=run_id, run_scope_id=scope,
            started_at=started, ended_at=vn_time.vn_now_iso(), requested_units=roots,
            attempted_units=attempted, successful_units=successes, failed_units=failures,
            skipped_units=skipped, output_dir=str(lake.raw_run_dir(runtime_root, PROVIDER, DATASET, run_id)),
            checkpoint_file=str(lake.checkpoint_path(runtime_root, PROVIDER, DATASET, scope)),
            extra={"session_date": session_date, "order": contract.ORDER, "limit": limit,
                   "board_scope": "UNSPECIFIED_PROVIDER_RESPONSE_BOARD_IDS_RETAINED",
                   "pagination": "nextPageToken; stop only when absent/empty; loops fail closed",
                   "raw_semantics": "PRESERVED_UNQUALIFIED", "foreign_flow_authority_changed": False,
                   "coverage": report, "auth_aborted": auth_aborted},
        )
        coverage_path = _save_coverage(runtime_root, run_id=run_id, report=report)
        manifest["coverage_report_path"] = str(coverage_path)
        lake.save_manifest(runtime_root, manifest)
        status = ("AUTHENTICATION_FAILED_MID_RUN" if auth_aborted else
                  "COMPLETE" if report["untouched_work_units"] == 0 and not failures else
                  "COMPLETE_WITH_FAILURES" if report["untouched_work_units"] == 0 else "IN_PROGRESS")
        return {"status": status, "run_scope_id": scope, "manifest": manifest,
                "coverage_report": report, "coverage_report_path": str(coverage_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--secrets-file", default=None)
    parser.add_argument("--universe-snapshot", required=True)
    parser.add_argument("--session-date", required=True, help="One YYYY-MM-DD Vietnam-local session.")
    parser.add_argument("--limit", type=int, default=contract.DEFAULT_LIMIT)
    parser.add_argument("--max-new-work-units", type=int, default=None)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff-seconds", type=float, default=DEFAULT_BACKOFF_SECONDS)
    parser.add_argument("--request-delay-seconds", type=float, default=DEFAULT_REQUEST_DELAY_SECONDS)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    snapshot = Path(args.universe_snapshot)
    symbols = contract.load_applicable_symbols(snapshot)
    if not args.live:
        print(json.dumps({"dry_run": True, "capability": contract.CAPABILITY, "endpoint": "/price/{symbol}/foreign-trading",
                          "session_date": args.session_date, "applicable_symbols": len(symbols),
                          "pagination": "nextPageToken", "order": contract.ORDER,
                          "board_scope": "UNSPECIFIED_PROVIDER_RESPONSE_BOARD_IDS_RETAINED"}, sort_keys=True))
        return 0
    ensure_credentials_loaded(args.secrets_file)
    if not credential_status()["configured"]:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2
    key, secret = credentials_for_request()
    result = run(runtime_root=resolve_runtime_root(args.runtime_root), api_key=key, api_secret=secret,
                 symbols=symbols, session_date=args.session_date,
                 run_id=args.run_id or vn_time.vn_now().strftime("run-%Y%m%dT%H%M%S"),
                 universe_context=_universe_context(snapshot, symbols), limit=args.limit,
                 max_new_work_units=args.max_new_work_units, max_retries=args.max_retries,
                 backoff_seconds=args.backoff_seconds, request_delay_seconds=args.request_delay_seconds,
                 retry_failed=args.retry_failed)
    print(json.dumps({"status": result["status"], "run_scope_id": result["run_scope_id"],
                      "coverage_report_path": result["coverage_report_path"],
                      "coverage": result["coverage_report"]}, sort_keys=True, default=str))
    return 0 if result["status"] != "AUTHENTICATION_FAILED_MID_RUN" else 3


if __name__ == "__main__":
    raise SystemExit(main())
