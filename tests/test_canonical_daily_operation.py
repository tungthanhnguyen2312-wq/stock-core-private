"""Canonical daily one-command operation: two-phase gate, one P3F9B owner, publication delegation."""
from __future__ import annotations

from datetime import datetime
import inspect
import json
from pathlib import Path
import shutil
import socket

import pytest

import canonical_daily_operation as cdo
import completed_market_session_gate as gate
from canonical_dashboard_runtime_release import CanonicalRuntimeReleaseError
from canonical_trusted_subset_release import CanonicalTrustedSubsetError
from daily_producer_pipeline import DailyProducerError
from governed_publication_completion import PublicationCompletionError
from vn_time import VN_TZ

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-08-26"
BEFORE = datetime(2026, 8, 26, 17, 59, tzinfo=VN_TZ)
AFTER = datetime(2026, 8, 26, 18, 5, tzinfo=VN_TZ)
POST_CLOSE = datetime(2026, 8, 26, 19, 19, tzinfo=VN_TZ)
SOURCE_SHA = "534e4971edf2b9be62467ce89758b6625544558d"


def _working_dates(*dates: str) -> dict:
    return {"workingDates": list(dates)}


def _p3f9b(session: str, *, requested_at: str, exact: int = 889, total: int = 1683, **extra) -> dict:
    payload = {
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
    }
    payload.update(extra)
    return payload


def _acquired(tmp_path: Path, session: str = SESSION, *, reused: bool = False, **snap_kw) -> dict:
    snapshot = _p3f9b(session, requested_at=snap_kw.pop("requested_at", f"{session}T19:19:00+07:00"), **snap_kw)
    return {
        "snapshot": snapshot,
        "resolved_completed_session": session,
        "coverage": {
            "exact_session_retained_count": snapshot["exact_session_observed_count"],
            "total_candidates": snapshot["attempted_candidate_count"],
            "ratio": snapshot["exact_session_observed_count"] / snapshot["attempted_candidate_count"],
        },
        "artifact_root": tmp_path,
        "eligibility": {"reused_existing_eligible_artifact": reused, "redirected": False},
        "triage_status": {},
        "paths": {},
    }


