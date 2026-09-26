"""OS-enforcement boundary for the provider worker (APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1).

The approved build manifest's ``os_containment`` block states *requirements*; it is never proof.
A worker process may only be spawned by a ``ProviderOSEnforcementBackend``, in three phases:

1. ``preflight(launch)`` -- the backend establishes/checks the OS controls it will apply;
2. ``spawn_contained(launch)`` -- the backend starts the worker under those controls;
3. ``verify_spawned_process(launch, process)`` -- the backend reads back what the OS actually
   applied to that process and returns a ``BackendVerification``: its raw observations plus the
   result it derived from them.

Trust is decided by *issuance*, not by the shape of a report. ``issue_attestation`` is the only
producer of a ``TrustedOSEnforcementAttestation``:

* it accepts a verification only from the backend this launch may use -- the configured production
  backend (``production_backend()``) for every live mode, the offline fake backend for the offline
  fake Gate B -- and only as a ``BackendVerification`` from that backend's own verification phase;
* it normalises the backend's result and validates every field against bindings derived from the
  launch and the approved manifest (``expected_enforcement_binding``): the manifest-bound backend
  id/contract, launch id, manifest digest, build, policy decision, worker PIDs and creation time,
  the restricted identity, the exact per-launch Job (limits, breakaway, assigned PIDs), the ACL
  policy (exact roots, access classes, identity), and the egress policy digest + gateway identity;
* worker self-observations (``provider_build_manifest.observe_worker_os_facts``) corroborate but
  never establish anything -- a worker in *some* Job proves nothing about *the* Job.

``evidence_sha256`` is a content identity of the raw observations, never a trust decision. The
launch layer (``vnstock_worker_client``) accepts only an issued attestation (``accept_attestation``).
This is not a cryptographic boundary against hostile in-process code; it stops the launch contract
from accepting declarative reports as OS proof.

**No production backend is implemented yet** (``production_backend()`` returns ``None``): the
Windows restricted identity + Job object + ACLs + OS egress gateway belong to the provisioning
milestone, so every live launch still fails closed with ``PROVIDER_OS_ENFORCEMENT_UNAVAILABLE``.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

import provider_build_manifest as build_manifest

ATTESTATION_CONTRACT_VERSION = "provider_os_enforcement_attestation/v2"
BACKEND_CONTRACT_VERSION = build_manifest.OS_ENFORCEMENT_BACKEND_CONTRACT_VERSION
BACKEND_PRODUCTION = build_manifest.OS_ENFORCEMENT_PRODUCTION
BACKEND_OFFLINE_FAKE = build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE
OFFLINE_FAKE_BACKEND_ID = build_manifest.OFFLINE_FAKE_BACKEND_ID

R_OS_ENFORCEMENT_UNAVAILABLE = build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
R_BACKEND_NOT_AUTHORIZED = "PROVIDER_OS_ENFORCEMENT_BACKEND_NOT_AUTHORIZED_FOR_MODE"
R_ATTESTATION_INVALID = "PROVIDER_OS_ENFORCEMENT_ATTESTATION_INVALID"
R_ATTESTATION_NOT_ISSUED = "PROVIDER_OS_ENFORCEMENT_ATTESTATION_NOT_ISSUED"

# Sources a production result may cite: facts read back from the OS about the spawned process.
OBSERVED_SOURCES = frozenset({"OS_TOKEN_QUERY", "OS_PROCESS_QUERY", "OS_JOB_QUERY", "OS_ACL_QUERY",
                              "OS_FIREWALL_QUERY", "OS_CGROUP_QUERY", "OS_NETNS_QUERY", "OS_SERVICE_QUERY"})
EGRESS_MECHANISMS = {
    "win32": frozenset({"WINDOWS_FILTERING_PLATFORM_DEFAULT_DENY"}),
    "linux": frozenset({"LINUX_NETNS_DEFAULT_DENY"}),
}
ACCESS_READ_EXECUTE = "READ_EXECUTE"
ACCESS_READ_WRITE = "READ_WRITE"
ACCESS_NONE = "NO_ACCESS"
# The only top-level keys a normalised attestation carries; anything else (for example the
# manifest's own declaration keys) is refused -- declarations are not evidence.
_RESULT_SECTIONS = ("binding", "worker_process", "restricted_identity", "process_control", "acl", "egress")
MAX_ATTESTATION_AGE = timedelta(minutes=10)
CLOCK_SKEW = timedelta(seconds=5)


class OSEnforcementUnavailable(RuntimeError):
    """No backend may spawn this launch. Carries a deterministic reason code; spawns nothing."""

    def __init__(self, reason_code: str, detail: Mapping[str, Any] | None = None):
        self.reason_code = reason_code
        self.detail = dict(detail or {})
        super().__init__(reason_code)


class OSEnforcementAttestationRejected(RuntimeError):
    """``issue_attestation`` refused: the backend's verification does not establish the launch's
    OS-enforcement requirement. ``failures`` never carry secret values."""

    def __init__(self, failures: list[dict[str, Any]]):
        self.failures = failures
        self.reason_code = failures[0]["code"] if failures else R_ATTESTATION_INVALID
        super().__init__(self.reason_code)


@dataclass(frozen=True)
class BackendVerification:
    """What a backend's verification phase returns: its identity, the raw OS observations it made
    (opaque evidence; hashed for identity only) and the result it derived from them."""

    backend_id: str
    contract_version: str
    raw_observations: Mapping[str, Any]
    result: Mapping[str, Any]
    verified_at_utc: str


class ProviderOSEnforcementBackend(Protocol):
    kind: str
    backend_id: str
    contract_version: str

    def preflight(self, launch: build_manifest.ProviderLaunchAuthorization) -> Mapping[str, Any]: ...

    def spawn_contained(self, launch: build_manifest.ProviderLaunchAuthorization) -> subprocess.Popen: ...

    def verify_spawned_process(self, launch: build_manifest.ProviderLaunchAuthorization,
                               process: subprocess.Popen) -> BackendVerification: ...


_ATTESTATION_ISSUER = object()


@dataclass(frozen=True)
class TrustedOSEnforcementAttestation:
    """An OS-enforcement attestation that ``issue_attestation`` validated for one exact launch.
    Constructing one directly (or passing a mapping) is never accepted by the launch layer."""

    launch_id: str
    manifest_sha256: str
    requirement: str
    backend_kind: str
    backend_id: str
    normalized: Mapping[str, Any]
    evidence_sha256: str
    _issuer: object = field(default=None, repr=False, compare=False)

    @property
    def issued_by_backend_verification(self) -> bool:
        return self._issuer is _ATTESTATION_ISSUER

    def to_record(self) -> dict[str, Any]:
        return {"launch_id": self.launch_id, "manifest_sha256": self.manifest_sha256, "requirement": self.requirement,
                "backend_kind": self.backend_kind, "backend_id": self.backend_id, "evidence_sha256": self.evidence_sha256,
                "authorizes_live_launch": self.requirement == BACKEND_PRODUCTION}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------
# Expected bindings (derived from the launch + approved manifest, never from a backend report).
# ---------------------------------------------------------------------------------------------


def acl_policy(launch: build_manifest.ProviderLaunchAuthorization) -> dict[str, Any]:
    """The exact roots and access classes the restricted identity must have for this launch."""
    runtime = launch.manifest.get("runtime") or {}
    roots = [
        {"path": str(runtime.get("venv_root")), "access_class": ACCESS_READ_EXECUTE},
        {"path": str(runtime.get("base_prefix")), "access_class": ACCESS_READ_EXECUTE},
        {"path": str(launch.bundle_root), "access_class": ACCESS_READ_EXECUTE},
        {"path": str(launch.state_root), "access_class": ACCESS_READ_WRITE},
        {"path": str(launch.scratch_root), "access_class": ACCESS_READ_WRITE},
    ]
    roots += [{"path": str(root), "access_class": ACCESS_NONE} for root in (launch.attestation or {}).get("denied_roots") or []]
    return {
        "contract_version": "provider_acl_policy/v1",
        "identity": (launch.manifest.get("os_containment") or {}).get("restricted_identity_sid"),
        "roots": sorted(roots, key=lambda item: (item["path"], item["access_class"])),
    }


def expected_enforcement_binding(launch: build_manifest.ProviderLaunchAuthorization) -> dict[str, Any]:
    manifest = launch.manifest
    containment = manifest.get("os_containment") or {}
    backend = containment.get("enforcement_backend") or {}
    policy = acl_policy(launch)
    return {
        "backend_id": backend.get("backend_id"),
        "backend_contract_version": backend.get("contract_version"),
        "launch_id": launch.launch_id,
        "manifest_sha256": launch.manifest_sha256,
        "build_id": manifest.get("build_id"),
        "policy_decision_id": launch.policy.decision_id,
        "platform": sys.platform,
        "issued_at_utc": (launch.attestation or {}).get("issued_at_utc"),
        "restricted_identity": containment.get("restricted_identity_sid"),
        "process_control_mechanism": containment.get("process_control_mechanism"),
        "job_name": build_manifest.expected_job_name(launch.launch_id),
        "job_active_process_limit": containment.get("job_active_process_limit"),
        "cgroup_path": build_manifest.expected_cgroup_path(launch.launch_id),
        "acl_policy": policy,
        "acl_policy_sha256": build_manifest.canonical_sha256(policy),
        "egress_policy_sha256": build_manifest.egress_policy_sha256(manifest),
        "telemetry_policy_sha256": build_manifest.telemetry_policy_sha256(manifest),
        "gateway": dict((manifest.get("network") or {}).get("egress_gateway") or {}),
    }


# ---------------------------------------------------------------------------------------------
# Backends.
# ---------------------------------------------------------------------------------------------


class OfflineFakeDirectPopenBackend:
    """Plain ``subprocess.Popen`` for the offline fake Gate B only. Enforces nothing at OS level
    and says so; refuses every launch that is not offline-fake eligible."""

    kind = BACKEND_OFFLINE_FAKE
    backend_id = OFFLINE_FAKE_BACKEND_ID
    contract_version = BACKEND_CONTRACT_VERSION

    def preflight(self, launch: build_manifest.ProviderLaunchAuthorization) -> Mapping[str, Any]:
        if not isinstance(launch, build_manifest.ProviderLaunchAuthorization) or not launch.issued_by_attestation:
            raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {"error": "launch not issued by attestation"})
        if launch.os_enforcement_requirement != BACKEND_OFFLINE_FAKE or not build_manifest.offline_fake_launch_eligible(
                launch.manifest, launch.launch_mode):
            raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {
                "backend": self.backend_id, "launch_mode": launch.launch_mode,
                "error": "plain Popen is reserved for the offline fake Gate B"})
        return {"backend_id": self.backend_id, "launch_id": launch.launch_id}

    def spawn_contained(self, launch: build_manifest.ProviderLaunchAuthorization) -> subprocess.Popen:
        self.preflight(launch)  # re-checked here: no caller can reach Popen around it
        # The launch's environment was constructed from the manifest: allow-listed OS names, the
        # approved credential (if any), and profile/temp names redirected into the provider
        # state/scratch roots -- never a copy of the parent's environment.
        return subprocess.Popen(
            list(launch.argv),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, env=dict(launch.environment), cwd=str(launch.cwd),
        )

    def verify_spawned_process(self, launch: build_manifest.ProviderLaunchAuthorization,
                               process: subprocess.Popen) -> BackendVerification:
        self.preflight(launch)
        not_enforced = {"source": "NOT_ENFORCED_OFFLINE_FAKE"}
        result = {
            "binding": {"launch_id": launch.launch_id, "manifest_sha256": launch.manifest_sha256,
                        "build_id": launch.manifest.get("build_id"), "policy_decision_id": launch.policy.decision_id,
                        "platform": sys.platform},
            "worker_process": {"spawned_pid": int(process.pid), "interpreter_pid": None, "creation_time_utc": None},
            "restricted_identity": dict(not_enforced, value=None),
            "process_control": dict(not_enforced, mechanism="NONE_OFFLINE_FAKE"),
            "acl": dict(not_enforced, policy_sha256=None, roots=[]),
            "egress": dict(not_enforced, mechanism="PYTHON_ALLOWLIST_ONLY_OFFLINE_FAKE", policy_sha256=None),
        }
        return BackendVerification(backend_id=self.backend_id, contract_version=self.contract_version,
                                   raw_observations={"popen_pid": int(process.pid)}, result=result,
                                   verified_at_utc=_utc(_now()))


def production_backend() -> ProviderOSEnforcementBackend | None:
    """The production OS-enforcement backend for this host, or ``None``.

    Not implemented in this milestone: provisioning a restricted identity, the per-launch Job object
    (or cgroup), ACLs and the OS egress gateway is the next (owner-authorized) provisioning milestone.
    Returning ``None`` keeps every live launch mode fail-closed."""
    return None


def backend_for_launch(launch: build_manifest.ProviderLaunchAuthorization) -> ProviderOSEnforcementBackend:
    """The only way to obtain something that can spawn a provider worker."""
    if not isinstance(launch, build_manifest.ProviderLaunchAuthorization) or not launch.issued_by_attestation:
        raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {"error": "launch not issued by attestation"})
    # Recomputed from the attested manifest + mode, never taken from the launch field alone.
    requirement = build_manifest.os_enforcement_requirement(launch.manifest, launch.launch_mode)
    if requirement != launch.os_enforcement_requirement:
        raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {"error": "launch requirement drift"})
    if requirement == BACKEND_OFFLINE_FAKE:
        return OfflineFakeDirectPopenBackend()
    backend = production_backend()
    if backend is None or getattr(backend, "kind", None) != BACKEND_PRODUCTION:
        raise OSEnforcementUnavailable(R_OS_ENFORCEMENT_UNAVAILABLE, {"launch_mode": launch.launch_mode})
    return backend


# ---------------------------------------------------------------------------------------------
# Validation of a backend result against the expected binding.
# ---------------------------------------------------------------------------------------------


def _fail(field_name: str, error: str, code: str = R_ATTESTATION_INVALID) -> dict[str, Any]:
    return {"code": code, "field": field_name, "error": error}


def _observed(section: Any) -> bool:
    return isinstance(section, Mapping) and section.get("source") in OBSERVED_SOURCES


def _pid_relation_ok(spawned_pid: Any, interpreter_pid: Any, facts: Mapping[str, Any], platform: str) -> bool:
    """The worker's own PID is the spawned PID, or (Windows venv redirector) its child."""
    if facts.get("pid") != interpreter_pid:
        return False
    return interpreter_pid == spawned_pid or (platform == "win32" and facts.get("ppid") == spawned_pid)


