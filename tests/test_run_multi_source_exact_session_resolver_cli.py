import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import multi_source_exact_session_resolver as resolver_module  # noqa: E402
import run_multi_source_exact_session_resolver as cli  # noqa: E402
from multi_source_exact_session_resolver import DnseProviderWideQualityDegraded  # noqa: E402
from vn_stock_pipeline import FetchOutcome  # noqa: E402

SESSION = "2026-09-03"


def make_df_stub(dates_closes, unit_scale=1000):
    df = pd.DataFrame({
        "ticker": "T", "date": [d for d, _ in dates_closes],
        "open": [c for _, c in dates_closes], "high": [c for _, c in dates_closes],
        "low": [c for _, c in dates_closes], "close": [c for _, c in dates_closes],
        "volume": [999000 for _ in dates_closes], "source": "VCI",
    })
    df.attrs["unit_scale"] = unit_scale
    return df


def _stub_fetch_always_missing(ticker, source, start, end):
    """Deterministic recovery/sentinel stub: every DNSE-exact_session_resolver CLI test that
    doesn't itself care about VCI/KBS recovery must never touch the real network -- this
    milestone's own Pass 5 sentinel now queries VCI/KBS for DNSE-resolved sentinel-cohort
    members too (see multi_source_exact_session_resolver.select_sentinel_cohort), so any test
    exercising cli.execute() needs an explicit fetch stub even when it expects zero recovery."""
    return FetchOutcome("empty")


def _fake_dnse_snapshot(candidates, requested_at, target_session, **kw):
    return {
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "resolved_completed_session": target_session, "retained_snapshot_session": target_session,
        "requested_at": requested_at.isoformat(), "target_session": target_session,
        "candidate_count": len(candidates), "attempted_candidate_count": len(candidates),
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "source": {"provider": "DNSE"},
        "authority_boundary": {"RAW_AS_TRADED": "NOT_PROMOTED", "HISTORICAL_PIT": "BLOCKED", "runtime_database_mutated": False},
        "records": {t: {"status": "OBSERVED", "reason": None, "disposition": "EXACT_SESSION_RETAINED",
                        "observations": [{"session": target_session, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
                                          "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
                                          "price_basis": "x"}],
                        "payload_hash": "h", "request": {}, "provider_endpoint": "/price/ohlc"} for t in candidates},
        "snapshot_sha256": "x", "snapshot_identity": "p3f9_exact_session_snapshot:x",
    }


def test_cli_explicit_session_is_threaded_through_to_dnse_and_resolver(tmp_path):
    captured = {}

    def fake_materialize_snapshot(*, candidates, requested_at, target_session, api_key, api_secret, workers=8, **kw):
        captured["dnse_target_session"] = target_session
        return _fake_dnse_snapshot(candidates, requested_at, target_session)

    with patch.object(cli.snapshotter, "canonical_candidates", return_value=["AAA", "BBB"]), \
         patch.object(cli, "ensure_credentials_loaded", return_value={"configured": True}), \
         patch.object(cli, "credentials_for_request", return_value=("key", "secret")), \
         patch.object(cli.snapshotter, "materialize_snapshot", fake_materialize_snapshot), \
         patch.object(resolver_module, "_default_fetch_single_source", return_value=_stub_fetch_always_missing):
        result = cli.execute(
            runtime=tmp_path / "runtime", output_dir=tmp_path / "out",
            target_session=SESSION, workers=4,
        )

    assert captured["dnse_target_session"] == SESSION
    assert result["session"] == SESSION
    assert result["candidate_count"] == 2
    assert result["dnse_exact_count"] == 2  # both AAA/BBB resolved by DNSE, no recovery needed
    assert result["vci_recovery_attempts"] == 0
    written = json.loads((tmp_path / "out" / "run_summary.json").read_text(encoding="utf-8"))
    assert written["session"] == SESSION


def test_cli_raises_when_credentials_unavailable(tmp_path):
    with patch.object(cli.snapshotter, "canonical_candidates", return_value=["AAA"]), \
         patch.object(cli, "ensure_credentials_loaded", return_value={"configured": False}), \
         patch.object(cli, "credentials_for_request", return_value=None):
        try:
            cli.execute(runtime=tmp_path / "runtime", output_dir=tmp_path / "out", target_session=SESSION)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "DNSE_CREDENTIAL_INJECTION_REQUIRED" in str(exc)


