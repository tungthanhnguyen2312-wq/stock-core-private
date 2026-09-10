"""Focused no-provider regression coverage for Daily execution-environment qualification."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_post_close_pipeline as cpp
import daily_execution_environment as env
from daily_session_level2_package import session_artifact_paths
from field_temporal_contract import stable_id


SESSION = "2026-09-10"


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "authoritative-runtime"
    runtime.mkdir()
    (runtime / "vn_stock.db").write_bytes(b"fixture")
    return runtime


def _qualified_release(_: Path) -> dict[str, object]:
    return {"qualified": True, "head": "c106", "origin_main": "c106", "dirty": False, "reason_code": "PASS"}


def _available_inputs(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
    return []


def _snapshot(root: Path, records: int = 3) -> Path:
    path = session_artifact_paths(root, SESSION)["exact_session_snapshot"]
    path.parent.mkdir(parents=True)
    payload: dict[str, object] = {
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "resolved_completed_session": SESSION,
        "records": {f"T{i}": {} for i in range(records)},
        "candidate_count": records,
        "exact_session_observed_count": records,
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
    }
    sha = stable_id(payload)
    payload["snapshot_sha256"] = sha
    payload["snapshot_identity"] = "p3f9_exact_session_snapshot:" + sha
    path.write_text(json.dumps(payload), encoding="utf-8")
    companion = session_artifact_paths(root, SESSION)["multi_source_market_evidence"]
    companion.write_text(json.dumps({
        "contract_version": "multi_source_exact_session_market_evidence/v1",
        "target_session": SESSION,
        "dnse_quality_sentinel": {"health": {"state": "DNSE_EXACT_AND_CORROBORATED"}},
    }), encoding="utf-8")
    return path


def test_stale_or_dirty_release_is_refused_before_any_resume_planning(tmp_path, monkeypatch):
    monkeypatch.setattr(env, "producer_release_qualification", lambda _: {
        "qualified": False, "head": "bf11", "origin_main": "c106", "dirty": True,
        "reason_code": "RELEASE_CHECKOUT_DIRTY",
    })
    monkeypatch.setattr(env, "required_retained_inputs", _available_inputs)
    result = env.preflight_canonical_daily(tmp_path, session=SESSION, runtime_root=_runtime(tmp_path))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "FAILED_PREFLIGHT_PRODUCER:RELEASE_CHECKOUT_NOT_QUALIFIED"


def test_qualified_release_and_explicit_runtime_win_over_worktree_sibling(tmp_path, monkeypatch):
    producer = tmp_path / "worktrees" / "release"
    producer.mkdir(parents=True)
    wrong = producer.parent / "dashboard-runtime"
    wrong.mkdir()
    selected = _runtime(tmp_path)
    monkeypatch.setattr(env, "producer_release_qualification", _qualified_release)
    monkeypatch.setattr(env, "required_retained_inputs", _available_inputs)
    result = env.preflight_canonical_daily(producer, session=SESSION, runtime_root=selected)
    assert result["status"] == "PASS"
    assert result["roots"]["runtime_root"] == str(selected.resolve())
    assert result["producer_release"]["qualified"] is True


def test_runtime_database_capability_is_required_before_acquisition(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime-without-db"
    runtime.mkdir()
    monkeypatch.setattr(env, "producer_release_qualification", _qualified_release)
    monkeypatch.setattr(env, "required_retained_inputs", _available_inputs)
    result = env.preflight_canonical_daily(tmp_path, session=SESSION, runtime_root=runtime)
    assert result["failure_code"] == "FAILED_PREFLIGHT_RUNTIME:CAPABILITY_NOT_QUALIFIED"
    assert result["failure_detail"] == "RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING"


def test_missing_static_contract_is_explicitly_classified_as_governed_input_block(tmp_path, monkeypatch):
    monkeypatch.setattr(env, "producer_release_qualification", _qualified_release)
    monkeypatch.setattr(env, "required_retained_inputs", lambda *_a, **_k: [
        {"contract": "governed_previous_session_bundle", "status": "UNAVAILABLE"},
    ])
    result = env.preflight_canonical_daily(tmp_path, session=SESSION, runtime_root=_runtime(tmp_path))
    assert result["failure_code"] == "FAILED_PREFLIGHT_RETAINED_EVIDENCE:STATIC_DEPENDENCY_UNAVAILABLE"
    assert {
        row["classification"]
        for row in result["resume_plan"]["components"]
        if row["component"] == "RETAINED_INPUT:governed_previous_session_bundle"
    } == {"BLOCKED_MISSING_GOVERNED_INPUT"}


def test_missing_static_dependency_blocks_acquire_before_snapshotter(tmp_path, monkeypatch):
    missing = [{"contract": "research_universe_qualification", "status": "UNAVAILABLE"}]
    monkeypatch.setattr(env, "missing_retained_inputs", lambda *_a, **_k: missing)
    import daily_session_level2_package as level2
    monkeypatch.setattr(level2, "ensure_exact_session_snapshot", lambda *_a, **_k: pytest.fail("provider boundary reached"))
    with pytest.raises(cpp.CanonicalPostCloseError, match="STATIC_DEPENDENCY_UNAVAILABLE:research_universe_qualification"):
        cpp.acquire_and_materialize(
            tmp_path, SESSION, _runtime(tmp_path), retained_evidence_root=tmp_path,
        )


def test_separate_roots_keep_registry_in_producer_and_static_inputs_in_retained_checkout(tmp_path):
    producer = tmp_path / "producer"
    retained = tmp_path / "retained"
    output = tmp_path / "output"
    producer.mkdir()
    retained.mkdir()
    output.mkdir()
    roots = env.resolve_roots(
        producer, retained_evidence_root=retained, output_root=output,
    )
    assert roots.producer_code_root == producer.resolve()
    assert roots.retained_evidence_root == retained.resolve()
    assert roots.output_root == output.resolve()
    items = env.required_retained_inputs(retained, SESSION, producer_registry_root=producer)
    assert any(row["contract"] == "research_universe_qualification" for row in items)
    assert any(row["status"] == "UNAVAILABLE" for row in items)
    registry = next(row for row in items if row["contract"] == "producer_session_input_registry")
    assert registry["path"] == str(producer / "config" / "daily_research_session_input_registry.json")
    assert all(
        row["contract"] == "producer_session_input_registry"
        or row["path"] is None
        or str(row["path"]).startswith(str(retained))
        for row in items
    )


def test_valid_snapshot_is_reused_and_liquidity_is_planned_separately(tmp_path):
    _snapshot(tmp_path, records=3)
    plan = env.build_resume_plan(tmp_path, SESSION)
    by_component = {row["component"]: row for row in plan["components"]}
    assert by_component["EXACT_SESSION_SNAPSHOT"]["classification"] == "REUSABLE_QUALIFIED"
    assert by_component["LIQUIDITY_RESEARCH"]["classification"] == "REQUIRES_PROVIDER_ACQUISITION"
    assert by_component["LIQUIDITY_RESEARCH"]["expected_provider_calls"] == 6
    assert "EXACT_SESSION_SNAPSHOT" not in plan["provider_required_components"]


def test_no_new_provider_mode_refuses_before_snapshot_boundary(tmp_path, monkeypatch):
    _snapshot(tmp_path, records=3)
    monkeypatch.setattr(env, "missing_retained_inputs", lambda *_a, **_k: [])
    import daily_session_level2_package as level2
    monkeypatch.setattr(level2, "ensure_exact_session_snapshot", lambda *_a, **_k: pytest.fail("provider boundary reached"))
    with pytest.raises(cpp.CanonicalPostCloseError, match="NO_NEW_PROVIDER_ACQUISITION_COMPONENTS_REQUIRED:LIQUIDITY_RESEARCH,TECHNICAL_RECOVERY"):
        cpp.acquire_and_materialize(
            tmp_path, SESSION, _runtime(tmp_path), retained_evidence_root=tmp_path,
            no_new_provider_acquisition=True,
        )


def test_legacy_roots_remain_identical_without_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv(env.RUNTIME_ROOT_ENV, raising=False)
    monkeypatch.delenv(env.RETAINED_EVIDENCE_ROOT_ENV, raising=False)
    monkeypatch.delenv(env.OUTPUT_ROOT_ENV, raising=False)
    producer = tmp_path / "producer"
    producer.mkdir()
    (tmp_path / "dashboard-runtime").mkdir()
    roots = env.resolve_roots(producer)
    assert roots.producer_code_root == roots.retained_evidence_root == roots.output_root
    assert roots.runtime_root == (tmp_path / "dashboard-runtime").resolve()


def test_daily_analysis_preflight_exits_before_canonical_execution(tmp_path, monkeypatch, capsys):
    import daily_analysis_pipeline as dap
    runtime = _runtime(tmp_path)
    result = {
        "status": "PASS", "session": SESSION,
        "roots": {"runtime_root": str(runtime), "retained_evidence_root": str(tmp_path), "output_root": str(tmp_path)},
        "producer_release": {"qualified": True, "head": "c106", "origin_main": "c106"},
        "resume_plan": {"provider_required_components": []},
    }
    monkeypatch.setattr(env, "preflight_canonical_daily", lambda *_a, **_k: result)
    monkeypatch.setattr(env, "format_preflight", lambda _: "DRY_PREFLIGHT")
    monkeypatch.setattr(dap, "run", lambda *_a, **_k: pytest.fail("canonical execution reached"))
    assert dap.main(["--canonical-post-close", "--preflight", "--session", SESSION, "--runtime-root", str(runtime)]) == 0
    assert "DRY_PREFLIGHT" in capsys.readouterr().out


def test_owner_daily_cli_preserves_default_command_and_exposes_guard_flags(tmp_path, monkeypatch, capsys):
    import stocklookup
    runtime = _runtime(tmp_path)
    calls: list[dict[str, object]] = []
    result = {
        "status": "PASS", "session": SESSION,
        "roots": {"runtime_root": str(runtime), "retained_evidence_root": str(tmp_path), "output_root": str(tmp_path)},
        "producer_release": {"qualified": True, "head": "c106", "origin_main": "c106"},
        "resume_plan": {"provider_required_components": []},
    }

    def _preflight(*_args, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(env, "preflight_canonical_daily", _preflight)
    monkeypatch.setattr(env, "format_preflight", lambda _: "OWNER_DRY_PREFLIGHT")
    assert stocklookup.main([
        "daily", "--session", SESSION, "--runtime-root", str(runtime),
        "--retained-evidence-root", str(tmp_path), "--output-root", str(tmp_path),
        "--no-new-provider-acquisition", "--preflight",
    ]) == 0
    assert calls and calls[0]["no_new_provider_acquisition"] is True
    assert "OWNER_DRY_PREFLIGHT" in capsys.readouterr().out
