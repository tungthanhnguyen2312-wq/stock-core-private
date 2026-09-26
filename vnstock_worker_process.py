"""Bounded VNStock worker subprocess entrypoint.

VNSTOCK_EXACT_SESSION_WORKER_ISOLATION_AND_SENTINEL_EQUIVALENCE_V1. This process is TRANSPORT
ONLY: it knows how to call the existing, qualified ``vn_stock_pipeline.fetch_single_source``
adapter for KBS/VCI and how to gate those calls through the existing shared
``vnstock_rate_governor``. It owns zero source-ordering/fallback/quarantine/conflict-resolution
policy -- every request it receives already names the exact ``(ticker, provider, start, end)`` to
fetch; ``purpose`` is diagnostic context only and must never change which adapter call is made.

This is the ONLY place in the whole exact-session acquisition path that imports ``vnstock``/
``vnai`` (transitively, via ``vn_stock_pipeline``). It is launched by
``vnstock_worker_client.VnstockWorkerFetcher`` as a plain child process and speaks
newline-delimited JSON on stdin/stdout (``vnstock_worker_protocol``). stdout carries ONLY protocol
messages -- never banners, prints, or provider stdout; this process redirects its own real stdout
to a private fd and gives the adapter/dependencies a harmless replacement for the whole run.

APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 -- start-up order (each step fail-closed):
    1. reserve the protocol fd;
    2. self-attestation against the launch contract (``provider_build_manifest.self_attest_worker``):
       interpreter flags/prefix/hash/build, ``sys.path``, startup hooks, bundled sources, manifest
       digest, environment names, profile redirection, credential tier, working directory -- a
       direct launch under the core or any other interpreter stops HERE, before any provider
       discovery or import (``PROVIDER_RUNTIME_ATTESTATION_FAILED``);
   2b. under the Windows production backend: connect the launch's named-pipe egress gateway
       (``provider_egress_gateway``), verify its server process and egress-policy digest -- the
       worker's only network path (its OS identity has no direct egress);
    3. in-worker containment (``provider_worker_containment``): process/socket/filesystem audit
       hook, name-resolution tracking and the ``requests`` transport guard, all driven by the
       approved manifest -- installed BEFORE any provider code can run;
    4. worker attestation granted to ``provider_execution_guard`` (the guarded provider operations
       of this process and of ``vn_stock_pipeline`` now pass);
    5. provider discovery (distribution presence + origin inside the attested runtime);
    6. the rate governor, derived from the approved rate contract (never the free-tier default);
    7. import-cache stubs bound by the manifest, then provider initialisation (``vnai.setup()``)
       under containment -- vendor telemetry, profile reads, subprocesses and egress are refused
       and recorded; an initialisation exception fails closed with its exact type;
    8. the adapter import and its quote-transport boundary (``_install_bounded_http``), verified
       installed;
    9. start-up verdict: any UNEXPECTED containment denial (one the manifest's telemetry
       disposition does not name) fails closed (``PROVIDER_STARTUP_CONTAINMENT_VIOLATION``);
   10. READY, carrying versions, the attestation identity and a containment summary.
Each request is a further controlled boundary: an unapproved quote host/redirect or any new
unexpected denial answers ``WORKER_CONTAINMENT_VIOLATION`` and the parent fails the runtime.

Not a security sandbox (see ``provider_worker_containment``): OS-level controls remain required.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import traceback
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from vnstock_worker_protocol import (
    FAILURE_CLASS_CONTAINMENT_VIOLATION,
    FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION,
    FAILURE_CLASS_STARTUP_FAILURE,
    MSG_FETCH,
    MSG_FETCH_RESULT,
    MSG_GOVERNOR_DIAGNOSTIC,
    MSG_GOVERNOR_DIAGNOSTIC_RESULT,
    MSG_READY,
    MSG_SHUTDOWN,
    MSG_SHUTDOWN_ACK,
    MSG_WORKER_ERROR,
    PROTOCOL_VERSION,
    STARTUP_KIND_ATTESTATION_FAILED,
    STARTUP_KIND_CONTAINMENT_VIOLATION,
    STARTUP_KIND_IMPORT_FAILED,
    STARTUP_KIND_INIT_FAILED,
    STARTUP_KIND_PACKAGE_NOT_INSTALLED,
    STARTUP_KIND_STARTUP_EXCEPTION,
)

# Provider distributions this worker needs (config/provider_dependency_lock.json). Checked with
# importlib.util.find_spec only AFTER self-attestation and containment, so an absent runtime is
# reported as NOT_INSTALLED without executing any provider code, distinct from a failing one.
PROVIDER_DISTRIBUTIONS = ("vnstock", "vnai")

# Generous internal concurrency: the REAL throttle is the contract-derived rate governor, not this
# pool's size. The parent's own per-provider dispatch policy already bounds in-flight requests.
_WORKER_INTERNAL_POOL_SIZE = 8
_STDOUT_WRITE_LOCK = threading.Lock()
_MAX_REPORTED_EVENTS = 50
REASON_TRANSPORT_BOUNDARY_NOT_INSTALLED = "PROVIDER_TRANSPORT_BOUNDARY_NOT_INSTALLED"
REASON_DISTRIBUTION_ORIGIN_OUTSIDE_RUNTIME = "PROVIDER_DISTRIBUTION_ORIGIN_OUTSIDE_RUNTIME"


def _emit(message: dict[str, Any], *, real_stdout) -> None:
    line = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    with _STDOUT_WRITE_LOCK:
        real_stdout.write(line + "\n")
        real_stdout.flush()


def _dataframe_to_rows(df) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _provider_modules_loaded() -> list[str]:
    return sorted(name for name in sys.modules if name.split(".", 1)[0] in PROVIDER_DISTRIBUTIONS)


def _emit_containment_violation(request_id: Any, reason_code: str, message: str, events: list, *, real_stdout) -> None:
    _emit(
        {
            "protocol_version": PROTOCOL_VERSION, "type": MSG_WORKER_ERROR, "request_id": request_id,
            "failure_class": FAILURE_CLASS_CONTAINMENT_VIOLATION, "reason_code": reason_code,
            "message": message, "containment_events": events[:_MAX_REPORTED_EVENTS],
        },
        real_stdout=real_stdout,
    )


def _process_fetch(request: dict[str, Any], *, real_stdout, adapter, containment) -> None:
    import provider_execution_guard as guard
    import provider_worker_containment as worker_containment

    request_id = request.get("request_id")
    ticker = request.get("ticker")
    provider = request.get("provider")
    mark = containment.log.sequence
    try:
        guard.require_governed_provider_execution("vnstock_worker_process.fetch")
        # The adapter (and therefore pandas/numpy) was imported on the main thread before this
        # pool started serving requests -- never a first-time C-extension load from a pool thread.
        outcome = adapter.fetch_single_source(
            ticker, provider, request.get("start"), request.get("end"),
            bypass_circuit_check=bool(request.get("bypass_circuit_check", False)),
        )
        unexpected = containment.log.unexpected_after(mark)
        if unexpected:
            _emit_containment_violation(request_id, unexpected[0]["reason_code"],
                                        "unexpected containment denial during the request", unexpected,
                                        real_stdout=real_stdout)
            return
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
    except (guard.ProviderContainmentViolation, worker_containment.ProviderContainmentDenied) as exc:
        # An unapproved host/method/path/redirect on the quote transport, or a denied action on the
        # data path: never a provider-level outcome, never retried.
        _emit_containment_violation(request_id, getattr(exc, "reason_code", type(exc).__name__), f"{type(exc).__name__}:{exc}",
                                    containment.log.events(after=mark), real_stdout=real_stdout)
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


# Import-cache stubs, by module name. The manifest's worker.startup_stubs must name exactly these
# (provider_build_manifest.WORKER_STARTUP_STUBS); self-attestation refuses any drift.
def _vnstock_upgrade_stub(module_name: str) -> types.ModuleType:
    """``vnstock/__init__.py`` calls ``update_notice(verbose=False)`` at import, which shells out
    to ``pip list`` and fetches pypi.org/vnstocks.com (dossier: live under core Python). A
    cosmetic update nag with no bearing on KBS/VCI data: pre-seeding the import cache (never the
    installed package) makes it a no-op instead of a denied subprocess + denied egress."""
    stub = types.ModuleType(module_name)
    stub.update_notice = lambda verbose=False: None  # noqa: ARG005 -- must match the real signature
    stub.migrate_to_sponsor = lambda target_dir=".": None  # noqa: ARG005 -- imported, never called at import
    return stub


_STUB_FACTORIES = {"vnstock.core.utils.upgrade": _vnstock_upgrade_stub}


def _install_startup_stubs(contract: dict[str, Any]) -> list[str]:
    installed = []
    for item in (contract.get("worker") or {}).get("startup_stubs") or []:
        name = item["module"]
        if name not in sys.modules:
            sys.modules[name] = _STUB_FACTORIES[name](name)
            installed.append(name)
    return installed


def _initialize_provider_under_containment() -> None:
    """Run the provider's own start-up (``vnai.setup()``) with containment already active.

    vnai's lazy singleton initialisation (telemetry dispatch, device fingerprint, terms record,
    content fetch, periodic sync thread, git probe) otherwise runs on the first decorated vnstock
    call. Doing it here, on the main thread, keeps every side effect inside the start-up phase,
    where an unexpected one fails the launch before READY. The old ``subprocess.run``-only git
    short-circuit is gone: the audit hook refuses every process-creation route (``Popen`` too),
    and a refused spawn returns immediately, so the historical git hang cannot occur.
    """
    import provider_execution_guard as guard

    guard.require_governed_provider_execution("vnstock_worker_process.provider_initialization")
    import vnai

    vnai.setup()


def _missing_provider_distributions() -> list[str]:
    import importlib.util

    return [name for name in PROVIDER_DISTRIBUTIONS if importlib.util.find_spec(name) is None]


def _distribution_origin_failures(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Every provider package must resolve from the attested runtime's site directories -- never a
    user site, the core interpreter or the worker bundle (``find_spec`` executes no package code)."""
    import importlib.util

    import provider_build_manifest as build_manifest

    interpreter = contract.get("interpreter") or {}
    site_dirs = build_manifest._site_dirs(build_manifest.Path(interpreter.get("venv_root", ".")),
                                          interpreter.get("site_dirs") or [])
    failures = []
    for name in PROVIDER_DISTRIBUTIONS:
        spec = importlib.util.find_spec(name)
        origin = (spec.origin if spec and spec.origin not in (None, "namespace") else None) or \
            (list(spec.submodule_search_locations or [None])[0] if spec else None)
        if origin is None or not any(build_manifest._under(origin, site_dir) for site_dir in site_dirs):
            failures.append({"code": REASON_DISTRIBUTION_ORIGIN_OUTSIDE_RUNTIME, "name": name, "origin": origin})
    return failures


