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
    from publish_dashboard import validate_screener_master_projection, validate_workspace_projection
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
    screener = tmp_path / "data/screener_master_projection.json"
    screener_payload = validate_screener_master_projection(screener, session)
    screener_lineage = result["lineage"]["screener_master_projection"]
    assert len(screener_payload["cards"]) == 1683
    assert screener_payload["artifact_identity"] == screener_lineage["artifact_identity"]
    assert screener.read_bytes() == (ROOT / screener_lineage["path"]).read_bytes()


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
    screener = {"schema_version": runtime_release.screener_contract.SCHEMA_VERSION,
                "contract_version": runtime_release.screener_contract.CONTRACT_VERSION,
                "as_of_session": session, "cards": {"AAA": {}},
                "coverage": {"ticker_denominator": 1, "zero_silent_drops": True}}
    screener.update(runtime_release.screener_contract.content_identity(screener))
    screener_source = write(operation / "screener_master_projection.json", screener)
    home_summary = {"schema_version": runtime_release.dashboard_home_summary.SCHEMA_VERSION,
                     "contract_version": runtime_release.dashboard_home_summary.CONTRACT_VERSION,
                     "as_of_session": session, "source_artifact_identity": screener["artifact_identity"],
                     "denominator": 1}
    home_summary.update(runtime_release.dashboard_home_summary.content_identity(home_summary))
    write(operation / "dashboard_home_summary.json", home_summary)
    write(operation / "run_manifest.json", {"market_session": session, "operation_identity": "operation:exact"})
    write(operation / "unrelated.json", {"must_not_promote": True})
    manifest = {"run_identity": "run:exact", "daily_session_operation": {"directory": "operation", "identity": "operation:exact"},
                "current_product_projections": {"status": "MATERIALIZED", "session": session,
                    "workspace": {"artifact_identity": workspace["artifact_identity"], "as_of_session": session, "ticker_denominator": 1},
                    "screener_master_projection": {"artifact_identity": screener["artifact_identity"], "as_of_session": session,
                        "denominator": {"ticker_count": 1}},
                    "dashboard_home_summary": {"status": "MATERIALIZED", "artifact_identity": home_summary["artifact_identity"],
                        "as_of_session": session, "source_artifact_identity": screener["artifact_identity"], "denominator": 1}}}
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


def test_screener_materialization_is_exact_and_rejects_stale_runtime_copy(tmp_path, monkeypatch):
    from publish_dashboard import validate_screener_master_projection
    root, workspace_source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    source = workspace_source.parent / "screener_master_projection.json"
    target = tmp_path / "runtime"
    stale = target / "data/screener_master_projection.json"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale projection")
    runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    payload = validate_screener_master_projection(stale, "2026-09-17")
    assert payload["artifact_identity"] == runtime_release.screener_contract.content_identity(payload)["artifact_identity"]
    assert stale.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("field,value,reason", [
    ("as_of_session", "2026-09-16", "SCREENER_SESSION_MISMATCH"),
    ("contract_version", "invalid", "SCREENER_CONTRACT_VERSION_MISMATCH"),
    ("artifact_identity", "tampered", "SCREENER_CONTENT_IDENTITY_MISMATCH"),
    ("cards", {}, "SCREENER_EMPTY_CORPUS"),
])
def test_invalid_screener_fails_before_any_runtime_promotion(tmp_path, monkeypatch, field, value, reason):
    root, source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    screener_source = source.parent / "screener_master_projection.json"
    screener = json.loads(screener_source.read_text(encoding="utf-8"))
    screener[field] = value
    screener_source.write_text(json.dumps(screener), encoding="utf-8")
    target = tmp_path / "runtime"
    target.mkdir()
    (target / "bundle_manifest.json").write_bytes(b"prior release")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError, match=reason):
        runtime_release.materialize_canonical_runtime_release(root, target, "2026-09-17")
    assert {p.name: p.read_bytes() for p in target.iterdir()} == {"bundle_manifest.json": b"prior release"}


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
    # CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 1/4: presentation
    # UNKNOWN now blocks publication before it starts, and the stage-aware resume verifiers probe
    # real external state by default -- stub all of them here so this test still exercises what it
    # actually targets (materialize-before-publisher ordering), not the unrelated new gates.
    monkeypatch.setattr(workflow, "_presentation_bound_state", lambda *a, **k: "LEGITIMATE_UNAVAILABLE")
    monkeypatch.setattr(workflow, "_verify_dashboard_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_ai_handoff_published", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_verify_action_center_ready", lambda *a, **k: None)
    materialize = workflow.materialize_release_ready_runtime
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
        return SimpleNamespace(returncode=0, stdout="PUBLICATION_STATE=PUBLISHED\n", stderr="")

    def trusted_subset(*args, **kwargs):
        assert args == (root.resolve(), runtime.resolve(), "2026-09-17")
        asset = runtime / "data/investment_decision_workspace.json"
        validate_workspace_projection(asset, "2026-09-17")
        assert asset.read_bytes() == source.read_bytes()
        seen.append("trusted_subset")
        return {"session": "2026-09-17", "trusted_subset_ready": True}

    monkeypatch.setattr(workflow, "materialize_release_ready_runtime", exact_materialize)
    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", trusted_subset)
    monkeypatch.setattr(workflow.subprocess, "run", publisher_validation)
    result = workflow.run_workflow(root=root, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
                                   replay_completed_session="2026-09-17")
    assert result["status"] == "PASS"
    assert result["daily_status"] == "ALREADY_COMPLETED / REUSED"
    assert seen == ["materialize", "trusted_subset", "validate"]


def test_replay_materialization_failure_never_invokes_live_publisher(tmp_path, monkeypatch):
    from tools import run_owner_daily as workflow
    root, source, _, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    source.unlink()
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: pytest.fail("must fail before publication"))
    result = workflow.publish_dashboard_release(root, tmp_path / "runtime", "2026-09-17", producer_run_identity="run:exact")
    assert result["status"] == "FAILED"
    assert "WORKSPACE_EXACT_SESSION_PROJECTION_MISSING" in result["reason"]


