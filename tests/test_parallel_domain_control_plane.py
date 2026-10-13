"""Hermetic multi-worktree adversarial workflow; no project runtime/source writes."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import roadmap_execution_state as res
from tools import stocklookup_roadmap as cli


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit(root, path, text="candidate\n"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(root, "add", path)
    git(root, "commit", "-qm", "fixture candidate")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "coordinator"
    root.mkdir()
    git(root, "init", "-qb", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    base = commit(root, "README.md", "initial\n")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-qu", "origin", "main")
    state_path = root / "docs/ROADMAP_STATE.json"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps({"schema_version": res.SCHEMA_VERSION, "milestones": [], "current": {},
                                      "queued_next": [], "implementation_lineage_head": base}, indent=2) + "\n", encoding="utf-8")
    def run(*args):
        return cli.main(["--repo", str(root), "--state-file", str(state_path), "--json", *args])
    assert run("--init-lanes", "--owner-override", "--scope-note", "fixture Owner directive", "--agent", "OwnerIntegrator") == 0
    return root, base, state_path, run


def add_lane(world, mid, path, agent="Codex", mode="IMPLEMENTATION", **extra):
    root, base, state_path, run = world
    wt = root.parent / mid
    git(root, "worktree", "add", "-qb", "feature/" + mid, str(wt), base)
    spec = {"milestone_id": mid, "responsible_agent": agent, "branch": "feature/" + mid,
            "worktree": str(wt), "base_sha": base, "domain": mid, "mode": mode,
            "allowed_paths": [path], "shared_paths": [], "dependencies": [], "provides": {},
            "consumes": {}, "required_checks": ["hermetic-integration"]}
    spec.update(extra)
    file = root.parent / (mid + "-spec.json")
    file.write_text(json.dumps(spec), encoding="utf-8")
    result = run("--admit-lane", mid, "--lane-spec", str(file), "--owner-override", "--scope-note", "Owner exact scope " + mid, "--agent", "OwnerIntegrator")
    return wt, result


def transition(world, mid, target, checkpoint=None, *extra):
    _, _, _, run = world
    return run("--transition-lane", mid, "--lane-state", target, "--owner-override", "--scope-note", "Owner lifecycle approval",
               "--agent", "OwnerIntegrator", *(["--checkpoint-at", checkpoint] if checkpoint else []), *extra)


def load(world):
    return res.load_state(world[2])


def receipt(plan):
    return {"plan_identity": plan["plan_identity"], "reviewed_by": "OwnerIntegrator",
            "review_note": "Hermetic fixture semantic review", "cross_repo_review": "unchanged Consumer API",
            "frozen_identity_review": "no frozen identity change",
            "checks": {mid: {name: {"status": "PASS", "evidence": "hermetic fixture test"} for name in checks}
                       for mid, checks in plan["required_checks"].items()}}


def candidate(world, mid, path, **kw):
    wt, code = add_lane(world, mid, path, **kw)
    assert code == 0
    assert transition(world, mid, "ACTIVE") == 0
    head = commit(wt, path.rstrip("/") + ("/candidate.py" if path.endswith("/") else ""), "value = 1\n")
    assert transition(world, mid, "REVIEW_READY", head) == 0
    return wt, head


def test_three_disjoint_agents_and_single_integration_owner(world):
    for mid, path, agent in (("financial", "stocklookup_core/financial/", "Codex"),
                             ("architecture", "tools/reliability/", "Claude"),
                             ("acquisition", "stocklookup_core/acquisition/", "Grok")):
        candidate(world, mid, path, agent=agent)
    before = load(world)
    plan = res.integration_plan(before, repo=world[0], main_sha=world[1])
    assert plan["order"] == ["acquisition", "architecture", "financial"]
    checked = res.integration_plan(before, repo=world[0], main_sha=world[1], receipts=receipt(plan))
    assert checked["errors"] == []
    assert checked["disposition"] == "READY_FOR_OWNER_REVIEW"
    assert not checked["merge_authorized"] and not checked["runtime_authorized"]
    assert before["current"] == {} and before["milestones"] == []


@pytest.mark.parametrize("scope", ["docs/ROADMAP_STATE.json", "official_source_registry.py", "config/", ".github/workflows/producer-ci.yml", ".gitignore"])
def test_shared_files_require_integration_owner_exact_lease(world, scope):
    _, result = add_lane(world, "bad", scope, agent="Claude")
    assert result == 2
    assert load(world)["development_control"]["lanes"] == []


@pytest.mark.parametrize("scope", ["../outside.py", "/absolute.py", "C:/external", "foo\\bar", "stocklookup_core/*", "data/", "operations-review/", "config/"])
def test_invalid_and_protected_scopes(world, scope):
    assert add_lane(world, "bad", scope)[1] == 2


def test_exact_shared_lease_and_frozen_review(world):
    wt, head = candidate(world, "pins", "config/frozen_source.json", agent="OwnerIntegrator",
                         shared_paths=["config/frozen_source.json"], lease_note="Owner narrowly approved frozen pin review")
    plan = res.integration_plan(load(world), repo=world[0], main_sha=world[1])
    assert plan["shared_and_frozen_review"] == ["config/frozen_source.json"]
    review = receipt(plan)
    review["frozen_identity_review"] = ""
    assert "LANE_EXACT_INTEGRATION_REVIEW_REQUIRED" in res.integration_plan(load(world), repo=world[0], main_sha=world[1], receipts=review)["errors"]


def test_same_file_or_directory_ownership_cannot_coexist(world):
    assert add_lane(world, "a", "stocklookup_core/financial/")[1] == 0
    assert add_lane(world, "b", "stocklookup_core/financial/inputs.py")[1] == 2
    assert add_lane(world, "c", "STOCKLOOKUP_CORE/FINANCIAL/")[1] == 2
    assert len(load(world)["development_control"]["lanes"]) == 1


def test_untracked_staged_rename_and_out_of_scope_changes(world):
    wt, code = add_lane(world, "a", "owned/")
    assert code == 0
    assert transition(world, "a", "ACTIVE") == 0
    (wt / "unowned.py").write_text("value = 1\n")
    assert world[3]("--check-lane", "a") == 1
    git(wt, "add", "unowned.py")
    assert world[3]("--check-lane", "a") == 1
    git(wt, "commit", "-qm", "outside candidate")
    git(wt, "mv", "unowned.py", "owned.py")
    checked = res.check_lane(load(world), "a", repo=world[0])
    assert {"unowned.py", "owned.py"} <= set(checked["paths"])
    assert not checked["clean"]


def test_pause_resume_preserves_independent_checkpoints_and_history(world):
    a, head = candidate(world, "a", "a.py")
    b, _ = add_lane(world, "b", "b.py")
    assert transition(world, "a", "COMPLETE_LOCAL", head) == 0
    assert transition(world, "a", "ACTIVE") == 0
    assert transition(world, "a", "PAUSED", head) == 0
    saved = load(world)
    assert saved["development_control"]["lanes"][1]["state"] == "ADMITTED"
    assert transition(world, "a", "ACTIVE") == 0
    assert res.lane_by_id(load(world), "a")["checkpoint"] == head
    assert len(res.lane_by_id(load(world), "a")["history"]) == 6


@pytest.mark.parametrize("mode", ["SHADOW", "READ_ONLY", "EXTERNAL_RESEARCH"])
def test_nonimplementation_never_promotes(world, mode):
    wt, code = add_lane(world, "a", "a.py", mode=mode)
    assert code == 0
    assert transition(world, "a", "ACTIVE") == 0
    if mode == "SHADOW":
        head = commit(wt, "a.py")
    else:
        head = world[1]
    assert transition(world, "a", "REVIEW_READY", head) == 2
    assert res.lane_by_id(load(world), "a")["state"] == "ACTIVE"


def test_disjoint_schema_incompatibility_and_missing_dependency(world):
    candidate(world, "a", "a.py", provides={"financial_fact": "v2"})
    candidate(world, "b", "b.py", consumes={"financial_fact": "v1"})
    plan = res.integration_plan(load(world), repo=world[0], main_sha=world[1])
    assert "LANE_INTERFACE_VERSION_CONFLICT:financial_fact" in plan["errors"]
    assert "LANE_INTERFACE_DEPENDENCY_UNDECLARED:financial_fact" in plan["errors"]
    assert not set(plan["changed_paths"]["a"]) & set(plan["changed_paths"]["b"])
    selected = res.integration_plan(load(world), repo=world[0], main_sha=world[1], candidate_id="b")
    assert "LANE_INTERFACE_VERSION_CONFLICT:financial_fact" in selected["errors"]
    assert "LANE_INTERFACE_DEPENDENCY_UNDECLARED:financial_fact" in selected["errors"]


def test_dependency_order_and_active_block(world):
    a, head = candidate(world, "a", "a.py")
    b, code = add_lane(world, "b", "b.py", dependencies=["a"])
    assert code == 0
    assert transition(world, "b", "ACTIVE") == 2
    assert transition(world, "a", "COMPLETE_LOCAL", head) == 0
    assert transition(world, "b", "ACTIVE") == 0
    bhead = commit(b, "b.py")
    assert transition(world, "b", "REVIEW_READY", bhead) == 0
    plan = res.integration_plan(load(world), repo=world[0], main_sha=world[1])
    assert plan["order"] == ["a", "b"]
    assert "LANE_DEPENDENCY_NOT_RELEASED:b:a" in plan["errors"]
    first = res.integration_plan(load(world), repo=world[0], main_sha=world[1], candidate_id="a")
    assert res.integration_plan(load(world), repo=world[0], main_sha=world[1], candidate_id="a", receipts=receipt(first))["errors"] == []


def test_integrate_a_then_verify_behind_b_without_rebase(world):
    a, ahead = candidate(world, "a", "a.py")
    b, bhead = candidate(world, "b", "b.py")
    # The only merges/pushes anywhere in these tests target this throwaway Git fixture.
    git(world[0], "merge", "--no-ff", "-qm", "fixture Owner integrates A", "feature/a")
    newmain = git(world[0], "rev-parse", "HEAD")
    git(world[0], "push", "-q", "origin", "main")
    plan = res.integration_plan(load(world), repo=world[0], main_sha=newmain, candidate_id="a")
    r = receipt(plan)
    r.update(owner_merge_directive="fixture Owner authorized A merge", post_merge_ci_evidence="fixture CI PASS")
    rf = world[0].parent / "release-receipt.json"
    rf.write_text(json.dumps(r))
    assert transition(world, "a", "MERGED_RELEASED", ahead, "--main-sha", newmain, "--review-receipt", str(rf)) == 0
    remaining = res.integration_plan(load(world), repo=world[0], main_sha=newmain)
    assert remaining["heads"] == {"b": bhead}
    combined = world[0].parent / "combined"
    git(world[0], "worktree", "add", "-qb", "fixture/integration", str(combined), newmain)
    git(combined, "merge", "--no-ff", "-qm", "fixture integration check B after A", "feature/b")
    result = subprocess.run([sys.executable, "-B", "-c", "import a, b; assert a.value == b.value == 1"], cwd=combined, capture_output=True)
    assert result.returncode == 0, result.stderr
    exact = receipt(remaining)
    exact["checks"]["b"]["hermetic-integration"]["evidence"] = "fixture combined " + git(combined, "rev-parse", "HEAD") + ": Python import assertions passed"
    assert res.integration_plan(load(world), repo=world[0], main_sha=newmain, receipts=exact)["errors"] == []
    assert git(b, "rev-parse", "HEAD") == bhead
    assert res.lane_by_id(load(world), "a")["release_sha"] == newmain


def test_stale_remote_tracking_and_receipt_are_rejected(world):
    candidate(world, "a", "a.py")
    old = res.integration_plan(load(world), repo=world[0], main_sha=world[1])
    new = commit(world[0], "other.py")
    # Direct bare-fixture ref update simulates somebody else advancing the remote.
    git(world[0], "push", "-q", "origin", "HEAD:refs/heads/other")
    git(world[0].parent / "remote.git", "update-ref", "refs/heads/main", new)
    assert "LANE_REMOTE_MAIN_STALE_OR_UNVERIFIED" in res.integration_plan(load(world), repo=world[0], main_sha=world[1])["errors"]
    git(world[0], "fetch", "-q", "origin", "main")
    newer = res.integration_plan(load(world), repo=world[0], main_sha=new, receipts=receipt(old))
    assert "LANE_EXACT_INTEGRATION_REVIEW_REQUIRED" in newer["errors"]


def test_owner_override_and_other_writer_cannot_mutate(world):
    snapshot = world[2].read_bytes()
    assert world[3]("--admit-lane", "a", "--agent", "OwnerIntegrator") == 2
    assert world[3]("--admit-lane", "a", "--owner-override", "--scope-note", "directive", "--agent", "Claude") == 2
    assert world[2].read_bytes() == snapshot


def test_duplicate_milestone_and_unmerged_release_claim(world):
    a, head = candidate(world, "a", "a.py")
    assert transition(world, "a", "MERGED_RELEASED", head, "--main-sha", world[1]) == 2
    state = load(world)
    state["development_control"]["lanes"].append(copy.deepcopy(state["development_control"]["lanes"][0]))
    assert "LANE_DUPLICATE_OR_INVALID_ID" in res.validate_development_control(state)


def test_branch_head_mismatch_and_reset_checkpoint(world):
    a, head = candidate(world, "a", "a.py")
    state = load(world)
    res.lane_by_id(state, "a")["branch"] = "feature/wrong"
    assert "LANE_WORKTREE_BRANCH_MISMATCH" in res.check_lane(state, "a", repo=world[0])["errors"]
    state = load(world)
    res.lane_by_id(state, "a")["checkpoint"] = "f" * 40
    assert "LANE_CHECKPOINT_NOT_ANCESTOR" in res.check_lane(state, "a", repo=world[0])["errors"]


def test_native_check_fails_unauthorized_lane_changes(world):
    wt, code = add_lane(world, "a", "a.py")
    assert code == 0
    (wt / "outside.py").write_text("fixture\n")
    assert res.evaluate(load(world), repo=world[0]).has_fail()


def test_atomic_compare_and_swap_preserves_crash_checkpoint(world):
    original = world[2].read_bytes().decode("utf-8")
    control = load(world)["development_control"]
    cli._write_control(world[2], original, control)
    changed = world[2].read_bytes().decode("utf-8") + "\n"
    world[2].write_bytes(changed.encode("utf-8"))
    with pytest.raises(res.RoadmapStateError, match="STATE_CHANGED"):
        cli._write_control(world[2], original, control)
    assert world[2].read_bytes().decode("utf-8") == changed


def test_production_writer_is_a_separate_authority_domain(world):
    candidate(world, "a", "stocklookup_core/financial/")
    state = load(world)
    # Runtime ownership is deliberately not inferred from number of development worktrees.
    state["runtime_writer_observation"] = {"pid": 123, "kind": "OWNER_DAILY", "active": True}
    result = res.check_lane(state, "a", repo=world[0])
    assert not result["errors"] and not result["runtime_authorized"]
    assert state["runtime_writer_observation"]["active"]


def test_new_main_same_file_requires_forward_correction(world):
    candidate(world, "a", "a.py")
    newmain = commit(world[0], "a.py", "value = 2\n")
    git(world[0], "push", "-q", "origin", "main")
    plan = res.integration_plan(load(world), repo=world[0], main_sha=newmain)
    assert "LANE_MAIN_CHANGED_FILE_OVERLAP:a:a.py" in plan["errors"]


def test_coordinated_mode_does_not_allow_unscoped_legacy_writer(world):
    with pytest.raises(SystemExit):
        world[3]("--admit-scope", "UNSCOPED", "--owner-override", "--scope-note", "directive", "--release-current-at", world[1])


def test_frozen_source_requires_lease_without_rewriting_manifest(world):
    manifest = "tests/fixtures/e2e3_frozen_sources.json"
    base = commit(world[0], manifest, json.dumps({"source_sha256_lf": {"frozen.py": "0" * 64}}))
    # Use a fresh fixture base containing the existing manifest schema.
    root, _, state_path, run = world
    world = root, base, state_path, run
    assert add_lane(world, "a", "frozen.py")[1] == 2
    assert add_lane(world, "b", "frozen.py", agent="OwnerIntegrator",
                    shared_paths=["frozen.py"], lease_note="Owner exact frozen lease")[1] == 0


def test_malformed_lane_fail_closed_without_traceback(world):
    state = load(world)
    state["development_control"]["lanes"] = [{"milestone_id": "bad", "admission_authority": "bad"}]
    assert res.validate_development_control(state)
    assert res.evaluate(state, repo=world[0]).has_fail()


def test_failed_atomic_publish_preserves_old_state(world, monkeypatch):
    import os
    original = world[2].read_bytes().decode("utf-8")
    def fail(*args):
        raise OSError("fixture interruption before publish")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="fixture interruption"):
        cli._write_control(world[2], original, load(world)["development_control"])
    assert world[2].read_bytes().decode("utf-8") == original
    assert not list(world[2].parent.glob(".roadmap-*.tmp"))


@pytest.mark.parametrize("field,value", [("shared_paths", None), ("required_checks", [123]),
                                         ("worktree", "relative"), ("history", None),
                                         ("base_sha", "--output=forbidden")])
def test_malformed_complete_spec_fails_native_validation(world, field, value):
    assert add_lane(world, "a", "a.py")[1] == 0
    state = load(world)
    res.lane_by_id(state, "a")[field] = value
    assert res.validate_development_control(state)
    assert res.evaluate(state, repo=world[0]).has_fail()


def test_ci_clone_structural_validation_cannot_grant_live_lane_authority(world):
    candidate(world, "a", "a.py")
    clone = world[0].parent / "ci-clone"
    git(world[0].parent, "clone", "-q", str(world[0]), str(clone))
    state = load(world)
    report = res.evaluate(state, repo=clone)
    assert report.overall == "ON_TRACK"  # Legacy Git and structural validation pass.
    assert "ROADMAP_LANE_WORKTREE_UNAVAILABLE" in {f.code for f in report.findings}
    assert cli._report_to_json(report, repo=clone)["development_control"]["host_observations"] == "SKIPPED_NON_COORDINATOR_CLONE"
    assert "LANE_REPOSITORY_MISMATCH" in res.check_lane(state, "a", repo=clone)["errors"]
    plan = res.integration_plan(state, repo=clone, main_sha=world[1])
    assert plan["disposition"] == "BLOCKED" and not plan["merge_authorized"]


def test_invalid_control_shape_has_native_failure_report(world):
    state = load(world)
    state["development_control"] = "invalid"
    report = res.evaluate(state, repo=world[0])
    assert report.has_fail()
    assert cli._report_to_json(report, repo=world[0])["overall"] == "DRIFT_DETECTED"


def test_crlf_history_bytes_preserved_and_line_ending_race_detected(world):
    before = world[2].read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    world[2].write_bytes(before)
    state = json.loads(before)
    prefix = before.split(b'  "development_control": ')[0]
    cli._write_control(world[2], before.decode("utf-8"), state["development_control"])
    assert world[2].read_bytes().startswith(prefix)
    stale = world[2].read_bytes().decode("utf-8")
    world[2].write_bytes(stale.replace("\r\n", "\n").encode("utf-8"))
    with pytest.raises(res.RoadmapStateError, match="STATE_CHANGED"):
        cli._write_control(world[2], stale, state["development_control"])


def test_dirty_integration_source_is_not_hidden_by_clean_candidates(world):
    candidate(world, "a", "a.py")
    (world[0] / "uncommitted.py").write_text("value = 2\n")
    plan = res.integration_plan(load(world), repo=world[0], main_sha=world[1])
    assert "LANE_COORDINATOR_SOURCE_DIRTY:uncommitted.py" in plan["errors"]
    assert plan["coordinator_native_state_dirty"]


def test_read_only_reviewer_can_overlap_shared_writer_without_a_write_lease(world):
    assert add_lane(world, "writer", "official_source_registry.py", agent="OwnerIntegrator",
                    shared_paths=["official_source_registry.py"], lease_note="Owner exact registry lease")[1] == 0
    reader, code = add_lane(world, "reviewer", "official_source_registry.py", agent="Claude", mode="READ_ONLY")
    assert code == 0
    assert not res.check_lane(load(world), "reviewer", repo=world[0])["errors"]
    (reader / "official_source_registry.py").write_text("unauthorized = True\n")
    assert "LANE_READ_ONLY_CHANGE" in res.check_lane(load(world), "reviewer", repo=world[0])["errors"]
