"""TACTICAL_REVERSAL_SHADOW_COLLECTION_OPERATIONALIZATION_V1.

Covers the operational-wiring gap: whether a genuine completed Daily session can actually
invoke the shadow collector, with strict failure isolation from the production result.
"""
from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import pytest

import canonical_daily_operation as cdo
import canonical_post_close_pipeline as cpc
import tactical_reversal_prospective_shadow_collection as collection
from test_canonical_daily_operation import SESSION, _run  # noqa: E402  (established cross-test-file convention)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_tactical_artifact(root: Path, session: str, records: dict) -> Path:
    ops = root / "operations-review" / f"watchlist-tactical-entry-decision-v1-{session.replace('-', '')}"
    ops.mkdir(parents=True, exist_ok=True)
    path = ops / "watchlist_tactical_entry_classifier_artifact.json"
    path.write_text(json.dumps({
        "session": session,
        "artifact_identity": f"watchlist_tactical_entry_classifier:test-{session}",
        "source_artifacts": {"descriptive": "market_wide_current_descriptive_research:abc"},
        "records": records,
    }), encoding="utf-8")
    return path


class TestRunTacticalReversalShadowCollectionUnit:
    """Direct tests of canonical_post_close_pipeline.run_tactical_reversal_shadow_collection."""

    def test_skipped_when_no_tactical_artifact_retained(self, tmp_path, monkeypatch):
        def _forbidden(*a, **k):
            raise AssertionError("subprocess.run must not be called when no artifact is retained")
        monkeypatch.setattr(cpc.subprocess, "run", _forbidden)
        result = cpc.run_tactical_reversal_shadow_collection(tmp_path, "2026-09-12")
        assert result["status"] == cpc.SHADOW_COLLECTION_SKIPPED_NO_ELIGIBLE_ARTIFACT
        assert result["session"] == "2026-09-12"

    def test_exact_completed_session_used_in_subprocess_call(self, tmp_path, monkeypatch):
        _write_tactical_artifact(tmp_path, "2026-09-12", {
            "XXX": {"rule_id": "R9_DOWNTREND_DEFAULT", "entry_state": "DOWNTREND", "entry_action": "AVOID", "signals": {"close": 10.0}},
        })
        captured = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")
        monkeypatch.setattr(cpc.subprocess, "run", _fake_run)
        result = cpc.run_tactical_reversal_shadow_collection(tmp_path, "2026-09-12")
        assert result["status"] == cpc.SHADOW_COLLECTION_COMPLETE
        assert "--session" in captured["cmd"]
        assert captured["cmd"][captured["cmd"].index("--session") + 1] == "2026-09-12"

    def test_no_provider_acquisition_flags_or_network_call_in_invocation(self, tmp_path, monkeypatch):
        _write_tactical_artifact(tmp_path, "2026-09-12", {
            "XXX": {"rule_id": "R9_DOWNTREND_DEFAULT", "entry_state": "DOWNTREND", "entry_action": "AVOID", "signals": {"close": 10.0}},
        })
        captured = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        monkeypatch.setattr(cpc.subprocess, "run", _fake_run)
        cpc.run_tactical_reversal_shadow_collection(tmp_path, "2026-09-12")
        joined = " ".join(captured["cmd"]).lower()
        for forbidden in ("dnse", "vnstock", "vci", "kbs", "http://", "https://"):
            assert forbidden not in joined
        source = inspect.getsource(cpc.run_tactical_reversal_shadow_collection)
        for forbidden in ("dnse", "vnstock", "vci_", "kbs_"):
            assert forbidden not in source.lower()

    def test_failed_when_subprocess_returns_nonzero(self, tmp_path, monkeypatch):
        _write_tactical_artifact(tmp_path, "2026-09-12", {
            "XXX": {"rule_id": "R9_DOWNTREND_DEFAULT", "entry_state": "DOWNTREND", "entry_action": "AVOID", "signals": {"close": 10.0}},
        })
        monkeypatch.setattr(cpc.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"))
        result = cpc.run_tactical_reversal_shadow_collection(tmp_path, "2026-09-12")
        assert result["status"] == cpc.SHADOW_COLLECTION_FAILED
        assert "boom" in result["reason"]

    def test_shadow_collection_never_raises_even_on_subprocess_exception(self, tmp_path, monkeypatch):
        _write_tactical_artifact(tmp_path, "2026-09-12", {
            "XXX": {"rule_id": "R9_DOWNTREND_DEFAULT", "entry_state": "DOWNTREND", "entry_action": "AVOID", "signals": {"close": 10.0}},
        })

        def _boom(cmd, **k):
            raise OSError("no such executable")
        monkeypatch.setattr(cpc.subprocess, "run", _boom)
        result = cpc.run_tactical_reversal_shadow_collection(tmp_path, "2026-09-12")  # must not raise
        assert result["status"] == cpc.SHADOW_COLLECTION_FAILED

    def test_real_subprocess_end_to_end_with_the_actual_tool_script(self, tmp_path):
        """One genuine (no-mock) real-subprocess run against a tiny synthetic artifact."""
        _write_tactical_artifact(tmp_path, "2026-09-12", {
            "AAA": {"rule_id": "R8_SELLING_PRESSURE_EASING", "entry_state": "SELLING_PRESSURE_EASING", "entry_action": "WAIT", "signals": {"close": 10.0, "momentum_bucket": "UPPER_QUARTILE"}},
        })
        result = cpc.run_tactical_reversal_shadow_collection(REPO_ROOT, "2026-09-12", artifact_root=tmp_path, output_root=tmp_path)
        assert result["status"] == cpc.SHADOW_COLLECTION_COMPLETE
        assert result["summary"]["collection"]["ticker_count"] == 1
        assert result["summary"]["collection"]["evidence_mode"] == collection.PROSPECTIVE


class TestDailyOperationIntegration:
    def test_daily_operation_invokes_shadow_collection_with_resolved_session(self, tmp_path, monkeypatch):
        calls = []

        def _fake_shadow(root, session, **kwargs):
            calls.append((root, session))
            return {"status": "SHADOW_COLLECTION_COMPLETE", "session": session}
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", _fake_shadow)
        record = _run(tmp_path, monkeypatch)
        assert len(calls) == 1
        assert calls[0][1] == SESSION
        assert record["tactical_reversal_shadow_collection"]["status"] == "SHADOW_COLLECTION_COMPLETE"

    def test_shadow_collection_failure_does_not_block_daily_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_FAILED", "reason": "boom"})
        record = _run(tmp_path, monkeypatch)
        assert record.get("daily_operation_state")
        assert record["tactical_reversal_shadow_collection"]["status"] == "SHADOW_COLLECTION_FAILED"
        assert record["daily_producer_status"] == "COMPLETED"

    def test_production_classifier_and_action_unchanged_regardless_of_shadow_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_COMPLETE"})
        record_ok = _run(tmp_path / "a", monkeypatch)
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_FAILED", "reason": "x"})
        record_failed = _run(tmp_path / "b", monkeypatch)
        assert record_ok["daily_producer_status"] == record_failed["daily_producer_status"]
        assert record_ok["daily_producer_run_identity"] == record_failed["daily_producer_run_identity"]
        assert record_ok["daily_session_shadow_recommendation"] == record_failed["daily_session_shadow_recommendation"]

    def test_shadow_collection_status_excluded_from_operation_identity(self, tmp_path, monkeypatch):
        """A volatile shadow-collection status must never destabilize Daily's idempotent
        operation identity -- otherwise a transient collector hiccup could spuriously raise
        IMMUTABLE_OPERATION_RECORD_CONFLICT on an otherwise-identical rerun."""
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_COMPLETE"})
        record_ok = _run(tmp_path / "a", monkeypatch)
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_FAILED", "reason": "different"})
        record_failed = _run(tmp_path / "b", monkeypatch)
        assert record_ok["operation_identity"] == record_failed["operation_identity"]

    def test_no_rerun_conflict_when_shadow_status_changes(self, tmp_path, monkeypatch):
        """Rerunning the exact same session, with the shadow-collection outcome differing
        between runs, must not raise IMMUTABLE_OPERATION_RECORD_CONFLICT."""
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_COMPLETE"})
        first = _run(tmp_path, monkeypatch)
        monkeypatch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *a, **k: {"status": "SHADOW_COLLECTION_FAILED", "reason": "transient"})
        second = _run(tmp_path, monkeypatch)  # must not raise
        assert first["operation_identity"] == second["operation_identity"]
        assert second["tactical_reversal_shadow_collection"]["status"] == "SHADOW_COLLECTION_FAILED"