def _write_runtime(runtime_root: Path, session: str) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "bundle_manifest.json").write_text(json.dumps({
        "freshness": {"reference_session": session, "blocked": False, "status": "fresh"},
    }), encoding="utf-8")
    (runtime_root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8")
    (runtime_root / "market_breadth.csv").write_text(
        f"group,date\nALL,{session}\n", encoding="utf-8")
    (runtime_root / "analysis_latest.json").write_text(json.dumps({
        "summary": {"session_date": session},
    }), encoding="utf-8")
    (runtime_root / "screen_snapshot_live.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8")


def _producer(tmp_path: Path, session: str = SESSION) -> dict:
    return {
        "status": "COMPLETED",
        "session": session,
        "run_identity": "daily_producer_run:9f8dcbb36d9428ff772d94a3dec85d96d0a573e39d5905b433c7ba28ffb856b0",
        "run_dir": tmp_path,
        "operation": {
            "opportunity": None,
            "manifest": {"operation_identity": "daily_research_session_operation:1883a16b50f0ef2d8e367391811ad164c1742532b7d4ae3c72fe6e3c218c30e0"},
        },
        "manifest": {
            "daily_session_shadow_recommendation": {
                "status": "REUSED",
                "session": session,
                "artifact_identity": "daily_session_shadow_recommendation:test",
                "shadow_security_recommendation_identity": "shadow_security_recommendation:test",
                "fundamental_invalidation_identity": "fundamental_thesis_invalidation_precision:test",
                "source_artifact_identities": {},
            },
        },
    }


def _patch_downstream(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cdo, "register_session_inputs", lambda *a, **k: {"status": "REGISTERED"})
    monkeypatch.setattr(cdo, "validate_and_freeze_completed_session", lambda *a, **k: {"status": "FROZEN"})
    monkeypatch.setattr(cdo, "build_enrichment_components", lambda *a, **k: {})
    monkeypatch.setattr(cdo, "build_decision_packet", lambda *a, **k: {"artifact_identity": "current_research_decision_packet:ed1bfde1"})
    monkeypatch.setattr(cdo, "run_prospective_collection", lambda *a, **k: {
        "status": "COLLECTED", "snapshot": {"snapshot_id": "prospective_research_cohort_snapshot:6b98b392"}, "path": str(tmp_path),
    })
    monkeypatch.setattr(cdo, "build_tiered_bundle", lambda *a, **k: {
        "session_handoff_bundle": {}, "bundle_dir": tmp_path,
    })


def _run(tmp_path: Path, monkeypatch, *, now=POST_CLOSE, session=SESSION, complete_publication=False,
         acquire_fn=None, producer_fn=None, runtime_fn=None, trusted_fn=None, publication_runner=None,
         working=None, exact=None, runtime_session=None, **kwargs):
    _patch_downstream(monkeypatch, tmp_path)
    runtime = tmp_path / "runtime"
    _write_runtime(runtime, runtime_session or session)

    calls = {"acquire": 0, "runtime": 0, "trusted": 0, "producer": 0, "publication": []}

    def acquire(*a, **k):
        calls["acquire"] += 1
        if acquire_fn:
            return acquire_fn(*a, **k)
        return _acquired(tmp_path, session)

    def produce(*a, **k):
        calls["producer"] += 1
        if producer_fn:
            return producer_fn(*a, **k)
        return _producer(tmp_path, session)

    def runtime_mat(*a, **k):
        calls["runtime"] += 1
        if runtime_fn:
            return runtime_fn(*a, **k)
        return {"session": session, "live_count": 889}

    def trusted_mat(*a, **k):
        calls["trusted"] += 1
        if trusted_fn:
            return trusted_fn(*a, **k)
        return {"session": session, "trusted_subset_ready": True, "records_fingerprint": "fp"}

    def pub_runner(argv):
        calls["publication"].append(list(argv))
        if publication_runner:
            return publication_runner(argv)
        return {
            "publication_state": "PUBLISHED",
            "release_source_sha": SOURCE_SHA,
            "dashboard_ci_status": "SUCCESS",
            "deploy_pages_status": "SUCCESS",
            "public_byte_identity": "PASS",
            "attestation_identity": "governed_publication_attestation:test",
        }

    record = cdo.run_canonical_daily_operation(
        tmp_path,
        runtime,
        session,
        now=now,
        complete_publication=complete_publication,
        working_dates_evidence=working if working is not None else _working_dates(session, "2026-08-27"),
        exact_session_evidence=exact,
        acquire_fn=acquire,
        producer_fn=produce,
        runtime_fn=runtime_mat,
        trusted_fn=trusted_mat,
        publication_runner=pub_runner if complete_publication else None,
        out_dir=tmp_path / "operations-review",
        **kwargs,
    )
    record["_calls"] = calls
    return record


def _completed_registry(root: Path, *sessions: str) -> None:
    path = root / "config" / "daily_research_session_input_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"completed_sessions": {
        session: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
                  "completion_evidence": {"basis": "EXACT_SESSION_UPSTREAM_ARTIFACT_REGISTRY"}}
        for session in sessions
    }}), encoding="utf-8")


def test_sunday_auto_resolves_latest_governed_completed_session_without_floor(monkeypatch, tmp_path):
    sunday = datetime(2026, 8, 30, 13, 0, tzinfo=VN_TZ)
    target = "2026-08-28"
    _completed_registry(tmp_path, target)
    exact = _p3f9b(target, requested_at="2026-08-28T19:19:00+07:00")
    monkeypatch.setattr(gate, "load_exact_session_evidence_from_root", lambda *_args: exact)
    resolution = gate.resolve_latest_qualified_completed_session(tmp_path, sunday.date().isoformat())
    assert resolution and resolution["session"] == target
    monkeypatch.setattr(cdo, "resolve_latest_qualified_completed_session", lambda *_args: resolution)
    record = _run(
        tmp_path, monkeypatch, now=sunday, session=None, runtime_session=target,
        working=_working_dates("2026-08-31", "2026-09-01"),
        acquire_fn=lambda *_args, **_kwargs: _acquired(tmp_path, target, reused=True),
        producer_fn=lambda *_args, **_kwargs: _producer(tmp_path, target),
        runtime_fn=lambda *_args, **_kwargs: {"session": target, "live_count": 889},
        trusted_fn=lambda *_args, **_kwargs: {"session": target, "trusted_subset_ready": True},
    )
    assert record["session"] == target
    assert record["phase_a"]["automatic_non_trading_resolution"]["session"] == target


