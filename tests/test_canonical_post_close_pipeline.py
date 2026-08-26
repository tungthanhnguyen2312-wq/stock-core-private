import copy
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

import canonical_post_close_pipeline as cpc
import daily_session_level2_package as level2
from daily_research_session_operations import load_registry
from vn_time import VN_TZ

ROOT = Path(__file__).resolve().parents[1]


def _registry_copy_at(tmp_path):
    registry = copy.deepcopy(load_registry(ROOT))
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _minimal_fake_result(tmp_path):
    return {
        "session": "2026-08-25",
        "producer_result": {"status": "COMPLETED"},
        "tiers": {
            "session_handoff_bundle": {
                "market_session_proof": {}, "market_coverage": {}, "breadth": {}, "tactical_counts": {},
                "high_priority_review_count": 0,
                "daily_producer": {"operation_identity": "x", "run_identity": "y", "status": "COMPLETED"},
                "current_research_packet_identity": None, "prospective_cohort_snapshot_identity": None,
                "blocked_dimensions": [], "warnings": [],
            },
            "full_universe_bundle_index": {"manifest_path": "x"},
            "bundle_dir": tmp_path,
            "dashboard_release_set_index": {"ready_for_governed_publication": True},
        },
    }


def _make_snapshot(session, *, requested_at, exact, total, **extra):
    return {
        "resolved_completed_session": session,
        "retained_snapshot_session": session,
        "snapshot_sha256": "a" * 64,
        "snapshot_identity": "p3f9_exact_session_snapshot:" + "a" * 64,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "attempted_candidate_count": total,
        "exact_session_observed_count": exact,
        "requested_at": requested_at,
        **extra,
    }


def _write_snapshot(paths, session, **kwargs):
    snapshot = _make_snapshot(session, **kwargs)
    paths["exact_session_snapshot"].parent.mkdir(parents=True, exist_ok=True)
    paths["exact_session_snapshot"].write_text(json.dumps(snapshot), encoding="utf-8")
    return snapshot


def _write_triage(paths, session):
    triage = {"source_market_session": session, "artifact_identity": "full_universe_entry_candidate_triage:" + "b" * 64}
    paths["session_triage"].parent.mkdir(parents=True, exist_ok=True)
    paths["session_triage"].write_text(json.dumps(triage), encoding="utf-8")
    return triage