def _runtime_info() -> dict[str, Any]:
    """Interpreter and provider distribution versions -- reported only in the READY message,
    i.e. only after the provider runtime genuinely imported and initialised."""
    import platform
    from importlib import metadata

    versions: dict[str, str | None] = {}
    for name in PROVIDER_DISTRIBUTIONS:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "provider_distributions": versions,
    }


def _emit_startup_failure(kind: str, exc: BaseException | None, *, real_stdout, **extra: Any) -> None:
    message = {
        "protocol_version": PROTOCOL_VERSION,
        "type": MSG_WORKER_ERROR,
        "request_id": None,
        "failure_class": FAILURE_CLASS_STARTUP_FAILURE,
        "startup_failure_kind": kind,
        "message": f"{type(exc).__name__}:{exc}" if exc is not None else kind,
        "exception_type": type(exc).__name__ if exc is not None else None,
        "traceback": traceback.format_exc(limit=20) if exc is not None else None,
        "provider_modules_loaded": _provider_modules_loaded(),
    }
    message.update(extra)
    _emit(message, real_stdout=real_stdout)


def _connect_egress_gateway(contract: dict[str, Any]):
    """The launch's named-pipe egress gateway client, or ``None`` when the launch has none (the
    offline fake Gate B). The pipe name derives from the manifest template + launch id; the
    expected server process comes from the read-only binding the backend wrote before spawn."""
    gateway = (contract.get("network") or {}).get("egress_gateway") or {}
    if gateway.get("transport") != "WINDOWS_NAMED_PIPE":
        return None
    import provider_egress_gateway as egress_gateway

    roots = contract.get("roots") or {}
    binding = json.loads(Path(roots["scratch_root"], "gateway_binding.json").read_text(encoding="utf-8"))
    pipe_name = egress_gateway.ipc_endpoint_for(contract["launch_id"], gateway["ipc_endpoint"])
    if binding.get("launch_id") != contract["launch_id"] or binding.get("ipc_endpoint_instance") != pipe_name:
        raise egress_gateway.GatewayRefusal(egress_gateway.R_SERVER_IDENTITY_MISMATCH, egress_gateway.KIND_PROTOCOL)
    client = egress_gateway.NamedPipeGatewayClient(
        pipe_name=pipe_name, launch_id=contract["launch_id"],
        egress_policy_sha256=(contract.get("os_enforcement") or {}).get("expected_egress_policy_sha256"),
        expected_server_pid=int(binding["server_pid"]))
    client.connect()
    return client


