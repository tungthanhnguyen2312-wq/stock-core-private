"""Atomic migration/refusal tests; no project runtime or coordinator writes."""
from __future__ import annotations

import copy
import json

import pytest

import roadmap_execution_state as res
from tools import stocklookup_roadmap as cli
from tests.test_parallel_domain_control_plane import (
    world, candidate, commit, git, load, receipt, transition,
)


def declarations(lane):
    return {k: copy.deepcopy(lane[k]) for k in ("provides", "consumes", "dependencies")}


def spec_for(state, after):
    return {"schema": "stocklookup_lane_declaration_amendment/1",
            "expected_revision": state["development_control"]["revision"],
            "amendments": [{"milestone_id": mid, "checkpoint": res.lane_by_id(state, mid)["checkpoint"],
                            "before": declarations(res.lane_by_id(state, mid)), "after": value,
                            "review_note": "Exact fixture source responsibility reviewed; metadata only"}
                           for mid, value in after.items()]}


@pytest.fixture
def completed(world):
    for mid, provides, consumes, deps in (
        ("home", {"cards": "v1", "inputs": "v1"}, {}, []),
        ("restage", {"cards": "v1", "inputs": "v1"}, {}, ["home"]),
        ("validation", {"validation": "v1"}, {"cards": "v1"}, ["home", "restage"]),
        ("unrelated", {"other": "v1"}, {}, []),
    ):
        _, head = candidate(world, mid, "stocklookup_core/" + mid + "/", provides=provides,
                            consumes=consumes, dependencies=deps)
        assert transition(world, mid, "COMPLETE_LOCAL", head) == 0
    return world


def corrected(state):
    return spec_for(state, {
        "home": {"provides": {"cards": "v1"}, "consumes": {}, "dependencies": []},
        "restage": {"provides": {"restaging": "v1", "assets": "v1"},
                    "consumes": {"cards": "v1"}, "dependencies": ["home"]},
        "validation": {"provides": {"validation": "v1"},
                       "consumes": {"cards": "v1", "restaging": "v1", "assets": "v1"},
                       "dependencies": ["home", "restage"]},
    })


def amend(world, spec, *extra, agent="OwnerIntegrator", owner=True):
    path = world[0].parent / "declarations.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return world[3]("--amend-lane-declarations", "--declaration-spec", str(path),
                    "--agent", agent, "--scope-note", "Owner exact declaration correction",
                    *(["--owner-override"] if owner else []), *extra)


def test_native_atomic_migration_preserves_lane_identity_history_and_legacy_bytes(completed):
    before = load(completed)
    raw = completed[2].read_bytes()
    amendment = corrected(before)
    assert amend(completed, amendment) == 0
    after = load(completed)
    old_control, new_control = before["development_control"], after["development_control"]
    assert new_control["revision"] == old_control["revision"] + 1
    assert new_control["history"][:-1] == old_control["history"]
    assert new_control["history"][-1]["operation"] == "AMEND_DECLARATIONS"
    assert len(new_control["history"][-1]["amendments"]) == 3
    for old, new in zip(old_control["lanes"], new_control["lanes"]):
        mid = old["milestone_id"]
        if mid == "unrelated":
            assert old == new
            assert json.dumps(old, ensure_ascii=False) == json.dumps(new, ensure_ascii=False)
        else:
            assert {k:v for k,v in old.items() if k not in {"provides", "consumes", "dependencies", "history"}} == {
                k:v for k,v in new.items() if k not in {"provides", "consumes", "dependencies", "history"}}
            assert new["history"][:-1] == old["history"]
            assert new["history"][-1]["before"] == declarations(old)
            assert new["history"][-1]["after"] == declarations(new)
    marker = b'  "development_control": '
    assert raw.split(marker)[0] == completed[2].read_bytes().split(marker)[0]
    assert {k:v for k,v in after.items() if k != "development_control"} == {
        k:v for k,v in before.items() if k != "development_control"}
    # Older readers and normal integration/release gates still apply.
    plan = res.integration_plan(after, repo=completed[0], main_sha=completed[1], candidate_id="restage")
    checked = res.integration_plan(after, repo=completed[0], main_sha=completed[1],
                                   candidate_id="restage", receipts=receipt(plan))
    assert "LANE_DEPENDENCY_NOT_RELEASED:restage:home" in checked["errors"]
    assert not any("DUPLICATE_INTERFACE_OWNER" in e for e in checked["errors"])
    assert res.check_lane(after, "home", repo=completed[0])["clean"]
    frozen = completed[2].read_bytes()
    assert amend(completed, amendment) == 2  # replay is stale, not idempotent mutation
    assert completed[2].read_bytes() == frozen


