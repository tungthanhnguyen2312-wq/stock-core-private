from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import integrated_decision_prospective_feedback as bridge
import prospective_decision_outcome_feedback as feedback
from tools.run_prospective_decision_outcome_feedback import run


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _record(session: str, *, posture: str = "WAIT_FOR_CONFIRMATION") -> dict:
    return {
        "ticker": "FPT", "as_of_session": session, "decision_identity": f"decision:FPT:{session}",
        "research_action_posture": posture, "fundamental_state": "IMPROVING",
        "valuation_context_summary": {"status": "AVAILABLE"}, "market_structure_state": "UPTREND",
        "momentum_context": {"status": "AVAILABLE"}, "participation": {"status": "AVAILABLE"},
        "market_sector_context": {"market_regime": "SUPPORTIVE", "sector_leadership": "LEADING"},
        "priority_posture_reconciliation": {"research_priority_tier": "PRIORITY_NOW"},
        "trigger": {"trigger_state": "APPROACHING", "trigger_level": 100.0},
        "invalidation": {"invalidation_level": 90.0},
        "evidence_axes": {
            "FUNDAMENTAL": {"state": "IMPROVING", "fitness": "AVAILABLE", "lineage": {"source_artifact_identity": "fund:a"}},
            "TACTICAL_STRUCTURE": {"state": "UPTREND", "fitness": "AVAILABLE", "lineage": {"source_artifact_identity": "tech:a"}},
        },
        "evidence_axis_coherence": {"state": "ALIGNED"},
    }


def _snapshot(session: str, close: float, *, transform: str = "normalize/v1") -> dict:
    return {
        "resolved_completed_session": session, "snapshot_identity": f"snapshot:{session}",
        "records": {"FPT": {"observations": [{
            "session": session, "close": close, "provider": "KBS", "dataset": "KBS_OHLC_1D",
            "price_basis": "CURRENT_DESCRIPTIVE", "transformation_identity": transform,
            "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
        }]}},
    }


