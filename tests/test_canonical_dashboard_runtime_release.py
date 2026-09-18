import csv
import copy
import json

import pytest

import canonical_dashboard_runtime_release as runtime_release
import release_session_contract


ROOT = runtime_release.Path(__file__).resolve().parents[1]
SESSION = "2026-08-26"


def _rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_explicit_producer_run_identity_resolves_an_ambiguous_session(tmp_path):
    session = "2026-08-28"
    sources = {name: (tmp_path / f"{name}.json", {"artifact_identity": f"{name}:identity"})
               for name in ("descriptive", "screening", "tactical", "triage")}
    for path, payload in sources.values():
        path.write_text(json.dumps(payload), encoding="utf-8")
    for identity in ("old", "current"):
        run = tmp_path / "operations-review" / "daily-producer-runs-v1" / session / identity
        run.mkdir(parents=True)
        bundle = run / "ai_research_session_bundle.json"
        bundle.write_text(json.dumps({"session": session, "identity": identity}), encoding="utf-8")
        manifest = {
            "target_market_session": session,
            "run_identity": f"daily_producer_run:{identity}",
            "upstream_artifact_identities": {name: {"artifact_identity": f"{name}:identity"} for name in sources},
            "ai_delivery": {"ai_research_session_bundle.json": {"sha256": runtime_release._sha256(bundle)}},
        }
        (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="AMBIGUOUS_OR_MISSING"):
        runtime_release._producer_run(tmp_path, session, sources)
    _, manifest, _, bundle = runtime_release._producer_run(
        tmp_path, session, sources, run_identity="daily_producer_run:current",
    )
    assert manifest["run_identity"] == "daily_producer_run:current"
    assert bundle["identity"] == "current"


def test_run_identity_not_found_among_session_candidates_fails_closed(tmp_path):
    session = "2026-08-28"
    sources = {name: (tmp_path / f"{name}.json", {"artifact_identity": f"{name}:identity"})
               for name in ("descriptive", "screening", "tactical", "triage")}
    for path, payload in sources.values():
        path.write_text(json.dumps(payload), encoding="utf-8")
    run = tmp_path / "operations-review" / "daily-producer-runs-v1" / session / "only"
    run.mkdir(parents=True)
    bundle = run / "ai_research_session_bundle.json"
    bundle.write_text(json.dumps({"session": session, "identity": "only"}), encoding="utf-8")
    manifest = {
        "target_market_session": session,
        "run_identity": "daily_producer_run:only",
        "upstream_artifact_identities": {name: {"artifact_identity": f"{name}:identity"} for name in sources},
        "ai_delivery": {"ai_research_session_bundle.json": {"sha256": runtime_release._sha256(bundle)}},
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match=r"AMBIGUOUS_OR_MISSING:.*count=0"):
        runtime_release._producer_run(tmp_path, session, sources, run_identity="daily_producer_run:does-not-exist")


def test_selecting_current_run_does_not_delete_other_retained_runs(tmp_path):
    session = "2026-08-28"
    sources = {name: (tmp_path / f"{name}.json", {"artifact_identity": f"{name}:identity"})
               for name in ("descriptive", "screening", "tactical", "triage")}
    for path, payload in sources.values():
        path.write_text(json.dumps(payload), encoding="utf-8")
    for identity in ("old", "current"):
        run = tmp_path / "operations-review" / "daily-producer-runs-v1" / session / identity
        run.mkdir(parents=True)
        bundle = run / "ai_research_session_bundle.json"
        bundle.write_text(json.dumps({"session": session, "identity": identity}), encoding="utf-8")
        manifest = {
            "target_market_session": session,
            "run_identity": f"daily_producer_run:{identity}",
            "upstream_artifact_identities": {name: {"artifact_identity": f"{name}:identity"} for name in sources},
            "ai_delivery": {"ai_research_session_bundle.json": {"sha256": runtime_release._sha256(bundle)}},
        }
        (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    runtime_release._producer_run(tmp_path, session, sources, run_identity="daily_producer_run:current")
    old_run = tmp_path / "operations-review" / "daily-producer-runs-v1" / session / "old"
    assert (old_run / "run_manifest.json").is_file()
    assert (old_run / "ai_research_session_bundle.json").is_file()


def _flat_descriptive_source(tmp_path, session):
    descriptive_path = (tmp_path / "operations-review"
                         / f"market-wide-current-descriptive-research-v1-{session.replace('-', '')}" / "artifact.json")
    descriptive_path.parent.mkdir(parents=True)
    descriptive_path.write_text("{}", encoding="utf-8")
    return {"descriptive": (descriptive_path, {})}


def test_p3_snapshot_falls_back_to_retained_scaleout_when_no_attempt_root(tmp_path):
    session = "2026-08-28"
    sources = _flat_descriptive_source(tmp_path, session)
    scaleout_dir = tmp_path / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}"
    scaleout_dir.mkdir(parents=True)
    snapshot = {"resolved_completed_session": session, "retained_snapshot_session": session, "records": {}}
    (scaleout_dir / "p3f9b_mva_exact_session_snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    assert runtime_release._p3_snapshot(tmp_path, session, sources) == snapshot


def test_p3_snapshot_fails_closed_when_neither_attempt_root_nor_retained_scaleout_exists(tmp_path):
    session = "2026-08-28"
    sources = _flat_descriptive_source(tmp_path, session)
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="FROZEN_DESCRIPTIVE_ATTEMPT_ROOT_MISSING"):
        runtime_release._p3_snapshot(tmp_path, session, sources)


