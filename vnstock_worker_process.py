"""Bounded VNStock worker subprocess entrypoint.

VNSTOCK_EXACT_SESSION_WORKER_ISOLATION_AND_SENTINEL_EQUIVALENCE_V1. This process is TRANSPORT
ONLY: it knows how to call the existing, qualified ``vn_stock_pipeline.fetch_single_source``
adapter for KBS/VCI and how to gate those calls through the existing shared
``vnstock_rate_governor``. It owns zero source-ordering/fallback/quarantine/conflict-resolution
policy -- every request it receives already names the exact ``(ticker, provider, start, end)`` to
fetch; ``purpose`` is diagnostic context only and must never change which adapter call is made.

This is the ONLY place in the whole exact-session acquisition path that imports ``vnstock``/
``vnai`` (transitively, via ``vn_stock_pipeline``) after this milestone. It is launched by
``vnstock_worker_client.VnstockWorkerFetcher`` as a plain child process
(``sys.executable vnstock_worker_process.py``) and speaks newline-delimited JSON on stdin/stdout
(``vnstock_worker_protocol``). stdout carries ONLY protocol messages -- never banners, prints, or
provider stdout; anything the adapter or a dependency writes to stdout would corrupt the protocol
stream, so this process redirects its own real stdout to a private fd and gives the adapter/
dependencies a harmless replacement for the duration of the run (see ``_reserve_protocol_stdout``).

Not a security sandbox. Process separation here buys failure isolation, import containment,
lifetime containment, and bounded timeout handling -- it does not by itself prevent telemetry,
filesystem writes, or arbitrary outbound network activity by the ``vnstock``/``vnai`` package or
its dependencies. Those require separate controls and are out of this milestone's scope.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from vnstock_worker_protocol import (
    FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION,
    MSG_FETCH,
    MSG_FETCH_RESULT,
    MSG_GOVERNOR_DIAGNOSTIC,
    MSG_GOVERNOR_DIAGNOSTIC_RESULT,
    MSG_READY,
    MSG_SHUTDOWN,
    MSG_SHUTDOWN_ACK,
    MSG_WORKER_ERROR,
    PROTOCOL_VERSION,
)

# Generous internal concurrency: the REAL throttle is the shared rate governor's 45-req/60s
# budget (vnstock_rate_governor), not this pool's size. The parent's own per-provider dispatch
# policy (KBS max 2 concurrent, VCI sequential) already bounds how many requests are ever
# in flight at once, so this only needs to be large enough to never itself become a bottleneck.
_WORKER_INTERNAL_POOL_SIZE = 8
# A request the parent never asked us to reconsider must still eventually return -- this is a
# process-level safety net, independent of (and larger than) the parent's own per-request
# timeout, so the parent's timeout always fires first under normal operation.
_STDOUT_WRITE_LOCK = threading.Lock()


def _emit(message: dict[str, Any], *, real_stdout) -> None:
    line = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with _STDOUT_WRITE_LOCK:
        real_stdout.write(line + "\n")
        real_stdout.flush()


def _dataframe_to_rows(df) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _process_fetch(request: dict[str, Any], *, real_stdout) -> None:
    request_id = request.get("request_id")
    ticker = request.get("ticker")
    provider = request.get("provider")
    try:
        import vn_stock_pipeline as vsp

        vsp._install_bounded_http()
        outcome = vsp.fetch_single_source(
            ticker, provider, request.get("start"), request.get("end"),
            bypass_circuit_check=bool(request.get("bypass_circuit_check", False)),
        )
        rows: list[dict[str, Any]] = []
        unit_scale = None
        if outcome.status == "success" and outcome.data is not None:
            rows = _dataframe_to_rows(outcome.data)
            unit_scale = outcome.data.attrs.get("unit_scale")
        response = {
            "protocol_version": PROTOCOL_VERSION,
            "type": MSG_FETCH_RESULT,
            "request_id": request_id,
            "provider": provider,
            "ticker": ticker,
            "status": outcome.status,
            "rows": rows,
            "unit_scale": unit_scale,
            "lineage": outcome.lineage or [],
            "errors": outcome.errors or [],
            "transient_failure": bool(outcome.transient_failure),
            "request_attempts": int(outcome.request_attempts),
            "retry_count": int(outcome.retry_count),
            "timeout_count": int(outcome.timeout_count),
            "http_429_count": int(outcome.http_429_count),
            "http_5xx_count": int(outcome.http_5xx_count),
            "retry_after_seconds": float(outcome.retry_after_seconds),
        }
        _emit(response, real_stdout=real_stdout)
    except Exception as exc:  # noqa: BLE001 -- must reach the parent as a typed worker_error,
        # never crash the worker for one bad request, never silently drop it.
        _emit(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": MSG_WORKER_ERROR,
                "request_id": request_id,
                "failure_class": FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION,
                "message": f"{type(exc).__name__}:{exc}",
                "traceback": traceback.format_exc(limit=20),
            },
            real_stdout=real_stdout,
        )


def main() -> int:
    # Reserve the real fd 1 for the protocol only; redirect Python-level sys.stdout so any
    # accidental print()/banner from the adapter or a dependency lands somewhere harmless
    # instead of corrupting the JSON-lines stream.
    real_stdout = os.fdopen(os.dup(1), "w", encoding="utf-8", closefd=True)
    devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = devnull

    pool = ThreadPoolExecutor(max_workers=_WORKER_INTERNAL_POOL_SIZE, thread_name_prefix="vnstock-worker")
    try:
        import vnstock_rate_governor as governor_module

        governor = governor_module.VnstockRateGovernor()
        governor_module.set_active_governor(governor)
    except Exception as exc:  # noqa: BLE001
        _emit(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": MSG_WORKER_ERROR,
                "request_id": None,
                "failure_class": "WORKER_STARTUP_FAILURE",
                "message": f"{type(exc).__name__}:{exc}",
                "traceback": traceback.format_exc(limit=20),
            },
            real_stdout=real_stdout,
        )
        return 1

    _emit({"protocol_version": PROTOCOL_VERSION, "type": MSG_READY, "request_id": None}, real_stdout=real_stdout)

    stdin = sys.stdin
    try:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Malformed input from the parent -- report and keep serving; the parent side
                # (not this process) owns whether that's fatal to the overall operation.
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": MSG_WORKER_ERROR,
                        "request_id": None,
                        "failure_class": "WORKER_RECEIVED_MALFORMED_JSON",
                        "message": "could not parse incoming line as JSON",
                    },
                    real_stdout=real_stdout,
                )
                continue
            msg_type = message.get("type")
            if msg_type == MSG_FETCH:
                pool.submit(_process_fetch, message, real_stdout=real_stdout)
            elif msg_type == MSG_GOVERNOR_DIAGNOSTIC:
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": MSG_GOVERNOR_DIAGNOSTIC_RESULT,
                        "request_id": message.get("request_id"),
                        "diagnostic": governor.diagnostic(),
                    },
                    real_stdout=real_stdout,
                )
            elif msg_type == MSG_SHUTDOWN:
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": MSG_SHUTDOWN_ACK,
                        "request_id": message.get("request_id"),
                    },
                    real_stdout=real_stdout,
                )
                break
            else:
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": MSG_WORKER_ERROR,
                        "request_id": message.get("request_id"),
                        "failure_class": "WORKER_RECEIVED_UNKNOWN_MESSAGE_TYPE",
                        "message": f"unknown type {msg_type!r}",
                    },
                    real_stdout=real_stdout,
                )
    finally:
        pool.shutdown(wait=True, cancel_futures=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