class TestHistoricalMappingInvariants:
    def test_historical_backfill_always_bootstrap_non_prospective(self):
        for session in ("2026-08-21", "2026-09-11"):
            assert collection.evidence_mode_for_session(session) == collection.BOOTSTRAP_NON_PROSPECTIVE

    def test_ambiguous_retained_session_raises_rather_than_silently_picking_one(self, tmp_path):
        _write_tactical_artifact(tmp_path, "2026-08-21", {"XXX": {"rule_id": "R9_DOWNTREND_DEFAULT", "signals": {"close": 1.0}}})
        other = tmp_path / "operations-review" / "watchlist-tactical-entry-decision-v1-20260823"
        other.mkdir(parents=True, exist_ok=True)
        (other / "watchlist_tactical_entry_classifier_artifact.json").write_text(json.dumps({
            "session": "2026-08-21", "artifact_identity": "x", "source_artifacts": {}, "records": {},
        }), encoding="utf-8")
        with pytest.raises(collection.ProspectiveShadowCollectionError):
            collection.discover_retained_tactical_sessions(tmp_path)

    def test_directory_date_mismatched_session_is_still_discovered_and_loadable(self, tmp_path):
        """Regression for the real retained evidence where a directory named for its rebuild
        date (...-20260823) declares an earlier session (2026-08-21) internally."""
        mismatched = tmp_path / "operations-review" / "watchlist-tactical-entry-decision-v1-20260823"
        mismatched.mkdir(parents=True, exist_ok=True)
        (mismatched / "watchlist_tactical_entry_classifier_artifact.json").write_text(json.dumps({
            "session": "2026-08-21", "artifact_identity": "x", "source_artifacts": {},
            "records": {"AAA": {"rule_id": "R9_DOWNTREND_DEFAULT", "signals": {"close": 1.0}}},
        }), encoding="utf-8")
        sessions = collection.discover_retained_tactical_sessions(tmp_path)
        assert sessions == ["2026-08-21"]
        artifact = collection.load_tactical_artifact(tmp_path, session="2026-08-21")
        assert artifact is not None and artifact["session"] == "2026-08-21"


