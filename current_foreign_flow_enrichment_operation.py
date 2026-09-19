"""Current foreign-flow enrichment operation: one bounded, resumable orchestration from a
frozen acquisition cohort to verified, exact-session, VALUE-only foreign-flow evidence.

CONTRACT SEPARATION (do not confuse the two)
    IMMUTABLE:  current_foreign_flow_acquisition_manifest/v1 (current_foreign_flow_retention.py)
                defines WHAT should be acquired for one reference session. Cohort membership
                never changes on a retry; a changed owner focus produces a different manifest
                identity, never a mutated one.
    MUTABLE:    current_foreign_flow_enrichment_operation/v1 (this module) records WHAT HAS
                HAPPENED to each manifest member -- per-ticker state, network usage, failure
                detail -- and is rebuilt fresh on every invocation from currently retained
                evidence. It never mutates the manifest.

NETWORK BOUNDARY
    ``acquire_foreign_flow_for_manifest`` is the only function in this codebase permitted to
    reach the live DNSE foreign-trading endpoint for this contract, and only when its caller
    passes ``allow_network=True`` explicitly. Every other caller (normal Daily, dry-run/plan
    tooling) leaves it at the default ``False``; a ticker that would otherwise need a network
    call is then reported ``NETWORK_DISABLED_PENDING_ACQUISITION`` -- a status, never an
    exception, so it can never fail Core Daily. No environment variable can silently flip this;
    the caller must pass the keyword argument itself.

CREDENTIAL BOUNDARY
    Credentials are resolved only inside this module's network path, only when
    ``allow_network=True`` and the caller did not already supply ``api_key``/``api_secret``
    (e.g. a test). No secret is ever written into a returned operation record, a log line, or
    an exception message -- only ``credentials_available`` (a boolean) and a bounded reason code.

EXACT-SESSION IDEMPOTENCY (Phase 5)
    Per ticker: if raw is not yet retained and a qualified exact-session VALUE observation
    already is, nothing is re-derived or reacquired -- the retained VALUE is trusted as-is.
    If raw IS retained (freshly acquired or from an earlier run) it is always re-normalized and
    handed to the store's own conflict guard; an identical re-derivation is a harmless rewrite
    (idempotent rerun), a differing one is surfaced as ``VALUE_CONFLICT``, never silently
    overwritten. This makes rerunning the exact same operation cheap, safe, and resumable.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import current_foreign_flow_retention as retention
import dnse_foreign_flow_store as store
import dnse_foreign_trading_raw as raw_contract
import market_raw_lake as lake
from dnse_foreign_flow_capability import DnseForeignFlowError
from vn_time import vn_now_iso

import sys as _sys
from pathlib import Path as _Path

_TOOLS = _Path(__file__).resolve().parent / "tools"
if str(_TOOLS) not in _sys.path:
    _sys.path.insert(0, str(_TOOLS))
import bulk_ingest_dnse_foreign_trading_raw as bulk_ingest  # noqa: E402

CONTRACT_VERSION = "current_foreign_flow_enrichment_operation/v1"
SCHEMA_VERSION = "1.0.0"

# Per-ticker states. Every ticker terminates in exactly one of these; none disappears silently.
PENDING = "PENDING"
RAW_ALREADY_RETAINED = "RAW_ALREADY_RETAINED"
RAW_ACQUIRED = "RAW_ACQUIRED"
VALUE_ALREADY_RETAINED = "VALUE_ALREADY_RETAINED"
VALUE_PERSISTED = "VALUE_PERSISTED"
COMPLETE = "COMPLETE"
FAILED_RETRYABLE = "FAILED_RETRYABLE"
FAILED_TERMINAL = "FAILED_TERMINAL"
SESSION_MISSING = "SESSION_MISSING"
SESSION_MISMATCH = "SESSION_MISMATCH"
RAW_CONFLICT = "RAW_CONFLICT"
VALUE_CONFLICT = "VALUE_CONFLICT"
SKIPPED_ALREADY_COMPLETE = "SKIPPED_ALREADY_COMPLETE"
NETWORK_DISABLED_PENDING_ACQUISITION = "NETWORK_DISABLED_PENDING_ACQUISITION"
CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"

_COMPLETE_STATES = frozenset({COMPLETE, SKIPPED_ALREADY_COMPLETE})
_FAILED_STATES = frozenset({FAILED_RETRYABLE, FAILED_TERMINAL, CREDENTIAL_UNAVAILABLE})
_CONFLICT_STATES = frozenset({VALUE_CONFLICT, RAW_CONFLICT})
_SESSION_ISSUE_STATES = frozenset({SESSION_MISSING, SESSION_MISMATCH})
_PENDING_STATES = frozenset({NETWORK_DISABLED_PENDING_ACQUISITION, PENDING})

# Operation-level statuses (Phase 16 deterministic reduction).
STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_PENDING_NETWORK = "PENDING_NETWORK"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_BLOCKED_CONFLICT = "BLOCKED_CONFLICT"
STATUS_FAILED_OPERATIONAL = "FAILED_OPERATIONAL"


class ForeignFlowEnrichmentError(ValueError):
    """Fail-closed rejection at the enrichment-operation boundary."""


def _result(ticker: str, state: str, detail: str, network_calls: int,
            history: Sequence[str], verification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ticker": ticker, "state": state, "detail": detail, "network_calls": network_calls,
        "state_history": list(history) + [state],
        "verification": dict(verification) if verification is not None else None,
    }


def _matching_value_observation(runtime_root: Path | str, ticker: str, session: str) -> dict[str, Any] | None:
    for observation in store.read_observations(runtime_root, ticker):
        if observation.get("session_date") == session:
            return observation
    return None


def verify_ticker_current(runtime_root: Path | str, ticker: str, session: str) -> dict[str, Any]:
    """Phase 12 post-persistence verification, reusing the store's own series/freshness logic.

    Never recalculates a semantic the store already owns; it only asserts the exact facts a
    ticker must satisfy before this operation may call it COMPLETE.
    """
    series = store.build_series(runtime_root, ticker, reference_session_date=session)
    latest = series.get("latest_session") or {}
    freshness = series.get("freshness") or {}
    same_session_count = sum(
        1 for observation in store.read_observations(runtime_root, ticker)
        if observation.get("session_date") == session
    )
    buy, sell, net = (latest.get("foreign_buy_value_vnd"), latest.get("foreign_sell_value_vnd"),
                      latest.get("foreign_net_value_vnd"))
    checks = {
        "ticker_present": latest.get("ticker") == ticker,
        "exact_session_observation_exists": latest.get("session_date") == session,
        "qualification_status_value_only": latest.get("qualification_status") == store.VALUE_QUALIFICATION_STATUS,
        "source_is_dnse": latest.get("source") == store.PROVIDER,
        "buy_sell_net_arithmetic_consistent": (
            buy is not None and sell is not None and net is not None and net == buy - sell
        ),
        "no_conflicting_same_session_observation": same_session_count <= 1,
        "freshness_current": freshness.get("status") == store.FRESHNESS_CURRENT,
    }
    failing = [name for name, ok in checks.items() if not ok]
    return {
        "status": "CURRENT" if not failing else "NOT_CURRENT",
        "checks": checks, "failing_checks": failing, "freshness": dict(freshness),
    }


def _read_retained_pages(runtime_root: Path | str, scope: str, root_unit: str) -> list[dict[str, Any]]:
    """Read the complete, already-retained cursor chain without network access."""
    import pandas as pd

    checkpoint = lake.load_checkpoint(runtime_root, raw_contract.PROVIDER, raw_contract.DATASET, scope)
    units = checkpoint.get("units", {}) or {}
    if lake.unit_status(checkpoint, root_unit) != "success":
        raise FileNotFoundError(f"root_not_complete:{root_unit}")
    pagination = raw_contract.pagination_state(checkpoint, root_unit)
    if not pagination or pagination.get("next_cursor") is not None:
        raise FileNotFoundError(f"pagination_not_complete:{root_unit}")
    pages: list[dict[str, Any]] = []
    prefix = root_unit + "__page_"
    for page_unit, unit in units.items():
        if not str(page_unit).startswith(prefix):
            continue
        if not isinstance(unit, Mapping) or unit.get("status") != "success" or not unit.get("raw_file"):
            raise FileNotFoundError(f"page_not_retained:{page_unit}")
        frame = pd.read_parquet(unit["raw_file"])
        if len(frame) != 1:
            raise FileNotFoundError(f"page_malformed:{page_unit}")
        row = frame.iloc[0]
        provenance = json.loads(row["provenance_json"])
        pages.append({
            "instrument": row["instrument"], "source_event_time": row["source_event_time"],
            "endpoint": provenance.get("endpoint"), "provenance": provenance,
            "raw_payload": json.loads(row["raw_payload_json"]), "raw_sha256": row["raw_payload_hash"],
        })
    if len(pages) != pagination.get("page_count"):
        raise FileNotFoundError(f"page_count_mismatch:{root_unit}")
    return sorted(pages, key=lambda page: (page.get("provenance") or {}).get("page_index", -1))


def _page_request_count(checkpoint: Mapping[str, Any], root_unit: str) -> int:
    """Count actual attempted HTTP pages, distinct from logical ticker roots."""
    prefix = root_unit + "__page_"
    return sum(int((unit or {}).get("attempts") or 0) for name, unit in (checkpoint.get("units", {}) or {}).items()
               if str(name).startswith(prefix))


_RAW_PAGE_ERROR_STATE = {
    "RAW_PAGE_MALFORMED_OR_EMPTY": SESSION_MISSING,
    "RAW_PAGE_TICKER_OR_REQUESTED_SESSION_MISMATCH": SESSION_MISMATCH,
    "RAW_PAGE_ENDPOINT_MISMATCH": RAW_CONFLICT,
    "RAW_PAGE_PROVIDER_TICKER_MISMATCH": RAW_CONFLICT,
    "RAW_PAGE_HASH_MISMATCH": RAW_CONFLICT,
    "RAW_PAGE_PAGINATION_NOT_COMPLETE": FAILED_TERMINAL,
    "RAW_SEQUENCE_EXACT_SESSION_MISSING": SESSION_MISSING,
    "RAW_SEQUENCE_TICKER_OR_REQUESTED_SESSION_MISMATCH": SESSION_MISMATCH,
    "RAW_SEQUENCE_PAGE_HASH_MISMATCH": RAW_CONFLICT,
    "RAW_SEQUENCE_ENDPOINT_MISMATCH": RAW_CONFLICT,
    "RAW_SEQUENCE_PROVIDER_TICKER_MISMATCH": RAW_CONFLICT,
    "RAW_SEQUENCE_DUPLICATE_PAGE_IDENTITY": RAW_CONFLICT,
    "RAW_SEQUENCE_CONFLICTING_EXACT_SESSION_RECORDS": RAW_CONFLICT,
}


def _normalize_and_persist(*, ticker: str, session: str, runtime_root: Path | str,
                           network_calls: int, history: list[str]) -> dict[str, Any]:
    scope = raw_contract.compute_run_scope_id(symbols=[ticker], session_date=session)
    root_unit = raw_contract.work_unit_id(ticker, session)
    try:
        pages = _read_retained_pages(runtime_root, scope, root_unit)
    except FileNotFoundError as exc:
        return _result(ticker, FAILED_TERMINAL, f"RAW_PAGE_FILE_MISSING:{exc}", network_calls, history)

    try:
        observation = retention.normalize_exact_raw_sequence(ticker=ticker, reference_session=session, pages=pages)
    except DnseForeignFlowError as exc:
        message = str(exc)
        state = SESSION_MISMATCH if message.startswith("point_in_time_mismatch") else RAW_CONFLICT
        return _result(ticker, state, message, network_calls, history)
    except ValueError as exc:
        message = str(exc)
        state = _RAW_PAGE_ERROR_STATE.get(message, FAILED_TERMINAL)
        return _result(ticker, state, message, network_calls, history)

    try:
        retention.write_exact_value_observation(runtime_root, ticker, observation)
    except ValueError as exc:
        return _result(ticker, VALUE_CONFLICT, str(exc), network_calls, history)
    history.append(VALUE_PERSISTED)

    verification = verify_ticker_current(runtime_root, ticker, session)
    if verification["status"] != "CURRENT":
        return _result(ticker, FAILED_TERMINAL, "POST_WRITE_VERIFICATION_FAILED:" + ",".join(verification["failing_checks"]),
                       network_calls, history, verification)
    return _result(ticker, COMPLETE, "RAW_TO_VALUE_PERSISTED_AND_VERIFIED", network_calls, history, verification)


def _process_ticker(*, ticker: str, session: str, runtime_root: Path | str, allow_network: bool,
                    credentials_available: bool, api_key: str | None, api_secret: str | None,
                    request_get: Callable[..., Any] | None, sleep: Callable[[float], None],
                    max_retries: int, backoff_seconds: float, request_delay_seconds: float,
                    retry_failed: bool, run_id: str) -> dict[str, Any]:
    history: list[str] = []
    scope = raw_contract.compute_run_scope_id(symbols=[ticker], session_date=session)
    root_unit = raw_contract.work_unit_id(ticker, session)
    checkpoint = lake.load_checkpoint(runtime_root, raw_contract.PROVIDER, raw_contract.DATASET, scope)
    root_status = lake.unit_status(checkpoint, root_unit)
    network_calls = 0

    if root_status != "success":
        existing_value = _matching_value_observation(runtime_root, ticker, session)
        if existing_value is not None:
            history.append(VALUE_ALREADY_RETAINED)
            verification = verify_ticker_current(runtime_root, ticker, session)
            if verification["status"] == "CURRENT":
                return _result(ticker, SKIPPED_ALREADY_COMPLETE, "EXACT_SESSION_VALUE_ALREADY_RETAINED_NO_RAW_TO_RECONCILE",
                               network_calls, history, verification)
            return _result(ticker, FAILED_TERMINAL, "RETAINED_VALUE_FAILED_VERIFICATION:" + ",".join(verification["failing_checks"]),
                           network_calls, history, verification)
        if not allow_network:
            history.append(PENDING)
            return _result(ticker, NETWORK_DISABLED_PENDING_ACQUISITION, "RAW_NOT_RETAINED_NETWORK_DISABLED",
                           network_calls, history)
        if not credentials_available:
            return _result(ticker, CREDENTIAL_UNAVAILABLE, "DNSE_CREDENTIALS_NOT_CONFIGURED", network_calls, history)

        raw_result = bulk_ingest.run(
            runtime_root=Path(runtime_root), api_key=api_key, api_secret=api_secret, symbols=[ticker],
            session_date=session, run_id=run_id, universe_context={}, max_retries=max_retries,
            backoff_seconds=backoff_seconds, request_delay_seconds=request_delay_seconds,
            request_get=request_get, sleep=sleep, retry_failed=retry_failed,
        )
        if raw_result["status"] == "AUTHENTICATION_FAILED_MID_RUN":
            return _result(ticker, CREDENTIAL_UNAVAILABLE, "DNSE_AUTHENTICATION_FAILED", network_calls, history)
        checkpoint = lake.load_checkpoint(runtime_root, raw_contract.PROVIDER, raw_contract.DATASET, scope)
        network_calls = _page_request_count(checkpoint, root_unit)
        root_status = lake.unit_status(checkpoint, root_unit)
        if root_status != "success":
            error_code = str((checkpoint.get("units", {}).get(root_unit) or {}).get("error_code"))
            retryable = error_code == "rate_limited" or error_code.startswith("request_failed_")
            state = FAILED_RETRYABLE if retryable else FAILED_TERMINAL
            return _result(ticker, state, f"RAW_ACQUISITION_FAILED:{error_code}", network_calls, history)
        history.append(RAW_ACQUIRED)
    else:
        history.append(RAW_ALREADY_RETAINED)

    return _normalize_and_persist(ticker=ticker, session=session, runtime_root=runtime_root,
                                  network_calls=network_calls, history=history)


def _reduce_status(counts: Mapping[str, int], total: int) -> str:
    complete = sum(counts.get(state, 0) for state in _COMPLETE_STATES)
    pending = sum(counts.get(state, 0) for state in _PENDING_STATES)
    conflict = sum(counts.get(state, 0) for state in _CONFLICT_STATES)
    failed = sum(counts.get(state, 0) for state in _FAILED_STATES)
    if total == 0:
        return STATUS_UNAVAILABLE
    if complete == total:
        return STATUS_COMPLETE
    if complete > 0:
        return STATUS_PARTIAL
    if pending == total:
        return STATUS_PENDING_NETWORK
    if failed == total:
        return STATUS_FAILED_OPERATIONAL
    if conflict > 0 and pending == 0:
        return STATUS_BLOCKED_CONFLICT
    if pending > 0:
        return STATUS_PENDING_NETWORK
    return STATUS_UNAVAILABLE


def _identity(operation: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in operation.items()
           if key not in {"operation_identity", "operation_sha256", "timestamps"}}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    operation["operation_sha256"] = digest
    operation["operation_identity"] = "current_foreign_flow_enrichment_operation:" + digest
    return operation


def acquire_foreign_flow_for_manifest(
    manifest: Mapping[str, Any], *, runtime_root: Path | str, allow_network: bool = False,
    api_key: str | None = None, api_secret: str | None = None, secrets_file: str | None = None,
    request_get: Callable[..., Any] | None = None, sleep: Callable[[float], None] = time.sleep,
    max_retries: int = bulk_ingest.DEFAULT_MAX_RETRIES, backoff_seconds: float = bulk_ingest.DEFAULT_BACKOFF_SECONDS,
    request_delay_seconds: float = bulk_ingest.DEFAULT_REQUEST_DELAY_SECONDS, retry_failed: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one enrichment attempt for one frozen manifest and exact session.

    ``allow_network`` defaults to False: no module reached from that default path can ever
    issue a real DNSE request (see module docstring). Passing ``True`` without also supplying
    ``api_key``/``api_secret`` triggers the one permitted credential read, scoped to this call.
    """
    if manifest.get("contract_version") != retention.CONTRACT_VERSION:
        raise ForeignFlowEnrichmentError("REQUIRE_CURRENT_FOREIGN_FLOW_ACQUISITION_MANIFEST_V1")
    session = str(manifest["reference_session"])
    runtime_root = Path(runtime_root)
    started_at = vn_now_iso()
    run_id = run_id or f"foreign-flow-enrichment-{session}"

    credentials_available = False
    credential_note = None
    if allow_network:
        if api_key is not None and api_secret is not None:
            credentials_available = True
        else:
            from dnse_access import credential_status, credentials_for_request
            from dnse_secrets_env import ensure_credentials_loaded

            ensure_credentials_loaded(secrets_file)
            status = credential_status()
            credentials_available = bool(status["configured"])
            if credentials_available:
                api_key, api_secret = credentials_for_request()
            else:
                credential_note = "CREDENTIAL_UNAVAILABLE_UNDER_LIVE_FLAG"

    records: dict[str, Any] = {}
    auth_aborted = False
    total_network_calls = 0
    for ticker in manifest["eligible_tickers"]:
        if auth_aborted:
            records[ticker] = _result(ticker, CREDENTIAL_UNAVAILABLE, "AUTHENTICATION_ABORTED_EARLIER_IN_OPERATION", 0, [])
            continue
        outcome = _process_ticker(
            ticker=ticker, session=session, runtime_root=runtime_root, allow_network=allow_network,
            credentials_available=credentials_available, api_key=api_key, api_secret=api_secret,
            request_get=request_get, sleep=sleep, max_retries=max_retries, backoff_seconds=backoff_seconds,
            request_delay_seconds=request_delay_seconds, retry_failed=retry_failed, run_id=run_id,
        )
        total_network_calls += outcome["network_calls"]
        if outcome["state"] == CREDENTIAL_UNAVAILABLE and outcome["detail"] == "DNSE_AUTHENTICATION_FAILED":
            auth_aborted = True
        records[ticker] = outcome

    counts = Counter(item["state"] for item in records.values())
    total = len(manifest["eligible_tickers"])
    complete_count = sum(counts.get(state, 0) for state in _COMPLETE_STATES)
    pending_count = sum(counts.get(state, 0) for state in _PENDING_STATES)
    failed_count = sum(counts.get(state, 0) for state in _FAILED_STATES)
    conflict_count = sum(counts.get(state, 0) for state in _CONFLICT_STATES)
    session_issue_count = sum(counts.get(state, 0) for state in _SESSION_ISSUE_STATES)

    operation = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "reference_session": session, "acquisition_manifest_identity": manifest["artifact_identity"],
        "requested_tickers": list(manifest["eligible_tickers"]), "excluded_tickers": list(manifest["excluded_tickers"]),
        "records": records, "counts": dict(sorted(counts.items())),
        "complete_count": complete_count, "pending_count": pending_count, "failed_count": failed_count,
        "conflict_count": conflict_count, "session_issue_count": session_issue_count,
        "network": {
            "allow_network": allow_network, "credentials_available": credentials_available,
            "credential_note": credential_note,
            "root_acquisition_units": sum(1 for item in records.values() if item["network_calls"] > 0),
            "http_page_requests": total_network_calls,
            "network_calls_made": total_network_calls,
        },
        "authority_boundary": {
            "value_only": True, "no_volume_or_room": True, "no_liquidity_or_sizing": True,
            "no_smart_money_or_intent": True, "no_price_prediction": True, "is_actionable": False,
        },
        "timestamps": {"started_at": started_at, "completed_at": vn_now_iso()},
    }
    operation["status"] = _reduce_status(dict(counts), total)
    return _identity(operation)


def write_operation_snapshot(path: str | Path, operation: Mapping[str, Any]) -> Path:
    """Persist the latest operation attempt at its session path.

    Deliberately mutable, unlike the manifest and every other write_immutable_* artifact in
    this codebase (see module docstring): a resumed or retried operation legitimately produces
    a different snapshot (more tickers COMPLETE) at the SAME session path, and that is the
    expected, correct behavior for the mutable progress contract -- never a conflict.
    """
    from atomic_io import atomic_write_file, validate_json_file

    destination = Path(path)
    text = json.dumps(operation, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    atomic_write_file(destination, text, validator=validate_json_file)
    return destination
