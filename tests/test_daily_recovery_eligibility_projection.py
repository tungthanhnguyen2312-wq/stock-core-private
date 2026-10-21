"""Tests for daily_recovery_eligibility_projection (DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1).

Fixtures build tiny, self-consistent qualification/VCI-exchange/dnse-snapshot artifacts by hand
(never touching the real retained 2026-08-23 evidence files) so this suite is fully offline and
independent of anything under operations-review/.
"""
from __future__ import annotations

import json
from pathlib import Path

from stocklookup_core.tactical import current_market_universe_breadth_foundation as breadth_mod
from stocklookup_core.evidence import current_universe_status_and_session_coverage_resolution as status_mod
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


# --- 2026-10-19 live incident: static inputs resolve from the retained-evidence root -------------
#
# The first T: Daily failed because the VCI exchange snapshot was resolved beside the Producer
# checkout. After the code/evidence root split the file only exists under the retained root.

def _place_static_inputs(root: Path, qualification: dict, vci_snapshot: dict) -> None:
    for rel, data in (
        (project.QUALIFICATION_ARTIFACT_RELATIVE_PATH, qualification),
        (project.VCI_EXCHANGE_SNAPSHOT_RELATIVE_PATH, vci_snapshot),
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(data), encoding="utf-8")


def test_default_static_inputs_come_from_profile_retained_role_not_checkout(tmp_path, monkeypatch):
    import runtime_paths
    retained = tmp_path / "retained"
    monkeypatch.delenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", raising=False)
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: {"paths": {"retained": retained}})
    assert project.default_vci_exchange_snapshot_path() == retained / project.VCI_EXCHANGE_SNAPSHOT_RELATIVE_PATH
    assert project.default_qualification_artifact_path() == retained / project.QUALIFICATION_ARTIFACT_RELATIVE_PATH
    assert not str(project.default_vci_exchange_snapshot_path()).startswith(str(project.REPO_ROOT))


def test_default_static_inputs_use_configured_retained_root_without_profile(tmp_path, monkeypatch):
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    monkeypatch.setenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", str(tmp_path))
    assert project.default_vci_exchange_snapshot_path() == tmp_path.resolve() / project.VCI_EXCHANGE_SNAPSHOT_RELATIVE_PATH


def test_legacy_single_root_default_is_unchanged(monkeypatch):
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    monkeypatch.delenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", raising=False)
    assert project.default_vci_exchange_snapshot_path() == project.DEFAULT_VCI_EXCHANGE_SNAPSHOT_PATH


def test_projection_without_explicit_paths_reads_split_retained_root(tmp_path, monkeypatch):
    import runtime_paths
    tickers = ["AAA", "BBB"]
    dnse_snapshot, qual_path, vci_path = _build(
        tmp_path, tickers=tickers,
        dispositions={"AAA": "PROVIDER_REJECTED", "BBB": "SESSION_MISSING"},
        instrument_classes={"AAA": "EQUITY", "BBB": "EQUITY"},
        exchanges={"AAA": "DELISTED", "BBB": "HOSE"},
    )
    retained = tmp_path / "retained"
    _place_static_inputs(retained, json.loads(qual_path.read_text("utf-8")), json.loads(vci_path.read_text("utf-8")))
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: {"paths": {"retained": retained}})
    result = project.project_recovery_eligibility(dnse_snapshot)
    assert result["available"] is True
    assert result["per_ticker"]["AAA"]["recovery_eligible"] is False


def test_unqualified_profile_degrades_instead_of_blocking_daily(monkeypatch):
    import runtime_paths

    def refuse(**_k):
        raise RuntimeError("workspace volume wrong/unavailable")

    monkeypatch.setattr(runtime_paths, "workspace_profile", refuse)
    result = project.project_recovery_eligibility(_dnse_snapshot({"AAA": {"disposition": "SESSION_MISSING"}}))
    assert result["available"] is False
    assert result["degraded_reason"] == "RETAINED_EVIDENCE_ROOT_UNRESOLVED"


def test_universe_status_tool_default_vci_path_is_the_retained_root(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_universe_status_tool",
        project.REPO_ROOT / "tools/run_current_universe_status_and_session_coverage_resolution.py",
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    expected = tmp_path / "retained" / project.VCI_EXCHANGE_SNAPSHOT_RELATIVE_PATH
    monkeypatch.setattr(tool, "default_vci_exchange_snapshot_path", lambda: expected)
    loaded: list[Path] = []

    def fake_load(path):
        loaded.append(Path(path))
        if Path(path) == expected:
            raise FileNotFoundError(str(path))
        return {}

    monkeypatch.setattr(tool, "_load", fake_load)
    try:
        tool.main(["--breadth-foundation-artifact", str(tmp_path / "b.json"),
                   "--p3f9b-snapshot", str(tmp_path / "s.json"), "--output", str(tmp_path / "o.json")])
    except FileNotFoundError:
        pass
    assert loaded[-1] == expected