def _write_runtime_release(root, session, *, analysis_session=None, live_session=None):
    analysis_session = analysis_session or session
    live_session = live_session or session
    (root / "bundle_manifest.json").write_text(json.dumps({
        "freshness": {"reference_session": session, "blocked": False, "status": "fresh"},
    }), encoding="utf-8")
    (root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8")
    (root / "market_breadth.csv").write_text(
        f"group,date\nALL,{session}\n", encoding="utf-8")
    (root / "analysis_latest.json").write_text(json.dumps({
        "summary": {"session_date": analysis_session},
    }), encoding="utf-8")
    (root / "screen_snapshot_live.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{live_session}\n", encoding="utf-8")


def test_runtime_release_readiness_rejects_stale_prior_session(tmp_path):
    _write_runtime_release(tmp_path, "2026-08-25")
    readiness = cpc.evaluate_dashboard_runtime_readiness(tmp_path, "2026-08-26")
    assert readiness["ready"] is False
    assert readiness["resolved_session"] == "2026-08-25"
    assert readiness["reason"] == "RUNTIME_RELEASE_SESSION_MISMATCH:expected=2026-08-26:observed=2026-08-25"


def test_runtime_release_readiness_accepts_exact_coherent_session(tmp_path):
    _write_runtime_release(tmp_path, "2026-08-26")
    readiness = cpc.evaluate_dashboard_runtime_readiness(tmp_path, "2026-08-26")
    assert readiness["ready"] is True
    assert readiness["resolved_session"] == "2026-08-26"
    assert readiness["reason"] is None


@pytest.mark.parametrize("variant", ("missing", "analysis_mismatch", "live_mismatch"))
def test_runtime_release_readiness_fails_closed_for_missing_or_mismatched_artifact(tmp_path, variant):
    _write_runtime_release(
        tmp_path, "2026-08-26",
        analysis_session="2026-08-25" if variant == "analysis_mismatch" else None,
        live_session="2026-08-25" if variant == "live_mismatch" else None,
    )
    if variant == "missing":
        (tmp_path / "market_breadth.csv").unlink()
    readiness = cpc.evaluate_dashboard_runtime_readiness(tmp_path, "2026-08-26")
    assert readiness["ready"] is False
    assert readiness["reason"] == "RUNTIME_RELEASE_SESSION_CONTRACT_FAILED"


# --- 1. explicit requested session required ---

def test_explicit_session_required_by_pipeline():
    with pytest.raises(cpc.CanonicalPostCloseError, match="EXPLICIT_SESSION_REQUIRED"):
        cpc.run_canonical_post_close(ROOT, ROOT.parent / "dashboard-runtime", "")


def test_explicit_session_required_by_cli(capsys):
    import daily_analysis_pipeline as dap
    rc = dap.main(["--runtime-root", str(ROOT.parent / "dashboard-runtime"), "--canonical-post-close"])
    assert rc == 2
    assert "requires an explicit --session" in capsys.readouterr().err


# --- 2. same-day partial/intraday session fails closed ---

def test_partial_session_evidence_fails_closed(tmp_path, monkeypatch):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    now = datetime(2026, 8, 27, 10, 0, tzinfo=VN_TZ)  # past the same-day gate; isolates the coverage check

    def fake_materialize(root, sess, runtime_root, workers=12, now=None, execution_root=None):
        _write_snapshot(paths, session, requested_at=f"{session}T16:07:09+07:00", exact=10, total=1683)

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    with pytest.raises(cpc.CanonicalPostCloseError, match="PARTIAL_OR_INTRADAY_SESSION_EVIDENCE"):
        cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime", now=now)


# --- 3. canonical mode does not use legacy VCI/KBS acquisition ---

def test_module_never_references_legacy_vci_kbs_route():
    # Prose in the module's own docstrings/comments may name vn_stock_pipeline.py to document why
    # it is deliberately excluded; only an actual import or subprocess invocation pattern matters.
    source = (ROOT / "canonical_post_close_pipeline.py").read_text(encoding="utf-8")
    assert "import vn_stock_pipeline" not in source
    assert '"vn_stock_pipeline.py"' not in source
    assert "'vn_stock_pipeline.py'" not in source


def test_canonical_post_close_flag_never_invokes_legacy_step_runner(tmp_path, monkeypatch):
    import daily_analysis_pipeline as dap
    calls = []

    def fake_runner(command, cwd, env, check):
        calls.append(command)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("canonical_post_close_pipeline.run_canonical_post_close", lambda *a, **k: _minimal_fake_result(tmp_path))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    rc = dap.main(["--runtime-root", str(runtime), "--session", "2026-08-25", "--canonical-post-close"], runner=fake_runner)
    assert rc == 0
    assert calls == []  # vn_stock_pipeline.py / macro_sync.py / etc. were never subprocessed


# --- 4. DNSE retained exact-session provenance is preserved ---

def test_acquisition_provenance_passthrough(tmp_path, monkeypatch):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    now = datetime(2026, 8, 27, 10, 0, tzinfo=VN_TZ)  # past the same-day gate

    def fake_materialize(root, sess, runtime_root, workers=12, now=None, execution_root=None):
        _write_snapshot(
            paths, session, requested_at=f"{session}T19:05:00+07:00", exact=500, total=1000,
            provider="DNSE", artifact_identity="p3f9_exact_session_mva_snapshot:deadbeef",
        )

    def fake_maybe_build_triage(root, s, execution_root=None):
        _write_triage(paths, s)
        return {"built": True}

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", fake_maybe_build_triage)

    result = cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime", now=now)
    assert result["snapshot"]["artifact_identity"] == "p3f9_exact_session_mva_snapshot:deadbeef"
    assert result["snapshot"]["provider"] == "DNSE"
    assert result["resolved_completed_session"] == session


# --- 5. runtime materialization targets only canonical runtime ---

def test_acquisition_never_writes_into_runtime_root(tmp_path, monkeypatch):
    session = "2026-08-26"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    paths = level2.session_artifact_paths(tmp_path, session)
    now = datetime(2026, 8, 27, 10, 0, tzinfo=VN_TZ)  # past the same-day gate

    def fake_materialize(root, sess, runtime_root_arg, workers=12, now=None, execution_root=None):
        assert runtime_root_arg == runtime_root
        _write_snapshot(paths, session, requested_at=f"{session}T19:05:00+07:00", exact=50, total=100)

    def fake_maybe_build_triage(root, s, execution_root=None):
        _write_triage(paths, s)
        return {"built": True}

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", fake_maybe_build_triage)

    cpc.acquire_and_materialize(tmp_path, session, runtime_root, now=now)
    assert list(runtime_root.iterdir()) == []


# --- 6. research components receive the same exact session (real retained evidence replay) ---

def test_enrichment_components_stamp_requested_session(tmp_path, monkeypatch):
    session = "2026-08-25"
    monkeypatch.setattr(cpc, "enrichment_output_path", lambda root, s, name: tmp_path / f"{name}.json")
    results = cpc.build_enrichment_components(ROOT, session)
    field_by_name = {"financial_momentum": "session", "corporate_event_context": "research_session", "historical_context": "session"}
    assert set(results) == set(field_by_name)
    for name, session_field in field_by_name.items():
        row = results[name]
        assert row["status"] in ("BUILT", "PRIOR_AS_OF_CONTEXT", "UNAVAILABLE")
        if row["status"] == "BUILT":
            assert row["artifact"].get(session_field) == session


# --- 7. component-local missing evidence does not globally reject unrelated uses ---

def test_component_local_failure_does_not_block_unrelated_components(tmp_path, monkeypatch):
    import current_corporate_event_context

    def boom(**kwargs):
        raise RuntimeError("SIMULATED_COMPONENT_FAILURE")

    monkeypatch.setattr(current_corporate_event_context, "build_artifact", boom)
    monkeypatch.setattr(cpc, "enrichment_output_path", lambda root, s, name: tmp_path / f"{name}.json")
    results = cpc.build_enrichment_components(ROOT, "2026-08-25")
    assert "SIMULATED_COMPONENT_FAILURE" in (results["corporate_event_context"].get("reason") or "")
    assert results["corporate_event_context"]["status"] in ("PRIOR_AS_OF_CONTEXT", "UNAVAILABLE")
    if results["corporate_event_context"]["status"] == "PRIOR_AS_OF_CONTEXT":
        assert results["corporate_event_context"]["path"] == level2.session_artifact_paths(
            ROOT, "2026-08-25"
        )["corporate_event_context"]
    # unrelated components still ran independently and reached a definitive status, not skipped
    assert results["financial_momentum"]["status"] in ("BUILT", "PRIOR_AS_OF_CONTEXT", "UNAVAILABLE")
    assert results["historical_context"]["status"] in ("BUILT", "PRIOR_AS_OF_CONTEXT", "UNAVAILABLE")


# --- 8. session registration occurs only after required inputs pass ---

def test_registration_refuses_when_required_input_missing(tmp_path, monkeypatch):
    session = "2026-08-25"
    registry_path = _registry_copy_at(tmp_path)
    original_session_artifact_paths = level2.session_artifact_paths

    def broken_paths(root, s):
        paths = dict(original_session_artifact_paths(root, s))
        paths["descriptive_research"] = tmp_path / "does_not_exist.json"
        return paths

    monkeypatch.setattr(cpc.level2, "session_artifact_paths", broken_paths)
    with pytest.raises(cpc.CanonicalPostCloseError, match="REQUIRED_REGISTRY_INPUT_UNAVAILABLE:descriptive"):
        cpc.register_session_inputs(ROOT, session, registry_path=registry_path)


# --- 9. frozen conflicting session identity is refused ---

def test_frozen_conflicting_identity_refused(tmp_path, monkeypatch):
    session = "2026-08-25"  # already COMPLETED_RETAINED_EVIDENCE in the real registry
    registry_path = _registry_copy_at(tmp_path)
    fake_paths = {}
    for reg_key, l2_key in cpc.REGISTRY_KEY_TO_LEVEL2_KEY.items():
        p = tmp_path / f"{l2_key}.json"
        p.write_text(json.dumps({"artifact_identity": f"fake:{reg_key}"}), encoding="utf-8")
        fake_paths[l2_key] = p
    monkeypatch.setattr(cpc.level2, "session_artifact_paths", lambda root, s: fake_paths)
    with pytest.raises(cpc.CanonicalPostCloseError, match="COMPLETED_SESSION_INPUT_MUTATION_REJECTED"):
        cpc.register_session_inputs(ROOT, session, registry_path=registry_path)


# --- shared ordering-test setup for items 10 and 11 ---

def _patch_full_pipeline_stages(monkeypatch, order, tmp_path, *, prospective_result=None):
    monkeypatch.setattr(cpc, "acquire_and_materialize", lambda *a, **k: order.append("acquire") or {
        "snapshot": {}, "resolved_completed_session": "2026-08-26", "coverage": {}, "artifact_root": tmp_path,
    })
    monkeypatch.setattr(cpc, "build_enrichment_components", lambda *a, **k: order.append("enrich") or {})
    monkeypatch.setattr(cpc, "register_session_inputs", lambda *a, **k: order.append("register") or {})
    monkeypatch.setattr(cpc, "validate_and_freeze_completed_session", lambda *a, **k: order.append("freeze") or {})
    monkeypatch.setattr(cpc, "_git_head", lambda p: "deadbeef")

    def fake_run_daily_producer(*a, **k):
        order.append("daily_producer")
        return {
            "status": "COMPLETED", "session": "2026-08-26", "run_identity": "daily_producer_run:fake",
            "run_dir": tmp_path, "operation": {"opportunity": None, "manifest": {}}, "manifest": {},
        }

    monkeypatch.setattr(cpc, "run_daily_producer", fake_run_daily_producer)
    monkeypatch.setattr(cpc, "materialize_canonical_runtime_release", lambda *a, **k: order.append("runtime_release") or {})
    monkeypatch.setattr(cpc, "build_decision_packet", lambda *a, **k: order.append("packet") or None)
    monkeypatch.setattr(cpc, "run_prospective_collection", lambda *a, **k: order.append("prospective") or (
        prospective_result if prospective_result is not None else {"status": "COLLECTED"}
    ))
    monkeypatch.setattr(cpc, "build_tiered_bundle", lambda *a, **k: order.append("bundle") or {
        "session_handoff_bundle": {}, "bundle_dir": tmp_path,
    })


# --- 10. Canonical Daily Producer runs only after registration ---

def test_daily_producer_runs_only_after_registration(tmp_path, monkeypatch):
    order = []
    _patch_full_pipeline_stages(monkeypatch, order, tmp_path)
    cpc.run_canonical_post_close(tmp_path, tmp_path / "runtime", "2026-08-26")
    assert order.index("acquire") < order.index("register")
    assert order.index("register") < order.index("daily_producer")
    assert order.index("freeze") < order.index("daily_producer")


# --- 11. prospective collection occurs after Daily Producer and does not change its authority ---

def test_prospective_collection_after_producer_and_does_not_revise_authority(tmp_path, monkeypatch):
    order = []
    _patch_full_pipeline_stages(monkeypatch, order, tmp_path, prospective_result={"status": "UNAVAILABLE", "reason": "boom"})
    result = cpc.run_canonical_post_close(tmp_path, tmp_path / "runtime", "2026-08-26")
    assert order.index("daily_producer") < order.index("prospective")
    assert result["producer_result"]["status"] == "COMPLETED"  # unaffected by prospective collection's own failure
    assert result["prospective"]["status"] == "UNAVAILABLE"


# --- 12. rerun with identical session evidence is idempotent ---

def test_registration_and_freeze_idempotent_on_rerun(tmp_path):
    session = "2026-08-25"
    registry_path = _registry_copy_at(tmp_path)
    first = cpc.register_session_inputs(ROOT, session, registry_path=registry_path)
    assert first["status"] == "ALREADY_FROZEN_IDENTICAL"
    second = cpc.register_session_inputs(ROOT, session, registry_path=registry_path)
    assert second["status"] == "ALREADY_FROZEN_IDENTICAL"
    freeze1 = cpc.validate_and_freeze_completed_session(ROOT, session, registry_path=registry_path)
    assert freeze1["status"] == "ALREADY_COMPLETED"
    freeze2 = cpc.validate_and_freeze_completed_session(ROOT, session, registry_path=registry_path)
    assert freeze2["status"] == "ALREADY_COMPLETED"


# --- 13. no Dashboard publication occurs ---

def test_module_never_invokes_dashboard_publication():
    # The module documents (in a plain data string) that release_orchestrator.py remains the
    # publication authority; only an actual import or subprocess/CLI invocation matters here.
    source = (ROOT / "canonical_post_close_pipeline.py").read_text(encoding="utf-8")
    for forbidden in ("import publish_dashboard", "import release_orchestrator", "import operate_stocklookup"):
        assert forbidden not in source
    for forbidden_arg in ('"publish_dashboard.py"', "'publish_dashboard.py'",
                           '"release_orchestrator.py"', "'release_orchestrator.py'",
                           '"operate_stocklookup.py"', "'operate_stocklookup.py'",
                           "--live-publish"):
        assert forbidden_arg not in source


# --- 14. final terminal handoff includes exact artifact identities/paths ---

def test_terminal_handoff_includes_exact_identities_and_paths(capsys, tmp_path):
    result = {
        "session": "2026-08-25",
        "producer_result": {"status": "COMPLETED"},
        "tiers": {
            "session_handoff_bundle": {
                "market_session_proof": {"resolved_completed_session": "2026-08-25"},
                "market_coverage": {"technical": 888},
                "breadth": {"advancing": 1, "declining": 2, "unchanged": 3},
                "tactical_counts": {"BREAKOUT_READY": 14},
                "high_priority_review_count": 91,
                "daily_producer": {
                    "operation_identity": "daily_research_session_operation:377cdcc6",
                    "run_identity": "daily_producer_run:abc123", "status": "COMPLETED",
                },
                "current_research_packet_identity": "current_research_decision_packet:xyz",
                "prospective_cohort_snapshot_identity": "prospective_research_cohort_snapshot:qrs",
                "blocked_dimensions": ["STRICT_VALUATION"],
                "warnings": ["w1"],
            },
            "full_universe_bundle_index": {"manifest_path": "operations-review/x/manifest.json"},
            "bundle_dir": tmp_path,
            "dashboard_release_set_index": {"ready_for_governed_publication": True},
        },
    }
    cpc.print_terminal_handoff(result)
    out = capsys.readouterr().out
    assert "daily_research_session_operation:377cdcc6" in out
    assert "daily_producer_run:abc123" in out
    assert "current_research_decision_packet:xyz" in out
    assert "prospective_research_cohort_snapshot:qrs" in out
    assert "operations-review/x/manifest.json" in out
    assert "READY_FOR_GOVERNED_PUBLICATION: YES" in out


# --- 15. no future session is manufactured ---

def test_resolved_completed_session_never_returns_a_future_date():
    from mva_exact_session_snapshot import resolved_completed_session
    now = datetime(2026, 8, 26, 16, 0, tzinfo=VN_TZ)
    resolved = resolved_completed_session(now)
    assert resolved <= "2026-08-26"
    assert resolved != "2026-08-27"


def test_acquired_session_mismatch_never_silently_substituted(tmp_path, monkeypatch):
    requested = "2026-08-27"

    def fake_materialize(root, sess, runtime_root, workers=12, now=None, execution_root=None):
        raise ValueError("P3F9B_ACQUIRED_SESSION_MISMATCH:requested=2026-08-27:resolved=2026-08-26")

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    with pytest.raises(cpc.CanonicalPostCloseError, match="never silently substituting"):
        cpc.acquire_and_materialize(tmp_path, requested, tmp_path / "runtime")


# =====================================================================================
# Pre-cutoff artifact reuse fix: session identity alone is not post-close eligibility.
# =====================================================================================

# --- 1. same-day canonical run before 18:00 fails closed ---

def test_same_day_run_before_cutoff_fails_closed():
    now = datetime(2026, 8, 26, 17, 59, tzinfo=VN_TZ)
    with pytest.raises(cpc.CanonicalPostCloseError, match="COMPLETED_SESSION_EVIDENCE_NOT_YET_ELIGIBLE"):
        cpc.assert_same_day_post_close_eligible("2026-08-26", now=now)


def test_same_day_run_at_or_after_cutoff_is_allowed():
    now = datetime(2026, 8, 26, 18, 0, tzinfo=VN_TZ)
    cpc.assert_same_day_post_close_eligible("2026-08-26", now=now)  # does not raise


def test_past_session_is_never_gated_by_same_day_cutoff():
    # A prior day's session is governed by its own retained acquisition evidence, not today's clock.
    now = datetime(2026, 8, 26, 9, 0, tzinfo=VN_TZ)
    cpc.assert_same_day_post_close_eligible("2026-08-25", now=now)  # does not raise


# --- 2. credentials/API availability does not bypass the gate ---

def test_gate_is_a_pure_function_of_session_and_clock_not_credentials(monkeypatch):
    # Simulate credentials being fully configured/reachable; the gate must still fire, because it
    # never inspects credential or API state at all -- only session identity and the injected clock.
    monkeypatch.setattr("dnse_secrets_env.ensure_credentials_loaded", lambda: {"configured": True})
    monkeypatch.setattr("dnse_access.credentials_for_request", lambda: ("fake-key", "fake-secret"))
    now = datetime(2026, 8, 26, 12, 0, tzinfo=VN_TZ)
    with pytest.raises(cpc.CanonicalPostCloseError, match="COMPLETED_SESSION_EVIDENCE_NOT_YET_ELIGIBLE"):
        cpc.assert_same_day_post_close_eligible("2026-08-26", now=now)


# --- 3, 4, 5. existing pre-cutoff artifact is not reused; stays byte-preserved; fresh eligible
#              artifact coexists alongside it without overwriting ---

def test_pre_cutoff_artifact_not_reused_stays_preserved_and_fresh_attempt_coexists(tmp_path, monkeypatch):
    session = "2026-08-26"
    default_paths = level2.session_artifact_paths(tmp_path, session)
    pre_cutoff = _write_snapshot(default_paths, session, requested_at=f"{session}T16:07:09+07:00", exact=889, total=1683)
    original_bytes = default_paths["exact_session_snapshot"].read_bytes()

    now = datetime(2026, 8, 26, 19, 0, tzinfo=VN_TZ)  # past the cutoff

    def fake_materialize(root, sess, runtime_root, workers=12, now=None, execution_root=None):
        fresh_paths = level2.session_artifact_paths(root, sess)
        _write_snapshot(fresh_paths, session, requested_at=f"{session}T19:05:00+07:00", exact=1200, total=1683)

    def fake_maybe_build_triage(root, s, execution_root=None):
        _write_triage(level2.session_artifact_paths(root, s), s)
        return {"built": True}

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", fake_maybe_build_triage)

    result = cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime", now=now)

    assert result["artifact_root"] != tmp_path  # redirected to a fresh-attempt directory
    assert result["eligibility"]["redirected"] is True
    assert result["eligibility"]["pre_cutoff_artifact_classification"] == "PRE_CUTOFF_RETAINED_NOT_POST_CLOSE_ELIGIBLE"
    # pre-cutoff artifact byte-preserved, never rewritten/relabeled
    assert default_paths["exact_session_snapshot"].read_bytes() == original_bytes
    assert json.loads(original_bytes)["exact_session_observed_count"] == 889
    # the fresh, now-eligible artifact coexists at a distinct path with its own (different) content
    fresh_snapshot_path = level2.session_artifact_paths(result["artifact_root"], session)["exact_session_snapshot"]
    assert fresh_snapshot_path != default_paths["exact_session_snapshot"]
    assert fresh_snapshot_path.is_file()
    assert result["snapshot"]["exact_session_observed_count"] == 1200
    assert result["snapshot"] != pre_cutoff


def test_redirected_attempt_propagates_artifact_and_execution_roots(tmp_path, monkeypatch):
    session = "2026-08-26"
    default_paths = level2.session_artifact_paths(tmp_path, session)
    _write_snapshot(default_paths, session, requested_at=f"{session}T16:07:09+07:00", exact=889, total=1683)
    calls = {}
    now = datetime(2026, 8, 26, 19, 0, tzinfo=VN_TZ)

    def fake_materialize(artifact_root, sess, runtime_root, workers=12, now=None, execution_root=None):
        calls["materialize"] = (artifact_root, execution_root)
        _write_snapshot(
            level2.session_artifact_paths(artifact_root, sess),
            sess,
            requested_at=f"{session}T19:05:00+07:00", exact=1200, total=1683,
        )

    def fake_triage(artifact_root, sess, execution_root=None):
        calls["triage"] = (artifact_root, execution_root)
        _write_triage(level2.session_artifact_paths(artifact_root, sess), sess)
        return {"built": True}

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", fake_triage)

    result = cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime", now=now)

    assert result["artifact_root"] != tmp_path
    assert calls["materialize"] == (result["artifact_root"], tmp_path)
    assert calls["triage"] == (result["artifact_root"], tmp_path)


# --- 6. downstream uses the selected eligible artifact identity/path, not a rediscovered static one ---

def test_registration_reads_from_the_redirected_artifact_root_not_the_default_path(tmp_path):
    session = "2026-08-26"
    attempt_root = tmp_path / "operations-review" / "canonical-post-close-v1" / session / "post-close-attempt-190500"
    fresh_paths = level2.session_artifact_paths(attempt_root, session)
    for reg_key, l2_key in cpc.REGISTRY_KEY_TO_LEVEL2_KEY.items():
        artifact = {"artifact_identity": f"{l2_key}:fresh-{reg_key}", "session": session, "source_market_session": session, "valuation_session": session, "research_session": session}
        path = (level2.session_artifact_paths(tmp_path, session)[l2_key]
                if l2_key in cpc.RETAINED_LEVEL2_INPUT_KEYS else fresh_paths[l2_key])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact), encoding="utf-8")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"schema_version": "1.0.0", "contract_version": "daily_research_session_input_registry/v1", "completed_sessions": {}, "sessions": {}}), encoding="utf-8")

    result = cpc.register_session_inputs(tmp_path, session, registry_path=registry_path, artifact_root=attempt_root)

    assert result["status"] == "REGISTERED"
    for reg_key in cpc.REQUIRED_REGISTRY_KEYS:
        recorded_path = result["selection"][reg_key]["path"]
        if cpc.REGISTRY_KEY_TO_LEVEL2_KEY[reg_key] in cpc.RETAINED_LEVEL2_INPUT_KEYS:
            assert "post-close-attempt-190500" not in recorded_path
        else:
            assert "post-close-attempt-190500" in recorded_path
        assert (tmp_path / recorded_path).is_file()  # resolves correctly relative to the real root