def process_control_violations(section: Any, expected: Mapping[str, Any], *, platform: str,
                               spawned_pid: Any, interpreter_pid: Any) -> list[dict[str, Any]]:
    """The exact per-launch process-lifetime control. A mechanism name plus ``verified=true`` is
    never enough; inherited membership in some other Job never satisfies it."""
    failures = []
    if not _observed(section):
        return [_fail("process_control", "missing or not read back from the OS")]
    mechanism = build_manifest.PROCESS_CONTROL_BY_PLATFORM.get(platform)
    if section.get("mechanism") != mechanism or section.get("mechanism") != expected.get("process_control_mechanism"):
        failures.append(_fail("process_control.mechanism", f"not the {platform} process-lifetime control"))
    if platform == "win32":
        job = section.get("job") if isinstance(section.get("job"), Mapping) else {}
        if not job or job.get("name") != expected.get("job_name"):
            failures.append(_fail("process_control.job.name", "not the Job created for this launch"))
        if job.get("membership_verified_with_job_handle") is not True:
            failures.append(_fail("process_control.job.membership_verified_with_job_handle",
                                  "membership not verified against the launcher's own Job handle"))
        assigned = set(job.get("assigned_pids") or [])
        if not {spawned_pid, interpreter_pid} <= assigned:
            failures.append(_fail("process_control.job.assigned_pids", "worker processes are not assigned to the Job"))
        limits = job.get("limits") if isinstance(job.get("limits"), Mapping) else {}
        if limits.get("kill_on_job_close") is not True:
            failures.append(_fail("process_control.job.limits.kill_on_job_close", "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE not active"))
        if limits.get("breakaway_ok") is not False:
            failures.append(_fail("process_control.job.limits.breakaway_ok", "breakaway must be prohibited"))
        if limits.get("silent_breakaway_ok") is not False:
            failures.append(_fail("process_control.job.limits.silent_breakaway_ok", "silent breakaway must be prohibited"))
        if limits.get("active_process_limit") != expected.get("job_active_process_limit") \
                or not isinstance(limits.get("active_process_limit"), int):
            failures.append(_fail("process_control.job.limits.active_process_limit", "not the approved active-process limit"))
    elif platform == "linux":
        cgroup = section.get("cgroup") if isinstance(section.get("cgroup"), Mapping) else {}
        if not cgroup or cgroup.get("path") != expected.get("cgroup_path"):
            failures.append(_fail("process_control.cgroup.path", "not the cgroup created for this launch"))
        if not {spawned_pid, interpreter_pid} <= set(cgroup.get("member_pids") or []):
            failures.append(_fail("process_control.cgroup.member_pids", "worker processes are not in the cgroup"))
        if cgroup.get("kill_on_close") is not True:
            failures.append(_fail("process_control.cgroup.kill_on_close", "cgroup kill on close not active"))
    else:
        failures.append(_fail("process_control", f"no reviewed process-lifetime control for {platform}"))
    return failures


