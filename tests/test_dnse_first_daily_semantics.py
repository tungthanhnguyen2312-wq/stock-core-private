"""DNSE_FIRST_DAILY_AND_RECOVERY_INFRASTRUCTURE_CORRECTIVE (2026-09-26 owner rebaseline).

DNSE/Livespeed is primary; VNSTOCK_KBS_VCI is OPTIONAL_SUPPLEMENTAL / DEFERRED_NON_CRITICAL. An
unavailable supplemental runtime is an explicit capability state, not a Daily-invalidating event.
These tests lock the ordinary-Daily and M1 live-acceptance consequences, and that RECOVERY_REPLAY
evidence can never satisfy an ordinary-Daily reuse gate or M1.

Hermetic: no provider, network, secret or retained evidence.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

import canonical_daily_operation as cdo
import canonical_post_close_pipeline as cpc
import daily_session_level2_package as level2
import multi_source_market_evidence_contract as contract
import provider_runtime_state as rt
import vnstock_worker_client as worker_client
from _provider_runtime_fixtures import healthy_sentinel_evidence, unavailable_handle
from vn_time import VN_TZ

TARGET = "2026-09-10"


def _unavailable_evidence(session: str = TARGET, *, runtime_state: str | None = rt.SECURITY_REVIEW_BLOCKED) -> dict:
    evidence = healthy_sentinel_evidence(session)
    evidence["dnse_quality_sentinel"]["health"] = {"state": "DNSE_QUALITY_UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"}
    if runtime_state is not None:
        evidence["provider_runtime"] = {"state": runtime_state}
    return evidence


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# License semantics
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("runtime_state", [
    rt.SECURITY_REVIEW_BLOCKED, rt.NOT_CONFIGURED, rt.NOT_INSTALLED, rt.STARTUP_FAILED, None,
])
def test_supplemental_unavailable_is_a_dnse_primary_qualifying_license(runtime_state):
    license_ = contract.dnse_quality_license(_unavailable_evidence(runtime_state=runtime_state))
    assert license_["license"] == "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"
    # Core Daily may proceed ...
    assert license_["qualifies_for_core_daily"] is True
    assert license_["core_daily_basis"] == "DNSE_PRIMARY_UNCORROBORATED"
    # ... but it is NOT qualified source health and NOT corroborated.
    assert license_["qualifies_for_ordinary_daily"] is False
    assert license_["dnse_values_corroborated"] is False
    assert license_["license"] != "CORROBORATED_HEALTHY"
    assert license_["dnse_corroboration"] == "NOT_CORROBORATED_SUPPLEMENTAL_UNAVAILABLE"
    assert license_["supplemental_capability_state"] == "SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE"
    assert license_["dnse_raw_evidence_status"] == "RETAINED_UNCHANGED"


def test_unavailable_sentinel_contradicted_by_an_available_runtime_record_never_qualifies():
    license_ = contract.dnse_quality_license(_unavailable_evidence(runtime_state=rt.AVAILABLE))
    assert license_["license"] == "NOT_EVALUATED_NO_QUALITY_SENTINEL"
    assert license_["qualifies_for_core_daily"] is False
    assert license_["core_daily_basis"] is None


def test_corroborated_license_keeps_its_own_basis():
    evidence = healthy_sentinel_evidence(TARGET)
    evidence["provider_runtime"] = {"state": rt.AVAILABLE}
    license_ = contract.dnse_quality_license(evidence)
    assert license_["license"] == "CORROBORATED_HEALTHY"
    assert license_["core_daily_basis"] == "QUALIFIED_SOURCE_HEALTH"
    assert license_["qualifies_for_ordinary_daily"] is True and license_["qualifies_for_core_daily"] is True
    assert license_["dnse_values_corroborated"] is True
    assert license_["supplemental_capability_state"] == "SUPPLEMENTAL_PROVIDER_RUNTIME_AVAILABLE"
    assert license_["dnse_corroboration"] == "CORROBORATED"


@pytest.mark.parametrize(("evidence", "license_name"), [
    # D2 unchanged: a live runtime that returned no secondary observation.
    ({"target_session": TARGET, "dnse_exact_session_count": 3,
      "dnse_quality_sentinel": {"cohort_tickers": ["A"], "health": {"state": "DNSE_EXACT_BUT_UNCORROBORATED"}}},
     "UNASSESSED_NO_SECONDARY_OBSERVATION"),
    # DATA_QUALITY_FAILED stays fail-closed.
    ({"target_session": TARGET, "dnse_exact_session_count": 3,
      "dnse_quality_sentinel": {"cohort_tickers": ["A"], "health": {"state": "DNSE_EXACT_BUT_UNCORROBORATED"}},
      "records": {"A": {"observations": [{"source": "KBS", "status": "MALFORMED"}]}}}, "DATA_QUALITY_FAILED"),
    ({"target_session": TARGET, "dnse_quality_sentinel": {"health": {"state": "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"}}},
     "DATA_QUALITY_FAILED"),
    # NOT_EVALUATED never silently becomes healthy.
    ({"target_session": TARGET}, "NOT_EVALUATED_NO_QUALITY_SENTINEL"),
])
def test_non_qualifying_licenses_are_unchanged(evidence, license_name):
    license_ = contract.dnse_quality_license(evidence)
    assert license_["license"] == license_name
    assert license_["qualifies_for_ordinary_daily"] is False
    assert license_["qualifies_for_core_daily"] is False
    assert license_["dnse_values_corroborated"] is False
    assert license_["core_daily_basis"] is None


# ---------------------------------------------------------------------------------------------
# Level-2 acquisition boundary
# ---------------------------------------------------------------------------------------------


def _dnse_snapshot(records: dict) -> dict:
    out = {}
    for ticker, exact in records.items():
        obs = [{"session": TARGET, "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1000,
                "provider": "DNSE", "dataset": "DNSE_OHLC_1D"}] if exact else []
        out[ticker] = {
            "status": "OBSERVED" if exact else "SESSION_MISSING", "reason": None if exact else "SESSION_MISSING",
            "disposition": "EXACT_SESSION_RETAINED" if exact else "SESSION_MISSING", "observations": obs,
            "payload_hash": f"h-{ticker}" if exact else None, "request": {"symbol": ticker},
            "provider_endpoint": "/price/ohlc" if exact else None,
        }
    return {
        "contract_version": "p3f9_exact_session_mva_snapshot/v2", "resolved_completed_session": TARGET,
        "retained_snapshot_session": TARGET, "requested_at": f"{TARGET}T20:00:00+07:00", "target_session": TARGET,
        "candidate_count": len(out), "attempted_candidate_count": len(out),
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET", "unattempted_without_explicit_disposition": 0,
        "source": {"provider": "DNSE"}, "records": out, "snapshot_identity": "p3f9_exact_session_snapshot:t",
    }


def _patch_pass1(monkeypatch, snapshot: dict, *, handle=None) -> list:
    import dnse_access
    import dnse_secrets_env
    import mva_exact_session_snapshot as snapshotter

    monkeypatch.setattr(snapshotter, "canonical_candidates", lambda _root: list(snapshot["records"]))
    monkeypatch.setattr(dnse_secrets_env, "ensure_credentials_loaded", lambda *a, **k: {"configured": True})
    monkeypatch.setattr(dnse_access, "credentials_for_request", lambda *a, **k: ("synthetic", "synthetic"))
    monkeypatch.setattr(snapshotter, "materialize_snapshot", lambda **_kw: json.loads(json.dumps(snapshot)))
    opened: list = []
    if handle is not None:
        def _open(**kw):
            opened.append(kw)
            return handle
        monkeypatch.setattr(worker_client, "open_provider_runtime", _open)
    return opened


@pytest.mark.parametrize("state", [rt.NOT_CONFIGURED, rt.NOT_INSTALLED])
def test_unconfigured_provider_interpreter_never_falls_back_and_daily_proceeds(tmp_path, monkeypatch, state):
    """No core-interpreter fallback: the handle carries no fetcher, the resolver never fetches."""
    handle = unavailable_handle(state=state, reason="synthetic")
    assert handle.fetcher is None
    _patch_pass1(monkeypatch, _dnse_snapshot({"A": True, "B": False}), handle=handle)
    path = level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["provider_runtime_state"] == state
    assert written["dnse_quality_license"]["core_daily_basis"] == "DNSE_PRIMARY_UNCORROBORATED"
    assert written["dnse_quality_license"]["dnse_values_corroborated"] is False
    assert written["records"]["B"]["disposition"] != "EXACT_SESSION_RETAINED"


def test_no_vnstock_module_is_imported_by_a_dnse_primary_acquisition(tmp_path, monkeypatch):
    import sys

    before = {m for m in sys.modules if m.split(".")[0] in ("vnstock", "vnai", "vn_stock_pipeline")}
    _patch_pass1(monkeypatch, _dnse_snapshot({"A": True}))  # real tracked blocked policy
    level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    after = {m for m in sys.modules if m.split(".")[0] in ("vnstock", "vnai", "vn_stock_pipeline")}
    assert after == before


def test_dnse_primary_snapshot_still_faces_the_coverage_floor(tmp_path):
    """The supplemental block is gone; the mandatory DNSE coverage gate is not."""
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    snapshot = {
        "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2", "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0, "exact_session_observed_count": 100,
        "attempted_candidate_count": 1000, "requested_at": f"{TARGET}T19:00:00+07:00",
        "snapshot_sha256": "abc", "snapshot_identity": "p3f9_exact_session_snapshot:abc",
    }
    _write(paths["multi_source_market_evidence"], _unavailable_evidence())
    now = datetime(2026, 9, 10, 20, 0, tzinfo=VN_TZ)
    with pytest.raises(cpc.PreCutoffArtifactError, match="PARTIAL_OR_INTRADAY_EVIDENCE"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)
    snapshot["exact_session_observed_count"] = 900
    cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)  # DNSE-primary reuse OK


# ---------------------------------------------------------------------------------------------
# Recovery artifacts can never satisfy ordinary-Daily reuse gates
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("marker", [
    {"operating_mode": "RECOVERY_REPLAY"},
    {"recovery_replay": {"target_session": TARGET}},
])
def test_recovery_snapshot_never_satisfies_the_level2_reuse_gate(tmp_path, marker):
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _write(paths["exact_session_snapshot"], {"resolved_completed_session": TARGET, **marker})
    # With no companion evidence (legacy bare-snapshot route) ...
    assert level2._canonical_snapshot_gate_satisfied(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False
    # ... and with perfectly healthy companion evidence.
    _write(paths["multi_source_market_evidence"], healthy_sentinel_evidence(TARGET))
    assert level2._canonical_snapshot_gate_satisfied(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False
    with pytest.raises(ValueError, match="PROVIDER_HEALTH_GATE_UNRESOLVED"):
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")


def test_recovery_evidence_never_licenses_an_ordinary_snapshot(tmp_path):
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _write(paths["exact_session_snapshot"], {"resolved_completed_session": TARGET})
    evidence = healthy_sentinel_evidence(TARGET)
    evidence["operating_mode"] = "RECOVERY_REPLAY"
    _write(paths["multi_source_market_evidence"], evidence)
    assert level2._canonical_snapshot_gate_satisfied(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False


def test_recovery_snapshot_is_never_post_close_eligible():
    snapshot = {
        "operating_mode": "RECOVERY_REPLAY", "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2", "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0, "exact_session_observed_count": 900,
        "attempted_candidate_count": 1000, "requested_at": f"{TARGET}T19:00:00+07:00",
        "snapshot_sha256": "abc", "snapshot_identity": "p3f9_exact_session_snapshot:abc",
    }
    with pytest.raises(cpc.PreCutoffArtifactError, match="RECOVERY_REPLAY_NOT_ORDINARY_DAILY"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=datetime(2026, 9, 10, 20, 0, tzinfo=VN_TZ))


# ---------------------------------------------------------------------------------------------
# Ordinary Daily + M1 live acceptance
# ---------------------------------------------------------------------------------------------


def _dnse_primary_acquire(tmp_path, monkeypatch=None):
    from test_canonical_daily_operation import SESSION, _acquired

    if monkeypatch is not None:
        monkeypatch.setattr(level2, "supplemental_runtime_launchable", lambda: False)
    _write(level2.session_artifact_paths(tmp_path, SESSION)["multi_source_market_evidence"],
           _unavailable_evidence(SESSION))

    def acquire(*_a, **_k):
        acquired = _acquired(tmp_path)
        acquired["snapshot"]["provider_runtime_state"] = rt.SECURITY_REVIEW_BLOCKED
        acquired["snapshot"]["dnse_quality_license"] = {
            "license": "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE", "qualifies_for_ordinary_daily": False,
            "reason_code": "SENTINEL_NOT_RUN_SUPPLEMENTAL_RUNTIME_UNAVAILABLE",
            "qualifies_for_core_daily": True, "dnse_values_corroborated": False,
            "core_daily_basis": "DNSE_PRIMARY_UNCORROBORATED",
            "supplemental_capability_state": "SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE",
        }
        return acquired
    return acquire


def test_dnse_primary_core_daily_completes_and_is_m1_eligible(tmp_path, monkeypatch):
    from test_canonical_daily_operation import _run

    record = _run(tmp_path, monkeypatch, acquire_fn=_dnse_primary_acquire(tmp_path, monkeypatch))
    assert record["daily_operation_state"] in (cdo.STATE_LOCAL_COMPLETE, cdo.STATE_PUBLISHED)
    assert record["_calls"]["producer"] == 1  # the Core Daily producer ran
    assert record["operating_mode"] == cdo.OPERATING_MODE_ORDINARY_DAILY
    assert record["acquisition"]["provider_runtime_state"] == rt.SECURITY_REVIEW_BLOCKED
    assert record["acquisition"]["dnse_quality_license"]["core_daily_basis"] == "DNSE_PRIMARY_UNCORROBORATED"
    assert record["acquisition"]["dnse_quality_license"]["dnse_values_corroborated"] is False
    assert cdo.m1_live_acceptance_eligible(record) is True


def test_diagnostic_override_run_is_never_m1_eligible(tmp_path, monkeypatch):
    from test_canonical_daily_operation import _run

    record = _run(tmp_path, monkeypatch, acquire_fn=_dnse_primary_acquire(tmp_path, monkeypatch),
                  operating_mode=cdo.OPERATING_MODE_DIAGNOSTIC)
    assert record["operating_mode"] == cdo.OPERATING_MODE_DIAGNOSTIC
    assert cdo.m1_live_acceptance_eligible(record) is False


def test_canonical_daily_refuses_recovery_replay_mode(tmp_path, monkeypatch):
    from test_canonical_daily_operation import _run

    with pytest.raises(cdo.CanonicalDailyOperationError, match="OPERATING_MODE_NOT_PERMITTED_FOR_CANONICAL_DAILY"):
        _run(tmp_path, monkeypatch, operating_mode=cdo.OPERATING_MODE_RECOVERY_REPLAY)


def _eligible_record(**acquisition_overrides) -> dict:
    record = {
        "daily_operation_state": cdo.STATE_LOCAL_COMPLETE, "operating_mode": cdo.OPERATING_MODE_ORDINARY_DAILY,
        "acquisition": {
            "provider_runtime_state": rt.SECURITY_REVIEW_BLOCKED,
            "dnse_quality_license": {"license": "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE",
                                     "qualifies_for_ordinary_daily": False, "qualifies_for_core_daily": True},
        },
    }
    record["acquisition"].update(acquisition_overrides)
    return record


def test_m1_does_not_require_the_optional_supplemental_runtime():
    assert cdo.m1_live_acceptance_eligible(_eligible_record()) is True
    for state in (rt.NOT_CONFIGURED, rt.NOT_INSTALLED, rt.STARTUP_TIMEOUT):
        assert cdo.m1_live_acceptance_eligible(_eligible_record(provider_runtime_state=state)) is True


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(operating_mode="RECOVERY_REPLAY"),
    lambda r: r.update(operating_mode=cdo.OPERATING_MODE_DIAGNOSTIC),
    lambda r: r.update(operating_mode="OFFLINE_REPLAY"),
    lambda r: r.pop("operating_mode"),
    lambda r: r.update(is_idempotent_replay=True),
    lambda r: r.update(recovery_replay={"target_session": TARGET}),
    lambda r: r["acquisition"].update(operating_mode="RECOVERY_REPLAY"),
    lambda r: r["acquisition"].update(recovery_replay=True),
    lambda r: r.update(daily_operation_state=cdo.STAGE_BLOCKED_DNSE_QUALITY_UNLICENSED),
    lambda r: r.update(daily_operation_state=cdo.STAGE_BLOCKED_ACQUISITION),
    # DNSE-primary license with a runtime that WAS available is incoherent.
    lambda r: r["acquisition"].update(provider_runtime_state=rt.AVAILABLE),
    lambda r: r["acquisition"].pop("provider_runtime_state"),
    lambda r: r["acquisition"].update(dnse_quality_license={"license": "DATA_QUALITY_FAILED", "qualifies_for_ordinary_daily": False}),
    # A stored label cannot smuggle a non-qualifying license through.
    lambda r: r["acquisition"].update(dnse_quality_license={"license": "DATA_QUALITY_FAILED", "qualifies_for_ordinary_daily": True}),
    lambda r: r["acquisition"].update(dnse_quality_license={"license": "DATA_QUALITY_FAILED", "qualifies_for_core_daily": True}),
    lambda r: r["acquisition"]["dnse_quality_license"].update(qualifies_for_core_daily=False),
    lambda r: r["acquisition"].update(dnse_quality_license={
        "license": "NOT_EVALUATED_NO_QUALITY_SENTINEL", "qualifies_for_ordinary_daily": True}),
    lambda r: r["acquisition"].update(dnse_quality_license={
        "license": "UNASSESSED_NO_SECONDARY_OBSERVATION", "qualifies_for_ordinary_daily": True}),
])
def test_m1_rejects_every_non_ordinary_or_non_qualified_record(mutate):
    record = _eligible_record()
    mutate(record)
    assert cdo.m1_live_acceptance_eligible(record) is False


def test_m1_rejects_a_bare_stage_string_or_non_mapping():
    assert cdo.m1_live_acceptance_eligible("LOCAL_COMPLETE") is False
    assert cdo.m1_live_acceptance_eligible(None) is False  # type: ignore[arg-type]


def test_data_quality_failure_still_blocks_ordinary_daily_before_the_producer(tmp_path, monkeypatch):
    from test_canonical_daily_operation import _run

    def blocked(*_a, **_k):
        raise cpc.SupplementalProviderBlockError(
            "REFUSE_CANONICAL_POST_CLOSE:DNSE_QUALITY_LICENSE_NOT_QUALIFIED",
            kind=level2.SUPPLEMENTAL_BLOCK_KIND_QUALITY,
            runtime_state=rt.runtime_state_record(rt.AVAILABLE, rt.REASON_READY_HANDSHAKE),
            quality_license={"license": "DATA_QUALITY_FAILED", "qualifies_for_ordinary_daily": False},
            diagnostic_path=Path("block.json"),
        )

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, acquire_fn=blocked,
             producer_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("producer must not run")))
    assert exc.value.stage == cdo.STAGE_BLOCKED_DNSE_QUALITY_UNLICENSED
    text = cdo.format_owner_daily_status(exc.value, now=cdo.vn_now())
    assert "DNSE quality license: DATA_QUALITY_FAILED" in text
    assert "M1 live acceptance: NOT_SATISFIED_BY_THIS_RUN" in text


# ---------------------------------------------------------------------------------------------
# Companion evidence is mandatory; later supplemental availability re-runs quality evaluation
# ---------------------------------------------------------------------------------------------


def _post_corrective_snapshot(path: Path, **extra) -> None:
    _write(path, {"resolved_completed_session": TARGET, "provider_runtime_state": rt.SECURITY_REVIEW_BLOCKED,
                  "dnse_quality_license": {"license": "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"},
                  "companion_evidence_required": True, **extra})


def test_missing_companion_evidence_refuses_reuse_of_a_post_corrective_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(level2, "supplemental_runtime_launchable", lambda: False)
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _post_corrective_snapshot(paths["exact_session_snapshot"])
    gate = level2._canonical_snapshot_gate_satisfied
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False
    with pytest.raises(ValueError, match="PROVIDER_HEALTH_GATE_UNRESOLVED"):
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    # With the companion evidence present it is reusable (DNSE-primary, runtime still blocked).
    _write(paths["multi_source_market_evidence"], _unavailable_evidence())
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is True
    # Evidence without any quality sentinel never licenses a post-corrective snapshot.
    _write(paths["multi_source_market_evidence"], {"target_session": TARGET})
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False


def test_missing_companion_evidence_is_not_post_close_eligible(tmp_path, monkeypatch):
    monkeypatch.setattr(level2, "supplemental_runtime_launchable", lambda: False)
    snapshot = {
        "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2", "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0, "exact_session_observed_count": 900,
        "attempted_candidate_count": 1000, "requested_at": f"{TARGET}T19:00:00+07:00",
        "snapshot_sha256": "abc", "snapshot_identity": "p3f9_exact_session_snapshot:abc",
        "provider_runtime_state": rt.SECURITY_REVIEW_BLOCKED, "companion_evidence_required": True,
    }
    now = datetime(2026, 9, 10, 20, 0, tzinfo=VN_TZ)
    with pytest.raises(cpc.PreCutoffArtifactError, match="QUALITY_EVIDENCE_MISSING"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)
    with pytest.raises(cpc.PreCutoffArtifactError, match="QUALITY_EVIDENCE_NOT_CHECKED"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now)


def test_later_supplemental_availability_forces_quality_reevaluation(tmp_path, monkeypatch):
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _post_corrective_snapshot(paths["exact_session_snapshot"])
    _write(paths["multi_source_market_evidence"], _unavailable_evidence())
    gate = level2._canonical_snapshot_gate_satisfied
    monkeypatch.setattr(level2, "supplemental_runtime_launchable", lambda: False)
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is True
    monkeypatch.setattr(level2, "supplemental_runtime_launchable", lambda: True)
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is False
    assert level2.core_daily_reuse_refusal(
        {"provider_runtime_state": "X"}, _unavailable_evidence(), TARGET, evidence_present=True,
    ) == "SUPPLEMENTAL_RUNTIME_NOW_LAUNCHABLE_QUALITY_REEVALUATION_REQUIRED"
    # A corroborated snapshot is unaffected by the runtime becoming launchable.
    corroborated = healthy_sentinel_evidence(TARGET)
    corroborated["provider_runtime"] = {"state": rt.AVAILABLE}
    _write(paths["multi_source_market_evidence"], corroborated)
    assert gate(paths["exact_session_snapshot"], paths["multi_source_market_evidence"], TARGET) is True


def test_supplemental_runtime_launchable_is_false_under_the_tracked_blocked_policy(monkeypatch):
    monkeypatch.setenv(rt.PROVIDER_PYTHON_ENV, "/nonexistent/provider/python")
    assert level2.supplemental_runtime_launchable() is False


def test_research_action_posture_policy_body_is_untouched_by_this_corrective():
    """The corrective changes evidence availability/operating eligibility only; NO_CURRENT_EVIDENCE /
    unavailable axes absorb missing data."""
    import integrated_investment_decision_product as iid

    assert iid.EVIDENCE_CURRENCY_CURRENT_SESSION == "CURRENT_SESSION"
    assert hasattr(iid, "decide_research_action_posture")