def test_retained_tier_handoff_allows_a_new_exact_run_with_identical_sources(tmp_path):
    session = "2026-08-28"
    handoff = tmp_path / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json"
    handoff.parent.mkdir(parents=True)
    source_identities = {name: {"artifact_identity": f"{name}:identity"}
                         for name in ("descriptive", "screening", "tactical", "triage")}
    handoff.write_text(json.dumps({
        "session": session,
        "market_session_proof": {"resolved_completed_session": session},
        "daily_producer": {"run_identity": "daily_producer_run:retained"},
        "upstream_evidence_identities": source_identities,
    }), encoding="utf-8")
    result = runtime_release._verify_retained_tier_lineage(
        tmp_path, session,
        {"run_identity": "daily_producer_run:current", "upstream_artifact_identities": source_identities},
    )
    assert result["retained_daily_producer_run_identity"] == "daily_producer_run:retained"
    assert result["runtime_daily_producer_run_identity"] == "daily_producer_run:current"
    assert result["source_lineage_status"] == "PASS"


def test_retained_tier_handoff_rejects_changed_sources(tmp_path):
    session = "2026-08-28"
    handoff = tmp_path / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(json.dumps({
        "session": session,
        "market_session_proof": {"resolved_completed_session": session},
        "daily_producer": {"run_identity": "daily_producer_run:retained"},
        "upstream_evidence_identities": {name: {"artifact_identity": f"{name}:old"}
                                        for name in ("descriptive", "screening", "tactical", "triage")},
    }), encoding="utf-8")
    current = {name: {"artifact_identity": f"{name}:current"}
               for name in ("descriptive", "screening", "tactical", "triage")}
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="TIER_HANDOFF_SOURCE_LINEAGE_MISMATCH:descriptive"):
        runtime_release._verify_retained_tier_lineage(
            tmp_path, session,
            {"run_identity": "daily_producer_run:current", "upstream_artifact_identities": current},
        )


def test_retained_canonical_session_materializes_exact_runtime_contract(tmp_path):
    from publish_dashboard import validate_workspace_projection
    # The older August fixture predates the mandatory current-product contract.
    session = "2026-09-17"
    result = runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, session)
    report = release_session_contract.resolve_release_session(tmp_path, runtime_release.RELEASE_SESSION_FILES, today=session)
    assert result["live_count"] == 858
    assert result["snapshot_count"] == 1683
    assert report.ready and report.session == session
    breadth = _rows(tmp_path / "market_breadth.csv")[0]
    assert {key: breadth[key] for key in ("n_up", "n_down", "n_flat")} == {"n_up": "380", "n_down": "282", "n_flat": "194"}
    hpg = next(row for row in _rows(tmp_path / "screen_snapshot.csv") if row["ticker"] == "HPG")
    assert hpg["date"] == session
    assert hpg["canonical_observation_status"] == "EXACT_SESSION_RETAINED"
    assert hpg["canonical_field_availability"] == "DIRECT_CANONICAL_MAPPING"
    analysis = json.loads((tmp_path / "analysis_latest.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert analysis["summary"]["session_date"] == manifest["freshness"]["reference_session"] == session
    assert analysis["summary"]["pct_above_ma200"] is None
    workspace = tmp_path / "data/investment_decision_workspace.json"
    payload = validate_workspace_projection(workspace, session)
    lineage = result["lineage"]["investment_decision_workspace"]
    assert len(payload["cards"]) == 1683
    assert payload["artifact_identity"] == lineage["artifact_identity"]
    assert workspace.read_bytes() == (ROOT / lineage["path"]).read_bytes()


def test_tampered_frozen_identity_fails_closed(tmp_path, monkeypatch):
    registry = copy.deepcopy(runtime_release.load_registry(ROOT))
    registry["sessions"][SESSION]["descriptive"]["artifact_identity"] = "tampered"
    monkeypatch.setattr(runtime_release, "load_registry", lambda root: registry)
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="CANONICAL_SOURCE_IDENTITY_MISMATCH:descriptive"):
        runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, SESSION)
    assert not list(tmp_path.iterdir())


