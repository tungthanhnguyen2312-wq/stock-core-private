from __future__ import annotations

import json
import os
import inspect
import subprocess
from pathlib import Path

import pytest

from tools import run_owner_daily as workflow
import owner_daily_journal as journal
import post_handoff_presentation_attestation as presentation_attestation
import governed_publication_completion as gpc
from release_checkout_identity import PUBLISHED


SESSION = "2026-09-16"
T0_IDENTITY = "prospective_decision_snapshot:test-t0"
DASHBOARD_SHA = "534e4971edf2b9be62467ce89758b6625544558d"
OTHER_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_REAL_VERIFY_DASHBOARD_PUBLISHED = workflow._verify_dashboard_published


def _write_presentation_attestation(root: Path, session: str = SESSION, *, status: str = "UNAVAILABLE") -> None:
    """Minimal, valid attestation for tests that only need PRESENTATION_BOUND to be earnable
    (BOUND or a legitimate UNAVAILABLE both count -- see presentation_bound_state)."""
    presentation_attestation.write_attestation(
        root, session,
        presentation_projection={"status": status, "session": session, "reason": "TEST_FIXTURE"} if status == "UNAVAILABLE"
        else {"status": "COLLECTED", "session": session, "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
              "workspace_artifact_identity": "workspace:test"},
    )


@pytest.fixture(autouse=True)
def _no_resume_verification_by_default(monkeypatch):
    """CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 4's stage-aware
    resume helpers independently probe REAL external state (the Dashboard's build_info.json, the
    AI handoff repo's own origin/main, the Action Center artifact root under %USERPROFILE%) --
    never journal text. Most tests in this module exercise the publish/materialize functions
    directly via mocks and must never have their outcome depend on whatever real state happens to
    exist elsewhere on the machine running the suite (e.g. a genuine checked-out Dashboard at
    C:\\Projects\\StockLookup\\market-dashboard). Default every verification helper to "not yet
    verified" here; the tests that specifically exercise resume-skip behavior override it."""
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda *a, **k: None)
    # Section 1: presentation UNKNOWN now blocks publication before it starts. Most tests in this
    # module are not exercising presentation semantics at all and must keep reaching PASS/PARTIAL
    # exactly as before -- default the gate to a legitimate non-UNKNOWN outcome here, and let the
    # tests that specifically exercise the presentation gate (or PRESENTATION_BOUND detail)
    # override this explicitly. This is independent of the COMPLETE attestation's own separate
    # re-read of the raw attestation file, which still reflects whatever `_write_presentation_
    # attestation` actually wrote (or its absence) for tests that call it.
    monkeypatch.setattr(workflow, "_presentation_bound_state", lambda *a, **k: "LEGITIMATE_UNAVAILABLE")


def _write_completion(root: Path, *, state="LOCAL_COMPLETE", producer="COMPLETED", runtime="READY", trusted="READY",
                      t0_identity: str | None = T0_IDENTITY) -> Path:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "daily_research_session_input_registry.json").write_text(json.dumps({
        "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}},
    }), encoding="utf-8")
    source = root / "operations-review" / "daily-research-session-operations-v1" / SESSION / "op"
    source.mkdir(parents=True)
    for name in ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json"):
        (source / name).write_text("{}", encoding="utf-8")
    (source / "ai_research_bundle_manifest.json").write_text(json.dumps({"operation_identity": "daily_research_session_operation:test"}), encoding="utf-8")
    record_path = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record_path.parent.mkdir(parents=True)
    record = {
        "session": SESSION, "daily_operation_state": state, "daily_producer_status": producer,
        "runtime_release_status": runtime, "trusted_subset_status": trusted,
        "acquisition": {"resolved_completed_session": SESSION}, "daily_producer_run_identity": "run:test",
        "daily_producer_operation_identity": "daily_research_session_operation:test", "operation_identity": "canonical:test",
    }
    if t0_identity:
        record["prospective_decision_snapshot"] = {
            "status": "RETAINED", "identity": t0_identity,
            "source_integrated_decision_identity": "integrated:test",
        }
        record["lineage"] = {"prospective_decision_snapshot": t0_identity}
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return source


@pytest.mark.parametrize("field,value", [("state", "FAILED"), ("runtime", "NOT_READY"), ("trusted", "NOT_READY")])
def test_completion_gate_refuses_incomplete_daily(tmp_path, field, value):
    kwargs = {field: value}
    _write_completion(tmp_path, **kwargs)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    with pytest.raises(workflow.OwnerDailyError, match="CANONICAL_GATE_FAILED"):
        workflow.verify_daily_completion(tmp_path, runtime, session=SESSION)


def test_completion_gate_returns_exact_source_operation(tmp_path):
    source = _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    result = workflow.verify_daily_completion(tmp_path, runtime, session=SESSION)
    assert result["session"] == SESSION
    assert result["source"] == source


def test_unexpected_post_daily_diff_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "_tracked_changes", lambda _: [" M config/daily_research_session_input_registry.json", " M README.md"])
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md"):
        workflow.commit_daily_state(tmp_path, SESSION)


def test_main_writes_a_result_file_on_an_uncaught_exception(monkeypatch, tmp_path):
    def _boom(**_k):
        raise RuntimeError("SIMULATED_UNEXPECTED_FAILURE")

    monkeypatch.setattr(workflow, "run_workflow", _boom)
    result_path = tmp_path / "result.json"
    code = workflow.main(["--result-path", str(result_path)])
    assert code == 2
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "INTERRUPTED"
    assert "SIMULATED_UNEXPECTED_FAILURE" in payload["reason"]


