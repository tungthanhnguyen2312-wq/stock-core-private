"""Restartable, rate-limit-resilient raw collection for DNSE intraday history.

The collector only persists provider responses and checkpoint facts. A page
uses a write-ahead pending record, so a crash between raw write and checkpoint
cannot create a duplicate, unreferenced observation on retry.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_bulk_market_data import fetch_capability_raw, is_retryable
import dnse_intraday_history_raw as contract
import market_raw_lake as lake
from runtime_paths import runtime_root as resolve_runtime_root
import vn_time
from dnse_access import credential_status, credentials_for_request
from dnse_secrets_env import ensure_credentials_loaded

PAGINATION_READINESS = {"trades_history": "MARKET_WIDE_ACQUISITION_READY", "quotes_history": "PARTIAL"}
DEFAULT_MAX_PAGES_PER_WORK = 1000
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0
DEFAULT_REQUEST_DELAY_SECONDS = 0.2
RunScopeLockedError = lake.RunScopeLockedError


class PaginationContractNotReady(RuntimeError):
    pass


def load_applicable_symbols(snapshot_path: Path) -> list[str]:
    import pandas as pd

    frame = pd.read_parquet(snapshot_path)
    if not {"symbol", "instrument_class"}.issubset(frame.columns):
        raise ValueError("universe_snapshot_missing_symbol_or_instrument_class")
    symbols = sorted(set(frame.loc[frame["instrument_class"].eq("EQUITY"), "symbol"].astype(str).str.upper()))
    if not symbols:
        raise ValueError("universe_snapshot_has_no_evidence_classified_equity")
    return symbols


def compute_run_scope_id(*, dataset: str, symbols: Sequence[str], session_date: str, limit: int) -> str:
    value = {"provider": contract.PROVIDER, "dataset": dataset, "symbols": sorted({s.upper() for s in symbols}),
             "session_date": session_date, "limit": limit, "order": contract.ORDER}
    return hashlib.sha256(contract.canonical_json(value).encode("utf-8")).hexdigest()[:24]


class _RequestPacer:
    """Invocation-local pacing, applied at the actual HTTP attempt boundary."""

    def __init__(self, delay_seconds: float, sleep: Callable[[float], None], telemetry: dict[str, int]) -> None:
        self.delay_seconds, self.sleep, self.telemetry, self.has_requested = delay_seconds, sleep, telemetry, False

    def before_request(self) -> None:
        if self.has_requested and self.delay_seconds:
            self.sleep(self.delay_seconds)
        self.has_requested = True
        self.telemetry["http_request_attempts"] += 1


def _fetch_with_retry(*, dataset: str, api_key: str, api_secret: str, symbol: str,
                      query: Mapping[str, Any], request_get: Callable[..., Any] | None,
                      max_retries: int, backoff_seconds: float, max_backoff_seconds: float,
                      pacer: _RequestPacer, sleep: Callable[[float], None], telemetry: dict[str, int]) -> dict[str, Any]:
    """Retry sanitized transient failures only; headers and credentials never persist."""
    for attempt in range(max_retries + 1):
        pacer.before_request()
        response = fetch_capability_raw(dataset, api_key=api_key, api_secret=api_secret,
                                        symbol=symbol, query=dict(query), request_get=request_get)
        response["attempts"] = attempt + 1
        if response.get("ok"):
            return response
        error = str(response.get("error_code") or "unknown_request_failure")
        if error == "rate_limited":
            telemetry["rate_limited_responses"] += 1
        if error.startswith("request_failed_"):
            telemetry["transport_failures"] += 1
        if not is_retryable(response):
            return response
        if attempt == max_retries:
            telemetry["retry_exhaustion"] += 1
            return response
        telemetry["retry_attempts"] += 1
        delay = min(max_backoff_seconds, backoff_seconds * (2 ** attempt))
        retry_after = response.get("retry_after_seconds")
        if isinstance(retry_after, (int, float)) and retry_after >= 0:
            delay = min(max_backoff_seconds, max(delay, float(retry_after)))
            telemetry["retry_after_honored"] += 1
        if delay:
            sleep(delay)
    raise AssertionError("retry loop must return")


def _pagination_state(checkpoint: Mapping[str, Any], root: str) -> dict[str, Any]:
    state = copy.deepcopy((checkpoint.get("intraday_pagination", {}) or {}).get(root, {}))
    state.setdefault("page_count", 0)
    state.setdefault("raw_record_count", 0)
    state.setdefault("seen_tokens", [contract.CURSOR_INITIAL])
    state.setdefault("seen_pages", [])
    state.setdefault("next_cursor", None)
    return state


def _effective_raw_run_id(checkpoint: Mapping[str, Any], state: Mapping[str, Any], root: str,
                          fallback_run_id: str) -> str:
    existing = state.get("raw_run_id")
    if isinstance(existing, str) and existing:
        return existing
    for pending in (checkpoint.get("pending_raw_pages", {}) or {}).values():
        if isinstance(pending, Mapping) and pending.get("root_unit_id") == root and pending.get("raw_run_id"):
            return str(pending["raw_run_id"])
    for unit_id, unit in (checkpoint.get("units", {}) or {}).items():
        if str(unit_id).startswith(f"{root}__page_") and isinstance(unit, Mapping) and unit.get("raw_file"):
            return Path(str(unit["raw_file"])).parent.name
    return fallback_run_id


def _with_pending(checkpoint: Mapping[str, Any], page_unit: str, pending: Mapping[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(dict(checkpoint))
    updated.setdefault("pending_raw_pages", {})[page_unit] = dict(pending)
    return updated


def _without_pending(checkpoint: Mapping[str, Any], page_unit: str) -> dict[str, Any]:
    updated = copy.deepcopy(dict(checkpoint))
    updated.setdefault("pending_raw_pages", {}).pop(page_unit, None)
    return updated


def _make_pending(*, root: str, page_unit: str, raw_run_id: str, page_index: int, cursor: str | None,
                  next_cursor: str | None, page_id: str, raw: Any, raw_file: Path, record_count: int) -> dict[str, Any]:
    return {"root_unit_id": root, "page_unit_id": page_unit, "raw_run_id": raw_run_id,
            "page_index": page_index, "cursor": cursor, "next_cursor": next_cursor,
            "page_identity": page_id, "raw_file": str(raw_file), "observation_id": raw.observation_id,
            "raw_payload_hash": raw.raw_payload_hash, "record_count": record_count,
            "prepared_at": vn_time.vn_now_iso()}


def _complete_page(checkpoint: Mapping[str, Any], *, root: str, pending: Mapping[str, Any],
                   state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    page_unit = str(pending["page_unit_id"])
    updated = lake.record_unit_result(checkpoint, page_unit, status="success", raw_file=str(pending["raw_file"]),
                                      observation_id=str(pending["observation_id"]))
    next_state = copy.deepcopy(dict(state))
    if int(pending["page_index"]) != int(next_state["page_count"]):
        raise ValueError("pending_raw_page_index_does_not_match_checkpoint")
    next_state["raw_run_id"] = str(pending["raw_run_id"])
    next_state["page_count"] = int(next_state["page_count"]) + 1
    next_state["raw_record_count"] = int(next_state["raw_record_count"]) + int(pending["record_count"])
    next_state["seen_pages"].append(str(pending["page_identity"]))
    next_state["next_cursor"] = pending.get("next_cursor")
    if pending.get("next_cursor"):
        next_state["seen_tokens"].append(str(pending["next_cursor"]))
    updated.setdefault("intraday_pagination", {})[root] = next_state
    if pending.get("next_cursor") is None:
        updated = lake.record_unit_result(updated, root, status="success", raw_file=str(pending["raw_file"]),
                                          observation_id=str(pending["observation_id"]))
    return _without_pending(updated, page_unit), next_state


def _pending_validation_error(*, runtime_root: Path, dataset: str, symbol: str, session_date: str,
                              scope: str, pending: Mapping[str, Any]) -> str | None:
    """Validate only the exact pending path; no raw-directory scan or arbitrary adoption."""
    try:
        import pandas as pd

        required = {"page_unit_id", "raw_run_id", "observation_id", "raw_file", "raw_payload_hash", "page_index",
                    "cursor", "next_cursor", "page_identity", "record_count"}
        if not required.issubset(pending):
            return "pending_raw_page_schema_invalid"
        expected = lake.raw_file_path(runtime_root, contract.PROVIDER, dataset, str(pending["raw_run_id"]), symbol,
                                      str(pending["observation_id"]))
        path = Path(str(pending["raw_file"]))
        if path != expected or not path.is_file():
            return "pending_raw_page_path_missing_or_mismatched"
        frame = pd.read_parquet(path)
        if len(frame) != 1:
            return "pending_raw_page_row_count_invalid"
        row = frame.iloc[0]
        checks = {"provider": contract.PROVIDER, "dataset": dataset, "instrument": symbol.upper(),
                  "observation_id": str(pending["observation_id"]), "raw_payload_hash": str(pending["raw_payload_hash"])}
        if any(str(row.get(key)) != value for key, value in checks.items()):
            return "pending_raw_page_identity_invalid"
        body = json.loads(str(row["raw_payload_json"]))
        if hashlib.sha256(contract.canonical_json(body).encode("utf-8")).hexdigest() != pending["raw_payload_hash"]:
            return "pending_raw_page_payload_hash_invalid"
        provenance = json.loads(str(row["provenance_json"]))
        if provenance.get("ingestion_run_id") != pending["raw_run_id"] or provenance.get("checkpoint_identity") != scope:
            return "pending_raw_page_provenance_invalid"
        if provenance.get("checkpoint_unit_id") != pending["page_unit_id"]:
            return "pending_raw_page_unit_invalid"
        if provenance.get("page_index") != pending["page_index"] or provenance.get("page_cursor") != pending["cursor"]:
            return "pending_raw_page_cursor_invalid"
        records = contract.extract_records(dataset, body)
        if len(records) != int(pending["record_count"]):
            return "pending_raw_page_record_count_invalid"
        query = provenance.get("request_parameters")
        if not isinstance(query, Mapping):
            return "pending_raw_page_query_invalid"
        page_id = contract.page_identity(dataset=dataset, symbol=symbol, session_date=session_date,
                                         query=query, cursor=pending["cursor"], body=body)
        if page_id != pending["page_identity"]:
            return "pending_raw_page_page_identity_invalid"
        if contract.continuation_token(body, seen_tokens=set(), seen_pages=set(), page_id=page_id) != pending["next_cursor"]:
            return "pending_raw_page_next_cursor_invalid"
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return "pending_raw_page_validation_exception"
    return None


def _recover_pending(*, runtime_root: Path, checkpoint: Mapping[str, Any], root: str, dataset: str,
                     symbol: str, session_date: str, scope: str, state: Mapping[str, Any],
                     telemetry: dict[str, int]) -> tuple[dict[str, Any], dict[str, Any], str]:
    candidates = [(key, value) for key, value in (checkpoint.get("pending_raw_pages", {}) or {}).items()
                  if isinstance(value, Mapping) and value.get("root_unit_id") == root]
    if not candidates:
        return dict(checkpoint), dict(state), "none"
    if len(candidates) == 1:
        key, pending = candidates[0]
        if key == pending.get("page_unit_id"):
            path = Path(str(pending.get("raw_file", "")))
            if not path.is_file():
                telemetry["pending_raw_pages_missing"] += 1
                return _without_pending(checkpoint, key), dict(state), "missing"
            error = _pending_validation_error(runtime_root=runtime_root, dataset=dataset, symbol=symbol,
                session_date=session_date, scope=scope, pending=pending)
            if error is None:
                updated, state = _complete_page(checkpoint, root=root, pending=pending, state=state)
                telemetry["orphan_raw_pages_adopted"] += 1
                return updated, state, "adopted"
        else:
            error = "pending_raw_page_key_invalid"
    else:
        key, pending, error = candidates[0][0], candidates[0][1], "pending_raw_page_state_ambiguous"
    page_unit = str(pending.get("page_unit_id") or key)
    updated = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code="orphan_raw_page_unreferenced")
    updated = lake.record_unit_result(updated, root, status="failed", error_code="orphan_raw_page_unreferenced")
    updated = _without_pending(updated, page_unit)
    updated.setdefault("orphan_raw_pages", []).append({"root_unit_id": root, "page_unit_id": page_unit,
        "raw_file": pending.get("raw_file"), "reason": error, "status": "ORPHAN_RAW_PAGE_UNREFERENCED"})
    telemetry["orphan_raw_pages_unreferenced"] += 1
    return updated, dict(state), "blocked"


def _validate_config(*, max_pages_per_work: int, max_retries: int, backoff_seconds: float,
                     max_backoff_seconds: float, request_delay_seconds: float,
                     max_units_per_invocation: int | None) -> None:
    if max_pages_per_work <= 0:
        raise ValueError("max_pages_per_work_must_be_positive")
    if max_retries < 0:
        raise ValueError("max_retries_must_be_nonnegative")
    if backoff_seconds < 0 or max_backoff_seconds < 0 or request_delay_seconds < 0:
        raise ValueError("retry_and_pacing_seconds_must_be_nonnegative")
    if max_units_per_invocation is not None and max_units_per_invocation <= 0:
        raise ValueError("max_units_per_invocation_must_be_positive")


def run(*, runtime_root: Path, dataset: str, symbols: Sequence[str], session_date: str, run_id: str,
        api_key: str, api_secret: str, pagination_contract_proven: bool = False,
        limit: int = contract.DEFAULT_LIMIT, max_pages_per_work: int = DEFAULT_MAX_PAGES_PER_WORK,
        max_retries: int = DEFAULT_MAX_RETRIES, backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS, retry_failed: bool = True,
        max_units_per_invocation: int | None = None, request_get: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    if dataset not in contract.SPECS:
        raise ValueError("unsupported_intraday_history_dataset")
    if not pagination_contract_proven:
        raise PaginationContractNotReady(f"{dataset} pagination continuation is not first-party proven")
    _validate_config(max_pages_per_work=max_pages_per_work, max_retries=max_retries,
        backoff_seconds=backoff_seconds, max_backoff_seconds=max_backoff_seconds,
        request_delay_seconds=request_delay_seconds, max_units_per_invocation=max_units_per_invocation)
    symbols = sorted({symbol.upper() for symbol in symbols})
    scope = compute_run_scope_id(dataset=dataset, symbols=symbols, session_date=session_date, limit=limit)
    started_at = vn_time.vn_now_iso()
    telemetry = {key: 0 for key in ("http_request_attempts", "retry_attempts", "rate_limited_responses",
        "transport_failures", "retry_exhaustion", "retry_after_honored", "retryable_failed_retried",
        "reused_successes", "resumed_partial_page_units", "orphan_raw_pages_adopted",
        "orphan_raw_pages_unreferenced", "pending_raw_pages_missing")}
    attempted: list[str] = []
    skipped: list[str] = []
    authentication_failed = False
    with lake.exclusive_run_scope_lock(runtime_root, contract.PROVIDER, dataset, scope):
        checkpoint = lake.load_checkpoint(runtime_root, contract.PROVIDER, dataset, scope)
        pacer = _RequestPacer(request_delay_seconds, sleep, telemetry)
        for symbol in symbols:
            root = contract.work_unit_id(dataset, symbol, session_date)
            state = _pagination_state(checkpoint, root)
            checkpoint, state, recovery = _recover_pending(runtime_root=runtime_root, checkpoint=checkpoint, root=root,
                dataset=dataset, symbol=symbol, session_date=session_date, scope=scope, state=state, telemetry=telemetry)
            if recovery != "none":
                lake.save_checkpoint(runtime_root, checkpoint)
            if recovery == "blocked":
                skipped.append(root)
                continue
            status = lake.unit_status(checkpoint, root)
            if status == "success":
                telemetry["reused_successes"] += 1
                skipped.append(root)
                continue
            failure = (checkpoint.get("units", {}).get(root, {}) or {}).get("error_code")
            if status == "failed":
                if not (retry_failed and is_retryable({"error_code": failure})):
                    skipped.append(root)
                    continue
                telemetry["retryable_failed_retried"] += 1
            if max_units_per_invocation is not None and len(attempted) >= max_units_per_invocation:
                break
            attempted.append(root)
            if int(state["page_count"]) > 0:
                telemetry["resumed_partial_page_units"] += 1
            raw_run_id = _effective_raw_run_id(checkpoint, state, root, run_id)
            cursor = state.get("next_cursor")
            while True:
                page_unit = contract.page_unit_id(root, cursor)
                if int(state["page_count"]) >= max_pages_per_work:
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code="max_pages_per_work_exceeded")
                    checkpoint = lake.record_unit_result(checkpoint, root, status="failed", error_code="max_pages_per_work_exceeded")
                    lake.save_checkpoint(runtime_root, checkpoint)
                    break
                query = contract.request_query(dataset, session_date, limit=limit, cursor=cursor)
                response = _fetch_with_retry(dataset=dataset, api_key=api_key, api_secret=api_secret, symbol=symbol,
                    query=query, request_get=request_get, max_retries=max_retries, backoff_seconds=backoff_seconds,
                    max_backoff_seconds=max_backoff_seconds, pacer=pacer, sleep=sleep, telemetry=telemetry)
                if not response.get("ok"):
                    error = str(response.get("error_code"))
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=error)
                    checkpoint = lake.record_unit_result(checkpoint, root, status="failed", error_code=error)
                    lake.save_checkpoint(runtime_root, checkpoint)
                    authentication_failed = error == "authentication_failed"
                    break
                body = response.get("body") or {}
                try:
                    records = contract.extract_records(dataset, body)
                    page_id = contract.page_identity(dataset=dataset, symbol=symbol, session_date=session_date,
                        query=query, cursor=cursor, body=body)
                    next_cursor = contract.continuation_token(body, seen_tokens=set(state["seen_tokens"]),
                        seen_pages=set(state["seen_pages"]), page_id=page_id)
                except ValueError as exc:
                    checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=str(exc))
                    checkpoint = lake.record_unit_result(checkpoint, root, status="failed", error_code=str(exc))
                    lake.save_checkpoint(runtime_root, checkpoint)
                    break
                raw = contract.observation(dataset=dataset, symbol=symbol, session_date=session_date, response=response,
                    cursor=cursor, page_index=int(state["page_count"]), run_id=raw_run_id, run_scope_id=scope,
                    page_unit=page_unit, records=records)
                raw_file = lake.raw_file_path(runtime_root, contract.PROVIDER, dataset, raw_run_id,
                    raw.instrument, raw.observation_id)
                pending = _make_pending(root=root, page_unit=page_unit, raw_run_id=raw_run_id,
                    page_index=int(state["page_count"]), cursor=cursor, next_cursor=next_cursor, page_id=page_id,
                    raw=raw, raw_file=raw_file, record_count=len(records))
                checkpoint = _with_pending(checkpoint, page_unit, pending)
                lake.save_checkpoint(runtime_root, checkpoint)
                write = lake.write_raw_observation(runtime_root, raw, run_id=raw_run_id)
                if Path(str(write["path"])) != raw_file:
                    raise ValueError("raw_write_path_does_not_match_pending_page")
                checkpoint, state = _complete_page(checkpoint, root=root, pending=pending, state=state)
                lake.save_checkpoint(runtime_root, checkpoint)
                if next_cursor is None:
                    break
                cursor = next_cursor
            if authentication_failed:
                break
        roots = [contract.work_unit_id(dataset, symbol, session_date) for symbol in symbols]
        successes = [root for root in roots if lake.unit_status(checkpoint, root) == "success"]
        failures = [{"unit_id": root, "error_code": checkpoint["units"][root].get("error_code")}
                    for root in roots if lake.unit_status(checkpoint, root) == "failed"]
        remaining = [root for root in roots if lake.unit_status(checkpoint, root) is None]
        status = "IN_PROGRESS" if remaining and not authentication_failed else ("COMPLETE" if not failures else "COMPLETE_WITH_FAILURES")
        manifest = lake.build_manifest(provider=contract.PROVIDER, dataset=dataset, run_id=run_id, run_scope_id=scope,
            started_at=started_at, ended_at=vn_time.vn_now_iso(), requested_units=roots, attempted_units=attempted,
            successful_units=successes, failed_units=failures, skipped_units=skipped,
            output_dir=str(lake.raw_run_dir(runtime_root, contract.PROVIDER, dataset, run_id)),
            checkpoint_file=str(lake.checkpoint_path(runtime_root, contract.PROVIDER, dataset, scope)),
            extra={"status": status, "session_date": session_date, "pagination_contract_proven": True,
                "planned_units": len(roots), "attempted_units_this_invocation": len(attempted),
                "cumulative_successes": len(successes), "cumulative_failed_units": len(failures),
                "request_roots": len(roots), "raw_page_files": sum(int(v.get("page_count", 0)) for v in checkpoint.get("intraday_pagination", {}).values()),
                "raw_records": sum(int(v.get("raw_record_count", 0)) for v in checkpoint.get("intraday_pagination", {}).values()),
                "successful_nonempty_units": sum(1 for root in successes if int(_pagination_state(checkpoint, root)["raw_record_count"]) > 0),
                "confirmed_empty_units": sum(1 for root in successes if int(_pagination_state(checkpoint, root)["raw_record_count"]) == 0),
                "cumulative_confirmed_empty_units": sum(1 for root in successes if int(_pagination_state(checkpoint, root)["raw_record_count"]) == 0),
                "retry_configuration": {"max_retries": max_retries, "backoff_seconds": backoff_seconds,
                    "max_backoff_seconds": max_backoff_seconds, "request_delay_seconds": request_delay_seconds},
                "retry_failed": retry_failed, "max_units_per_invocation": max_units_per_invocation,
                "raw_semantics": "PRESERVED_UNQUALIFIED", **telemetry})
        lake.save_manifest(runtime_root, manifest)
    return {"manifest": manifest, "checkpoint": checkpoint}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(contract.SPECS), required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--universe-snapshot", required=True)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--secrets-file", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=contract.DEFAULT_LIMIT)
    parser.add_argument("--max-pages-per-work", type=int, default=DEFAULT_MAX_PAGES_PER_WORK)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff-seconds", type=float, default=DEFAULT_BACKOFF_SECONDS)
    parser.add_argument("--max-backoff-seconds", type=float, default=DEFAULT_MAX_BACKOFF_SECONDS)
    parser.add_argument("--request-delay-seconds", type=float, default=DEFAULT_REQUEST_DELAY_SECONDS)
    parser.add_argument("--retry-failed", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--max-units-per-invocation", type=int, default=None)
    args = parser.parse_args(argv)
    symbols = load_applicable_symbols(Path(args.universe_snapshot))
    payload = {"dataset": args.dataset, "session_date": args.session_date, "applicable_symbols": len(symbols),
               "pagination_readiness": PAGINATION_READINESS[args.dataset]}
    if args.live:
        if PAGINATION_READINESS[args.dataset] != "MARKET_WIDE_ACQUISITION_READY":
            print(json.dumps({**payload, "status": "REFUSE_BULK_LIVE_RUN_UNTIL_PAGINATION_PROVEN"}, sort_keys=True))
            return 2
        ensure_credentials_loaded(args.secrets_file)
        if not credential_status()["configured"]:
            print(json.dumps({**payload, "status": "DNSE_CREDENTIAL_INJECTION_REQUIRED"}, sort_keys=True))
            return 2
        key, secret = credentials_for_request()
        result = run(runtime_root=resolve_runtime_root(args.runtime_root), dataset=args.dataset, symbols=symbols,
            session_date=args.session_date, run_id=args.run_id or vn_time.vn_now().strftime("run-%Y%m%dT%H%M%S"),
            api_key=key, api_secret=secret, pagination_contract_proven=True, limit=args.limit,
            max_pages_per_work=args.max_pages_per_work, max_retries=args.max_retries,
            backoff_seconds=args.backoff_seconds, max_backoff_seconds=args.max_backoff_seconds,
            request_delay_seconds=args.request_delay_seconds, retry_failed=args.retry_failed,
            max_units_per_invocation=args.max_units_per_invocation)
        print(json.dumps({**payload, "status": "BULK_RUN_FINISHED", "manifest": result["manifest"]}, sort_keys=True, default=str))
        return 0
    print(json.dumps({**payload, "status": "DRY_VALIDATION_ONLY"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