def test_cli_watchlist_11_status_reports_every_named_ticker(tmp_path):
    def fake_materialize_snapshot(*, candidates, requested_at, target_session, api_key, api_secret, workers=8, **kw):
        return _fake_dnse_snapshot(candidates, requested_at, target_session)

    with patch.object(cli.snapshotter, "canonical_candidates", return_value=list(cli.WATCHLIST_11)), \
         patch.object(cli, "ensure_credentials_loaded", return_value={"configured": True}), \
         patch.object(cli, "credentials_for_request", return_value=("key", "secret")), \
         patch.object(cli.snapshotter, "materialize_snapshot", fake_materialize_snapshot), \
         patch.object(resolver_module, "_default_fetch_single_source", return_value=_stub_fetch_always_missing):
        result = cli.execute(runtime=tmp_path / "runtime", output_dir=tmp_path / "out", target_session=SESSION)

    assert set(result["watchlist_11_status"]) == set(cli.WATCHLIST_11)
    for ticker in cli.WATCHLIST_11:
        assert result["watchlist_11_status"][ticker]["disposition"] == "EXACT_SESSION_RETAINED"


def test_cli_builds_and_reports_dnse_quality_sentinel(tmp_path):
    def fake_materialize_snapshot(*, candidates, requested_at, target_session, api_key, api_secret, workers=8, **kw):
        return _fake_dnse_snapshot(candidates, requested_at, target_session)

    with patch.object(cli.snapshotter, "canonical_candidates", return_value=["AAA", "BBB"]), \
         patch.object(cli, "ensure_credentials_loaded", return_value={"configured": True}), \
         patch.object(cli, "credentials_for_request", return_value=("key", "secret")), \
         patch.object(cli.snapshotter, "materialize_snapshot", fake_materialize_snapshot), \
         patch.object(resolver_module, "_default_fetch_single_source", return_value=_stub_fetch_always_missing):
        result = cli.execute(runtime=tmp_path / "runtime", output_dir=tmp_path / "out", target_session=SESSION)

    assert result["dnse_quality_sentinel"] is not None
    assert result["dnse_quality_sentinel"]["cohort_version"] == resolver_module.SENTINEL_COHORT_VERSION
    assert set(result["dnse_quality_sentinel"]["cohort_tickers"]) >= {"AAA", "BBB"}
    cohort_file = json.loads((tmp_path / "out" / "dnse_quality_sentinel_cohort.json").read_text(encoding="utf-8"))
    assert cohort_file["cohort_version"] == resolver_module.SENTINEL_COHORT_VERSION


def test_cli_persists_all_artifacts_then_raises_on_broad_dnse_conflict(tmp_path):
    """A DNSE_BROAD_STALE_OR_INCOMPLETE_EOD verdict must never cost the real, already-collected
    evidence: this milestone's own real 2026-09-03 sentinel run found exactly this shape on its
    first live attempt, and discarding that evidence would have thrown away the only record of
    why the day degraded."""
    candidates = [f"C{i}" for i in range(6)]  # all DNSE-exact, fake close=1 (see _fake_dnse_snapshot)

    def fake_materialize_snapshot(*, candidates, requested_at, target_session, api_key, api_secret, workers=8, **kw):
        return _fake_dnse_snapshot(candidates, requested_at, target_session)

    def conflicting_fetch(ticker, source, start, end):
        # Real close far from DNSE's fake close=1 -- VCI and KBS agree with each other.
        return FetchOutcome("success", data=make_df_stub([(SESSION, 8000.0)]))

    with patch.object(cli.snapshotter, "canonical_candidates", return_value=candidates), \
         patch.object(cli, "ensure_credentials_loaded", return_value={"configured": True}), \
         patch.object(cli, "credentials_for_request", return_value=("key", "secret")), \
         patch.object(cli.snapshotter, "materialize_snapshot", fake_materialize_snapshot), \
         patch.object(resolver_module, "_default_fetch_single_source", return_value=conflicting_fetch):
        with pytest.raises(DnseProviderWideQualityDegraded) as excinfo:
            cli.execute(runtime=tmp_path / "runtime", output_dir=tmp_path / "out", target_session=SESSION)

    assert excinfo.value.dnse_quality_sentinel["health"]["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
    # Every artifact was still written before the raise -- nothing about the real evidence is lost.
    out = tmp_path / "out"
    assert json.loads((out / "run_summary.json").read_text(encoding="utf-8"))["dnse_exact_count"] == 6
    assert (out / "multi_source_exact_session_market_evidence.json").exists()
    assert (out / "resolved_exact_session_snapshot.json").exists()
    assert (out / "dnse_quality_sentinel_cohort.json").exists()
