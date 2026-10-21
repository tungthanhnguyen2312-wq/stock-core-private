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
    vci = next(row for row in items if row["contract"] == "vci_exchange_reference_snapshot")
    assert vci["status"] == "UNAVAILABLE" and vci["reason_code"] == "MISSING"
    assert vci["path"].startswith(str(retained))
    assert any(row["status"] == "UNAVAILABLE" for row in items)
    registry = next(row for row in items if row["contract"] == "producer_session_input_registry")
    assert registry["path"] == str(producer / "config" / "daily_research_session_input_registry.json")
    assert all(
        row["contract"] == "producer_session_input_registry"
        or row["contract"] == "daily_static_inputs_manifest"
        or row["contract"].startswith("static_input:producer:")
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


def test_vci_snapshot_only_in_producer_checkout_is_not_accepted_for_split_roots(tmp_path):
    # 2026-10-19 incident shape: the static file sat beside the old single-root checkout and never
    # reached the retained-evidence root. Preflight must name it before acquisition starts.
    producer = tmp_path / "producer"
    retained = tmp_path / "retained"
    rel = Path("operations-review/vci-exchange-reference-snapshot-v1-20260823/vci_exchange_reference_snapshot_artifact.json")
    (producer / rel).parent.mkdir(parents=True)
    (producer / rel).write_text(json.dumps({
        "contract_version": "vci_exchange_reference_snapshot/v1",
        "snapshot_identity": "vci_exchange_reference_snapshot:x",
    }), encoding="utf-8")
    retained.mkdir()

    def vci_row():
        items = env.required_retained_inputs(retained, SESSION, producer_registry_root=producer)
        return next(row for row in items if row["contract"] == "vci_exchange_reference_snapshot")

    assert vci_row()["status"] == "UNAVAILABLE"
    (retained / rel).parent.mkdir(parents=True)
    (retained / rel).write_bytes((producer / rel).read_bytes())
    assert vci_row()["status"] == "AVAILABLE"


# --- daily_static_inputs/v1 (2026-10-19 split-root incident) ---------------------------------

def _static_manifest(producer: Path, entries: list[dict]) -> None:
    (producer / "config").mkdir(parents=True, exist_ok=True)
    (producer / env.STATIC_INPUTS_MANIFEST).write_text(json.dumps({
        "contract_version": "daily_static_inputs/v1", "inputs": entries,
    }), encoding="utf-8")


def test_static_inputs_resolve_against_their_role_root(tmp_path):
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    _static_manifest(producer, [
        {"role": "producer", "path": "operations-review/a/x.json"},
        {"role": "retained", "path": "operations-review/b/y.json"},
    ])
    (producer / "operations-review/a").mkdir(parents=True)
    (producer / "operations-review/a/x.json").write_text("{}", encoding="utf-8")
    # The retained input exists only beside the checkout: wrong root, must be refused.
    (producer / "operations-review/b").mkdir(parents=True)
    (producer / "operations-review/b/y.json").write_text("{}", encoding="utf-8")
    rows = {r["contract"]: r for r in env.static_input_rows(producer, retained)}
    assert rows["static_input:producer:operations-review/a/x.json"]["status"] == "AVAILABLE"
    assert rows["static_input:retained:operations-review/b/y.json"]["reason_code"] == "MISSING"


def test_static_input_manifest_missing_is_a_refusal_row(tmp_path):
    rows = env.static_input_rows(tmp_path / "producer", tmp_path / "retained")
    assert rows == [{
        "contract": "daily_static_inputs_manifest",
        "path": str(tmp_path / "producer" / env.STATIC_INPUTS_MANIFEST),
        "expected_contract_version": "daily_static_inputs/v1",
        "status": "UNAVAILABLE", "reason_code": "MANIFEST_MISSING_OR_INVALID",
    }]


def test_static_input_entries_cannot_escape_their_root(tmp_path):
    producer = tmp_path / "producer"
    _static_manifest(producer, [
        {"role": "producer", "path": "../outside.json"},
        {"role": "producer", "path": str(tmp_path / "abs.json")},
        {"role": "unknown", "path": "x.json"},
    ])
    rows = env.static_input_rows(producer, tmp_path / "retained")
    assert [r["reason_code"] for r in rows] == ["MANIFEST_ENTRY_INVALID"] * 3


def test_static_inputs_join_the_pre_acquisition_closure(tmp_path):
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    _static_manifest(producer, [{"role": "producer", "path": "registry_snapshots/metadata/s.jsonl"}])
    retained.mkdir()
    items = env.required_retained_inputs(retained, SESSION, producer_registry_root=producer)
    row = next(r for r in items if r["contract"].startswith("static_input:"))
    assert row["status"] == "UNAVAILABLE" and row["reason_code"] == "MISSING"


def test_repository_static_manifest_is_well_formed():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / env.STATIC_INPUTS_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["contract_version"] == "daily_static_inputs/v1"
    seen = set()
    for entry in manifest["inputs"]:
        assert entry["role"] in {"producer", "retained"}
        rel = Path(entry["path"])
        assert not rel.is_absolute() and ".." not in rel.parts
        assert (entry["role"], entry["path"]) not in seen
        seen.add((entry["role"], entry["path"]))
