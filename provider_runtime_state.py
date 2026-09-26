"""Provider runtime isolation contract (PROVIDER_RUNTIME_ISOLATION_V1).

Standard-library only. Imported by the canonical Daily parent process, the technical-history
recovery runner and the worker client -- it must never import ``vnstock``/``vnai``/
``vn_stock_pipeline`` or anything that transitively does.

Two axes that must never be conflated
    * ``provider_runtime_state`` (THIS module) -- is the optional KBS/VCI provider runtime usable
      for this operation, and if not, the one observed reason. Operational metadata only: it
      never promotes, demotes or rewrites a market-data value.
    * DNSE quality license / market-evidence quality -- see
      ``multi_source_market_evidence_contract.dnse_quality_license``. ``DATA_QUALITY_FAILED``
      belongs there, never here.

Owner decisions implemented here (docs/DECISIONS.md, PROVIDER_RUNTIME_ISOLATION_V1)
    D1  The provider policy is explicit tracked configuration
        (``config/provider_runtime_policy.json``) controlled by the owner. The default -- and the
        fail-closed reading of a missing/invalid policy file -- is ``SECURITY_REVIEW_BLOCKED``. A
        blocked policy prevents the worker from ever being spawned; an already-installed package
        never bypasses it. Nothing here queries a package index or changes policy from network
        conditions.
    D3  The provider worker runs only under an explicitly configured provider interpreter
        (``STOCKLOOKUP_PROVIDER_PYTHON``). There is no fallback to the core/current interpreter:
        absent, missing or identical-to-core configuration is ``NOT_CONFIGURED``.

Credential isolation
    ``build_provider_environment`` constructs the worker environment from an explicit allow-list
    of operating-system variables plus exact, policy-approved provider variables. Credential
    families of other providers (``DNSE_*``, ``LIVESPEED_*``, ``FINHAY_*``) can never be forwarded,
    not even by explicit allow-listing, and generic secret-shaped names (``*TOKEN*``, ``*SECRET*``,
    ``*PASSWORD*``, ...) are forwarded only when exactly allow-listed by the policy.

APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1
    * Profile and temp names (``USERPROFILE``, ``HOME``, ``HOMEDRIVE``/``HOMEPATH``, ``APPDATA``,
      ``LOCALAPPDATA``, ``TEMP``/``TMP``/``TMPDIR``) are never inherited from the parent any more:
      forwarding them exposed the owner's ``%USERPROFILE%\\.vnstock\\api_key.json`` to vendor code
      (dossier finding N2). ``provider_build_manifest.build_isolated_worker_environment``
      constructs them from the worker-owned provider state/scratch roots instead.
    * An allowing policy is not enough to launch: it must also pin an approved build manifest
      (``approved_build_manifest`` path + canonical SHA-256, ``decision_id``), and the manifest,
      revocation registry, credential/rate binding and interpreter attestation must all pass
      (``provider_build_manifest.authorize_provider_launch``). Any refusal there is recorded as
      ``SECURITY_REVIEW_BLOCKED`` with the manifest/attestation reason code -- the runtime-state
      vocabulary stays exactly the twelve states below.

This is process and dependency isolation plus in-worker containment, not a security sandbox; see
``provider_worker_containment`` for what in-process controls can and cannot enforce.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent

CONTRACT_VERSION = "provider_runtime_state/v1"
POLICY_CONTRACT_VERSION = "provider_runtime_policy/v1"
PROVIDER_FAMILY_VNSTOCK_KBS_VCI = "VNSTOCK_KBS_VCI"
POLICY_PATH = ROOT / "config" / "provider_runtime_policy.json"
PROVIDER_PYTHON_ENV = "STOCKLOOKUP_PROVIDER_PYTHON"

# ---------------------------------------------------------------------------------------------
# Runtime-state vocabulary (exactly these twelve).
# ---------------------------------------------------------------------------------------------
AVAILABLE = "AVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"
SECURITY_REVIEW_BLOCKED = "SECURITY_REVIEW_BLOCKED"
NOT_INSTALLED = "NOT_INSTALLED"
IMPORT_FAILED = "IMPORT_FAILED"
STARTUP_FAILED = "STARTUP_FAILED"
STARTUP_TIMEOUT = "STARTUP_TIMEOUT"
PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"
PROCESS_CRASHED = "PROCESS_CRASHED"
AUTH_FAILED = "AUTH_FAILED"
RATE_LIMITED = "RATE_LIMITED"
UNAVAILABLE_CAUSE_UNKNOWN = "UNAVAILABLE_CAUSE_UNKNOWN"
RUNTIME_STATES = (
    AVAILABLE, NOT_CONFIGURED, SECURITY_REVIEW_BLOCKED, NOT_INSTALLED, IMPORT_FAILED,
    STARTUP_FAILED, STARTUP_TIMEOUT, PROTOCOL_VIOLATION, PROCESS_CRASHED, AUTH_FAILED,
    RATE_LIMITED, UNAVAILABLE_CAUSE_UNKNOWN,
)

PHASE_PREFLIGHT = "PREFLIGHT"
PHASE_OPERATION = "OPERATION"
PHASES = (PHASE_PREFLIGHT, PHASE_OPERATION)

# ---------------------------------------------------------------------------------------------
# Policy vocabulary.
# ---------------------------------------------------------------------------------------------
POLICY_SECURITY_REVIEW_BLOCKED = "SECURITY_REVIEW_BLOCKED"
POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME = "ALLOW_CONFIGURED_PROVIDER_RUNTIME"
POLICY_VALUES = (POLICY_SECURITY_REVIEW_BLOCKED, POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME)
DEFAULT_POLICY = POLICY_SECURITY_REVIEW_BLOCKED

# ---------------------------------------------------------------------------------------------
# Deterministic reason codes.
# ---------------------------------------------------------------------------------------------
REASON_READY_HANDSHAKE = "PROVIDER_RUNTIME_READY_HANDSHAKE"
REASON_NO_USABLE_FAILURE_OBSERVED = "PROVIDER_RUNTIME_NO_FAILURE_OBSERVED"
REASON_POLICY_SECURITY_REVIEW_BLOCKED = "PROVIDER_POLICY_SECURITY_REVIEW_BLOCKED"
REASON_POLICY_MISSING_OR_INVALID = "PROVIDER_POLICY_MISSING_OR_INVALID_FAIL_CLOSED"
REASON_INTERPRETER_UNSET = "PROVIDER_INTERPRETER_NOT_CONFIGURED"
REASON_INTERPRETER_NOT_FOUND = "PROVIDER_INTERPRETER_PATH_NOT_FOUND"
REASON_INTERPRETER_IS_CORE = "PROVIDER_INTERPRETER_IS_CORE_INTERPRETER"
REASON_PACKAGE_NOT_INSTALLED = "PROVIDER_PACKAGE_NOT_INSTALLED"
REASON_IMPORT_FAILED = "PROVIDER_IMPORT_FAILED"
REASON_SPAWN_FAILED = "PROVIDER_WORKER_SPAWN_FAILED"
REASON_EXITED_BEFORE_READY = "PROVIDER_WORKER_EXITED_BEFORE_READY"
REASON_STARTUP_EXCEPTION = "PROVIDER_WORKER_STARTUP_EXCEPTION"
REASON_STARTUP_TIMEOUT = "PROVIDER_WORKER_STARTUP_TIMEOUT"
REASON_PROTOCOL_VIOLATION = "PROVIDER_WORKER_PROTOCOL_VIOLATION"
REASON_PROCESS_EXIT = "PROVIDER_WORKER_PROCESS_EXITED"
REASON_REQUEST_TIMEOUT = "PROVIDER_WORKER_REQUEST_TIMEOUT"
REASON_REQUEST_PROCESSING_EXCEPTION = "PROVIDER_WORKER_REQUEST_PROCESSING_EXCEPTION"
REASON_AUTH_REJECTED = "PROVIDER_AUTH_REJECTED_NO_USABLE_RESPONSE"
REASON_RATE_LIMITED = "PROVIDER_RATE_LIMITED_NO_USABLE_RESPONSE"
REASON_UNCLASSIFIED_WORKER_FAILURE = "PROVIDER_WORKER_FAILURE_UNCLASSIFIED"
# APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 (all under SECURITY_REVIEW_BLOCKED except the
# initialisation failure, which is a STARTUP_FAILED of an attested, contained runtime).
REASON_WORKER_SELF_ATTESTATION_FAILED = "PROVIDER_WORKER_SELF_ATTESTATION_FAILED"
REASON_STARTUP_CONTAINMENT_VIOLATION = "PROVIDER_STARTUP_CONTAINMENT_VIOLATION"
REASON_CONTAINMENT_VIOLATION = "PROVIDER_CONTAINMENT_VIOLATION"
REASON_BUILD_REVOKED = "PROVIDER_BUILD_REVOKED"
REASON_INIT_FAILED_UNDER_CONTAINMENT = "PROVIDER_INIT_FAILED_UNDER_CONTAINMENT"

# Generic per-operation reason a recovery surface records when it was not attempted because the
# supplemental provider runtime was unavailable (residual-yield probe, gap recovery,
# technical-history recovery, DNSE quality sentinel).
SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE = "SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE"

# Worker startup-failure kinds (``vnstock_worker_protocol`` carries them; mapped below).
STARTUP_KIND_SPAWN_FAILED = "SPAWN_FAILED"
STARTUP_KIND_STARTUP_TIMEOUT = "STARTUP_TIMEOUT"
STARTUP_KIND_EXITED_BEFORE_READY = "EXITED_BEFORE_READY"
STARTUP_KIND_PACKAGE_NOT_INSTALLED = "PROVIDER_PACKAGE_NOT_INSTALLED"
STARTUP_KIND_IMPORT_FAILED = "PROVIDER_IMPORT_FAILED"
STARTUP_KIND_STARTUP_EXCEPTION = "WORKER_STARTUP_EXCEPTION"
STARTUP_KIND_ATTESTATION_FAILED = "PROVIDER_RUNTIME_ATTESTATION_FAILED"
STARTUP_KIND_CONTAINMENT_VIOLATION = "PROVIDER_STARTUP_CONTAINMENT_VIOLATION"
STARTUP_KIND_INIT_FAILED = "PROVIDER_INIT_FAILED_UNDER_CONTAINMENT"

_STARTUP_KIND_TO_STATE = {
    STARTUP_KIND_SPAWN_FAILED: (STARTUP_FAILED, REASON_SPAWN_FAILED),
    STARTUP_KIND_STARTUP_TIMEOUT: (STARTUP_TIMEOUT, REASON_STARTUP_TIMEOUT),
    STARTUP_KIND_EXITED_BEFORE_READY: (STARTUP_FAILED, REASON_EXITED_BEFORE_READY),
    STARTUP_KIND_PACKAGE_NOT_INSTALLED: (NOT_INSTALLED, REASON_PACKAGE_NOT_INSTALLED),
    STARTUP_KIND_IMPORT_FAILED: (IMPORT_FAILED, REASON_IMPORT_FAILED),
    STARTUP_KIND_STARTUP_EXCEPTION: (STARTUP_FAILED, REASON_STARTUP_EXCEPTION),
    STARTUP_KIND_ATTESTATION_FAILED: (SECURITY_REVIEW_BLOCKED, REASON_WORKER_SELF_ATTESTATION_FAILED),
    STARTUP_KIND_CONTAINMENT_VIOLATION: (SECURITY_REVIEW_BLOCKED, REASON_STARTUP_CONTAINMENT_VIOLATION),
    STARTUP_KIND_INIT_FAILED: (STARTUP_FAILED, REASON_INIT_FAILED_UNDER_CONTAINMENT),
}

# Must equal vnstock_worker_protocol.FAILURE_CLASS_* (kept literal: this module imports nothing
# from the worker stack; tests/test_provider_runtime_state.py pins the equality).
_FAILURE_CLASS_TO_STATE = {
    "WORKER_PROTOCOL_VIOLATION": (PROTOCOL_VIOLATION, REASON_PROTOCOL_VIOLATION),
    "WORKER_PROCESS_EXIT": (PROCESS_CRASHED, REASON_PROCESS_EXIT),
    "WORKER_TIMEOUT": (UNAVAILABLE_CAUSE_UNKNOWN, REASON_REQUEST_TIMEOUT),
    "WORKER_REQUEST_PROCESSING_EXCEPTION": (UNAVAILABLE_CAUSE_UNKNOWN, REASON_REQUEST_PROCESSING_EXCEPTION),
    "WORKER_CONTAINMENT_VIOLATION": (SECURITY_REVIEW_BLOCKED, REASON_CONTAINMENT_VIOLATION),
    "PROVIDER_BUILD_REVOKED": (SECURITY_REVIEW_BLOCKED, REASON_BUILD_REVOKED),
}
# Diagnostics a worker failure may carry into the runtime-state detail (bounded, never secrets).
_FAILURE_DETAIL_KEYS = ("attestation_failures", "containment_events", "revocation", "reason_code",
                        "provider_modules_loaded")


class ProviderRuntimeContractError(ValueError):
    """A caller violated this contract's own invariants (never a provider outcome)."""


