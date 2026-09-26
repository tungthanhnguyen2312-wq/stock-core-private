"""Offline fake provider qualification (APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1).

This tool is NOT live provider qualification and MUST NOT be confused with one. The only
mode implemented in this milestone is:

    OFFLINE_FAKE_PROVIDER_QUALIFICATION

Gate A is a static preflight of a fake (or tracked DRAFT) build. Gate B launches the fake
provider runtime under containment. Gates C/D/E remain unavailable until an owner approval.

    python tools/run_provider_qualification.py
    python tools/run_provider_qualification.py --gate A
    python tools/run_provider_qualification.py --gate B
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS = ROOT / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import provider_build_manifest as build_manifest  # noqa: E402
import provider_runtime_state as runtime_contract  # noqa: E402

MODE = "OFFLINE_FAKE_PROVIDER_QUALIFICATION"
CONTRACT_VERSION = "provider_qualification/v1-offline-fake"
GATE_A = "A_STATIC_PREFLIGHT"
GATE_B = "B_CONTAINMENT_FAKE"
GATES_UNAVAILABLE = {
    "C": "QUALIFICATION_GATE_C_AUTH_PROBE_UNAVAILABLE_UNTIL_OWNER_APPROVAL",
    "D": "QUALIFICATION_GATE_D_EXACT_SESSION_UNAVAILABLE_UNTIL_OWNER_APPROVAL",
    "E": "QUALIFICATION_GATE_E_QUALITY_LICENSE_UNAVAILABLE_UNTIL_OWNER_APPROVAL",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(code: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, **detail}


def gate_a_tracked_draft() -> dict[str, Any]:
    """Static preflight of the tracked DRAFT manifest. Expected: not approved, not launchable."""
    reasons: list[dict[str, Any]] = []
    policy = runtime_contract.load_provider_policy()
    if policy.policy != runtime_contract.POLICY_SECURITY_REVIEW_BLOCKED:
        reasons.append(_fail("POLICY_NOT_SECURITY_REVIEW_BLOCKED", policy=policy.policy))
    if policy.approved_manifest_sha256 or policy.decision_id:
        reasons.append(_fail("POLICY_PIN_POPULATED_WHILE_BLOCKED"))
    try:
        manifest, digest = build_manifest.load_manifest()
    except build_manifest.ProviderBuildManifestError as exc:
        return {
            "gate": GATE_A, "mode": MODE, "verdict": "FAIL",
            "reason_codes": [exc.reason_code], "failures": exc.failures,
        }
    if manifest.get("status") != build_manifest.STATUS_DRAFT:
        reasons.append(_fail("TRACKED_MANIFEST_NOT_DRAFT", status=manifest.get("status")))
    if manifest.get("launch_authorized") is not False:
        reasons.append(_fail("TRACKED_MANIFEST_LAUNCH_AUTHORIZED"))
    if manifest.get("approval") is not None:
        reasons.append(_fail("TRACKED_MANIFEST_HAS_APPROVAL"))
    lock, lock_digest = build_manifest.load_dependency_lock()
    if (manifest.get("dependency_lock") or {}).get("sha256") != lock_digest:
        reasons.append(_fail("DEPENDENCY_LOCK_DIGEST_STALE", lock=lock_digest))
    identity = build_manifest.canonical_sha256({
        "mode": MODE, "gate": GATE_A, "manifest_sha256": digest, "lock_sha256": lock_digest,
        "policy": policy.policy,
    })
    return {
        "gate": GATE_A, "mode": MODE, "verdict": "PASS" if not reasons else "FAIL",
        "reason_codes": [item["code"] for item in reasons] or ["TRACKED_DRAFT_PREFLIGHT_PASS"],
        "failures": reasons,
        "identity": identity,
        "manifest_sha256": digest,
        "dependency_lock_sha256": lock_digest,
        "lock_approval_state": lock.get("approval_state"),
        "policy": policy.policy,
        "request_budget": {"max_seconds": 0, "max_total_http": 0},
        "live_qualification": False,
    }


def live_candidate_blockers(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """What stops ``manifest`` from being a live-launch candidate (Gates C/D/E, ordinary Daily):
    approval state, mandatory OS containment + egress gateway, credential/rate binding, telemetry,
    and fake (test-fixture) containment evidence. Empty = no static blocker."""
    blockers: list[dict[str, Any]] = []
    if manifest.get("status") != build_manifest.STATUS_APPROVED or manifest.get("launch_authorized") is not True:
        blockers.append(_fail("BUILD_NOT_APPROVED", status=manifest.get("status")))
    blockers += build_manifest.os_containment_violations(manifest)
    blockers += build_manifest.egress_gateway_violations(manifest, approved=True)
    credential = manifest.get("vendor_credential") or {}
    if credential.get("mechanism") not in build_manifest.CREDENTIAL_MECHANISMS:
        blockers.append(_fail(build_manifest.R_CREDENTIAL_CONTRACT_INVALID, error="credential mechanism unresolved"))
    else:
        blockers += build_manifest.rate_binding_violations(manifest.get("rate_tier_binding"), credential)
    for index, entry in enumerate(manifest.get("telemetry_disposition") or []):
        if entry.get("decision") not in (build_manifest.TELEMETRY_DENY, build_manifest.TELEMETRY_ALLOW):
            blockers.append(_fail(build_manifest.R_TELEMETRY_UNRESOLVED, field=f"telemetry_disposition[{index}]"))
    if build_manifest._containment_evidence_is_fake(manifest):
        blockers.append(_fail(build_manifest.R_OS_CONTAINMENT_FAKE_EVIDENCE, error="test-fixture containment evidence"))
    return blockers


def gate_a_live_candidate(manifest_path: Path | None = None) -> dict[str, Any]:
    """Gate A for a LIVE candidate: FAIL while any mandatory containment/credential contract is
    unresolved. (The tracked DRAFT is expected to fail this -- it is not a live candidate yet.)"""
    try:
        manifest, digest = build_manifest.load_manifest(manifest_path)
    except build_manifest.ProviderBuildManifestError as exc:
        return {"gate": GATE_A, "mode": MODE, "verdict": "FAIL", "reason_codes": [exc.reason_code],
                "failures": exc.failures, "live_qualification": False}
    blockers = live_candidate_blockers(manifest)
    return {
        "gate": GATE_A, "mode": MODE, "scope": "LIVE_CANDIDATE",
        "verdict": "FAIL" if blockers else "PASS",
        "reason_codes": sorted({item["code"] for item in blockers}) or ["LIVE_CANDIDATE_STATIC_PREFLIGHT_PASS"],
        "failures": blockers, "manifest_sha256": digest, "live_qualification": False,
    }


def gate_a_fake(runtime) -> dict[str, Any]:
    """Static preflight of a fake attested runtime (interpreter, lock, containment contract)."""
    reasons: list[dict[str, Any]] = []
    try:
        manifest, digest = build_manifest.load_manifest(runtime.manifest_path)
    except build_manifest.ProviderBuildManifestError as exc:
        return {"gate": GATE_A, "mode": MODE, "verdict": "FAIL", "reason_codes": [exc.reason_code],
                "failures": exc.failures, "live_qualification": False}
    if digest != runtime.policy.approved_manifest_sha256:
        reasons.append(_fail("FAKE_POLICY_PIN_MISMATCH"))
    failures = build_manifest.attest_runtime_static(
        manifest, configured_executable=runtime.interpreter,
        manifest_dir=runtime.manifest_path.parent, producer_root=ROOT,
        worker_script=ROOT / manifest["worker"]["entrypoint"],
    )
    reasons.extend(failures)
    identity = build_manifest.canonical_sha256({
        "mode": MODE, "gate": GATE_A, "manifest_sha256": digest, "style": runtime.style,
    })
    return {
        "gate": GATE_A, "mode": MODE, "verdict": "PASS" if not reasons else "FAIL",
        "reason_codes": [item["code"] for item in reasons] or ["FAKE_STATIC_PREFLIGHT_PASS"],
        "failures": reasons, "identity": identity, "manifest_sha256": digest,
        "interpreter": runtime.interpreter, "live_qualification": False,
        "request_budget": manifest.get("launch_mode", {}).get("request_budget"),
        "containment_evidence": "TEST_FIXTURE_ONLY_NOT_OWNER_VERIFIED",
        "live_candidate_blockers": sorted({item["code"] for item in live_candidate_blockers(manifest)}),
    }


def gate_b_fake(runtime) -> dict[str, Any]:
    """Contained fake-worker launch: bounded startup, denials, deterministic shutdown."""
    budget = {"max_seconds": 20, "max_total_http": 0}
    handle = runtime.open_provider_runtime(startup_timeout=20.0)
    try:
        available = bool(handle.available)
        state = handle.final_state()
        events = ((handle.fetcher.worker_diagnostics() if handle.fetcher else {}) or {}).get("containment_events") or []
    finally:
        handle.shutdown()
    if not available:
        return {
            "gate": GATE_B, "mode": MODE, "verdict": "FAIL",
            "reason_codes": [state.get("reason_code") or "FAKE_WORKER_NOT_AVAILABLE"],
            "state": state, "live_qualification": False, "request_budget": budget,
        }
    identity = build_manifest.canonical_sha256({
        "mode": MODE, "gate": GATE_B, "manifest_sha256": runtime.manifest_sha256, "style": runtime.style,
    })
    return {
        "gate": GATE_B, "mode": MODE, "verdict": "PASS",
        "reason_codes": ["FAKE_CONTAINED_STARTUP_PASS"],
        "identity": identity, "state": state, "containment_events": events,
        "live_qualification": False, "request_budget": budget,
        "containment_evidence": "TEST_FIXTURE_ONLY_NOT_OWNER_VERIFIED",
        "authorizes_live_launch": False,
        "note": "Fake worker protocol launch. Not a live provider qualification, not owner-verified OS "
                "containment, not Gates C/D/E and not ordinary-Daily qualification.",
    }


def unavailable_live_gate(letter: str) -> dict[str, Any]:
    return {
        "gate": letter, "mode": MODE, "verdict": "UNAVAILABLE",
        "reason_codes": [GATES_UNAVAILABLE[letter]],
        "live_qualification": False,
    }


def run(*, gate: str = "ALL") -> dict[str, Any]:
    from _provider_build_fixtures import protocol_runtime

    results: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "mode": MODE, "generated_at_utc": _now(),
        "live_qualification": False, "provider_build_approved": False,
    }
    if gate in ("A", "ALL"):
        results["gate_a_tracked_draft"] = gate_a_tracked_draft()
        results["gate_a_fake"] = gate_a_fake(protocol_runtime())
        # Reported, not a gate verdict of this offline run: the tracked DRAFT is not a live candidate.
        live = gate_a_live_candidate()
        results["live_candidate_readiness"] = {
            "scope": "TRACKED_MANIFEST_AS_LIVE_CANDIDATE", "state": "BLOCKED" if live["verdict"] != "PASS" else "READY",
            "reason_codes": live["reason_codes"],
        }
    if gate in ("B", "ALL"):
        results["gate_b_fake"] = gate_b_fake(protocol_runtime())
    for letter in ("C", "D", "E"):
        if gate in (letter, "ALL"):
            results[f"gate_{letter.lower()}"] = unavailable_live_gate(letter)
    failed = [
        name for name, payload in results.items()
        if isinstance(payload, dict) and payload.get("verdict") == "FAIL"
    ]
    results["verdict"] = "FAIL" if failed else "PASS"
    results["failed_gates"] = failed
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", choices=("A", "B", "C", "D", "E", "ALL"), default="ALL")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(gate=args.gate)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PROVIDER_QUALIFICATION {report['verdict']} mode={MODE}")
        for key, payload in report.items():
            if isinstance(payload, dict) and "verdict" in payload and key != "verdict":
                print(f"  {key}: {payload['verdict']} {payload.get('reason_codes')}")
        print("live_qualification=NO provider_build_approved=NO")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