def test_holiday_auto_resolution_uses_ledger_not_calendar_day_subtraction(monkeypatch, tmp_path):
    holiday = datetime(2026, 9, 2, 13, 0, tzinfo=VN_TZ)
    target = "2026-08-28"
    _completed_registry(tmp_path, "2026-08-27", target)
    exact = _p3f9b(target, requested_at="2026-08-28T19:19:00+07:00")
    monkeypatch.setattr(gate, "load_exact_session_evidence_from_root", lambda _root, session: exact if session == target else None)
    resolution = gate.resolve_latest_qualified_completed_session(tmp_path, holiday.date().isoformat())
    assert resolution and resolution["session"] == target


def test_non_trading_day_without_qualified_ledger_evidence_fails_closed():
    result = gate.evaluate_attempt_eligibility(
        requested_at=datetime(2026, 8, 30, 13, 0, tzinfo=VN_TZ),
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
    )
    assert result["attempt_gate_status"] == gate.STATUS_PROVIDER_EVIDENCE_UNAVAILABLE
    assert "NON_TRADING_DAY_NO_QUALIFIED_COMPLETED_SESSION" in result["reason_codes"]


def test_before_safety_floor_no_acquisition(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("acquisition_must_not_run")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, now=BEFORE, acquire_fn=forbidden)
    assert exc.value.stage == cdo.STAGE_TOO_EARLY


