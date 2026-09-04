import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import daily_session_level2_package as level2
from daily_research_session_operations import load_registry
from daily_session_level2_package import (
    BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
    EXACT_SESSION_CLEAN,
    UNAVAILABLE_REQUIRED_INPUT,
    build_tactical_current_session_signal,
    classify_level2_components,
    evaluate_canonical_daily_producer,
    resolve_level2_session,
    session_triage_status,
    write_level2_package,
)
from vn_time import VN_TZ

ROOT = Path(__file__).resolve().parents[1]
NAMED_TRIAGE = ROOT / "operations-review/full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prime_materialization_outputs(paths: dict[str, Path]) -> None:
    for key in (
        "breadth_foundation", "universe_resolution", "liquidity_research", "technical_recovery",
        "descriptive_research", "screening_foundation", "tactical_classifier",
        "corporate_intelligence", "valuation", "sector_leadership", "peer_relative",
        "risk_register", "technical_coverage_disposition",
    ):
        _write_json(paths[key], {})


def test_run_cmd_executes_relative_tool_from_explicit_execution_root(tmp_path):
    execution_root = tmp_path / "producer"
    execution_root.mkdir()
    with patch.object(level2.subprocess, "run") as mocked:
        level2.run_cmd(execution_root, ["tools/example.py", "--flag"])
    assert mocked.call_args.args[0] == [sys.executable, "tools/example.py", "--flag"]
    assert mocked.call_args.kwargs["cwd"] == str(execution_root)
    assert mocked.call_args.kwargs["check"] is True


def _patch_resolved_acquisition(session: str, *, resolved_session: str | None = None, monkeypatch_target="patch"):
    """Shared fake for the DNSE-Pass-1 + multi-source-resolver chain
    ensure_exact_session_snapshot() now runs in-process. Returns the context managers
    plus a `calls` list recording (dnse_candidates, resolver_target_session) so callers
    can assert on what was actually invoked, mirroring the old fake_run() pattern this
    replaces.
    """
    import dnse_access
    import dnse_secrets_env
    import multi_source_exact_session_resolver as resolver
    import mva_exact_session_snapshot as snapshotter

    calls: list[dict] = []
    resolved_session = resolved_session or session

    def fake_canonical_candidates(runtime_root):
        return ["AAA", "BBB"]

    def fake_ensure_credentials_loaded(*a, **k):
        return {"configured": True}

    def fake_credentials_for_request(*a, **k):
        return ("key", "secret")

    def fake_materialize_snapshot(*, candidates, requested_at, target_session, api_key, api_secret, workers=8, **kw):
        calls.append({"stage": "dnse", "candidates": candidates, "target_session": target_session})
        return {
            "contract_version": "p3f9_exact_session_mva_snapshot/v2",
            "resolved_completed_session": resolved_session, "retained_snapshot_session": resolved_session,
            "requested_at": requested_at.isoformat(), "target_session": target_session,
            "candidate_count": len(candidates), "attempted_candidate_count": len(candidates),
            "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
            "unattempted_without_explicit_disposition": 0,
            "source": {"provider": "DNSE"},
            "authority_boundary": {"RAW_AS_TRADED": "NOT_PROMOTED", "HISTORICAL_PIT": "BLOCKED", "runtime_database_mutated": False},
            "records": {t: {"status": "OBSERVED", "reason": None, "disposition": "EXACT_SESSION_RETAINED",
                            "observations": [{"session": resolved_session, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
                                              "provider": "DNSE", "dataset": "DNSE_OHLC_1D"}],
                            "payload_hash": "h", "request": {}, "provider_endpoint": "/price/ohlc"} for t in candidates},
            "snapshot_sha256": "x", "snapshot_identity": "p3f9_exact_session_snapshot:x",
        }

    def fake_resolve(*, dnse_snapshot, target_session, requested_at, **kw):
        calls.append({"stage": "resolver", "target_session": target_session})
        projected = dict(dnse_snapshot)
        projected["resolved_completed_session"] = resolved_session
        return {"evidence": True}, projected

    patches = [
        patch.object(snapshotter, "canonical_candidates", fake_canonical_candidates),
        patch.object(dnse_secrets_env, "ensure_credentials_loaded", fake_ensure_credentials_loaded),
        patch.object(dnse_access, "credentials_for_request", fake_credentials_for_request),
        patch.object(snapshotter, "materialize_snapshot", fake_materialize_snapshot),
        patch.object(resolver, "resolve_multi_source_exact_session_snapshot", fake_resolve),
    ]
    return patches, calls