@pytest.fixture
def model(monkeypatch, tmp_path):
    """Pure adversarial cases; exact live Git enforcement is tested separately."""
    sha = "a" * 40
    lane = lambda mid, p, c, d: {"milestone_id": mid, "responsible_agent": "Codex", "branch": "feature/" + mid,
        "worktree": str(tmp_path / mid), "base_sha": sha, "domain": mid, "mode": "IMPLEMENTATION",
        "allowed_paths": ["stocklookup_core/" + mid + "/"], "shared_paths": [], "dependencies": d,
        "provides": p, "consumes": c, "required_checks": ["test"], "state": "COMPLETE_LOCAL",
        "checkpoint": sha, "authority_effect": "NONE", "history": [],
        "admission_authority": {"kind": "EXPLICIT_OWNER_DIRECTIVE", "note": "fixture"}}
    state = {"milestones": [], "development_control": {"schema": res.LANE_SCHEMA, "revision": 1,
        "history": [{"operation": "fixture"}], "integration_agent": "Codex", "integration_branch": "ops/native",
        "integration_worktree": str(tmp_path), "lanes": [
            lane("home", {"cards": "v1", "inputs": "v1"}, {}, []),
            lane("restage", {"cards": "v1", "inputs": "v1"}, {}, ["home"]),
            lane("validation", {"validation": "v1"}, {"cards": "v1"}, ["home", "restage"])]}}
    monkeypatch.setattr(res, "check_lane", lambda *a, **kw: {"errors": [], "clean": True, "head": sha})
    return state, corrected(state), tmp_path


@pytest.mark.parametrize("field", ["state", "allowed_paths", "shared_paths", "responsible_agent", "branch",
                                   "worktree", "base_sha", "authority_effect", "required_checks", "history"])
def test_reserved_fields_cannot_change_completed_lane_or_lease(model, field):
    state, spec, repo = model
    spec["amendments"][0]["after"][field] = "injected"
    before = copy.deepcopy(state)
    with pytest.raises(res.RoadmapStateError, match="RESERVED_OR_MISSING_FIELDS"):
        res.prepare_declaration_amendment(state, spec, repo=repo)
    assert state == before


@pytest.mark.parametrize("defect,code", [
    ("revision", "REVISION_CHANGED"), ("boolean_revision", "EXACT_SPEC"),
    ("checkpoint", "CHECKPOINT_MISMATCH"), ("before", "BEFORE_CHANGED"),
    ("duplicate", "DUPLICATE_TARGET"), ("no_change", "NO_CHANGE"),
    ("dep_removal", "DEPENDENCY_REMOVAL"), ("duplicate_dep", "DEPENDENCY_REMOVAL"),
    ("bad_interface", "INTERFACE_INVALID"), ("duplicate_owner", "DUPLICATE_INTERFACE_OWNER"),
    ("version", "INTERFACE_VERSION_CONFLICT"), ("undeclared", "INTERFACE_DEPENDENCY_UNDECLARED"),
    ("orphan", "INTERFACE_OWNER_MISSING"), ("cycle", "DEPENDENCY_CYCLE"),
    ("unknown_dep", "DEPENDENCY_INVALID"), ("blank_review", "RESERVED_OR_MISSING_FIELDS"),
    ("released", "DURABLE_UNRELEASED"), ("active", "DURABLE_UNRELEASED"),
    ("unknown_target", "LANE_UNKNOWN"),
])
def test_adversarial_batch_has_no_partial_mutation(model, defect, code):
    state, spec, repo = model
    item = spec["amendments"][1]
    if defect == "revision": spec["expected_revision"] += 1
    elif defect == "boolean_revision": spec["expected_revision"] = True
    elif defect == "checkpoint": item["checkpoint"] = "b" * 40
    elif defect == "before": item["before"]["provides"] = {}
    elif defect == "duplicate": spec["amendments"].append(copy.deepcopy(item))
    elif defect == "no_change": item["after"] = copy.deepcopy(item["before"])
    elif defect == "dep_removal": item["after"]["dependencies"] = []
    elif defect == "duplicate_dep": item["after"]["dependencies"] *= 2
    elif defect == "bad_interface": item["after"]["provides"] = []
    elif defect == "duplicate_owner": item["after"]["provides"]["cards"] = "v1"
    elif defect == "version": item["after"]["consumes"]["cards"] = "v2"
    elif defect == "undeclared": spec["amendments"][0]["after"]["consumes"] = {"assets": "v1"}
    elif defect == "orphan": item["after"]["consumes"]["missing"] = "v1"
    elif defect == "cycle": spec["amendments"][0]["after"]["dependencies"] = ["restage"]
    elif defect == "unknown_dep": item["after"]["dependencies"].append("unknown")
    elif defect == "blank_review": item["review_note"] = " "
    elif defect in {"released", "active"}: state["development_control"]["lanes"][1]["state"] = "MERGED_RELEASED" if defect == "released" else "ACTIVE"
    elif defect == "unknown_target": item["milestone_id"] = "unknown"
    before = copy.deepcopy(state)
    with pytest.raises(res.RoadmapStateError, match=code):
        res.prepare_declaration_amendment(state, spec, repo=repo)
    assert state == before