# ---- restage_runtime_with_presentation_projection
# (CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1): additive overlay of the
# already-promoted runtime-served Workspace/Screener with the post-handoff presentation
# projection's enriched bytes. Must never touch sealed Producer evidence, and must degrade to
# SKIPPED (never raise) on anything unproven. ----

def test_restage_skipped_when_presentation_not_collected(tmp_path):
    result = runtime_release.restage_runtime_with_presentation_projection(
        tmp_path / "runtime", tmp_path, {"status": "UNAVAILABLE"},
    )
    assert result["status"] == "SKIPPED"


def test_restage_skipped_when_lineage_not_verified(tmp_path):
    result = runtime_release.restage_runtime_with_presentation_projection(
        tmp_path / "runtime", tmp_path, {"status": "COLLECTED", "lineage_status": "UNVERIFIED", "path": "x"},
    )
    assert result["status"] == "SKIPPED"


def test_restage_skipped_when_source_or_target_missing(tmp_path):
    runtime = tmp_path / "runtime"
    result = runtime_release.restage_runtime_with_presentation_projection(
        runtime, tmp_path,
        {"status": "COLLECTED", "session": "2026-09-17", "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
         "path": "nope.json"},
    )
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "SOURCE_OR_TARGET_WORKSPACE_MISSING"


