"""Wire protocol between the canonical exact-session parent process and the bounded VNStock
worker subprocess (VNSTOCK_EXACT_SESSION_WORKER_ISOLATION_AND_SENTINEL_EQUIVALENCE_V1).

Newline-delimited JSON over stdio, standard-library only (``json``/``dataclasses``). This module
is imported by BOTH the parent process and the worker subprocess; it must never import
``vnstock``/``vnai`` or anything that transitively does (``vn_stock_pipeline``,
``vnstock_rate_governor`` are fine to import from the WORKER side, but this module itself stays
dependency-free so the parent can import it without any worker-side footprint).

The worker is transport, not authority: every field here is either a bounded execution fact
(what to fetch) or a typed transport/provider outcome (what happened). No field encodes source
ordering, fallback, quarancy, or conflict-resolution policy -- the parent keeps all of that
completely unchanged; see ``multi_source_exact_session_resolver.py``.

``purpose`` is diagnostic/execution context only (which of gap recovery, residual-yield probe,
quality corroboration, or degraded expansion asked for this fetch) -- the worker must never
branch on it to change source policy; it only ever calls the one qualified adapter
(``vn_stock_pipeline.fetch_single_source``) the same way regardless of ``purpose``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "vnstock_worker_protocol/1.0.0"

MSG_FETCH = "fetch"
MSG_FETCH_RESULT = "fetch_result"
MSG_WORKER_ERROR = "worker_error"
MSG_READY = "ready"
MSG_SHUTDOWN = "shutdown"
MSG_SHUTDOWN_ACK = "shutdown_ack"
# Round-trip query for the worker's OWN real vnstock_rate_governor.diagnostic() -- so the parent
# can embed honest, worker-sourced governor stats into its evidence artifact without ever
# maintaining a parent-side governor that pretends to gate a child process's requests.
MSG_GOVERNOR_DIAGNOSTIC = "governor_diagnostic"
MSG_GOVERNOR_DIAGNOSTIC_RESULT = "governor_diagnostic_result"

# Diagnostic-only purpose tags -- never a policy input to the worker.
PURPOSE_GAP_RECOVERY = "gap_recovery"
PURPOSE_RESIDUAL_YIELD_PROBE = "residual_yield_probe"
PURPOSE_QUALITY_CORROBORATION = "quality_corroboration"
PURPOSE_DEGRADED_EXPANSION = "degraded_expansion"

# Failure classes a worker_error message may carry -- distinct from any provider-level outcome
# status (EXACT_SESSION_OBSERVED / SESSION_MISSING / SOURCE_REJECTED / TRANSPORT_FAILED /
# MALFORMED). A worker/protocol failure must never be mistaken for one of those.
FAILURE_CLASS_STARTUP_FAILURE = "WORKER_STARTUP_FAILURE"
FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION = "WORKER_REQUEST_PROCESSING_EXCEPTION"
FAILURE_CLASS_PROTOCOL_VIOLATION = "WORKER_PROTOCOL_VIOLATION"
FAILURE_CLASS_TIMEOUT = "WORKER_TIMEOUT"
FAILURE_CLASS_PROCESS_EXIT = "WORKER_PROCESS_EXIT"


class VnstockWorkerFailure(RuntimeError):
    """Base class for every worker/protocol-level failure.

    Deliberately NEVER raised in place of, or caught and converted into, a provider-level
    outcome (SESSION_MISSING/SOURCE_REJECTED/TRANSPORT_FAILED/MALFORMED) -- a worker failure
    means the transport channel itself is broken, not that KBS/VCI answered anything. Per the
    milestone's own V1 policy this is never silently retried/restarted; it always propagates to
    the caller as an explicit exception.
    """

    def __init__(self, message: str, *, failure_class: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.failure_class = failure_class
        self.diagnostics = dict(diagnostics or {})


class VnstockWorkerStartupError(VnstockWorkerFailure):
    """The worker subprocess failed to start or become ready."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message, failure_class=FAILURE_CLASS_STARTUP_FAILURE, diagnostics=diagnostics)