class SupplementalProviderRuntimeUnavailable(RuntimeError):
    """Raised by a provider fetch surface that is not allowed/able to reach the provider runtime.

    Carries the JSON-safe runtime-state record so the catching surface can record the exact
    reason (never a fabricated provider-level ``empty``/``failed`` outcome).
    """

    def __init__(self, state_record: Mapping[str, Any]):
        self.state_record = dict(state_record)
        super().__init__(
            f"{SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE}:{self.state_record.get('state')}:"
            f"{self.state_record.get('reason_code')}"
        )


# ---------------------------------------------------------------------------------------------
# Policy.
# ---------------------------------------------------------------------------------------------

# Never forwardable, even when explicitly allow-listed: other providers' credential families.
DENIED_ENV_PREFIXES = ("DNSE_", "LIVESPEED_", "FINHAY_")
# Secret-shaped names: forwarded only when exactly allow-listed by the policy.
SECRET_ENV_MARKERS = (
    "TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "CREDENTIAL", "PRIVATE_KEY",
    "ACCESS_KEY", "COOKIE", "SIGNATURE", "AUTH",
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProviderPolicy:
    """Owner-controlled launch policy for one provider runtime family."""

    provider_family: str
    policy: str
    reason: str
    evidence_ref: str | None = None
    set_by: str | None = None
    set_at: str | None = None
    allowed_provider_env: tuple[str, ...] = field(default_factory=tuple)
    source: str = "EXPLICIT"
    load_reason_code: str | None = None
    # APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1: the approved build this policy pins. An
    # allowing policy without a pin can never launch (provider_build_manifest refuses it).
    approved_manifest_path: str | None = None
    approved_manifest_sha256: str | None = None
    decision_id: str | None = None

    def __post_init__(self) -> None:
        if self.policy not in POLICY_VALUES:
            raise ProviderRuntimeContractError(f"PROVIDER_POLICY_VALUE_UNKNOWN:{self.policy!r}")
        for name in self.allowed_provider_env:
            if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
                raise ProviderRuntimeContractError(f"PROVIDER_ENV_ALLOWLIST_NAME_INVALID:{name!r}")
            if name.upper().startswith(DENIED_ENV_PREFIXES):
                raise ProviderRuntimeContractError(f"PROVIDER_ENV_ALLOWLIST_DENIED_FAMILY:{name}")
        if self.approved_manifest_sha256 is not None and not _SHA256_RE.match(str(self.approved_manifest_sha256)):
            raise ProviderRuntimeContractError("PROVIDER_POLICY_MANIFEST_SHA256_INVALID")

    @property
    def allows_launch(self) -> bool:
        return self.policy == POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME

    def to_record(self) -> dict[str, Any]:
        return {
            "contract_version": POLICY_CONTRACT_VERSION,
            "provider_family": self.provider_family,
            "policy": self.policy,
            "reason": self.reason,
            "evidence_ref": self.evidence_ref,
            "set_by": self.set_by,
            "set_at": self.set_at,
            "allowed_provider_env": sorted(self.allowed_provider_env),
            "source": self.source,
            "load_reason_code": self.load_reason_code,
            "approved_build_manifest": (
                {"path": self.approved_manifest_path, "sha256": self.approved_manifest_sha256}
                if self.approved_manifest_path or self.approved_manifest_sha256 else None
            ),
            "decision_id": self.decision_id,
        }


def _fail_closed_policy(reason_code: str, detail: str) -> ProviderPolicy:
    return ProviderPolicy(
        provider_family=PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
        policy=POLICY_SECURITY_REVIEW_BLOCKED,
        reason=f"{reason_code}:{detail}",
        source="FAIL_CLOSED_DEFAULT",
        load_reason_code=reason_code,
    )


def load_provider_policy(
    path: Path | None = None, *, provider_family: str = PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
) -> ProviderPolicy:
    """Read the owner-controlled policy for ``provider_family``.

    Any missing, unreadable, malformed or unknown-valued policy reads as
    ``SECURITY_REVIEW_BLOCKED`` (fail closed). Never touches the network.
    """
    policy_path = Path(path) if path is not None else POLICY_PATH
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, f"unreadable:{type(exc).__name__}")
    if not isinstance(payload, Mapping) or payload.get("contract_version") != POLICY_CONTRACT_VERSION:
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, "contract_version")
    providers = payload.get("providers")
    entry = providers.get(provider_family) if isinstance(providers, Mapping) else None
    if not isinstance(entry, Mapping):
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, f"provider_family_absent:{provider_family}")
    allowed = entry.get("allowed_provider_env") or []
    if not isinstance(allowed, list):
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, "allowed_provider_env_not_a_list")
    pin = entry.get("approved_build_manifest")
    if pin is not None and not (isinstance(pin, Mapping) and isinstance(pin.get("path"), str)
                                and isinstance(pin.get("sha256"), str)):
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, "approved_build_manifest_shape")
    decision_id = entry.get("decision_id")
    if decision_id is not None and not isinstance(decision_id, str):
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, "decision_id_shape")
    try:
        return ProviderPolicy(
            provider_family=provider_family,
            policy=str(entry.get("policy")),
            reason=str(entry.get("reason") or ""),
            evidence_ref=entry.get("evidence_ref"),
            set_by=entry.get("set_by"),
            set_at=entry.get("set_at"),
            allowed_provider_env=tuple(allowed),
            source=f"TRACKED_POLICY_FILE:{policy_path.name}",
            approved_manifest_path=pin.get("path") if pin else None,
            approved_manifest_sha256=pin.get("sha256") if pin else None,
            decision_id=decision_id,
        )
    except ProviderRuntimeContractError as exc:
        return _fail_closed_policy(REASON_POLICY_MISSING_OR_INVALID, str(exc))