# --- 7. pre-cutoff partial liquidity batches are not silently reused against a new upstream identity ---

def test_fresh_attempt_is_isolated_from_pre_cutoff_partial_liquidity_batches(tmp_path):
    session = "2026-08-26"
    default_paths = level2.session_artifact_paths(tmp_path, session)
    _write_snapshot(default_paths, session, requested_at=f"{session}T16:07:09+07:00", exact=889, total=1683)
    # simulate the genuinely partial liquidity-batch state left by the interrupted pre-cutoff run
    partial_batch = default_paths["liquidity_research"].parent / "batches" / "batch-000.json"
    partial_batch.parent.mkdir(parents=True, exist_ok=True)
    partial_batch.write_text("{}", encoding="utf-8")

    now = datetime(2026, 8, 26, 19, 0, tzinfo=VN_TZ)
    artifact_root, info = cpc.resolve_acquisition_root(tmp_path, session, now=now)

    assert info["redirected"] is True
    fresh_liquidity_dir = level2.session_artifact_paths(artifact_root, session)["liquidity_research"].parent
    default_liquidity_dir = default_paths["liquidity_research"].parent
    assert fresh_liquidity_dir != default_liquidity_dir
    # the fresh namespace has never seen the old partial batches -- nothing to silently resume from
    assert not (fresh_liquidity_dir / "batches").exists()
    # the old partial batch itself is untouched
    assert partial_batch.is_file()