def test_phase_a_eligible_after_floor_not_completion_ready_before_acquisition(tmp_path):
    phase_a = gate.evaluate_attempt_eligibility(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
    )
    phase_b = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
    )
    assert phase_a["attempt_gate_status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert phase_b["completion_gate_status"] != gate.STATUS_READY
    assert phase_b["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT


def test_time_alone_cannot_establish_phase_b():
    phase_b = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
    )
    assert phase_b["completion_gate_status"] != gate.STATUS_READY
    assert phase_b["ready_semantic"] is None


def test_one_valid_exact_session_acquisition_phase_b_ready(tmp_path, monkeypatch):
    record = _run(tmp_path, monkeypatch)
    assert record["phase_b"]["status"] == gate.STATUS_READY
    assert record["session_gate"] == gate.READY_SEMANTIC
    assert record["_calls"]["acquire"] == 1


def test_backdated_retained_session_uses_exact_evidence_and_preserves_requested_session(tmp_path, monkeypatch):
    backdated_now = datetime(2026, 8, 30, 18, 5, tzinfo=VN_TZ)
    seen_sessions = []

    def acquire(_root, requested_session, *_args, **_kwargs):
        seen_sessions.append(requested_session)
        return _acquired(tmp_path, requested_session, reused=True)

    record = _run(
        tmp_path,
        monkeypatch,
        now=backdated_now,
        working=_working_dates("2026-08-31", "2026-09-01"),
        exact=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
        acquire_fn=acquire,
    )
    assert record["phase_a"]["status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert record["phase_b"]["status"] == gate.STATUS_READY
    assert seen_sessions == [SESSION]


def test_2026_08_26_retained_artifact_is_loaded_read_only_without_regeneration(tmp_path, monkeypatch):
    nodash = SESSION.replace("-", "")
    retained = (
        tmp_path / "operations-review" / "canonical-post-close-v1" / SESSION
        / "post-close-attempt-191900" / "operations-review"
        / f"p3f9b-market-wide-exact-session-scaleout-{nodash}"
        / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
    )
    retained.parent.mkdir(parents=True)
    retained.write_text(gate.canonical_dump({
        "artifact_identity": "p3f9b_market_wide_exact_session_scaleout:" + "c" * 64,
        "artifact_sha256": "c" * 64,
        "contract_version": "p3f9b_market_wide_exact_session_scaleout/v1",
        "execution_timestamp": "2026-08-26T19:19:00+07:00",
        "exact_session_coverage": {"attempted_candidate_count": 1683, "exact_session_observed_count": 889},
        "resolved_session": {
            "resolved_completed_session": SESSION,
            "retained_snapshot_session": SESSION,
            "execution_timestamp": "2026-08-26T19:19:00+07:00",
        },
        "snapshot_identity": "p3f9_exact_session_snapshot:" + "c" * 64,
    }), encoding="utf-8")
    original_bytes = retained.read_bytes()
    record = _run(
        tmp_path,
        monkeypatch,
        now=datetime(2026, 8, 30, 18, 5, tzinfo=VN_TZ),
        working=_working_dates("2026-08-31", "2026-09-01"),
    )
    assert record["phase_a"]["status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert retained.read_bytes() == original_bytes


def test_backdated_historical_session_without_exact_evidence_requests_exact_target(tmp_path, monkeypatch):
    seen_sessions = []

    def acquire(_root, requested_session, *_args, **_kwargs):
        seen_sessions.append(requested_session)
        return _acquired(tmp_path, requested_session)

    record = _run(
        tmp_path,
        monkeypatch,
        now=datetime(2026, 8, 30, 18, 5, tzinfo=VN_TZ),
        working=_working_dates("2026-08-31", "2026-09-01"),
        acquire_fn=acquire,
    )
    assert record["phase_a"]["status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert seen_sessions == [SESSION]


def test_stale_prior_session_response_fails(tmp_path, monkeypatch):
    def acquire(*a, **k):
        return _acquired(tmp_path, "2026-08-21", requested_at="2026-08-21T19:19:00+07:00")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, acquire_fn=acquire)
    assert exc.value.stage == cdo.STAGE_BLOCKED_POST_ACQUISITION


def test_future_explicit_session_fails(tmp_path, monkeypatch):
    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, now=AFTER, session="2026-08-27")
    assert exc.value.stage == cdo.STAGE_FUTURE_SESSION


def test_weekend_fails(tmp_path, monkeypatch):
    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        cdo.run_canonical_daily_operation(
            tmp_path, tmp_path / "runtime", "2026-08-29",
            now=datetime(2026, 8, 29, 18, 5, tzinfo=VN_TZ),
            working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
            acquire_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no acquire")),
            out_dir=tmp_path / "ops",
        )
    assert exc.value.stage == cdo.STAGE_NON_WORKING_DATE


def test_holiday_in_observed_window_fails(tmp_path, monkeypatch):
    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        cdo.run_canonical_daily_operation(
            tmp_path, tmp_path / "runtime", "2026-09-02",
            now=datetime(2026, 9, 2, 18, 5, tzinfo=VN_TZ),
            working_dates_evidence=_working_dates("2026-09-01", "2026-09-03"),
            acquire_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no acquire")),
            out_dir=tmp_path / "ops",
        )
    assert exc.value.stage == cdo.STAGE_NON_WORKING_DATE


def test_provider_evidence_unavailable_fails_precisely(tmp_path, monkeypatch):
    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, working={})
    assert exc.value.stage == cdo.STAGE_PROVIDER_EVIDENCE_UNAVAILABLE


def test_exactly_one_market_wide_acquisition(tmp_path, monkeypatch):
    record = _run(tmp_path, monkeypatch)
    assert record["market_acquisition_attempts"] == 1
    assert record["_calls"]["acquire"] == 1
    assert record["market_acquisition_owner"] == cdo.MARKET_ACQUISITION_OWNER


def test_no_duplicate_capability_first_and_canonical_collection():
    source = inspect.getsource(cdo)
    assert "import collect_market_evidence" not in source
    assert "from tools import collect_market_evidence" not in source
    assert "run_capability_first_eod_operation" not in inspect.getsource(cdo.run_canonical_daily_operation)
    assert cdo.MARKET_ACQUISITION_OWNER == "canonical_p3f9b_exact_session"


def test_canonical_path_never_falls_back_to_legacy_provider_pipeline():
    assert "vn_stock_pipeline.py" not in inspect.getsource(cdo.run_canonical_daily_operation)


def test_registration_only_after_phase_b(tmp_path, monkeypatch):
    order = []
    _patch_downstream(monkeypatch, tmp_path)
    monkeypatch.setattr(cdo, "register_session_inputs", lambda *a, **k: order.append("register") or {"status": "REGISTERED"})
    monkeypatch.setattr(cdo, "validate_and_freeze_completed_session", lambda *a, **k: order.append("freeze") or {"status": "FROZEN"})

    def acquire(*a, **k):
        order.append("acquire")
        return _acquired(tmp_path)

    runtime = tmp_path / "runtime"
    _write_runtime(runtime, SESSION)
    cdo.run_canonical_daily_operation(
        tmp_path, runtime, SESSION, now=POST_CLOSE,
        working_dates_evidence=_working_dates(SESSION),
        acquire_fn=acquire,
        producer_fn=lambda *a, **k: order.append("producer") or _producer(tmp_path),
        runtime_fn=lambda *a, **k: {"session": SESSION},
        trusted_fn=lambda *a, **k: {"session": SESSION, "trusted_subset_ready": True},
        out_dir=tmp_path / "ops",
    )
    assert order.index("acquire") < order.index("register")
    assert order.index("register") < order.index("producer")


def test_daily_producer_failure_skips_runtime_and_publication(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise DailyProducerError("PRODUCER_BROKEN")

    def runtime_forbidden(*a, **k):
        raise AssertionError("runtime_must_not_run")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, producer_fn=boom, runtime_fn=runtime_forbidden, complete_publication=True)
    assert exc.value.stage == cdo.STAGE_BLOCKED_DAILY_PRODUCER


def test_runtime_failure_skips_trusted_and_publication(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise CanonicalRuntimeReleaseError("RUNTIME_BROKEN")

    def trusted_forbidden(*a, **k):
        raise AssertionError("trusted_must_not_run")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, runtime_fn=boom, trusted_fn=trusted_forbidden, complete_publication=True)
    assert exc.value.stage == cdo.STAGE_BLOCKED_RUNTIME_RELEASE


def test_trusted_failure_skips_publication(tmp_path, monkeypatch):
    pubs = []

    def boom(*a, **k):
        raise CanonicalTrustedSubsetError("TRUSTED_BROKEN")

    def pub(argv):
        pubs.append(argv)
        raise AssertionError("publication_must_not_run")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, trusted_fn=boom, complete_publication=True, publication_runner=pub)
    assert exc.value.stage == cdo.STAGE_BLOCKED_TRUSTED_SUBSET
    assert pubs == []