# ---------------------------------------------------------------------------------------------
# Runtime-state records.
# ---------------------------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def runtime_state_record(
    state: str,
    reason_code: str,
    *,
    phase: str = PHASE_PREFLIGHT,
    provider_family: str = PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
    policy: ProviderPolicy | None = None,
    interpreter_configured: bool | None = None,
    runtime_info: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic, JSON-safe runtime-state record.

    ``runtime_info`` (interpreter/package versions) is accepted only for ``AVAILABLE`` -- a
    runtime that never completed its readiness handshake has no reportable version.
    """
    if state not in RUNTIME_STATES:
        raise ProviderRuntimeContractError(f"PROVIDER_RUNTIME_STATE_UNKNOWN:{state!r}")
    if phase not in PHASES:
        raise ProviderRuntimeContractError(f"PROVIDER_RUNTIME_PHASE_UNKNOWN:{phase!r}")
    if runtime_info is not None and state != AVAILABLE:
        raise ProviderRuntimeContractError("PROVIDER_RUNTIME_INFO_WITHOUT_READY_HANDSHAKE")
    record = {
        "contract_version": CONTRACT_VERSION,
        "provider_family": provider_family,
        "state": state,
        "reason_code": reason_code,
        "phase": phase,
        "available": state == AVAILABLE,
        "policy": policy.policy if policy is not None else None,
        "policy_source": policy.source if policy is not None else None,
        "interpreter_configured": interpreter_configured,
        "runtime_info": dict(runtime_info) if runtime_info is not None else None,
        "detail": dict(detail) if detail else {},
        "authority_effect": "NONE_OPERATIONAL_METADATA_ONLY",
    }
    return _json_safe(record)


def policy_block_record(policy: ProviderPolicy) -> dict[str, Any]:
    reason = (
        policy.load_reason_code
        if policy.load_reason_code is not None else REASON_POLICY_SECURITY_REVIEW_BLOCKED
    )
    return runtime_state_record(
        SECURITY_REVIEW_BLOCKED, reason, policy=policy,
        detail={"policy_reason": policy.reason, "policy_evidence_ref": policy.evidence_ref},
    )


def resolve_provider_interpreter(
    environ: Mapping[str, str], *, core_executable: str, policy: ProviderPolicy | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(interpreter_path, None)`` or ``(None, NOT_CONFIGURED record)``.

    No fallback to ``core_executable``: an unset variable, a path that is not a file, or a path
    identical (after normalisation, symlinks not followed) to the core interpreter is refused.
    """
    raw = str(environ.get(PROVIDER_PYTHON_ENV) or "").strip()
    if not raw:
        return None, runtime_state_record(
            NOT_CONFIGURED, REASON_INTERPRETER_UNSET, policy=policy, interpreter_configured=False,
        )
    candidate = os.path.normcase(os.path.abspath(os.path.expanduser(raw)))
    if not os.path.isfile(candidate):
        return None, runtime_state_record(
            NOT_CONFIGURED, REASON_INTERPRETER_NOT_FOUND, policy=policy, interpreter_configured=True,
        )
    if candidate == os.path.normcase(os.path.abspath(core_executable)):
        return None, runtime_state_record(
            NOT_CONFIGURED, REASON_INTERPRETER_IS_CORE, policy=policy, interpreter_configured=True,
        )
    return candidate, None