def test_ensure_exact_session_snapshot_runs_dnse_then_resolver_and_returns_the_path(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    patches, calls = _patch_resolved_acquisition(session)

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    assert result == paths["exact_session_snapshot"]
    assert [c["stage"] for c in calls] == ["dnse", "resolver"]
    assert calls[0]["target_session"] == session
    assert calls[1]["target_session"] == session
    # The resolved projection landed at the same path every existing Level-2 consumer reads.
    written = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert written["resolved_completed_session"] == session
    # DNSE Pass 1's own unmodified output is retained as a standalone diagnostic artifact.
    dnse_only = json.loads(paths["dnse_only_exact_session_snapshot"].read_text(encoding="utf-8"))
    assert dnse_only["resolved_completed_session"] == session


def test_ensure_exact_session_snapshot_is_idempotent_when_already_present(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})

    with patch.object(level2, "run_cmd") as mocked:
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    mocked.assert_not_called()
    assert result == paths["exact_session_snapshot"]


def test_ensure_exact_session_snapshot_is_idempotent_when_companion_evidence_is_healthy(tmp_path):
    """An existing snapshot with companion evidence showing a NON-degraded sentinel verdict is
    reused exactly like a bare snapshot with no companion evidence at all."""
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})
    _write_json(paths["multi_source_market_evidence"], {
        "dnse_quality_sentinel": {"health": {"state": "DNSE_EXACT_AND_CORROBORATED"}},
    })

    with patch.object(level2, "run_cmd") as mocked:
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    mocked.assert_not_called()
    assert result == paths["exact_session_snapshot"]


def test_ensure_exact_session_snapshot_refuses_to_reuse_unresolved_degraded_existing_snapshot(tmp_path):
    """MANDATORY regression test (P0 DEFECT 2): the exact idempotency-escape shape this corrective
    milestone closes. A canonical snapshot exists at the default path (as the pre-corrective code
    would have written it, BEFORE ever checking DNSE provider health) whose companion evidence
    proves DNSE_BROAD_STALE_OR_INCOMPLETE_EOD was found for this session, but the snapshot itself
    carries no completed degraded-provider-recovery marker (because the code that wrote it never
    ran degraded-provider recovery, or predates this milestone entirely). A rerun must NOT silently
    reuse it -- it must refuse loudly rather than let a contaminated session proceed.
    """
    session = "2026-09-03"
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_json(paths["exact_session_snapshot"], {
        "resolved_completed_session": session,
        "exact_session_observed_count": 772,
        "attempted_candidate_count": 1683,
        # No "degraded_provider_recovery" key at all -- exactly what pre-corrective code (or a
        # write that crashed/stopped before the wrapper could stamp it) would have produced.
    })
    _write_json(paths["multi_source_market_evidence"], {
        "dnse_quality_sentinel": {
            "health": {"state": "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD", "conflict_count": 18, "dnse_assessed_count": 18},
        },
    })

    with patch.object(level2, "run_cmd") as mocked:
        with pytest.raises(ValueError, match="P3F9B_EXISTING_SNAPSHOT_PROVIDER_HEALTH_GATE_UNRESOLVED"):
            level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    mocked.assert_not_called()
    # Old bytes are never touched by this refusal -- still exactly what was written above.
    retained = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert retained["exact_session_observed_count"] == 772


def test_ensure_exact_session_snapshot_reuses_degraded_snapshot_once_recovery_completed(tmp_path):
    """The corrected policy DOES still allow idempotent reuse of a degraded day once it was
    genuinely, honestly resolved via DEGRADED_PROVIDER_RECOVERY_MODE this run or a prior one --
    the gate is about whether recovery ran to completion, never about whether DNSE happened to be
    healthy."""
    session = "2026-09-03"
    paths = level2.session_artifact_paths(tmp_path, session)
    _write_json(paths["exact_session_snapshot"], {
        "resolved_completed_session": session,
        "degraded_provider_recovery": {"mode": "COMPLETED", "expanded_ticker_count": 0},
    })
    _write_json(paths["multi_source_market_evidence"], {
        "dnse_quality_sentinel": {"health": {"state": "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD", "conflict_count": 18}},
    })

    with patch.object(level2, "run_cmd") as mocked:
        result = level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    mocked.assert_not_called()
    assert result == paths["exact_session_snapshot"]


