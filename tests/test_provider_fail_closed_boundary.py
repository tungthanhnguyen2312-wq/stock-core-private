"""APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 -- final fail-closed corrective.

Mandatory owner-verified OS containment + egress gateway, owner-root separation before any provider
directory exists, denied-root dominance in the worker filesystem policy, and the isolated state-file
credential format. Hermetic: fake venv, fake packages, fake credentials; no vnstock/vnai, no network.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import provider_build_manifest as build_manifest
import provider_worker_containment as containment
from _provider_build_fixtures import isolated_base, protocol_runtime

ROOT = Path(__file__).resolve().parents[1]
FAKE_SECRET = "fixture-credential-value-7f3a9c"  # not a real key; must never appear in diagnostics


def _codes(failures) -> set[str]:
    return {item["code"] for item in failures}


def _fields(failures) -> set[str]:
    return {item.get("field") for item in failures}


def _launch_violations(runtime, manifest, launch_mode=build_manifest.LAUNCH_MODE_GATE_B):
    """The launch-authorization layer, applied directly (independent of load_manifest)."""
    return build_manifest._approval_violations(manifest, runtime.policy, runtime.manifest_sha256,
                                               datetime.now(timezone.utc), launch_mode)


def _dir_alias(link: Path, target: Path) -> bool:
    """A directory alias resolving into ``target`` (POSIX symlink; Windows junction, no privilege)."""
    try:
        if os.name == "nt":
            done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
            return done.returncode == 0 and link.exists()
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


# --- A. mandatory owner-verified OS containment ------------------------------------------------


@pytest.mark.parametrize("field, value", [
    ("egress_gateway_verified", False),
    ("job_object_kill_on_close", False),
    ("runtime_root_read_only_acl", False),
    ("restricted_identity_sid", None),
    ("restricted_identity_sid", "TEST_FIXTURE"),
    ("restricted_identity_sid", "S-1-5-18"),  # SYSTEM is never a restricted identity
    ("verification_evidence_sha256", None),
    ("verification_evidence_sha256", "not-a-sha256"),
    ("state", "NOT_PROVISIONED_OWNER_DECISION_REQUIRED"),
])
def test_approved_manifest_with_unverified_os_containment_fails_at_both_layers(tmp_path, field, value):
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m["os_containment"].__setitem__(field, value))
    semantic = build_manifest.manifest_contract_violations(runtime.manifest)
    assert f"os_containment.{field}" in _fields(semantic)
    assert build_manifest.R_OS_CONTAINMENT_UNVERIFIED in _codes(semantic)
    assert f"os_containment.{field}" in _fields(_launch_violations(runtime, runtime.manifest))
    with pytest.raises(build_manifest.ProviderBuildManifestError):
        runtime.authorize()


def test_draft_manifest_may_keep_containment_unresolved_but_stays_non_launchable():
    manifest, _digest = build_manifest.load_manifest()
    assert manifest["status"] == build_manifest.STATUS_DRAFT and manifest["launch_authorized"] is False
    assert manifest["os_containment"]["state"] != build_manifest.OS_CONTAINMENT_OWNER_VERIFIED
    assert build_manifest.os_containment_violations(manifest)  # unresolved, and that is allowed for DRAFT
    assert manifest["network"]["egress_gateway"] is None


def test_fake_containment_evidence_drives_only_offline_gate_b(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    assert build_manifest.R_OS_CONTAINMENT_FAKE_EVIDENCE not in _codes(_launch_violations(runtime, runtime.manifest))
    for mode in (build_manifest.LAUNCH_MODE_GATE_C, build_manifest.LAUNCH_MODE_GATE_D,
                 build_manifest.LAUNCH_MODE_GATE_E, build_manifest.LAUNCH_MODE_ORDINARY_DAILY):
        assert build_manifest.R_OS_CONTAINMENT_FAKE_EVIDENCE in _codes(_launch_violations(runtime, runtime.manifest, mode))


# --- B. mandatory OS egress gateway -------------------------------------------------------------


def test_gateway_verified_without_a_bound_gateway_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m["network"].__setitem__("egress_gateway", None))
    assert build_manifest.R_EGRESS_GATEWAY_CONTRACT_INVALID in _codes(build_manifest.manifest_contract_violations(runtime.manifest))
    assert build_manifest.R_EGRESS_GATEWAY_CONTRACT_INVALID in _codes(_launch_violations(runtime, runtime.manifest))
    with pytest.raises(build_manifest.ProviderBuildManifestError):
        runtime.authorize()


def test_bound_gateway_without_verified_containment_is_contradictory_even_for_a_draft():
    manifest, _digest = build_manifest.load_manifest()
    manifest = json.loads(json.dumps(manifest))
    manifest["network"]["egress_gateway"] = {"host": "egress-gateway.test", "port": 3128}
    assert build_manifest.R_EGRESS_GATEWAY_CONTRACT_INVALID in _codes(build_manifest.manifest_contract_violations(manifest))


def test_approved_endpoints_without_the_os_egress_gate_fail(tmp_path):
    def mutate(manifest):
        manifest["network"]["egress_gateway"] = None
        manifest["os_containment"]["egress_gateway_verified"] = False

    runtime = protocol_runtime(tmp_path / "rt", style="governed", mutate_manifest=mutate)
    assert runtime.manifest["network"]["endpoints"]
    failures = build_manifest.egress_gateway_violations(runtime.manifest, approved=True)
    assert any("mandatory OS egress gateway" in str(item.get("error")) for item in failures)


# --- C. owner-root separation before any provider directory exists -----------------------------


@pytest.mark.parametrize("which", ["provider_state_root", "provider_scratch_base"])
def test_provider_root_inside_owner_profile_fails_before_mkdir(tmp_path, which):
    target = tmp_path / "rt" / "owner-profile" / f"nested-{which}"
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m["filesystem"].__setitem__(which, str(target)))
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_PROVIDER_ROOT_OVERLAPS_OWNER_ROOT
    assert not target.exists()


def test_provider_root_that_is_an_ancestor_of_an_owner_root_fails(tmp_path):
    ancestor = tmp_path / "rt"  # contains the owner profile
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=lambda m: m["filesystem"].__setitem__(
        "provider_state_root", str(ancestor)))
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_PROVIDER_ROOT_OVERLAPS_OWNER_ROOT


def test_aliased_provider_root_resolving_into_the_owner_profile_fails(tmp_path):
    runtime_root = tmp_path / "rt"
    owner_profile = runtime_root / "owner-profile"
    owner_profile.mkdir(parents=True)
    alias = Path(isolated_base()) / f"alias-{os.getpid()}-{tmp_path.name}"
    if not _dir_alias(alias, owner_profile):
        pytest.skip("cannot create a directory alias on this host")
    try:
        runtime = protocol_runtime(runtime_root, mutate_manifest=lambda m: m["filesystem"].__setitem__(
            "provider_state_root", str(alias / "provider-state")))
        with pytest.raises(build_manifest.ProviderAttestationError) as exc:
            runtime.authorize()
        assert exc.value.reason_code == build_manifest.R_PROVIDER_ROOT_OVERLAPS_OWNER_ROOT
    finally:
        os.rmdir(alias) if os.name == "nt" else alias.unlink()


def test_valid_isolated_provider_roots_pass_and_launch(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    denied = build_manifest.owner_denied_roots(runtime.parent_environ())
    assert build_manifest.provider_root_violations(runtime.manifest, denied) == []
    launch = runtime.authorize()
    assert launch.issued_by_attestation
    launch.cleanup()


# --- D. denied roots dominate the worker filesystem policy -------------------------------------


def test_denied_root_dominates_nested_writable_and_read_only_roots(tmp_path):
    owner = tmp_path / "owner"
    policy = containment.FilesystemPolicy(
        denied_roots=(str(owner),), read_only_roots=(str(owner / "ro"),), writable_roots=(str(owner / "rw"),))
    assert policy.evaluate(owner / "rw" / "x.json", write=True) == containment.FILESYSTEM_DENIED_ROOT
    assert policy.evaluate(owner / "rw" / "x.json", write=False) == containment.FILESYSTEM_DENIED_ROOT
    assert policy.evaluate(owner / "ro" / "x.json", write=False) == containment.FILESYSTEM_DENIED_ROOT


def test_unrelated_provider_roots_keep_governed_behaviour(tmp_path):
    policy = containment.FilesystemPolicy(
        denied_roots=(str(tmp_path / "owner"),), read_only_roots=(str(tmp_path / "venv"),),
        writable_roots=(str(tmp_path / "state"),))
    assert policy.evaluate(tmp_path / "state" / "x.json", write=True) is None
    assert policy.evaluate(tmp_path / "venv" / "lib.py", write=False) is None
    assert policy.evaluate(tmp_path / "venv" / "lib.py", write=True) == containment.FILESYSTEM_WRITE_TO_READ_ONLY_ROOT
    assert policy.evaluate(tmp_path / "owner" / "secret", write=False) == containment.FILESYSTEM_DENIED_ROOT


def test_alias_into_a_denied_root_is_denied(tmp_path):
    owner = tmp_path / "owner"
    owner.mkdir()
    alias = tmp_path / "state-alias"
    if not _dir_alias(alias, owner):
        pytest.skip("cannot create a directory alias on this host")
    try:
        policy = containment.FilesystemPolicy(denied_roots=(str(owner),), read_only_roots=(), writable_roots=(str(alias),))
        assert policy.evaluate(alias / "x.json", write=True) == containment.FILESYSTEM_DENIED_ROOT
    finally:
        os.rmdir(alias) if os.name == "nt" else alias.unlink()


# --- E. APPROVED_STATE_FILE credential format -------------------------------------------------


@pytest.mark.parametrize("payload, code", [
    (b"", build_manifest.R_CREDENTIAL_REQUIRED_ABSENT),
    (b"{not json", build_manifest.R_CREDENTIAL_STATE_FILE_INVALID),
    (b"[]", build_manifest.R_CREDENTIAL_STATE_FILE_INVALID),
    (b"{}", build_manifest.R_CREDENTIAL_STATE_FILE_INVALID),
    (b'{"key": "x"}', build_manifest.R_CREDENTIAL_STATE_FILE_INVALID),
    (b'{"api_key": 12345}', build_manifest.R_CREDENTIAL_STATE_FILE_INVALID),
    (b'{"api_key": "   "}', build_manifest.R_CREDENTIAL_REQUIRED_ABSENT),
    (b'{"api_key": "placeholder"}', build_manifest.R_CREDENTIAL_PLACEHOLDER),
    (b'{"api_key": "fake-key"}', build_manifest.R_CREDENTIAL_PLACEHOLDER),
    (b'{"api_key": "dummy_api_key"}', build_manifest.R_CREDENTIAL_PLACEHOLDER),
    (b'{"api_key": "your_api_key_here"}', build_manifest.R_CREDENTIAL_PLACEHOLDER),
])
def test_invalid_state_file_credentials_fail_closed(tmp_path, payload, code):
    path = tmp_path / ".vnstock" / "api_key.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    failures = build_manifest.state_file_credential_violations(path)
    assert _codes(failures) == {code}


def test_state_file_diagnostics_never_carry_the_value(tmp_path):
    path = tmp_path / "api_key.json"
    for value in (FAKE_SECRET + "x" * 5000, "placeholder"):
        path.write_text(json.dumps({"api_key": value}), encoding="utf-8")
        assert value not in json.dumps(build_manifest.state_file_credential_violations(path))


def test_missing_state_file_is_absent(tmp_path):
    assert _codes(build_manifest.state_file_credential_violations(tmp_path / "nope.json")) == {
        build_manifest.R_CREDENTIAL_REQUIRED_ABSENT}


def _state_file_runtime(tmp_path, value):
    runtime = protocol_runtime(tmp_path / "rt", credential_mechanism=build_manifest.CREDENTIAL_APPROVED_STATE_FILE)
    path = runtime.state_root / build_manifest.VENDOR_CREDENTIAL_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"api_key": value}), encoding="utf-8")
    return runtime


def test_placeholder_state_file_blocks_launch(tmp_path):
    runtime = _state_file_runtime(tmp_path, "placeholder")
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_CREDENTIAL_PLACEHOLDER
    assert "placeholder" not in json.dumps(exc.value.failures)


def test_valid_fake_state_file_credential_binds_the_free_tier_at_20_rpm(tmp_path):
    runtime = _state_file_runtime(tmp_path, FAKE_SECRET)
    launch = runtime.authorize()
    try:
        assert launch.tier == build_manifest.TIER_FREE
        assert launch.governor_rpm == 20
        assert FAKE_SECRET not in json.dumps(launch.identity())
        assert FAKE_SECRET not in json.dumps(dict(launch.attestation), default=str)
    finally:
        launch.cleanup()


def test_env_credential_semantics_are_unchanged_and_shared(tmp_path):
    ok = protocol_runtime(tmp_path / "ok", credential_mechanism=build_manifest.CREDENTIAL_APPROVED_ENV_NAME,
                          credential_value="test-fixture-credential-not-a-real-key")
    launch = ok.authorize()
    assert launch.tier == build_manifest.TIER_FREE
    launch.cleanup()
    fake = protocol_runtime(tmp_path / "fake", credential_mechanism=build_manifest.CREDENTIAL_APPROVED_ENV_NAME,
                            credential_value="fake-key")
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        fake.authorize()
    assert exc.value.reason_code == build_manifest.R_CREDENTIAL_PLACEHOLDER
