"""Fresh Daily may continue one faithful pre-Producer input freeze, and nothing weaker."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import canonical_post_close_pipeline as pipeline
import daily_execution_environment as env
import pending_session_input_freeze as freeze
from tools import run_owner_daily as workflow


SESSION = "2026-10-09"
PRIOR = "2026-10-08"
REGISTRY = freeze.REGISTRY_RELATIVE


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)


def _git_out(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def _porcelain(path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _clone(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "stock-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    (seed / ".gitignore").write_text("operations-review/\n", encoding="utf-8")
    registry = {
        "contract_version": "daily_research_session_input_registry/v1",
        "schema_version": "1.0.0",
        "sessions": {PRIOR: {"descriptive": {"path": "operations-review/old.json", "artifact_identity": "descriptive:old"}}},
        "completed_sessions": {},
    }
    (seed / "config").mkdir()
    (seed / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    _git(seed, "add", "README.md", ".gitignore", REGISTRY)
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    root = tmp_path / "stock-core-private"
    subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True)
    _git(root, "checkout", "-q", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    return root, origin


def _identities() -> dict[str, str]:
    return {key: key + ":frozen" for key in (*freeze.REQUIRED_INPUT_KEYS, *freeze.OPTIONAL_INPUT_KEYS)}


def _write_artifacts(root: Path, identities: dict[str, str]) -> dict[str, dict[str, str]]:
    selection = {}
    for key, identity in identities.items():
        relative = f"operations-review/freeze/{key}.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"artifact_identity": identity}), encoding="utf-8")
        selection[key] = {"path": relative, "artifact_identity": identity}
    return selection


def _apply_freeze(root: Path, *, identities: dict[str, str] | None = None, session: str = SESSION,
                  row_status: str = "COMPLETED_RETAINED_EVIDENCE", trading_day_valid: bool = True) -> dict:
    identities = identities or _identities()
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    registry["sessions"][session] = _write_artifacts(root, identities)
    registry["completed_sessions"][session] = {
        "status": row_status,
        "trading_day_valid": trading_day_valid,
        "frozen_input_identities": identities,
        "completion_evidence": {"basis": "EXACT_SESSION_UPSTREAM_ARTIFACT_REGISTRY"},
    }
    (root / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    return registry


def _preflight(root: Path, **kwargs):
    return workflow.preflight_repository(
        root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private", **kwargs,
    )


def test_required_keys_match_the_post_close_registry_contract():
    assert freeze.REQUIRED_INPUT_KEYS == pipeline.REQUIRED_REGISTRY_KEYS
    assert freeze.OPTIONAL_INPUT_KEYS == pipeline.OPTIONAL_REGISTRY_KEYS


def test_fresh_preflight_admits_exact_freeze_without_committing_or_rewriting(tmp_path):
    root, origin = _clone(tmp_path)
    _apply_freeze(root)
    before = (root / REGISTRY).read_bytes()
    head = _git_out(root, "rev-parse", "HEAD")
    result = _preflight(root)
    assert result == {"head": head, "status": "PENDING_INPUT_FREEZE_AT_ORIGIN_MAIN"}
    assert (root / REGISTRY).read_bytes() == before
    assert _git_out(root, "rev-parse", "HEAD") == head
    assert _git_out(origin, "rev-parse", "main") == head
    assert _porcelain(root) == [" M " + REGISTRY]
    release = env.producer_release_qualification(root)
    assert release["qualified"] is True
    assert release["reason_code"] == "PENDING_INPUT_FREEZE"
    assert release["session"] == SESSION
    assert release["dirty"] is True


def test_fresh_workflow_reaches_daily_and_does_not_commit_the_freeze(monkeypatch, tmp_path):
    root, origin = _clone(tmp_path)
    _apply_freeze(root)
    monkeypatch.setattr(workflow, "preflight_consumer_repository", lambda *a, **k: {"head": "consumer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_require_host_ready", lambda _root: {"classification": "READY"})
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "_run_daily", lambda *a, **k: (_ for _ in ()).throw(
        workflow.OwnerDailyError("Canonical Daily", "STOP_AFTER_GATE")))
    head = _git_out(origin, "rev-parse", "main")
    with pytest.raises(workflow.OwnerDailyError, match="STOP_AFTER_GATE"):
        workflow.run_workflow(
            root=root, runtime_root=tmp_path / "runtime", handoff_repo=tmp_path / "handoff",
            publish_dashboard=False,
        )
    assert _git_out(origin, "rev-parse", "main") == head
    assert _porcelain(root) == [" M " + REGISTRY]


@pytest.mark.parametrize("stage", ["M ", "MM"])
def test_staged_registry_freeze_is_admitted(tmp_path, stage):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    _git(root, "add", REGISTRY)
    if stage == "MM":
        (root / REGISTRY).write_bytes((root / REGISTRY).read_bytes() + b"\n")
    assert _porcelain(root) == [stage + " " + REGISTRY]
    assert _preflight(root)["status"] == "PENDING_INPUT_FREEZE_AT_ORIGIN_MAIN"


def test_identity_mismatch_and_missing_artifact_stay_blocked(tmp_path):
    root, _origin = _clone(tmp_path)
    identities = _identities()
    identities["tactical"] = "tactical:rewritten"
    _apply_freeze(root, identities=identities)
    # Selection was written with the rewritten identity, so align the lock to a different value.
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    registry["completed_sessions"][SESSION]["frozen_input_identities"]["tactical"] = "tactical:frozen"
    (root / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).reason_code == "ARTIFACT_IDENTITY_MISMATCH"
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES:" + REGISTRY):
        _preflight(root)
    assert env.producer_release_qualification(root)["reason_code"] == "RELEASE_CHECKOUT_DIRTY"

    (root / "operations-review" / "freeze" / "tactical.json").unlink()
    registry["sessions"][SESSION]["tactical"]["artifact_identity"] = "tactical:frozen"
    registry["completed_sessions"][SESSION]["frozen_input_identities"]["tactical"] = "tactical:frozen"
    (root / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).reason_code == "ARTIFACT_IDENTITY_MISMATCH"


@pytest.mark.parametrize("mutate", ["second_file", "older_session", "drop_required", "unknown_key", "false_completion"])
def test_weaker_registry_diffs_stay_blocked(tmp_path, mutate):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    if mutate == "second_file":
        (root / "README.md").write_text("dirty\n", encoding="utf-8")
    elif mutate == "older_session":
        registry["sessions"][PRIOR]["descriptive"]["artifact_identity"] = "descriptive:changed"
    elif mutate == "drop_required":
        registry["sessions"][SESSION].pop("catalyst")
        registry["completed_sessions"][SESSION]["frozen_input_identities"].pop("catalyst")
    elif mutate == "unknown_key":
        registry["sessions"][SESSION]["promoted_lane"] = {"path": "operations-review/freeze/catalyst.json", "artifact_identity": "catalyst:frozen"}
        registry["completed_sessions"][SESSION]["frozen_input_identities"]["promoted_lane"] = "catalyst:frozen"
    else:
        registry["completed_sessions"][SESSION]["status"] = "LOCAL_COMPLETE"
    if mutate != "second_file":
        (root / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).admitted is False
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        _preflight(root)
    assert env.producer_release_qualification(root)["qualified"] is False
    assert env.producer_release_qualification(root)["reason_code"] == "RELEASE_CHECKOUT_DIRTY"


@pytest.mark.parametrize("state", ["LOCAL_COMPLETE", "PUBLISHED"])
def test_sealed_operation_keeps_the_fresh_path_blocked(tmp_path, state):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    record = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"session": SESSION, "daily_operation_state": state}), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).reason_code == "SEALED_OPERATION_PRESENT"
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES:" + REGISTRY):
        _preflight(root)
    assert env.producer_release_qualification(root)["reason_code"] == "RELEASE_CHECKOUT_DIRTY"


def test_failed_operation_record_does_not_block_the_input_freeze(tmp_path):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    record = root / "operations-review" / "canonical-daily-operation-v1" / SESSION / "op" / "daily_operation_record.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"session": SESSION, "daily_operation_state": "FAILED"}), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).admitted is True
    assert _preflight(root)["status"] == "PENDING_INPUT_FREEZE_AT_ORIGIN_MAIN"


def test_unsafe_untracked_still_blocks_a_valid_freeze(tmp_path):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    (root / "unexpected_module.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        _preflight(root)
    assert env.producer_release_qualification(root)["reason_code"] == "RELEASE_CHECKOUT_DIRTY"


def test_path_escape_is_not_an_admitted_freeze(tmp_path):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"artifact_identity": "catalyst:frozen"}), encoding="utf-8")
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    registry["sessions"][SESSION]["catalyst"]["path"] = "../outside.json"
    (root / REGISTRY).write_text(json.dumps(registry), encoding="utf-8")
    assert freeze.classify_pending_input_freeze(root).reason_code == "ARTIFACT_IDENTITY_MISMATCH"
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        _preflight(root)


def test_freeze_behind_origin_never_pulls(tmp_path):
    root, origin = _clone(tmp_path)
    _apply_freeze(root)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "checkout", "-q", "main")
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "Test")
    (other / "next.txt").write_text("next\n", encoding="utf-8")
    _git(other, "add", "next.txt")
    _git(other, "commit", "-qm", "next")
    _git(other, "push")
    before = (root / REGISTRY).read_bytes()
    head = _git_out(root, "rev-parse", "HEAD")
    with pytest.raises(workflow.OwnerDailyError, match="PENDING_INPUT_FREEZE_HEAD_NOT_ORIGIN_MAIN"):
        _preflight(root)
    assert _git_out(root, "rev-parse", "HEAD") == head
    assert not (root / "next.txt").exists()
    assert (root / REGISTRY).read_bytes() == before
    _git(root, "fetch", "origin")
    release = env.producer_release_qualification(root)
    assert release["qualified"] is False
    assert release["reason_code"] == "PENDING_INPUT_FREEZE_HEAD_NOT_ORIGIN_MAIN"


def test_replay_of_unsealed_freeze_is_not_relabeled_complete(tmp_path):
    root, _origin = _clone(tmp_path)
    _apply_freeze(root)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(workflow.OwnerDailyError, match="PENDING_DAILY_STATE_SESSION_NOT_VERIFIED"):
        _preflight(root, completed_session=SESSION, runtime_root=runtime)