def test_runtime_trusted_producer_session_mismatch_fails_closed(tmp_path, monkeypatch):
    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(
            tmp_path, monkeypatch,
            trusted_fn=lambda *a, **k: {"session": "2026-08-25", "trusted_subset_ready": True},
        )
    assert exc.value.stage in {cdo.STAGE_BLOCKED_TRUSTED_SUBSET, cdo.STAGE_BLOCKED_SESSION_IDENTITY}


def test_publication_called_only_as_release_orchestrator_complete_publication(tmp_path, monkeypatch):
    record = _run(tmp_path, monkeypatch, complete_publication=True)
    argv = record["_calls"]["publication"][0]
    assert argv[0] == "all"
    assert "--live" in argv
    assert "--complete-publication" in argv
    assert "--expected-session" in argv
    assert SESSION in argv
    assert record["daily_operation_state"] == cdo.STATE_PUBLISHED


def test_publication_failure_retains_recoverable_local_state(tmp_path, monkeypatch):
    def pub(argv):
        raise PublicationCompletionError("BLOCKED_PUBLIC_BYTE_PROOF", "public byte missing")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, complete_publication=True, publication_runner=pub)
    assert exc.value.stage.startswith("BLOCKED_PUBLICATION_")
    assert exc.value.local_state.get("runtime_release")
    assert exc.value.local_state.get("trusted_subset", {}).get("ready") is True


def test_success_fixture_reaches_published(tmp_path, monkeypatch):
    record = _run(tmp_path, monkeypatch, complete_publication=True)
    assert record["daily_operation_state"] == "PUBLISHED"
    assert record["session"] == SESSION
    assert record["session_gate"] == "EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR"
    assert record["daily_producer_status"] == "COMPLETED"
    assert record["runtime_release_status"] == "READY"
    assert record["trusted_subset_status"] == "READY"
    assert record["publication"]["dashboard_ci_status"] == "SUCCESS"
    assert record["publication"]["deploy_pages_status"] == "SUCCESS"
    assert record["publication"]["public_byte_identity"] == "PASS"