def acl_violations(section: Any, expected: Mapping[str, Any]) -> list[dict[str, Any]]:
    """ACL enforcement bound to the exact roots, access classes and restricted identity."""
    if not _observed(section):
        return [_fail("acl", "missing or not read back from the OS")]
    failures = []
    policy = expected.get("acl_policy") or {}
    if section.get("identity") != policy.get("identity") or not policy.get("identity"):
        failures.append(_fail("acl.identity", "ACLs not evaluated for the restricted worker identity"))
    if section.get("policy_sha256") != expected.get("acl_policy_sha256"):
        failures.append(_fail("acl.policy_sha256", "not the ACL policy of this launch"))
    observed = {(item.get("path"), item.get("access_class")): item for item in section.get("roots") or []
                if isinstance(item, Mapping)}
    wanted = {(item["path"], item["access_class"]) for item in policy.get("roots") or []}
    if set(observed) != wanted:
        failures.append(_fail("acl.roots", "effective access not evaluated for exactly the policy roots"))
    if any(item.get("effective_access_verified") is not True for item in observed.values()):
        failures.append(_fail("acl.roots.effective_access_verified", "effective access not verified for every root"))
    return failures


def egress_violations(section: Any, expected: Mapping[str, Any], *, platform: str) -> list[dict[str, Any]]:
    """OS egress enforcement of the exact approved egress policy through the exact gateway."""
    if not _observed(section):
        return [_fail("egress", "missing OS egress-enforcement attestation (a gateway address alone is not enforcement)")]
    failures = []
    if section.get("mechanism") not in EGRESS_MECHANISMS.get(platform, frozenset()):
        failures.append(_fail("egress.mechanism", "not an OS egress-enforcement mechanism for this platform"))
    if section.get("policy_sha256") != expected.get("egress_policy_sha256") or not expected.get("egress_policy_sha256"):
        failures.append(_fail("egress.policy_sha256", "not the approved egress policy identity"))
    if section.get("telemetry_policy_sha256") != expected.get("telemetry_policy_sha256"):
        failures.append(_fail("egress.telemetry_policy_sha256", "not the approved telemetry (DENY) policy"))
    if section.get("direct_egress_prohibited_verified") is not True:
        failures.append(_fail("egress.direct_egress_prohibited_verified", "direct egress around the gateway not proven prohibited"))
    gateway = section.get("gateway") if isinstance(section.get("gateway"), Mapping) else {}
    wanted = expected.get("gateway") or {}
    for key in ("gateway_id", "implementation", "ipc_endpoint", "executable_sha256", "host", "port"):
        if not wanted.get(key) or gateway.get(key) != wanted.get(key):
            failures.append(_fail(f"egress.gateway.{key}", "gateway identity differs from the approved gateway"))
    if gateway.get("identity_verified") is not True:
        failures.append(_fail("egress.gateway.identity_verified", "the process behind the gateway endpoint is not verified"))
    return failures