def test_restage_never_raises_on_malformed_source_json(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    runtime = tmp_path / "runtime" / "data"
    runtime.mkdir(parents=True)
    (runtime / "investment_decision_workspace.json").write_text("{}", encoding="utf-8")
    result = runtime_release.restage_runtime_with_presentation_projection(
        tmp_path / "runtime", tmp_path,
        {"status": "COLLECTED", "session": "2026-09-17", "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
         "path": "bad.json"},
    )
    assert result["status"] == "SKIPPED"


def test_restage_overlays_valid_runtime_with_enriched_bytes_never_touching_sealed_evidence(tmp_path, monkeypatch):
    root, source, workspace, manifest = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, "2026-09-17")
    target_before = (runtime / "data" / "investment_decision_workspace.json").read_bytes()
    sealed_before = source.read_bytes()

    presentation_dir = root / "operations-review" / "post-handoff-presentation-projection-v1" / "2026-09-17"
    presentation_dir.mkdir(parents=True)
    enriched_workspace = {k: v for k, v in workspace.items() if k not in ("artifact_identity", "artifact_sha256")}
    enriched_workspace["cards"] = {"AAA": {"signal_velocity": {"overall_transition_state": "STABLE"}}}
    enriched_workspace.update(runtime_release.workspace_contract.content_identity(enriched_workspace))
    (presentation_dir / "investment_decision_workspace_projection.json").write_text(
        json.dumps(enriched_workspace), encoding="utf-8")
    screener_source = source.parent / "screener_master_projection.json"
    (presentation_dir / "screener_master_projection.json").write_text(
        screener_source.read_text(encoding="utf-8"), encoding="utf-8")

    presentation_result = {
        "status": "COLLECTED", "session": "2026-09-17",
        "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
        "path": str((presentation_dir / "investment_decision_workspace_projection.json").resolve().relative_to(root.resolve())),
    }
    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)

    assert result["status"] == "RESTAGED"
    assert result["workspace_artifact_identity"] == enriched_workspace["artifact_identity"]
    assert result["screener_master_projection_status"] == "RESTAGED"
    new_target = (runtime / "data" / "investment_decision_workspace.json").read_bytes()
    assert new_target != target_before
    assert json.loads(new_target)["cards"]["AAA"]["signal_velocity"]["overall_transition_state"] == "STABLE"
    # Sealed Producer evidence (the original operation-directory copy) must be untouched.
    assert source.read_bytes() == sealed_before


def test_restage_skipped_on_session_mismatch(tmp_path, monkeypatch):
    root, source, workspace, manifest = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, "2026-09-17")

    presentation_dir = root / "operations-review" / "post-handoff-presentation-projection-v1" / "2026-09-16"
    presentation_dir.mkdir(parents=True)
    mismatched = {k: v for k, v in workspace.items() if k not in ("artifact_identity", "artifact_sha256")}
    mismatched["as_of_session"] = "2026-09-16"
    mismatched.update(runtime_release.workspace_contract.content_identity(mismatched))
    (presentation_dir / "investment_decision_workspace_projection.json").write_text(
        json.dumps(mismatched), encoding="utf-8")

    presentation_result = {
        "status": "COLLECTED", "session": "2026-09-16",
        "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
        "path": str((presentation_dir / "investment_decision_workspace_projection.json").resolve().relative_to(root.resolve())),
    }
    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "SESSION_OR_CONTRACT_MISMATCH"


# =====================================================================================
# CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 2 / section 10
# items C+D: materialize_release_ready_runtime -- the ONE governed release-ready runtime
# boundary -- and its use through publish_dashboard_release (the exact call site of the
# original second-materialization erasure defect), never just the isolated restage helper.
# =====================================================================================

def _enriched_presentation_fixture(root, session, workspace, source):
    """Write an enriched post-handoff presentation projection plus its dedicated attestation
    artifact, exactly as canonical_daily_operation.py does after post-handoff observers run."""
    presentation_dir = root / "operations-review" / "post-handoff-presentation-projection-v1" / session
    presentation_dir.mkdir(parents=True)
    enriched_workspace = {k: v for k, v in workspace.items() if k not in ("artifact_identity", "artifact_sha256")}
    enriched_workspace["cards"] = {"AAA": {"signal_velocity": {"overall_transition_state": "STABLE"}}}
    enriched_workspace.update(runtime_release.workspace_contract.content_identity(enriched_workspace))
    (presentation_dir / "investment_decision_workspace_projection.json").write_text(
        json.dumps(enriched_workspace), encoding="utf-8")
    screener_source = source.parent / "screener_master_projection.json"
    (presentation_dir / "screener_master_projection.json").write_text(
        screener_source.read_text(encoding="utf-8"), encoding="utf-8")
    presentation_result = {
        "status": "COLLECTED", "session": session,
        "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
        "path": str((presentation_dir / "investment_decision_workspace_projection.json").resolve().relative_to(root.resolve())),
        "workspace_artifact_identity": enriched_workspace["artifact_identity"],
        "sealed_producer_workspace_artifact_identity": workspace.get("artifact_identity"),
    }
    import post_handoff_presentation_attestation as attestation
    attestation.write_attestation(
        root, session,
        presentation_projection=presentation_result,
        signal_velocity={"status": "COLLECTED", "artifact_identity": "velocity:test"},
        flow_price_divergence={"status": "COLLECTED", "artifact_identity": "flow_price:test"},
    )
    return enriched_workspace, presentation_result