def test_main_writes_a_result_file_on_keyboard_interrupt_then_reraises(monkeypatch, tmp_path):
    def _interrupt(**_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(workflow, "run_workflow", _interrupt)
    result_path = tmp_path / "result.json"
    with pytest.raises(KeyboardInterrupt):
        workflow.main(["--result-path", str(result_path)])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "INTERRUPTED"
    assert payload["reason"] == "KEYBOARD_INTERRUPT"


def _ready_dashboard(_root, _runtime, session, **_k):
    return {
        "status": "READY", "expected_session": session, "observed_session": session, "build_id": "b",
        "publication_state": PUBLISHED, "release_source_sha": DASHBOARD_SHA,
        "public_byte_identity": "PASS",
        "attestation_identity": "governed_publication_attestation:test",
        "content_identity": "governed_publication_content:test",
    }


def _write_dashboard_build_info(web: Path, session: str = SESSION, *, build_id: str = "abc") -> Path:
    data = web / "data"
    data.mkdir(parents=True, exist_ok=True)
    path = data / "build_info.json"
    path.write_text(json.dumps({
        "market_session": session, "build_id": build_id,
        "investment_workspace": {"status": "CURRENT", "source_session": session},
        "current_decision_cockpit": {"status": "CURRENT", "source_session": session},
    }), encoding="utf-8")
    return path


def _write_governed_publication(
    root: Path, *, session: str = SESSION, sha: str = DASHBOARD_SHA,
    publication_state: str = PUBLISHED, public_byte_identity: str = "PASS",
    proof_session: str | None = None, proof_sha: str | None = None,
    digest: str = "deadbeef", payload_session: str | None = None,
    path_session: str | None = None,
) -> Path:
    payload_session = payload_session if payload_session is not None else session
    path_session = path_session if path_session is not None else session
    proof_session = proof_session if proof_session is not None else payload_session
    proof_sha = (proof_sha if proof_sha is not None else sha).lower()
    record = {
        "schema_version": gpc.CONTRACT_VERSION,
        "session": payload_session,
        "release_source_sha": sha.lower(),
        "publication_state": publication_state,
        "public_byte_identity": public_byte_identity,
        "public_byte_proof": {
            "status": "PASS" if public_byte_identity == "PASS" else "FAIL",
            "session": proof_session,
            "sha": proof_sha,
            "line": f"PUBLIC_BYTE_IDENTITY_PASS session={proof_session} sha={proof_sha}",
        },
        "attestation_digest": digest,
        "attestation_identity": f"governed_publication_attestation:{digest}",
        "content_identity": f"governed_publication_content:{digest}",
    }
    if path_session == payload_session:
        return gpc.write_completion_artifact(root, record)
    directory = gpc._artifact_dir(root, path_session, digest)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "publication_completion.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _pin_dashboard_sha(monkeypatch, sha: str = DASHBOARD_SHA) -> None:
    monkeypatch.setattr(workflow, "resolve_dashboard_origin_main_sha", lambda *a, **k: sha)


def _use_real_dashboard_verifier(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_verify_dashboard_published", _REAL_VERIFY_DASHBOARD_PUBLISHED)


def _pass_publication_mocks(monkeypatch, *, dashboard=None) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    publisher = dashboard or (lambda *a, **k: calls.append("publish") or _ready_dashboard(*a, **k))
    monkeypatch.setattr(workflow, "publish_dashboard_release", publisher)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    return calls


def test_successful_replay_allows_publication_and_reuses_daily(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("publish") or {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: {"status": "READY", "session": session, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert result["dashboard"]["status"] == "READY"
    assert calls == ["publish"]


def test_action_center_receives_the_exact_completed_session(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: seen.append(session) or {"status": "READY", "session": session, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY"})
    assert workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)["status"] == "PASS"
    assert seen == [SESSION]


def test_action_center_failure_is_partial_after_core_success(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "PARTIAL", "reason": "ACTION_CENTER_MATERIALIZATION_FAILED:test"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert result["ai_handoff"]["remote"]["remote_sha"] == "ai"
    assert result["dashboard"]["status"] == "READY"


def test_view_open_failure_is_non_fatal(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "private.json", "view_path": "private.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _path: {"status": "READY_VIEW_OPEN_FAILED", "reason": "VIEW_OPEN_FAILED:test"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PASS"
    assert result["action_center"]["view_open"]["status"] == "READY_VIEW_OPEN_FAILED"


# --- WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: Daily -> Dashboard ---

def test_daily_resolved_session_passed_exactly_into_dashboard_publisher(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen = {}
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    def _capture_and_publish(root, rt, session, **k):
        seen["session"] = session
        return _ready_dashboard(root, rt, session)
    monkeypatch.setattr(workflow, "publish_dashboard_release", _capture_and_publish)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert seen["session"] == SESSION
    assert result["status"] == "PASS"


def test_normal_daily_uses_the_same_dashboard_publication_boundary(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    seen: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: seen.append("daily"))
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: seen.append("dashboard") or _ready_dashboard(*a, **k))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert result["status"] == "PASS"
    assert result["daily_status"] == "COMPLETED"
    assert seen == ["daily", "dashboard"]


def test_stale_dashboard_session_produces_partial_never_pass(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {
        "status": "FAILED", "expected_session": SESSION, "observed_session": "2026-09-15",
        "reason": "DASHBOARD_SESSION_MISMATCH:build_info.market_session='2026-09-15'",
    })
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: pytest.fail("must not open view on PARTIAL"))
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert result["dashboard"]["status"] == "FAILED"
    assert result["dashboard"]["expected_session"] == SESSION
    assert result["dashboard"]["observed_session"] == "2026-09-15"


def test_dashboard_publish_failure_does_not_prevent_ai_handoff_or_action_center(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    calls: list[str] = []
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {"status": "FAILED", "expected_session": SESSION, "observed_session": None, "reason": "x"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("handoff") or {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: calls.append("action_center") or {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    assert result["status"] == "PARTIAL"
    assert calls == ["handoff", "action_center"]
    assert result["ai_handoff"]["remote"]["remote_sha"] == "ai"
    assert result["action_center"]["status"] == "READY"


def test_dashboard_disabled_flag_skips_publication_and_never_fails_workflow(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("must not be called when disabled"))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   replay_completed_session=SESSION, publish_dashboard=False)
    assert result["status"] == "PASS"
    assert result["dashboard"]["status"] == "SKIPPED"


def test_verify_dashboard_session_requires_both_market_and_workspace_session(tmp_path):
    web = tmp_path / "web"; (web / "data").mkdir(parents=True)
    (web / "data" / "build_info.json").write_text(json.dumps({
        "market_session": SESSION,
        "investment_workspace": {"status": "CURRENT", "source_session": "2026-09-15"},
    }), encoding="utf-8")
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "FAILED"
    assert "DASHBOARD_SESSION_MISMATCH" in result["reason"]


def test_verify_dashboard_session_ready_when_both_sessions_match(tmp_path):
    web = tmp_path / "web"; (web / "data").mkdir(parents=True)
    (web / "data" / "build_info.json").write_text(json.dumps({
        "market_session": SESSION, "build_id": "abc",
        "investment_workspace": {"status": "CURRENT", "source_session": SESSION},
        "current_decision_cockpit": {"status": "CURRENT", "source_session": SESSION},
    }), encoding="utf-8")
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "READY"
    assert result["observed_session"] == SESSION


@pytest.mark.parametrize("cockpit", [
    {"status": "CURRENT", "source_session": "2026-09-15"},  # the published 2026-09-24 release shape
    None,                                                   # a release that never proved its cockpit
])
def test_verify_dashboard_session_requires_the_current_cockpit_session(tmp_path, cockpit):
    """M1_LIVE_ACCEPTANCE_CORRECTIVE_V1: a release whose current Decision Cockpit belongs to
    another session (or is unproven) is not a session-coherent Dashboard release."""
    web = tmp_path / "web"; (web / "data").mkdir(parents=True)
    build_info = {"market_session": SESSION, "build_id": "abc",
                  "investment_workspace": {"status": "CURRENT", "source_session": SESSION}}
    if cockpit is not None:
        build_info["current_decision_cockpit"] = cockpit
    (web / "data" / "build_info.json").write_text(json.dumps(build_info), encoding="utf-8")
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "FAILED"
    assert "build_info.current_decision_cockpit.source_session=" in result["reason"]


def test_publish_dashboard_release_invokes_all_group_with_exact_session(monkeypatch, tmp_path):
    """Group `all` (not `whole-market` alone -- see publish_dashboard_release's own docstring
    for why a whole-market-only publish fails the Dashboard's own release-smoke session-
    coherence gate). No `--generate`/provider-acquisition flags, and never a bare `--expected-
    session` omission that would let the child re-resolve "latest" on its own."""
    captured = {}
    stages: list[str] = []

    class _Result:
        returncode = 0
        stdout = (
            "PUBLICATION_STATE=PUBLISHED\n"
            f"SESSION={SESSION}\n"
            f"DASHBOARD_RELEASE_SHA={DASHBOARD_SHA}\n"
            "PUBLIC_BYTE_IDENTITY=PASS\n"
            "ATTESTATION_IDENTITY=governed_publication_attestation:test\n"
            "CONTENT_IDENTITY=governed_publication_content:test\n"
        )
        stderr = ""

    def _fake_run(argv, **kwargs):
        assert stages == ["runtime", "trusted_subset"]
        captured["argv"] = argv
        return _Result()

    def _runtime(*args, **kwargs):
        assert args == (tmp_path, tmp_path / "runtime", SESSION)
        stages.append("runtime")
        return {}

    def _trusted(*args, **kwargs):
        assert args == (tmp_path, tmp_path / "runtime", SESSION)
        stages.append("trusted_subset")
        return {"session": SESSION, "trusted_subset_ready": True}

    monkeypatch.setattr(workflow, "materialize_release_ready_runtime", _runtime)
    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", _trusted)
    monkeypatch.setattr(workflow.subprocess, "run", _fake_run)
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, session: {"status": "READY", "expected_session": session, "observed_session": session})
    web_dir = tmp_path / "web"
    result = workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=web_dir)
    argv = captured["argv"]
    assert any("release_orchestrator.py" in str(part) for part in argv)
    assert "all" in argv
    assert "whole-market" not in argv
    assert "--live" in argv
    assert "--complete-publication" in argv
    assert "--expected-session" in argv and argv[argv.index("--expected-session") + 1] == SESSION
    assert "--generate" not in argv
    assert stages == ["runtime", "trusted_subset"]
    assert result["status"] == "READY"
    assert result["publication_state"] == "PUBLISHED"
    assert result["release_source_sha"] == DASHBOARD_SHA
    assert result["public_byte_identity"] == "PASS"
    assert result["attestation_identity"] == "governed_publication_attestation:test"


def test_publish_dashboard_release_can_skip_complete_publication(monkeypatch, tmp_path):
    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr(workflow, "materialize_release_ready_runtime", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", lambda *a, **k: {})
    monkeypatch.setattr(workflow.subprocess, "run", _fake_run)
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, session: {"status": "READY", "expected_session": session, "observed_session": session})
    workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web", complete_publication=False)
    assert "--complete-publication" not in captured["argv"]


def test_publish_dashboard_release_refuses_missing_trusted_evidence_before_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "materialize_release_ready_runtime", lambda *a, **k: {})
    monkeypatch.setattr(
        workflow, "materialize_canonical_trusted_subset",
        lambda *a, **k: (_ for _ in ()).throw(workflow.CanonicalTrustedSubsetError("STATEMENT_PAYLOAD_ROOT_MISSING")),
    )
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("orchestrator must not run"))

    result = workflow.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web")

    assert result["status"] == "FAILED"
    assert result["expected_session"] == SESSION
    assert result["reason"] == "CANONICAL_TRUSTED_SUBSET_MATERIALIZATION_FAILED:STATEMENT_PAYLOAD_ROOT_MISSING"


def test_verify_dashboard_session_fails_closed_when_build_info_missing(tmp_path):
    web = tmp_path / "web"; web.mkdir()
    result = workflow.verify_dashboard_session(web, SESSION)
    assert result["status"] == "FAILED"
    assert result["observed_session"] is None


def test_failed_daily_prevents_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: (_ for _ in ()).throw(workflow.OwnerDailyError("Canonical Daily", "FAILED")))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("publication must not run"))
    with pytest.raises(workflow.OwnerDailyError, match="FAILED"):
        workflow.run_workflow(root=tmp_path, runtime_root=tmp_path, handoff_repo=tmp_path / "handoff")


def test_workflow_keeps_private_action_center_out_of_publication_and_uses_safe_git_shortcuts():
    source = Path(workflow.__file__).read_text(encoding="utf-8")
    publication = inspect.getsource(workflow.publish_ai_handoff).lower()
    assert "action_center" not in publication
    assert "portfolio" not in publication
    assert "git add ." not in source
    assert "reset --hard" not in source
    assert '"rebase"' not in source
    assert " push --force" not in source
    assert "DAILY_STATE_ALLOWLIST" in source


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _clone_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "stock-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    seed = tmp_path / "seed"; seed.mkdir(); _git(seed, "init", "-q"); _git(seed, "config", "user.email", "test@example.com"); _git(seed, "config", "user.name", "Test")
    (seed / "README.md").write_text("seed\n"); _git(seed, "add", "README.md"); _git(seed, "commit", "-qm", "seed"); _git(seed, "branch", "-M", "main"); _git(seed, "remote", "add", "origin", str(origin)); _git(seed, "push", "-u", "origin", "main")
    root = tmp_path / "stock-core-private"; subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True); _git(root, "checkout", "-q", "main")
    return root, origin


def test_clean_behind_origin_is_fast_forwarded(tmp_path):
    root, origin = _clone_with_origin(tmp_path)
    other = tmp_path / "other"; subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True); _git(other, "checkout", "-q", "main"); _git(other, "config", "user.email", "test@example.com"); _git(other, "config", "user.name", "Test")
    (other / "next.txt").write_text("next\n"); _git(other, "add", "next.txt"); _git(other, "commit", "-qm", "next"); _git(other, "push")
    result = workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    assert result["status"] == "FAST_FORWARDED"
    assert (root / "next.txt").is_file()


def test_dirty_producer_is_refused(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    (root / "README.md").write_text("dirty\n")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")


def test_approved_untracked_runtime_evidence_does_not_block_preflight(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    evidence = root / "data" / "dnse-foreign-flow" / "observations" / "HPG.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}", encoding="utf-8")
    result = workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    assert result["status"] == "UP_TO_DATE"
    assert evidence.is_file()


def test_unsafe_untracked_file_is_refused(tmp_path):
    root, _origin = _clone_with_origin(tmp_path)
    (root / "unexpected_module.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")


# =====================================================================================
# OWNER_DAILY_GIT_PORCELAIN_STATE_PUBLICATION_CORRECTIVE_V1: `_git`'s whole-stdout `.strip()`
# silently ate the leading space of a `git status --porcelain` record whose XY status code
# starts with a space (e.g. " M path" for an unstaged-only modification), shifting every
# downstream fixed-offset `line[3:]` path slice one character into the path. Real, unmocked git
# repos below so this cannot regress silently through a mocked `_tracked_changes` again.
# =====================================================================================

REGISTRY_PATH = "config/daily_research_session_input_registry.json"


def _clone_with_registry(tmp_path: Path, session: str = SESSION) -> tuple[Path, Path]:
    """Like `_clone_with_origin`, but the seeded repo also carries an already-committed
    ``config/daily_research_session_input_registry.json`` with an empty completed-sessions
    ledger, so a test can apply just the session's completion update as an uncommitted change."""
    root, origin = _clone_with_origin(tmp_path)
    registry_dir = root / "config"
    registry_dir.mkdir(exist_ok=True)
    (registry_dir / "daily_research_session_input_registry.json").write_text(
        json.dumps({"completed_sessions": {}}), encoding="utf-8",
    )
    _git(root, "add", REGISTRY_PATH)
    _git(root, "commit", "-qm", "seed registry")
    _git(root, "push")
    return root, origin


def _write_completed_registry(root: Path, session: str = SESSION) -> None:
    (root / REGISTRY_PATH).write_text(
        json.dumps({"completed_sessions": {session: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}}}),
        encoding="utf-8",
    )


def test_tracked_changes_preserves_leading_status_space_for_unstaged_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    lines = workflow._tracked_changes(root)
    assert lines == [" M " + REGISTRY_PATH]
    assert {line[3:] for line in lines} == {REGISTRY_PATH}


def test_commit_daily_state_accepts_real_unstaged_registry_modification(tmp_path):
    root, origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"
    assert workflow._tracked_changes(root) == []
    remote_head = subprocess.run(["git", "-C", str(origin), "rev-parse", "main"], check=True, capture_output=True, text=True).stdout.strip()
    assert remote_head == result["sha"]


def test_commit_daily_state_accepts_staged_only_registry_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    _git(root, "add", REGISTRY_PATH)
    lines = workflow._tracked_changes(root)
    assert lines == ["M  " + REGISTRY_PATH]
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"


def test_commit_daily_state_accepts_staged_and_worktree_registry_modification(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    _git(root, "add", REGISTRY_PATH)
    (root / REGISTRY_PATH).write_text(
        json.dumps({"completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}}, "note": "second edit"}),
        encoding="utf-8",
    )
    lines = workflow._tracked_changes(root)
    assert lines == ["MM " + REGISTRY_PATH]
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"


def test_commit_daily_state_still_rejects_unexpected_tracked_file(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    (root / "README.md").write_text("unexpected change\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md"):
        workflow.commit_daily_state(root, SESSION)


def test_commit_daily_state_still_rejects_mixed_allowlisted_and_unexpected_files(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    (root / "README.md").write_text("unexpected change\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_POST_DAILY_DIFF:README.md") as exc:
        workflow.commit_daily_state(root, SESSION)
    assert REGISTRY_PATH not in str(exc.value)


def test_commit_daily_state_stages_only_allowlisted_path(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    _write_completed_registry(root)
    (root / "scratch_untracked.txt").write_text("ignored by this function\n", encoding="utf-8")
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "COMMITTED"
    committed_files = subprocess.run(
        ["git", "-C", str(root), "show", "--stat", "--pretty=format:", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert REGISTRY_PATH in committed_files
    assert "scratch_untracked.txt" not in committed_files
    # The untracked scratch file must remain on disk, untouched by this function.
    assert (root / "scratch_untracked.txt").is_file()


def test_commit_daily_state_no_change_when_registry_already_matches_committed_state(tmp_path):
    root, _origin = _clone_with_registry(tmp_path)
    result = workflow.commit_daily_state(root, SESSION)
    assert result["status"] == "NO_CHANGE"


# =====================================================================================
# CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1: durable owner-operation
# journal + auto-resume. A hard terminal close/process kill cannot run cleanup code -- the next
# ORDINARY invocation (no --replay-completed-session) must resume from the last durable stage
# without reacquiring/re-running Daily Producer for a session that already fully completed.
# =====================================================================================

def test_auto_resumable_session_none_without_journal(tmp_path):
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    assert workflow._auto_resumable_session(tmp_path, runtime, intended_session=SESSION) is None


def test_auto_resumable_session_none_when_journal_session_not_actually_complete(tmp_path):
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    # No canonical-daily-operation-v1 record exists for SESSION -- verify_daily_completion must
    # fail, so this must never be offered as auto-resumable.
    assert workflow._auto_resumable_session(tmp_path, runtime, intended_session=SESSION) is None


def test_auto_resumable_session_returns_session_when_verifiably_complete(tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    assert workflow._auto_resumable_session(tmp_path, runtime, intended_session=SESSION) == SESSION


def test_auto_resumable_session_none_when_intended_session_unresolved(tmp_path):
    """Section 1: resolution failure must disable auto-resume, never fall back to accepting any
    resolved session (the pre-fix behavior that let a COMPLETE journal be replayed forever)."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    assert workflow._auto_resumable_session(tmp_path, runtime, intended_session=None) is None


def test_auto_resumable_session_none_when_journal_session_is_older_than_intended(tmp_path):
    """Section 1's core regression: a COMPLETE (or merely resumable) journal for an OLDER
    session must never be offered as auto-resumable once a newer session is intended."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    assert workflow._auto_resumable_session(tmp_path, runtime, intended_session="2026-09-23") is None


def test_run_workflow_auto_resumes_without_explicit_replay_flag(monkeypatch, tmp_path):
    """Section 5/13 acceptance: the next ordinary owner invocation resumes without
    --replay-completed-session and never reacquires (never calls _run_daily again) once the
    session already fully completed."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire an already-completed session"))
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    final_journal = journal.read_journal(tmp_path)
    assert final_journal["stage"] == journal.COMPLETE
    assert final_journal["resolved_session"] == SESSION


def test_run_workflow_never_auto_resumes_an_older_session_when_a_newer_one_is_intended(monkeypatch, tmp_path):
    """Section 1's exact regression scenario: COMPLETE journal for session N, but the ordinary
    invocation's own intended session is N+1 -- must START FRESH (reacquire), never replay N."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.COMPLETE)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: "2026-09-23")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    daily_calls: list[str] = []
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: daily_calls.append("acquired"))

    def _latest_completion(_root, _runtime, session=None):
        return {"session": "2026-09-23", "record": {"daily_producer_run_identity": "run:new",
                "daily_producer_operation_identity": "op:new", "operation_identity": "canonical:new"},
                "source": tmp_path / "operations-review" / "daily-research-session-operations-v1" / "2026-09-23" / "op"}

    monkeypatch.setattr(workflow, "verify_daily_completion", _latest_completion)
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda _root, _rt, session, **_k: {
        "status": "READY", "expected_session": session, "observed_session": session, "build_id": "b"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: {"status": "READY", "session": session, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert daily_calls == ["acquired"]
    assert result["status"] == "PASS"
    assert str(result["session"]) == "2026-09-23"
    final_journal = journal.read_journal(tmp_path)
    assert final_journal["resolved_session"] == "2026-09-23"
    assert final_journal["run_id"] != entry["run_id"]


def test_run_workflow_writes_journal_stages_through_to_complete(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    _write_presentation_attestation(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    final_journal = journal.read_journal(tmp_path)
    assert final_journal["stage"] == journal.COMPLETE
    stages = [row["stage"] for row in final_journal["stage_history"]]
    assert stages == [journal.STARTED, journal.SESSION_RESOLVED, journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED,
                      journal.PRESENTATION_BOUND, journal.DASHBOARD_PUBLISHED, journal.AI_HANDOFF_PUBLISHED,
                      journal.ACTION_CENTER_READY, journal.COMPLETE]
    assert final_journal["attestation"]["session"] == SESSION
    assert final_journal["attestation"]["ai_handoff"]["remote_sha"] == "ai"
    assert final_journal["attestation"]["post_handoff_presentation_projection"]["status"] == "UNAVAILABLE"
    assert final_journal["attestation"]["t0_snapshot"]["identity"] == T0_IDENTITY
    assert final_journal["attestation"]["dashboard"]["publication_state"] == PUBLISHED
    assert final_journal["attestation"]["dashboard"]["release_source_sha"] == DASHBOARD_SHA
    assert final_journal["attestation"]["dashboard"]["public_byte_identity"] == "PASS"


# Section 1 / required test 1: UNKNOWN presentation must never record PRESENTATION_BOUND and
# must never reach owner COMPLETE -- no attestation artifact at all (older session, or the
# kernel never wrote one) fails BEFORE publication (Dashboard/AI handoff/Action Center are never
# called), with PARTIAL/BLOCKED, not a fabricated PASS.
def test_unknown_presentation_cannot_reach_owner_complete(monkeypatch, tmp_path):
    _write_completion(tmp_path)  # deliberately no _write_presentation_attestation(...) call
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "_presentation_bound_state", lambda *a, **k: "UNKNOWN")  # exercise the real gate
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("must not publish when presentation is UNKNOWN"))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("must not publish when presentation is UNKNOWN"))
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: pytest.fail("must not materialize when presentation is UNKNOWN"))
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: pytest.fail("must not open view when presentation is UNKNOWN"))

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "PRESENTATION_UNKNOWN_CANNOT_COMPLETE"
    assert result["presentation_state"] == "UNKNOWN"
    final_journal = journal.read_journal(tmp_path)
    stages = [row["stage"] for row in final_journal["stage_history"]]
    assert journal.PRESENTATION_BOUND not in stages
    assert journal.COMPLETE not in stages
    assert stages == [journal.STARTED, journal.SESSION_RESOLVED, journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED]
    assert final_journal["stage"] == journal.PRODUCER_STATE_RETAINED
    assert final_journal["failure"]["stage"] == journal.BLOCKED
    assert final_journal["failure"]["detail"]["reason"] == "PRESENTATION_UNKNOWN_CANNOT_COMPLETE"


def test_run_workflow_partial_advances_to_blocked_not_complete(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: {"status": "FAILED", "expected_session": SESSION, "observed_session": None, "reason": "x"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PARTIAL"
    final_journal = journal.read_journal(tmp_path)
    # Dashboard failure never blocks the independent AI handoff / Action Center steps (existing
    # PARTIAL behavior) -- both still complete and advance the journal; only the final
    # PASS-only COMPLETE stage is withheld, with BLOCKED recorded as failure metadata.
    assert final_journal["stage"] == journal.ACTION_CENTER_READY
    assert final_journal["failure"]["stage"] == journal.BLOCKED


def test_run_workflow_marks_journal_failed_on_exception_and_next_run_resumes_without_reacquisition(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    _write_presentation_attestation(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})

    def boom(*a, **k):
        raise RuntimeError("dashboard publisher exploded")

    monkeypatch.setattr(workflow, "publish_dashboard_release", boom)
    with pytest.raises(RuntimeError, match="exploded"):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    interrupted = journal.read_journal(tmp_path)
    # PRESENTATION_BOUND is recorded once the dedicated attestation proves a real outcome (here:
    # the fixture's legitimate UNAVAILABLE) -- the crash happens one step later, at Dashboard
    # publication.
    assert interrupted["stage"] == journal.PRESENTATION_BOUND
    assert interrupted["failure"]["stage"] == journal.FAILED
    assert "exploded" in interrupted["failure"]["detail"]["reason"]

    # The NEXT ordinary invocation (no explicit replay flag) must resume without reacquiring.
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire on resume"))

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    assert journal.read_journal(tmp_path)["stage"] == journal.COMPLETE


def test_run_workflow_marks_journal_interrupted_on_keyboard_interrupt(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})

    def interrupt(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(workflow, "commit_daily_state", interrupt)
    with pytest.raises(KeyboardInterrupt):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)
    interrupted = journal.read_journal(tmp_path)
    assert interrupted["stage"] == journal.LOCAL_COMPLETE
    assert interrupted["failure"]["stage"] == journal.INTERRUPTED


def test_journal_stage_write_failure_prevents_advancing_to_next_side_effect(monkeypatch, tmp_path):
    """Section 3: a durable-write failure at a stage that GATES a subsequent external side
    effect must stop the workflow BEFORE that side effect, never silently swallow the failure
    and continue (the pre-fix behavior)."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    real_advance = journal.advance

    def _fail_only_on_dashboard_published(root, run_id, stage, **kwargs):
        if stage == journal.DASHBOARD_PUBLISHED:
            raise OSError("disk full")
        return real_advance(root, run_id, stage, **kwargs)

    monkeypatch.setattr(workflow.journal, "advance", _fail_only_on_dashboard_published)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("must not publish -- gated by the failed DASHBOARD_PUBLISHED write"))
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: pytest.fail("must not materialize -- gated by the failed DASHBOARD_PUBLISHED write"))

    with pytest.raises(workflow.OwnerDailyError, match="OWNER_JOURNAL_ADVANCE_FAILED:DASHBOARD_PUBLISHED"):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    final_journal = journal.read_journal(tmp_path)
    # The last stage that WAS durably recorded is PRESENTATION_BOUND (the one immediately before
    # the failed DASHBOARD_PUBLISHED write) -- never advanced past it, and the failure is honestly
    # recorded as FAILED metadata (best-effort; this later write may also fail, which is fine).
    assert final_journal["stage"] == journal.PRESENTATION_BOUND
    assert final_journal["failure"]["stage"] == journal.FAILED
    assert "OWNER_JOURNAL_ADVANCE_FAILED" in final_journal["failure"]["detail"]["reason"]


# =====================================================================================
# Section 2 (required test 2): SESSION_RESOLVED must be durable BEFORE `_run_daily` runs, for a
# genuinely fresh production acquisition (not a replay).
# =====================================================================================

def test_session_resolved_is_durable_before_run_daily_for_a_fresh_acquisition(monkeypatch, tmp_path):
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    seen = {}

    def _run_daily_capture(root, _runtime_root):
        on_disk = journal.read_journal(root)
        seen["stage"] = on_disk["stage"]
        seen["intended_session"] = on_disk["intended_session"]

    monkeypatch.setattr(workflow, "_run_daily", _run_daily_capture)
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    # The stage itself is durable before `_run_daily` runs; `resolved_session` is filled in only
    # once Daily Producer's own gate confirms it right afterwards (see the SESSION_RESOLVED
    # comment in `run_workflow`) -- `intended_session` is what was durably recorded up front.
    assert seen["stage"] == journal.SESSION_RESOLVED
    assert seen["intended_session"] == SESSION
    assert result["status"] == "PASS"
    assert result["daily_status"] == "COMPLETED"
    assert journal.read_journal(tmp_path)["resolved_session"] == SESSION


def test_hard_interruption_after_session_resolved_leaves_a_truthful_journal(monkeypatch, tmp_path):
    """A crash right after SESSION_RESOLVED but before Daily Producer finishes must leave the
    journal honestly at SESSION_RESOLVED, never fabricate LOCAL_COMPLETE."""
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})

    def _boom(*_a):
        raise RuntimeError("hard interruption mid-acquisition")

    monkeypatch.setattr(workflow, "_run_daily", _boom)
    with pytest.raises(RuntimeError, match="hard interruption"):
        workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    interrupted = journal.read_journal(tmp_path)
    assert interrupted["stage"] == journal.SESSION_RESOLVED
    assert interrupted["intended_session"] == SESSION
    assert interrupted["resolved_session"] is None
    assert interrupted["failure"]["stage"] == journal.FAILED


def test_session_resolved_only_journal_still_reacquires_on_next_invocation(monkeypatch, tmp_path):
    """Required test 2: the next invocation must NOT treat a SESSION_RESOLVED-only journal as a
    completed Daily -- it safely retries analytical execution under the existing acquisition
    resume rules (superseding the stale run, never skipping `_run_daily`). Deliberately no
    `_write_completion(tmp_path)` call up front -- unlike LOCAL_COMPLETE-or-later, a genuinely
    SESSION_RESOLVED-only journal means Daily never actually finished, so no completion record
    should exist yet; `_run_daily` itself (mocked) is what makes one appear, exactly as the real
    analytical kernel would."""
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.SESSION_RESOLVED, resolved_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.FAILED, detail={"reason": "simulated hard kill"})

    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    daily_calls: list[str] = []

    def _run_daily_now(root, _runtime_root):
        daily_calls.append("acquired")
        _write_completion(root)

    monkeypatch.setattr(workflow, "_run_daily", _run_daily_now)
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert daily_calls == ["acquired"]
    assert result["status"] == "PASS"
    assert result["daily_status"] == "COMPLETED"
    # A fresh run_id -- the SESSION_RESOLVED-only journal was superseded, never trusted as-is.
    assert journal.read_journal(tmp_path)["run_id"] != entry["run_id"]


def test_different_intended_session_never_reuses_the_prior_journal(monkeypatch, tmp_path):
    """Required test 2: a different intended session always gets its own fresh run_id."""
    entry = journal.start_run(tmp_path, intended_session="2026-09-10")
    journal.advance(tmp_path, entry["run_id"], journal.SESSION_RESOLVED, resolved_session="2026-09-10")
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: None)
    monkeypatch.setattr(workflow, "verify_daily_completion", lambda *_a, **_k: (_ for _ in ()).throw(workflow.OwnerDailyError("Daily completion verification", "SIMULATED_STOP_HERE")))

    with pytest.raises(workflow.OwnerDailyError, match="SIMULATED_STOP_HERE"):
        workflow.run_workflow(root=tmp_path, runtime_root=tmp_path, handoff_repo=tmp_path / "handoff")

    started = journal.read_journal(tmp_path)
    assert started["run_id"] != entry["run_id"]
    assert started["intended_session"] == SESSION


# =====================================================================================
# Section 4 (required tests 5-8): genuine stage-aware resume -- each resumed stage is
# INDEPENDENTLY reverified against real external state, never merely skipped because the journal
# says so.
# =====================================================================================

def test_resume_after_producer_state_retained_reverifies_without_a_new_commit(monkeypatch, tmp_path):
    """Required test 5: `commit_daily_state` itself is the verification -- it re-reads real
    tracked Git state and only skips (returns NO_CHANGE) when that state is already retained,
    never blindly because the journal claims PRODUCER_STATE_RETAINED."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire"))
    commit_calls: list[str] = []
    monkeypatch.setattr(workflow, "commit_daily_state", lambda root, session: commit_calls.append(session) or {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff")

    assert result["status"] == "PASS"
    # Re-verified (called), not blindly skipped -- but re-verification proved no new commit needed.
    assert commit_calls == [SESSION]
    assert result["producer_state"]["status"] == "NO_CHANGE"


def test_resume_after_dashboard_published_skips_republish_when_verified(monkeypatch, tmp_path):
    """Required test 6, valid-proof branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: {
        "status": "READY", "expected_session": SESSION, "observed_session": SESSION,
        "publication_state": PUBLISHED, "release_source_sha": DASHBOARD_SHA,
        "public_byte_identity": "PASS", "build_id": "abc",
        "resume_status": "REUSED_EXISTING_PUBLICATION"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("must not republish once verified"))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert result["dashboard"]["publication_state"] == PUBLISHED
    assert result["dashboard"]["release_source_sha"] == DASHBOARD_SHA
    assert result["dashboard"]["public_byte_identity"] == "PASS"
    assert "ALREADY_PUBLISHED_VERIFIED" not in json.dumps(result["dashboard"])
    assert journal.read_journal(tmp_path)["stage"] == journal.COMPLETE
    assert journal.read_journal(tmp_path)["attestation"]["dashboard"]["publication_state"] == PUBLISHED


def test_resume_after_dashboard_published_republishes_when_verification_fails(monkeypatch, tmp_path):
    """Required test 6, invalid-proof branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: None)
    calls: list[str] = []
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: calls.append("publish") or _ready_dashboard(*a, **k))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert calls == ["publish"]


def test_resume_after_ai_handoff_published_skips_republish_when_verified(monkeypatch, tmp_path):
    """Required test 7, valid-proof branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published", lambda repo, session: {
        "remote_sha": "already-remote", "latest_session": session, "handoff_build_id": "build:already"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: pytest.fail("must not republish once verified"))
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert result["ai_handoff"]["remote"]["remote_sha"] == "already-remote"
    assert journal.read_journal(tmp_path)["stage"] == journal.COMPLETE


def test_resume_after_ai_handoff_published_republishes_when_verification_fails(monkeypatch, tmp_path):
    """Required test 7, invalid-proof branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published", lambda repo, session: None)
    calls: list[str] = []
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: calls.append("publish") or {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert calls == ["publish"]


def test_resume_after_action_center_ready_skips_rebuild_when_verified(monkeypatch, tmp_path):
    """Required test 8, valid-artifact branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda session, **k: {
        "status": "READY", "session": session, "portfolio_status": None,
        "json_path": "already.json", "view_path": "already.md", "identity": "already:identity"})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: pytest.fail("must not rebuild once verified"))
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert result["action_center"]["identity"] == "already:identity"
    assert journal.read_journal(tmp_path)["stage"] == journal.COMPLETE


def test_resume_after_action_center_ready_rebuilds_when_verification_fails(monkeypatch, tmp_path):
    """Required test 8, invalid/missing-artifact branch."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda session, **k: None)
    calls: list[str] = []
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *_a: calls.append("rebuild") or {"status": "READY", "session": SESSION, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})

    result = workflow.run_workflow(root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff", replay_completed_session=SESSION)

    assert result["status"] == "PASS"
    assert calls == ["rebuild"]


# =====================================================================================
# Final bounded corrective: Dashboard resume requires governed PUBLISHED proof, and
# COMPLETE attests exact T0 identity plus Dashboard release SHA / public-byte PASS.
# =====================================================================================

def test_verify_dashboard_published_local_session_without_attestation_returns_none(monkeypatch, tmp_path):
    """A: local build_info matches session, but no governed PUBLISHED attestation."""
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _pin_dashboard_sha(monkeypatch)
    assert _REAL_VERIFY_DASHBOARD_PUBLISHED(web, SESSION, producer_root=tmp_path) is None


def test_verify_dashboard_published_matching_attestation_returns_published_facts(monkeypatch, tmp_path):
    """B: local match + governed PUBLISHED/PASS/exact SHA/session."""
    web = tmp_path / "web"
    _write_dashboard_build_info(web, build_id="build-1")
    _write_governed_publication(tmp_path)
    _pin_dashboard_sha(monkeypatch)
    verified = _REAL_VERIFY_DASHBOARD_PUBLISHED(web, SESSION, producer_root=tmp_path)
    assert verified is not None
    assert verified["status"] == "READY"
    assert verified["publication_state"] == PUBLISHED
    assert verified["release_source_sha"] == DASHBOARD_SHA
    assert verified["public_byte_identity"] == "PASS"
    assert verified["build_id"] == "build-1"
    assert verified["resume_status"] == "REUSED_EXISTING_PUBLICATION"
    assert "ALREADY_PUBLISHED_VERIFIED" not in json.dumps(verified)


def test_verify_dashboard_published_wrong_session_returns_none(monkeypatch, tmp_path):
    """C: governed attestation has the wrong session."""
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path, payload_session="2026-09-01", path_session=SESSION)
    _pin_dashboard_sha(monkeypatch)
    assert _REAL_VERIFY_DASHBOARD_PUBLISHED(web, SESSION, producer_root=tmp_path) is None


def test_verify_dashboard_published_wrong_release_sha_returns_none(monkeypatch, tmp_path):
    """D: governed attestation has the wrong release SHA."""
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path, sha=OTHER_SHA)
    _pin_dashboard_sha(monkeypatch)
    assert _REAL_VERIFY_DASHBOARD_PUBLISHED(web, SESSION, producer_root=tmp_path) is None


@pytest.mark.parametrize("publication_state,public_byte_identity", [
    ("GITHUB_SOURCE_UPDATED", "PASS"),
    ("PUBLISHED", "FAIL"),
    ("CI_FAILED", "PASS"),
    ("PAGES_FAILED", "PASS"),
])
def test_verify_dashboard_published_incomplete_attestation_returns_none(
    monkeypatch, tmp_path, publication_state, public_byte_identity,
):
    """E: GITHUB_SOURCE_UPDATED / CI failed / Pages failed / missing public-byte PASS."""
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(
        tmp_path, publication_state=publication_state, public_byte_identity=public_byte_identity,
    )
    _pin_dashboard_sha(monkeypatch)
    assert _REAL_VERIFY_DASHBOARD_PUBLISHED(web, SESSION, producer_root=tmp_path) is None


def test_resume_local_session_without_governed_proof_calls_publisher(monkeypatch, tmp_path):
    """A + 2: journal may already say DASHBOARD_PUBLISHED; independent proof still required."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.DASHBOARD_PUBLISHED, resolved_session=SESSION)
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire"))
    calls = _pass_publication_mocks(monkeypatch)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web,
    )

    assert result["status"] == "PASS"
    assert calls == ["publish"]
    assert result["dashboard"]["publication_state"] == PUBLISHED


def test_resume_governed_published_proof_skips_publisher(monkeypatch, tmp_path):
    """B + F: matching governed proof skips the publisher and keeps PUBLISHED facts."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web, build_id="build-skip")
    _write_governed_publication(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    calls = _pass_publication_mocks(
        monkeypatch, dashboard=lambda *a, **k: pytest.fail("must not republish once governed proof passes"),
    )

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web, replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    assert calls == []
    assert result["dashboard"]["publication_state"] == PUBLISHED
    assert result["dashboard"]["release_source_sha"] == DASHBOARD_SHA
    assert result["dashboard"]["public_byte_identity"] == "PASS"
    assert result["dashboard"]["resume_status"] == "REUSED_EXISTING_PUBLICATION"
    assert "ALREADY_PUBLISHED_VERIFIED" not in json.dumps(result["dashboard"])
    attestation = journal.read_journal(tmp_path)["attestation"]
    assert attestation["dashboard"]["publication_state"] == PUBLISHED
    assert attestation["dashboard"]["release_source_sha"] == DASHBOARD_SHA
    assert attestation["dashboard"]["public_byte_identity"] == "PASS"


def test_resume_wrong_session_attestation_retries_publisher(monkeypatch, tmp_path):
    """C through workflow."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path, payload_session="2026-09-01", path_session=SESSION)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    calls = _pass_publication_mocks(monkeypatch)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web, replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    assert calls == ["publish"]


def test_resume_wrong_release_sha_attestation_retries_publisher(monkeypatch, tmp_path):
    """D through workflow."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path, sha=OTHER_SHA)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    calls = _pass_publication_mocks(monkeypatch)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web, replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    assert calls == ["publish"]


def test_resume_incomplete_publication_attestation_retries_publisher(monkeypatch, tmp_path):
    """E through workflow: source pushed, remote publication not PUBLISHED."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path, publication_state="GITHUB_SOURCE_UPDATED")
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    calls = _pass_publication_mocks(monkeypatch)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web, replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    assert calls == ["publish"]


def test_owner_complete_attests_exact_t0_identity(monkeypatch, tmp_path):
    """G: final owner COMPLETE contains the exact retained T0 identity."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _pass_publication_mocks(monkeypatch, dashboard=_ready_dashboard)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    t0 = journal.read_journal(tmp_path)["attestation"]["t0_snapshot"]
    assert t0["identity"] == T0_IDENTITY
    assert t0["status"] == "RETAINED"


def test_owner_complete_records_t0_unavailable_for_legacy_record(monkeypatch, tmp_path):
    _write_completion(tmp_path, t0_identity=None)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _pass_publication_mocks(monkeypatch, dashboard=_ready_dashboard)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    t0 = journal.read_journal(tmp_path)["attestation"]["t0_snapshot"]
    assert t0["status"] == "UNAVAILABLE"
    assert t0["identity"] is None
    assert t0["reason"] == "T0_SNAPSHOT_IDENTITY_NOT_RETAINED"


def test_owner_complete_attests_dashboard_proof_on_fresh_publication(monkeypatch, tmp_path):
    """H: fresh publication path records PUBLISHED + release SHA + public-byte PASS."""
    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _pass_publication_mocks(monkeypatch, dashboard=_ready_dashboard)

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    dashboard = journal.read_journal(tmp_path)["attestation"]["dashboard"]
    assert dashboard["publication_state"] == PUBLISHED
    assert dashboard["release_source_sha"] == DASHBOARD_SHA
    assert dashboard["public_byte_identity"] == "PASS"
    assert dashboard.get("resume_status") is None


def test_owner_complete_attests_dashboard_proof_on_verified_resume_skip(monkeypatch, tmp_path):
    """H: verified resume-skip path records the same governed PUBLISHED facts."""
    _write_completion(tmp_path)
    web = tmp_path / "web"
    _write_dashboard_build_info(web)
    _write_governed_publication(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    _use_real_dashboard_verifier(monkeypatch)
    _pin_dashboard_sha(monkeypatch)
    _pass_publication_mocks(
        monkeypatch, dashboard=lambda *a, **k: pytest.fail("must not republish once governed proof passes"),
    )

    result = workflow.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=web, replay_completed_session=SESSION,
    )

    assert result["status"] == "PASS"
    dashboard = journal.read_journal(tmp_path)["attestation"]["dashboard"]
    assert dashboard["publication_state"] == PUBLISHED
    assert dashboard["release_source_sha"] == DASHBOARD_SHA
    assert dashboard["public_byte_identity"] == "PASS"
    assert dashboard["resume_status"] == "REUSED_EXISTING_PUBLICATION"
    assert dashboard["attestation_identity"] == "governed_publication_attestation:deadbeef"



# =====================================================================================
# OWNER_DAILY_CRASH_RECOVERY_CONTRACT_CORRECTIVE_V1: an interrupted Daily whose analytical kernel
# completed legitimately leaves the governed Daily registry as the sole tracked diff awaiting
# `commit_daily_state`, which only runs AFTER `preflight_repository`. Explicit replay / verified
# auto-resume may tolerate exactly that one pending diff (HEAD == origin/main, exact session
# canonically verified); a fresh Daily stays strictly clean. Real, unmocked git repos below.
# =====================================================================================

def _git_out(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def _clone_with_pending_registry(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A producer clone whose kernel completed SESSION but never ran `commit_daily_state`: the
    governed registry is the sole tracked diff, canonical completion evidence is retained under
    the (ignored) operations-review tree, and the runtime release manifest exists."""
    root, origin = _clone_with_registry(tmp_path)
    (root / ".gitignore").write_text("operations-review/\n", encoding="utf-8")
    _git(root, "add", ".gitignore"); _git(root, "commit", "-qm", "ignore evidence"); _git(root, "push")
    _write_completion(root)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}")
    assert workflow._tracked_changes(root) == [" M " + REGISTRY_PATH]
    return root, origin, runtime


def _push_from_other_clone(tmp_path: Path, origin: Path) -> None:
    other = tmp_path / "other"; subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "checkout", "-q", "main"); _git(other, "config", "user.email", "test@example.com"); _git(other, "config", "user.name", "Test")
    (other / "next.txt").write_text("next\n"); _git(other, "add", "next.txt"); _git(other, "commit", "-qm", "next"); _git(other, "push")


def _commit_local_only(root: Path) -> None:
    _git(root, "config", "user.email", "test@example.com"); _git(root, "config", "user.name", "Test")
    (root / "local.txt").write_text("local\n"); _git(root, "add", "local.txt"); _git(root, "commit", "-qm", "local")


def _replay_preflight(root: Path, runtime: Path, session: str | None = SESSION) -> dict[str, str]:
    return workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private",
                                         completed_session=session, runtime_root=runtime)


def _stub_downstream_publication(monkeypatch) -> None:
    # These tests exercise the real Producer preflight's pending-registry path; the sibling
    # Consumer checkout gate has its own real-git tests (test_pre_daily_consumer_and_m1_brief_guards).
    monkeypatch.setattr(workflow, "preflight_consumer_repository", lambda *a, **k: {"head": "consumer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda _root, session: {"status": "READY", "session": session, "json_path": "p.json", "view_path": "p.md"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda _p: {"status": "READY"})


def test_replay_preflight_accepts_sole_pending_registry_for_completed_session(tmp_path):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    head = _git_out(root, "rev-parse", "HEAD")
    result = _replay_preflight(root, runtime)
    assert result == {"head": head, "status": "PENDING_DAILY_STATE_AT_ORIGIN_MAIN"}
    # Preflight itself never mutates the pending registry; commit_daily_state owns that.
    assert workflow._tracked_changes(root) == [" M " + REGISTRY_PATH]
    assert _git_out(root, "rev-parse", "HEAD") == head


@pytest.mark.parametrize("stage_status", ["M ", "MM"])
def test_replay_preflight_accepts_staged_pending_registry(tmp_path, stage_status):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    _git(root, "add", REGISTRY_PATH)
    if stage_status == "MM":
        (root / REGISTRY_PATH).write_text((root / REGISTRY_PATH).read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert workflow._tracked_changes(root) == [stage_status + " " + REGISTRY_PATH]
    assert _replay_preflight(root, runtime)["status"] == "PENDING_DAILY_STATE_AT_ORIGIN_MAIN"


def test_replay_preflight_blocks_a_second_tracked_diff(tmp_path):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    (root / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES:.*README.md"):
        _replay_preflight(root, runtime)


def test_replay_preflight_blocks_a_deleted_registry(tmp_path):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    (root / REGISTRY_PATH).unlink()
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        _replay_preflight(root, runtime)


@pytest.mark.parametrize("relative", ["unexpected_module.py", "config/local_override.json"])
def test_replay_preflight_blocks_unsafe_untracked_path(tmp_path, relative):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    (root / relative).write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        _replay_preflight(root, runtime)


@pytest.mark.parametrize("relationship", ["behind", "ahead", "diverged"])
def test_replay_preflight_blocks_non_origin_head_with_pending_registry_and_never_pulls(tmp_path, relationship):
    root, origin, runtime = _clone_with_pending_registry(tmp_path)
    if relationship in ("behind", "diverged"):
        _push_from_other_clone(tmp_path, origin)
    if relationship in ("ahead", "diverged"):
        _commit_local_only(root)
    head_before = _git_out(root, "rev-parse", "HEAD")
    remote_before = _git_out(origin, "rev-parse", "main")
    with pytest.raises(workflow.OwnerDailyError, match="PENDING_DAILY_STATE_HEAD_NOT_ORIGIN_MAIN"):
        _replay_preflight(root, runtime)
    assert _git_out(root, "rev-parse", "HEAD") == head_before
    assert _git_out(origin, "rev-parse", "main") == remote_before
    assert not (root / "next.txt").exists()
    assert workflow._tracked_changes(root) == [" M " + REGISTRY_PATH]


def test_fresh_daily_preflight_with_dirty_registry_stays_blocked(tmp_path):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES:" + REGISTRY_PATH):
        workflow.preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        _replay_preflight(root, runtime, session=None)


def test_fresh_run_workflow_with_dirty_registry_never_reaches_daily(monkeypatch, tmp_path):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: "2026-09-17")
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("fresh Daily must not start on a dirty checkout"))
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff", publish_dashboard=False)
    assert workflow._tracked_changes(root) == [" M " + REGISTRY_PATH]


@pytest.mark.parametrize("breakage", ["runtime_manifest_missing", "record_not_local_complete", "other_session"])
def test_replay_preflight_requires_exact_session_completion_before_tolerating_registry(tmp_path, breakage):
    root, _origin, runtime = _clone_with_pending_registry(tmp_path)
    session = SESSION
    if breakage == "runtime_manifest_missing":
        (runtime / "bundle_manifest.json").unlink()
    elif breakage == "record_not_local_complete":
        record_path = next((root / "operations-review" / "canonical-daily-operation-v1").glob("*/*/daily_operation_record.json"))
        record = json.loads(record_path.read_text(encoding="utf-8")); record["daily_operation_state"] = "FAILED"
        record_path.write_text(json.dumps(record), encoding="utf-8")
    else:
        session = "2026-09-17"
    with pytest.raises(workflow.OwnerDailyError, match="PENDING_DAILY_STATE_SESSION_NOT_VERIFIED"):
        _replay_preflight(root, runtime, session=session)
    assert workflow._tracked_changes(root) == [" M " + REGISTRY_PATH]


def test_explicit_replay_commits_pending_registry_then_replays_idempotently(monkeypatch, tmp_path):
    root, origin, runtime = _clone_with_pending_registry(tmp_path)
    _stub_downstream_publication(monkeypatch)
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("replay must never reacquire"))
    base = _git_out(origin, "rev-parse", "main")

    first = workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                  publish_dashboard=False, replay_completed_session=SESSION)
    assert first["status"] == "PASS"
    assert first["producer_preflight"]["status"] == "PENDING_DAILY_STATE_AT_ORIGIN_MAIN"
    assert first["producer_state"]["status"] == "COMMITTED"
    assert workflow._tracked_changes(root) == []
    committed = _git_out(origin, "rev-parse", "main")
    assert committed == first["producer_state"]["sha"] != base
    assert _git_out(root, "show", "--name-only", "--pretty=format:", committed) == REGISTRY_PATH
    assert _git_out(origin, "rev-list", "--count", f"{base}..main") == "1"

    second = workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   publish_dashboard=False, replay_completed_session=SESSION)
    assert second["status"] == "PASS"
    assert second["producer_preflight"]["status"] == "UP_TO_DATE"
    assert second["producer_state"] == {"status": "NO_CHANGE", "sha": committed}
    assert _git_out(origin, "rev-parse", "main") == committed


def test_verified_auto_resume_commits_pending_registry_after_post_kernel_crash(monkeypatch, tmp_path):
    """Hard kill after the kernel completed (journal durably at SESSION_RESOLVED with the confirmed
    session -- the 368dbbc persistence fix) and before `commit_daily_state`: the next ORDINARY
    invocation must auto-resume, commit the pending registry exactly once, and never reacquire."""
    root, origin, runtime = _clone_with_pending_registry(tmp_path)
    entry = journal.start_run(root, intended_session=SESSION)
    journal.advance(root, entry["run_id"], journal.SESSION_RESOLVED)
    journal.advance(root, entry["run_id"], journal.SESSION_RESOLVED, resolved_session=SESSION)
    assert journal.resumable_state(root, intended_session=SESSION)["action"] == "RESUME"
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "_run_daily", lambda *a: pytest.fail("must not reacquire an already-completed session"))
    _stub_downstream_publication(monkeypatch)
    base = _git_out(origin, "rev-parse", "main")

    result = workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff", publish_dashboard=False)

    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    assert result["producer_preflight"]["status"] == "PENDING_DAILY_STATE_AT_ORIGIN_MAIN"
    assert result["producer_state"]["status"] == "COMMITTED"
    assert _git_out(origin, "rev-list", "--count", f"{base}..main") == "1"
    assert workflow._tracked_changes(root) == []
    final_journal = journal.read_journal(root)
    assert final_journal["stage"] == journal.COMPLETE
    assert final_journal["resolved_session"] == SESSION


# =====================================================================================
# OWNER_DAILY_CRASH_RECOVERY_CONTRACT_CORRECTIVE_V1 -- result-path self-poisoning: a
# `--result-path` inside the Producer checkout leaves an untracked file that makes the NEXT
# Daily/replay fail UNSAFE_UNTRACKED_CHECKOUT. It is refused before any workflow work, and the
# refusal itself never creates the file.
# =====================================================================================

def _fake_checkout(tmp_path: Path, monkeypatch) -> Path:
    checkout = tmp_path / "stock-core-private"
    checkout.mkdir()
    monkeypatch.setattr(workflow, "ROOT", checkout)
    monkeypatch.setattr(workflow, "run_workflow",
                        lambda **_k: pytest.fail("material workflow must not start for a refused result path"))
    return checkout


@pytest.mark.parametrize("relative", ["result.json", "run-logs/x.json", "data/dnse-foreign-flow/result.json"])
def test_result_path_inside_producer_checkout_is_refused_before_material_work(tmp_path, monkeypatch, capsys, relative):
    checkout = _fake_checkout(tmp_path, monkeypatch)
    target = checkout / relative
    code = workflow.main(["--result-path", str(target)])
    assert code == 1
    assert "OWNER_DAILY_RESULT_PATH_REJECTED=RESULT_PATH_INSIDE_PRODUCER_CHECKOUT" in capsys.readouterr().err
    assert not target.exists()
    assert list(checkout.iterdir()) == []  # not even a parent directory was created


@pytest.mark.parametrize("spelling", ["outside/../stock-core-private/run-logs/x.json",
                                      "stock-core-private/./nested/../run-logs/x.json"])
def test_result_path_normalization_cannot_bypass_the_guard(tmp_path, monkeypatch, spelling):
    checkout = _fake_checkout(tmp_path, monkeypatch)
    (tmp_path / "outside").mkdir()
    raw = str(tmp_path) + "/" + spelling
    with pytest.raises(workflow.OwnerDailyError, match="RESULT_PATH_INSIDE_PRODUCER_CHECKOUT"):
        workflow.validate_result_path(Path(raw), root=checkout)
    assert workflow.main(["--result-path", raw]) == 1
    assert list(checkout.iterdir()) == []


def test_result_path_guard_is_case_insensitive_where_the_filesystem_is(tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path, monkeypatch)
    if os.path.normcase("A") != os.path.normcase("a"):
        pytest.skip("case-sensitive filesystem")
    upper = Path(str(checkout).upper()) / "run-logs" / "x.json"
    with pytest.raises(workflow.OwnerDailyError, match="RESULT_PATH_INSIDE_PRODUCER_CHECKOUT"):
        workflow.validate_result_path(upper, root=checkout)


def test_sibling_directory_sharing_the_checkout_name_prefix_is_accepted(tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path, monkeypatch)
    sibling = tmp_path / "stock-core-private-run-logs" / "x.json"
    assert workflow.validate_result_path(sibling, root=checkout) == sibling.resolve()


def test_external_result_path_is_accepted_and_written_unchanged(tmp_path, monkeypatch):
    checkout = tmp_path / "stock-core-private"
    checkout.mkdir()
    monkeypatch.setattr(workflow, "ROOT", checkout)
    monkeypatch.setattr(workflow, "run_workflow", lambda **_k: {"status": "PASS", "session": SESSION})
    target = tmp_path / "owner-daily-run-logs" / "run.result.json"
    assert workflow.main(["--result-path", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "PASS", "session": SESSION}
    assert list(checkout.iterdir()) == []


def test_result_path_guard_leaves_governed_untracked_data_semantics_unchanged(tmp_path):
    """The guard is a CLI argument check only: approved runtime/evidence under data/ still passes
    the (unchanged) shared cleanliness contract and repository preflight."""
    import checkout_cleanliness_contract as cleanliness
    assert "data/dnse-foreign-flow/" in cleanliness.APPROVED_RUNTIME_EVIDENCE_PREFIXES
    root, _origin = _clone_with_origin(tmp_path)
    evidence = root / "data" / "dnse-foreign-flow" / "observations" / "HPG.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}", encoding="utf-8")
    assert cleanliness.classify_checkout_cleanliness(root).qualified is True
    assert workflow.preflight_repository(root, expected_name="stock-core-private",
                                         expected_remote_fragment="stock-core-private")["status"] == "UP_TO_DATE"