def test_ensure_exact_session_snapshot_raises_on_session_mismatch(tmp_path):
    session = "2026-08-26"
    patches, _ = _patch_resolved_acquisition(session, resolved_session="2026-08-25")

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with pytest.raises(ValueError, match="P3F9B_ACQUIRED_SESSION_MISMATCH:requested=2026-08-26:resolved=2026-08-25"):
            level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")


def test_materialize_independent_components_delegates_snapshot_acquisition_to_the_helper(tmp_path):
    # Backward-compatibility contract: a standalone materialize_independent_components() caller
    # (any pre-existing caller that never adopted ensure_exact_session_snapshot directly) must
    # still get exactly the same acquisition behaviour through the extracted helper.
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    calls = []

    def fake_ensure(artifact_root, sess, runtime_root, workers, now, *, execution_root=None):
        calls.append((artifact_root, sess, execution_root))
        _write_json(paths["exact_session_snapshot"], {"resolved_completed_session": session})
        return paths["exact_session_snapshot"]

    _prime_materialization_outputs(paths)
    with patch.object(level2, "ensure_exact_session_snapshot", fake_ensure), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    assert calls == [(tmp_path, session, tmp_path)]


def test_materialization_separates_attempt_artifact_root_from_execution_root(tmp_path):
    # ensure_exact_session_snapshot's DNSE+resolver acquisition (2026-09-03 rewrite) writes
    # directly to absolute artifact_root paths -- it no longer shells out via run_cmd/execution_root
    # at all, so this test now asserts the acquisition OUTPUT lands under attempt_root regardless
    # of execution_root, and that every remaining (already-primed) step still never touches run_cmd.
    session = "2026-08-26"
    attempt_root = tmp_path / "operations-review" / "canonical-post-close-v1" / session / "post-close-attempt-190500"
    paths = level2.session_artifact_paths(attempt_root, session)
    _prime_materialization_outputs(paths)
    patches, calls = _patch_resolved_acquisition(session)

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch.object(level2, "run_cmd") as mocked_run_cmd, \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"):
        level2.materialize_independent_components(
            attempt_root,
            session,
            tmp_path / "runtime",
            execution_root=ROOT,
        )

    mocked_run_cmd.assert_not_called()
    assert [c["stage"] for c in calls] == ["dnse", "resolver"]
    written = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert written["resolved_completed_session"] == session
    assert str(attempt_root) in str(paths["exact_session_snapshot"])


def test_ordinary_materialization_keeps_its_single_root_as_execution_root(tmp_path):
    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    _prime_materialization_outputs(paths)
    patches, calls = _patch_resolved_acquisition(session)

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch.object(level2, "run_cmd") as mocked_run_cmd, \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    mocked_run_cmd.assert_not_called()
    written = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert written["resolved_completed_session"] == session


def test_named_20260824_triage_file_is_2026_08_21_session():
    import json
    artifact = json.loads(NAMED_TRIAGE.read_text(encoding="utf-8"))
    assert artifact["source_market_session"] == "2026-08-21"
    assert artifact["artifact_identity"].startswith("full_universe_entry_candidate_triage:4b527330")


def test_2026_08_25_has_authorized_exact_session_triage():
    registry = load_registry(ROOT)
    status = session_triage_status(ROOT, "2026-08-25", registry)
    assert status["status"] == EXACT_SESSION_CLEAN
    assert status["source_session"] == "2026-08-25"
    assert status["identity"].startswith("full_universe_entry_candidate_triage:97d80cf0")


def test_latest_completed_after_close_on_trading_day():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session(None, now=now)
    assert resolved["session"] == "2026-08-25"
    assert resolved["resolution_mode"] == "LATEST_COMPLETED_WORKING_DATE"