def runtime_state_from_worker_failure(
    failure_class: str | None,
    diagnostics: Mapping[str, Any] | None,
    *,
    phase: str,
    policy: ProviderPolicy | None = None,
) -> dict[str, Any]:
    """Map a ``vnstock_worker_protocol.VnstockWorkerFailure`` (class + diagnostics) to a state."""
    diagnostics = diagnostics or {}
    if failure_class == "WORKER_STARTUP_FAILURE":
        kind = str(diagnostics.get("startup_failure_kind") or STARTUP_KIND_STARTUP_EXCEPTION)
        state, reason = _STARTUP_KIND_TO_STATE.get(kind, (STARTUP_FAILED, REASON_STARTUP_EXCEPTION))
        detail = {"startup_failure_kind": kind}
        if diagnostics.get("missing_packages"):
            detail["missing_packages"] = sorted(str(p) for p in diagnostics["missing_packages"])
        if diagnostics.get("exception_type"):
            detail["exception_type"] = str(diagnostics["exception_type"])
    else:
        state, reason = _FAILURE_CLASS_TO_STATE.get(
            str(failure_class), (UNAVAILABLE_CAUSE_UNKNOWN, REASON_UNCLASSIFIED_WORKER_FAILURE),
        )
        detail = {"failure_class": failure_class}
    for key in _FAILURE_DETAIL_KEYS:
        value = diagnostics.get(key)
        if value:
            detail[key] = value[:50] if isinstance(value, list) else value
    return runtime_state_record(state, reason, phase=phase, policy=policy, interpreter_configured=True, detail=detail)