# --- 8. valid terminal post-cutoff rerun is idempotent (no unnecessary network acquisition) ---

def test_eligible_post_cutoff_artifact_rerun_is_idempotent_no_redirect(tmp_path):
    session = "2026-08-25"  # a prior day -- same-day cutoff does not apply
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_snapshot(paths, session, requested_at=f"{session}T19:05:00+07:00", exact=900, total=1683)
    now = datetime(2026, 8, 26, 10, 0, tzinfo=VN_TZ)

    root1, info1 = cpc.resolve_acquisition_root(tmp_path, session, now=now)
    root2, info2 = cpc.resolve_acquisition_root(tmp_path, session, now=now)

    assert root1 == root2 == tmp_path
    assert info1["redirected"] is False and info1.get("reused_existing_eligible_artifact") is True
    assert info2["redirected"] is False and info2.get("reused_existing_eligible_artifact") is True


# --- 9. requested session mismatch still fails: see test_acquired_session_mismatch_never_silently_substituted above ---
# --- 10. legacy VCI/KBS unreachable from --canonical-post-close: see test_module_never_references_legacy_vci_kbs_route
#         and test_canonical_post_close_flag_never_invokes_legacy_step_runner above ---
# --- 11a. no Dashboard mutation: see test_module_never_invokes_dashboard_publication above ---