def _fixture_root(tmp_path: Path, *, sessions: int = 6) -> tuple[Path, list[str]]:
    chain = [f"2026-01-{number:02d}" for number in range(1, sessions + 1)]
    for index, session in enumerate(chain):
        operation_identity = f"daily-operation:{session}"
        artifact_path = tmp_path / "operations-review" / "integrated-artifacts" / session / "integrated_investment_decision_product_artifact.json"
        artifact = {
            "contract_version": "integrated_investment_decision_product/v1", "session": session,
            "requested_at": session + "T15:00:00+07:00", "artifact_identity": f"integrated:{session}",
            "records": {"FPT": _record(session)},
        }
        _write(artifact_path, artifact)
        _write(tmp_path / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
            "market_session": session, "operation_identity": operation_identity,
            "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
        })
        _write(tmp_path / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
            "session": session, "daily_session_operation_identity": operation_identity,
            "integrated_investment_decision_product_identity": f"integrated:{session}",
            "deeper_bundles": {"integrated_investment_decision_product": str(artifact_path.relative_to(tmp_path)).replace("\\", "/")},
            "daily_producer": {"status": "COMPLETED"}, "market_session_proof": {"resolved_completed_session": session},
        })
        nodash = session.replace("-", "")
        _write(tmp_path / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json", _snapshot(session, 100.0 + index))
    # A retained-looking replay must be inventoried but never admitted.
    _write(tmp_path / "operations-review" / "sample-replay" / "integrated_investment_decision_product_artifact.json", {
        "contract_version": "integrated_investment_decision_product/v1", "session": chain[0],
        "requested_at": chain[0] + "T15:00:00+07:00", "artifact_identity": "integrated:replay",
        "records": {"FPT": _record(chain[0])},
    })
    return tmp_path, chain


def test_temporal_gate_excludes_replay_and_uses_only_identity_bound_daily_operations(tmp_path: Path):
    root, chain = _fixture_root(tmp_path)
    corpus = feedback.discover_prospective_corpus(root)
    assert corpus["classification_counts"][feedback.GENUINE] == len(chain)
    assert corpus["classification_counts"][feedback.REPLAY_ONLY] == 1
    assert all(item["temporal"]["status"] == feedback.GENUINE for item in corpus["genuine_artifacts"])


def test_horizons_close_excursions_policy_diagnostics_and_identity_are_deterministic(tmp_path: Path):
    root, chain = _fixture_root(tmp_path)
    original = json.loads(json.dumps(_record(chain[0])))
    first = feedback.build_feedback_artifact(root)
    second = feedback.build_feedback_artifact(root)
    assert first == second
    assert first["prospective_corpus"]["genuine_decision_count"] == len(chain)
    row = next(item for item in first["feedback_records"] if item["decision_session"] == chain[0])
    h1 = row["forward_outcomes"]["horizons"]["forward_close_return_1"]
    h5 = row["forward_outcomes"]["horizons"]["forward_close_return_5"]
    assert h1["status"] == bridge.MATURE
    assert h1["start_session"] == chain[0] and h1["end_session"] == chain[1]
    assert h1["start_price"] == 100.0 and h1["end_price"] == 101.0
    assert h1["series_fitness"] == "COMPATIBLE_RETAINED_CLOSE_SERIES"
    assert h5["return"] == pytest.approx(0.05)
    close5 = row["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"]
    assert close5["CLOSE_MFE"] == pytest.approx(0.05) and close5["CLOSE_MAE"] == pytest.approx(0.01)
    assert "MFE" not in row["forward_outcomes"]["close_path"]
    assert row["outcome_classification"]["label"] == "WAIT_MISSED_UPSIDE"
    assert first["false_negative_cases"] == []  # price rise alone is descriptive, not a policy failure
    assert row["trigger_invalidation_outcome"]["trigger"]["status"].startswith("T0_TRIGGER_EVENT_NOT_EVALUABLE")
    assert original == _record(chain[0])  # feedback did not mutate the decision source shape
    assert first["policy_diagnostic_candidates"][0]["policy_mutated"] is False


def test_incompatible_transformation_is_not_spliced_between_retained_sessions():
    chain = ["2026-01-01", "2026-01-02"]
    snapshots = {chain[0]: _snapshot(chain[0], 100.0), chain[1]: _snapshot(chain[1], 101.0, transform="other/v1")}
    result = bridge.evaluate_decision_forward_outcome(
        decision_record=_record(chain[0]), p3f9b_snapshot=None, governed_chain=chain, retained_session_snapshots=snapshots,
    )
    assert result["horizons"]["forward_close_return_1"]["status"] == bridge.PRICE_BASIS_INCOMPATIBLE
    assert result["horizons"]["forward_close_return_1"]["series_fitness"] == "INCOMPATIBLE_PRICE_SERIES"


def test_wait_avoided_drawdown_and_failed_breakout_are_descriptive_states():
    negative = {"horizons": {"forward_close_return_5": {"status": bridge.MATURE, "return": -0.04}}, "close_path_by_horizon": {"close_excursion_5": {"CLOSE_MAE": -0.04}}}
    assert feedback._outcome_label(_record("2026-01-01"), negative)["label"] == "WAIT_AVOIDED_DRAWDOWN"
    assert feedback._outcome_label(_record("2026-01-01", posture="INITIATE_ON_BREAKOUT"), negative)["label"] == "FALSE_BREAKOUT_OUTCOME"


def test_runner_writes_required_immutable_evidence_views(tmp_path: Path):
    root, _ = _fixture_root(tmp_path)
    evidence_dir = root / "evidence"
    result = run(root=root, evidence_dir=evidence_dir)
    assert result["artifact_identity"].startswith("prospective_decision_outcome_feedback:")
    for name in (
        "REPORT.md", "prospective_decision_feedback_artifact.json", "prospective_corpus_inventory.json",
        "temporal_qualification.json", "forward_outcome_coverage.json", "posture_outcome_summary.json",
        "coherence_outcome_summary.json", "evidence_axis_outcome_summary.json", "false_negative_cases.json",
        "failed_setup_cases.json", "trigger_invalidation_outcomes.json", "policy_diagnostic_candidates.json",
        "product_feedback_gap_matrix.json",
    ):
        assert (evidence_dir / name).is_file()


def _classification_fixture(tmp_path):
    root, chain = _fixture_root(tmp_path, sessions=2)
    path = root / "operations-review/integrated-artifacts" / chain[0] / "integrated_investment_decision_product_artifact.json"
    value = json.loads(path.read_text())
    value["requested_at"] = "legacy-unqualified-time"
    _write(path, value)
    return root, chain, path


def test_full_cold_warm_feedback_bytes_identity_and_parse_counts(tmp_path, monkeypatch):
    root, chain, path = _classification_fixture(tmp_path)
    full = feedback.build_feedback_artifact(root, use_summary_cache=False)
    cold_metrics, warm_metrics = {}, {}
    cold = feedback.build_feedback_artifact(root, cache_metrics=cold_metrics)
    original = feedback._load_json
    reads = []

    def observe(source):
        reads.append(source.resolve())
        return original(source)

    monkeypatch.setattr(feedback, "_load_json", observe)
    warm = feedback.build_feedback_artifact(root, cache_metrics=warm_metrics)
    assert feedback._canon(full) == feedback._canon(cold) == feedback._canon(warm)
    assert full["artifact_identity"] == warm["artifact_identity"]
    assert cold_metrics["full_iid_parses"] == 3
    assert warm_metrics["full_iid_parses"] == 1
    assert warm_metrics["summary_hits"] == 2
    assert path.resolve() not in reads
    genuine_path = path.parent.parent / chain[1] / path.name
    assert reads.count(genuine_path.resolve()) == 1


@pytest.mark.parametrize("damage", ["empty", "malformed", "missing", "size", "mtime", "same-stat-malformed"])
def test_current_source_damage_and_metadata_invalidate_summary(tmp_path, damage):
    root, _, path = _classification_fixture(tmp_path)
    feedback.discover_prospective_corpus(root)
    before = path.stat()
    if damage == "empty":
        path.write_bytes(b"")
    elif damage == "malformed":
        path.write_text("{broken")
    elif damage == "missing":
        path.unlink()
    elif damage == "size":
        path.write_bytes(path.read_bytes() + b" ")
    elif damage == "mtime":
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    else:
        path.write_bytes(b"!" + path.read_bytes()[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    metrics = {}
    cached = feedback.discover_prospective_corpus(root, cache_metrics=metrics)
    assert cached == feedback.discover_prospective_corpus(root, use_summary_cache=False)
    assert metrics["full_iid_parses"] == 2  # invalidated linked source plus genuine payload


@pytest.mark.parametrize("field", ["session", "artifact_identity"])
def test_even_resealed_conflicting_summary_cannot_override_handoff(tmp_path, field):
    root, _, path = _classification_fixture(tmp_path)
    feedback.discover_prospective_corpus(root)
    cache_path = root / feedback._SUMMARY_CACHE_PATH
    cache = json.loads(cache_path.read_text())
    entry = cache["entries"][feedback._relative(root, path)]
    entry["header"][field] = "another-session-or-identity"
    entry.pop("summary_identity")
    feedback._identity(entry, "iid-summary:", "summary_identity")
    _write(cache_path, cache)
    metrics = {}
    assert feedback.discover_prospective_corpus(root, cache_metrics=metrics) == feedback.discover_prospective_corpus(root, use_summary_cache=False)
    assert metrics["full_iid_parses"] == 2


@pytest.mark.parametrize("declaration", ["handoff_identity", "handoff_session", "operation_session", "operation_identity", "operation_output"])
def test_changed_exact_declaration_falls_back_without_altering_qualification(tmp_path, declaration):
    root, chain, path = _classification_fixture(tmp_path)
    feedback.discover_prospective_corpus(root)
    if declaration.startswith("handoff"):
        authority = root / "operations-review/canonical-post-close-v1" / chain[0] / "session_handoff_bundle.json"
        value = json.loads(authority.read_text())
        value["integrated_investment_decision_product_identity" if declaration == "handoff_identity" else "session"] = "another-session"
    else:
        authority = root / "operations-review/daily-research-session-operations-v1" / chain[0] / "run/run_manifest.json"
        value = json.loads(authority.read_text())
        if declaration == "operation_output":
            value["outputs"] = {"integrated_investment_decision_product": {"artifact_identity": "conflict"}}
        else:
            value["market_session" if declaration == "operation_session" else "operation_identity"] = "another-session"
    _write(authority, value)
    metrics = {}
    cached = feedback.discover_prospective_corpus(root, cache_metrics=metrics)
    assert cached == feedback.discover_prospective_corpus(root, use_summary_cache=False)
    if declaration != "operation_identity":
        assert metrics["full_iid_parses"] == 2
    assert not any(row["artifact_path"] == feedback._relative(root, path) for row in cached["genuine_artifacts"])


@pytest.mark.parametrize("corruption", ["malformed", "schema", "identity", "header", "oversized"])
def test_cache_corruption_is_optional_and_truthfully_reparsed(tmp_path, corruption):
    root, _, path = _classification_fixture(tmp_path)
    expected = feedback.discover_prospective_corpus(root)
    cache_path = root / feedback._SUMMARY_CACHE_PATH
    value = json.loads(cache_path.read_text())
    if corruption == "malformed":
        cache_path.write_text("{broken")
    elif corruption == "oversized":
        cache_path.write_bytes(b" " * (feedback._SUMMARY_CACHE_MAX_BYTES + 1))
    else:
        if corruption == "schema":
            value["contract_version"] = "old/version"
        else:
            entry = value["entries"][feedback._relative(root, path)]
            if corruption == "identity":
                entry["summary_identity"] = "wrong"
            else:
                entry["header"] = []
                entry.pop("summary_identity")
                feedback._identity(entry, "iid-summary:", "summary_identity")
        _write(cache_path, value)
    metrics = {}
    assert feedback.discover_prospective_corpus(root, cache_metrics=metrics) == expected
    assert metrics["full_iid_parses"] >= 2


def test_atomic_cache_replace_failure_preserves_previous_bytes_and_output(tmp_path, monkeypatch):
    root, _, path = _classification_fixture(tmp_path)
    feedback.discover_prospective_corpus(root)
    cache_path = root / feedback._SUMMARY_CACHE_PATH
    previous = cache_path.read_bytes()
    path.write_bytes(path.read_bytes() + b" ")

    def fail_replace(*args):
        raise OSError("injected atomic replace failure")

    monkeypatch.setattr(feedback.os, "replace", fail_replace)
    assert feedback.discover_prospective_corpus(root) == feedback.discover_prospective_corpus(root, use_summary_cache=False)
    assert cache_path.read_bytes() == previous
    assert not list(cache_path.parent.glob(".iid-summary-*.tmp"))


def test_writer_emits_from_memory_without_iid_parse(tmp_path, monkeypatch):
    root, _, path = _classification_fixture(tmp_path)
    artifact = json.loads(path.read_text())
    original = feedback._load_json

    def no_iid_parse(source):
        assert source != path
        return original(source)

    monkeypatch.setattr(feedback, "_load_json", no_iid_parse)
    feedback.retain_iid_classification_summary(root, path, artifact)
    metrics = {}
    feedback.discover_prospective_corpus(root, cache_metrics=metrics)
    assert metrics["summary_hits"] == 1


def test_pre_post_handoff_and_later_session_preserve_earlier_temporal_truth(tmp_path):
    root, chain, path = _classification_fixture(tmp_path)
    handoff = root / "operations-review/canonical-post-close-v1" / chain[0] / "session_handoff_bundle.json"
    saved = handoff.read_bytes()
    handoff.unlink()
    # The replay remains classification-only before the exact handoff exists.
    pre = feedback.build_feedback_artifact(root, use_summary_cache=False)
    assert feedback._canon(pre) == feedback._canon(feedback.build_feedback_artifact(root))
    assert feedback._canon(pre) == feedback._canon(feedback.build_feedback_artifact(root))
    handoff.write_bytes(saved)
    post = feedback.build_feedback_artifact(root, use_summary_cache=False)
    assert feedback._canon(post) == feedback._canon(feedback.build_feedback_artifact(root))
    assert feedback._canon(post) == feedback._canon(feedback.build_feedback_artifact(root))
    earlier = feedback.discover_prospective_corpus(root)["inventory"]
    _fixture_root(root, sessions=3)
    artifact = json.loads(path.read_text())
    artifact["requested_at"] = "legacy-unqualified-time"
    _write(path, artifact)
    later = feedback.discover_prospective_corpus(root)
    assert [row for row in later["inventory"] if row["decision_session"] in chain] == earlier
    assert later == feedback.discover_prospective_corpus(root, use_summary_cache=False)


@pytest.mark.parametrize("mutation", ["snapshot", "decision", "condition", "policy", "corrupt", "oversize"])
def test_settled_cache_invalidates_dependency_and_binding(tmp_path, monkeypatch, mutation):
    chain = [f"2026-01-{n:02d}" for n in range(1, 23)]
    snapshots = {s: _snapshot(s, 100 + i) for i, s in enumerate(chain)}
    kwargs = dict(artifact={"session": chain[0]}, source_path="retained.json", temporal={"status": feedback.GENUINE}, record=_record(chain[0]))
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    full = cache.evaluate(**kwargs)
    cache.finish()
    metrics = {}
    assert feedback.SettledFeedbackCache(tmp_path, chain, snapshots, metrics=metrics).evaluate(**kwargs) == full
    assert metrics == {"settled_hits": 1}
    if mutation == "snapshot":
        snapshots[chain[3]]["records"]["FPT"]["observations"][0]["close"] += 1
    elif mutation == "decision":
        kwargs["record"]["decision_identity"] += "changed"
    elif mutation == "condition":
        kwargs["record"]["trigger"]["trigger_level"] += 1
    elif mutation == "policy":
        monkeypatch.setattr(feedback, "OUTCOME_POLICY_CONSTANTS", {**feedback.OUTCOME_POLICY_CONSTANTS, "version": "bumped"})
    elif mutation == "corrupt":
        (tmp_path / feedback._SETTLED_CACHE_PATH).write_text("{bad", encoding="utf-8")
    else:
        monkeypatch.setattr(feedback, "_SETTLED_MAX_BYTES", 1)
    metrics = {}
    changed = feedback.SettledFeedbackCache(tmp_path, chain, snapshots, metrics=metrics).evaluate(**kwargs)
    assert metrics == {"settled_misses": 1}
    assert changed == feedback._feedback_record(chain=chain, snapshots=snapshots, **kwargs)


@pytest.mark.parametrize("role", ["trigger", "invalidation"])
def test_open_condition_never_settles(tmp_path, role):
    import prospective_decision_retention as retention
    chain = [f"2026-01-{n:02d}" for n in range(1, 23)]
    snapshots = {s: _snapshot(s, 100) for s in chain}
    record = _record(chain[0])
    record[role]["condition"] = retention.serialize_boundary_condition(
        {"status": "READY", "source_metric": "resistance", "baseline_value": 200,
         "comparison_operator": "FUTURE_CLOSE_GT_RESISTANCE_LEVEL"}, role=role, source_strategy_identity="strategy:1")
    kwargs = dict(artifact={"session": chain[0]}, source_path="retained.json", temporal={}, record=record)
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    cache.evaluate(**kwargs)
    assert cache.retained == {}


@pytest.mark.parametrize("price", [100, None])
def test_settled_extension_and_terminal_unqualified_parity(tmp_path, price):
    chain = [f"2026-01-{n:02d}" for n in range(1, 23)]
    snapshots = {s: _snapshot(s, price) for s in chain}
    kwargs = dict(artifact={"session": chain[0]}, source_path="retained.json", temporal={}, record=_record(chain[0]))
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    row = cache.evaluate(**kwargs)
    cache.finish()
    chain.append("2026-01-23")
    snapshots[chain[-1]] = _snapshot(chain[-1], 900)
    metrics = {}
    warm = feedback.SettledFeedbackCache(tmp_path, chain, snapshots, metrics=metrics).evaluate(**kwargs)
    assert metrics == {"settled_hits": 1}
    assert feedback._canon(row) == feedback._canon(warm) == feedback._canon(feedback._feedback_record(chain=chain, snapshots=snapshots, **kwargs))


def test_pending_horizons_and_absent_t0_not_settled(tmp_path):
    chain = ["2026-01-01", "2026-01-02"]
    snapshots = {s: _snapshot(s, 100) for s in chain}
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    for start in [chain[0], "2025-01-01"]:
        cache.evaluate(artifact={"session": start}, source_path="a", temporal={}, record=_record(start))
    assert cache.retained == {}


def test_full_artifact_settled_warm_equals_oracle(tmp_path):
    root, _ = _fixture_root(tmp_path, sessions=23)
    full = feedback.build_feedback_artifact(root, use_settled_cache=False)
    cold = feedback.build_feedback_artifact(root)
    metrics = {}
    warm = feedback.build_feedback_artifact(root, cache_metrics=metrics)
    assert metrics["settled_hits"] == 3
    assert feedback._canon(full) == feedback._canon(cold) == feedback._canon(warm)


def test_satisfied_conditions_terminal_but_incomplete_future_not_terminal(tmp_path):
    import prospective_decision_retention as retention
    chain = [f"2026-01-{n:02d}" for n in range(1, 23)]
    snapshots = {s: _snapshot(s, 100) for s in chain}
    record = _record(chain[0])
    for role in ("trigger", "invalidation"):
        record[role]["condition"] = retention.serialize_boundary_condition(
            {"status": "READY", "source_metric": "resistance", "baseline_value": 90,
             "comparison_operator": "FUTURE_CLOSE_GT_RESISTANCE_LEVEL"}, role=role, source_strategy_identity="s")
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    kwargs = dict(artifact={"session": chain[0]}, source_path="a", temporal={}, record=record)
    row = cache.evaluate(**kwargs)
    assert len(cache.retained) == 1
    assert row["trigger_invalidation_outcome"]["trigger"]["event_session"] == chain[1]
    snapshots[chain[1]]["records"] = {}
    cache = feedback.SettledFeedbackCache(tmp_path, chain, snapshots)
    cache.evaluate(**kwargs)
    assert cache.retained == {}


def test_settled_cache_prunes_entries_without_changing_full_output(tmp_path, monkeypatch):
    root, _ = _fixture_root(tmp_path, sessions=23)
    monkeypatch.setattr(feedback, "_SETTLED_MAX_ENTRIES", 1)
    cold = feedback.build_feedback_artifact(root)
    metrics = {}
    warm = feedback.build_feedback_artifact(root, cache_metrics=metrics)
    assert metrics["settled_hits"] == 1
    assert warm == cold == feedback.build_feedback_artifact(root, use_settled_cache=False)
    cache = json.loads((root / feedback._SETTLED_CACHE_PATH).read_text(encoding="utf-8"))
    assert len(cache["entries"]) == 1