_AUTH_ERROR_RE = re.compile(r":(401|403)$")


def empty_outcome_stats() -> dict[str, int]:
    return {"responses": 0, "usable_responses": 0, "http_429": 0, "auth_rejections": 0}


def record_outcome_stats(stats: dict[str, int], *, status: str, errors: list, http_429_count: int) -> None:
    """Accumulate the transport facts ``classify_observed_runtime`` needs (never data values)."""
    stats["responses"] += 1
    if status in ("success", "empty"):
        stats["usable_responses"] += 1
    stats["http_429"] += int(http_429_count or 0)
    if any(_AUTH_ERROR_RE.search(str(item)) for item in errors or []):
        stats["auth_rejections"] += 1


def classify_observed_runtime(
    preflight: Mapping[str, Any], stats: Mapping[str, int], *, policy: ProviderPolicy | None = None,
) -> dict[str, Any]:
    """Operation-phase state of a runtime that passed its readiness handshake.

    Only an explicit signal changes it: zero usable responses AND every/most responses carrying
    an explicit HTTP 401/403 -> ``AUTH_FAILED``; zero usable responses AND HTTP 429 observed ->
    ``RATE_LIMITED``. Otherwise the runtime stays ``AVAILABLE`` (a provider that answered is a
    working runtime, whatever the data says -- that is the evidence axis's concern).
    """
    if preflight.get("state") != AVAILABLE:
        return dict(preflight)
    responses = int(stats.get("responses", 0))
    usable = int(stats.get("usable_responses", 0))
    detail = {key: int(stats.get(key, 0)) for key in ("responses", "usable_responses", "http_429", "auth_rejections")}
    if responses and usable == 0 and int(stats.get("auth_rejections", 0)) * 2 >= responses:
        return runtime_state_record(AUTH_FAILED, REASON_AUTH_REJECTED, phase=PHASE_OPERATION, policy=policy,
                                    interpreter_configured=True, detail=detail)
    if responses and usable == 0 and int(stats.get("http_429", 0)) > 0:
        return runtime_state_record(RATE_LIMITED, REASON_RATE_LIMITED, phase=PHASE_OPERATION, policy=policy,
                                    interpreter_configured=True, detail=detail)
    return runtime_state_record(
        AVAILABLE, REASON_NO_USABLE_FAILURE_OBSERVED, phase=PHASE_OPERATION, policy=policy,
        interpreter_configured=True, runtime_info=preflight.get("runtime_info"), detail=detail,
    )