def test_latest_completed_morning_before_session_completes():
    now = datetime(2026, 8, 25, 9, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session("latest-completed", now=now)
    assert resolved["session"] == "2026-08-24"


def test_latest_completed_weekend_is_prior_friday():
    saturday = datetime(2026, 8, 22, 16, 0, tzinfo=VN_TZ)
    sunday = datetime(2026, 8, 23, 10, 0, tzinfo=VN_TZ)
    assert resolve_level2_session(None, now=saturday)["session"] == "2026-08-21"
    assert resolve_level2_session(None, now=sunday)["session"] == "2026-08-21"


def test_explicit_historical_session_is_not_overridden_by_clock():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=VN_TZ)
    resolved = resolve_level2_session("2026-08-21", now=now)
    assert resolved["session"] == "2026-08-21"
    assert resolved["resolution_mode"] == "EXPLICIT_SESSION"


def test_canonical_2026_08_25_is_eligible_without_fake_outputs():
    now = datetime(2026, 8, 26, 16, 0, tzinfo=VN_TZ)
    status = evaluate_canonical_daily_producer(ROOT, "2026-08-25", now=now)
    assert status["canonical_daily_producer_status"] == "ELIGIBLE_NOT_EXECUTED_BY_LEVEL2"
    assert status["fake_canonical_outputs_written"] is False
    assert status["root_blocker"] is None


def test_tactical_signal_is_distinct_from_opportunity_prioritization():
    tactical = {
        "session": "2026-08-25",
        "artifact_identity": "watchlist_tactical_entry_classifier:test",
        "coverage": {
            "classified_count": 3,
            "entry_state_counts": {"BREAKOUT_READY": 1, "UPTREND_CONFIRMED": 1, "BASE_BUILDING": 1},
            "entry_action_counts": {"BUY_ON_CONFIRMATION": 1, "WAIT": 1, "ACCUMULATE_IN_BASE": 1},
        },
        "records": {
            "AAA": {"entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION"},
            "BBB": {"entry_state": "UPTREND_CONFIRMED", "entry_action": "WAIT"},
            "CCC": {"entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE_IN_BASE"},
        },
    }
    signal = build_tactical_current_session_signal(tactical, "2026-08-25")
    assert signal["signal_class"] == "TACTICAL_CURRENT_SESSION_SIGNAL"
    assert signal["full_opportunity_prioritization"] == "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE"
    assert signal["selective_tactical_states"]["BREAKOUT_READY"]["tickers"] == ["AAA"]
    assert "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE" in signal["blocked_claims"]