def test_missing_or_mixed_session_frozen_source_fails_closed(tmp_path, monkeypatch):
    registry = copy.deepcopy(runtime_release.load_registry(ROOT))
    registry["sessions"][SESSION]["tactical"]["path"] = "operations-review/not-present.json"
    monkeypatch.setattr(runtime_release, "load_registry", lambda root: registry)
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="RETAINED_SOURCE_UNREADABLE"):
        runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, SESSION)

    registry = copy.deepcopy(runtime_release.load_registry(ROOT))
    registry["sessions"][SESSION]["descriptive"] = registry["sessions"]["2026-08-25"]["descriptive"]
    monkeypatch.setattr(runtime_release, "load_registry", lambda root: registry)
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="CANONICAL_SOURCE_SESSION_MISMATCH:descriptive"):
        runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, SESSION)


def test_staging_failure_does_not_mutate_existing_runtime(tmp_path, monkeypatch):
    original = tmp_path / "screen_snapshot.csv"
    original.write_text("ticker,exchange,date\nHPG,HSX,2026-08-25\n", encoding="utf-8")
    monkeypatch.setattr(runtime_release, "_build_release", lambda *args: (_ for _ in ()).throw(runtime_release.CanonicalRuntimeReleaseError("STAGING_FAILURE")))
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="STAGING_FAILURE"):
        runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, SESSION)
    assert original.read_text(encoding="utf-8") == "ticker,exchange,date\nHPG,HSX,2026-08-25\n"


def test_pipeline_materializes_before_runtime_readiness(tmp_path, monkeypatch):
    import canonical_post_close_pipeline as pipeline
    # The existing orchestration tests prove all other stages; this isolates the new boundary.
    seen = []
    monkeypatch.setattr(pipeline, "acquire_and_materialize", lambda *a, **k: {"artifact_root": tmp_path, "snapshot": {}, "resolved_completed_session": SESSION, "coverage": {}})
    monkeypatch.setattr(pipeline, "register_session_inputs", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "validate_and_freeze_completed_session", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "_git_head", lambda *a: "head")
    monkeypatch.setattr(pipeline, "run_daily_producer", lambda *a, **k: {"operation": {"opportunity": None}, "status": "COMPLETED", "run_identity": "x"})
    monkeypatch.setattr(pipeline, "materialize_canonical_runtime_release", lambda *a: seen.append("materialize") or {})
    monkeypatch.setattr(pipeline, "build_enrichment_components", lambda *a, **k: {
        "integrated_investment_decision_product": {"artifact": {"session": SESSION}},
    })
    monkeypatch.setattr(pipeline, "retain_prospective_decision_snapshot", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "build_decision_packet", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "run_prospective_collection", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "evaluate_dashboard_runtime_readiness", lambda *a: seen.append("readiness") or {"ready": True})
    monkeypatch.setattr(pipeline, "build_tiered_bundle", lambda *a, **k: {"session_handoff_bundle": {}, "bundle_dir": tmp_path})
    pipeline.run_canonical_post_close(tmp_path, tmp_path / "runtime", SESSION)
    assert seen == ["materialize", "readiness"]


