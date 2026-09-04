"""Tests for daily_recovery_eligibility_projection (DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1).

Fixtures build tiny, self-consistent qualification/VCI-exchange/dnse-snapshot artifacts by hand
(never touching the real retained 2026-08-23 evidence files) so this suite is fully offline and
independent of anything under operations-review/.
"""
from __future__ import annotations

import json
from pathlib import Path

import current_market_universe_breadth_foundation as breadth_mod
import current_universe_status_and_session_coverage_resolution as status_mod
import daily_recovery_eligibility_projection as project


def _dnse_snapshot(records: dict) -> dict:
    snapshot = {
        "records": records,
        "resolved_completed_session": "2026-09-04",
        "snapshot_identity": "TEST_SNAPSHOT",
    }
    from field_temporal_contract import stable_id
    payload = {k: v for k, v in snapshot.items() if k not in {"snapshot_sha256", "snapshot_identity"}}
    snapshot["snapshot_sha256"] = stable_id(payload)
    snapshot["snapshot_identity"] = f"p3f9_exact_session_snapshot:{snapshot['snapshot_sha256']}"
    return snapshot


def _qualification_artifact(tickers: list[str], instrument_class_by_ticker: dict) -> dict:
    import hashlib

    def _canon(v):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    records = {t: {"instrument_class": instrument_class_by_ticker.get(t, "EQUITY")} for t in tickers}
    artifact = {"records": records}
    artifact["artifact_sha256"] = hashlib.sha256(_canon(artifact)).hexdigest()
    artifact["artifact_identity"] = f"market_wide_current_research_universe:{artifact['artifact_sha256']}"
    return artifact


def _vci_snapshot(tickers: list[str], exchange_by_ticker: dict) -> dict:
    from field_temporal_contract import stable_id
    snapshot = {"records": {t: {"exchange": exchange_by_ticker.get(t)} for t in tickers}}
    payload = dict(snapshot)
    snapshot["snapshot_sha256"] = stable_id(payload)
    snapshot["snapshot_identity"] = f"vci_exchange_reference_snapshot:{snapshot['snapshot_sha256']}"
    return snapshot


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _build(tmp_path, *, tickers, dispositions, instrument_classes, exchanges):
    records = {}
    for ticker in tickers:
        disp = dispositions.get(ticker, "SESSION_MISSING")
        obs = [{"session": "2026-09-04", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] if disp == "EXACT_SESSION_RETAINED" else []
        records[ticker] = {"disposition": disp, "observations": obs}
    dnse_snapshot = _dnse_snapshot(records)
    qualification = _qualification_artifact(tickers, instrument_classes)
    vci_snapshot = _vci_snapshot(tickers, exchanges)
    qual_path = _write(tmp_path, "qual.json", qualification)
    vci_path = _write(tmp_path, "vci.json", vci_snapshot)
    return dnse_snapshot, qual_path, vci_path


def test_available_projection_marks_delisted_ticker_ineligible(tmp_path):
    tickers = ["AAA", "BBB"]
    dnse_snapshot, qual_path, vci_path = _build(
        tmp_path, tickers=tickers,
        dispositions={"AAA": "PROVIDER_REJECTED", "BBB": "SESSION_MISSING"},
        instrument_classes={"AAA": "EQUITY", "BBB": "EQUITY"},
        exchanges={"AAA": "DELISTED", "BBB": "HOSE"},
    )
    result = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=qual_path, vci_exchange_snapshot_path=vci_path,
    )
    assert result["available"] is True
    assert result["per_ticker"]["AAA"]["recovery_eligible"] is False
    assert result["per_ticker"]["AAA"]["reason_code"] == "RECOVERY_INELIGIBLE_INACTIVE_OR_DELISTED"
    assert result["per_ticker"]["BBB"]["recovery_eligible"] is True
    assert result["counts"] == {"total": 2, "recovery_eligible": 1, "recovery_ineligible": 1}


def test_available_projection_marks_non_equity_ineligible(tmp_path):
    # current_market_universe_breadth_foundation.build_artifact requires a non-zero INCLUDED
    # (EQUITY) denominator, so DDD (EQUITY) must be present alongside CCC (ETF) for this to
    # exercise the real classification path rather than degrading on that unrelated constraint.
    tickers = ["CCC", "DDD"]
    dnse_snapshot, qual_path, vci_path = _build(
        tmp_path, tickers=tickers, dispositions={"CCC": "SESSION_MISSING", "DDD": "EXACT_SESSION_RETAINED"},
        instrument_classes={"CCC": "ETF", "DDD": "EQUITY"}, exchanges={"CCC": "HOSE", "DDD": "HOSE"},
    )
    result = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=qual_path, vci_exchange_snapshot_path=vci_path,
    )
    assert result["available"] is True
    assert result["per_ticker"]["CCC"]["recovery_eligible"] is False
    assert result["per_ticker"]["CCC"]["reason_code"] == "RECOVERY_INELIGIBLE_NON_EQUITY"


