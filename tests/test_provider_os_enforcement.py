"""APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 -- runtime OS enforcement, fail closed.

A manifest's os_containment block is a requirement, never proof, and an attestation is trusted only
when ``provider_os_enforcement.issue_attestation`` issued it from the permitted backend's own
verification phase for one exact launch. Production-contract tests use ``_FixtureProductionVerifier``:
TEST FIXTURE ONLY -- it exercises the contract plumbing with a complete normalised result and
enforces nothing; no test here implies that real Windows/Linux enforcement occurred.
Hermetic: fake venv, fake packages; no vnstock/vnai, no network, no real credentials.
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime, timedelta, timezone

import pytest

import provider_build_manifest as build_manifest
import provider_os_enforcement as os_enforcement
import provider_runtime_state as rt
import vnstock_worker_client as worker_client
from _provider_build_fixtures import FAKE_PRODUCTION_BACKEND_ID, protocol_runtime

LIVE_MODES = (build_manifest.LAUNCH_MODE_GATE_C, build_manifest.LAUNCH_MODE_GATE_D,
              build_manifest.LAUNCH_MODE_GATE_E, build_manifest.LAUNCH_MODE_ORDINARY_DAILY)
OTHER_PLATFORM_CONTROL = ("LINUX_CGROUP_V2_KILL" if sys.platform == "win32" else "WINDOWS_JOB_OBJECT_KILL_ON_CLOSE")
SPAWNED_PID = 4242
# A Windows venv python.exe is a redirector: the interpreter is its child.
INTERPRETER_PID = 4243 if sys.platform == "win32" else SPAWNED_PID


class _Process:
    def __init__(self, pid: int):
        self.pid = pid


def _utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_worker_spawns(monkeypatch):
    """Record every Popen whose argv runs a provider worker entrypoint; delegate everything else
    (venv creation, the ``-I -S`` probe) to the real Popen."""
    calls = []
    real_popen = worker_client.subprocess.Popen

    def counting(argv, *args, **kwargs):
        if any(str(item).endswith(("vnstock_worker_process.py", "fake_vnstock_worker.py")) for item in list(argv)):
            calls.append(list(argv))
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(worker_client.subprocess, "Popen", counting)
    return calls


def _real_build(manifest):
    """A manifest that is NOT a test fixture: no fixture marker, real provenance classes and a
    production backend id that is not the fixture verifier."""
    manifest["os_containment"]["requirements"] = ["owner-verified restricted identity, Job object, ACLs, OS egress gate"]
    manifest["os_containment"]["enforcement_backend"]["backend_id"] = "stocklookup-windows-os-enforcement"
    for item in manifest["packages"]:
        item["provenance_classification"] = "PROVENANCE_SUFFICIENT_FOR_OWNER_REVIEW"
    manifest["qualification_evidence_sha256"] = "c" * 64


def _as_live(launch, mode=build_manifest.LAUNCH_MODE_GATE_C):
    return dataclasses.replace(launch, launch_mode=mode, os_enforcement_requirement=build_manifest.OS_ENFORCEMENT_PRODUCTION)


def _process_control(expected, platform=sys.platform):
    if platform == "win32":
        return {"mechanism": "WINDOWS_JOB_OBJECT_KILL_ON_CLOSE", "source": "OS_JOB_QUERY",
                "job": {"name": expected["job_name"], "membership_verified_with_job_handle": True,
                        "assigned_pids": [SPAWNED_PID, INTERPRETER_PID],
                        "limits": {"kill_on_job_close": True, "breakaway_ok": False, "silent_breakaway_ok": False,
                                   "active_process_limit": expected["job_active_process_limit"]}}}
    return {"mechanism": "LINUX_CGROUP_V2_KILL", "source": "OS_CGROUP_QUERY",
            "cgroup": {"path": expected["cgroup_path"], "member_pids": [SPAWNED_PID, INTERPRETER_PID], "kill_on_close": True}}


def _complete_result(launch):
    """Every mandatory field of a production result, bound to ``launch`` (fixture data only)."""
    expected = os_enforcement.expected_enforcement_binding(launch)
    return {
        "binding": {key: expected[key] for key in ("launch_id", "manifest_sha256", "build_id", "policy_decision_id", "platform")},
        "worker_process": {"spawned_pid": SPAWNED_PID, "interpreter_pid": INTERPRETER_PID,
                           "creation_time_utc": _utc(datetime.now(timezone.utc))},
        "restricted_identity": {"value": expected["restricted_identity"], "source": "OS_TOKEN_QUERY"},
        "process_control": _process_control(expected),
        "acl": {"identity": expected["acl_policy"]["identity"], "policy_sha256": expected["acl_policy_sha256"],
                "roots": [dict(item, effective_access_verified=True) for item in expected["acl_policy"]["roots"]],
                "source": "OS_ACL_QUERY"},
        "egress": {"mechanism": sorted(os_enforcement.EGRESS_MECHANISMS[sys.platform])[0],
                   "policy_sha256": expected["egress_policy_sha256"],
                   "telemetry_policy_sha256": expected["telemetry_policy_sha256"],
                   "direct_egress_prohibited_verified": True,
                   "gateway": dict(expected["gateway"], identity_verified=True), "source": "OS_FIREWALL_QUERY"},
    }


def _facts(launch):
    return {"platform": sys.platform, "pid": INTERPRETER_PID, "ppid": SPAWNED_PID,
            "identity": launch.manifest["os_containment"]["restricted_identity_sid"],
            "in_job": True if sys.platform == "win32" else None, "cgroup": None}


class _FixtureProductionVerifier:
    """TEST FIXTURE ONLY production-contract verifier: returns a prepared result, enforces nothing."""

    kind = os_enforcement.BACKEND_PRODUCTION
    contract_version = os_enforcement.BACKEND_CONTRACT_VERSION

    def __init__(self, result, *, backend_id=FAKE_PRODUCTION_BACKEND_ID, verification=None):
        self.result = result
        self.backend_id = backend_id
        self._verification = verification

    def preflight(self, launch):
        return {}

    def spawn_contained(self, launch):
        raise AssertionError("the fixture verifier never spawns")

    def verify_spawned_process(self, launch, process):
        if self._verification is not None:
            return self._verification
        return os_enforcement.BackendVerification(
            backend_id=self.backend_id, contract_version=self.contract_version,
            raw_observations={"fixture_only": True, "pid": process.pid}, result=self.result,
            verified_at_utc=_utc(datetime.now(timezone.utc)))


def _issue(monkeypatch, launch, result=None, **verifier_kwargs):
    verifier = _FixtureProductionVerifier(result if result is not None else _complete_result(launch), **verifier_kwargs)
    monkeypatch.setattr(os_enforcement, "production_backend", lambda: verifier)
    return os_enforcement.issue_attestation(verifier, launch, _Process(SPAWNED_PID), worker_facts=_facts(launch))


def _rejected_fields(monkeypatch, launch, result=None, **verifier_kwargs):
    with pytest.raises(os_enforcement.OSEnforcementAttestationRejected) as exc:
        _issue(monkeypatch, launch, result, **verifier_kwargs)
    return {item.get("field") for item in exc.value.failures}


@pytest.fixture
def gate_b_launch(tmp_path):
    launch = protocol_runtime(tmp_path / "rt").authorize()
    yield launch
    launch.cleanup()


@pytest.fixture
def live_launch(gate_b_launch):
    return _as_live(gate_b_launch)


# --- no production backend => no live launch, no Popen fallback -------------------------------


def test_no_production_backend_is_provisioned_in_this_milestone():
    assert os_enforcement.production_backend() is None


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_approved_real_build_with_all_containment_flags_true_still_cannot_launch_live(tmp_path, mode):
    runtime = protocol_runtime(tmp_path / "rt", launch_mode=mode, mutate_manifest=_real_build)
    assert build_manifest.manifest_contract_violations(runtime.manifest) == []
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
    assert not any(runtime.scratch_base.iterdir())  # refused before any launch directory exists


def test_real_build_cannot_use_plain_popen_even_for_gate_b(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=_real_build)
    assert not build_manifest.offline_fake_launch_eligible(runtime.manifest, build_manifest.LAUNCH_MODE_GATE_B)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE


def test_a_manifest_binding_the_fixture_verifier_is_never_live(tmp_path):
    def fixture_backend_only(manifest):
        _real_build(manifest)
        manifest["os_containment"]["enforcement_backend"]["backend_id"] = FAKE_PRODUCTION_BACKEND_ID

    runtime = protocol_runtime(tmp_path / "rt", launch_mode=build_manifest.LAUNCH_MODE_GATE_C, mutate_manifest=fixture_backend_only)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_OS_CONTAINMENT_FAKE_EVIDENCE


def test_open_provider_runtime_for_a_live_mode_spawns_nothing(tmp_path, monkeypatch):
    calls = _count_worker_spawns(monkeypatch)
    runtime = protocol_runtime(tmp_path / "rt", launch_mode=build_manifest.LAUNCH_MODE_GATE_C, mutate_manifest=_real_build)
    handle = runtime.open_provider_runtime()
    assert not handle.available
    assert handle.state["state"] == rt.SECURITY_REVIEW_BLOCKED
    assert handle.state["reason_code"] == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
    assert calls == []


def test_a_live_launch_cannot_fall_back_to_plain_popen(gate_b_launch, monkeypatch):
    calls = _count_worker_spawns(monkeypatch)
    live = _as_live(gate_b_launch)
    with pytest.raises(os_enforcement.OSEnforcementUnavailable) as exc:
        os_enforcement.backend_for_launch(live)
    assert exc.value.reason_code == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
    drifted = dataclasses.replace(gate_b_launch, launch_mode=build_manifest.LAUNCH_MODE_GATE_C)
    with pytest.raises(os_enforcement.OSEnforcementUnavailable):
        os_enforcement.backend_for_launch(drifted)  # the requirement is recomputed from manifest + mode
    with pytest.raises(os_enforcement.OSEnforcementUnavailable):
        os_enforcement.OfflineFakeDirectPopenBackend().spawn_contained(live)
    fetcher = worker_client.VnstockWorkerFetcher(python_executable=gate_b_launch.interpreter, policy=gate_b_launch.policy, launch=live)
    with pytest.raises(worker_client.VnstockWorkerStartupError) as failure:
        fetcher.start()
    assert failure.value.diagnostics["reason_code"] == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
    assert calls == []


def test_live_issuance_without_a_production_backend_is_refused(live_launch):  # 23
    verifier = _FixtureProductionVerifier(_complete_result(live_launch))
    with pytest.raises(os_enforcement.OSEnforcementAttestationRejected) as exc:
        os_enforcement.issue_attestation(verifier, live_launch, _Process(SPAWNED_PID), worker_facts=_facts(live_launch))
    assert exc.value.reason_code == os_enforcement.R_BACKEND_NOT_AUTHORIZED


# --- the offline fake issuer: Gate B only (21, 22) ----------------------------------------------


def test_offline_fake_attestation_is_issued_for_gate_b_only(gate_b_launch):
    backend = os_enforcement.OfflineFakeDirectPopenBackend()
    facts = {"platform": sys.platform, "pid": SPAWNED_PID, "ppid": 1}
    trusted = os_enforcement.issue_attestation(backend, gate_b_launch, _Process(SPAWNED_PID), worker_facts=facts)
    assert trusted.issued_by_backend_verification
    assert trusted.requirement == build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE
    assert trusted.to_record()["authorizes_live_launch"] is False
    assert os_enforcement.accept_attestation(trusted, launch=gate_b_launch) == []
    for mode in LIVE_MODES:
        live = _as_live(gate_b_launch, mode)
        assert os_enforcement.accept_attestation(trusted, launch=live)  # never accepted for a live launch
        with pytest.raises((os_enforcement.OSEnforcementAttestationRejected, os_enforcement.OSEnforcementUnavailable)):
            os_enforcement.issue_attestation(backend, live, _Process(SPAWNED_PID), worker_facts=facts)


def test_offline_fake_backend_runs_gate_b_end_to_end(tmp_path):
    handle = protocol_runtime(tmp_path / "rt").open_provider_runtime()
    try:
        assert handle.available, handle.state
        enforcement = handle.fetcher.worker_diagnostics()["os_enforcement"]
        assert enforcement["backend_id"] == os_enforcement.OFFLINE_FAKE_BACKEND_ID
        assert enforcement["requirement"] == build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE
        assert enforcement["authorizes_live_launch"] is False
        assert enforcement["failures"] == []
    finally:
        handle.shutdown()


# --- issuance boundary (4, 5) ---------------------------------------------------------------------


def test_a_complete_fixture_production_result_is_issued_through_the_boundary(monkeypatch, live_launch):
    trusted = _issue(monkeypatch, live_launch)
    assert trusted.issued_by_backend_verification
    assert trusted.backend_id == FAKE_PRODUCTION_BACKEND_ID  # fixture verifier; no real enforcement occurred
    assert os_enforcement.accept_attestation(trusted, launch=live_launch) == []


def test_plain_objects_are_never_accepted_as_attestations(monkeypatch, live_launch):
    trusted = _issue(monkeypatch, live_launch)
    forged = os_enforcement.TrustedOSEnforcementAttestation(
        launch_id=trusted.launch_id, manifest_sha256=trusted.manifest_sha256, requirement=trusted.requirement,
        backend_kind=trusted.backend_kind, backend_id=trusted.backend_id, normalized=trusted.normalized,
        evidence_sha256=trusted.evidence_sha256)
    for candidate in (dict(trusted.normalized), trusted.normalized, forged, trusted.to_record(), None):
        codes = {item["code"] for item in os_enforcement.accept_attestation(candidate, launch=live_launch)}
        assert codes == {os_enforcement.R_ATTESTATION_NOT_ISSUED}


def test_a_verification_that_is_not_a_backend_verification_is_refused(monkeypatch, live_launch):
    result = _complete_result(live_launch)
    fields = _rejected_fields(monkeypatch, live_launch, result, verification=dict(result))
    assert fields == {"verification"}


def test_a_content_hash_is_identity_not_proof(monkeypatch, live_launch):
    # A self-consistent report hash says nothing: an incomplete result with a matching digest fails.
    thin = {"binding": _complete_result(live_launch)["binding"],
            "worker_process": {"spawned_pid": SPAWNED_PID}}
    thin["evidence_sha256"] = build_manifest.canonical_sha256(thin)
    fields = _rejected_fields(monkeypatch, live_launch, thin)
    assert {"restricted_identity", "process_control", "acl", "egress", "worker_process.creation_time_utc"} <= fields


def test_result_carrying_manifest_declarations_is_refused(monkeypatch, live_launch):
    result = _complete_result(live_launch)
    result.update({key: live_launch.manifest["os_containment"][key]
                   for key in ("job_object_kill_on_close", "egress_gateway_verified", "runtime_root_read_only_acl")})
    assert "attestation" in _rejected_fields(monkeypatch, live_launch, result)


# --- backend identity (1, 2, 3) ----------------------------------------------------------------


@pytest.mark.parametrize("backend_id", ["", "some-other-os-backend", os_enforcement.OFFLINE_FAKE_BACKEND_ID])
def test_backend_identity_must_be_the_manifest_bound_production_backend(monkeypatch, live_launch, backend_id):
    assert "backend.backend_id" in _rejected_fields(monkeypatch, live_launch, backend_id=backend_id)


def test_backend_contract_version_must_match(monkeypatch, live_launch):
    verifier_result = _complete_result(live_launch)
    verification = os_enforcement.BackendVerification(
        backend_id=FAKE_PRODUCTION_BACKEND_ID, contract_version="provider_os_enforcement_backend/v0",
        raw_observations={}, result=verifier_result, verified_at_utc=_utc(datetime.now(timezone.utc)))
    assert "verification.backend_id" in _rejected_fields(monkeypatch, live_launch, verifier_result, verification=verification)


def test_manifest_must_bind_a_production_backend(tmp_path):
    for value in (None, {"backend_id": "", "contract_version": build_manifest.OS_ENFORCEMENT_BACKEND_CONTRACT_VERSION},
                  {"backend_id": os_enforcement.OFFLINE_FAKE_BACKEND_ID,
                   "contract_version": build_manifest.OS_ENFORCEMENT_BACKEND_CONTRACT_VERSION},
                  {"backend_id": "x", "contract_version": "provider_os_enforcement_backend/v0"}):
        runtime = protocol_runtime(tmp_path / f"rt-{len(str(value))}",
                                   mutate_manifest=lambda m, v=value: m["os_containment"].__setitem__("enforcement_backend", v))
        fields = {item.get("field") for item in build_manifest.os_containment_violations(runtime.manifest)}
        assert "os_containment.enforcement_backend" in fields


# --- exact launch binding (6, 7, 8) -------------------------------------------------------------


@pytest.mark.parametrize("key", ["launch_id", "manifest_sha256", "build_id", "policy_decision_id", "platform"])
def test_binding_mismatch_fails(monkeypatch, live_launch, key):
    result = _complete_result(live_launch)
    result["binding"][key] = "other"
    assert f"binding.{key}" in _rejected_fields(monkeypatch, live_launch, result)


def test_an_attestation_for_one_launch_is_never_reused_for_another(monkeypatch, tmp_path, live_launch):
    trusted = _issue(monkeypatch, live_launch)
    other = protocol_runtime(tmp_path / "other").authorize()
    try:
        fields = {item["field"] for item in os_enforcement.accept_attestation(trusted, launch=_as_live(other))}
        assert {"launch_id", "manifest_sha256"} <= fields
    finally:
        other.cleanup()


@pytest.mark.parametrize("mutate, field", [
    (lambda r, f: r["worker_process"].update(spawned_pid=999), "worker_process.spawned_pid"),
    (lambda r, f: r["worker_process"].update(interpreter_pid=999), "worker_process.interpreter_pid"),
    (lambda r, f: f.update(pid=999), "worker_process.interpreter_pid"),
    (lambda r, f: r["worker_process"].update(creation_time_utc=None), "worker_process.creation_time_utc"),
    (lambda r, f: r["worker_process"].update(creation_time_utc="2020-01-01T00:00:00Z"), "worker_process.creation_time_utc"),
])
def test_worker_process_binding_mismatch_fails(monkeypatch, live_launch, mutate, field):
    result, facts = _complete_result(live_launch), _facts(live_launch)
    mutate(result, facts)
    verifier = _FixtureProductionVerifier(result)
    monkeypatch.setattr(os_enforcement, "production_backend", lambda: verifier)
    with pytest.raises(os_enforcement.OSEnforcementAttestationRejected) as exc:
        os_enforcement.issue_attestation(verifier, live_launch, _Process(SPAWNED_PID), worker_facts=facts)
    assert field in {item.get("field") for item in exc.value.failures}


def test_stale_verification_fails(monkeypatch, live_launch):
    verification = os_enforcement.BackendVerification(
        backend_id=FAKE_PRODUCTION_BACKEND_ID, contract_version=os_enforcement.BACKEND_CONTRACT_VERSION,
        raw_observations={}, result=_complete_result(live_launch),
        verified_at_utc=_utc(datetime.now(timezone.utc) - timedelta(hours=2)))
    assert "verified_at_utc" in _rejected_fields(monkeypatch, live_launch, verification=verification)


# --- process-lifetime control (9-13): Windows contract checked on every host ---------------------


WIN_EXPECTED = {"process_control_mechanism": "WINDOWS_JOB_OBJECT_KILL_ON_CLOSE", "job_name": "Local\\StockLookupProvider-L1",
                "job_active_process_limit": 2, "cgroup_path": "/stocklookup-provider/L1"}


def _win_section():
    return _process_control(WIN_EXPECTED, platform="win32")


@pytest.mark.parametrize("mutate, field", [
    (lambda s: s.pop("job"), "process_control.job.name"),  # 9: in-a-job alone, no job identity
    (lambda s: s["job"].update(name="Local\\SomeOtherJob"), "process_control.job.name"),  # 10
    (lambda s: s["job"].update(membership_verified_with_job_handle=False), "process_control.job.membership_verified_with_job_handle"),
    (lambda s: s["job"].update(assigned_pids=[SPAWNED_PID]), "process_control.job.assigned_pids"),
    (lambda s: s["job"]["limits"].pop("kill_on_job_close"), "process_control.job.limits.kill_on_job_close"),  # 11
    (lambda s: s["job"]["limits"].update(breakaway_ok=True), "process_control.job.limits.breakaway_ok"),  # 12
    (lambda s: s["job"]["limits"].update(silent_breakaway_ok=True), "process_control.job.limits.silent_breakaway_ok"),  # 13
    (lambda s: s["job"]["limits"].update(active_process_limit=50), "process_control.job.limits.active_process_limit"),
    (lambda s: s.update(mechanism="LINUX_CGROUP_V2_KILL"), "process_control.mechanism"),
])
def test_windows_job_contract_binds_the_exact_launch_job(mutate, field):
    section = _win_section()
    mutate(section)
    failures = os_enforcement.process_control_violations(section, WIN_EXPECTED, platform="win32",
                                                         spawned_pid=SPAWNED_PID, interpreter_pid=INTERPRETER_PID)
    assert field in {item["field"] for item in failures}


def test_windows_job_contract_accepts_the_complete_section():
    assert os_enforcement.process_control_violations(_win_section(), WIN_EXPECTED, platform="win32",
                                                     spawned_pid=SPAWNED_PID, interpreter_pid=INTERPRETER_PID) == []


def test_mechanism_name_plus_verified_is_not_a_job(monkeypatch, live_launch):
    result = _complete_result(live_launch)
    result["process_control"] = {"mechanism": build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform], "verified": True,
                                 "source": "OS_JOB_QUERY"}
    fields = _rejected_fields(monkeypatch, live_launch, result)
    assert fields & {"process_control.job.name", "process_control.cgroup.path"}


def test_worker_in_job_observation_alone_is_insufficient(monkeypatch, live_launch):
    result = _complete_result(live_launch)
    result["process_control"] = {"mechanism": build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform], "source": "OS_JOB_QUERY"}
    facts = dict(_facts(live_launch), in_job=True)
    verifier = _FixtureProductionVerifier(result)
    monkeypatch.setattr(os_enforcement, "production_backend", lambda: verifier)
    with pytest.raises(os_enforcement.OSEnforcementAttestationRejected):
        os_enforcement.issue_attestation(verifier, live_launch, _Process(SPAWNED_PID), worker_facts=facts)


def test_posix_cgroup_contract_binds_the_exact_launch_cgroup():
    section = _process_control(WIN_EXPECTED, platform="linux")
    assert os_enforcement.process_control_violations(section, dict(WIN_EXPECTED, process_control_mechanism="LINUX_CGROUP_V2_KILL"),
                                                     platform="linux", spawned_pid=SPAWNED_PID, interpreter_pid=INTERPRETER_PID) == []
    section["cgroup"]["path"] = "/some/other"
    failures = os_enforcement.process_control_violations(section, dict(WIN_EXPECTED, process_control_mechanism="LINUX_CGROUP_V2_KILL"),
                                                         platform="linux", spawned_pid=SPAWNED_PID, interpreter_pid=INTERPRETER_PID)
    assert "process_control.cgroup.path" in {item["field"] for item in failures}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX: a Windows Job object must never be asserted as satisfied")
def test_posix_never_accepts_a_windows_job_claim(monkeypatch, live_launch):
    manifest = dict(live_launch.manifest)
    manifest["os_containment"] = dict(manifest["os_containment"], job_object_kill_on_close=True)
    assert "os_containment.job_object_kill_on_close" in {
        item.get("field") for item in build_manifest.os_containment_violations(manifest)}
    result = _complete_result(live_launch)
    result["process_control"] = _process_control(os_enforcement.expected_enforcement_binding(live_launch), platform="win32")
    assert "process_control.mechanism" in _rejected_fields(monkeypatch, live_launch, result)


# --- egress / gateway (14-17) --------------------------------------------------------------------


@pytest.mark.parametrize("mutate, field", [
    (lambda e: e.update(gateway={"host": e["gateway"]["host"], "port": e["gateway"]["port"], "identity_verified": True}),
     "egress.gateway.gateway_id"),  # 14: address without identity
    (lambda e: e["gateway"].update(executable_sha256="0" * 64), "egress.gateway.executable_sha256"),
    (lambda e: e["gateway"].update(identity_verified=False), "egress.gateway.identity_verified"),
    (lambda e: e.update(policy_sha256="0" * 64), "egress.policy_sha256"),  # 15
    (lambda e: e.pop("direct_egress_prohibited_verified"), "egress.direct_egress_prohibited_verified"),  # 16
    (lambda e: e.update(telemetry_policy_sha256="0" * 64), "egress.telemetry_policy_sha256"),  # 17
    (lambda e: e.update(mechanism="PYTHON_REQUESTS_ALLOWLIST"), "egress.mechanism"),
])
def test_egress_contract_binds_the_exact_policy_and_gateway(monkeypatch, live_launch, mutate, field):
    result = _complete_result(live_launch)
    mutate(result["egress"])
    assert field in _rejected_fields(monkeypatch, live_launch, result)


def test_a_gateway_address_alone_is_not_egress_enforcement(monkeypatch, live_launch):
    result = _complete_result(live_launch)
    result["egress"] = {"gateway": {"host": "egress-gateway.test", "port": 3128}}
    assert "egress" in _rejected_fields(monkeypatch, live_launch, result)


def test_egress_policy_identity_tracks_telemetry_and_endpoints(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    base = build_manifest.egress_policy_sha256(runtime.manifest)
    manifest = dict(runtime.manifest, telemetry_disposition=runtime.manifest["telemetry_disposition"][1:])
    assert build_manifest.egress_policy_sha256(manifest) != base
    manifest = dict(runtime.manifest, network=dict(runtime.manifest["network"], endpoints=[{"host": "other.test"}]))
    assert build_manifest.egress_policy_sha256(manifest) != base
    assert build_manifest.egress_policy_identity(runtime.manifest)["direct_egress"] == "PROHIBITED"


def test_approved_manifest_gateway_must_carry_an_identity(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m["network"].__setitem__(
        "egress_gateway", {"host": "egress-gateway.test", "port": 3128}))
    fields = {item.get("field") for item in build_manifest.egress_gateway_violations(runtime.manifest, approved=True)}
    assert {f"network.egress_gateway.{key}" for key in build_manifest.GATEWAY_IDENTITY_KEYS} <= fields


# --- ACL (18-20) ----------------------------------------------------------------------------


@pytest.mark.parametrize("mutate, field", [
    (lambda a, r: a.clear() or a.update(verified=True, source="OS_ACL_QUERY"), "acl.roots"),  # 18
    (lambda a, r: a["roots"][0].update(path=r), "acl.roots"),  # 19
    (lambda a, r: a["roots"][0].update(access_class=os_enforcement.ACCESS_READ_WRITE), "acl.roots"),
    (lambda a, r: a["roots"][-1].update(effective_access_verified=False), "acl.roots.effective_access_verified"),
    (lambda a, r: a.update(identity="S-1-5-21-9-9-9-2002"), "acl.identity"),  # 20
    (lambda a, r: a.update(policy_sha256="0" * 64), "acl.policy_sha256"),
])
def test_acl_contract_binds_exact_roots_classes_and_identity(monkeypatch, tmp_path, live_launch, mutate, field):
    result = _complete_result(live_launch)
    mutate(result["acl"], str(tmp_path / "elsewhere"))
    assert field in _rejected_fields(monkeypatch, live_launch, result)


def test_acl_policy_names_every_launch_root(live_launch):
    policy = os_enforcement.acl_policy(live_launch)
    classes = {item["path"]: item["access_class"] for item in policy["roots"]}
    assert classes[str(live_launch.state_root)] == os_enforcement.ACCESS_READ_WRITE
    assert classes[str(live_launch.scratch_root)] == os_enforcement.ACCESS_READ_WRITE
    assert classes[str(live_launch.bundle_root)] == os_enforcement.ACCESS_READ_EXECUTE
    assert all(classes[root] == os_enforcement.ACCESS_NONE for root in live_launch.attestation["denied_roots"])
    assert policy["identity"] == live_launch.manifest["os_containment"]["restricted_identity_sid"]


# --- identity -----------------------------------------------------------------------------------


@pytest.mark.parametrize("mutate", [
    lambda r, f: r["restricted_identity"].update(value="S-1-5-21-9-9-9-2002"),
    lambda r, f: r["restricted_identity"].update(source="MANIFEST"),
    lambda r, f: f.update(identity="uid:1"),
])
def test_restricted_identity_mismatch_fails(monkeypatch, live_launch, mutate):
    result, facts = _complete_result(live_launch), _facts(live_launch)
    mutate(result, facts)
    verifier = _FixtureProductionVerifier(result)
    monkeypatch.setattr(os_enforcement, "production_backend", lambda: verifier)
    with pytest.raises(os_enforcement.OSEnforcementAttestationRejected) as exc:
        os_enforcement.issue_attestation(verifier, live_launch, _Process(SPAWNED_PID), worker_facts=facts)
    assert "restricted_identity" in {item.get("field") for item in exc.value.failures}


# --- platform-specific manifest contract ---------------------------------------------------------


def test_process_control_requirement_is_platform_specific(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    containment = runtime.manifest["os_containment"]
    assert containment["process_control_mechanism"] == build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform]
    assert containment["job_object_kill_on_close"] is (sys.platform == "win32")


# --- worker-side corroboration -------------------------------------------------------------------


def test_worker_observes_its_own_os_facts():
    facts = build_manifest.observe_worker_os_facts()
    assert facts["platform"] == sys.platform and isinstance(facts["pid"], int) and isinstance(facts["ppid"], int)
    if sys.platform == "win32":
        assert str(facts["identity"]).startswith("S-1-")
        assert facts["in_job"] in (True, False)
    else:
        assert str(facts["identity"]).startswith("uid:") and facts["in_job"] is None


def _contract(requirement, mode, **enforcement):
    binding = {"requirement": requirement, "launch_id": "L1", "platform": sys.platform,
               "expected_restricted_identity": None, "expected_cgroup": None}
    binding.update(enforcement)
    return {"launch_id": "L1", "launch_mode": mode, "os_enforcement": binding}


def test_worker_refuses_offline_fake_outside_gate_b_and_missing_or_foreign_bindings():
    facts = build_manifest.observe_worker_os_facts()
    assert build_manifest.worker_os_enforcement_violations(
        _contract(build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE, build_manifest.LAUNCH_MODE_GATE_B), facts, None) == []
    for contract in (
        _contract(build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE, build_manifest.LAUNCH_MODE_GATE_C),
        _contract(build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE, build_manifest.LAUNCH_MODE_GATE_B, launch_id="L2"),
        _contract(build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE, build_manifest.LAUNCH_MODE_GATE_B, platform="darwin"),
        {"launch_id": "L1", "launch_mode": build_manifest.LAUNCH_MODE_GATE_B},
    ):
        assert build_manifest.worker_os_enforcement_violations(contract, facts, None)


def test_worker_refuses_production_binding_it_cannot_observe():
    facts = build_manifest.observe_worker_os_facts()
    wrong = _contract(build_manifest.OS_ENFORCEMENT_PRODUCTION, build_manifest.LAUNCH_MODE_GATE_C,
                      expected_restricted_identity="S-1-5-21-1-2-3-4001" if sys.platform == "win32" else "uid:64001")
    assert "identity" in {item.get("field") for item in build_manifest.worker_os_enforcement_violations(wrong, facts, None)}
    own = _contract(build_manifest.OS_ENFORCEMENT_PRODUCTION, build_manifest.LAUNCH_MODE_GATE_C,
                    expected_restricted_identity=facts["identity"])
    fields = {item.get("field") for item in build_manifest.worker_os_enforcement_violations(own, dict(facts, in_job=False), None)}
    assert ("in_job" if sys.platform == "win32" else "cgroup") in fields


# --- telemetry owner decision is DENY -------------------------------------------------------------


@pytest.mark.parametrize("ref", ["VNAI_ANALYTICS", "VNAI_CONTENT_DELIVERY", "VNAI_DEVICE_REGISTER", "VNAI_PROFILE_SYNC",
                                 "VNAI_LICENSE_VERIFY", "VNSTOCK_UPDATE_PYPI"])
def test_approved_manifest_cannot_allow_a_reviewed_telemetry_class(tmp_path, ref):
    def allow(manifest):
        for entry in manifest["telemetry_disposition"]:
            if entry["endpoint_ref"] == ref:
                entry["decision"] = build_manifest.TELEMETRY_ALLOW

    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=allow)
    failures = build_manifest.manifest_contract_violations(runtime.manifest)
    assert build_manifest.R_TELEMETRY_OWNER_DENY_REQUIRED in {item["code"] for item in failures}
    with pytest.raises(build_manifest.ProviderBuildManifestError):
        runtime.authorize()


def test_approved_manifest_must_materialise_every_reviewed_class(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m.__setitem__(
        "telemetry_disposition", [e for e in m["telemetry_disposition"] if e["endpoint_ref"] != "VNAI_PROFILE_SYNC"]))
    failures = build_manifest.telemetry_owner_deny_violations(runtime.manifest)
    assert [item.get("endpoint_ref") for item in failures] == ["VNAI_PROFILE_SYNC"]


def test_explicit_deny_for_every_reviewed_class_is_semantically_valid(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    assert {e["endpoint_ref"] for e in runtime.manifest["telemetry_disposition"]} == set(build_manifest.REVIEWED_TELEMETRY_REFS)
    assert build_manifest.telemetry_owner_deny_violations(runtime.manifest) == []
    assert build_manifest.manifest_contract_violations(runtime.manifest) == []
