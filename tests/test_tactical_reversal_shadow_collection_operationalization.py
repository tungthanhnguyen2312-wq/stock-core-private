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
