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


def test_ensure_exact_session_snapshot_stamps_recovery_eligibility_and_stays_self_consistent(tmp_path):
    """DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1 (2026-09-04): the projected snapshot must
    carry the new current-equity coverage/sentinel-decision fields, and its own hash must still
    verify against its full final payload (the fields are added AFTER _project_to_p3f9_shape's
    own hash stamp, so ensure_exact_session_snapshot must re-stamp it)."""
    from field_temporal_contract import stable_id

    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    patches, _ = _patch_resolved_acquisition(session)

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    written = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert "recovery_eligibility" in written
    assert "residual_gap_sentinel_decision" in written
    # Self-consistency: recomputing the hash over everything except the two identity fields
    # must reproduce the recorded snapshot_sha256 -- the real (non-test-double) verification
    # every consumer (e.g. current_universe_status_and_session_coverage_resolution) performs.
    payload = {k: v for k, v in written.items() if k not in {"snapshot_sha256", "snapshot_identity"}}
    assert written["snapshot_sha256"] == stable_id(payload)
    assert written["snapshot_identity"] == f"p3f9_exact_session_snapshot:{written['snapshot_sha256']}"


def test_ensure_exact_session_snapshot_retains_runtime_budget_abort_not_partial_projection(tmp_path):
    """A forecast abort is immutable diagnostic evidence, never a plausibly reusable snapshot."""
    import multi_source_exact_session_resolver as resolver

    session = "2026-08-26"
    paths = level2.session_artifact_paths(tmp_path, session)
    patches, _ = _patch_resolved_acquisition(session)
    diagnostic = {
        "stage": "DNSE_GAP_RECOVERY_VCI_FIRST",
        "projected_total_seconds": 8_000.0,
        "runtime_budget_seconds": 2_700.0,
        "request_count": 5,
        "providers": {},
    }
    with patches[0], patches[1], patches[2], patches[3], \
         patch.object(resolver, "resolve_exact_session_with_autorecovery",
                      side_effect=resolver.DailyRecoveryRuntimeBudgetExceeded(diagnostic)):
        with pytest.raises(ValueError, match="P3F9B_DAILY_RECOVERY_RUNTIME_BUDGET_EXCEEDED"):
            level2.ensure_exact_session_snapshot(tmp_path, session, tmp_path / "runtime")

    assert paths["dnse_only_exact_session_snapshot"].is_file()
    assert not paths["exact_session_snapshot"].exists()
    abort = json.loads(paths["multi_source_recovery_abort"].read_text(encoding="utf-8"))
    assert abort["reason"] == "DAILY_RECOVERY_RUNTIME_BUDGET_EXCEEDED"
    assert abort["throughput"]["projected_total_seconds"] == 8_000.0
    assert abort["runtime_database_mutated"] is False
    assert abort["abort_identity"].startswith("daily_multi_source_recovery_runtime_budget_abort:")


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
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "resolve_technical_recovery_artifact", return_value={"selected_path": paths["technical_recovery"]}):
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
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "resolve_technical_recovery_artifact", return_value={"selected_path": paths["technical_recovery"]}):
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
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "resolve_technical_recovery_artifact", return_value={"selected_path": paths["technical_recovery"]}):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    mocked_run_cmd.assert_not_called()
    written = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    assert written["resolved_completed_session"] == session


# --- technical_recovery cache-identity validation (materialize_independent_components) --------
#
# daily_session_level2_package.py::materialize_independent_components() used to treat mere file
# existence at paths["technical_recovery"] as proof a cached recovery artifact was safe to hand
# downstream (`if not tech_out.exists(): <regenerate>`). A 2026-09-07 artifact written by the
# pre-fix producer (before 0a0fd2d, "fix(technical): finalize recovery artifact before identity")
# has bytes that no longer match its own stored artifact_sha256, and
# market_wide_current_descriptive_research.build_artifact() correctly rejects that mismatch with
# TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH -- but only after the orchestrator had already
# hardcoded it as this session's technical_recovery input. These tests exercise the fix directly
# at the materialize_independent_components() boundary using the recovery producer's real
# market_wide_current_technical_coverage_scaleout.content_identity() helper (not a re-implementation).


def _independent_component_session_paths(tmp_path, session):
    paths = level2.session_artifact_paths(tmp_path, session)
    for key in (
        "breadth_foundation", "universe_resolution", "liquidity_research",
        "descriptive_research", "screening_foundation", "tactical_classifier",
        "corporate_intelligence", "valuation", "sector_leadership", "peer_relative",
        "risk_register", "technical_coverage_disposition",
    ):
        _write_json(paths[key], {})
    return paths


