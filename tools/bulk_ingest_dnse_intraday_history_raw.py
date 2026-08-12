"""Readiness-gated, restartable raw collection for DNSE intraday histories.

The collector opens only for a dataset whose retained first-party pagination
probe proves cursor continuation and termination.  It uses the same immutable
page/checkpoint model as foreign trading without assigning analytical meaning
to raw records; all other datasets remain refused by the dataset-specific
readiness gate.
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

from dnse_bulk_market_data import fetch_capability_raw
import dnse_intraday_history_raw as contract
import market_raw_lake as lake
from runtime_paths import runtime_root as resolve_runtime_root
import vn_time
from dnse_access import credential_status, credentials_for_request
from dnse_secrets_env import ensure_credentials_loaded

PAGINATION_READINESS = {"trades_history": "MARKET_WIDE_ACQUISITION_READY", "quotes_history": "PARTIAL"}
DEFAULT_MAX_PAGES_PER_WORK = 1000


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


def run(*, runtime_root: Path, dataset: str, symbols: Sequence[str], session_date: str,
        run_id: str, api_key: str, api_secret: str, pagination_contract_proven: bool = False,
        limit: int = contract.DEFAULT_LIMIT, max_pages_per_work: int = DEFAULT_MAX_PAGES_PER_WORK,
        request_get: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    if dataset not in contract.SPECS:
        raise ValueError("unsupported_intraday_history_dataset")
    if not pagination_contract_proven:
        raise PaginationContractNotReady(f"{dataset} pagination continuation is not first-party proven")
    symbols = sorted({symbol.upper() for symbol in symbols})
    scope_value = {"provider": contract.PROVIDER, "dataset": dataset, "symbols": symbols,
                   "session_date": session_date, "limit": limit, "order": contract.ORDER}
    scope = hashlib.sha256(contract.canonical_json(scope_value).encode("utf-8")).hexdigest()[:24]
    checkpoint = lake.load_checkpoint(runtime_root, contract.PROVIDER, dataset, scope)
    attempted: list[str] = []
    skipped: list[str] = []
    for symbol in symbols:
        root = contract.work_unit_id(dataset, symbol, session_date)
        if lake.unit_status(checkpoint, root) in {"success", "failed"}:
            skipped.append(root)
            continue
        attempted.append(root)
        state = dict((checkpoint.get("intraday_pagination", {}) or {}).get(root, {}))
        state.setdefault("page_count", 0); state.setdefault("raw_record_count", 0)
        state.setdefault("seen_tokens", [contract.CURSOR_INITIAL]); state.setdefault("seen_pages", [])
        cursor = state.get("next_cursor")
        while True:
            page_unit = contract.page_unit_id(root, cursor)
            if int(state["page_count"]) >= max_pages_per_work:
                checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code="max_pages_per_work_exceeded")
                checkpoint = lake.record_unit_result(checkpoint, root, status="failed", error_code="max_pages_per_work_exceeded")
                lake.save_checkpoint(runtime_root, checkpoint)
                break
            query = contract.request_query(dataset, session_date, limit=limit, cursor=cursor)
            response = fetch_capability_raw(dataset, api_key=api_key, api_secret=api_secret,
                                            symbol=symbol, query=query, request_get=request_get)
            if not response.get("ok"):
                checkpoint = lake.record_unit_result(checkpoint, page_unit, status="failed", error_code=str(response.get("error_code")))
                checkpoint = lake.record_unit_result(checkpoint, root, status="failed", error_code=str(response.get("error_code")))
                lake.save_checkpoint(runtime_root, checkpoint); break
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
                lake.save_checkpoint(runtime_root, checkpoint); break
            raw = contract.observation(dataset=dataset, symbol=symbol, session_date=session_date, response=response,
                                       cursor=cursor, page_index=int(state["page_count"]), run_id=run_id,
                                       run_scope_id=scope, page_unit=page_unit, records=records)
            write = lake.write_raw_observation(runtime_root, raw, run_id=run_id)
            checkpoint = lake.record_unit_result(checkpoint, page_unit, status="success", raw_file=write["path"], observation_id=raw.observation_id)
            state = copy.deepcopy(state); state["page_count"] += 1; state["raw_record_count"] += len(records)
            state["seen_pages"].append(page_id); state["next_cursor"] = next_cursor
            if next_cursor: state["seen_tokens"].append(next_cursor)
            checkpoint.setdefault("intraday_pagination", {})[root] = state
            if next_cursor is None:
                checkpoint = lake.record_unit_result(checkpoint, root, status="success", raw_file=write["path"], observation_id=raw.observation_id)
            lake.save_checkpoint(runtime_root, checkpoint)
            if next_cursor is None: break
            cursor = next_cursor; sleep(0.0)
    roots = [contract.work_unit_id(dataset, symbol, session_date) for symbol in symbols]
    successes = [root for root in roots if lake.unit_status(checkpoint, root) == "success"]
    failures = [{"unit_id": root, "error_code": checkpoint["units"][root].get("error_code")} for root in roots if lake.unit_status(checkpoint, root) == "failed"]
    manifest = lake.build_manifest(provider=contract.PROVIDER, dataset=dataset, run_id=run_id, run_scope_id=scope,
        started_at=vn_time.vn_now_iso(), ended_at=vn_time.vn_now_iso(), requested_units=roots,
        attempted_units=attempted, successful_units=successes, failed_units=failures, skipped_units=skipped,
        output_dir=str(lake.raw_run_dir(runtime_root, contract.PROVIDER, dataset, run_id)),
        checkpoint_file=str(lake.checkpoint_path(runtime_root, contract.PROVIDER, dataset, scope)),
        extra={"session_date": session_date, "pagination_contract_proven": True,
               "request_roots": len(roots), "raw_page_files": sum(int(v.get("page_count", 0)) for v in checkpoint.get("intraday_pagination", {}).values()),
               "raw_records": sum(int(v.get("raw_record_count", 0)) for v in checkpoint.get("intraday_pagination", {}).values()),
               "raw_semantics": "PRESERVED_UNQUALIFIED"})
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
                     max_pages_per_work=args.max_pages_per_work)
        print(json.dumps({**payload, "status": "BULK_RUN_FINISHED", "manifest": result["manifest"]},
                         sort_keys=True, default=str))
        return 0
    print(json.dumps({**payload, "status": "DRY_VALIDATION_ONLY"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
