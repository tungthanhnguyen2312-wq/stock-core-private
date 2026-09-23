"""CURRENT_FOREIGN_FLOW_DAILY_ACTIVATION_V1: production Daily live-path contract.

No test here performs a real provider/network call. Simulated DNSE responses are injected
via ``request_get``, matching ``tests/test_current_foreign_flow_enrichment_operation.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_current_product_projections as ccpp
import canonical_post_close_pipeline as cpc
import current_foreign_flow_enrichment_operation as op
import current_foreign_flow_retention as retention
import dnse_foreign_flow_store as store
import flow_price_divergence_shadow as flow_price
from dnse_foreign_flow_capability import normalize_record
from velocity_flow_price_presentation_projection import flow_price_view

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-23"
PRIOR_SESSION = "2026-09-18"
COHORT = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
_REAL_BUILD_MANIFEST_FROM_ROOT = retention.build_manifest_from_root


class _Response:
    def __init__(self, body: dict, status_code: int = 200, headers: dict | None = None):
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._body


def _record(symbol: str, session: str = SESSION, buy: int = 100, sell: int = 40) -> dict:
    return {
        "symbol": symbol, "boardId": "G1", "marketId": "STO",
        "time": f"{session} 14:45:00.000",
        "totalBuyTradedAmount": buy, "totalSellTradedAmount": sell,
        "totalBuyVolume": 999, "totalSellVolume": 500, "foreignerBuyPossibleQuantity": 9,
    }


def _symbol_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-2]


def _manifest(session: str = SESSION):
    return _REAL_BUILD_MANIFEST_FROM_ROOT(ROOT, session)


def _velocity(session: str, tickers=COHORT, state: str = "MIXED_TRANSITION") -> dict:
    records = []
    for ticker in tickers:
        records.append({
            "ticker": ticker, "session": session,
            "overall_transition_state": state,
            "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"},
            "source_snapshot_identity": f"velocity:{ticker}:{session}",
            "axes": {
                "structural_repair": {"state": "NEUTRAL", "source_identity": "tech:1"},
                "setup_maturation": {"state": "VALID"},
                "participation_confirmation": {"state": "NEUTRAL"},
                "market_support": {"state": "NEUTRAL"},
                "sector_support": {"state": "NEUTRAL"},
            },
        })
    return {
        "contract_version": flow_price.VELOCITY_CONTRACT_VERSION,
        "artifact_identity": "multi_session_signal_velocity:test-activation",
        "records": records,
        "validation": {"latest_session": session},
    }


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch):
    for key in ("DNSE_API_KEY", "DNSE_API_SECRET", "LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("STOCK_LOOKUP_SECRETS_FILE", str(Path("no_such_secrets.env")))


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_LOOKUP_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_LOOKUP_SECRETS_FILE", str(tmp_path / "no_such_secrets.env"))
    return tmp_path


def _patch_manifest(monkeypatch):
    monkeypatch.setattr(
        retention, "build_manifest_from_root",
        lambda _root, session: _REAL_BUILD_MANIFEST_FROM_ROOT(ROOT, session),
    )


def _patch_live_acquire(monkeypatch, get):
    real = op.acquire_foreign_flow_for_manifest

    def wrapped(manifest, *, runtime_root, allow_network=False, **kwargs):
        if allow_network:
            kwargs.setdefault("api_key", "k")
            kwargs.setdefault("api_secret", "s")
            kwargs.setdefault("request_get", get)
            kwargs.setdefault("sleep", lambda _s: None)
        return real(manifest, runtime_root=runtime_root, allow_network=allow_network, **kwargs)

    monkeypatch.setattr(op, "acquire_foreign_flow_for_manifest", wrapped)


def test_normal_daily_constant_enables_live_foreign_flow():
    assert cpc.NORMAL_DAILY_ENABLE_CURRENT_FOREIGN_FLOW_LIVE is True


def test_success_admits_exact_session_value(isolated_runtime, monkeypatch):
    calls = {"count": 0}

    def get(url, *, params, headers, timeout):
        calls["count"] += 1
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    _patch_manifest(monkeypatch)
    _patch_live_acquire(monkeypatch, get)
    result = cpc.run_current_foreign_flow_enrichment(
        isolated_runtime, isolated_runtime, SESSION, allow_network=True,
    )
    assert result["status"] == op.STATUS_COMPLETE
    assert result["complete_count"] == 11
    assert result["network_calls_made"] == 11
    assert calls["count"] == 11
    for ticker in COHORT:
        verification = op.verify_ticker_current(isolated_runtime, ticker, SESSION)
        assert verification["status"] == "CURRENT"
        assert store.read_observations(isolated_runtime, ticker)[0]["session_date"] == SESSION


def test_partial_failure_keeps_successful_tickers(isolated_runtime, monkeypatch):
    retryable = {"NVL", "PAN"}

    def get(url, *, params, headers, timeout):
        symbol = _symbol_from_url(url)
        if symbol in retryable:
            return _Response({"message": "rate limited"}, 429)
        return _Response({"foreigners": [_record(symbol)]})

    operation = op.acquire_foreign_flow_for_manifest(
        _manifest(), runtime_root=isolated_runtime, allow_network=True,
        api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None,
        max_retries=1, backoff_seconds=0.0,
    )
    assert operation["status"] == op.STATUS_PARTIAL
    assert operation["complete_count"] == 9
    assert operation["failed_count"] == 2
    assert op.verify_ticker_current(isolated_runtime, "HPG", SESSION)["status"] == "CURRENT"
    assert op.verify_ticker_current(isolated_runtime, "NVL", SESSION)["status"] == "NOT_CURRENT"


def test_credential_and_network_failure_degrades_without_calls(isolated_runtime, monkeypatch):
    _patch_manifest(monkeypatch)
    result = cpc.run_current_foreign_flow_enrichment(
        isolated_runtime, isolated_runtime, SESSION, allow_network=True,
    )
    assert result["status"] == op.STATUS_FAILED_OPERATIONAL
    assert result["network_calls_made"] == 0
    written = json.loads((isolated_runtime / result["path"]).read_text(encoding="utf-8"))
    assert written["network"]["credentials_available"] is False
    assert all(record["state"] == op.CREDENTIAL_UNAVAILABLE for record in written["records"].values())
    assert store.read_observations(isolated_runtime, "HPG") == []


def test_rerun_reuses_retained_raw_and_makes_no_duplicate_calls(isolated_runtime, monkeypatch):
    calls = {"count": 0}

    def get(url, *, params, headers, timeout):
        calls["count"] += 1
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    _patch_manifest(monkeypatch)
    _patch_live_acquire(monkeypatch, get)
    first = cpc.run_current_foreign_flow_enrichment(
        isolated_runtime, isolated_runtime, SESSION, allow_network=True,
    )
    after_first = calls["count"]
    second = cpc.run_current_foreign_flow_enrichment(
        isolated_runtime, isolated_runtime, SESSION, allow_network=True,
    )
    assert first["status"] == second["status"] == op.STATUS_COMPLETE
    assert calls["count"] == after_first
    assert second["network_calls_made"] == 0
    assert second["complete_count"] == 11


def test_exact_session_mismatch_does_not_admit_value(isolated_runtime):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record("HPG", session=PRIOR_SESSION)]})

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=isolated_runtime, allow_network=True,
        credentials_available=True, api_key="k", api_secret="s", request_get=get,
        sleep=lambda _s: None, max_retries=1, backoff_seconds=0.0, request_delay_seconds=0.0,
        retry_failed=False, run_id="r",
    )
    assert outcome["state"] in {op.SESSION_MISSING, op.SESSION_MISMATCH}
    assert store.read_observations(isolated_runtime, "HPG") == []
    assert op.verify_ticker_current(isolated_runtime, "HPG", SESSION)["status"] == "NOT_CURRENT"


def test_flow_price_consumes_same_session_value(isolated_runtime, monkeypatch):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    op.acquire_foreign_flow_for_manifest(
        _manifest(), runtime_root=isolated_runtime, allow_network=True,
        api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None,
    )
    artifact = flow_price.collect_from_retained_runtime(
        root=ROOT, runtime_root=isolated_runtime, reference_session=SESSION,
        velocity_artifact=_velocity(SESSION, tickers=("HPG",)),
    )
    hpg = next(row for row in artifact["records"] if row["ticker"] == "HPG")
    assert hpg["session_alignment"]["state"] == "EXACT_SESSION_ALIGNED"
    assert hpg["flow"]["freshness"]["status"] == "current"
    assert hpg["flow"]["latest_qualified_flow_session"] == SESSION
    assert hpg["relationship"] not in {"FLOW_UNAVAILABLE", "RELATIONSHIP_NOT_EVALUABLE"}
    view = flow_price_view(ticker="HPG", artifact=artifact, cohort_tickers=frozenset(COHORT))
    assert view["reference_session"] == SESSION
    assert view["latest_qualified_flow_session"] == SESSION
    assert view["flow_freshness"]["status"] == "current"
    assert view["session_alignment"] == "EXACT_SESSION_ALIGNED"


def test_stale_2026_09_18_is_never_labelled_current_for_later_session(isolated_runtime):
    observation = normalize_record(
        _record("HPG", session=PRIOR_SESSION), source_endpoint="/price/HPG/foreign-trading",
    )
    retention.write_exact_value_observation(isolated_runtime, "HPG", observation)
    assert op.verify_ticker_current(isolated_runtime, "HPG", SESSION)["status"] == "NOT_CURRENT"
    artifact = flow_price.collect_from_retained_runtime(
        root=ROOT, runtime_root=isolated_runtime, reference_session=SESSION,
        velocity_artifact=_velocity(SESSION, tickers=("HPG",)),
    )
    hpg = next(row for row in artifact["records"] if row["ticker"] == "HPG")
    assert hpg["flow"]["state"] == "FLOW_STALE"
    assert hpg["flow"]["latest_qualified_flow_session"] == PRIOR_SESSION
    assert hpg["flow"]["freshness"]["status"] == "stale"
    assert hpg["session_alignment"]["state"] == "STALE_NOT_COMPARABLE"
    assert hpg["relationship"] == "FLOW_UNAVAILABLE"
    view = flow_price_view(ticker="HPG", artifact=artifact, cohort_tickers=frozenset(COHORT))
    assert view["flow_freshness"]["status"] == "stale"
    assert view["latest_qualified_flow_session"] == PRIOR_SESSION
    assert view["relationship"] == "FLOW_UNAVAILABLE"
    assert view["session_alignment"] != "EXACT_SESSION_ALIGNED"


def test_presentation_rebuild_excludes_stale_prior_session(isolated_runtime):
    observation = normalize_record(
        _record("HPG", session=PRIOR_SESSION), source_endpoint="/price/HPG/foreign-trading",
    )
    retention.write_exact_value_observation(isolated_runtime, "HPG", observation)
    rebuilt = ccpp.materialize_current_flow_price_divergence_shadow(
        root=isolated_runtime, session=SESSION, velocity_artifact=_velocity(SESSION, tickers=("HPG",)),
        flow_cohort_tickers=frozenset(COHORT),
    )
    assert rebuilt is None


def test_historical_2026_09_10_and_11_remain_temporally_ineligible():
    for session in ("2026-09-10", "2026-09-11"):
        with pytest.raises(ValueError, match="OFFICIAL_UNIVERSE_TEMPORALLY_INELIGIBLE"):
            retention.build_manifest_from_root(ROOT, session)