def _write_valid_p3f9b_snapshot(path: Path, session: str) -> str:
    from field_temporal_contract import stable_id
    payload = {"resolved_completed_session": session, "records": {}}
    payload["snapshot_sha256"] = stable_id(payload)
    payload["snapshot_identity"] = f"p3f9_exact_session_snapshot:{payload['snapshot_sha256']}"
    _write_json(path, payload)
    return payload["snapshot_identity"]


def _valid_technical_recovery_payload(session: str, snapshot_identity: str) -> dict:
    from market_wide_current_technical_coverage_scaleout import content_identity
    payload = {
        "target_session": session,
        "source_lineage": {"p3f9b_snapshot_identity": snapshot_identity},
        "recovered_history_overrides": {},
    }
    payload.update(content_identity(payload))
    return payload


def _stale_technical_recovery_payload(session: str, snapshot_identity: str) -> dict:
    # Mirrors the real 2026-09-07 defect: correct target_session/source_lineage, but an
    # artifact_sha256 stamped before HISTORY_RECOVERY_RUNTIME was merged into the payload, so it
    # no longer reproduces the artifact's own recomputed content hash.
    payload = _valid_technical_recovery_payload(session, snapshot_identity)
    payload["artifact_sha256"] = "0" * 64
    payload["operational_summary"] = {"HISTORY_RECOVERY_RUNTIME": {"attempts": 1}}
    return payload


def _fake_ensure_exact_session_snapshot(paths):
    def fake_ensure(artifact_root, sess, runtime_root, workers, now, *, execution_root=None):
        return paths["exact_session_snapshot"]
    return fake_ensure


def test_retained_technical_resolution_keeps_valid_canonical_path(tmp_path):
    session = "2026-09-07"
    snapshot_identity = "p3f9_exact_session_snapshot:test"
    canonical = tmp_path / "canonical.json"
    _write_json(canonical, _valid_technical_recovery_payload(session, snapshot_identity))

    resolution = level2._resolve_technical_recovery_candidates(
        canonical_path=canonical, replacement_paths=(), session=session,
        p3f9b_snapshot_identity=snapshot_identity, expected_artifact_identity=None,
    )

    assert resolution["status"] == "VALID_EXACT_SESSION_RETAINED_ARTIFACT"
    assert resolution["selected_path"] == canonical
    assert resolution["canonical"]["stored_artifact_sha256"] == resolution["canonical"]["recomputed_artifact_sha256"]
    assert resolution["canonical"]["stored_artifact_identity"] == resolution["canonical"]["recomputed_artifact_identity"]


def test_retained_technical_resolution_selects_only_valid_same_lineage_replacement(tmp_path):
    session = "2026-09-07"
    snapshot_identity = "p3f9_exact_session_snapshot:test"
    canonical = tmp_path / "canonical.json"
    replacement = tmp_path / "canonical-revalidated.json"
    _write_json(canonical, _stale_technical_recovery_payload(session, snapshot_identity))
    replacement_payload = _valid_technical_recovery_payload(session, snapshot_identity)
    _write_json(replacement, replacement_payload)

    resolution = level2._resolve_technical_recovery_candidates(
        canonical_path=canonical, replacement_paths=(replacement,), session=session,
        p3f9b_snapshot_identity=snapshot_identity,
        expected_artifact_identity=replacement_payload["artifact_identity"],
    )

    assert resolution["status"] == "INVALID_RETAINED_ARTIFACT_QUALIFIED_REPLACEMENT"
    assert resolution["selected_path"] == replacement
    assert resolution["canonical"]["reason_code"] == "TECHNICAL_RECOVERY_STORED_HASH_MISMATCH"
    assert resolution["replacements"][0]["stored_artifact_sha256"] == resolution["replacements"][0]["recomputed_artifact_sha256"]
    assert resolution["replacements"][0]["stored_artifact_identity"] == resolution["replacements"][0]["recomputed_artifact_identity"]


def test_retained_technical_resolution_fails_closed_without_qualified_replacement(tmp_path):
    session = "2026-09-07"
    snapshot_identity = "p3f9_exact_session_snapshot:test"
    canonical = tmp_path / "canonical.json"
    _write_json(canonical, _stale_technical_recovery_payload(session, snapshot_identity))

    with pytest.raises(level2.TechnicalRecoveryArtifactResolutionError,
                       match="INVALID_TECHNICAL_RECOVERY_NO_QUALIFIED_REPLACEMENT"):
        level2._resolve_technical_recovery_candidates(
            canonical_path=canonical, replacement_paths=(), session=session,
            p3f9b_snapshot_identity=snapshot_identity, expected_artifact_identity=None,
        )