# --- 11b. no Consumer (ai-core-private) mutation ---

def test_module_never_mutates_consumer_repository():
    # ai-core-private is referenced exactly once, for a read-only `git rev-parse HEAD` provenance
    # stamp (_git_head) -- never opened, written to, or otherwise mutated.
    source = (ROOT / "canonical_post_close_pipeline.py").read_text(encoding="utf-8")
    assert source.count('"ai-core-private"') == 1
    assert 'root.parent / "ai-core-private"' in source


# --- 12. no authority promotion: bundle tiers pass authority fields through verbatim ---

def test_tiered_bundle_never_invents_authority_only_passes_it_through(tmp_path):
    sentinel_authority = {"is_actionable": False, "no_recommendation": True, "sentinel_marker": "NOT_INVENTED_HERE"}
    session = "2026-08-25"
    paths = level2.session_artifact_paths(tmp_path, session)
    for key in ("session_triage", "tactical_classifier", "descriptive_research", "opportunity_prioritization", "decision_packet"):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        paths[key].write_text(json.dumps({"records": {}}), encoding="utf-8")
    run_dir = tmp_path / "run"
    (run_dir / "dashboard").mkdir(parents=True, exist_ok=True)
    (run_dir / "ai_research_full_universe.ndjson").write_text("", encoding="utf-8")
    (run_dir / "ai_research_bundle_manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "dashboard" / "current_decision_cockpit_projection.json").write_text("{}", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
    producer_result = {
        "run_identity": "daily_producer_run:fake", "run_dir": run_dir, "status": "COMPLETED",
        "manifest": {
            "upstream_artifact_identities": {}, "blocked_dimensions": [], "warnings": [],
            "authority_boundary": sentinel_authority,
            "dashboard_projection": {"identity": "current_decision_cockpit_projection:fake"},
        },
        "operation": {"manifest": {"operation_identity": "daily_research_session_operation:fake"},
                      "product": {"market_brief": {"coverage": {}}, "high_priority_full_universe_review_set": {"count": 0}}},
    }
    acquisition = {"resolved_completed_session": session, "coverage": {}}

    tiers = cpc.build_tiered_bundle(
        tmp_path, session, acquisition=acquisition, producer_result=producer_result,
        decision_packet=None, prospective=None, enrichment={}, producer_head="deadbeef", consumer_head="deadbeef",
        artifact_root=tmp_path,
    )

    assert tiers["session_handoff_bundle"]["authority_boundary"] == sentinel_authority


# --- bonus regression coverage for the two pre-existing Level-2 acquisition bugs fixed alongside this milestone ---

def test_level2_p3f9b_acquisition_uses_real_cli_flags():
    source = (ROOT / "daily_session_level2_package.py").read_text(encoding="utf-8")
    block = re.search(r"run_p3f9b_market_wide_exact_session_scaleout\.py.*?\]\)", source, re.S).group(0)
    assert "--output-dir" in block
    assert "--out-dir" not in block
    assert '"--session", session' not in block


def test_level2_universe_resolution_uses_real_cli_flags():
    source = (ROOT / "daily_session_level2_package.py").read_text(encoding="utf-8")
    block = re.search(r"run_current_universe_status_and_session_coverage_resolution\.py.*?\]\)", source, re.S).group(0)
    assert "--p3f9b-snapshot" in block
    assert "--breadth-foundation-artifact" in block
    assert '"--snapshot"' not in block
