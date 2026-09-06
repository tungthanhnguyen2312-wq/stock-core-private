from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import owner_research_focus

from canonical_daily_release_acceptance import CONTRACT_VERSION, evaluate_artifact_root, human_summary


SESSION = "2026-09-04"
OPERATION = "daily_research_session_operation:operation-20260904"
PRODUCT = "current_daily_decision_research_product:product-20260904"


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path, *, input_overrides: dict | None = None, artifact_overrides: dict | None = None) -> Path:
    tickers = list(owner_research_focus.broader_watchlist())
    records = [{"ticker": ticker} for ticker in tickers]
    input_value = {
        "contract_version": "canonical_daily_release_acceptance_input/v1",
        "session": SESSION,
        "signal_components": [{"ticker": tickers[0], "state": "CURRENT", "source_session": SESSION}],
        "technical_records": [{"ticker": tickers[0], "target_close_session": SESSION}],
        "valuation": {"valuation_session": SESSION, "status": "AVAILABLE", "methods": []},
        "financial": {"financial_evidence_as_of_period": "2026-Q2", "status": "AVAILABLE"},
        "corporate": {"session": SESSION, "status": "AVAILABLE"},
        "prospective": {"research_session": SESSION, "snapshot_id": "snapshot-20260904", "future_outcomes": "PENDING_FUTURE_OBSERVATION"},
    }
    if input_overrides:
        input_value.update(input_overrides)
    operation = {
        "contract_version": "daily_research_session_operation/v1",
        "market_session": SESSION,
        "operation_identity": OPERATION,
        "input_artifacts": {name: {"session": SESSION, "artifact_identity": name + "-identity"} for name in ("descriptive", "screening", "tactical", "triage", "valuation", "corporate_intelligence")},
        "outputs": {"daily_product": PRODUCT, "prospective_snapshot": "snapshot-20260904"},
    }
    artifacts = {
        "run_manifest.json": operation,
        "current_daily_decision_research_product_artifact.json": {"session": SESSION, "artifact_identity": PRODUCT, "watchlist": {"tickers": tickers}},
        "daily_integrated_decision_brief.json": {"session": SESSION, "watchlist": {"tickers": tickers, "records": records}, "financial_evidence_context": {"financial_evidence_as_of_period": "2026-Q2", "status": "AVAILABLE"}},
        "prospective_snapshot.json": {"research_session": SESSION, "snapshot_id": "snapshot-20260904", "future_outcomes": "PENDING_FUTURE_OBSERVATION"},
        "ai_research_session_bundle.json": {"session": SESSION, "operation_identity": OPERATION, "product_identity": PRODUCT},
        "current_decision_cockpit_projection.json": {"session": SESSION, "source": {"operation_identity": OPERATION}, "watchlist": {"tickers": tickers}},
        "data/build_info.json": {"market_session": SESSION, "domains": {"screening": {"source_session": SESSION}}},
        "release_acceptance_input.json": input_value,
    }
    for name, changes in (artifact_overrides or {}).items():
        if changes is None:
            artifacts.pop(name)
        else:
            artifacts[name].update(changes)
    for name, value in artifacts.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, value)
    return tmp_path


def _report(tmp_path: Path, **kwargs: object) -> dict:
    return evaluate_artifact_root(_fixture(tmp_path, **kwargs))


def test_coherent_exact_session_release_passes(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert report["contract_version"] == CONTRACT_VERSION
    assert report["overall_state"] == "PASS"
    assert report["current_research_usable"] is True


def test_no_pattern_current_session_is_not_stale(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"signal_components": [{"state": "NO_PATTERN_CURRENT_SESSION", "source_session": SESSION}]})
    assert report["domains"]["signal_presentation"]["state"] == "EXACT_SESSION"


def test_explicitly_stale_signal_is_local_partial(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"signal_components": [{"state": "STALE_BUT_EXPLICITLY_LABELLED", "source_session": "2026-09-03"}]})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert report["current_research_usable"] is True
    assert "SIGNAL_SOURCE_SESSION_MISMATCH" in report["domains"]["signal_presentation"]["reason_codes"]


def test_false_current_signal_claim_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"signal_components": [{"state": "STALE", "source_session": "2026-09-03", "claims_current": True}]})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "SIGNAL_FALSE_CURRENT_CLAIM" in report["domains"]["signal_presentation"]["reason_codes"]


def test_insufficient_history_stays_distinct_from_no_pattern(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"signal_components": [{"state": "INSUFFICIENT_HISTORY", "source_session": SESSION}]})
    assert report["domains"]["signal_presentation"]["state"] == "EXPLICIT_PARTIAL"
    assert "SIGNAL_INSUFFICIENT_HISTORY" in report["domains"]["signal_presentation"]["reason_codes"]


def test_target_close_session_mismatch_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"technical_records": [{"target_close_session": "2026-09-03"}]})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "TECHNICAL_TARGET_CLOSE_SESSION_MISMATCH" in report["domains"]["technical_target_close"]["reason_codes"]


def test_missing_target_close_metadata_is_explicit_partial(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"technical_records": [{"ticker": "EVF"}]})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert "TECHNICAL_TARGET_CLOSE_NOT_EXPOSED" in report["domains"]["technical_target_close"]["reason_codes"]