def test_stale_scenario_is_not_advertised_exact_session_clean(tmp_path):
    root = tmp_path
    ops = root / "operations-review"
    session = "2026-08-25"
    nodash = "20260825"
    (ops / f"current-evidence-bound-scenario-v1-{nodash}").mkdir(parents=True)
    (ops / "full-universe-entry-candidate-triage-20260824").mkdir(parents=True)
    (root / "config").mkdir()
    registry = {
        "schema_version": "1.0.0",
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {
            "2026-08-21": {
                "status": "COMPLETED_RETAINED_EVIDENCE",
                "trading_day_valid": True,
                "frozen_input_identities": {"triage": "full_universe_entry_candidate_triage:stale21"},
            }
        },
        "sessions": {
            "2026-08-21": {
                "descriptive": {"path": "x", "artifact_identity": "d"},
                "screening": {"path": "x", "artifact_identity": "s"},
                "tactical": {"path": "x", "artifact_identity": "t"},
                "triage": {"path": "operations-review/full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json", "artifact_identity": "full_universe_entry_candidate_triage:stale21"},
                "fundamental": {"path": "x", "artifact_identity": "f"},
                "valuation": {"path": "x", "artifact_identity": "v"},
                "catalyst": {"path": "x", "artifact_identity": "c"},
                "corporate_intelligence": {"path": "x", "artifact_identity": "ci"},
            }
        },
    }
    (root / "config" / "daily_research_session_input_registry.json").write_text(
        __import__("json").dumps(registry), encoding="utf-8"
    )
    triage = {
        "artifact_identity": "full_universe_entry_candidate_triage:stale21",
        "source_market_session": "2026-08-21",
    }
    (ops / "full-universe-entry-candidate-triage-20260824" / "full_universe_entry_candidate_triage_20260824.json").write_text(
        __import__("json").dumps(triage), encoding="utf-8"
    )
    scenario = {
        "artifact_identity": "current_evidence_bound_scenario:contaminated",
        "session": "2026-08-25",
        "source_artifact_identities": {"triage": "full_universe_entry_candidate_triage:stale21"},
        "records": {},
    }
    (ops / f"current-evidence-bound-scenario-v1-{nodash}" / "current_evidence_bound_scenario_artifact.json").write_text(
        __import__("json").dumps(scenario), encoding="utf-8"
    )
    snapshot = {
        "snapshot_identity": "p3f9_exact_session_snapshot:sess",
        "resolved_completed_session": session,
        "records": {},
    }
    snap_dir = ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}"
    snap_dir.mkdir(parents=True)
    (snap_dir / "p3f9b_mva_exact_session_snapshot.json").write_text(__import__("json").dumps(snapshot), encoding="utf-8")
    tactical = {
        "artifact_identity": "watchlist_tactical_entry_classifier:clean",
        "session": session,
        "coverage": {"classified_count": 1, "entry_state_counts": {"BREAKOUT_READY": 1}, "entry_action_counts": {"BUY_ON_CONFIRMATION": 1}},
        "records": {"AAA": {"entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION"}},
    }
    tac_dir = ops / f"watchlist-tactical-entry-decision-v1-{nodash}"
    tac_dir.mkdir(parents=True)
    (tac_dir / "watchlist_tactical_entry_classifier_artifact.json").write_text(__import__("json").dumps(tactical), encoding="utf-8")

    classification = classify_level2_components(root, session)
    by_id = {row["component_id"]: row for row in classification["components"]}
    assert by_id["current_evidence_bound_scenario"]["exact_session_vs_reusable_context_status"] == BLOCKED_BY_STALE_TRIAGE_DEPENDENCY
    assert by_id["current_evidence_bound_scenario"]["advertised_as_exact_session_clean"] is False
    assert by_id["current_opportunity_prioritization"]["exact_session_vs_reusable_context_status"] == BLOCKED_BY_STALE_TRIAGE_DEPENDENCY
    assert by_id["tactical_classifier"]["exact_session_vs_reusable_context_status"] == EXACT_SESSION_CLEAN
    assert classification["tactical_current_session_signal"]["status"] == "AVAILABLE"
    assert classification["stale_triage_dependency_trace"]["stale_triage_used_by_scenario"]["source_session"] == "2026-08-21"
    assert "PRIORITY" not in " ".join(by_id["tactical_classifier"]["allowed_claims"])

    canonical = evaluate_canonical_daily_producer(root, session, now=datetime(2026, 8, 25, 16, tzinfo=VN_TZ))
    resolution = resolve_level2_session(session, now=datetime(2026, 8, 25, 16, tzinfo=VN_TZ))
    written = write_level2_package(root, session, classification=classification, canonical=canonical, resolution=resolution)
    manifest = __import__("json").loads(written["manifest"].read_text(encoding="utf-8"))
    brief = written["brief"].read_text(encoding="utf-8")
    assert manifest["canonical_daily_producer_status"] == "BLOCKED"
    assert manifest["canonical_producer_status"]["root_blocker"] == "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"
    assert manifest["canonical_producer_status"]["fake_canonical_outputs_written"] is False
    scenario_row = next(c for c in manifest["components"] if c["component_id"] == "current_evidence_bound_scenario")
    assert scenario_row["advertised_as_exact_session_clean"] is False
    assert "FULL_OPPORTUNITY_PRIORITIZATION" in " ".join(manifest["governed_claims"]["blocked_claims"])
    assert brief.startswith("# Stock Lookup")
    assert "CANONICAL DAILY PRODUCER: BLOCKED" in brief
    assert "BLOCKER: REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE" in brief
    assert "CURRENT-SESSION ANALYSIS STILL AVAILABLE: YES" in brief
    assert "## CURRENT-SESSION CLEAN COMPONENTS" in brief
    assert "## PRIOR-AS-OF CONTEXT" in brief
    assert "## UNAVAILABLE / TRIAGE-DEPENDENT COMPONENTS" in brief
    assert "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE" in brief
    assert "TACTICAL_CURRENT_SESSION_SIGNAL" in brief
    producer_dir = root / "operations-review" / "daily-producer-runs-v1"
    assert not producer_dir.exists()