def attestation_contract_violations(
    normalized: Mapping[str, Any], expected: Mapping[str, Any], *, requirement: str, spawned_pid: int,
    worker_facts: Mapping[str, Any] | None, now: datetime | None = None, platform: str = sys.platform,
) -> list[dict[str, Any]]:
    """Every reason a normalised backend result does not establish the requirement. Empty = valid."""
    failures: list[dict[str, Any]] = []
    facts = worker_facts if isinstance(worker_facts, Mapping) else {}
    current = now or _now()
    backend = normalized.get("backend") or {}
    extra = set(normalized) - {"contract_version", "backend", "verified_at_utc", "evidence_sha256", *_RESULT_SECTIONS}
    if extra:
        failures.append(_fail("attestation", f"unexpected keys {sorted(extra)}; declarations are not evidence"))
    binding = normalized.get("binding") if isinstance(normalized.get("binding"), Mapping) else {}
    for key in ("launch_id", "manifest_sha256", "build_id", "policy_decision_id", "platform"):
        if not expected.get(key) or binding.get(key) != expected.get(key):
            failures.append(_fail(f"binding.{key}", "does not bind this exact launch"))
    worker = normalized.get("worker_process") if isinstance(normalized.get("worker_process"), Mapping) else {}
    if worker.get("spawned_pid") != spawned_pid:
        failures.append(_fail("worker_process.spawned_pid", "not the process this launch spawned"))
    verified_at = build_manifest._parse_utc(normalized.get("verified_at_utc"))
    if verified_at is None or verified_at > current + CLOCK_SKEW or current - verified_at > MAX_ATTESTATION_AGE:
        failures.append(_fail("verified_at_utc", "missing, future or stale"))

    if requirement == BACKEND_OFFLINE_FAKE:
        if backend.get("kind") != BACKEND_OFFLINE_FAKE or backend.get("backend_id") != OFFLINE_FAKE_BACKEND_ID:
            failures.append(_fail("backend", "offline fake launch verified by another backend", R_BACKEND_NOT_AUTHORIZED))
        if facts.get("pid") != spawned_pid and not (platform == "win32" and facts.get("ppid") == spawned_pid):
            failures.append(_fail("worker_facts.pid", "the worker's own PID does not descend from the spawned process"))
        for section in ("restricted_identity", "process_control", "acl", "egress"):
            if (normalized.get(section) or {}).get("source") != "NOT_ENFORCED_OFFLINE_FAKE":
                failures.append(_fail(f"{section}.source", "an offline fake backend cannot claim OS enforcement"))
        return failures

    # PRODUCTION requirement.
    if backend.get("kind") != BACKEND_PRODUCTION:
        failures.append(_fail("backend.kind", "live launch requires the production OS-enforcement backend", R_BACKEND_NOT_AUTHORIZED))
    if not backend.get("backend_id") or backend.get("backend_id") == OFFLINE_FAKE_BACKEND_ID \
            or backend.get("backend_id") != expected.get("backend_id"):
        failures.append(_fail("backend.backend_id", "absent, fake or not the manifest-bound backend", R_BACKEND_NOT_AUTHORIZED))
    if backend.get("contract_version") != BACKEND_CONTRACT_VERSION or backend.get("contract_version") != expected.get(
            "backend_contract_version"):
        failures.append(_fail("backend.contract_version", "backend contract differs from the manifest-bound contract"))
    interpreter_pid = worker.get("interpreter_pid")
    if not _pid_relation_ok(spawned_pid, interpreter_pid, facts, platform):
        failures.append(_fail("worker_process.interpreter_pid", "worker PID relationship not established"))
    created = build_manifest._parse_utc(worker.get("creation_time_utc"))
    issued = build_manifest._parse_utc(expected.get("issued_at_utc"))
    if created is None or issued is None or created < issued - CLOCK_SKEW or (verified_at is not None and created > verified_at):
        failures.append(_fail("worker_process.creation_time_utc", "worker creation time does not fall within this launch"))
    identity = normalized.get("restricted_identity")
    if not _observed(identity):
        failures.append(_fail("restricted_identity", "missing or not read back from the OS"))
    elif not expected.get("restricted_identity") or identity.get("value") != expected.get("restricted_identity") \
            or facts.get("identity") != expected.get("restricted_identity"):
        failures.append(_fail("restricted_identity", "attested/observed identity differs from the required identity"))
    failures += process_control_violations(normalized.get("process_control"), expected, platform=platform,
                                           spawned_pid=spawned_pid, interpreter_pid=interpreter_pid)
    # Worker self-observation corroborates only: never a substitute for the Job facts above.
    if platform == "win32" and facts.get("in_job") is not True:
        failures.append(_fail("worker_facts.in_job", "the worker does not observe Job membership"))
    if platform != "win32" and facts.get("in_job"):
        failures.append(_fail("worker_facts.in_job", "a Windows Job object is not a POSIX control"))
    failures += acl_violations(normalized.get("acl"), expected)
    failures += egress_violations(normalized.get("egress"), expected, platform=platform)
    return failures