def test_idempotent_replay_creates_no_duplicate_semantic_operation(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch, complete_publication=True)
    second = _run(tmp_path, monkeypatch, complete_publication=True)
    assert first["operation_identity"] == second["operation_identity"]
    assert second["is_idempotent_replay"] is True


def test_tampered_retained_artifact_fails(tmp_path, monkeypatch):
    def acquire(*a, **k):
        payload = _acquired(tmp_path, SESSION)
        payload["snapshot"]["snapshot_identity"] = "p3f9_exact_session_snapshot:tampered"
        return payload

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, acquire_fn=acquire)
    assert exc.value.stage == cdo.STAGE_BLOCKED_POST_ACQUISITION


def test_no_sleep_poll_or_background_loops():
    source = inspect.getsource(cdo)
    assert "sleep(" not in source
    assert "time.sleep" not in source
    assert "BackgroundScheduler" not in source
    assert "sched." not in source
    assert inspect.getsource(cdo.run_canonical_daily_operation).count("while ") == 0


def test_no_new_provider_and_no_authority_changes(tmp_path, monkeypatch):
    record = _run(tmp_path, monkeypatch, complete_publication=True)
    source = inspect.getsource(cdo)
    assert "eodhd" not in source.lower()
    assert record["authority_effect"] == "NONE"
    bounds = record["authority_boundaries"]
    assert bounds["raw_as_traded_promoted"] is False
    assert bounds["pit_backtest_eligible"] is False
    assert bounds["liquidity_sizing_authority"] == "BLOCKED"
    assert bounds["valuation_authority"] is False
    assert bounds["recommendation_authority"] is False
    blob = json.dumps(record["authority_boundaries"])
    assert "TARGET_PRICE" not in blob
    assert "PROBABILITY" not in blob


def test_cli_complete_publication_requires_canonical_flag(capsys, tmp_path):
    import daily_analysis_pipeline as dap
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    rc = dap.main(["--runtime-root", str(runtime), "--complete-publication"])
    assert rc == 2
    assert "requires --canonical-post-close" in capsys.readouterr().err


