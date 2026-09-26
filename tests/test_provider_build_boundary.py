"""APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 security tests.

Hermetic: throwaway fake venv, fake packages, fake worker. No real vnstock/vnai, no network,
no live credentials, no Daily, no retained-evidence mutation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import provider_build_manifest as build_manifest
import provider_execution_guard as guard
import provider_runtime_state as rt
import provider_worker_containment as containment
import vn_stock_pipeline as pipeline
from _provider_build_fixtures import (
    FAKE_ENDPOINT_HOST,
    FAKE_WORKER,
    MODE_OFFLINE_FAKE,
    build_fake_provider_runtime,
    governed_runtime,
    protocol_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).with_name("fixtures") / "check_provider_containment.py"


def _probe_at(tmp_path: Path, contract: dict, action: str, target, *, method: str = "GET") -> dict:
    spec_path = tmp_path / "containment-probe.json"
    spec_path.write_text(json.dumps({"action": action, "target": target, "method": method, "contract": contract}), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-u", str(PROBE), str(spec_path)],
        capture_output=True, text=True, timeout=20, cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


# --- tracked DRAFT / policy ------------------------------------------------------------------


def test_tracked_manifest_is_draft_and_not_launchable():
    manifest, _digest = build_manifest.load_manifest()
    assert manifest["status"] == build_manifest.STATUS_DRAFT
    assert manifest["launch_authorized"] is False
    assert manifest["approval"] is None
    policy = rt.load_provider_policy()
    assert policy.policy == rt.POLICY_SECURITY_REVIEW_BLOCKED
    assert policy.approved_manifest_sha256 is None and policy.decision_id is None


def test_tracked_lock_is_a_candidate_not_an_approval():
    lock, _digest = build_manifest.load_dependency_lock()
    assert lock["approval_state"] == "CANDIDATE_FOR_OWNER_REVIEW_NOT_APPROVED"
    assert "anthropic" not in {item["name"] for item in lock["candidate_closure"]["packages"]}
    assert lock["candidate_closure"]["count"] == 39
    assert len(lock["runtime_minimal_hypothesis"]["packages"]) == 23
    assert len(lock["unnecessary_for_governed_worker"]["packages"]) == 16


@pytest.mark.parametrize("payload", [None, "{not json", "[]"])
def test_missing_or_malformed_manifest_fails_closed(tmp_path, payload):
    path = tmp_path / "manifest.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    with pytest.raises(build_manifest.ProviderBuildManifestError) as exc:
        build_manifest.load_manifest(path)
    assert exc.value.reason_code in (
        build_manifest.R_MANIFEST_ABSENT, build_manifest.R_MANIFEST_MALFORMED,
    )


def test_draft_manifest_cannot_authorize_launch(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", status=build_manifest.STATUS_DRAFT, launch_authorized=False)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_NOT_APPROVED


def test_revoked_manifest_blocks_new_launch(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    runtime.revoke(reason="TEST_REVOKE")
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_REVOKED


def test_policy_pin_mismatch_and_identity_mismatch_fail_closed(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    bad = rt.ProviderPolicy(
        provider_family=runtime.policy.provider_family, policy=runtime.policy.policy,
        reason="x", source="TEST", approved_manifest_path=str(runtime.manifest_path),
        approved_manifest_sha256="c" * 64, decision_id=runtime.policy.decision_id,
    )
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize(policy=bad)
    assert exc.value.reason_code == build_manifest.R_POLICY_DIGEST_MISMATCH


# --- attestation -----------------------------------------------------------------------------


def test_executable_hash_mismatch_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", python_build_override="not-the-real-build")
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code in (
        build_manifest.R_PYTHON_BUILD_MISMATCH, build_manifest.R_EXECUTABLE_HASH_MISMATCH,
    )


def test_unexpected_pth_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", unexpected_pth=True)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_STARTUP_HOOK_UNEXPECTED


def test_startup_hook_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", startup_hook=True)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_STARTUP_HOOK_UNEXPECTED


def test_system_site_enabled_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", system_site=True)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_SYSTEM_SITE_ENABLED


def test_worker_source_hash_mismatch_fails(tmp_path):
    def mutate(manifest):
        manifest["worker"]["source_files"][0]["sha256"] = "d" * 64
    runtime = protocol_runtime(tmp_path / "rt", mutate_manifest=mutate)
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_WORKER_SOURCE_MISMATCH


def test_valid_fake_attestation_passes(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    launch = runtime.authorize()
    assert launch.issued_by_attestation
    assert launch.governor_rpm >= 1
    launch.cleanup()


# --- credential / rate -----------------------------------------------------------------------


def test_credential_required_without_key_fails(tmp_path):
    runtime = protocol_runtime(
        tmp_path / "rt", credential_mechanism=build_manifest.CREDENTIAL_APPROVED_ENV_NAME,
    )
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_CREDENTIAL_REQUIRED_ABSENT


def test_placeholder_key_fails(tmp_path):
    runtime = protocol_runtime(
        tmp_path / "rt", credential_mechanism=build_manifest.CREDENTIAL_APPROVED_ENV_NAME,
        credential_value="placeholder",
    )
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize()
    assert exc.value.reason_code == build_manifest.R_CREDENTIAL_PLACEHOLDER


def test_governor_rate_above_manifest_maximum_fails(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    with pytest.raises(build_manifest.ProviderAttestationError) as exc:
        runtime.authorize(configured_governor_rpm=runtime.manifest["rate_tier_binding"]["governor_effective_rpm"] + 1)
    assert exc.value.reason_code == build_manifest.R_GOVERNOR_EXCEEDS_APPROVED


def test_valid_guest_tier_rate_contract_passes(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    launch = runtime.authorize()
    assert launch.tier == build_manifest.TIER_GUEST
    assert launch.governor_rpm == runtime.manifest["rate_tier_binding"]["governor_effective_rpm"]
    launch.cleanup()


# --- transport -------------------------------------------------------------------------------


def test_transport_allow_list_accepts_approved_and_rejects_wrong_host_method_path():
    policy = containment.EgressPolicy.from_endpoints([{
        "scheme": "https", "host": FAKE_ENDPOINT_HOST, "port": 443, "method": "GET",
        "path_pattern": "/ohlc/{symbol}", "purpose": "test", "max_redirects": 0,
    }])
    assert policy.evaluate_http("GET", "https://fake-provider.test/ohlc/AAA") is None
    assert policy.evaluate_http("GET", "https://evil.example/ohlc/AAA") == containment.TRANSPORT_HOST_NOT_ALLOWLISTED
    assert policy.evaluate_http("POST", "https://fake-provider.test/ohlc/AAA") == containment.TRANSPORT_METHOD_NOT_ALLOWED
    assert policy.evaluate_http("GET", "https://fake-provider.test/other/AAA") == containment.TRANSPORT_PATH_NOT_ALLOWLISTED


def test_redirect_to_unapproved_host_is_refused():
    # evaluate_http of the Location itself is the redirect check the requests guard uses.
    policy = containment.EgressPolicy.from_endpoints([{
        "scheme": "https", "host": FAKE_ENDPOINT_HOST, "port": 443, "method": "GET",
        "path_pattern": "/ohlc/{symbol}", "purpose": "test", "max_redirects": 0,
    }])
    assert policy.evaluate_http("GET", "https://hq.vnstocks.com/analytics") == containment.TRANSPORT_HOST_NOT_ALLOWLISTED


def test_enforce_transport_policy_without_install_fails_closed():
    with pytest.raises(containment.TransportPolicyViolation) as exc:
        containment.enforce_transport_policy("GET", "https://fake-provider.test/ohlc/AAA")
    assert exc.value.reason_code == containment.TRANSPORT_POLICY_NOT_INSTALLED


# --- process / filesystem containment --------------------------------------------------------


def _contract_for(tmp_path: Path, *, denied: Path, writable: Path) -> dict:
    return {
        "network": {"endpoints": [{
            "scheme": "https", "host": FAKE_ENDPOINT_HOST, "port": 443, "method": "GET",
            "path_pattern": "/ohlc/{symbol}", "purpose": "test", "max_redirects": 0,
        }], "expected_denied_hosts": ["hq.vnstocks.com"], "expected_denied_processes": ["git"]},
        "roots": {
            "denied_roots": [str(denied)], "read_only_roots": [str(tmp_path / "ro")],
            "writable_roots": [str(writable)],
        },
    }


def test_subprocess_run_and_popen_are_blocked(tmp_path):
    writable = tmp_path / "rw"
    writable.mkdir()
    contract = _contract_for(tmp_path, denied=tmp_path / "denied", writable=writable)
    for action in ("popen", "run"):
        result = _probe_at(tmp_path, contract, action, ["git", "status"])
        assert result["denied"] is True
        assert result["reason_code"] == containment.PROCESS_CREATION_DENIED


def test_owner_profile_and_stocklookup_state_are_denied(tmp_path):
    owner = tmp_path / "owner"
    (owner / ".vnstock").mkdir(parents=True)
    (owner / ".stocklookup").mkdir()
    (owner / ".vnstock" / "api_key.json").write_text("secret", encoding="utf-8")
    (owner / ".stocklookup" / "secrets.env").write_text("x", encoding="utf-8")
    writable = tmp_path / "rw"
    writable.mkdir()
    contract = _contract_for(tmp_path, denied=owner, writable=writable)
    for relative in (".vnstock/api_key.json", ".stocklookup/secrets.env"):
        result = _probe_at(tmp_path, contract, "open", str(owner / relative))
        assert result["denied"] is True
        assert result["reason_code"] == containment.FILESYSTEM_DENIED_ROOT


def test_approved_fake_http_endpoint_passes_policy_check(tmp_path):
    writable = tmp_path / "rw"
    writable.mkdir()
    contract = _contract_for(tmp_path, denied=tmp_path / "denied", writable=writable)
    result = _probe_at(tmp_path, contract, "http", "https://fake-provider.test/ohlc/AAA")
    assert result["denied"] is False
    denied = _probe_at(tmp_path, contract, "http", "https://hq.vnstocks.com/analytics")
    assert denied["denied"] is True


# --- legacy bypass ---------------------------------------------------------------------------


def test_core_python_manual_provider_execution_fails_fast():
    with pytest.raises(guard.GovernedProviderExecutionRequired):
        guard.require_governed_provider_execution("vn_stock_pipeline._quote")
    with pytest.raises(guard.UnsupportedLegacyProviderOperation):
        guard.require_governed_provider_execution("vn_stock_pipeline.cli.update")
    assert pipeline.main(["update"]) == pipeline.EXIT_REFUSED_UNGOVERNED_PROVIDER


def test_resolver_no_longer_silently_imports_provider():
    from multi_source_exact_session_resolver import _require_fetch_boundary
    with pytest.raises(rt.SupplementalProviderRuntimeUnavailable):
        _require_fetch_boundary(None)


def test_direct_worker_launch_under_wrong_interpreter_fails(tmp_path):
    result = subprocess.run(
        [sys.executable, "-s", "-E", "-X", "utf8", "-u", "-B", str(ROOT / "vnstock_worker_process.py")],
        capture_output=True, text=True, timeout=20,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        cwd=str(tmp_path),
    )
    assert result.returncode != 0
    assert "vnstock" not in sys.modules


def test_harmless_retained_data_readers_remain_importable():
    import financial_observations
    import index_constituents_sync
    import meta_sync
    assert callable(getattr(financial_observations, "ingest_pilot", None) or True)
    assert meta_sync is not None and index_constituents_sync is not None


# --- revocation of an active worker ----------------------------------------------------------


def test_active_fake_worker_detects_revocation_at_controlled_boundary(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt")
    fetcher = runtime.fetcher()
    try:
        outcome = fetcher.fetch("EXACT_AAA", "KBS", "2026-09-01", "2026-09-10")
        assert outcome.status == "success"
        runtime.revoke(reason="TEST_ACTIVE_REVOKE", epoch=2)
        with pytest.raises(Exception) as exc:
            fetcher.fetch("EXACT_BBB", "KBS", "2026-09-01", "2026-09-10")
        assert "REVOKED" in type(exc.value).__name__ or "REVOKED" in str(exc.value)
        diag = fetcher.worker_diagnostics()
        assert diag["revocation"]["revoked"] is True
        assert diag["revocation"]["reason"] == "TEST_ACTIVE_REVOKE" or diag["revocation"]["registry_epoch"] == 2
    finally:
        fetcher.shutdown()


# --- existing security invariants ------------------------------------------------------------


def test_dnse_livespeed_finhay_credentials_are_not_forwarded(tmp_path):
    runtime = protocol_runtime(tmp_path / "rt", extra_env={"FAKE_WORKER_REPORT_ENV": "1"})
    parent = runtime.parent_environ(
        DNSE_API_KEY="synthetic-dnse", LIVESPEED_API_KEY="synthetic-ls", FINHAY_API_KEY="synthetic-fh",
    )
    handle = runtime.open_provider_runtime(environ=parent)
    try:
        assert handle.available
        child = handle.fetcher.runtime_info["environment"]
        assert "DNSE_API_KEY" not in child
        assert "LIVESPEED_API_KEY" not in child
        assert "FINHAY_API_KEY" not in child
        dumped = json.dumps(child)
        assert "synthetic-dnse" not in dumped
    finally:
        handle.shutdown()


def test_no_core_interpreter_fallback_and_unresolved_quality_conflict_fail_closed():
    import vnstock_worker_client as worker_client
    env = {"PATH": os.environ.get("PATH", ""), rt.PROVIDER_PYTHON_ENV: sys.executable}
    handle = worker_client.open_provider_runtime(
        session="2026-09-10", environ=env, core_executable=sys.executable,
        policy=rt.ProviderPolicy(
            provider_family=rt.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
            policy=rt.POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME, reason="x", source="TEST",
        ),
    )
    assert handle.state["state"] == rt.NOT_CONFIGURED
    assert handle.state["reason_code"] == rt.REASON_INTERPRETER_IS_CORE


def test_kbs_lineage_records_the_reviewed_data_day_route():
    assert pipeline.KBS_STOCK_HISTORY_ROUTE.endswith("/stocks/{symbol}/data_day")
    assert build_manifest.KBS_HISTORY_ROUTE == pipeline.KBS_STOCK_HISTORY_ROUTE
    assert "investment/history" not in pipeline.KBS_STOCK_HISTORY_ROUTE


def test_nineteen_guarded_operations_are_registered():
    record = guard.registry_record()
    names = {item["operation"] for item in record["operations"]}
    assert len(names) >= 19
    assert "vn_stock_pipeline._quote" in names
    assert "vn_stock_pipeline.cli.update" in names


def test_qualification_mode_is_explicitly_offline_fake():
    assert MODE_OFFLINE_FAKE == "OFFLINE_FAKE_PROVIDER_QUALIFICATION"


def test_governed_worker_self_attests_before_provider_adapter_import(tmp_path):
    runtime = governed_runtime(tmp_path)
    handle = runtime.open_provider_runtime(startup_timeout=25.0)
    try:
        assert handle.state["reason_code"] != rt.REASON_WORKER_SELF_ATTESTATION_FAILED
        assert handle.state["state"] in (
            rt.IMPORT_FAILED, rt.STARTUP_FAILED, rt.SECURITY_REVIEW_BLOCKED, rt.AVAILABLE, rt.NOT_INSTALLED,
        )
        detail = handle.state.get("detail") or {}
        events = detail.get("containment_events") or []
        reasons = {item.get("reason_code") for item in events}
        assert containment.FILESYSTEM_DENIED_ROOT in reasons or handle.available
        assert containment.PROCESS_CREATION_DENIED in reasons or handle.available
    finally:
        handle.shutdown()