def _workspace_release_fixture(tmp_path, monkeypatch):
    session = "2026-09-17"
    root = tmp_path / "producer"
    operation = root / "operation"
    operation.mkdir(parents=True)

    def write(path, payload):
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    workspace = {"schema_version": "1.0.0", "contract_version": runtime_release.workspace_contract.CONTRACT_VERSION,
                 "as_of_session": session, "cards": {"AAA": {}},
                 "coverage": {"ticker_denominator": 1, "zero_silent_ticker_drops": True}}
    workspace.update(runtime_release.workspace_contract.content_identity(workspace))
    source = write(operation / "investment_decision_workspace_projection.json", workspace)
    write(operation / "run_manifest.json", {"market_session": session, "operation_identity": "operation:exact"})
    write(operation / "unrelated.json", {"must_not_promote": True})
    manifest = {"run_identity": "run:exact", "daily_session_operation": {"directory": "operation", "identity": "operation:exact"},
                "current_product_projections": {"status": "MATERIALIZED", "session": session,
                    "workspace": {"artifact_identity": workspace["artifact_identity"], "as_of_session": session, "ticker_denominator": 1}}}
    run_path = write(root / "run_manifest.json", manifest)
    bundle_path = write(root / "bundle.json", {})
    sources = {}
    for name in runtime_release.REQUIRED_INPUTS:
        payload = {"records": {"AAA": {"exchange_or_market": "HOSE"}}, "artifact_identity": name}
        if name == "descriptive":
            payload["market_breadth"] = {"session": session, "advancing": 1, "declining": 0, "unchanged": 0}
        sources[name] = (write(root / f"{name}.json", payload), payload)
    monkeypatch.setattr(runtime_release, "_source_paths", lambda *a: (sources, {}))
    monkeypatch.setattr(runtime_release, "_producer_run", lambda *a, **k: (run_path, manifest, bundle_path, {}))
    monkeypatch.setattr(runtime_release, "_p3_snapshot", lambda *a: {"records": {"AAA": {"observations": [{"session": session, "close": 100}]}}})
    return root, source, workspace, manifest


def test_workspace_materialization_is_exact_deterministic_and_allowlisted(tmp_path, monkeypatch):
    from publish_dashboard import validate_workspace_projection
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    target = tmp_path / "runtime"
    target.mkdir()
    (target / "unrelated.json").write_bytes(b"preserve")
    runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    asset = target / "data/investment_decision_workspace.json"
    assert validate_workspace_projection(asset, "2026-09-17") == workspace
    assert asset.read_bytes() == source.read_bytes()
    first = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*")
             if p.is_file() and p.name != "observability_events.jsonl"}
    runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    second = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*")
             if p.is_file() and p.name != "observability_events.jsonl"}
    assert first == second
    assert set(second) == set(runtime_release.RELEASE_FILES) | {"unrelated.json"}
    assert second["unrelated.json"] == b"preserve"


@pytest.mark.parametrize("field,value,reason", [
    ("as_of_session", "2026-09-16", "WORKSPACE_SESSION_MISMATCH"),
    ("schema_version", "invalid", "WORKSPACE_SCHEMA_VERSION_MISMATCH"),
    ("contract_version", "invalid", "WORKSPACE_CONTRACT_VERSION_MISMATCH"),
    ("artifact_identity", "", "WORKSPACE_CONTENT_IDENTITY_MISMATCH"),
    ("artifact_identity", "tampered", "WORKSPACE_CONTENT_IDENTITY_MISMATCH"),
    ("artifact_sha256", "tampered", "WORKSPACE_CONTENT_IDENTITY_MISMATCH"),
    ("cards", {}, "WORKSPACE_EMPTY_CORPUS"),
    ("cards", {"AAA": {"tampered": True}}, "WORKSPACE_CONTENT_IDENTITY_MISMATCH"),
    ("coverage", {"ticker_denominator": 2, "zero_silent_ticker_drops": True}, "WORKSPACE_DENOMINATOR"),
    ("coverage", {"ticker_denominator": 1, "zero_silent_ticker_drops": False}, "WORKSPACE_DENOMINATOR"),
])
def test_invalid_workspace_fails_before_any_runtime_promotion(tmp_path, monkeypatch, field, value, reason):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    workspace[field] = value
    source.write_text(json.dumps(workspace), encoding="utf-8")
    target = tmp_path / "runtime"
    target.mkdir()
    (target / "bundle_manifest.json").write_bytes(b"prior release")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match=reason):
        runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    assert {p.name: p.read_bytes() for p in target.iterdir()} == {"bundle_manifest.json": b"prior release"}