def test_known_consumer_cannot_be_orphaned_by_renaming_owner(model):
    state, spec, repo = model
    spec["amendments"][0]["after"]["provides"] = {"renamed_cards": "v1"}
    with pytest.raises(res.RoadmapStateError, match="INTERFACE_OWNER_MISSING:cards"):
        res.prepare_declaration_amendment(state, spec, repo=repo)


@pytest.mark.parametrize("dirty,head,errors", [(True, "a" * 40, []), (False, "b" * 40, []),
                                             (False, "a" * 40, ["LANE_BRANCH_IDENTITY_MISMATCH"])])
def test_live_checkpoint_failures_are_not_waived(model, monkeypatch, dirty, head, errors):
    state, spec, repo = model
    monkeypatch.setattr(res, "check_lane", lambda *a, **kw: {"clean": not dirty, "head": head, "errors": errors})
    with pytest.raises(res.RoadmapStateError, match="EXACT_CLEAN_CHECKPOINT_REQUIRED"):
        res.prepare_declaration_amendment(state, spec, repo=repo)


@pytest.mark.parametrize("agent,owner", [("OtherAgent", True), ("OwnerIntegrator", False)])
def test_cli_requires_real_bound_owner_and_directive(world, agent, owner):
    wt, head = candidate(world, "home", "stocklookup_core/home/", provides={"cards": "v1"})
    assert transition(world, "home", "COMPLETE_LOCAL", head) == 0
    state = load(world)
    spec = spec_for(state, {"home": {"provides": {"cards": "v1", "new": "v1"}, "consumes": {}, "dependencies": []}})
    before = world[2].read_bytes()
    assert amend(world, spec, agent=agent, owner=owner) == 2
    assert world[2].read_bytes() == before


def test_cli_refuses_wrong_checkpoint_and_dirty_worktree_with_exact_bytes_preserved(world):
    wt, head = candidate(world, "home", "stocklookup_core/home/", provides={"cards": "v1"})
    assert transition(world, "home", "COMPLETE_LOCAL", head) == 0
    spec = spec_for(load(world), {"home": {"provides": {"cards": "v1", "new": "v1"}, "consumes": {}, "dependencies": []}})
    before = world[2].read_bytes()
    (wt / "stocklookup_core/home/candidate.py").write_text("dirty\n", encoding="utf-8")
    assert amend(world, spec) == 2
    assert world[2].read_bytes() == before
    git(wt, "add", ".")
    git(wt, "commit", "-qm", "fixture later source")
    assert amend(world, spec) == 2  # exact checkpoint ancestry alone is insufficient
    assert world[2].read_bytes() == before


def test_atomic_writer_failure_preserves_complete_old_state(completed, monkeypatch):
    before = completed[2].read_bytes()
    def refused(*args):
        raise res.RoadmapStateError("LANE_STATE_CHANGED_RELOAD_REQUIRED")
    monkeypatch.setattr(cli, "_write_control", refused)
    assert amend(completed, corrected(load(completed))) == 2
    assert completed[2].read_bytes() == before


def test_no_extension_legacy_queries_remain_unchanged(tmp_path, capsys):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"schema_version": res.SCHEMA_VERSION, "milestones": [],
                               "current": {}, "queued_next": []}), encoding="utf-8")
    assert cli.main(["--state-file", str(path), "--repo", str(tmp_path / "absent"), "--json"]) == 0
    capsys.readouterr()
    before = path.read_bytes()
    assert cli.main(["--state-file", str(path), "--repo", str(tmp_path), "--amend-lane-declarations",
                     "--agent", "Codex", "--owner-override", "--scope-note", "fixture"]) == 2
    assert path.read_bytes() == before