def test_materialize_release_ready_runtime_restages_from_dedicated_attestation(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    session = "2026-09-17"
    enriched_workspace, _ = _enriched_presentation_fixture(root, session, workspace, source)
    runtime = tmp_path / "runtime"

    result = runtime_release.materialize_release_ready_runtime(root, runtime, session)

    assert result["presentation_restage"]["status"] == "RESTAGED"
    served = json.loads((runtime / "data" / "investment_decision_workspace.json").read_text(encoding="utf-8"))
    assert served["cards"]["AAA"]["signal_velocity"]["overall_transition_state"] == "STABLE"
    assert served["artifact_identity"] == enriched_workspace["artifact_identity"]
    # Sealed Producer evidence untouched.
    assert json.loads(source.read_text(encoding="utf-8"))["artifact_identity"] == workspace["artifact_identity"]


def test_materialize_release_ready_runtime_without_attestation_is_baseline_only(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    session = "2026-09-17"
    runtime = tmp_path / "runtime"

    result = runtime_release.materialize_release_ready_runtime(root, runtime, session)

    assert result["presentation_restage"]["status"] == "SKIPPED"
    served = json.loads((runtime / "data" / "investment_decision_workspace.json").read_text(encoding="utf-8"))
    assert served["artifact_identity"] == workspace["artifact_identity"]


def test_materialize_release_ready_runtime_manifest_identity_agrees_with_restaged_bytes(tmp_path, monkeypatch):
    """Section 10 item D: final runtime Workspace identity/hash matches the runtime manifest
    after presentation binding -- not merely the sealed baseline identity."""
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    session = "2026-09-17"
    enriched_workspace, _ = _enriched_presentation_fixture(root, session, workspace, source)
    runtime = tmp_path / "runtime"

    runtime_release.materialize_release_ready_runtime(root, runtime, session)

    manifest = json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8"))
    served = json.loads((runtime / "data" / "investment_decision_workspace.json").read_text(encoding="utf-8"))
    declared = manifest["lineage"]["investment_decision_workspace"]["artifact_identity"]
    assert declared == served["artifact_identity"] == enriched_workspace["artifact_identity"]
    assert manifest["lineage"]["investment_decision_workspace"]["sha256"] == runtime_release._sha256(
        runtime / "data" / "investment_decision_workspace.json")
    presentation_lineage = manifest["lineage"]["presentation_projection"]
    assert presentation_lineage["sealed_workspace_artifact_identity"] == workspace["artifact_identity"]
    assert presentation_lineage["restaged_workspace_artifact_identity"] == enriched_workspace["artifact_identity"]


def test_publish_dashboard_release_survives_presentation_projection_end_to_end(tmp_path, monkeypatch):
    """Section 10 item C: same-session Signal Velocity must reach the final Dashboard source
    bytes THROUGH publish_dashboard_release (the second-materialization erasure bug's exact
    call site), not merely through the isolated restage helper called directly."""
    from tools import run_owner_daily as workflow
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    session = "2026-09-17"
    _enriched_presentation_fixture(root, session, workspace, source)
    runtime = tmp_path / "runtime"

    class _Result:
        returncode = 0
        stdout = "PUBLICATION_STATE=PUBLISHED\n"
        stderr = ""

    monkeypatch.setattr(workflow, "materialize_canonical_trusted_subset", lambda *a, **k: {"session": session, "trusted_subset_ready": True})
    monkeypatch.setattr(workflow.subprocess, "run", lambda *a, **k: _Result())
    monkeypatch.setattr(workflow, "verify_dashboard_session", lambda web_dir, s: {"status": "READY", "expected_session": s, "observed_session": s})

    result = workflow.publish_dashboard_release(root, runtime, session, web_dir=tmp_path / "web", producer_run_identity="run:exact")

    assert result["status"] == "READY"
    served = json.loads((runtime / "data" / "investment_decision_workspace.json").read_text(encoding="utf-8"))
    assert served["cards"]["AAA"]["signal_velocity"]["overall_transition_state"] == "STABLE"


# =====================================================================================
# DASHBOARD_PRESENTATION_RESTAGE_HOME_SUMMARY_COHERENCE_V1: the post-handoff restage replaced
# the runtime Screener (identity A -> B) but left the sealed Home summary bound to A, so the
# governed publisher (correctly) refused DASHBOARD_HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_MISMATCH.
# The restage must move Workspace + Screener + Home summary + manifest lineage as one unit.
# =====================================================================================

RESTAGE_SESSION = "2026-09-17"
RUNTIME_PRESENTATION_FILES = ("data/investment_decision_workspace.json", "data/screener_master_projection.json",
                              "data/dashboard_home_summary.json", "bundle_manifest.json")


def _runtime_bytes(runtime):
    return {name: (runtime / name).read_bytes() for name in RUNTIME_PRESENTATION_FILES}


def _presentation_with_new_screener(root, workspace, source, *, with_screener=True, screener_mutator=None,
                                    attest=False, declared_screener_identity=True):
    """Enriched presentation Workspace plus (optionally) a presentation Screener whose content --
    and therefore identity -- differs from the sealed baseline Screener, exactly like 2026-09-23."""
    presentation_dir = root / "operations-review" / "post-handoff-presentation-projection-v1" / RESTAGE_SESSION
    presentation_dir.mkdir(parents=True, exist_ok=True)
    enriched_workspace = {k: v for k, v in workspace.items() if k not in ("artifact_identity", "artifact_sha256")}
    enriched_workspace["cards"] = {"AAA": {"signal_velocity": {"overall_transition_state": "STABLE"}}}
    enriched_workspace.update(runtime_release.workspace_contract.content_identity(enriched_workspace))
    (presentation_dir / "investment_decision_workspace_projection.json").write_text(json.dumps(enriched_workspace), encoding="utf-8")
    new_screener = None
    if with_screener:
        sealed_screener = json.loads((source.parent / "screener_master_projection.json").read_text(encoding="utf-8"))
        new_screener = {k: v for k, v in sealed_screener.items() if k not in ("artifact_identity", "artifact_sha256")}
        new_screener["cards"] = {"AAA": {"signal_velocity": {"overall_transition_state": "STABLE"}}}
        new_screener["requested_at"] = f"{RESTAGE_SESSION}T17:03:04+07:00"
        new_screener.update(runtime_release.screener_contract.content_identity(new_screener))
        assert new_screener["artifact_identity"] != sealed_screener["artifact_identity"]
        if screener_mutator is not None:
            screener_mutator(new_screener)
        (presentation_dir / "screener_master_projection.json").write_text(json.dumps(new_screener), encoding="utf-8")
    presentation_result = {
        "status": "COLLECTED", "session": RESTAGE_SESSION,
        "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
        "path": str((presentation_dir / "investment_decision_workspace_projection.json").resolve().relative_to(root.resolve())),
        "workspace_artifact_identity": enriched_workspace["artifact_identity"],
        "sealed_producer_workspace_artifact_identity": workspace.get("artifact_identity"),
    }
    if new_screener is not None and declared_screener_identity:
        presentation_result["screener_master_projection_artifact_identity"] = new_screener.get("artifact_identity")
    if attest:
        import post_handoff_presentation_attestation as attestation
        attestation.write_attestation(root, RESTAGE_SESSION, presentation_projection=presentation_result)
    return enriched_workspace, new_screener, presentation_result


def _assert_publisher_accepts_runtime_pair(runtime):
    from publish_dashboard import validate_dashboard_home_summary
    screener = json.loads((runtime / "data" / "screener_master_projection.json").read_text(encoding="utf-8"))
    summary = validate_dashboard_home_summary(runtime / "data" / "dashboard_home_summary.json", RESTAGE_SESSION,
                                              screener_artifact_identity=screener["artifact_identity"])
    assert summary["source_artifact_identity"] == screener["artifact_identity"]


def test_restage_rederives_home_summary_from_restaged_screener(tmp_path, monkeypatch):
    """The exact 2026-09-23 failure shape: baseline Screener A + Home summary bound to A, then a
    presentation Screener B. After restage the runtime Home summary must be derived from B."""
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    baseline_screener = json.loads((runtime / "data" / "screener_master_projection.json").read_text(encoding="utf-8"))
    baseline_home = json.loads((runtime / "data" / "dashboard_home_summary.json").read_text(encoding="utf-8"))
    assert baseline_home["source_artifact_identity"] == baseline_screener["artifact_identity"]  # A bound to A
    sealed_home_bytes = (source.parent / "dashboard_home_summary.json").read_bytes()
    _, new_screener, presentation_result = _presentation_with_new_screener(root, workspace, source)

    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)

    assert result["status"] == "RESTAGED"
    assert result["screener_master_projection_status"] == "RESTAGED"
    assert result["dashboard_home_summary_status"] == "RESTAGED"
    served_screener = json.loads((runtime / "data" / "screener_master_projection.json").read_text(encoding="utf-8"))
    served_home = json.loads((runtime / "data" / "dashboard_home_summary.json").read_text(encoding="utf-8"))
    assert served_screener["artifact_identity"] == new_screener["artifact_identity"]  # runtime Screener = B
    assert served_home["source_artifact_identity"] == new_screener["artifact_identity"]  # Home bound to B
    expected_home = runtime_release.dashboard_home_summary.build_home_summary(
        new_screener, requested_at=new_screener["requested_at"])
    assert served_home == expected_home
    assert served_home["artifact_identity"] != baseline_home["artifact_identity"]
    assert result["dashboard_home_summary_artifact_identity"] == served_home["artifact_identity"]

    manifest = json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8"))
    home_entry = manifest["lineage"]["dashboard_home_summary"]
    assert home_entry["artifact_identity"] == served_home["artifact_identity"]
    assert home_entry["sha256"] == runtime_release._sha256(runtime / "data" / "dashboard_home_summary.json")
    assert home_entry["source_artifact_identity"] == new_screener["artifact_identity"]
    assert home_entry["derivation"] == runtime_release.HOME_SUMMARY_RESTAGE_DERIVATION
    assert manifest["lineage"]["screener_master_projection"]["artifact_identity"] == new_screener["artifact_identity"]
    presentation_lineage = manifest["lineage"]["presentation_projection"]
    assert presentation_lineage["sealed_screener_master_projection_artifact_identity"] == baseline_screener["artifact_identity"]
    assert presentation_lineage["sealed_dashboard_home_summary_artifact_identity"] == baseline_home["artifact_identity"]
    assert presentation_lineage["restaged_dashboard_home_summary_artifact_identity"] == served_home["artifact_identity"]

    runtime_release._verify_runtime_manifest_coherence(runtime)
    _assert_publisher_accepts_runtime_pair(runtime)
    # Sealed Producer evidence untouched.
    assert (source.parent / "dashboard_home_summary.json").read_bytes() == sealed_home_bytes


def test_materialize_release_ready_runtime_rebinds_home_summary_end_to_end(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    _, new_screener, _ = _presentation_with_new_screener(root, workspace, source, attest=True)
    runtime = tmp_path / "runtime"

    result = runtime_release.materialize_release_ready_runtime(root, runtime, RESTAGE_SESSION)

    assert result["presentation_restage"]["status"] == "RESTAGED"
    served_home = json.loads((runtime / "data" / "dashboard_home_summary.json").read_text(encoding="utf-8"))
    assert served_home["source_artifact_identity"] == new_screener["artifact_identity"]
    _assert_publisher_accepts_runtime_pair(runtime)


def test_publisher_still_refuses_the_pre_fix_mixed_runtime_shape(tmp_path, monkeypatch):
    """Guard preserved: the pre-fix runtime (Screener B beside a Home summary bound to A) is
    exactly what the governed publisher must keep refusing."""
    from publish_dashboard import validate_dashboard_home_summary
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    _, new_screener, _ = _presentation_with_new_screener(root, workspace, source)
    with pytest.raises(ValueError, match="DASHBOARD_HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_MISMATCH"):
        validate_dashboard_home_summary(runtime / "data" / "dashboard_home_summary.json", RESTAGE_SESSION,
                                        screener_artifact_identity=new_screener["artifact_identity"])


@pytest.mark.parametrize("breakage,reason", [
    ("tampered_identity", "PRESENTATION_SCREENER_CONTENT_IDENTITY_MISMATCH"),
    ("wrong_session", "PRESENTATION_SCREENER_SESSION_MISMATCH"),
    ("wrong_contract", "PRESENTATION_SCREENER_CONTRACT_VERSION_MISMATCH"),
    ("denominator", "PRESENTATION_SCREENER_DENOMINATOR_OR_SILENT_DROP_VIOLATION"),
    ("declared_identity", "PRESENTATION_SCREENER_IDENTITY_DIVERGES_FROM_PRESENTATION_RESULT"),
    ("not_json", "JSONDecodeError"),
])
def test_malformed_presentation_screener_never_creates_a_mixed_runtime(tmp_path, monkeypatch, breakage, reason):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    before = _runtime_bytes(runtime)

    def mutate(screener):
        if breakage == "tampered_identity":
            screener["artifact_identity"] = "screener_master_projection/v1:" + "0" * 64
        elif breakage == "wrong_session":
            screener["as_of_session"] = "2026-09-16"
            screener.update(runtime_release.screener_contract.content_identity(screener))
        elif breakage == "wrong_contract":
            screener["contract_version"] = "screener_master_projection/v0"
        elif breakage == "denominator":
            screener["coverage"] = {"ticker_denominator": 2, "zero_silent_drops": True}
            screener.update(runtime_release.screener_contract.content_identity(screener))

    _, _, presentation_result = _presentation_with_new_screener(root, workspace, source, screener_mutator=mutate)
    if breakage == "declared_identity":
        presentation_result["screener_master_projection_artifact_identity"] = "screener_master_projection/v1:" + "f" * 64
    if breakage == "not_json":
        (root / presentation_result["path"]).parent.joinpath("screener_master_projection.json").write_text("{nope", encoding="utf-8")

    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)

    assert result["status"] == "SKIPPED"
    assert reason in result["reason"]
    assert _runtime_bytes(runtime) == before  # no enriched Workspace beside a stale Screener
    runtime_release._verify_runtime_manifest_coherence(runtime)
    _assert_publisher_accepts_runtime_pair(runtime)


def test_home_summary_derivation_failure_keeps_baseline_set_and_never_claims_success(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    _presentation_with_new_screener(root, workspace, source, attest=True)
    runtime = tmp_path / "runtime"

    def _boom(*_a, **_k):
        raise runtime_release.dashboard_home_summary.DashboardHomeSummaryError("SIMULATED_DERIVATION_FAILURE")

    monkeypatch.setattr(runtime_release.dashboard_home_summary, "build_home_summary", _boom)
    result = runtime_release.materialize_release_ready_runtime(root, runtime, RESTAGE_SESSION)

    restage = result["presentation_restage"]
    assert restage["status"] == "SKIPPED"
    assert "HOME_SUMMARY_DERIVATION_FAILED" in restage["reason"]
    served_workspace = json.loads((runtime / "data" / "investment_decision_workspace.json").read_text(encoding="utf-8"))
    assert served_workspace["artifact_identity"] == workspace["artifact_identity"]  # baseline, not enriched
    manifest = json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert "presentation_projection" not in manifest["lineage"]
    runtime_release._verify_runtime_manifest_coherence(runtime)
    _assert_publisher_accepts_runtime_pair(runtime)


def test_failure_after_first_runtime_write_restores_every_touched_file(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    before = _runtime_bytes(runtime)
    _, _, presentation_result = _presentation_with_new_screener(root, workspace, source)
    monkeypatch.setattr(runtime_release, "_patch_runtime_manifest_after_restage", lambda *a, **k: "MANIFEST_WRITE_FAILED")

    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)

    assert result["status"] == "SKIPPED"
    assert result["reason"] == "RUNTIME_MANIFEST_MANIFEST_WRITE_FAILED:RUNTIME_RESTORED"
    assert _runtime_bytes(runtime) == before


def test_workspace_only_restage_preserves_baseline_screener_home_summary_pair(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    before = _runtime_bytes(runtime)
    derivations = []
    real_build = runtime_release.dashboard_home_summary.build_home_summary
    monkeypatch.setattr(runtime_release.dashboard_home_summary, "build_home_summary",
                        lambda *a, **k: derivations.append(1) or real_build(*a, **k))
    enriched_workspace, _, presentation_result = _presentation_with_new_screener(root, workspace, source, with_screener=False)

    result = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)

    assert result["status"] == "RESTAGED"
    assert result["screener_master_projection_status"] == "SKIPPED"
    assert result["dashboard_home_summary_status"] == "BASELINE_PRESERVED"
    assert derivations == []
    after = _runtime_bytes(runtime)
    for name in ("data/screener_master_projection.json", "data/dashboard_home_summary.json"):
        assert after[name] == before[name]
    served_workspace = json.loads(after["data/investment_decision_workspace.json"])
    assert served_workspace["artifact_identity"] == enriched_workspace["artifact_identity"]
    runtime_release._verify_runtime_manifest_coherence(runtime)
    _assert_publisher_accepts_runtime_pair(runtime)


def test_repeated_same_presentation_restage_is_idempotent(tmp_path, monkeypatch):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    baseline_manifest = json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8"))
    _, _, presentation_result = _presentation_with_new_screener(root, workspace, source)

    first = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)
    after_first = _runtime_bytes(runtime)
    second = runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)
    after_second = _runtime_bytes(runtime)

    assert first["status"] == second["status"] == "RESTAGED"
    assert second["dashboard_home_summary_status"] == "ALREADY_BOUND_TO_RESTAGED_SCREENER"
    assert after_second == after_first
    presentation_lineage = json.loads(after_second["bundle_manifest.json"])["lineage"]["presentation_projection"]
    assert presentation_lineage["sealed_screener_master_projection_artifact_identity"] == \
        baseline_manifest["lineage"]["screener_master_projection"]["artifact_identity"]
    assert presentation_lineage["sealed_dashboard_home_summary_artifact_identity"] == \
        baseline_manifest["lineage"]["dashboard_home_summary"]["artifact_identity"]
    runtime_release._verify_runtime_manifest_coherence(runtime)