def test_retained_technical_resolution_fails_closed_for_conflicting_replacements(tmp_path):
    session = "2026-09-07"
    snapshot_identity = "p3f9_exact_session_snapshot:test"
    canonical = tmp_path / "canonical.json"
    first = tmp_path / "first-revalidated.json"
    second = tmp_path / "second-revalidated.json"
    _write_json(canonical, _stale_technical_recovery_payload(session, snapshot_identity))
    _write_json(first, _valid_technical_recovery_payload(session, snapshot_identity))
    conflicting = _valid_technical_recovery_payload(session, snapshot_identity)
    conflicting["recovered_history_overrides"] = {"AAA": {"history": [1]}}
    from market_wide_current_technical_coverage_scaleout import content_identity
    conflicting.update(content_identity(conflicting))
    _write_json(second, conflicting)

    with pytest.raises(level2.TechnicalRecoveryArtifactResolutionError,
                       match="CONFLICTING_QUALIFIED_TECHNICAL_RECOVERY_REPLACEMENTS"):
        level2._resolve_technical_recovery_candidates(
            canonical_path=canonical, replacement_paths=(first, second), session=session,
            p3f9b_snapshot_identity=snapshot_identity, expected_artifact_identity=None,
        )


def test_technical_recovery_cache_reused_when_identity_is_valid(tmp_path):
    session = "2026-09-07"
    paths = _independent_component_session_paths(tmp_path, session)
    snapshot_identity = _write_valid_p3f9b_snapshot(paths["exact_session_snapshot"], session)
    valid_payload = _valid_technical_recovery_payload(session, snapshot_identity)
    _write_json(paths["technical_recovery"], valid_payload)

    with patch.object(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths)), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "run_cmd") as mocked_run_cmd:
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    mocked_run_cmd.assert_not_called()
    assert json.loads(paths["technical_recovery"].read_text(encoding="utf-8")) == valid_payload


def test_technical_recovery_cache_rejected_and_regenerated_when_identity_is_stale(tmp_path):
    session = "2026-09-07"
    paths = _independent_component_session_paths(tmp_path, session)
    snapshot_identity = _write_valid_p3f9b_snapshot(paths["exact_session_snapshot"], session)
    stale_payload = _stale_technical_recovery_payload(session, snapshot_identity)
    _write_json(paths["technical_recovery"], stale_payload)
    original_tech_dir = paths["technical_recovery"].parent
    regenerated_out_dirs = []

    def fake_run_cmd(root, argv):
        assert argv[0] == "tools/run_market_wide_current_technical_coverage_scaleout.py"
        out_dir = Path(argv[argv.index("--out-dir") + 1])
        regenerated_out_dirs.append(out_dir)
        fresh = _valid_technical_recovery_payload(session, snapshot_identity)
        _write_json(out_dir / "market_wide_current_technical_coverage_recovery_artifact.json", fresh)

    with patch.object(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths)), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "run_cmd", side_effect=fake_run_cmd) as mocked_run_cmd:
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    mocked_run_cmd.assert_called_once()
    assert regenerated_out_dirs == [original_tech_dir.parent / f"{original_tech_dir.name}-revalidated"]

    regenerated_path = regenerated_out_dirs[0] / "market_wide_current_technical_coverage_recovery_artifact.json"
    regenerated = json.loads(regenerated_path.read_text(encoding="utf-8"))
    from market_wide_current_descriptive_research import content_identity
    assert regenerated["artifact_sha256"] == content_identity(regenerated)["artifact_sha256"]

    # Downstream descriptive-research must accept the regenerated artifact, using the real,
    # unmodified verifier -- not a relaxed or bypassed one.
    from market_wide_current_descriptive_research import build_artifact
    ur = {"records": {}, "input_candidates": {"resolved_completed_session": session},
          "current_active_equity_denominator": {"count": 1}, "observed_session_cohort": {"count": 0}}
    ur.update(content_identity(ur))
    import market_wide_current_liquidity_research as liquidity_module
    liq = {"records": {}, "resolved_completed_session": session,
           "universe": {"source_snapshot_identity": snapshot_identity}}
    liq.update(liquidity_module.content_identity(liq))
    p3f9b_snapshot = json.loads(paths["exact_session_snapshot"].read_text(encoding="utf-8"))
    artifact = build_artifact(
        universe_resolution_artifact=ur, p3f9b_snapshot=p3f9b_snapshot, liquidity_artifact=liq,
        entity_classifications={}, technical_history_recovery_artifact=regenerated,
    )
    assert artifact["input_lineage"]["technical_history_recovery_artifact_identity"] == regenerated["artifact_identity"]


