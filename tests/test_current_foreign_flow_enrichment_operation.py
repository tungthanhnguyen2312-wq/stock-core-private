"""Simulated end-to-end acceptance for current_foreign_flow_enrichment_operation/v1.

No test here ever performs a real network call: every DNSE response is a locally
constructed fixture injected via ``request_get``, matching the existing
``tests/test_bulk_ingest_dnse_foreign_trading_raw.py`` convention.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import current_foreign_flow_enrichment_operation as op
import current_foreign_flow_retention as retention
import dnse_foreign_flow_store as store
from dnse_foreign_flow_capability import normalize_record

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-18"
COHORT = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")


class _Response:
    def __init__(self, body: dict, status_code: int = 200, headers: dict | None = None):
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._body


def _record(symbol: str, session: str = SESSION, buy: int = 100, sell: int = 40) -> dict:
    return {"symbol": symbol, "boardId": "G1", "marketId": "STO", "time": f"{session} 14:45:00.000",
            "totalBuyTradedAmount": buy, "totalSellTradedAmount": sell,
            "totalBuyVolume": 999, "totalSellVolume": 500, "foreignerBuyPossibleQuantity": 9}


def _symbol_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-2]


def _manifest():
    return retention.build_manifest_from_root(ROOT, SESSION)


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch):
    """Every test in this file is a no-network-authority acceptance run; never let a real
    developer secrets.env leak credentials into a test that must prove the boundary."""
    for key in ("DNSE_API_KEY", "DNSE_API_SECRET", "LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"):
        monkeypatch.delenv(key, raising=False)


def test_manifest_is_the_real_eleven_ticker_cohort():
    manifest = _manifest()
    assert manifest["cohort_count"] == 11
    assert set(manifest["eligible_tickers"]) == set(COHORT)


# ---------------------------------------------------------------------------
# CASE A: 11/11 success
# ---------------------------------------------------------------------------
def test_case_a_eleven_of_eleven_success(tmp_path):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    operation = op.acquire_foreign_flow_for_manifest(
        _manifest(), runtime_root=tmp_path, allow_network=True, api_key="k", api_secret="s",
        request_get=get, sleep=lambda _s: None,
    )
    assert operation["status"] == op.STATUS_COMPLETE
    assert operation["complete_count"] == 11
    assert operation["failed_count"] == 0
    assert all(record["state"] == op.COMPLETE for record in operation["records"].values())
    assert operation["network"]["network_calls_made"] == 11
    # Store actually holds VALUE-only fields, never volume/room.
    stored = store.read_observations(tmp_path, "HPG")[0]
    assert stored["foreign_buy_value"] == 100 and stored["foreign_net_value"] == 60
    assert not any("volume" in key or "room" in key for key in stored)


# ---------------------------------------------------------------------------
# CASE B: 8 success, 2 retryable timeout, 1 missing session
# ---------------------------------------------------------------------------
def test_case_b_partial_success_reduces_to_partial_status(tmp_path):
    retryable = {"NVL", "PAN"}
    missing_session = "PVD"

    def get(url, *, params, headers, timeout):
        symbol = _symbol_from_url(url)
        if symbol in retryable:
            return _Response({"message": "rate limited"}, 429)
        if symbol == missing_session:
            return _Response({"foreigners": []})
        return _Response({"foreigners": [_record(symbol)]})

    operation = op.acquire_foreign_flow_for_manifest(
        _manifest(), runtime_root=tmp_path, allow_network=True, api_key="k", api_secret="s",
        request_get=get, sleep=lambda _s: None, max_retries=1, backoff_seconds=0.0,
    )
    assert operation["status"] == op.STATUS_PARTIAL
    assert operation["complete_count"] == 8
    states = {ticker: record["state"] for ticker, record in operation["records"].items()}
    assert states["NVL"] == op.FAILED_RETRYABLE and states["PAN"] == op.FAILED_RETRYABLE
    assert states["PVD"] == op.SESSION_MISSING
    assert operation["failed_count"] == 2
    assert operation["session_issue_count"] == 1


# ---------------------------------------------------------------------------
# CASE C: already-complete exact-session ticker
# ---------------------------------------------------------------------------
def test_case_c_already_retained_value_is_never_reacquired(tmp_path):
    observation = normalize_record(_record("HPG"), source_endpoint="/price/HPG/foreign-trading")
    retention.write_exact_value_observation(tmp_path, "HPG", observation)

    def get(*_a, **_k):
        raise AssertionError("must never be called for an already-retained exact-session ticker")

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=True, credentials_available=True,
        api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None, max_retries=1, backoff_seconds=0.0,
        request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.SKIPPED_ALREADY_COMPLETE
    assert outcome["network_calls"] == 0


# ---------------------------------------------------------------------------
# CASE D: retained raw but store missing -> adapter runs, no network
# ---------------------------------------------------------------------------
def test_case_d_retained_raw_without_store_runs_adapter_only(tmp_path):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    op.bulk_ingest.run(runtime_root=tmp_path, api_key="k", api_secret="s", symbols=["HPG"],
                       session_date=SESSION, run_id="prep", universe_context={},
                       request_get=get, sleep=lambda _s: None)
    assert store.read_observations(tmp_path, "HPG") == []

    def refuse(*_a, **_k):
        raise AssertionError("must not call the network when raw is already retained")

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=False, credentials_available=False,
        api_key=None, api_secret=None, request_get=refuse, sleep=lambda _s: None, max_retries=1,
        backoff_seconds=0.0, request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.COMPLETE
    assert outcome["network_calls"] == 0
    assert op.RAW_ALREADY_RETAINED in outcome["state_history"]
    assert store.read_observations(tmp_path, "HPG")[0]["foreign_buy_value"] == 100


# ---------------------------------------------------------------------------
# CASE E: same-session VALUE conflict
# ---------------------------------------------------------------------------
def test_case_e_conflicting_retained_value_is_never_overwritten(tmp_path):
    stale = normalize_record(_record("HPG", buy=999, sell=1), source_endpoint="/price/HPG/foreign-trading")
    retention.write_exact_value_observation(tmp_path, "HPG", stale)

    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record("HPG", buy=100, sell=40)]})

    op.bulk_ingest.run(runtime_root=tmp_path, api_key="k", api_secret="s", symbols=["HPG"],
                       session_date=SESSION, run_id="prep", universe_context={},
                       request_get=get, sleep=lambda _s: None)

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=False, credentials_available=False,
        api_key=None, api_secret=None, request_get=None, sleep=lambda _s: None, max_retries=1,
        backoff_seconds=0.0, request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.VALUE_CONFLICT
    assert store.read_observations(tmp_path, "HPG")[0]["foreign_buy_value"] == 999  # untouched


# ---------------------------------------------------------------------------
# CASE F: raw response ticker mismatch
# ---------------------------------------------------------------------------
def test_case_f_provider_ticker_mismatch_fails_closed(tmp_path):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record("WRONG_TICKER")]})

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=True, credentials_available=True,
        api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None, max_retries=1,
        backoff_seconds=0.0, request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.RAW_CONFLICT
    assert store.read_observations(tmp_path, "HPG") == []


# ---------------------------------------------------------------------------
# CASE G: provider session mismatch (point-in-time)
# ---------------------------------------------------------------------------
def test_case_g_provider_session_mismatch_fails_closed(tmp_path):
    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record("HPG", session="2026-09-17")]})

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=True, credentials_available=True,
        api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None, max_retries=1,
        backoff_seconds=0.0, request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.SESSION_MISMATCH
    assert store.read_observations(tmp_path, "HPG") == []


# ---------------------------------------------------------------------------
# CASE H: multi-page raw resumes correctly, but the single-page VALUE adapter
# fails closed rather than silently reading only the first page.
# ---------------------------------------------------------------------------
def test_case_h_multipage_raw_resumes_then_adapter_fails_closed_on_pagination(tmp_path):
    calls = []

    def get(url, *, params, headers, timeout):
        calls.append(dict(params))
        if "nextPageToken" not in params:
            return _Response({"foreigners": [_record("HPG")], "nextPageToken": "cursor-1"})
        return _Response({"foreigners": [_record("HPG")]})

    result = op.bulk_ingest.run(runtime_root=tmp_path, api_key="k", api_secret="s", symbols=["HPG"],
                                session_date=SESSION, run_id="r1", universe_context={},
                                request_get=get, sleep=lambda _s: None)
    assert result["status"] == "COMPLETE"
    assert len(calls) == 2  # both pages retained; no re-fetch of page 0 on the second request

    outcome = op._process_ticker(
        ticker="HPG", session=SESSION, runtime_root=tmp_path, allow_network=False, credentials_available=False,
        api_key=None, api_secret=None, request_get=None, sleep=lambda _s: None, max_retries=1,
        backoff_seconds=0.0, request_delay_seconds=0.0, retry_failed=False, run_id="r",
    )
    assert outcome["state"] == op.FAILED_TERMINAL
    assert outcome["detail"] == "RAW_PAGE_PAGINATION_NOT_COMPLETE"


# ---------------------------------------------------------------------------
# CASE I: network disabled
# ---------------------------------------------------------------------------
def test_case_i_network_disabled_by_default_makes_zero_calls(tmp_path):
    operation = op.acquire_foreign_flow_for_manifest(_manifest(), runtime_root=tmp_path)
    assert operation["network"]["allow_network"] is False
    assert operation["network"]["network_calls_made"] == 0
    assert operation["status"] == op.STATUS_PENDING_NETWORK
    assert all(record["state"] == op.NETWORK_DISABLED_PENDING_ACQUISITION for record in operation["records"].values())


# ---------------------------------------------------------------------------
# CASE J: credential unavailable under live flag
# ---------------------------------------------------------------------------
def test_case_j_credential_unavailable_under_live_flag(tmp_path):
    operation = op.acquire_foreign_flow_for_manifest(
        _manifest(), runtime_root=tmp_path, allow_network=True, secrets_file=str(tmp_path / "no_such_secrets.env"),
    )
    assert operation["network"]["credentials_available"] is False
    assert operation["network"]["credential_note"] == "CREDENTIAL_UNAVAILABLE_UNDER_LIVE_FLAG"
    assert operation["network"]["network_calls_made"] == 0
    assert all(record["state"] == op.CREDENTIAL_UNAVAILABLE for record in operation["records"].values())
    dumped = json.dumps(operation, default=str)
    assert "DNSE_API_SECRET" not in dumped


# ---------------------------------------------------------------------------
# CASE K: Flow-Price input unavailable after otherwise successful store update
# ---------------------------------------------------------------------------
def test_case_k_flow_price_stays_honest_when_velocity_record_absent(tmp_path):
    from flow_price_divergence_shadow import collect_from_retained_runtime, VELOCITY_CONTRACT_VERSION

    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    op.acquire_foreign_flow_for_manifest(_manifest(), runtime_root=tmp_path, allow_network=True,
                                         api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None)
    empty_velocity = {"contract_version": VELOCITY_CONTRACT_VERSION, "records": []}
    artifact = collect_from_retained_runtime(root=ROOT, runtime_root=tmp_path, reference_session=SESSION,
                                             velocity_artifact=empty_velocity)
    hpg = next(r for r in artifact["records"] if r["ticker"] == "HPG")
    assert hpg["price"]["state"] == "PRICE_EVIDENCE_INSUFFICIENT"
    assert hpg["relationship"] == "PRICE_EVIDENCE_INSUFFICIENT"
    assert hpg["flow"]["state"] == "NET_FOREIGN_BUY"  # store side is genuinely current and qualified


# ---------------------------------------------------------------------------
# CASE L: future rerun is idempotent
# ---------------------------------------------------------------------------
def test_case_l_rerun_is_idempotent_and_makes_no_further_network_calls(tmp_path):
    calls = {"count": 0}

    def get(url, *, params, headers, timeout):
        calls["count"] += 1
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    manifest = _manifest()
    first = op.acquire_foreign_flow_for_manifest(manifest, runtime_root=tmp_path, allow_network=True,
                                                 api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None)
    calls_after_first = calls["count"]
    second = op.acquire_foreign_flow_for_manifest(manifest, runtime_root=tmp_path, allow_network=True,
                                                  api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None)
    assert calls["count"] == calls_after_first  # zero additional network calls on rerun
    assert second["status"] == first["status"] == op.STATUS_COMPLETE
    assert {t: r["state"] for t, r in second["records"].items()} == {t: r["state"] for t, r in first["records"].items()}
    assert second["acquisition_manifest_identity"] == first["acquisition_manifest_identity"]
    assert second["counts"] == first["counts"]
    assert second["complete_count"] == first["complete_count"] == 11
    assert second["network"]["network_calls_made"] == 0
    assert second["network"]["network_calls_made"] < first["network"]["network_calls_made"]


# ---------------------------------------------------------------------------
# Verification (Phase 12) and status reduction unit coverage
# ---------------------------------------------------------------------------
def test_verify_ticker_current_fails_when_no_observation_retained(tmp_path):
    verification = op.verify_ticker_current(tmp_path, "HPG", SESSION)
    assert verification["status"] == "NOT_CURRENT"
    assert "exact_session_observation_exists" in verification["failing_checks"]


def test_reduce_status_matrix():
    assert op._reduce_status({op.COMPLETE: 3}, 3) == op.STATUS_COMPLETE
    assert op._reduce_status({op.COMPLETE: 2, op.FAILED_TERMINAL: 1}, 3) == op.STATUS_PARTIAL
    assert op._reduce_status({op.NETWORK_DISABLED_PENDING_ACQUISITION: 3}, 3) == op.STATUS_PENDING_NETWORK
    assert op._reduce_status({op.FAILED_TERMINAL: 3}, 3) == op.STATUS_FAILED_OPERATIONAL
    assert op._reduce_status({op.VALUE_CONFLICT: 3}, 3) == op.STATUS_BLOCKED_CONFLICT
    assert op._reduce_status({}, 0) == op.STATUS_UNAVAILABLE


def test_operation_snapshot_write_is_mutable_across_reruns(tmp_path):
    manifest = _manifest()
    path = tmp_path / "operation.json"
    pending = op.acquire_foreign_flow_for_manifest(manifest, runtime_root=tmp_path)
    op.write_operation_snapshot(path, pending)

    def get(url, *, params, headers, timeout):
        return _Response({"foreigners": [_record(_symbol_from_url(url))]})

    complete = op.acquire_foreign_flow_for_manifest(manifest, runtime_root=tmp_path, allow_network=True,
                                                     api_key="k", api_secret="s", request_get=get, sleep=lambda _s: None)
    op.write_operation_snapshot(path, complete)  # different content at the same path: must not raise
    assert json.loads(path.read_text())["status"] == op.STATUS_COMPLETE
