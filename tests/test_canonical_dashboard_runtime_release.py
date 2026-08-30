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
    result = runtime_release.materialize_canonical_runtime_release(ROOT, tmp_path, SESSION)
    report = release_session_contract.resolve_release_session(tmp_path, runtime_release.RELEASE_SESSION_FILES, today=SESSION)
    assert result["live_count"] == 889
    assert result["snapshot_count"] == 1683
    assert report.ready and report.session == SESSION
    breadth = _rows(tmp_path / "market_breadth.csv")[0]
    assert {key: breadth[key] for key in ("n_up", "n_down", "n_flat")} == {"n_up": "378", "n_down": "289", "n_flat": "220"}
    hpg = next(row for row in _rows(tmp_path / "screen_snapshot.csv") if row["ticker"] == "HPG")
    assert hpg["date"] == SESSION
    assert hpg["canonical_observation_status"] == "EXACT_SESSION_RETAINED"
    assert hpg["canonical_field_availability"] == "DIRECT_CANONICAL_MAPPING"
    analysis = json.loads((tmp_path / "analysis_latest.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert analysis["summary"]["session_date"] == manifest["freshness"]["reference_session"] == SESSION
    assert analysis["summary"]["pct_above_ma200"] is None


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
    monkeypatch.setattr(pipeline, "build_enrichment_components", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "build_decision_packet", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "run_prospective_collection", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "evaluate_dashboard_runtime_readiness", lambda *a: seen.append("readiness") or {"ready": True})
    monkeypatch.setattr(pipeline, "build_tiered_bundle", lambda *a, **k: {"session_handoff_bundle": {}, "bundle_dir": tmp_path})
    pipeline.run_canonical_post_close(tmp_path, tmp_path / "runtime", SESSION)
    assert seen == ["materialize", "readiness"]