def test_technical_recovery_stale_cache_is_never_mutated_in_place(tmp_path):
    session = "2026-09-07"
    paths = _independent_component_session_paths(tmp_path, session)
    snapshot_identity = _write_valid_p3f9b_snapshot(paths["exact_session_snapshot"], session)
    stale_payload = _stale_technical_recovery_payload(session, snapshot_identity)
    _write_json(paths["technical_recovery"], stale_payload)
    original_bytes = paths["technical_recovery"].read_bytes()
    original_tech_dir = paths["technical_recovery"].parent

    def fake_run_cmd(root, argv):
        out_dir = Path(argv[argv.index("--out-dir") + 1])
        # The implementation must never point the producer at the original, already-occupied
        # tech_dir -- run_all() there would just print "REUSED" over the stale file's own path,
        # and nothing may write to that path at all once it is known invalid.
        assert out_dir != original_tech_dir
        fresh = _valid_technical_recovery_payload(session, snapshot_identity)
        _write_json(out_dir / "market_wide_current_technical_coverage_recovery_artifact.json", fresh)

    with patch.object(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths)), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "run_cmd", side_effect=fake_run_cmd):
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")

    # The retained historical artifact is byte-for-byte untouched -- never repaired, re-signed, or
    # overwritten in place to force it to pass identity validation.
    assert paths["technical_recovery"].read_bytes() == original_bytes
    assert json.loads(paths["technical_recovery"].read_text(encoding="utf-8"))["artifact_sha256"] == "0" * 64


def test_technical_recovery_regenerated_cache_is_reused_on_second_invocation(tmp_path):
    session = "2026-09-07"
    paths = _independent_component_session_paths(tmp_path, session)
    snapshot_identity = _write_valid_p3f9b_snapshot(paths["exact_session_snapshot"], session)
    stale_payload = _stale_technical_recovery_payload(session, snapshot_identity)
    _write_json(paths["technical_recovery"], stale_payload)

    def fake_run_cmd(root, argv):
        out_dir = Path(argv[argv.index("--out-dir") + 1])
        fresh = _valid_technical_recovery_payload(session, snapshot_identity)
        _write_json(out_dir / "market_wide_current_technical_coverage_recovery_artifact.json", fresh)

    with patch.object(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths)), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "run_cmd", side_effect=fake_run_cmd) as mocked_run_cmd:
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")
    assert mocked_run_cmd.call_count == 1

    # Second same-input invocation: the stale original is still on disk and still invalid, but the
    # regenerated cache from the first invocation must now be reused without a second producer run.
    with patch.object(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths)), \
         patch.object(level2, "_prior_completed_descriptive", return_value=tmp_path / "prior.json"), \
         patch.object(level2, "run_cmd", side_effect=fake_run_cmd) as mocked_run_cmd_second:
        level2.materialize_independent_components(tmp_path, session, tmp_path / "runtime")
    mocked_run_cmd_second.assert_not_called()


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


def test_official_event_context_resolves_latest_dated_snapshot(tmp_path):
    """CORPORATE_EVENT_CANONICAL_DATA_REFRESH_AND_LEDGER_CONSOLIDATION_V1: the previous hardcoded
    literal never picked up a fresher current_official_event_context materialization without a
    source-code edit (LATEST_POINTER_STALE). A newer dated snapshot directory must be resolved
    automatically."""
    ops = tmp_path / "operations-review"
    older = ops / "current-official-event-context-integration-v1-20260824"
    newer = ops / "current-official-event-context-integration-v1-20260910"
    for directory in (older, newer):
        directory.mkdir(parents=True)
        (directory / "current_official_event_context_artifact.json").write_text("{}", encoding="utf-8")
    paths = level2.session_artifact_paths(tmp_path, "2026-09-10")
    assert paths["official_event_context"] == newer / "current_official_event_context_artifact.json"


def test_official_event_context_falls_back_when_no_dated_snapshot_exists(tmp_path):
    """No dated snapshot directory (e.g. a fresh tmp_path, as in every other test in this file)
    must resolve to the one known-retained literal, unchanged from before this fix."""
    paths = level2.session_artifact_paths(tmp_path, "2026-09-10")
    assert paths["official_event_context"] == (
        tmp_path / "operations-review" / "current-official-event-context-integration-v1-20260824"
        / "current_official_event_context_artifact.json"
    )