def test_coherence_verifier_detects_home_summary_bound_to_another_screener(tmp_path, monkeypatch):
    """Even when the manifest agrees with the served Home summary bytes, a Home summary bound to a
    Screener other than the one actually served must fail the runtime coherence check."""
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    _, _, presentation_result = _presentation_with_new_screener(root, workspace, source)
    assert runtime_release.restage_runtime_with_presentation_projection(runtime, root, presentation_result)["status"] == "RESTAGED"
    runtime_release._verify_runtime_manifest_coherence(runtime)

    home_path = runtime / "data" / "dashboard_home_summary.json"
    stale = {k: v for k, v in json.loads(home_path.read_text(encoding="utf-8")).items()
             if k not in ("artifact_identity", "artifact_sha256")}
    stale["source_artifact_identity"] = "screener_master_projection/v1:" + "a" * 64
    stale.update(runtime_release.dashboard_home_summary.content_identity(stale))
    home_path.write_text(json.dumps(stale), encoding="utf-8")
    manifest_path = runtime / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["lineage"]["dashboard_home_summary"].update(
        {"artifact_identity": stale["artifact_identity"], "sha256": runtime_release._sha256(home_path)})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError,
                       match="RUNTIME_HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_INCOHERENT_AFTER_RESTAGE"):
        runtime_release._verify_runtime_manifest_coherence(runtime)


@pytest.mark.parametrize("key,relative,label", [
    ("screener_master_projection", "data/screener_master_projection.json", "SCREENER"),
    ("dashboard_home_summary", "data/dashboard_home_summary.json", "HOME_SUMMARY"),
])
def test_coherence_verifier_detects_manifest_identity_drift(tmp_path, monkeypatch, key, relative, label):
    root, source, workspace, _ = _workspace_release_fixture(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(root, runtime, RESTAGE_SESSION)
    runtime_release._verify_runtime_manifest_coherence(runtime)
    manifest_path = runtime / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["lineage"][key]["artifact_identity"] = "drifted"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runtime_release.CanonicalRuntimeReleaseError,
                       match=f"RUNTIME_MANIFEST_{label}_IDENTITY_INCOHERENT_AFTER_RESTAGE"):
        runtime_release._verify_runtime_manifest_coherence(runtime)