class VnstockWorkerProtocolError(VnstockWorkerFailure):
    """Malformed message, unknown protocol version, or a duplicate/missing/unknown request id."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message, failure_class=FAILURE_CLASS_PROTOCOL_VIOLATION, diagnostics=diagnostics)


class VnstockWorkerTimeoutError(VnstockWorkerFailure):
    """The worker did not answer a request within the bounded timeout (hang)."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message, failure_class=FAILURE_CLASS_TIMEOUT, diagnostics=diagnostics)


class VnstockWorkerProcessExitError(VnstockWorkerFailure):
    """The worker process exited (cleanly or via SystemExit/crash) while requests were pending."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message, failure_class=FAILURE_CLASS_PROCESS_EXIT, diagnostics=diagnostics)


class VnstockWorkerAdapterError(VnstockWorkerFailure):
    """The worker ran the real adapter but it raised an exception processing one request."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(
            message, failure_class=FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION, diagnostics=diagnostics,
        )


@dataclass
class WorkerFetchOutcome:
    """Mirrors ``vn_stock_pipeline.FetchOutcome``'s field names/shape exactly, so
    ``multi_source_exact_session_resolver._classify_recovery_outcome`` (which only ever does
    attribute access -- ``.status``, ``.data``, ``.lineage``, ``.errors``, ``.transient_failure``)
    works completely unmodified regardless of whether the outcome came from a direct in-process
    call or a worker round-trip. Defined here (not imported from ``vn_stock_pipeline``) so the
    parent process never needs to import that module for the canonical exact-session path.

    ``data`` is a pandas DataFrame with the same columns/``attrs["unit_scale"]`` as today's
    direct-import ``FetchOutcome.data`` when ``status == "success"``, else ``None`` -- see
    ``vnstock_worker_client._rows_to_dataframe``.
    """

    status: str
    data: Any = None
    lineage: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    transient_failure: bool = False
    request_attempts: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    http_429_count: int = 0
    http_5xx_count: int = 0
    retry_after_seconds: float = 0.0


def build_fetch_request(
    *, request_id: str, session: str | None, ticker: str, provider: str, start: str, end: str,
    purpose: str, bypass_circuit_check: bool = False,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": MSG_FETCH,
        "request_id": request_id,
        "session": session,
        "ticker": ticker,
        "provider": provider,
        "start": start,
        "end": end,
        "purpose": purpose,
        "bypass_circuit_check": bool(bypass_circuit_check),
    }


def build_shutdown_request(*, request_id: str) -> dict[str, Any]:
    return {"protocol_version": PROTOCOL_VERSION, "type": MSG_SHUTDOWN, "request_id": request_id}


def build_governor_diagnostic_request(*, request_id: str) -> dict[str, Any]:
    return {"protocol_version": PROTOCOL_VERSION, "type": MSG_GOVERNOR_DIAGNOSTIC, "request_id": request_id}


def validate_envelope(message: Any) -> None:
    """Raise ``VnstockWorkerProtocolError`` if ``message`` is not a well-formed envelope.

    Checks only the version/shape invariants shared by every message type; caller-specific
    required fields (e.g. ``request_id`` correlation) are checked by the caller.
    """
    if not isinstance(message, dict):
        raise VnstockWorkerProtocolError(
            f"WORKER_MESSAGE_NOT_AN_OBJECT:{type(message).__name__}", diagnostics={"message": repr(message)[:500]},
        )
    version = message.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise VnstockWorkerProtocolError(
            f"WORKER_PROTOCOL_VERSION_MISMATCH:got={version!r}:expected={PROTOCOL_VERSION!r}",
            diagnostics={"message": message},
        )
    msg_type = message.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        raise VnstockWorkerProtocolError("WORKER_MESSAGE_MISSING_TYPE", diagnostics={"message": message})