# ---------------------------------------------------------------------------------------------
# Environment construction.
# ---------------------------------------------------------------------------------------------

# Operating-system values a Python worker needs to run and reach HTTPS endpoints. Compared
# case-insensitively (Windows environment names are case-insensitive). Profile and temp names
# (USERPROFILE, HOME, HOMEDRIVE, HOMEPATH, APPDATA, LOCALAPPDATA, TEMP, TMP, TMPDIR) are NOT
# here: they are never inherited from the parent; the governed launch constructs them from the
# provider state/scratch roots (provider_build_manifest.build_isolated_worker_environment).
BASE_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "TZ",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
})
# Never inherited, whatever the allow-list says (they would point vendor code at the owner profile).
PROFILE_ENV_NAMES = frozenset({
    "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR",
})


def is_denied_family(name: str) -> bool:
    return name.upper().startswith(DENIED_ENV_PREFIXES)


def is_secret_shaped(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in SECRET_ENV_MARKERS)


def build_provider_environment(
    parent_env: Mapping[str, str],
    *,
    allowed_provider_env: tuple[str, ...] | list[str] = (),
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Explicit worker environment -- never a blind copy of ``parent_env``.

    * base operating-system variables (``BASE_ENV_ALLOWLIST``) from ``parent_env``;
    * exact provider variables named in ``allowed_provider_env`` (policy-approved) from
      ``parent_env``;
    * ``extra`` explicit values (e.g. a test fixture's control variable).
    A ``DNSE_*``/``LIVESPEED_*``/``FINHAY_*`` name is never forwarded from any source; a
    secret-shaped name is forwarded only when exactly listed in ``allowed_provider_env``.
    """
    allowed = {name.upper() for name in allowed_provider_env}
    for name in allowed:
        if is_denied_family(name):
            raise ProviderRuntimeContractError(f"PROVIDER_ENV_ALLOWLIST_DENIED_FAMILY:{name}")

    def _permitted(name: str) -> bool:
        upper = name.upper()
        if is_denied_family(upper) or upper in PROFILE_ENV_NAMES:
            return False
        if upper in allowed:
            return True
        if is_secret_shaped(upper):
            return False
        return upper in BASE_ENV_ALLOWLIST

    environment = {name: str(value) for name, value in parent_env.items() if _permitted(name)}
    for name, value in (extra or {}).items():
        upper = name.upper()
        if is_denied_family(upper) or (is_secret_shaped(upper) and upper not in allowed):
            raise ProviderRuntimeContractError(f"PROVIDER_ENV_EXTRA_DENIED:{name}")
        environment[name] = str(value)
    return environment


# Interpreter flags for the provider worker (see docs/CI_AND_DEPENDENCY_TIERS.md):
#   -s  no user site-packages;  -E  ignore PYTHON* variables (PYTHONPATH/PYTHONHOME/...);
#   -X utf8  replaces PYTHONUTF8/PYTHONIOENCODING, which -E would otherwise ignore;  -u unbuffered;
#   -B  never write bytecode (the worker writes nothing into its runtime or bundle).
# Not -I: isolated mode also drops the script directory from sys.path, which the worker needs
# to import its bundled protocol/adapter modules.
WORKER_INTERPRETER_FLAGS = ("-s", "-E", "-X", "utf8", "-u", "-B")