# --------------------------------------------------------------------------------------
# OWNER_DAILY_P2B_TACTICAL_SHADOW_IO_DEDUP_V1: run-scoped index + single-read observations.
# --------------------------------------------------------------------------------------

import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "tools"))
import run_tactical_reversal_prospective_shadow_collection as runner  # noqa: E402

_RULES = ("R8_SELLING_PRESSURE_EASING", "R9_DOWNTREND_DEFAULT", "R6_EARLY_REVERSAL_CANDIDATE", "R3_UPTREND_CONFIRMED_DEFAULT")
_SESSIONS = tuple(f"2026-09-{day:02d}" for day in range(14, 26))  # 12 sessions after the activation boundary


def _records(session_index: int) -> dict:
    return {
        f"T{n}": {
            "rule_id": _RULES[(n + session_index) % len(_RULES)], "entry_state": "S", "entry_action": "WATCH",
            "signals": {"close": 10.0 + n + session_index * 0.5 * (-1) ** n},
        }
        for n in range(6)
    }


def _corpus(root: Path, sessions=_SESSIONS) -> None:
    for position, session in enumerate(sessions):
        _write_tactical_artifact(root, session, _records(position))


def _populate(root: Path, store_root: Path, sessions=_SESSIONS) -> None:
    index = collection.build_tactical_artifact_index(root)
    for session in sessions:
        runner.collect_session(retained_evidence_root=root, store_root=store_root, session=session, index=index)