def test_missing_exact_projection_does_not_use_existing_runtime_workspace(tmp_path, monkeypatch):
    root, source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    source.unlink()
    target = tmp_path / "runtime"
    (target / "data").mkdir(parents=True)
    asset = target / "data/investment_decision_workspace.json"
    asset.write_bytes(b"stale")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match="WORKSPACE_EXACT_SESSION_PROJECTION_MISSING"):
        runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    assert asset.read_bytes() == b"stale"


@pytest.mark.parametrize("section,key,value,reason", [
    ("daily_session_operation", "identity", "wrong", "WORKSPACE_OPERATION_IDENTITY_MISMATCH"),
    ("daily_session_operation", "directory", "", "WORKSPACE_OPERATION_LINEAGE_MISSING"),
    ("current_product_projections", "session", "2026-09-16", "WORKSPACE_PRODUCER_MATERIALIZATION_UNAVAILABLE"),
    ("workspace", "artifact_identity", "wrong", "WORKSPACE_CONTENT_IDENTITY_MISMATCH"),
])
def test_workspace_producer_lineage_fails_closed(tmp_path, monkeypatch, section, key, value, reason):
    root, _, _, manifest = _workspace_release_fixture(tmp_path, monkeypatch)
    container = manifest["current_product_projections"]["workspace"] if section == "workspace" else manifest[section]
    container[key] = value
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match=reason):
        runtime_release.materialize_canonical_runtime_release(root, tmp_path / "runtime", "2026-09-17")


def test_workspace_nested_file_is_restored_on_promotion_failure(tmp_path, monkeypatch):
    root, _, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    target = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    asset = target / "data/investment_decision_workspace.json"
    asset.write_bytes(b"old workspace")
    before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*")
             if p.is_file() and p.name != "observability_events.jsonl"}
    original_copy = runtime_release.atomic_copy_file
    failed = False

    def fail_manifest_once(source, destination, **kwargs):
        nonlocal failed
        if destination == target / "bundle_manifest.json" and not failed:
            failed = True
            raise OSError("promotion failure")
        return original_copy(source, destination, **kwargs)

    monkeypatch.setattr(runtime_release, "atomic_copy_file", fail_manifest_once)
    with pytest.raises(OSError, match="promotion failure"):
        runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    assert before == {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*")
             if p.is_file() and p.name != "observability_events.jsonl"}


def test_completed_session_replay_materializes_before_publisher_without_acquisition(tmp_path, monkeypatch):
    from tools import run_owner_daily as workflow
    from publish_dashboard import validate_workspace_projection
    root, source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    completion = {"session": "2026-09-17", "record": {"daily_producer_run_identity": "run:exact"}}
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "verify_daily_completion", lambda *a, **k: completion)
    monkeypatch.setattr(workflow, "commit_daily_state", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "_run_daily", lambda *a, **k: pytest.fail("replay must not acquire or rebuild"))
    monkeypatch.setattr(workflow, "publish_ai_handoff", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "materialize_action_center", lambda *a, **k: {"status": "READY", "view_path": "unused"})
    monkeypatch.setattr(workflow, "open_action_center_view", lambda *a, **k: {})
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda *a: {"status": "READY"})
    materialize = workflow.materialize_canonical_runtime_release
    seen = []

    def exact_materialize(*args, **kwargs):
        assert args == (root.resolve(), runtime.resolve(), "2026-09-17")
        assert kwargs == {"producer_run_identity": "run:exact"}
        seen.append("materialize")
        return materialize(*args, **kwargs)

    def publisher_validation(argv, **kwargs):
        assert "release_orchestrator.py" in argv[2]
        asset = runtime / "data/investment_decision_workspace.json"
        validate_workspace_projection(asset, "2026-09-17")
        assert asset.read_bytes() == source.read_bytes()
        seen.append("validate")
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(workflow, "materialize_canonical_runtime_release", exact_materialize)
    monkeypatch.setattr(workflow.subprocess, "run", publisher_validation)
    result = workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   replay_completed_session="2026-09-17")
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert seen == ["materialize", "validate"]


def test_replay_materialization_failure_never_invokes_live_publisher(tmp_path, monkeypatch):
    from tools import run_owner_daily as workflow
    root, source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    source.unlink()
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("must fail before publication"))
    result = workflow.publish_dashboard_release(root, tmp_path / "runtime", "2026-09-17", producer_run_identity="run:exact")
    assert result["status"] == "FAILED"
    assert "WORKSPACE_EXACT_SESSION_PROJECTION_MISSING" in result["reason"]