def test_contradictory_pre_acquisition_evidence_blocks_before_acquire(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("acquisition_must_not_run")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(
            tmp_path, monkeypatch,
            exact=_p3f9b("2026-08-21", requested_at="2026-08-21T19:19:00+07:00"),
            acquire_fn=forbidden,
        )
    assert exc.value.stage == cdo.STAGE_BLOCKED_PRE_ACQUISITION


def test_isolated_2026_08_26_full_replay_reaches_published_without_dispatch(tmp_path, monkeypatch):
    """Retained 26/8 evidence -> Phase B -> runtime -> trusted -> read-only publication reuse."""
    from tests.test_governed_publication_completion import (
        FakeGh, FakeGit, PUBLIC_LINE, CI_ID, PAGES_ID, CANONICAL_ORIGIN,
    )
    import governed_publication_completion as gpc
    import canonical_dashboard_runtime_release as runtime_release
    import canonical_trusted_subset_release as trusted

    scaleout = (
        ROOT / "operations-review" / "canonical-post-close-v1" / SESSION
        / "post-close-attempt-191900" / "operations-review"
        / "p3f9b-market-wide-exact-session-scaleout-20260826"
        / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
    )
    envelope = json.loads(scaleout.read_text(encoding="utf-8"))
    snapshot = _p3f9b(
        SESSION,
        requested_at=str(envelope["resolved_session"]["execution_timestamp"]),
        exact=int(envelope["exact_session_coverage"]["exact_session_observed_count"]),
        total=int(envelope["exact_session_coverage"]["attempted_candidate_count"]),
    )
    acquire_calls = []

    def acquire(*a, **k):
        acquire_calls.append(1)
        return {
            "snapshot": snapshot,
            "resolved_completed_session": SESSION,
            "coverage": {
                "exact_session_retained_count": snapshot["exact_session_observed_count"],
                "total_candidates": snapshot["attempted_candidate_count"],
                "ratio": snapshot["exact_session_observed_count"] / snapshot["attempted_candidate_count"],
            },
            "artifact_root": ROOT,
            "eligibility": {"reused_existing_eligible_artifact": True, "redirected": False},
            "paths": {},
            "triage_status": {},
        }

    runtime = tmp_path / "runtime"
    src_bctc = ROOT / "data_bctc"
    if src_bctc.is_dir():
        shutil.copytree(src_bctc, runtime / "data_bctc")

    def runtime_mat(root, runtime_root, session):
        return runtime_release.materialize_canonical_runtime_release(ROOT, runtime_root, session)

    def trusted_mat(producer_root, runtime_root, session, **kwargs):
        return trusted.materialize_canonical_trusted_subset(
            ROOT, runtime_root, session, consumer_root=kwargs.get("consumer_root") or ROOT.parent / "ai-core-private",
        )

    gh = FakeGh()
    gh.ci_runs = [{
        "databaseId": CI_ID, "headSha": SOURCE_SHA, "status": "completed", "conclusion": "success",
        "name": "Dashboard CI", "workflowName": "Dashboard CI", "event": "workflow_dispatch",
        "headBranch": "main", "url": f"https://github.com/example/actions/runs/{CI_ID}",
        "displayTitle": "Dashboard CI", "createdAt": "2026-08-26T12:00:00Z", "number": 1,
    }]
    gh.pages_runs = [{
        "databaseId": PAGES_ID, "headSha": "691b63dedec8625bfab7f6b126d8928a2184abf4",
        "status": "completed", "conclusion": "success", "name": "Deploy Pages",
        "workflowName": "Deploy Pages", "event": "workflow_dispatch", "headBranch": "main",
        "url": f"https://github.com/example/actions/runs/{PAGES_ID}",
        "displayTitle": "Deploy Pages", "createdAt": "2026-08-26T12:10:00Z", "number": 2,
    }]
    gh.logs[PAGES_ID] = PUBLIC_LINE
    git = FakeGit(head=SOURCE_SHA, origin_main=SOURCE_SHA, origin_url=CANONICAL_ORIGIN)
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(web_dir.resolve()))
    monkeypatch.setattr(gpc, "which_gh", lambda: "gh")

    def publication_runner(argv):
        assert argv[0] == "all"
        assert "--complete-publication" in argv
        assert "--live" in argv
        assert SESSION in argv
        return gpc.complete_publication(
            web_dir=web_dir,
            expected_session=SESSION,
            producer_root=tmp_path,
            release_source_sha=SOURCE_SHA,
            require_identical_main=True,
            allow_dispatch=False,
            runner=gh,
            git_runner=git,
            watch_timeout=5,
        )

    def forbidden_net(*a, **k):
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden_net)
    _patch_downstream(monkeypatch, tmp_path)
    monkeypatch.setattr(cdo, "register_session_inputs", lambda *a, **k: {"status": "ALREADY_FROZEN_IDENTICAL"})
    monkeypatch.setattr(cdo, "validate_and_freeze_completed_session", lambda *a, **k: {"status": "ALREADY_COMPLETED"})

    record = cdo.run_canonical_daily_operation(
        tmp_path, runtime, SESSION, now=POST_CLOSE,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        complete_publication=True,
        acquire_fn=acquire,
        producer_fn=lambda *a, **k: _producer(tmp_path, SESSION),
        runtime_fn=runtime_mat,
        trusted_fn=trusted_mat,
        publication_runner=publication_runner,
        out_dir=tmp_path / "operations-review",
        consumer_root=ROOT.parent / "ai-core-private",
    )
    assert record["daily_operation_state"] == "PUBLISHED"
    assert record["phase_b"]["status"] == gate.STATUS_READY
    assert record["session"] == SESSION
    assert record["runtime_release_status"] == "READY"
    assert record["trusted_subset_status"] == "READY"
    assert record["publication"]["ci_reused"] is True
    assert record["publication"]["pages_reused"] is True
    assert gh.ci_dispatch_count == 0
    assert gh.pages_dispatch_count == 0
    assert len(acquire_calls) == 1
    assert record["capability_first_collector_invoked"] is False
    assert record["publication"]["public_byte_identity"] == "PASS"
    assert record["publication"]["release_source_sha"] == SOURCE_SHA