def _legacy_mature_all(*, retained_evidence_root: Path, store_root: Path) -> dict:
    """Verbatim pre-P2B maturation procedure (full objects, list+load+persist-with-reload)."""
    sessions = collection.discover_retained_tactical_sessions(retained_evidence_root)
    latest = sessions[-1] if sessions else None
    artifacts = {s: collection.load_tactical_artifact(retained_evidence_root, session=s) for s in sessions}
    store = collection.ProspectiveShadowObservationStore(store_root)
    outcomes, matured, observations = {}, [], []
    for observation_id in store.list_observation_ids():
        observation = store.load_observation(observation_id)
        observations.append(observation)
        future = [item for item in sessions if item > observation["trigger_session"]]
        if not future:
            continue
        rows = runner._future_rows(observation["ticker"], future, artifacts)
        outcome = collection.mature_outcome(observation, rows, evaluation_as_of_session=latest)
        store.persist_outcome_update(observation_id, outcome)
        outcomes[observation_id] = outcome
        matured.append(observation_id)
    return {"matured_observation_ids": matured, "collection_status": collection.build_collection_status(observations, outcomes)}


def _tree_bytes(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*.json"))}


class _ReadCounter:
    """Counts Path.read_text calls by kind without touching production code."""

    def __init__(self, monkeypatch):
        self.counts = {"classifier": 0, "observation": 0, "outcome": 0}
        original = Path.read_text

        def counting(path, *args, **kwargs):
            if path.name == "watchlist_tactical_entry_classifier_artifact.json":
                self.counts["classifier"] += 1
            elif path.parent.name == "observations":
                self.counts["observation"] += 1
            elif path.parent.name == "outcome_updates":
                self.counts["outcome"] += 1
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting)


class TestTacticalIndexRunScope:
    def test_index_discovered_once_per_collection_run_and_each_artifact_parsed_once(self, tmp_path, monkeypatch, capsys):
        _corpus(tmp_path / "ev")
        discoveries = []
        original = collection._discover_retained_tactical_index
        monkeypatch.setattr(collection, "_discover_retained_tactical_index",
                            lambda *a, **k: discoveries.append(1) or original(*a, **k))
        counter = _ReadCounter(monkeypatch)
        assert runner.main(["--retained-evidence-root", str(tmp_path / "ev"), "--store-root", str(tmp_path / "st")]) == 0
        capsys.readouterr()
        sessions = len(_SESSIONS)
        assert len(discoveries) == 1
        # one index parse per artifact + (current, prior) for collection + one load per session for maturation
        assert counter.counts["classifier"] == sessions + 2 + sessions

    def test_mature_all_alone_is_linear_not_quadratic(self, tmp_path, monkeypatch):
        _corpus(tmp_path / "ev")
        _populate(tmp_path / "ev", tmp_path / "st")
        counter = _ReadCounter(monkeypatch)
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")
        assert counter.counts["classifier"] == 2 * len(_SESSIONS)  # index + one load per session

    def test_supplied_index_is_not_rebuilt(self, tmp_path, monkeypatch):
        _corpus(tmp_path / "ev")
        index = collection.build_tactical_artifact_index(tmp_path / "ev")
        counter = _ReadCounter(monkeypatch)
        for session in _SESSIONS:
            assert collection.load_tactical_artifact(tmp_path / "ev", session=session, index=index)["session"] == session
        assert counter.counts["classifier"] == len(_SESSIONS)  # loads only; no index parse

    def test_index_metrics_seam_counts_parses(self, tmp_path):
        _corpus(tmp_path / "ev")
        metrics: dict = {}
        index = collection.build_tactical_artifact_index(tmp_path / "ev", metrics=metrics)
        collection.load_tactical_artifact(tmp_path / "ev", session=_SESSIONS[0], index=index, metrics=metrics)
        assert metrics == {"classifier_index_parses": len(_SESSIONS), "classifier_artifact_loads": 1}

    def test_exact_session_addressing_deterministic_order_and_read_only(self, tmp_path):
        _corpus(tmp_path / "ev")
        index = collection.build_tactical_artifact_index(tmp_path / "ev")
        assert index.sessions == sorted(_SESSIONS) == collection.discover_retained_tactical_sessions(tmp_path / "ev", index=index)
        with pytest.raises(TypeError):
            index.paths[_SESSIONS[0]] = tmp_path  # type: ignore[index]
        # equal to what a standalone discovery returns
        assert dict(index.paths) == collection._discover_retained_tactical_index(tmp_path / "ev")

    def test_another_session_artifact_cannot_satisfy_request_and_no_latest_fallback(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:3])
        index = collection.build_tactical_artifact_index(tmp_path / "ev")
        assert collection.load_tactical_artifact(tmp_path / "ev", session="2026-09-30", index=index) is None
        assert collection.load_tactical_artifact(tmp_path / "ev", session="2026-09-13", index=index) is None
        loaded = collection.load_tactical_artifact(tmp_path / "ev", session=_SESSIONS[1], index=index)
        assert loaded["session"] == _SESSIONS[1]

    def test_missing_artifact_after_indexing_returns_none_as_before(self, tmp_path):
        path = _write_tactical_artifact(tmp_path / "ev", "2026-09-14", _records(0))
        index = collection.build_tactical_artifact_index(tmp_path / "ev")
        path.unlink()
        assert collection.load_tactical_artifact(tmp_path / "ev", session="2026-09-14", index=index) is None

    def test_malformed_artifact_semantics_unchanged(self, tmp_path):
        good = _write_tactical_artifact(tmp_path / "ev", "2026-09-14", _records(0))
        bad = _write_tactical_artifact(tmp_path / "ev", "2026-09-15", _records(1))
        bad.write_text("{not json", encoding="utf-8")
        # discovery skips unparseable artifacts exactly as before ...
        index = collection.build_tactical_artifact_index(tmp_path / "ev")
        assert index.sessions == ["2026-09-14"]
        # ... and a artifact that turns malformed after indexing still raises on load, as before
        good.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            collection.load_tactical_artifact(tmp_path / "ev", session="2026-09-14", index=index)

    def test_ambiguous_session_still_raises_when_building_index(self, tmp_path):
        _write_tactical_artifact(tmp_path / "ev", "2026-08-21", _records(0))
        other = tmp_path / "ev" / "operations-review" / "watchlist-tactical-entry-decision-v1-20260823"
        other.mkdir(parents=True)
        (other / "watchlist_tactical_entry_classifier_artifact.json").write_text(
            json.dumps({"session": "2026-08-21", "records": {}}), encoding="utf-8")
        with pytest.raises(collection.ProspectiveShadowCollectionError):
            collection.build_tactical_artifact_index(tmp_path / "ev")

    def test_legacy_call_shapes_still_work_without_index(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:2])
        assert collection.discover_retained_tactical_sessions(tmp_path / "ev") == list(_SESSIONS[:2])
        assert collection.load_tactical_artifact(tmp_path / "ev", session=_SESSIONS[0])["session"] == _SESSIONS[0]


