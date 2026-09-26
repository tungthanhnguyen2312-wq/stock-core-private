"""Shared provider execution guard (APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1).

Standard-library only. Imported by the provider adapter (``vn_stock_pipeline``), the worker
(``vnstock_worker_process``) and every legacy module that still names a provider API, so it must
never import ``vnstock``/``vnai``/``vn_stock_pipeline`` itself.

One mechanism replaces nineteen ad-hoc policies. Every function that can reach provider code calls
``require_governed_provider_execution(<operation id>)`` *before* its provider import. The operation
id is registered below with exactly one treatment:

``GOVERNED_WORKER_ONLY``
    Legitimate only inside the attested provider worker. It passes only when this process holds a
    worker attestation, which ``grant_worker_attestation`` accepts once, from the worker's own
    self-attestation (``provider_build_manifest.self_attest_worker``), after the launch contract,
    interpreter, site isolation, environment, bound worker sources and manifest digest were
    verified and the in-worker containment was installed. An environment variable, a path string
    or an installed package is never accepted as proof. Under the core interpreter it raises
    ``GovernedProviderExecutionRequired`` -- a ``SupplementalProviderRuntimeUnavailable``, so OHLC
    callers record an unavailable supplemental runtime instead of a fabricated provider outcome.

``UNSUPPORTED_LEGACY_PROVIDER_OPERATION``
    No governed worker operation exists yet. It always raises ``UnsupportedLegacyProviderOperation``
    with migration guidance -- inside or outside a worker -- until the path is explicitly wrapped
    behind ``vnstock_worker_client.open_provider_runtime``.

The guards are function-level on purpose: several of these modules also hold retained-data readers
with harmless importers (``financial_observations``, ``index_constituents_sync``, ``meta_sync``,
``provider_financial_source_metadata``), and those keep importing and working.

A guard is protection against accidental execution of unapproved provider bytes through normal or
legacy Stock Lookup paths, not a security sandbox; see ``provider_worker_containment``.
"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

import provider_runtime_state as runtime_contract

CONTRACT_VERSION = "provider_execution_guard/v1"

TREATMENT_GOVERNED_WORKER_ONLY = "GOVERNED_WORKER_ONLY"
TREATMENT_UNSUPPORTED_LEGACY = "UNSUPPORTED_LEGACY_PROVIDER_OPERATION"
TREATMENTS = (TREATMENT_GOVERNED_WORKER_ONLY, TREATMENT_UNSUPPORTED_LEGACY)

REASON_GOVERNED_WORKER_REQUIRED = "PROVIDER_EXECUTION_REQUIRES_ATTESTED_GOVERNED_WORKER"
REASON_UNSUPPORTED_LEGACY = "UNSUPPORTED_LEGACY_PROVIDER_OPERATION"
REASON_OPERATION_NOT_REGISTERED = "PROVIDER_OPERATION_NOT_REGISTERED"

_GOVERNED_GUIDANCE = (
    "This provider operation runs only inside the attested provider worker. Obtain a runtime through "
    "vnstock_worker_client.open_provider_runtime (tracked owner policy, approved build manifest, "
    "attested dedicated interpreter); ordinary Daily already does this through "
    "daily_session_level2_package. There is no core-interpreter fallback."
)
_UNSUPPORTED_GUIDANCE = (
    "This legacy provider path executed provider code under the core interpreter and is disabled "
    "until it is wrapped behind vnstock_worker_client.open_provider_runtime (owner-approved build "
    "manifest + attested worker). Retained-data readers in the same module stay available."
)


@dataclass(frozen=True)
class GuardedOperation:
    operation: str
    treatment: str
    boundary_file: str
    guidance: str

    def to_record(self) -> dict[str, Any]:
        return {
            "operation": self.operation, "treatment": self.treatment,
            "boundary_file": self.boundary_file, "guidance": self.guidance,
        }


def _governed(operation: str, boundary_file: str) -> GuardedOperation:
    return GuardedOperation(operation, TREATMENT_GOVERNED_WORKER_ONLY, boundary_file, _GOVERNED_GUIDANCE)


def _unsupported(operation: str, boundary_file: str, extra: str = "") -> GuardedOperation:
    guidance = _UNSUPPORTED_GUIDANCE + (f" {extra}" if extra else "")
    return GuardedOperation(operation, TREATMENT_UNSUPPORTED_LEGACY, boundary_file, guidance)


# The dossier's 19 import-bearing boundaries (claude-reports/provider-supply-chain-approval-dossier-
# v1-takeover-20260926/evidence/legacy-bypass-guard-map.json, re-verified on main 7ac6784), plus
# the operator entrypoints that reach them. multi_source_exact_session_resolver and
# tools/run_market_data_historical_series_failover.py have no guard entry: the resolver's implicit
# in-process fallback is removed and the tool routes through the governed worker client instead.
_OPERATIONS: tuple[GuardedOperation, ...] = (
    # vn_stock_pipeline -- the provider adapter, legitimate only inside the attested worker.
    _governed("vn_stock_pipeline._install_bounded_http", "vn_stock_pipeline.py"),
    _governed("vn_stock_pipeline._quote", "vn_stock_pipeline.py"),
    # vnstock_worker_process -- direct launch under a non-attested interpreter refuses before any
    # provider discovery or initialisation.
    _governed("vnstock_worker_process.provider_discovery", "vnstock_worker_process.py"),
    _governed("vnstock_worker_process.provider_initialization", "vnstock_worker_process.py"),
    _governed("vnstock_worker_process.fetch", "vnstock_worker_process.py"),
    # vn_stock_pipeline legacy CLI and universe refresh.
    _unsupported("vn_stock_pipeline.load_full_universe", "vn_stock_pipeline.py",
                 "The canonical universe is resolved from retained evidence, not a VCI listing call."),
    _unsupported("vn_stock_pipeline.cli.update", "vn_stock_pipeline.py",
                 "Use `stocklookup.ps1 daily` (canonical post-close Daily)."),
    _unsupported("vn_stock_pipeline.cli.backfill", "vn_stock_pipeline.py",
                 "Use `stocklookup.ps1 daily` (canonical post-close Daily)."),
    _unsupported("vn_stock_pipeline.cli.universe", "vn_stock_pipeline.py"),
    _unsupported("daily_analysis_pipeline.legacy_price_update", "daily_analysis_pipeline.py",
                 "Use --canonical-post-close (`stocklookup.ps1 daily`) or pass --skip-price-update."),
    _unsupported("operate_stocklookup.refresh_metadata", "tools/operate_stocklookup.py",
                 "Run without --refresh-metadata; the metadata refresh reaches meta_sync provider calls."),
    # The fifteen fail-fast legacy acquisition helpers.
    _unsupported("bctc_sync._finance", "bctc_sync.py"),
    _unsupported("blacklist_sync.scan_trading_status", "blacklist_sync.py"),
    _unsupported("company_profile_sync.fetch_current_payload", "company_profile_sync.py"),
    _unsupported("company_subsidiaries_sync.fetch_current_payload", "company_subsidiaries_sync.py"),
    _unsupported("corporate_events_sync.fetch_vci_events", "corporate_events_sync.py"),
    _unsupported("index_constituents_sync.fetch_current_payload", "index_constituents_sync.py"),
    _unsupported("instrument_master_sync.fetch_current_payload", "instrument_master_sync.py"),
    _unsupported("meta_sync.sync_exchange_industry", "meta_sync.py"),
    _unsupported("meta_sync.sync_foreign_room", "meta_sync.py"),
    _unsupported("meta_sync.sync_fundamentals", "meta_sync.py"),
    _unsupported("meta_sync.sync_ratio_only", "meta_sync.py"),
    _unsupported("ownership_structure_sync.fetch_current_payload", "ownership_structure_sync.py"),
    _unsupported("shareholders_sync._provider_payload", "shareholders_sync.py"),
    _unsupported("annual_provider_financial_recovery.acquire_annual_once", "annual_provider_financial_recovery.py"),
    _unsupported("missing_payload_reconciliation._default_fetcher", "missing_payload_reconciliation.py"),
    _unsupported("provider_financial_source_metadata.fetch_raw_once", "provider_financial_source_metadata.py"),
    _unsupported("provider_financial_source_metadata.adapter_dataframe_from_raw", "provider_financial_source_metadata.py",
                 "Even an offline parse imports vnstock and runs its import-time side effects."),
    _unsupported("vci_financial_statement_retention.fetch_statement", "vci_financial_statement_retention.py"),
    _unsupported("financial_observations.ingest_pilot", "financial_observations.py"),
)
OPERATIONS: Mapping[str, GuardedOperation] = {entry.operation: entry for entry in _OPERATIONS}
if len(OPERATIONS) != len(_OPERATIONS):  # pragma: no cover - a registration typo, caught at import
    raise RuntimeError("PROVIDER_EXECUTION_GUARD_DUPLICATE_OPERATION")


class ProviderExecutionGuardError(RuntimeError):
    """Base class of every provider execution-boundary refusal (guard, containment, transport).

    Callers that classify provider outcomes (``vn_stock_pipeline.fetch_single_source``) re-raise
    these unchanged: a boundary refusal is never a provider ``empty``/``failed`` answer.
    """

    reason_code = "PROVIDER_EXECUTION_BOUNDARY_REFUSED"


class UnsupportedLegacyProviderOperation(ProviderExecutionGuardError):
    reason_code = REASON_UNSUPPORTED_LEGACY

    def __init__(self, operation: str, guidance: str):
        self.operation = operation
        self.guidance = guidance
        super().__init__(f"{REASON_UNSUPPORTED_LEGACY}:{operation}: {guidance}")


class GovernedProviderExecutionRequired(ProviderExecutionGuardError,
                                        runtime_contract.SupplementalProviderRuntimeUnavailable):
    """Provider execution outside the attested worker.

    Also a ``SupplementalProviderRuntimeUnavailable``: an OHLC caller that already records an
    unavailable supplemental runtime (``historical_series_failover.vnstock_provider_series``, the
    technical-history recovery) keeps doing exactly that, with this reason code.
    """

    reason_code = REASON_GOVERNED_WORKER_REQUIRED

    def __init__(self, operation: str, guidance: str):
        self.operation = operation
        self.guidance = guidance
        runtime_contract.SupplementalProviderRuntimeUnavailable.__init__(
            self,
            runtime_contract.runtime_state_record(
                runtime_contract.NOT_CONFIGURED, REASON_GOVERNED_WORKER_REQUIRED,
                detail={"operation": operation},
            ),
        )
        self.args = (f"{REASON_GOVERNED_WORKER_REQUIRED}:{operation}: {guidance}",)

    def __str__(self) -> str:
        return str(self.args[0])


class ProviderContainmentViolation(ProviderExecutionGuardError):
    """A provider action outside the approved containment boundary (transport, process, filesystem).

    ``provider_worker_containment.TransportPolicyViolation`` derives from this.
    """

    reason_code = "PROVIDER_CONTAINMENT_VIOLATION"


# ---------------------------------------------------------------------------------------------
# Worker attestation (in-process, one-shot).
# ---------------------------------------------------------------------------------------------

_ISSUER = object()


@dataclass(frozen=True)
class WorkerAttestation:
    """Proof, inside one worker process, that its launch was self-attested.

    Only ``issue_worker_attestation`` creates one, and only when the interpreter-level
    preconditions of a governed worker hold (see there). JSON-safe via ``to_record``.
    """

    build_id: str
    manifest_sha256: str
    launch_id: str
    revocation_epoch: int
    checks: tuple[str, ...] = field(default_factory=tuple)
    _issuer: object = field(default=None, repr=False, compare=False)

    def to_record(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION, "build_id": self.build_id,
            "manifest_sha256": self.manifest_sha256, "launch_id": self.launch_id,
            "revocation_epoch": self.revocation_epoch, "checks": list(self.checks),
        }


_ATTESTATION: WorkerAttestation | None = None
_ATTESTATION_LOCK = threading.Lock()


def _interpreter_preconditions() -> list[str]:
    """Process-level facts every governed worker has and a core-interpreter process lacks."""
    problems = []
    if not sys.flags.no_user_site:
        problems.append("USER_SITE_NOT_DISABLED")
    if not sys.flags.ignore_environment:
        problems.append("PYTHON_ENVIRONMENT_NOT_IGNORED")
    if not sys.flags.dont_write_bytecode:
        problems.append("BYTECODE_WRITES_NOT_DISABLED")
    if sys.prefix == sys.base_prefix:
        problems.append("NOT_A_DEDICATED_VIRTUAL_ENVIRONMENT")
    import provider_worker_containment

    if not provider_worker_containment.containment_installed():
        problems.append("WORKER_CONTAINMENT_NOT_INSTALLED")
    return problems


def issue_worker_attestation(
    *, build_id: str, manifest_sha256: str, launch_id: str, revocation_epoch: int, checks: tuple[str, ...],
) -> WorkerAttestation:
    """Create the attestation after a successful self-attestation (``provider_build_manifest``).

    Refuses in any process that is not a governed worker: user site enabled, ``PYTHON*`` honoured,
    bytecode writes enabled, no dedicated virtual environment, or containment not installed.
    """
    problems = _interpreter_preconditions()
    if problems:
        raise ProviderExecutionGuardError(f"WORKER_ATTESTATION_PRECONDITIONS_FAILED:{','.join(problems)}")
    if not (isinstance(manifest_sha256, str) and len(manifest_sha256) == 64):
        raise ProviderExecutionGuardError("WORKER_ATTESTATION_MANIFEST_DIGEST_INVALID")
    return WorkerAttestation(
        build_id=str(build_id), manifest_sha256=manifest_sha256, launch_id=str(launch_id),
        revocation_epoch=int(revocation_epoch), checks=tuple(checks), _issuer=_ISSUER,
    )


def grant_worker_attestation(attestation: WorkerAttestation) -> None:
    """Install the worker attestation for this process. One-shot: a second grant is refused."""
    global _ATTESTATION
    if not isinstance(attestation, WorkerAttestation) or attestation._issuer is not _ISSUER:
        raise ProviderExecutionGuardError("WORKER_ATTESTATION_NOT_ISSUED_BY_SELF_ATTESTATION")
    with _ATTESTATION_LOCK:
        if _ATTESTATION is not None:
            raise ProviderExecutionGuardError("WORKER_ATTESTATION_ALREADY_GRANTED")
        _ATTESTATION = attestation


def current_worker_attestation() -> WorkerAttestation | None:
    with _ATTESTATION_LOCK:
        return _ATTESTATION


def operation(operation_id: str) -> GuardedOperation:
    entry = OPERATIONS.get(operation_id)
    if entry is None:
        raise ProviderExecutionGuardError(f"{REASON_OPERATION_NOT_REGISTERED}:{operation_id}")
    return entry


def require_governed_provider_execution(operation_id: str) -> WorkerAttestation:
    """Pass only for a ``GOVERNED_WORKER_ONLY`` operation inside an attested worker.

    Raises ``UnsupportedLegacyProviderOperation`` for an unsupported legacy path (always) and
    ``GovernedProviderExecutionRequired`` for a governed operation without a worker attestation.
    Call it before the provider import it protects.
    """
    entry = operation(operation_id)
    if entry.treatment == TREATMENT_UNSUPPORTED_LEGACY:
        raise UnsupportedLegacyProviderOperation(entry.operation, entry.guidance)
    attestation = current_worker_attestation()
    if attestation is None:
        raise GovernedProviderExecutionRequired(entry.operation, entry.guidance)
    return attestation


def legacy_operator_refusal(operation_id: str) -> str:
    """One-line operator refusal text for a CLI entrypoint (never executes the operation)."""
    entry = operation(operation_id)
    return f"{entry.treatment}:{entry.operation}: {entry.guidance}"


def registry_record() -> dict[str, Any]:
    """JSON-safe inventory of every guarded operation (for docs, tests and qualification Gate A)."""
    return {
        "contract_version": CONTRACT_VERSION,
        "operations": [OPERATIONS[name].to_record() for name in sorted(OPERATIONS)],
        "treatments": list(TREATMENTS),
    }