def test_valuation_method_block_remains_local_partial(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"valuation": {"valuation_session": SESSION, "methods": [{"status": "BLOCKED", "price_basis_compatible": False, "shares_lineage": "MISSING"}]}})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert "VALUATION_METHOD_BLOCKED" in report["domains"]["valuation_readiness"]["reason_codes"]


def test_valuation_session_mismatch_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"valuation": {"valuation_session": "2026-09-03"}})
    assert report["overall_state"] == "INVALID_RELEASE"


def test_future_financial_period_is_rejected(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"financial": {"financial_evidence_as_of_period": "2026-Q4", "status": "AVAILABLE"}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert report["current_research_usable"] is False
    assert "FINANCIAL_KNOWLEDGE_CUTOFF_FUTURE" in report["domains"]["financial_cutoff"]["reason_codes"]


def test_explicitly_historical_corporate_context_is_partial_not_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"corporate": {"session": SESSION, "freshness_counts": {"HISTORICAL_OVER_90_DAYS": 2}}})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert report["current_research_usable"] is True


def test_corporate_session_mismatch_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"corporate": {"session": "2026-09-03"}})
    assert report["overall_state"] == "INVALID_RELEASE"


def test_realized_future_outcome_is_rejected(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"prospective": {"research_session": SESSION, "snapshot_id": "snapshot-20260904", "future_outcomes": {"outcome": "WIN", "observed_at": "2026-09-05"}}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "FUTURE_OUTCOME_EVIDENCE_REJECTED" in report["domains"]["prospective_snapshot"]["reason_codes"]


def test_prospective_operation_mismatch_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, input_overrides={"prospective": {"research_session": SESSION, "snapshot_id": "snapshot-20260904", "operation_identity": "other-operation", "future_outcomes": "PENDING_FUTURE_OBSERVATION"}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "PROSPECTIVE_OPERATION_IDENTITY_MISMATCH" in report["domains"]["prospective_snapshot"]["reason_codes"]


def test_ai_handoff_wrong_operation_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, artifact_overrides={"ai_research_session_bundle.json": {"operation_identity": "other-operation"}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "AI_HANDOFF_OPERATION_IDENTITY_MISMATCH" in report["domains"]["ai_handoff"]["reason_codes"]


def test_dashboard_wrong_session_is_invalid(tmp_path: Path) -> None:
    report = _report(tmp_path, artifact_overrides={"current_decision_cockpit_projection.json": {"session": "2026-09-03"}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert report["current_research_usable"] is True


def test_dashboard_domain_source_mismatch_is_disclosed_partial(tmp_path: Path) -> None:
    report = _report(tmp_path, artifact_overrides={"data/build_info.json": {"domains": {"signals": {"source_session": "2026-09-03"}}}})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert "DASHBOARD_DOMAIN_SOURCE_SESSION_MISMATCH:SIGNALS" in report["domains"]["dashboard_release"]["reason_codes"]


def test_dashboard_stale_signal_components_remain_explicitly_partial(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        input_overrides={"signal_components": []},
        artifact_overrides={"data/build_info.json": {"domains": {"signals": {"status": "STALE", "components": {"candle": {"status": "STALE", "source_session": "2026-09-03"}}}}}},
    )
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert "SIGNAL_STALE" in report["domains"]["signal_presentation"]["reason_codes"]
    assert "DASHBOARD_COMPONENT_SOURCE_SESSION_MISMATCH:SIGNALS:CANDLE" in report["domains"]["dashboard_release"]["reason_codes"]


def test_missing_watchlist_member_is_partial(tmp_path: Path) -> None:
    tickers = list(owner_research_focus.broader_watchlist())
    report = _report(tmp_path, artifact_overrides={"current_daily_decision_research_product_artifact.json": {"watchlist": {"tickers": tickers[:-1]}}})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"
    assert "WATCHLIST_MEMBER_MISSING" in report["domains"]["watchlist_authority"]["reason_codes"]


def test_unlabelled_watchlist_extra_is_invalid(tmp_path: Path) -> None:
    tickers = list(owner_research_focus.broader_watchlist()) + ["TEST"]
    report = _report(tmp_path, artifact_overrides={"current_daily_decision_research_product_artifact.json": {"watchlist": {"tickers": tickers}}})
    assert report["overall_state"] == "INVALID_RELEASE"
    assert "WATCHLIST_EXTRA_MEMBER_UNLABELLED" in report["domains"]["watchlist_authority"]["reason_codes"]


def test_labelled_validation_only_extra_is_partial(tmp_path: Path) -> None:
    tickers = list(owner_research_focus.broader_watchlist()) + ["TEST"]
    report = _report(tmp_path, input_overrides={"watchlist": {"validation_only_tickers": ["TEST"]}}, artifact_overrides={"current_daily_decision_research_product_artifact.json": {"watchlist": {"tickers": tickers}}})
    assert report["overall_state"] == "PASS_WITH_EXPLICIT_PARTIALS"


def test_cli_json_and_summary_are_machine_and_human_readable(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    command = [sys.executable, "tools/validate_canonical_daily_release.py", "--artifact-root", str(root), "--json"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["overall_state"] == "PASS"
    assert "CANONICAL_DAILY_RELEASE_ACCEPTANCE=PASS" in human_summary(evaluate_artifact_root(root))
