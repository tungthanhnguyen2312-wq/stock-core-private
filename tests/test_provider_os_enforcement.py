"""APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 -- runtime OS enforcement, fail closed.

A manifest's os_containment block is a requirement, never proof. Only an OS-enforcement backend may
spawn a provider worker: plain Popen for the offline fake Gate B, a production backend (none exists
yet) for everything that can lead to real provider execution. Hermetic: fake venv, fake packages;
no vnstock/vnai, no network, no real credentials.
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
from _provider_build_fixtures import protocol_runtime

LIVE_MODES = (build_manifest.LAUNCH_MODE_GATE_C, build_manifest.LAUNCH_MODE_GATE_D,
              build_manifest.LAUNCH_MODE_GATE_E, build_manifest.LAUNCH_MODE_ORDINARY_DAILY)
OTHER_PLATFORM_CONTROL = ("LINUX_CGROUP_V2_KILL" if sys.platform == "win32" else "WINDOWS_JOB_OBJECT_KILL_ON_CLOSE")


class _Process:
    def __init__(self, pid: int):
        self.pid = pid


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
    """A manifest that is NOT a test fixture: no fixture marker, real provenance classes."""
    manifest["os_containment"]["requirements"] = ["owner-verified restricted identity, Job object, ACLs, OS egress gate"]
    for item in manifest["packages"]:
        item["provenance_classification"] = "PROVENANCE_SUFFICIENT_FOR_OWNER_REVIEW"
    manifest["qualification_evidence_sha256"] = "c" * 64


def _gate_b_launch(tmp_path):
    return protocol_runtime(tmp_path / "rt").authorize()


def _as_live(launch, mode=build_manifest.LAUNCH_MODE_GATE_C):
    return dataclasses.replace(launch, launch_mode=mode, os_enforcement_requirement=build_manifest.OS_ENFORCEMENT_PRODUCTION)


def _good_production_attestation(launch, pid=4242):
    manifest = launch.manifest
    containment = manifest["os_containment"]
    body = {
        "contract_version": os_enforcement.ATTESTATION_CONTRACT_VERSION,
        "backend_kind": os_enforcement.BACKEND_PRODUCTION, "backend_id": "test-production-backend",
        "platform": sys.platform, "launch_id": launch.launch_id, "worker_pid": pid,
        "restricted_identity": {"value": containment["restricted_identity_sid"], "source": "OS_TOKEN_QUERY"},
        "process_control": {"mechanism": build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform], "verified": True,
                            "source": "OS_PROCESS_QUERY"},
        "acl": {"runtime_root_read_only_verified": True, "provider_roots_isolated_verified": True,
                "owner_roots_denied_verified": True, "source": "OS_ACL_QUERY"},
        "egress": {"mechanism": sorted(os_enforcement.EGRESS_MECHANISMS[sys.platform])[0],
                   "direct_egress_blocked_verified": True, "gateway": dict(manifest["network"]["egress_gateway"]),
                   "gateway_identity_verified": True, "source": "OS_FIREWALL_QUERY"},
        "verified_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    body["evidence_sha256"] = os_enforcement.attestation_body_sha256(body)
    facts = {"platform": sys.platform, "pid": pid, "ppid": 1, "identity": containment["restricted_identity_sid"],
             "in_job": True if sys.platform == "win32" else None, "cgroup": None}
    return body, facts


def _rehash(attestation):
    attestation = dict(attestation)
    attestation["evidence_sha256"] = os_enforcement.attestation_body_sha256(attestation)
    return attestation


def _fields(failures):
    return {item.get("field") for item in failures}


# --- 1-2. no production backend => no live launch, and no Popen fallback ----------------------


def test_no_production_backend_is_provisioned_in_this_milestone():
    assert os_enforcement.production_backend() is None


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_approved_real_build_with_all_containment_flags_true_still_cannot_launch_live(tmp_path, mode):
    runtime = protocol_runtime(tmp_path / "rt", launch_mode=mode, mutate_manifest=_real_build)
    containment = runtime.manifest["os_containment"]
    assert containment["state"] == "OWNER_VERIFIED" and containment["egress_gateway_verified"] is True
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


def test_open_provider_runtime_for_a_live_mode_spawns_nothing(tmp_path, monkeypatch):
    calls = _count_worker_spawns(monkeypatch)
    runtime = protocol_runtime(tmp_path / "rt", launch_mode=build_manifest.LAUNCH_MODE_GATE_C, mutate_manifest=_real_build)
    handle = runtime.open_provider_runtime()
    assert not handle.available
    assert handle.state["state"] == rt.SECURITY_REVIEW_BLOCKED
    assert handle.state["reason_code"] == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
    assert calls == []


def test_a_live_launch_cannot_fall_back_to_plain_popen(tmp_path, monkeypatch):
    calls = _count_worker_spawns(monkeypatch)
    launch = _gate_b_launch(tmp_path)
    try:
        live = _as_live(launch)
        with pytest.raises(os_enforcement.OSEnforcementUnavailable) as exc:
            os_enforcement.backend_for_launch(live)
        assert exc.value.reason_code == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
        # A launch that still CLAIMS the offline requirement is recomputed from manifest + mode.
        drifted = dataclasses.replace(launch, launch_mode=build_manifest.LAUNCH_MODE_GATE_C)
        with pytest.raises(os_enforcement.OSEnforcementUnavailable):
            os_enforcement.backend_for_launch(drifted)
        # The offline backend re-checks eligibility itself.
        with pytest.raises(os_enforcement.OSEnforcementUnavailable):
            os_enforcement.OfflineFakeDirectPopenBackend().spawn_contained(live)
        fetcher = worker_client.VnstockWorkerFetcher(python_executable=launch.interpreter, policy=launch.policy, launch=live)
        with pytest.raises(worker_client.VnstockWorkerStartupError) as failure:
            fetcher.start()
        assert failure.value.diagnostics["reason_code"] == build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE
        assert calls == []
    finally:
        launch.cleanup()


# --- 3-4. the offline fake backend -------------------------------------------------------------


def test_offline_fake_backend_runs_gate_b_and_says_it_enforced_nothing(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    handle = runtime.open_provider_runtime()
    try:
        assert handle.available, handle.state
        enforcement = handle.fetcher.worker_diagnostics()["os_enforcement"]
        assert enforcement["backend_kind"] == os_enforcement.BACKEND_OFFLINE_FAKE
        assert enforcement["requirement"] == build_manifest.OS_ENFORCEMENT_OFFLINE_FAKE
        assert enforcement["failures"] == []
    finally:
        handle.shutdown()


def test_offline_fake_attestation_is_rejected_for_a_live_launch(tmp_path):
    launch = _gate_b_launch(tmp_path)
    try:
        fake = os_enforcement.OfflineFakeDirectPopenBackend().attest_spawned_process(launch, _Process(4242))
        assert fake["authorizes_live_launch"] is False
        assert os_enforcement.validate_attestation(
            fake, launch=launch, worker_pid=4242, worker_facts={"platform": sys.platform, "pid": 4242}) == []
        for mode in LIVE_MODES:
            failures = os_enforcement.validate_attestation(
                fake, launch=_as_live(launch, mode), worker_pid=4242, worker_facts={"platform": sys.platform, "pid": 4242})
            assert os_enforcement.R_BACKEND_NOT_AUTHORIZED in {item["code"] for item in failures}
    finally:
        launch.cleanup()


def test_offline_fake_attestation_cannot_claim_enforcement(tmp_path):
    launch = _gate_b_launch(tmp_path)
    try:
        fake = os_enforcement.OfflineFakeDirectPopenBackend().attest_spawned_process(launch, _Process(4242))
        forged = _rehash(dict(fake, process_control={"mechanism": build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform],
                                                     "verified": True, "source": "OS_PROCESS_QUERY"}))
        failures = os_enforcement.validate_attestation(
            forged, launch=launch, worker_pid=4242, worker_facts={"platform": sys.platform, "pid": 4242})
        assert "process_control.verified" in _fields(failures)
    finally:
        launch.cleanup()


# --- 5-11. production attestation contract -----------------------------------------------------


@pytest.fixture
def live_launch(tmp_path):
    launch = _gate_b_launch(tmp_path)
    yield _as_live(launch)
    launch.cleanup()


def test_a_consistent_production_attestation_is_accepted(live_launch):
    attestation, facts = _good_production_attestation(live_launch)
    assert os_enforcement.validate_attestation(attestation, launch=live_launch, worker_pid=4242, worker_facts=facts) == []


def test_attestation_that_mirrors_the_manifest_declarations_is_rejected(live_launch):
    _good, facts = _good_production_attestation(live_launch)
    mirrored = dict(live_launch.manifest["os_containment"])
    mirrored.update(contract_version=os_enforcement.ATTESTATION_CONTRACT_VERSION, backend_kind=os_enforcement.BACKEND_PRODUCTION,
                    platform=sys.platform, launch_id=live_launch.launch_id, worker_pid=4242,
                    verified_at_utc=_good["verified_at_utc"])
    mirrored["evidence_sha256"] = live_launch.manifest["os_containment"]["verification_evidence_sha256"]
    failures = os_enforcement.validate_attestation(mirrored, launch=live_launch, worker_pid=4242, worker_facts=facts)
    fields = _fields(failures)
    assert {"attestation", "evidence_sha256", "restricted_identity", "process_control", "acl", "egress"} <= fields


@pytest.mark.parametrize("mutation, field", [
    (lambda a, f: a.update(launch_id="0" * 32), "launch_id"),
    (lambda a, f: a.update(worker_pid=999), "worker_pid"),
    (lambda a, f: a["restricted_identity"].update(value="S-1-5-21-9-9-9-2002"), "restricted_identity"),
    (lambda a, f: f.update(identity="uid:1"), "restricted_identity"),
    (lambda a, f: a["restricted_identity"].update(source="MANIFEST"), "restricted_identity"),
    (lambda a, f: a.pop("process_control"), "process_control"),
    (lambda a, f: a["process_control"].update(verified=False), "process_control"),
    (lambda a, f: a["process_control"].update(mechanism=OTHER_PLATFORM_CONTROL), "process_control.mechanism"),
    (lambda a, f: a.pop("acl"), "acl"),
    (lambda a, f: a["acl"].update(owner_roots_denied_verified=False), "acl"),
    (lambda a, f: a.pop("egress"), "egress"),
    (lambda a, f: a["egress"].update(direct_egress_blocked_verified=False), "egress.direct_egress_blocked_verified"),
    (lambda a, f: a["egress"].update(mechanism="PYTHON_REQUESTS_ALLOWLIST"), "egress.mechanism"),
    (lambda a, f: a["egress"].update(gateway={"host": "other-gateway.test", "port": 3128}), "egress.gateway"),
    (lambda a, f: a.update(backend_kind=os_enforcement.BACKEND_OFFLINE_FAKE), "backend_kind"),
    (lambda a, f: a.update(platform="darwin"), "platform"),
    (lambda a, f: a.update(verified_at_utc=(datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")),
     "verified_at_utc"),
])
def test_each_production_attestation_defect_fails_closed(live_launch, mutation, field):
    attestation, facts = _good_production_attestation(live_launch)
    attestation = {key: (dict(value) if isinstance(value, dict) else value) for key, value in attestation.items()}
    mutation(attestation, facts)
    failures = os_enforcement.validate_attestation(_rehash(attestation), launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert field in _fields(failures)


def test_a_gateway_address_alone_is_not_egress_enforcement(live_launch):
    attestation, facts = _good_production_attestation(live_launch)
    attestation["egress"] = {"gateway": dict(live_launch.manifest["network"]["egress_gateway"])}
    failures = os_enforcement.validate_attestation(_rehash(attestation), launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert "egress" in _fields(failures)
    attestation["egress"] = {"gateway": dict(live_launch.manifest["network"]["egress_gateway"]),
                             "gateway_identity_verified": True, "source": "OS_FIREWALL_QUERY"}
    failures = os_enforcement.validate_attestation(_rehash(attestation), launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert {"egress.mechanism", "egress.direct_egress_blocked_verified"} <= _fields(failures)


def test_tampered_evidence_hash_fails(live_launch):
    attestation, facts = _good_production_attestation(live_launch)
    attestation["acl"] = dict(attestation["acl"], source="OS_ACL_QUERY", extra=True)  # changed without rehash
    failures = os_enforcement.validate_attestation(attestation, launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert "evidence_sha256" in _fields(failures)


# --- 12. platform-specific process control ------------------------------------------------------


def test_process_control_requirement_is_platform_specific(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    containment = runtime.manifest["os_containment"]
    assert containment["process_control_mechanism"] == build_manifest.PROCESS_CONTROL_BY_PLATFORM[sys.platform]
    assert containment["job_object_kill_on_close"] is (sys.platform == "win32")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX: a Windows Job object must never be asserted as satisfied")
def test_posix_never_accepts_a_windows_job_claim(tmp_path, live_launch):
    manifest = dict(live_launch.manifest)
    manifest["os_containment"] = dict(manifest["os_containment"], job_object_kill_on_close=True)
    assert "os_containment.job_object_kill_on_close" in _fields(build_manifest.os_containment_violations(manifest))
    attestation, facts = _good_production_attestation(live_launch)
    attestation["process_control"] = dict(attestation["process_control"], mechanism="WINDOWS_JOB_OBJECT_KILL_ON_CLOSE")
    facts["in_job"] = True
    failures = os_enforcement.validate_attestation(_rehash(attestation), launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert {"process_control.mechanism", "worker_facts.in_job"} <= _fields(failures)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows: the worker must observe Job object membership")
def test_windows_production_requires_observed_job_membership(live_launch):
    attestation, facts = _good_production_attestation(live_launch)
    facts["in_job"] = False
    failures = os_enforcement.validate_attestation(attestation, launch=live_launch, worker_pid=4242, worker_facts=facts)
    assert "worker_facts.in_job" in _fields(failures)


# --- worker-side independent checks -------------------------------------------------------------


def test_worker_observes_its_own_os_facts():
    facts = build_manifest.observe_worker_os_facts()
    assert facts["platform"] == sys.platform and isinstance(facts["pid"], int)
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
    assert "identity" in _fields(build_manifest.worker_os_enforcement_violations(wrong, facts, None))
    own = _contract(build_manifest.OS_ENFORCEMENT_PRODUCTION, build_manifest.LAUNCH_MODE_GATE_C,
                    expected_restricted_identity=facts["identity"])
    fields = _fields(build_manifest.worker_os_enforcement_violations(own, dict(facts, in_job=False), None))
    assert ("in_job" if sys.platform == "win32" else "cgroup") in fields


# --- 13-16. telemetry owner decision is DENY -------------------------------------------------


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