class TestObservationSingleReadAndStreaming:
    def test_list_ids_reads_each_observation_file_once(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:2])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:2])
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        ids = store.list_observation_ids()
        assert len(ids) == 12 and ids == sorted(ids)
        assert store.read_metrics["observation_file_reads"] == 12

    def test_mature_all_reads_each_observation_once_and_never_reloads_for_persist(self, tmp_path, monkeypatch):
        _corpus(tmp_path / "ev")
        _populate(tmp_path / "ev", tmp_path / "st")
        total = len(_SESSIONS) * 6
        counter = _ReadCounter(monkeypatch)
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")
        assert counter.counts["observation"] == total  # legacy: 3 reads per observation (+1 for persist)

    def test_iterator_is_lazy_and_does_not_retain_observations(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:2])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:2])
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        stream = store.iter_validated_observations()
        next(stream)
        assert store.read_metrics["observation_file_reads"] == 1  # only the file actually consumed
        assert not hasattr(store, "_observations")
        assert sum(1 for _ in stream) == 11

    def test_malformed_observation_still_fails_identically(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:1])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:1])
        victim = sorted((tmp_path / "st" / "observations").glob("*.json"))[0]
        victim.write_text("{broken", encoding="utf-8")
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="STORE_RECORD_UNREADABLE_OR_TAMPERED"):
            list(store.iter_validated_observations())
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="STORE_RECORD_UNREADABLE_OR_TAMPERED"):
            store.list_observation_ids()

    def test_tampered_observation_identity_still_verified(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:1])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:1])
        victim = sorted((tmp_path / "st" / "observations").glob("*.json"))[0]
        body = json.loads(victim.read_text(encoding="utf-8"))
        body["ticker"] = "TAMPERED"
        victim.write_text(json.dumps(body), encoding="utf-8")
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="OBSERVATION_CONTENT_IDENTITY_INVALID"):
            store.list_observation_ids()
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="OBSERVATION_CONTENT_IDENTITY_INVALID"):
            runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")

    def test_misfiled_observation_validated_via_canonical_path_and_deduplicated(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:1])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:1])
        obs_dir = tmp_path / "st" / "observations"
        victim = sorted(obs_dir.glob("*.json"))[0]
        (obs_dir / "copy.json").write_bytes(victim.read_bytes())  # same valid id under a non-canonical name
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        assert len(store.list_observation_ids()) == 6
        victim.unlink()  # canonical file gone -> the misfiled copy cannot stand in for it
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="OBSERVATION_NOT_FOUND"):
            store.list_observation_ids()

    def test_persist_outcome_update_fallback_when_validated_observation_mismatched(self, tmp_path):
        _corpus(tmp_path / "ev", _SESSIONS[:2])
        _populate(tmp_path / "ev", tmp_path / "st", _SESSIONS[:2])
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        oid, observation = next(store.iter_validated_observations())
        outcome = collection.mature_outcome(observation, [], evaluation_as_of_session=_SESSIONS[-1])
        store.read_metrics["observation_file_reads"] = 0
        store.persist_outcome_update(oid, outcome, validated_observation=observation)
        assert store.read_metrics["observation_file_reads"] == 0
        store.persist_outcome_update(oid, outcome, validated_observation={"observation_id": "other"})
        assert store.read_metrics["observation_file_reads"] == 1  # fail-closed reload
        with pytest.raises(collection.ProspectiveShadowCollectionError, match="OBSERVATION_NOT_FOUND"):
            store.persist_outcome_update("missing", outcome, validated_observation=observation)