# ---------------------------------------------------------------------------------------------
# Issuance and acceptance.
# ---------------------------------------------------------------------------------------------


def issue_attestation(
    backend: Any, launch: build_manifest.ProviderLaunchAuthorization, process: Any, *,
    worker_facts: Mapping[str, Any] | None, now: datetime | None = None,
) -> TrustedOSEnforcementAttestation:
    """The only producer of a ``TrustedOSEnforcementAttestation``: the permitted backend's own
    verification phase, normalised and validated against this exact launch."""
    if not isinstance(launch, build_manifest.ProviderLaunchAuthorization) or not launch.issued_by_attestation:
        raise OSEnforcementAttestationRejected([_fail("launch", "launch not issued by attestation", R_BACKEND_NOT_AUTHORIZED)])
    requirement = build_manifest.os_enforcement_requirement(launch.manifest, launch.launch_mode)
    if requirement == BACKEND_OFFLINE_FAKE:
        permitted = type(backend) is OfflineFakeDirectPopenBackend
    else:
        configured = production_backend()
        permitted = configured is not None and backend is configured and getattr(backend, "kind", None) == BACKEND_PRODUCTION
    if not permitted:
        raise OSEnforcementAttestationRejected([_fail("backend", f"not the backend this {requirement} launch may use",
                                                      R_BACKEND_NOT_AUTHORIZED)])
    verification = backend.verify_spawned_process(launch, process)
    if type(verification) is not BackendVerification or not isinstance(verification.result, Mapping):
        raise OSEnforcementAttestationRejected([_fail("verification", "not a BackendVerification from the backend")])
    if verification.backend_id != getattr(backend, "backend_id", None) \
            or verification.contract_version != getattr(backend, "contract_version", None):
        raise OSEnforcementAttestationRejected([_fail("verification.backend_id", "verification from another backend identity",
                                                      R_BACKEND_NOT_AUTHORIZED)])
    normalized = {
        "contract_version": ATTESTATION_CONTRACT_VERSION,
        "backend": {"backend_id": verification.backend_id, "contract_version": verification.contract_version,
                    "kind": getattr(backend, "kind", None)},
        "verified_at_utc": verification.verified_at_utc,
        # Content identity of the raw observations -- never the trust decision.
        "evidence_sha256": build_manifest.canonical_sha256(dict(verification.raw_observations or {})),
    }
    for key, value in verification.result.items():
        normalized[key] = value  # unknown keys are refused by the contract check
    failures = attestation_contract_violations(
        normalized, expected_enforcement_binding(launch), requirement=requirement, spawned_pid=getattr(process, "pid", None),
        worker_facts=worker_facts, now=now,
    )
    if failures:
        raise OSEnforcementAttestationRejected(failures)
    return TrustedOSEnforcementAttestation(
        launch_id=launch.launch_id, manifest_sha256=launch.manifest_sha256, requirement=requirement,
        backend_kind=str(normalized["backend"]["kind"]), backend_id=verification.backend_id,
        normalized=normalized, evidence_sha256=normalized["evidence_sha256"], _issuer=_ATTESTATION_ISSUER,
    )


def accept_attestation(attestation: Any, *, launch: build_manifest.ProviderLaunchAuthorization) -> list[dict[str, Any]]:
    """The launch layer's check: only an issued attestation for THIS launch. Empty = accepted."""
    if not isinstance(attestation, TrustedOSEnforcementAttestation) or not attestation.issued_by_backend_verification:
        return [_fail("attestation", "not issued by a backend verification", R_ATTESTATION_NOT_ISSUED)]
    failures = []
    requirement = build_manifest.os_enforcement_requirement(launch.manifest, launch.launch_mode)
    if attestation.launch_id != launch.launch_id:
        failures.append(_fail("launch_id", "attestation issued for another launch"))
    if attestation.manifest_sha256 != launch.manifest_sha256:
        failures.append(_fail("manifest_sha256", "attestation issued for another build"))
    if attestation.requirement != requirement:
        failures.append(_fail("requirement", "attestation issued for another enforcement requirement", R_BACKEND_NOT_AUTHORIZED))
    if requirement == BACKEND_PRODUCTION and attestation.backend_kind != BACKEND_PRODUCTION:
        failures.append(_fail("backend_kind", "live launch requires a production attestation", R_BACKEND_NOT_AUTHORIZED))
    return failures