def _gateway_forwarder(client):
    """``requests`` send replacement: the governed operation goes to the gateway, which performs it."""
    import provider_egress_gateway as egress_gateway

    def forward(prepared, **_kwargs):
        body = prepared.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        answer = client.request(method=str(prepared.method), url=str(prepared.url),
                                headers=list(prepared.headers.items()), body=body or None)
        return egress_gateway.answer_to_requests_response(answer, prepared)

    return forward


def main() -> int:
    # Reserve the real fd 1 for the protocol only; redirect Python-level sys.stdout so any
    # accidental print()/banner from the adapter or a dependency lands somewhere harmless
    # instead of corrupting the JSON-lines stream.
    real_stdout = os.fdopen(os.dup(1), "w", encoding="utf-8", closefd=True)
    devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = devnull

    # --- 2. self-attestation, before ANY provider discovery or import -------------------------
    try:
        import provider_build_manifest as build_manifest

        try:
            contract = build_manifest.read_launch_contract()
            failures = build_manifest.self_attest_worker(
                contract, protocol_version=PROTOCOL_VERSION, entrypoint_file=os.path.abspath(__file__),
            )
        except build_manifest.ProviderAttestationError as exc:
            contract, failures = None, exc.failures
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_STARTUP_EXCEPTION, exc, real_stdout=real_stdout)
        return 1
    if failures:
        _emit_startup_failure(STARTUP_KIND_ATTESTATION_FAILED, None, real_stdout=real_stdout,
                              attestation_failures=failures[:_MAX_REPORTED_EVENTS])
        return 1
    # Read from the OS before containment is installed; reported in READY so the parent can cross-
    # check the OS-enforcement backend's attestation against the worker's own view of itself.
    os_facts = build_manifest.observe_worker_os_facts()

    # --- 2b. egress gateway (production Windows backend): the worker's only network path --------
    # Connected before containment is installed and before any provider code exists: the pipe is
    # the trusted Producer's per-launch endpoint, verified by server process and policy digest.
    try:
        gateway_client = _connect_egress_gateway(contract)
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_ATTESTATION_FAILED, None, real_stdout=real_stdout, attestation_failures=[{
            "code": getattr(exc, "code", None) or "GATEWAY_UNAVAILABLE", "error": type(exc).__name__}])
        return 1

    # --- 3./4. containment, then the worker attestation for the execution guard ----------------
    try:
        import provider_execution_guard as guard
        import provider_worker_containment as worker_containment

        containment = worker_containment.install_worker_containment(
            build_manifest.worker_containment_from_contract(contract),
        )
        requests_guard = containment.install_requests_guard(
            forward=_gateway_forwarder(gateway_client) if gateway_client is not None else None)
        guard.grant_worker_attestation(guard.issue_worker_attestation(
            build_id=contract["build_id"], manifest_sha256=contract["manifest_sha256"],
            launch_id=contract["launch_id"], revocation_epoch=int(contract.get("revocation_epoch") or 0),
            checks=("LAUNCH_CONTRACT", "INTERPRETER", "SITE_ISOLATION", "WORKER_SOURCES", "MANIFEST_DIGEST",
                    "ENVIRONMENT", "PROFILE_REDIRECTION", "CREDENTIAL_TIER", "CONTAINMENT_INSTALLED"),
        ))
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_STARTUP_EXCEPTION, exc, real_stdout=real_stdout)
        return 1

    # --- 5. provider discovery ------------------------------------------------------------------
    try:
        guard.require_governed_provider_execution("vnstock_worker_process.provider_discovery")
        missing = _missing_provider_distributions()
        origin_failures = [] if missing else _distribution_origin_failures(contract)
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_STARTUP_EXCEPTION, exc, real_stdout=real_stdout)
        return 1
    if missing:
        _emit_startup_failure(
            STARTUP_KIND_PACKAGE_NOT_INSTALLED, None, real_stdout=real_stdout, missing_packages=missing,
        )
        return 1
    if origin_failures:
        _emit_startup_failure(STARTUP_KIND_ATTESTATION_FAILED, None, real_stdout=real_stdout,
                              attestation_failures=origin_failures)
        return 1

    # --- 6. governor from the approved rate contract ----------------------------------------------
    try:
        import vnstock_rate_governor as governor_module

        governor = governor_module.governor_from_rate_contract(contract["rate"])
        governor_module.set_active_governor(governor)
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_STARTUP_EXCEPTION, exc, real_stdout=real_stdout)
        return 1

    # --- 7. stubs + provider initialisation under containment -----------------------------------
    try:
        stubs = _install_startup_stubs(contract)
        _initialize_provider_under_containment()
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_INIT_FAILED, exc, real_stdout=real_stdout,
                              containment_events=containment.log.events()[:_MAX_REPORTED_EVENTS])
        return 1

    # --- 8. adapter + quote-transport boundary ------------------------------------------------
    try:
        # Imported here, on the MAIN thread, before the request pool exists: numpy's native
        # initialisation is not safe to trigger first from a pool thread (observed deadlock).
        adapter = importlib.import_module(contract["worker"]["adapter_module"])
        adapter._install_bounded_http()
        boundary_installed = bool(adapter.transport_boundary_installed())
        runtime = _runtime_info()
    except Exception as exc:  # noqa: BLE001
        _emit_startup_failure(STARTUP_KIND_IMPORT_FAILED, exc, real_stdout=real_stdout,
                              containment_events=containment.log.events()[:_MAX_REPORTED_EVENTS])
        return 1
    if not boundary_installed:
        _emit_startup_failure(STARTUP_KIND_CONTAINMENT_VIOLATION, None, real_stdout=real_stdout,
                              reason_code=REASON_TRANSPORT_BOUNDARY_NOT_INSTALLED)
        return 1

    # --- 9. start-up verdict ------------------------------------------------------------------
    unexpected = containment.log.unexpected_after(0)
    if unexpected:
        _emit_startup_failure(STARTUP_KIND_CONTAINMENT_VIOLATION, None, real_stdout=real_stdout,
                              reason_code=unexpected[0]["reason_code"],
                              containment_events=unexpected[:_MAX_REPORTED_EVENTS])
        return 1
    containment.set_phase(worker_containment.PHASE_OPERATION)
    runtime["attestation"] = guard.current_worker_attestation().to_record()
    runtime["os_facts"] = os_facts
    runtime["egress_gateway"] = dict(gateway_client.server) if gateway_client is not None else None
    runtime["containment"] = {"requests_guard": requests_guard, "startup_stubs": stubs,
                              "events": containment.log.summary()}
    runtime["rate_contract"] = {"governor_effective_rpm": governor.limit, "tier_minute_limit": governor.hard_ceiling,
                                "credential_tier": (contract.get("credential") or {}).get("expected_tier")}

    # --- 10. READY -------------------------------------------------------------------------------
    pool = ThreadPoolExecutor(max_workers=_WORKER_INTERNAL_POOL_SIZE, thread_name_prefix="vnstock-worker")
    _emit(
        {"protocol_version": PROTOCOL_VERSION, "type": MSG_READY, "request_id": None, "runtime": runtime},
        real_stdout=real_stdout,
    )

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
                pool.submit(_process_fetch, message, real_stdout=real_stdout, adapter=adapter, containment=containment)
            elif msg_type == MSG_GOVERNOR_DIAGNOSTIC:
                diagnostic = governor.diagnostic()
                diagnostic["containment_events"] = containment.log.summary()
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": MSG_GOVERNOR_DIAGNOSTIC_RESULT,
                        "request_id": message.get("request_id"),
                        "diagnostic": diagnostic,
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