class TestOutputEquivalenceWithLegacyProcedure:
    def test_outcome_updates_observations_and_status_are_byte_and_content_identical(self, tmp_path):
        _corpus(tmp_path / "ev")
        _populate(tmp_path / "ev", tmp_path / "legacy")
        _populate(tmp_path / "ev", tmp_path / "new")
        legacy = _legacy_mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy")
        new = runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "new")
        assert new == legacy
        assert _tree_bytes(tmp_path / "new") == _tree_bytes(tmp_path / "legacy")
        assert len(list((tmp_path / "new" / "outcome_updates").glob("*.json"))) == (len(_SESSIONS) - 1) * 6

    def test_matured_ids_sorted_and_posture_authority_untouched(self, tmp_path):
        _corpus(tmp_path / "ev")
        _populate(tmp_path / "ev", tmp_path / "st")
        result = runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")
        assert result["matured_observation_ids"] == sorted(result["matured_observation_ids"])
        store = collection.ProspectiveShadowObservationStore(tmp_path / "st")
        for _, observation in store.iter_validated_observations():
            assert observation["authority"] == collection.AUTHORITY_LABEL
            assert observation["no_probability_target_or_sizing_emitted"] is True
        for update in store.latest_outcome_updates_by_observation().values():
            assert update["no_probability_target_or_sizing_emitted"] is True

    def test_idempotent_rerun_changes_no_bytes(self, tmp_path):
        _corpus(tmp_path / "ev")
        _populate(tmp_path / "ev", tmp_path / "st")
        first = runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")
        snapshot = _tree_bytes(tmp_path / "st")
        second = runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "st")
        assert second == first and _tree_bytes(tmp_path / "st") == snapshot

    def test_cli_main_output_matches_legacy_collection_then_maturation(self, tmp_path, capsys):
        _corpus(tmp_path / "ev")
        for session in _SESSIONS[:-1]:
            runner.collect_session(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy", session=session)
            runner.collect_session(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "new", session=session)
        runner.collect_session(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy", session=_SESSIONS[-1])
        legacy = _legacy_mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy")
        assert runner.main(["--retained-evidence-root", str(tmp_path / "ev"), "--store-root", str(tmp_path / "new")]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["maturation"] == legacy
        assert _tree_bytes(tmp_path / "new") == _tree_bytes(tmp_path / "legacy")
