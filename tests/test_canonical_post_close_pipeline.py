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

    def fake_materialize(root, sess, runtime_root, workers=12, now=None):
        snapshot = {
            "resolved_completed_session": session,
            "acquisition_cohort": {"total_candidates": 1683},
            "exact_session_dispositions": {"exact_session_retained_count": 10},
        }
        paths["exact_session_snapshot"].parent.mkdir(parents=True, exist_ok=True)
        paths["exact_session_snapshot"].write_text(json.dumps(snapshot), encoding="utf-8")

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    with pytest.raises(cpc.CanonicalPostCloseError, match="PARTIAL_OR_INTRADAY_SESSION_EVIDENCE"):
        cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime")


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
    snapshot = {
        "resolved_completed_session": session,
        "acquisition_cohort": {"total_candidates": 1000},
        "exact_session_dispositions": {"exact_session_retained_count": 500},
        "provider": "DNSE",
        "artifact_identity": "p3f9_exact_session_mva_snapshot:deadbeef",
    }

    def fake_materialize(root, sess, runtime_root, workers=12, now=None):
        paths["exact_session_snapshot"].parent.mkdir(parents=True, exist_ok=True)
        paths["exact_session_snapshot"].write_text(json.dumps(snapshot), encoding="utf-8")

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", lambda root, s: {"built": False})
    monkeypatch.setattr(cpc.level2, "session_triage_status", lambda root, s, registry: {"status": cpc.level2.EXACT_SESSION_CLEAN})
    monkeypatch.setattr(cpc, "load_registry", lambda root: {})

    result = cpc.acquire_and_materialize(tmp_path, session, tmp_path / "runtime")
    assert result["snapshot"]["artifact_identity"] == "p3f9_exact_session_mva_snapshot:deadbeef"
    assert result["snapshot"]["provider"] == "DNSE"
    assert result["resolved_completed_session"] == session


# --- 5. runtime materialization targets only canonical runtime ---

def test_acquisition_never_writes_into_runtime_root(tmp_path, monkeypatch):
    session = "2026-08-26"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    paths = level2.session_artifact_paths(tmp_path, session)

    def fake_materialize(root, sess, runtime_root_arg, workers=12, now=None):
        assert runtime_root_arg == runtime_root
        paths["exact_session_snapshot"].parent.mkdir(parents=True, exist_ok=True)
        paths["exact_session_snapshot"].write_text(json.dumps({
            "resolved_completed_session": session,
            "acquisition_cohort": {"total_candidates": 100},
            "exact_session_dispositions": {"exact_session_retained_count": 50},
        }), encoding="utf-8")

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    monkeypatch.setattr(cpc.level2, "maybe_build_triage_dependent", lambda root, s: {"built": False})
    monkeypatch.setattr(cpc.level2, "session_triage_status", lambda root, s, registry: {"status": cpc.level2.EXACT_SESSION_CLEAN})
    monkeypatch.setattr(cpc, "load_registry", lambda root: {})

    cpc.acquire_and_materialize(tmp_path, session, runtime_root)
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
        "snapshot": {}, "resolved_completed_session": "2026-08-26", "coverage": {},
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

    def fake_materialize(root, sess, runtime_root, workers=12, now=None):
        raise ValueError("P3F9B_ACQUIRED_SESSION_MISMATCH:requested=2026-08-27:resolved=2026-08-26")

    monkeypatch.setattr(cpc.level2, "materialize_independent_components", fake_materialize)
    with pytest.raises(cpc.CanonicalPostCloseError, match="never silently substituting"):
        cpc.acquire_and_materialize(tmp_path, requested, tmp_path / "runtime")


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
