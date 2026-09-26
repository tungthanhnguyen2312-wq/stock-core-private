"""OS-enforcement boundary for the provider worker (APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1).

The approved build manifest's ``os_containment`` block states *requirements*; it is never proof.
A worker process may only be spawned by a ``ProviderOSEnforcementBackend``, in three phases:

1. ``preflight(launch)`` -- the backend establishes/checks the OS controls it will apply;
2. ``spawn_contained(launch)`` -- the backend starts the worker under those controls;
3. ``attest_spawned_process(launch, process)`` -- the backend reports what it actually applied to
   that process (identity, process-lifetime control, ACLs, egress enforcement, gateway), bound to
   the launch id and the worker PID.

``validate_attestation`` then checks that report against the launch, the manifest requirements
and the facts the worker observed about itself (``provider_build_manifest.observe_worker_os_facts``).

Two backend kinds exist:

* ``PRODUCTION_OS_ENFORCEMENT`` -- required by every launch mode that can lead to real provider
  execution (qualification Gates C/D/E, ordinary Daily, and Gate B of a real build). **No
  production backend is implemented yet** (``production_backend()`` returns ``None``): a Windows
  restricted identity + Job object + ACLs + OS egress gate (or a POSIX equivalent) belongs to the
  provisioning milestone. Until then every such launch fails closed with
  ``PROVIDER_OS_ENFORCEMENT_UNAVAILABLE`` before any provider directory or process exists.
* ``OFFLINE_FAKE_DIRECT_POPEN`` -- plain ``subprocess.Popen``. Usable only for the offline fake
  Gate B (test-fixture containment evidence + test-fixture packages; see
  ``provider_build_manifest.offline_fake_launch_eligible``). It re-checks that eligibility itself
  and its attestation always states that nothing was OS-enforced.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

import provider_build_manifest as build_manifest

ATTESTATION_CONTRACT_VERSION = "provider_os_enforcement_attestation/v1"
BACKEND_PRODUCTION = build_manifest.OS_ENFORCEMENT_PRODUCTION
BACKEND_OFFLINE_FAKE = build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE

R_OS_ENFORCEMENT_UNAVAILABLE = build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
R_BACKEND_NOT_AUTHORIZED = "PROVIDER_OS_ENFORCEMENT_BACKEND_NOT_AUTHORIZED_FOR_MODE"
R_ATTESTATION_INVALID = "PROVIDER_OS_ENFORCEMENT_ATTESTATION_INVALID"

# Sources a production backend may cite: facts read back from the OS about the spawned process,
# never values copied from the manifest.
OBSERVED_SOURCES = frozenset({"OS_TOKEN_QUERY", "OS_PROCESS_QUERY", "OS_ACL_QUERY", "OS_FIREWALL_QUERY",
                              "OS_CGROUP_QUERY", "OS_NETNS_QUERY"})
EGRESS_MECHANISMS = {
    "win32": frozenset({"WINDOWS_FILTERING_PLATFORM_DEFAULT_DENY"}),
    "linux": frozenset({"LINUX_NETNS_DEFAULT_DENY"}),
}
# Keys that belong to the manifest's declarations. An attestation shaped like them is a copy of the
# requirements, not evidence about the spawned process.
_MANIFEST_DECLARATION_KEYS = frozenset({"egress_gateway_verified", "job_object_kill_on_close",
                                        "runtime_root_read_only_acl", "restricted_identity_sid", "state",
                                        "requirements", "verification_evidence_sha256"})
MAX_ATTESTATION_AGE = timedelta(minutes=10)


class OSEnforcementUnavailable(RuntimeError):
    """No backend may spawn this launch. Carries a deterministic reason code; spawns nothing."""

    def __init__(self, reason_code: str, detail: Mapping[str, Any] | None = None):
        self.reason_code = reason_code
        self.detail = dict(detail or {})
        super().__init__(reason_code)


class ProviderOSEnforcementBackend(Protocol):
    kind: str

    def preflight(self, launch: build_manifest.ProviderLaunchAuthorization) -> Mapping[str, Any]: ...

    def spawn_contained(self, launch: build_manifest.ProviderLaunchAuthorization) -> subprocess.Popen: ...

    def attest_spawned_process(self, launch: build_manifest.ProviderLaunchAuthorization,
                               process: subprocess.Popen) -> dict[str, Any]: ...


def attestation_body_sha256(attestation: Mapping[str, Any]) -> str:
    return build_manifest.canonical_sha256({key: value for key, value in attestation.items() if key != "evidence_sha256"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class OfflineFakeDirectPopenBackend:
    """Plain ``subprocess.Popen`` for the offline fake Gate B only. Enforces nothing at OS level
    and says so in its attestation; refuses every launch that is not offline-fake eligible."""

    kind = BACKEND_OFFLINE_FAKE

    def preflight(self, launch: build_manifest.ProviderLaunchAuthorization) -> Mapping[str, Any]:
        if not launch.issued_by_attestation:
            raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {"error": "launch not issued by attestation"})
        if launch.os_enforcement_requirement != BACKEND_OFFLINE_FAKE or not build_manifest.offline_fake_launch_eligible(
                launch.manifest, launch.launch_mode):
            raise OSEnforcementUnavailable(R_BACKEND_NOT_AUTHORIZED, {
                "backend": self.kind, "launch_mode": launch.launch_mode,
                "error": "plain Popen is reserved for the offline fake Gate B"})
        return {"backend": self.kind, "launch_id": launch.launch_id}

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

    def attest_spawned_process(self, launch: build_manifest.ProviderLaunchAuthorization,
                               process: subprocess.Popen) -> dict[str, Any]:
        body = {
            "contract_version": ATTESTATION_CONTRACT_VERSION, "backend_kind": self.kind,
            "backend_id": "offline-fake-direct-popen", "platform": sys.platform,
            "launch_id": launch.launch_id, "worker_pid": int(process.pid),
            "authorizes_live_launch": False,
            "restricted_identity": {"value": None, "source": "NOT_ENFORCED_OFFLINE_FAKE"},
            "process_control": {"mechanism": "NONE_OFFLINE_FAKE", "verified": False, "source": "NOT_ENFORCED_OFFLINE_FAKE"},
            "acl": {"runtime_root_read_only_verified": False, "provider_roots_isolated_verified": False,
                    "owner_roots_denied_verified": False, "source": "NOT_ENFORCED_OFFLINE_FAKE"},
            "egress": {"mechanism": "PYTHON_ALLOWLIST_ONLY_OFFLINE_FAKE", "direct_egress_blocked_verified": False,
                       "gateway": None, "gateway_identity_verified": False, "source": "NOT_ENFORCED_OFFLINE_FAKE"},
            "verified_at_utc": _utc(_now()),
        }
        body["evidence_sha256"] = attestation_body_sha256(body)
        return body


def production_backend() -> ProviderOSEnforcementBackend | None:
    """The production OS-enforcement backend for this host, or ``None``.

    Not implemented in this milestone: provisioning a restricted identity, a verified process-lifetime
    control, ACLs and an OS egress gate is the next (owner-authorized) provisioning milestone. Returning
    ``None`` keeps every live launch mode fail-closed."""
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


def _fail(field: str, error: str, code: str = R_ATTESTATION_INVALID) -> dict[str, Any]:
    return {"code": code, "field": field, "error": error}


def _observed(section: Any) -> bool:
    return isinstance(section, Mapping) and section.get("source") in OBSERVED_SOURCES


def validate_attestation(
    attestation: Any, *, launch: build_manifest.ProviderLaunchAuthorization, worker_pid: int | None,
    worker_facts: Mapping[str, Any] | None, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Every reason ``attestation`` does not establish the launch's OS-enforcement requirement.
    Empty = accepted. Never trusts a field only because the manifest states the same value."""
    failures: list[dict[str, Any]] = []
    if not isinstance(attestation, Mapping):
        return [_fail("attestation", "absent")]
    requirement = build_manifest.os_enforcement_requirement(launch.manifest, launch.launch_mode)
    facts = worker_facts if isinstance(worker_facts, Mapping) else {}
    if attestation.get("contract_version") != ATTESTATION_CONTRACT_VERSION:
        failures.append(_fail("contract_version", "unexpected contract"))
    if attestation.get("evidence_sha256") != attestation_body_sha256(attestation):
        failures.append(_fail("evidence_sha256", "does not hash the attestation body"))
    if attestation.get("launch_id") != launch.launch_id:
        failures.append(_fail("launch_id", "does not match this launch"))
    if worker_pid is None or attestation.get("worker_pid") != worker_pid:
        failures.append(_fail("worker_pid", "does not match the spawned process"))
    # A Windows venv's python.exe is a redirector that starts the base interpreter as its child,
    # so the worker observes the spawned PID as its parent there.
    spawned_or_redirected = facts.get("pid") == worker_pid or (sys.platform == "win32" and facts.get("ppid") == worker_pid)
    if worker_pid is None or not spawned_or_redirected:
        failures.append(_fail("worker_facts.pid", "the worker's own PID does not descend from the spawned process"))
    if attestation.get("platform") != sys.platform or facts.get("platform") != sys.platform:
        failures.append(_fail("platform", "attested/observed platform is not this host"))
    parsed = build_manifest._parse_utc(attestation.get("verified_at_utc"))
    current = now or _now()
    if parsed is None or parsed > current + timedelta(minutes=1) or current - parsed > MAX_ATTESTATION_AGE:
        failures.append(_fail("verified_at_utc", "missing, future or stale"))

    kind = attestation.get("backend_kind")
    if requirement == BACKEND_OFFLINE_FAKE:
        if kind != BACKEND_OFFLINE_FAKE:
            failures.append(_fail("backend_kind", "offline fake launch attested by another backend", R_BACKEND_NOT_AUTHORIZED))
        if attestation.get("authorizes_live_launch") is not False:
            failures.append(_fail("authorizes_live_launch", "an offline fake attestation never authorizes live launch"))
        for section, flag in (("process_control", "verified"), ("egress", "direct_egress_blocked_verified"),
                              ("acl", "runtime_root_read_only_verified")):
            if (attestation.get(section) or {}).get(flag) is not False:
                failures.append(_fail(f"{section}.{flag}", "an offline fake backend cannot claim OS enforcement"))
        return failures

    # PRODUCTION requirement.
    if kind != BACKEND_PRODUCTION:
        failures.append(_fail("backend_kind", "live launch requires the production OS-enforcement backend",
                              R_BACKEND_NOT_AUTHORIZED))
    containment = launch.manifest.get("os_containment") or {}
    if _MANIFEST_DECLARATION_KEYS & set(attestation):
        failures.append(_fail("attestation", "shaped like the manifest's declarations; declarations are not evidence"))
    if attestation.get("evidence_sha256") in {containment.get("verification_evidence_sha256"),
                                              build_manifest.canonical_sha256(dict(containment))}:
        failures.append(_fail("evidence_sha256", "mirrors the manifest's own OS declarations"))

    identity = attestation.get("restricted_identity")
    expected_identity = containment.get("restricted_identity_sid")
    if not _observed(identity):
        failures.append(_fail("restricted_identity", "missing or not read back from the OS"))
    elif identity.get("value") != expected_identity or facts.get("identity") != expected_identity:
        failures.append(_fail("restricted_identity", "attested/observed identity differs from the required identity"))

    control = attestation.get("process_control")
    expected_control = build_manifest.PROCESS_CONTROL_BY_PLATFORM.get(sys.platform)
    if not _observed(control) or control.get("verified") is not True:
        failures.append(_fail("process_control", "missing or unverified process-lifetime control"))
    elif control.get("mechanism") != expected_control or control.get("mechanism") != containment.get("process_control_mechanism"):
        failures.append(_fail("process_control.mechanism", f"not the {sys.platform} process-lifetime control"))
    if sys.platform == "win32" and facts.get("in_job") is not True:
        failures.append(_fail("worker_facts.in_job", "the worker does not observe Job object membership"))
    if sys.platform != "win32" and facts.get("in_job"):
        failures.append(_fail("worker_facts.in_job", "a Windows Job object is not a POSIX control"))

    acl = attestation.get("acl")
    if not _observed(acl) or not all(acl.get(key) is True for key in (
            "runtime_root_read_only_verified", "provider_roots_isolated_verified", "owner_roots_denied_verified")):
        failures.append(_fail("acl", "missing or unverified runtime/state/scratch ACLs"))

    egress = attestation.get("egress")
    gateway = (launch.manifest.get("network") or {}).get("egress_gateway")
    if not _observed(egress):
        failures.append(_fail("egress", "missing OS egress-enforcement attestation (a gateway address alone is not enforcement)"))
    else:
        if egress.get("mechanism") not in EGRESS_MECHANISMS.get(sys.platform, frozenset()):
            failures.append(_fail("egress.mechanism", "not an OS egress-enforcement mechanism for this platform"))
        if egress.get("direct_egress_blocked_verified") is not True:
            failures.append(_fail("egress.direct_egress_blocked_verified", "direct egress around the gateway not proven blocked"))
        if egress.get("gateway_identity_verified") is not True or egress.get("gateway") != gateway:
            failures.append(_fail("egress.gateway", "gateway identity not verified or not the bound gateway"))
    return failures
