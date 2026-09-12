from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import roadmap_execution_state as res
from subprocess_capture import run_utf8

_TOOLS_PARENT = Path(__file__).resolve().parents[1]
if str(_TOOLS_PARENT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_PARENT))
import tools.stocklookup_roadmap as cli  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    code, out, err = run_utf8(["git", "-C", str(cwd), *args])
    assert code == 0, f"git {args} failed: {err}"
    return out


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    return path


def _commit_all(path: Path, message: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", message)
    return _git(path, "rev-parse", "HEAD").strip()


@pytest.fixture
def git_repo(tmp_path):
    """A throwaway Git repository under tmp_path -- never a real project worktree."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    sha = _commit_all(repo, "initial")
    return repo, sha


def _milestone(mid: str, state: str, **overrides) -> dict:
    entry = {
        "milestone_id": mid,
        "state": state,
        "checkpoint": None,
        "dependencies": [],
        "unlocks": [],
        "authority_effect": "NONE",
        "state_history": [],
        "owner_override": None,
    }
    entry.update(overrides)
    return entry


def _state(milestones, *, current=None, queued_next=None, lineage_head=None, allowlist=None) -> dict:
    return {
        "schema_version": res.SCHEMA_VERSION,
        "roadmap_id": "test",
        "roadmap_version": "0.0.1",
        "implementation_lineage_head": lineage_head,
        "known_operational_diff_allowlist": allowlist or [],
        "current": current or {},
        "queued_next": queued_next or [],
        "milestones": milestones,
        "blocked_capabilities": [],
    }


# ---------------------------------------------------------------------------
# Pure structural validation (no Git needed)
# ---------------------------------------------------------------------------

def test_valid_roadmap_state_passes():
    state = _state(
        [
            _milestone("A", "COMPLETE", checkpoint="deadbeef"),
            _milestone("B", "NEXT", dependencies=["A"]),
        ],
        current={"milestone": "A", "state": "COMPLETE"},
        queued_next=["B"],
    )
    report = res.evaluate(state)
    assert report.overall == "ON_TRACK"
    assert not report.has_fail()


def test_two_active_milestones_fail():
    state = _state([_milestone("A", "ACTIVE"), _milestone("B", "ACTIVE")])
    report = res.evaluate(state)
    assert report.overall == "DRIFT_DETECTED"
    assert "ROADMAP_MULTIPLE_ACTIVE_MILESTONES" in {f.code for f in report.findings}


def test_active_with_unsatisfied_dependency_fails():
    state = _state([_milestone("A", "NEXT"), _milestone("B", "ACTIVE", dependencies=["A"])])
    report = res.evaluate(state)
    assert report.overall == "DRIFT_DETECTED"
    assert "ROADMAP_ACTIVE_NOT_ALLOWED_BY_DEPENDENCIES" in {f.code for f in report.findings}


def test_next_depending_on_blocked_fails():
    state = _state(
        [_milestone("A", "BLOCKED"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["B"],
    )
    report = res.evaluate(state)
    assert "ROADMAP_NEXT_DEPENDENCY_UNSATISFIED" in {f.code for f in report.findings}


def test_completed_checkpoint_missing_fails():
    state = _state([_milestone("A", "COMPLETE", checkpoint=None)])
    report = res.evaluate(state)
    assert "ROADMAP_CHECKPOINT_MISSING" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"


def test_closed_milestone_reopened_fails_without_override():
    state = _state([_milestone("A", "ACTIVE", state_history=["COMPLETE"])])
    report = res.evaluate(state)
    assert "ROADMAP_CLOSED_MILESTONE_REOPENED" in {f.code for f in report.findings}


def test_owner_override_allows_reopen():
    state = _state(
        [
            _milestone(
                "A",
                "ACTIVE",
                state_history=["COMPLETE"],
                owner_override={"allows_reopen": True, "approved_by": "owner", "reason": "test", "at": "2026-08-30"},
            )
        ]
    )
    report = res.evaluate(state)
    assert "ROADMAP_CLOSED_MILESTONE_REOPENED" not in {f.code for f in report.findings}


def test_stale_next_pointer_not_in_queue():
    state = _state([_milestone("A", "NEXT")], queued_next=[])
    report = res.evaluate(state)
    assert "ROADMAP_STALE_NEXT_POINTER" in {f.code for f in report.findings}


def test_stale_next_pointer_mismatched_queue_head():
    state = _state([_milestone("A", "NEXT")], queued_next=["B_DOES_NOT_MATCH"])
    report = res.evaluate(state)
    codes = {f.code for f in report.findings}
    assert "ROADMAP_UNKNOWN_MILESTONE" in codes
    assert "ROADMAP_STALE_NEXT_POINTER" in codes


def test_unknown_milestone_reference_fails():
    state = _state([_milestone("A", "COMPLETE", checkpoint="x", unlocks=["GHOST"])])
    report = res.evaluate(state)
    assert "ROADMAP_UNKNOWN_MILESTONE" in {f.code for f in report.findings}


def test_can_start_allowed_when_next_and_satisfied():
    state = _state(
        [_milestone("A", "COMPLETE", checkpoint="x"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["B"],
    )
    allowed, reasons = res.can_start(state, "B")
    assert allowed
    assert reasons == []


def test_can_start_blocked_unsatisfied_dependency():
    state = _state(
        [_milestone("A", "NEXT"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["A"],
    )
    allowed, reasons = res.can_start(state, "B")
    assert not allowed
    assert any("UNSATISFIED_DEPENDENCIES" in r for r in reasons)


def test_can_start_blocked_conflicting_active_writer():
    state = _state([_milestone("A", "ACTIVE"), _milestone("B", "NEXT")])
    allowed, reasons = res.can_start(state, "B")
    assert not allowed
    assert any("CONFLICTING_ACTIVE_WRITER" in r for r in reasons)


def test_can_start_unknown_milestone():
    state = _state([_milestone("A", "NEXT")])
    allowed, reasons = res.can_start(state, "GHOST")
    assert not allowed
    assert reasons == ["ROADMAP_UNKNOWN_MILESTONE:GHOST"]


def test_deterministic_output_ordering():
    state = _state(
        [
            _milestone("A", "ACTIVE"),
            _milestone("B", "ACTIVE"),
            _milestone("C", "COMPLETE", checkpoint=None),
        ]
    )
    first = res.evaluate(state)
    second = res.evaluate(state)
    assert [(f.code, f.severity, f.message) for f in first.findings] == [
        (f.code, f.severity, f.message) for f in second.findings
    ]


def test_deterministic_content_identity():
    state = _state([_milestone("A", "COMPLETE", checkpoint="x")])
    first = res.evaluate(state)
    second = res.evaluate(state)
    assert first.content_identity == second.content_identity
    mutated = _state([_milestone("A", "COMPLETE", checkpoint="y")])
    third = res.evaluate(mutated)
    assert third.content_identity != first.content_identity


# ---------------------------------------------------------------------------
# Git-backed checks (temporary repos only; never touch real project worktrees)
# ---------------------------------------------------------------------------

def test_checkpoint_resolves_against_real_commit(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}


def test_checkpoint_not_in_git_fails(git_repo):
    repo, sha = git_repo
    fake = "f" * 40
    state = _state([_milestone("A", "COMPLETE", checkpoint=fake)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"


def test_head_sentinel_resolves_live(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint="HEAD")], lineage_head="HEAD")
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}
    assert "ROADMAP_RECORDED_HEAD_DIVERGENCE" not in {f.code for f in report.findings if f.severity == res.FAIL}


def test_recorded_head_divergence_when_repo_reset_behind(git_repo):
    repo, sha = git_repo
    (repo / "second.txt").write_text("x\n", encoding="utf-8")
    forward_sha = _commit_all(repo, "second")
    state = _state([_milestone("A", "COMPLETE", checkpoint=forward_sha)], lineage_head=forward_sha)
    _git(repo, "reset", "--hard", sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_RECORDED_HEAD_DIVERGENCE" in {f.code for f in report.findings if f.severity == res.FAIL}


def test_known_operational_diff_is_info_not_fatal(git_repo):
    repo, sha = git_repo
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha, allowlist=["README.md"])
    report = res.evaluate(state, repo=repo)
    dirty = [f for f in report.findings if f.code == "ROADMAP_DIRTY_WORKTREE"]
    assert dirty and all(f.severity == res.INFO for f in dirty)
    assert report.overall == "ON_TRACK"


def test_unallowlisted_dirty_file_is_warning_not_fatal(git_repo):
    repo, sha = git_repo
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha, allowlist=[])
    report = res.evaluate(state, repo=repo)
    dirty = [f for f in report.findings if f.code == "ROADMAP_DIRTY_WORKTREE"]
    assert dirty and all(f.severity == res.WARNING for f in dirty)
    assert report.overall == "ON_TRACK"


def test_multiple_source_writers_detected(git_repo):
    repo, sha = git_repo
    _git(repo, "branch", "feature/shared-milestone-v1-a")
    _git(repo, "branch", "feature/shared-milestone-v1-b")
    wt_a = repo.parent / "wt-a"
    wt_b = repo.parent / "wt-b"
    _git(repo, "worktree", "add", str(wt_a), "feature/shared-milestone-v1-a")
    _git(repo, "worktree", "add", str(wt_b), "feature/shared-milestone-v1-b")
    (wt_a / "a.txt").write_text("a\n", encoding="utf-8")
    _commit_all(wt_a, "a work")
    (wt_b / "b.txt").write_text("b\n", encoding="utf-8")
    _commit_all(wt_b, "b work")

    state = _state([_milestone("SHARED_MILESTONE_V1", "ACTIVE")], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    fail_findings = [
        f for f in report.findings if f.code == "ROADMAP_MULTIPLE_SOURCE_WRITERS" and f.severity == res.FAIL
    ]
    assert fail_findings, [f.message for f in report.findings]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state), encoding="utf-8")


def test_cli_json_mode_emits_parseable_report(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state([_milestone("A", "COMPLETE", checkpoint="x")], current={"milestone": "A", "state": "COMPLETE"}),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall"] == "ON_TRACK"
    assert payload["schema_version"] == res.SCHEMA_VERSION


def test_cli_check_exit_code_nonzero_on_drift(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(state_path, _state([_milestone("A", "ACTIVE"), _milestone("B", "ACTIVE")]))
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--check"])
    capsys.readouterr()
    assert code == 1


def test_cli_check_exit_code_zero_on_track(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state([_milestone("A", "COMPLETE", checkpoint="x")], current={"milestone": "A", "state": "COMPLETE"}),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--check"])
    capsys.readouterr()
    assert code == 0


def test_cli_can_start_allowed(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state(
            [_milestone("A", "COMPLETE", checkpoint="x"), _milestone("B", "NEXT", dependencies=["A"])],
            queued_next=["B"],
        ),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--can-start", "B"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("ALLOWED")


def test_cli_can_start_blocked(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(state_path, _state([_milestone("A", "NEXT", dependencies=["MISSING"])]))
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--can-start", "A"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("BLOCKED")


# ---------------------------------------------------------------------------
# Real bootstrap file sanity (read-only against this actual worktree)
# ---------------------------------------------------------------------------

def test_real_bootstrap_roadmap_state_is_on_track():
    state = res.load_state()
    report = res.evaluate(state, repo=res.REPO_ROOT)
    assert not report.has_fail(), [(f.code, f.message) for f in report.findings if f.severity == res.FAIL]


# ---------------------------------------------------------------------------
# Authoritative-vs-historical checkpoint reconciliation
# (ROADMAP_REMOTE_CHECKPOINT_RECONCILIATION_AND_HOSTED_CI_CLOSEOUT_V1)
#
# A checkpoint resolving against *this* worktree's local Git object store is
# not sufficient: this worktree also holds many local-only feature branches
# that a fresh clone of origin/main never sees. The real regression is a
# COMPLETE milestone whose checkpoint only resolves because the object
# happens to exist locally, not because it is reachable from shared mainline
# history. `git_is_ancestor(repo, checkpoint, HEAD)` is the offline-provable
# proxy for "would also resolve in a fresh clone of the branch HEAD sits on".
# ---------------------------------------------------------------------------

def test_completed_milestone_checkpoints_are_ancestors_of_head():
    """Every COMPLETE milestone's checkpoint must be reachable from live HEAD.

    A local-only feature-branch commit can satisfy ``git cat-file -t`` in this
    worktree (the object exists) while being unreachable from any commit a
    fresh clone of the pushed branch would ever see. Ancestry of HEAD is the
    offline-checkable stand-in for "resolvable from shared Git history".
    """
    state = res.load_state()
    head = res.git_head(res.REPO_ROOT)
    assert head, "expected a resolvable HEAD in this worktree"
    milestones = res._milestones_by_id(state)
    non_ancestor = []
    for mid, m in milestones.items():
        if m.get("state") != "COMPLETE":
            continue
        checkpoint = m.get("checkpoint")
        if not checkpoint or checkpoint == res.HEAD_SENTINEL:
            continue
        if not res.git_is_ancestor(res.REPO_ROOT, checkpoint, head):
            non_ancestor.append((mid, checkpoint))
    assert not non_ancestor, non_ancestor


def test_notes_may_reference_unmerged_sha_without_effect(git_repo):
    """Descriptive lineage may name a SHA that was never merged anywhere;
    only the machine-readable `checkpoint` field is validated."""
    repo, sha = git_repo
    never_merged = "b" * 40
    state = _state(
        [
            _milestone(
                "A",
                "COMPLETE",
                checkpoint=sha,
                notes=f"historical local execution checkpoint {never_merged}, never merged to origin/main",
            )
        ],
        lineage_head=sha,
    )
    report = res.evaluate(state, repo=repo)
    assert not report.has_fail()


def test_retained_unmerged_milestone_keeps_terminal_status_without_claiming_merge(git_repo):
    """A RETAINED_UNMERGED-style milestone stays COMPLETE/ON_TRACK as long as
    its authoritative `checkpoint` is a real shared commit -- it must not need
    to (and must not) claim its own unmerged feature branch was ever merged."""
    repo, sha = git_repo
    unmerged_feature_sha = "c" * 40
    state = _state(
        [
            _milestone(
                "RETAINED_UNMERGED_EXAMPLE_V1",
                "COMPLETE",
                checkpoint=sha,
                narrative_disposition="PARTIAL_BY_EVIDENCE / RETAINED_UNMERGED",
                notes=f"Historical local execution checkpoint {unmerged_feature_sha} was never merged to origin/main.",
            )
        ],
        lineage_head=sha,
    )
    report = res.evaluate(state, repo=repo)
    assert not report.has_fail()
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}


def test_hnx_and_text_native_authority_effects_unchanged_by_reconciliation():
    """The checkpoint-field correction must not change what either milestone
    is recorded as having actually done (authority effect, terminal state,
    RETAINED_UNMERGED disposition)."""
    state = res.load_state()
    milestones = res._milestones_by_id(state)
    hnx = milestones["HNX_PERIODIC_FINANCIAL_DOCUMENT_ROUTE_ACTIVATION_AND_RAW_ACQUISITION_V1"]
    text_native = milestones["TEXT_NATIVE_OFFICIAL_FINANCIAL_TABLE_EXTRACTION_SCALEOUT_V1"]

    assert hnx["state"] == "COMPLETE"
    assert hnx["authority_effect"] == (
        "RAW_DOCUMENT_ROUTE_AUTHORITY_PROMOTED_WITHIN_OWNER_APPROVED_SCOPE / FINANCIAL_FACT_AUTHORITY_UNCHANGED"
    )

    assert text_native["state"] == "COMPLETE"
    assert text_native["authority_effect"] == "NONE / FINANCIAL_FACT_AUTHORITY_UNCHANGED"
    assert "RETAINED_UNMERGED" in text_native["narrative_disposition"]

    # The corrected authoritative checkpoint is shared between both entries
    # (the single governance rebaseline commit that recorded both
    # dispositions) and differs from each entry's historical, unmerged
    # implementation SHA, which now lives only in `notes`.
    assert hnx["checkpoint"] == text_native["checkpoint"]
    assert hnx["checkpoint"] != "a0fcf8957c6e2d1bb541b93c136ce65b6d4223a2"
    assert text_native["checkpoint"] != "2507c86a3a8b07f6c09133097e799c5bd194f063"
    assert "a0fcf8957c6e2d1bb541b93c136ce65b6d4223a2" in hnx["notes"]
    assert "2507c86a3a8b07f6c09133097e799c5bd194f063" in text_native["notes"]


def test_truly_nonexistent_authoritative_checkpoint_still_fails(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint="d" * 40)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"


def test_no_milestone_specific_checkpoint_bypass_in_checker_source():
    """The checkpoint-existence check must stay milestone-agnostic: no
    hardcoded exemption for the two milestones this reconciliation fixed."""
    source = Path(res.__file__).read_text(encoding="utf-8")
    assert "HNX_PERIODIC_FINANCIAL_DOCUMENT_ROUTE_ACTIVATION_AND_RAW_ACQUISITION_V1" not in source
    assert "TEXT_NATIVE_OFFICIAL_FINANCIAL_TABLE_EXTRACTION_SCALEOUT_V1" not in source
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in source
