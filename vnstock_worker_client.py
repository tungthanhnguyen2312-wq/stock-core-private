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

PROVIDER_RUNTIME_ISOLATION_V1 (owner decisions D1/D3): a fetcher can only be constructed with an
explicit ``provider_runtime_state.ProviderPolicy`` that allows launch and an explicitly supplied
provider interpreter -- there is no default to ``sys.executable``. The worker runs under that
interpreter with ``provider_runtime_state.WORKER_INTERPRETER_FLAGS`` and an explicitly constructed
environment (``provider_runtime_state.build_provider_environment``): DNSE/Livespeed/Finhay
credentials and other secret-shaped variables of the parent are never forwarded. Production
callers obtain a fetcher only through ``open_provider_runtime``, which applies the tracked owner
policy (``SECURITY_REVIEW_BLOCKED`` spawns nothing), resolves ``STOCKLOOKUP_PROVIDER_PYTHON``, and
runs the readiness handshake before any provider request.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import provider_runtime_state as runtime_contract

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
    STARTUP_KIND_EXITED_BEFORE_READY,
    STARTUP_KIND_SPAWN_FAILED,
    STARTUP_KIND_STARTUP_EXCEPTION,
    STARTUP_KIND_STARTUP_TIMEOUT,
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
        python_executable: str,
        policy: runtime_contract.ProviderPolicy,
        session: str | None = None,
        worker_script: Path | None = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
        shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        env: dict[str, str] | None = None,
        parent_environ: Mapping[str, str] | None = None,
        worker_cwd: Path | str | None = None,
    ):
        # D1: a blocked policy can never produce a spawnable fetcher (zero provider processes).
        if not isinstance(policy, runtime_contract.ProviderPolicy) or not policy.allows_launch:
            raise runtime_contract.ProviderRuntimeContractError("PROVIDER_POLICY_DOES_NOT_ALLOW_LAUNCH")
        # D3: the provider interpreter is always explicit -- never a silent sys.executable default.
        if not isinstance(python_executable, str) or not python_executable.strip():
            raise runtime_contract.ProviderRuntimeContractError("PROVIDER_INTERPRETER_REQUIRED")
        self._policy = policy
        self._session = session
        self._worker_script = worker_script or _WORKER_SCRIPT
        self._python_executable = python_executable
        # The environment the worker's allow-listed variables are read from (default: os.environ at
        # spawn time). ``env`` (below) holds explicit extra variables, e.g. a test fixture's control
        # switch; both pass the same credential deny-rules when the environment is built.
        self._parent_environ = parent_environ
        self._runtime_info: dict[str, Any] | None = None
        self._outcome_stats = runtime_contract.empty_outcome_stats()
        # Set by shutdown(): the worker's exit after a deliberate shutdown is not a failure.
        self._shutting_down = False
        self._request_timeout = request_timeout
        self._startup_timeout = startup_timeout
        self._shutdown_timeout = shutdown_timeout
        self._env = env
        # Deliberately NOT this repository's own working directory (or any git repository) by
        # default. vnai's first-real-use lazy telemetry initialization
        # (vnai.scope.profile.Inspector.analyze_git_info) shells out to several UNBOUNDED
        # (no `timeout=`) `git` subprocesses against the process's current working directory --
        # observed hanging for 60+ seconds via a watchdog thread stack dump against this
        # multi-worktree repository during this milestone's own live release probe. Launching
        # the worker from a neutral, non-repository directory makes `git rev-parse
        # --is-inside-work-tree` fail fast (~0.1s) and short-circuit the rest of that function,
        # entirely avoiding the hazard without touching vnai's own behavior/telemetry semantics.
        self._worker_cwd = Path(worker_cwd) if worker_cwd is not None else Path(tempfile.gettempdir())

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

                # Explicit construction -- never a blind copy of the parent environment.
                popen_env = runtime_contract.build_provider_environment(
                    self._parent_environ if self._parent_environ is not None else os.environ,
                    allowed_provider_env=self._policy.allowed_provider_env,
                    extra=self._env,
                )
                self._process = subprocess.Popen(
                    [self._python_executable, *runtime_contract.WORKER_INTERPRETER_FLAGS, str(self._worker_script)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", bufsize=1, env=popen_env,
                    cwd=str(self._worker_cwd),
                )
            except OSError as exc:
                failure = VnstockWorkerStartupError(
                    f"WORKER_PROCESS_SPAWN_FAILED:{exc}",
                    diagnostics={"exception": str(exc), "startup_failure_kind": STARTUP_KIND_SPAWN_FAILED},
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
                diagnostics={
                    "startup_timeout_seconds": self._startup_timeout,
                    "startup_failure_kind": STARTUP_KIND_STARTUP_TIMEOUT,
                },
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
                self._fail(VnstockWorkerStartupError(
                    "WORKER_EXITED_BEFORE_BECOMING_READY",
                    diagnostics={"startup_failure_kind": STARTUP_KIND_EXITED_BEFORE_READY},
                ))
            elif self._failed_exc is None and not self._shutting_down:
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
            runtime = message.get("runtime")
            self._runtime_info = dict(runtime) if isinstance(runtime, dict) else None
            self._ready_event.set()
            return
        if msg_type == MSG_SHUTDOWN_ACK:
            return
        request_id = message.get("request_id")
        if (
            msg_type == MSG_WORKER_ERROR and request_id is None and not self._ready_event.is_set()
            and message.get("failure_class") == "WORKER_STARTUP_FAILURE"
        ):
            # The worker's own typed startup report (provider package absent / import failed /
            # startup exception) -- a startup failure, never a protocol violation.
            self._fail(VnstockWorkerStartupError(
                f"WORKER_STARTUP_FAILURE:{message.get('startup_failure_kind')}:{message.get('message')}",
                diagnostics={
                    "startup_failure_kind": message.get("startup_failure_kind") or STARTUP_KIND_STARTUP_EXCEPTION,
                    "missing_packages": message.get("missing_packages") or [],
                    "exception_type": message.get("exception_type"),
                },
            ))
            return
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
            with self._diagnostics_lock:
                runtime_contract.record_outcome_stats(
                    self._outcome_stats, status=str(message.get("status")),
                    errors=message.get("errors") or [], http_429_count=int(message.get("http_429_count") or 0),
                )
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

    # -- readiness / runtime state --------------------------------------------------------------

    def start(self) -> None:
        """Spawn the worker and complete the readiness handshake now (pre-flight probe); raises
        the same ``VnstockWorkerFailure`` a first fetch would."""
        self._ensure_started()

    @property
    def failure(self) -> VnstockWorkerFailure | None:
        return self._failed_exc

    @property
    def runtime_info(self) -> dict[str, Any] | None:
        """Interpreter/package versions from the READY message (None before a successful start)."""
        return dict(self._runtime_info) if self._runtime_info is not None else None

    def outcome_stats(self) -> dict[str, int]:
        with self._diagnostics_lock:
            return dict(self._outcome_stats)

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
        self._shutting_down = True
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


# ---------------------------------------------------------------------------------------------
# Governed factory (PROVIDER_RUNTIME_ISOLATION_V1) -- the only production way to obtain a fetcher.
# ---------------------------------------------------------------------------------------------


@dataclass
class ProviderRuntimeHandle:
    """Pre-flight runtime state plus, only when ``AVAILABLE``, a started fetcher."""

    state: dict[str, Any]
    fetcher: VnstockWorkerFetcher | None
    policy: runtime_contract.ProviderPolicy
    _final_state: dict[str, Any] | None = None

    @property
    def available(self) -> bool:
        return self.fetcher is not None and self.state.get("state") == runtime_contract.AVAILABLE

    def unavailable_error(self) -> runtime_contract.SupplementalProviderRuntimeUnavailable:
        return runtime_contract.SupplementalProviderRuntimeUnavailable(self.state)

    def final_state(self) -> dict[str, Any]:
        """Operation-phase state: a mid-operation worker failure, an explicit auth/rate-limit
        signal, or the unchanged pre-flight state."""
        if self._final_state is not None:
            return dict(self._final_state)
        if self.fetcher is None:
            return dict(self.state)
        failure = self.fetcher.failure
        if failure is not None:
            return runtime_contract.runtime_state_from_worker_failure(
                failure.failure_class, failure.diagnostics,
                phase=runtime_contract.PHASE_OPERATION, policy=self.policy,
            )
        return runtime_contract.classify_observed_runtime(
            self.state, self.fetcher.outcome_stats(), policy=self.policy,
        )

    def shutdown(self) -> None:
        """Freeze the operation-phase state first, then tear the worker down."""
        if self.fetcher is not None:
            if self._final_state is None:
                self._final_state = self.final_state()
            self.fetcher.shutdown()


def open_provider_runtime(
    *,
    session: str | None = None,
    policy: runtime_contract.ProviderPolicy | None = None,
    environ: Mapping[str, str] | None = None,
    core_executable: str | None = None,
    worker_script: Path | None = None,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
    shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> ProviderRuntimeHandle:
    """Apply the owner policy, resolve the provider interpreter and run the readiness handshake.

    Order (each step fail-closed, none spawning anything before the policy allows it):
      1. ``SECURITY_REVIEW_BLOCKED`` policy (default; also any missing/invalid policy file)
         -> state ``SECURITY_REVIEW_BLOCKED``, zero processes started;
      2. ``STOCKLOOKUP_PROVIDER_PYTHON`` unset / not a file / identical to the core interpreter
         -> ``NOT_CONFIGURED``, zero processes started;
      3. spawn + READY handshake -> ``AVAILABLE`` (with reported versions) or the precise
         startup failure state (``NOT_INSTALLED``, ``IMPORT_FAILED``, ``STARTUP_FAILED``,
         ``STARTUP_TIMEOUT``, ``PROTOCOL_VIOLATION``, ``PROCESS_CRASHED``, ...).
    Never raises for an unavailable runtime; the caller decides what the state blocks.
    """
    import os

    policy = policy if policy is not None else runtime_contract.load_provider_policy()
    if not policy.allows_launch:
        return ProviderRuntimeHandle(runtime_contract.policy_block_record(policy), None, policy)
    parent_environ = environ if environ is not None else os.environ
    interpreter, not_configured = runtime_contract.resolve_provider_interpreter(
        parent_environ, core_executable=core_executable or sys.executable, policy=policy,
    )
    if interpreter is None:
        return ProviderRuntimeHandle(not_configured or {}, None, policy)
    fetcher = VnstockWorkerFetcher(
        python_executable=interpreter, policy=policy, session=session, worker_script=worker_script,
        request_timeout=request_timeout, startup_timeout=startup_timeout, shutdown_timeout=shutdown_timeout,
        env=extra_env, parent_environ=parent_environ,
    )
    try:
        fetcher.start()
    except VnstockWorkerFailure as exc:
        fetcher.shutdown()
        state = runtime_contract.runtime_state_from_worker_failure(
            exc.failure_class, exc.diagnostics, phase=runtime_contract.PHASE_PREFLIGHT, policy=policy,
        )
        return ProviderRuntimeHandle(state, None, policy)
    state = runtime_contract.runtime_state_record(
        runtime_contract.AVAILABLE, runtime_contract.REASON_READY_HANDSHAKE, policy=policy,
        interpreter_configured=True, runtime_info=fetcher.runtime_info or {},
    )
    return ProviderRuntimeHandle(state, fetcher, policy)
