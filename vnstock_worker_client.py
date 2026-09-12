"""Parent-side client for the bounded VNStock worker subprocess.

VNSTOCK_EXACT_SESSION_WORKER_ISOLATION_AND_SENTINEL_EQUIVALENCE_V1. ``VnstockWorkerFetcher`` is a
drop-in replacement for ``vn_stock_pipeline.fetch_single_source`` (same call signature, same
``FetchOutcome``-shaped return value via ``vnstock_worker_protocol.WorkerFetchOutcome``) that
routes the actual KBS/VCI transport call through one bounded worker subprocess instead of calling
``vn_stock_pipeline``/``vnstock``/``vnai`` directly in this process.

This module -- and everything it imports (``vnstock_worker_protocol``, stdlib only) -- must never
import ``vnstock``/``vnai`` or ``vn_stock_pipeline``. The worker subprocess (a fully separate
Python process, launched via ``subprocess.Popen``) is the only place those are imported; see
``vnstock_worker_process.py``.

Lifetime: ONE worker subprocess per exact-session resolution operation. The subprocess is started
lazily (only on the first ``fetch``/``fetch_many`` call) so an operation that needs no secondary
transport at all never spawns one, and it is torn down deterministically via ``shutdown()`` --
callers MUST call ``shutdown()`` in a ``finally`` block regardless of how the operation ended.

Failure policy (V1, no transparent restart): any worker/protocol-level failure (startup failure,
malformed/duplicate/unknown-version message, timeout, unexpected process exit) marks this
fetcher permanently failed -- every subsequent call raises the same
``vnstock_worker_protocol.VnstockWorkerFailure`` subclass immediately, and the underlying process
(if still alive) is killed. A worker/import failure is NEVER translated into a provider-level
``SESSION_MISSING``/rejection/malformed outcome -- it always raises, so the parent's own
gap-recovery/sentinel/conflict logic never mistakes "the transport channel broke" for "the
provider genuinely had nothing."

Not a security sandbox -- see ``vnstock_worker_process.py``'s own docstring for the exact scope
of what process separation here does and does not provide.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# vnstock_rate_governor is a pure accounting/policy module (threading/time/collections only --
# no vnstock/vnai import anywhere in it), so importing it here does not reintroduce a parent-side
# transport dependency. Only its two fixed steady-state-pacing constants are used, to reproduce
# VnstockRateGovernor.estimated_minimum_seconds_for()'s pure arithmetic without a parent-side
# governor instance that would "pretend" to gate the worker's real requests.
from vnstock_rate_governor import DEFAULT_EFFECTIVE_RPM, RATE_WINDOW_SECONDS
from vnstock_worker_protocol import (
    MSG_FETCH_RESULT,
    MSG_GOVERNOR_DIAGNOSTIC_RESULT,
    MSG_READY,
    MSG_SHUTDOWN_ACK,
    MSG_WORKER_ERROR,
    PROTOCOL_VERSION,
    PURPOSE_GAP_RECOVERY,
    VnstockWorkerAdapterError,
    VnstockWorkerFailure,
    VnstockWorkerProcessExitError,
    VnstockWorkerProtocolError,
    VnstockWorkerStartupError,
    VnstockWorkerTimeoutError,
    WorkerFetchOutcome,
    build_fetch_request,
    build_governor_diagnostic_request,
    build_shutdown_request,
    validate_envelope,
)

_WORKER_SCRIPT = Path(__file__).with_name("vnstock_worker_process.py")
DEFAULT_STARTUP_TIMEOUT_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0


def _rows_to_dataframe(rows: list[dict[str, Any]], unit_scale: Any):
    import pandas as pd

    df = pd.DataFrame(rows)
    df.attrs["unit_scale"] = unit_scale
    return df


class VnstockWorkerFetcher:
    """One bounded worker subprocess, lazily started, serving every KBS/VCI transport request
    for a single exact-session resolution operation (ordinary gaps, residual-yield probe, DNSE
    quality sentinel corroboration, and degraded-provider expansion alike -- the caller decides
    which of those to run; this object only ever executes the exact ``(ticker, provider, start,
    end)`` it is asked for).
    """

    def __init__(
        self,
        *,
        session: str | None = None,
        worker_script: Path | None = None,
        python_executable: str | None = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
        shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        env: dict[str, str] | None = None,
    ):
        self._session = session
        self._worker_script = worker_script or _WORKER_SCRIPT
        self._python_executable = python_executable or sys.executable
        self._request_timeout = request_timeout
        self._startup_timeout = startup_timeout
        self._shutdown_timeout = shutdown_timeout
        self._env = env

        self._lifecycle_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._started = False
        self._failed_exc: VnstockWorkerFailure | None = None
        self._ready_event = threading.Event()

        self._diagnostics: dict[str, Any] = {
            "worker_started": False,
            "worker_pid": None,
            "worker_protocol_version": PROTOCOL_VERSION,
            "request_count": 0,
            "provider_attempt_counts": {},
            "worker_exit_status": None,
            "timeout_state": "NOT_APPLICABLE",
        }
        self._diagnostics_lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------------------------

    def _ensure_started(self) -> None:
        if self._failed_exc is not None:
            raise self._failed_exc
        if self._started:
            return
        with self._lifecycle_lock:
            if self._started:
                if self._failed_exc is not None:
                    raise self._failed_exc
                return
            try:
                import os

                popen_env = {**os.environ, **self._env} if self._env else None
                self._process = subprocess.Popen(
                    [self._python_executable, "-u", str(self._worker_script)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", bufsize=1, env=popen_env,
                )
            except OSError as exc:
                failure = VnstockWorkerStartupError(
                    f"WORKER_PROCESS_SPAWN_FAILED:{exc}", diagnostics={"exception": str(exc)},
                )
                self._failed_exc = failure
                raise failure from exc
            self._started = True
            with self._diagnostics_lock:
                self._diagnostics["worker_started"] = True
                self._diagnostics["worker_pid"] = self._process.pid
            self._reader_thread = threading.Thread(
                target=self._reader_loop, name="vnstock-worker-reader", daemon=True,
            )
            self._reader_thread.start()
        # IMPORTANT: wait for readiness OUTSIDE _lifecycle_lock. A startup failure is reported
        # by the reader thread calling _fail(), which itself needs _lifecycle_lock -- holding it
        # here while blocked in .wait() would deadlock the reader thread against this one.
        if not self._ready_event.wait(timeout=self._startup_timeout):
            failure = VnstockWorkerStartupError(
                "WORKER_DID_NOT_BECOME_READY_WITHIN_TIMEOUT",
                diagnostics={"startup_timeout_seconds": self._startup_timeout},
            )
            self._fail(failure)
            raise failure
        if self._failed_exc is not None:
            raise self._failed_exc

    def _reader_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                    validate_envelope(message)
                except (json.JSONDecodeError, VnstockWorkerProtocolError) as exc:
                    failure = exc if isinstance(exc, VnstockWorkerProtocolError) else VnstockWorkerProtocolError(
                        f"WORKER_SENT_MALFORMED_JSON:{exc}", diagnostics={"raw_line": line[:500]},
                    )
                    self._fail(failure)
                    return
                self._dispatch(message)
                if message.get("type") == MSG_SHUTDOWN_ACK:
                    return
        finally:
            # Stream ended (EOF) -- if we were not already torn down deliberately and requests
            # were (or could still be) pending, this is an unexpected process exit.
            if self._failed_exc is None and not self._ready_event.is_set():
                self._fail(VnstockWorkerStartupError("WORKER_EXITED_BEFORE_BECOMING_READY"))
            elif self._failed_exc is None:
                exit_status = self._process.wait(timeout=5) if self._process else None
                self._fail(
                    VnstockWorkerProcessExitError(
                        f"WORKER_PROCESS_EXITED_UNEXPECTEDLY:exit_status={exit_status}",
                        diagnostics={"exit_status": exit_status},
                    )
                )

    def _dispatch(self, message: dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == MSG_READY:
            self._ready_event.set()
            return
        if msg_type == MSG_SHUTDOWN_ACK:
            return
        request_id = message.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            self._fail(
                VnstockWorkerProtocolError(
                    "WORKER_RESPONSE_MISSING_REQUEST_ID", diagnostics={"message": message},
                )
            )
            return
        with self._pending_lock:
            q = self._pending.pop(request_id, None)
        if q is None:
            # Unknown or duplicate request id -- the protocol invariant (exactly one response
            # per outstanding request) is broken; fail closed rather than silently drop it.
            self._fail(
                VnstockWorkerProtocolError(
                    f"WORKER_RESPONSE_UNKNOWN_OR_DUPLICATE_REQUEST_ID:{request_id}",
                    diagnostics={"message": message},
                )
            )
            return
        if msg_type == MSG_FETCH_RESULT:
            outcome = WorkerFetchOutcome(
                status=message["status"],
                data=(
                    _rows_to_dataframe(message.get("rows") or [], message.get("unit_scale"))
                    if message["status"] == "success" else None
                ),
                lineage=message.get("lineage") or [],
                errors=message.get("errors") or [],
                transient_failure=bool(message.get("transient_failure")),
                request_attempts=int(message.get("request_attempts") or 0),
                retry_count=int(message.get("retry_count") or 0),
                timeout_count=int(message.get("timeout_count") or 0),
                http_429_count=int(message.get("http_429_count") or 0),
                http_5xx_count=int(message.get("http_5xx_count") or 0),
                retry_after_seconds=float(message.get("retry_after_seconds") or 0.0),
            )
            q.put(("ok", outcome))
        elif msg_type == MSG_WORKER_ERROR:
            failure = VnstockWorkerAdapterError(
                f"WORKER_ADAPTER_FAILURE:{message.get('failure_class')}:{message.get('message')}",
                diagnostics={"traceback": message.get("traceback"), "failure_class": message.get("failure_class")},
            )
            q.put(("error", failure))
        elif msg_type == MSG_GOVERNOR_DIAGNOSTIC_RESULT:
            q.put(("ok", message.get("diagnostic") or {}))
        else:
            self._fail(
                VnstockWorkerProtocolError(
                    f"WORKER_SENT_UNKNOWN_MESSAGE_TYPE:{msg_type}", diagnostics={"message": message},
                )
            )

    def _fail(self, failure: VnstockWorkerFailure) -> None:
        with self._lifecycle_lock:
            if self._failed_exc is None:
                self._failed_exc = failure
                with self._diagnostics_lock:
                    self._diagnostics["worker_exit_status"] = failure.failure_class
                    if isinstance(failure, VnstockWorkerTimeoutError):
                        self._diagnostics["timeout_state"] = "TIMED_OUT"
        with self._pending_lock:
            stale = list(self._pending.items())
            self._pending.clear()
        for _request_id, q in stale:
            q.put(("error", failure))
        self._ready_event.set()
        if self._process is not None:
            try:
                self._process.kill()
            except Exception:  # noqa: BLE001 -- best-effort; never let cleanup mask the failure.
                pass

    def _send(self, message: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        line = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._send_lock:
            try:
                self._process.stdin.write(line + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                failure = VnstockWorkerProcessExitError(f"WORKER_STDIN_WRITE_FAILED:{exc}")
                self._fail(failure)
                raise failure from exc

    def _round_trip(self, message: dict[str, Any], *, timeout: float) -> Any:
        self._ensure_started()
        request_id = message["request_id"]
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = q
        self._send(message)
        try:
            kind, payload = q.get(timeout=timeout)
        except queue.Empty:
            failure = VnstockWorkerTimeoutError(
                f"WORKER_REQUEST_TIMED_OUT:request_id={request_id}:timeout={timeout}",
                diagnostics={"request_id": request_id, "timeout_seconds": timeout},
            )
            self._fail(failure)
            raise failure
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if kind == "error":
            raise payload
        return payload

    # -- public transport API (drop-in for vn_stock_pipeline.fetch_single_source) --------------

    def fetch(
        self, ticker: str, source: str, start: str, end: str,
        *, bypass_circuit_check: bool = False, purpose: str = PURPOSE_GAP_RECOVERY,
    ) -> WorkerFetchOutcome:
        """Same signature/return shape as ``vn_stock_pipeline.fetch_single_source`` -- a drop-in
        replacement wherever this repository's resolver code injects a ``fetch_single_source``
        callable. ``purpose`` is diagnostic only; it never changes which provider/window is
        fetched."""
        request_id = uuid.uuid4().hex
        message = build_fetch_request(
            request_id=request_id, session=self._session, ticker=ticker, provider=source,
            start=start, end=end, purpose=purpose, bypass_circuit_check=bypass_circuit_check,
        )
        with self._diagnostics_lock:
            self._diagnostics["request_count"] += 1
            self._diagnostics["provider_attempt_counts"][source] = (
                self._diagnostics["provider_attempt_counts"].get(source, 0) + 1
            )
        return self._round_trip(message, timeout=self._request_timeout)

    def fetch_many(self, requests) -> list[WorkerFetchOutcome]:
        """Sequential convenience wrapper -- production callers in this repository route
        concurrency/pacing through ``multi_source_exact_session_resolver._ProviderAwareMemoizingFetch``,
        which calls ``fetch`` (never this method) from its own bounded per-provider thread pool.
        This exists only so ``VnstockWorkerFetcher`` remains a fully interchangeable
        ``fetch_single_source``-shaped dependency for any caller that wants the simpler batch form."""
        return [self.fetch(ticker, source, start, end) for ticker, source, start, end in requests]

    def estimated_minimum_seconds_for(self, additional_requests: int) -> float:
        """Duck-typed replacement for ``VnstockRateGovernor.estimated_minimum_seconds_for`` --
        used only by ``_DailyRecoveryRuntimeGuard``'s pacing-floor forecast, never by dispatch.
        The real method is pure arithmetic over two fixed constants (steady-state seconds per
        request), not the governor's live window state, so this reproduces it exactly using the
        same constants the worker's own governor is constructed with -- no round trip needed and
        nothing is approximated."""
        if additional_requests <= 0:
            return 0.0
        return additional_requests * (RATE_WINDOW_SECONDS / DEFAULT_EFFECTIVE_RPM)

    def diagnostic(self) -> dict[str, Any]:
        """Duck-typed replacement for ``vnstock_rate_governor.VnstockRateGovernor.diagnostic()``.

        Queries the WORKER's own real, active rate governor for its true accounting -- this
        object never maintains a parent-side governor that would only pretend to gate a child
        process's requests (explicitly forbidden: "do not pretend parent in-memory governor
        governs a child process"). If the worker was never started (no secondary transport was
        needed this operation) or has already failed, returns a clearly-labeled empty/degraded
        diagnostic rather than raising -- diagnostics must never crash an otherwise-successful
        operation.
        """
        if not self._started or self._failed_exc is not None:
            return {
                "source": "VNSTOCK_WORKER_GOVERNOR_DIAGNOSTIC_UNAVAILABLE",
                "worker_started": self._started,
                "worker_failed": self._failed_exc.failure_class if self._failed_exc else None,
            }
        request_id = uuid.uuid4().hex
        message = build_governor_diagnostic_request(request_id=request_id)
        try:
            diagnostic = self._round_trip(message, timeout=self._request_timeout)
        except VnstockWorkerFailure as exc:
            return {"source": "VNSTOCK_WORKER_GOVERNOR_DIAGNOSTIC_UNAVAILABLE", "worker_failed": exc.failure_class}
        result = dict(diagnostic)
        result["source"] = "VNSTOCK_WORKER_REMOTE_GOVERNOR"
        return result

    def worker_diagnostics(self) -> dict[str, Any]:
        """Bounded operational diagnostics for this operation (task step 18) -- never includes
        secrets, owner-private information, or PID/timing as part of any deterministic research
        identity; purely an operability breadcrumb."""
        with self._diagnostics_lock:
            return dict(self._diagnostics)

    def shutdown(self) -> None:
        """Deterministic teardown. Always safe to call (including when the worker was never
        started, or already failed) and never raises -- callers invoke this from a ``finally``
        block and must not have a cleanup failure mask a real exception from the try body."""
        if not self._started:
            return
        with self._lifecycle_lock:
            process = self._process
        if process is None:
            return
        if self._failed_exc is None:
            try:
                request_id = uuid.uuid4().hex
                with self._send_lock:
                    if process.stdin is not None and not process.stdin.closed:
                        line = json.dumps(
                            build_shutdown_request(request_id=request_id),
                            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                        )
                        process.stdin.write(line + "\n")
                        process.stdin.flush()
            except Exception:  # noqa: BLE001 -- best-effort only.
                pass
        try:
            process.wait(timeout=self._shutdown_timeout)
        except Exception:  # noqa: BLE001 -- subprocess.TimeoutExpired or already-closed pipes.
            try:
                process.kill()
                process.wait(timeout=self._shutdown_timeout)
            except Exception:  # noqa: BLE001
                pass
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:  # noqa: BLE001
                    pass
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=self._shutdown_timeout)