def test_missing_qualification_artifact_degrades_to_no_filter(tmp_path):
    tickers = ["AAA"]
    dnse_snapshot, _qual_path, vci_path = _build(
        tmp_path, tickers=tickers, dispositions={"AAA": "SESSION_MISSING"},
        instrument_classes={"AAA": "EQUITY"}, exchanges={"AAA": "HOSE"},
    )
    result = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=tmp_path / "does_not_exist.json",
        vci_exchange_snapshot_path=vci_path,
    )
    assert result["available"] is False
    assert result["per_ticker"]["AAA"]["recovery_eligible"] is True
    assert result["counts"] == {"total": 1, "recovery_eligible": 1, "recovery_ineligible": 0}


def test_missing_vci_snapshot_degrades_to_no_filter(tmp_path):
    tickers = ["AAA"]
    dnse_snapshot, qual_path, _vci_path = _build(
        tmp_path, tickers=tickers, dispositions={"AAA": "SESSION_MISSING"},
        instrument_classes={"AAA": "EQUITY"}, exchanges={"AAA": "HOSE"},
    )
    result = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=qual_path,
        vci_exchange_snapshot_path=tmp_path / "does_not_exist.json",
    )
    assert result["available"] is False
    assert result["per_ticker"]["AAA"]["recovery_eligible"] is True


def test_candidate_set_mismatch_degrades_to_no_filter_never_raises(tmp_path):
    """A stale/rotated static artifact whose ticker set no longer matches this session's
    candidates must never block Daily -- fail-open, not fail-closed."""
    dnse_snapshot, qual_path, vci_path = _build(
        tmp_path, tickers=["AAA", "BBB"], dispositions={"AAA": "SESSION_MISSING", "BBB": "SESSION_MISSING"},
        instrument_classes={"AAA": "EQUITY", "BBB": "EQUITY"}, exchanges={"AAA": "HOSE", "BBB": "HOSE"},
    )
    # Rebuild the qualification/vci artifacts over a DIFFERENT ticker set to force a mismatch.
    mismatched_qual = _qualification_artifact(["AAA", "ZZZ"], {"AAA": "EQUITY", "ZZZ": "EQUITY"})
    qual_path = _write(tmp_path, "qual_mismatch.json", mismatched_qual)
    result = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=qual_path, vci_exchange_snapshot_path=vci_path,
    )
    assert result["available"] is False
    assert result["per_ticker"]["AAA"]["recovery_eligible"] is True
    assert result["per_ticker"]["BBB"]["recovery_eligible"] is True


def test_recovery_eligible_ticker_set_none_means_no_filter(tmp_path):
    dnse_snapshot, qual_path, vci_path = _build(
        tmp_path, tickers=["AAA"], dispositions={"AAA": "PROVIDER_REJECTED"},
        instrument_classes={"AAA": "EQUITY"}, exchanges={"AAA": "DELISTED"},
    )
    degraded = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=tmp_path / "absent.json",
        vci_exchange_snapshot_path=vci_path,
    )
    assert project.recovery_eligible_ticker_set(degraded) is None

    available = project.project_recovery_eligibility(
        dnse_snapshot, qualification_artifact_path=qual_path, vci_exchange_snapshot_path=vci_path,
    )
    assert project.recovery_eligible_ticker_set(available) == set()


def test_reuses_existing_contracts_not_a_new_state(tmp_path):
    """Every non-eligible reason code must trace back to one of the two existing contracts'
    own documented states -- this module invents no new listing/activity vocabulary."""
    known_states = {
        status_mod.INACTIVE_OR_DELISTED, status_mod.NOT_APPLICABLE_NON_EQUITY,
        status_mod.UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL, status_mod.UNKNOWN,
    }
    assert set(project._INELIGIBLE_REASON_BY_STATE) == known_states
    assert project._RECOVERY_ELIGIBLE_STATES == frozenset({
        status_mod.ACTIVE_LISTED_OBSERVED, status_mod.ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION,
    })
