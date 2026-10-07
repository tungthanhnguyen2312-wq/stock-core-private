"""OWNER_DAILY_20261005_END_TO_END_RECOVERY: regressions for the late-stage seams.

2026-10-05's rerun completed Canonical Daily, then failed AI handoff with
AI_HANDOFF_REQUIRED_FILE_MISSING. Two defects:

1. Rerun selection: the first attempt's own after-close rollforward retained a newer, post-cutoff
   official event context; the rerun picked only the newest directory, found it not known by the
   15:00 cutoff, and dropped the eligible earlier context. Without an event context the operation
   (by design) builds no opportunity decision queue.
2. Handoff contract: the producer attaches the queue only when the session registers both optional
   inputs, but the handoff hard-required the file. The sealed operation manifest now decides.

The acceptance tests drive ``run_workflow`` on the completed-session resume path through the REAL
``publish_ai_handoff`` -> ``ai_handoff_publication.publish`` (a real Git repository pushed to a
real bare origin) -> ``verify_remote_publication``; every previous workflow test mocked that
boundary, which is why this escaped.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import ai_handoff_publication as handoff
import canonical_post_close_pipeline as pipeline
import current_official_event_context as event_context
import owner_daily_journal as journal
import post_handoff_presentation_attestation as presentation_attestation
from daily_research_session_operations import _identity as operation_identity_of
from tools import run_owner_daily as workflow

SESSION = "2026-10-05"
QUEUE = "daily_opportunity_decision_queue_artifact.json"
QUEUE_IDENTITY = "daily_opportunity_decision_queue:" + "a" * 64


def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "core.longpaths", "true")  # pytest tmp paths; production paths are short
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("x\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-qm", "init")


def _handoff_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "remote" / "stocklookup-ai-handoffs.git"
    origin.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    repo = tmp_path / "stocklookup-ai-handoffs"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _operation(root: Path, *, declare_queue: bool, write_queue: bool, session: str = SESSION,
               queue_identity: str = QUEUE_IDENTITY) -> tuple[Path, str]:
    """A completed, sealed, pre-M1-shaped operation: the manifest recomputes to its identity."""
    outputs = {"daily_product": "current_daily_decision_research_product:test"}
    if declare_queue:
        outputs["daily_opportunity_decision_queue"] = QUEUE_IDENTITY
    manifest = {"market_session": session, "producer_head": "producer", "outputs": outputs,
                "coverage_summary": {}}
    manifest["operation_identity"] = operation_identity_of(manifest)
    source = root / "operations-review" / "daily-research-session-operations-v1" / SESSION / manifest["operation_identity"].split(":")[1]
    source.mkdir(parents=True)
    (source / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "ai_research_session_bundle.json").write_text(json.dumps({"session": session}), encoding="utf-8")
    (source / "ai_research_bundle_manifest.json").write_text(json.dumps({
        "operation_identity": manifest["operation_identity"], "producer_head": "producer",
        "daily_product_identity": "current_daily_decision_research_product:test", "session": session}), encoding="utf-8")
    if write_queue:
        (source / QUEUE).write_text(json.dumps({"artifact_identity": queue_identity}), encoding="utf-8")
    return source, manifest["operation_identity"]


def _completed_session(root: Path, **kwargs) -> tuple[Path, Path]:
    _init_repo(root)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "daily_research_session_input_registry.json").write_text(json.dumps({
        "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}}}), encoding="utf-8")
    source, operation_identity = _operation(root, **kwargs)
    record_path = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps({
        "session": SESSION, "daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
        "runtime_release_status": "READY", "trusted_subset_status": "READY",
        "acquisition": {"resolved_completed_session": SESSION}, "daily_producer_run_identity": "run:test",
        "daily_producer_operation_identity": operation_identity, "operation_identity": "canonical:test",
        "prospective_decision_snapshot": {"status": "RETAINED", "identity": "prospective_decision_snapshot:original",
                                          "source_integrated_decision_identity": "integrated:original"}}), encoding="utf-8")
    # Sealed original T0 / capture / first marker: the resume path must never touch them.
    for relative in ("operations-review/prospective-decision-retention-v1/2026-10-05/original/snapshot.json",
                     "operations-review/prospective-pit-capture-v1/sessions/2026-10-05.json",
                     "operations-review/prospective-pit-capture-v1/first_real_marker.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sealed": relative}), encoding="utf-8")
    presentation_attestation.write_attestation(
        root, SESSION, presentation_projection={"status": "UNAVAILABLE", "session": SESSION, "reason": "TEST_FIXTURE"})
    runtime = root.parent / "runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "bundle_manifest.json").write_text("{}", encoding="utf-8")
    return source, runtime


def _sealed_hashes(root: Path) -> dict[str, str]:
    base = root / "operations-review"
    paths = [*(base / "prospective-decision-retention-v1").rglob("*.json"),
             *(base / "prospective-pit-capture-v1").rglob("*.json")]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.fixture()
def harness(monkeypatch, tmp_path):
    """Everything outside the late-stage boundary is fixed; the handoff boundary is real."""
    calls: list[str] = []
    monkeypatch.setattr(workflow, "_run_daily", lambda *a, **k: pytest.fail("Canonical Daily must not rerun on resume"))
    monkeypatch.setattr(workflow, "_require_host_ready", lambda *a, **k: pytest.fail("replay acquires nothing"))
    real_preflight = workflow.preflight_repository

    def preflight(path, **kwargs):
        if kwargs.get("expected_name") == "stocklookup-ai-handoffs":
            return real_preflight(path, **kwargs)
        return {"head": "producer", "status": "UP_TO_DATE"}

    monkeypatch.setattr(workflow, "preflight_repository", preflight)
    monkeypatch.setattr(workflow, "preflight_consumer_repository", lambda *a, **k: {"head": "consumer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(workflow, "_verify_dashboard_published",
                        lambda *a, **k: {"status": "READY", "expected_session": SESSION, "observed_session": SESSION,
                                         "resume_status": "REUSED_EXISTING_PUBLICATION"})
    monkeypatch.setattr(workflow, "publish_dashboard_release", lambda *a, **k: pytest.fail("Dashboard already published"))
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "materialize_action_center",
                        lambda _root, session: calls.append(f"action_center:{session}") or
                        {"status": "READY", "session": session, "json_path": "ac.json", "view_path": "ac.md", "identity": "ac:test"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda path: calls.append(f"open:{path}") or {"status": "READY"})
    root = tmp_path / "stock-core-private"
    return {"root": root, "handoff": _handoff_repo(tmp_path), "calls": calls}


def _resume(h, runtime):
    return workflow.run_workflow(root=h["root"], runtime_root=runtime, handoff_repo=h["handoff"],
                                 replay_completed_session=SESSION)


def _remote_latest(repo: Path) -> dict:
    return json.loads(_git(repo, "show", "origin/main:LATEST.json"))


def test_resume_completes_phases_6_to_9_without_queue_when_sealed_operation_declares_none(harness):
    _, runtime = _completed_session(harness["root"], declare_queue=False, write_queue=False)
    before = _sealed_hashes(harness["root"])
    result = _resume(harness, runtime)
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert result["ai_handoff"]["remote"]["status"] == "READY_FOR_AI"
    latest = _remote_latest(harness["handoff"])
    assert latest["latest_session"] == SESSION
    assert latest["opportunity_artifact_sha256"] is None
    assert latest["opportunity_decision_queue_status"] == handoff.QUEUE_NOT_DECLARED
    assert latest["producer_lineage"]["opportunity_decision_queue"] == {"status": handoff.QUEUE_NOT_DECLARED}
    files = _git(harness["handoff"], "ls-tree", "-r", "--name-only", "origin/main", latest["immutable_session_path"]).splitlines()
    assert not any(name.endswith(QUEUE) for name in files)
    assert harness["calls"] == [f"action_center:{SESSION}", "open:ac.md"]
    assert journal.read_journal(harness["root"])["stage"] == journal.COMPLETE
    assert _sealed_hashes(harness["root"]) == before


def test_resume_publishes_declared_queue_and_verifies_it_remotely(harness):
    _, runtime = _completed_session(harness["root"], declare_queue=True, write_queue=True)
    result = _resume(harness, runtime)
    assert result["status"] == "PASS"
    latest = _remote_latest(harness["handoff"])
    assert latest["opportunity_artifact_sha256"]
    assert "opportunity_decision_queue_status" not in latest
    assert "opportunity_decision_queue" not in latest["producer_lineage"]


def test_declared_queue_missing_fails_phase_6_naming_the_file_then_resume_is_deterministic(harness, monkeypatch):
    source, runtime = _completed_session(harness["root"], declare_queue=True, write_queue=False)
    before = _sealed_hashes(harness["root"])
    with pytest.raises(workflow.OwnerDailyError, match="AI_HANDOFF_REQUIRED_FILE_MISSING:" + QUEUE):
        _resume(harness, runtime)
    failed = journal.read_journal(harness["root"])
    assert failed["stage"] == journal.DASHBOARD_PUBLISHED and failed["failure"]["stage"] == journal.FAILED
    assert harness["calls"] == []
    assert journal.resumable_state(harness["root"], intended_session=SESSION)["action"] == "RESUME"
    # The producer's own artifact appears (never a copy from another operation). The ordinary owner
    # invocation (no explicit replay flag) auto-resumes the completed session from publication.
    (source / QUEUE).write_text(json.dumps({"artifact_identity": QUEUE_IDENTITY}), encoding="utf-8")
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    result = workflow.run_workflow(root=harness["root"], runtime_root=runtime, handoff_repo=harness["handoff"])
    assert result["status"] == "PASS" and result["daily_status"] == "ALREADY_COMPLETED / RESUMED"
    assert _remote_latest(harness["handoff"])["latest_session"] == SESSION
    assert journal.read_journal(harness["root"])["stage"] == journal.COMPLETE
    assert _sealed_hashes(harness["root"]) == before


def test_declared_queue_with_other_identity_is_refused(harness):
    source, runtime = _completed_session(harness["root"], declare_queue=True, write_queue=True)
    (source / QUEUE).write_text(json.dumps({"artifact_identity": "daily_opportunity_decision_queue:" + "b" * 64}), encoding="utf-8")
    with pytest.raises(handoff.HandoffPublicationError, match="OPPORTUNITY_QUEUE_IDENTITY_MISMATCH"):
        _resume(harness, runtime)
    assert _git(harness["handoff"], "rev-list", "--count", "origin/main") == "1"


def test_undeclared_queue_file_present_is_refused_never_borrowed(tmp_path):
    source, _ = _operation(tmp_path, declare_queue=False, write_queue=True)
    with pytest.raises(handoff.HandoffPublicationError, match="QUEUE_PRESENT_BUT_UNDECLARED"):
        handoff.build_package(source, SESSION, producer_checkpoint="abc")


def test_wrong_session_operation_is_refused_before_publication(harness):
    _, runtime = _completed_session(harness["root"], declare_queue=False, write_queue=False, session="2026-10-02")
    with pytest.raises(workflow.OwnerDailyError):
        _resume(harness, runtime)
    assert _git(harness["handoff"], "rev-list", "--count", "origin/main") == "1"


def test_source_without_sealed_manifest_keeps_legacy_required_queue(tmp_path):
    source = tmp_path / "legacy"
    source.mkdir()
    for name in ("ai_research_session_bundle.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}", encoding="utf-8")
    assert handoff.required_files(source) == handoff.REQUIRED
    with pytest.raises(handoff.HandoffPublicationError, match="HANDOFF_SOURCE_MISSING:" + QUEUE):
        handoff.build_package(source, SESSION, producer_checkpoint="abc")


# --- Defect 1: cutoff-bounded event context selection on a rerun -----------------------------

def _event_context(path: Path, observed_at: str) -> str:
    artifact = {"contract_version": "current_official_event_context/v1",
                "research_session": SESSION,
                "all_current_universe_event_records": [{"ticker": "AAA", "official_observed_at": observed_at}],
                "excluded_noncurrent_or_official_only_event_records": []}
    artifact.update(event_context._identity(artifact))
    path.mkdir(parents=True)
    (path / "current_official_event_context_artifact.json").write_text(json.dumps(artifact), encoding="utf-8")
    return artifact["artifact_identity"]


def test_rerun_keeps_the_eligible_event_context_when_a_post_cutoff_one_is_newer(tmp_path):
    ops = tmp_path / "operations-review"
    eligible = _event_context(ops / "current-official-event-context-integration-v1-20261002", "2026-10-02T08:47:45Z")
    # The first attempt's own after-close rollforward (18:04 ICT = 11:04Z) on the session day.
    _event_context(ops / "current-official-event-context-integration-v1-20261005", "2026-10-05T11:04:29Z")
    # A later-dated directory than the session is never a candidate.
    _event_context(ops / "current-official-event-context-integration-v1-20261006", "2026-10-05T07:00:00Z")
    selected = pipeline.capture_corporate_session_inputs(tmp_path, tmp_path, SESSION)
    assert selected["event_context"]["artifact_identity"] == eligible
    retained = tmp_path / selected["event_context"]["path"]
    assert retained.parent == ops / "corporate-daily-frozen-inputs-v1" / SESSION


def test_newest_context_known_by_cutoff_still_wins(tmp_path):
    ops = tmp_path / "operations-review"
    _event_context(ops / "current-official-event-context-integration-v1-20261002", "2026-10-02T08:47:45Z")
    newest = _event_context(ops / "current-official-event-context-integration-v1-20261005", "2026-10-05T07:59:00Z")
    assert pipeline.capture_corporate_session_inputs(tmp_path, tmp_path, SESSION)["event_context"]["artifact_identity"] == newest


def test_no_context_known_by_cutoff_stays_absent(tmp_path):
    _event_context(tmp_path / "operations-review" / "current-official-event-context-integration-v1-20261005", "2026-10-05T11:04:29Z")
    assert "event_context" not in pipeline.capture_corporate_session_inputs(tmp_path, tmp_path, SESSION)


def test_completed_session_keeps_its_actual_lock(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "daily_research_session_input_registry.json").write_text(json.dumps(
        {"completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE"}}}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "frozen_optional_session_inputs", lambda root, session: {"locked": session})
    _event_context(tmp_path / "operations-review" / "current-official-event-context-integration-v1-20261002", "2026-10-02T08:47:45Z")
    assert pipeline.capture_corporate_session_inputs(tmp_path, tmp_path, SESSION) == {"locked": SESSION}
