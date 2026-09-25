"""PROVIDER_RUNTIME_ISOLATION_V1: runtime-state contract, owner policy, dedicated interpreter,
credential isolation, single provider boundary, DNSE quality license, governed Daily blocking,
reuse safety, posture monotonicity and M1 eligibility.

Hermetic: the only "provider" is tests/fixtures/fake_vnstock_worker.py run by this interpreter
under an explicit test-only ALLOW policy. No vnstock/vnai is imported or executed, no provider or
network is contacted, no secret is read (all credentials below are synthetic).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import canonical_daily_operation as cdo
import canonical_post_close_pipeline as cpc
import daily_session_level2_package as level2
import multi_source_market_evidence_contract as contract
import provider_runtime_state as rt
import vnstock_worker_client as worker_client
import vnstock_worker_protocol as protocol
from _provider_runtime_fixtures import (
    FAKE_WORKER,
    TEST_ALLOW_POLICY,
    available_handle,
    fake_fetcher,
    healthy_sentinel_evidence,
    unavailable_handle,
)
from multi_source_exact_session_resolver import (
    DEGRADED_RECOVERY_COMPLETED,
    DEGRADED_RECOVERY_NOT_EVALUABLE,
    resolve_exact_session_with_autorecovery,
)
from vnstock_rate_governor import get_active_governor, set_active_governor

ROOT = Path(__file__).resolve().parents[1]
REAL_WORKER = ROOT / "vnstock_worker_process.py"
TARGET = "2026-09-10"
REQUESTED_AT = "2026-09-10T20:00:00+07:00"
NONEXISTENT_CORE = str(Path("/nonexistent/core/python"))

SYNTHETIC_SECRETS = {
    "DNSE_API_KEY": "synthetic-dnse-key-000",
    "DNSE_API_SECRET": "synthetic-dnse-secret-000",
    "LIVESPEED_API_KEY": "synthetic-livespeed-key-000",
    "LIVESPEED_API_SECRET": "synthetic-livespeed-secret-000",
    "FINHAY_API_KEY": "synthetic-finhay-key-000",
    "GITHUB_TOKEN": "synthetic-github-token-000",
    "SOME_SERVICE_SECRET": "synthetic-service-secret-000",
    "DB_PASSWORD": "synthetic-db-password-000",
}


def _allow_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), rt.PROVIDER_PYTHON_ENV: sys.executable}
    for key in ("SYSTEMROOT", "TEMP", "TMP", "HOME"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(extra)
    return env


_REAL_OPEN_PROVIDER_RUNTIME = worker_client.open_provider_runtime


def _open(**kwargs: Any) -> worker_client.ProviderRuntimeHandle:
    kwargs.setdefault("policy", TEST_ALLOW_POLICY)
    kwargs.setdefault("environ", _allow_env())
    kwargs.setdefault("core_executable", NONEXISTENT_CORE)
    kwargs.setdefault("worker_script", FAKE_WORKER)
    kwargs.setdefault("startup_timeout", 10.0)
    kwargs.setdefault("request_timeout", 10.0)
    kwargs.setdefault("shutdown_timeout", 5.0)
    return _REAL_OPEN_PROVIDER_RUNTIME(session=TARGET, **kwargs)


@pytest.fixture
def popen_counter(monkeypatch):
    calls: list[list[str]] = []
    real_popen = subprocess.Popen

    def counting_popen(argv, *args, **kwargs):
        calls.append(list(argv))
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(worker_client.subprocess, "Popen", counting_popen)
    return calls


# =============================================================================================
# 1. Runtime-state contract
# =============================================================================================


def test_runtime_state_vocabulary_is_exactly_the_twelve_owner_states():
    assert rt.RUNTIME_STATES == (
        "AVAILABLE", "NOT_CONFIGURED", "SECURITY_REVIEW_BLOCKED", "NOT_INSTALLED", "IMPORT_FAILED",
        "STARTUP_FAILED", "STARTUP_TIMEOUT", "PROTOCOL_VIOLATION", "PROCESS_CRASHED", "AUTH_FAILED",
        "RATE_LIMITED", "UNAVAILABLE_CAUSE_UNKNOWN",
    )
    assert "DATA_QUALITY_FAILED" not in rt.RUNTIME_STATES  # evidence axis, never runtime
    assert contract.LICENSE_DATA_QUALITY_FAILED == "DATA_QUALITY_FAILED"


def test_runtime_state_record_is_deterministic_json_safe_and_validated():
    first = rt.runtime_state_record(rt.NOT_CONFIGURED, rt.REASON_INTERPRETER_UNSET, detail={"b": 1, "a": 2})
    second = rt.runtime_state_record(rt.NOT_CONFIGURED, rt.REASON_INTERPRETER_UNSET, detail={"a": 2, "b": 1})
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["available"] is False and first["authority_effect"] == "NONE_OPERATIONAL_METADATA_ONLY"
    with pytest.raises(rt.ProviderRuntimeContractError):
        rt.runtime_state_record("DATA_QUALITY_FAILED", "x")
    with pytest.raises(rt.ProviderRuntimeContractError, match="WITHOUT_READY_HANDSHAKE"):
        rt.runtime_state_record(rt.IMPORT_FAILED, "x", runtime_info={"vnstock": "1"})


def test_runtime_contract_failure_class_literals_match_the_worker_protocol():
    assert set(rt._FAILURE_CLASS_TO_STATE) == {
        protocol.FAILURE_CLASS_PROTOCOL_VIOLATION, protocol.FAILURE_CLASS_PROCESS_EXIT,
        protocol.FAILURE_CLASS_TIMEOUT, protocol.FAILURE_CLASS_REQUEST_PROCESSING_EXCEPTION,
    }
    assert protocol.FAILURE_CLASS_STARTUP_FAILURE == "WORKER_STARTUP_FAILURE"
    for name in ("PACKAGE_NOT_INSTALLED", "IMPORT_FAILED", "STARTUP_EXCEPTION", "SPAWN_FAILED",
                 "STARTUP_TIMEOUT", "EXITED_BEFORE_READY"):
        assert getattr(protocol, f"STARTUP_KIND_{name}") == getattr(rt, f"STARTUP_KIND_{name}")


# =============================================================================================
# 2. Owner policy (D1)
# =============================================================================================


def test_tracked_default_policy_is_security_review_blocked():
    policy = rt.load_provider_policy()
    assert policy.policy == rt.POLICY_SECURITY_REVIEW_BLOCKED
    assert policy.allows_launch is False
    assert policy.source.startswith("TRACKED_POLICY_FILE")
    assert "quarantined" in (policy.evidence_ref or "")


@pytest.mark.parametrize("content", [
    None, "{not json", json.dumps({"contract_version": "other"}),
    json.dumps({"contract_version": rt.POLICY_CONTRACT_VERSION, "providers": {}}),
    json.dumps({"contract_version": rt.POLICY_CONTRACT_VERSION,
                "providers": {rt.PROVIDER_FAMILY_VNSTOCK_KBS_VCI: {"policy": "ALLOW_EVERYTHING"}}}),
    json.dumps({"contract_version": rt.POLICY_CONTRACT_VERSION,
                "providers": {rt.PROVIDER_FAMILY_VNSTOCK_KBS_VCI: {
                    "policy": rt.POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME,
                    "allowed_provider_env": ["DNSE_API_KEY"]}}}),
])
def test_missing_or_invalid_policy_fails_closed_to_security_review_blocked(tmp_path, content):
    path = tmp_path / "policy.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    policy = rt.load_provider_policy(path)
    assert policy.policy == rt.POLICY_SECURITY_REVIEW_BLOCKED
    assert policy.load_reason_code == rt.REASON_POLICY_MISSING_OR_INVALID


def test_explicit_owner_allow_policy_is_parsed(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"contract_version": rt.POLICY_CONTRACT_VERSION, "providers": {
        rt.PROVIDER_FAMILY_VNSTOCK_KBS_VCI: {"policy": rt.POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME,
                                             "reason": "owner approved", "allowed_provider_env": ["VNSTOCK_API_KEY"]},
    }}), encoding="utf-8")
    policy = rt.load_provider_policy(path)
    assert policy.allows_launch is True and policy.allowed_provider_env == ("VNSTOCK_API_KEY",)


def test_blocked_policy_spawns_zero_provider_processes_even_with_an_installed_interpreter(popen_counter):
    # A valid, existing provider interpreter is configured -- the tracked blocked policy still wins.
    handle = worker_client.open_provider_runtime(
        session=TARGET, environ=_allow_env(), core_executable=NONEXISTENT_CORE, worker_script=FAKE_WORKER,
    )
    assert handle.state["state"] == rt.SECURITY_REVIEW_BLOCKED
    assert handle.state["reason_code"] == rt.REASON_POLICY_SECURITY_REVIEW_BLOCKED
    assert handle.fetcher is None and handle.available is False
    assert popen_counter == []


def test_a_fetcher_can_never_be_constructed_under_a_blocked_policy():
    with pytest.raises(rt.ProviderRuntimeContractError, match="DOES_NOT_ALLOW_LAUNCH"):
        worker_client.VnstockWorkerFetcher(python_executable=sys.executable, policy=rt.load_provider_policy())
    with pytest.raises(TypeError):
        worker_client.VnstockWorkerFetcher(policy=TEST_ALLOW_POLICY)  # no default interpreter
    with pytest.raises(rt.ProviderRuntimeContractError, match="PROVIDER_INTERPRETER_REQUIRED"):
        worker_client.VnstockWorkerFetcher(python_executable="", policy=TEST_ALLOW_POLICY)


# =============================================================================================
# 3. Dedicated provider interpreter (D3)
# =============================================================================================


def test_unset_provider_interpreter_is_not_configured_and_never_falls_back(popen_counter):
    env = _allow_env()
    env.pop(rt.PROVIDER_PYTHON_ENV)
    handle = _open(environ=env, core_executable=sys.executable)
    assert handle.state["state"] == rt.NOT_CONFIGURED
    assert handle.state["reason_code"] == rt.REASON_INTERPRETER_UNSET
    assert popen_counter == []


def test_missing_provider_interpreter_path_is_not_configured(tmp_path, popen_counter):
    handle = _open(environ=_allow_env(**{rt.PROVIDER_PYTHON_ENV: str(tmp_path / "absent-python")}))
    assert (handle.state["state"], handle.state["reason_code"]) == (rt.NOT_CONFIGURED, rt.REASON_INTERPRETER_NOT_FOUND)
    assert popen_counter == []


def test_provider_interpreter_identical_to_the_core_interpreter_is_refused(popen_counter):
    handle = _open(core_executable=sys.executable)
    assert (handle.state["state"], handle.state["reason_code"]) == (rt.NOT_CONFIGURED, rt.REASON_INTERPRETER_IS_CORE)
    assert popen_counter == []


def test_configured_provider_interpreter_starts_and_reports_versions_only_after_ready(popen_counter):
    handle = _open()
    try:
        assert handle.available is True
        assert handle.state["state"] == rt.AVAILABLE
        assert handle.state["runtime_info"]["provider_distributions"] == {"vnstock": "fake-0", "vnai": "fake-0"}
        assert len(popen_counter) == 1
        argv = popen_counter[0]
        # The configured interpreter is the one spawned. resolve_provider_interpreter normalises the
        # path (os.path.normcase lowercases it on Windows), so compare as paths, not raw strings.
        assert os.path.samefile(argv[0], sys.executable)
        assert os.path.normcase(os.path.abspath(argv[0])) == os.path.normcase(os.path.abspath(sys.executable))
        assert argv[1:6] == ["-s", "-E", "-X", "utf8", "-u"]
        assert argv[-1] == str(FAKE_WORKER)
    finally:
        handle.shutdown()


# =============================================================================================
# 4. Startup / operation failure classification
# =============================================================================================


@pytest.mark.parametrize(("extra_env", "expected_state", "expected_reason"), [
    ({"FAKE_WORKER_STARTUP_KIND": "PROVIDER_PACKAGE_NOT_INSTALLED"}, rt.NOT_INSTALLED, rt.REASON_PACKAGE_NOT_INSTALLED),
    ({"FAKE_WORKER_STARTUP_KIND": "PROVIDER_IMPORT_FAILED"}, rt.IMPORT_FAILED, rt.REASON_IMPORT_FAILED),
    ({"FAKE_WORKER_STARTUP_FAIL": "1"}, rt.STARTUP_FAILED, rt.REASON_EXITED_BEFORE_READY),
    ({"FAKE_WORKER_READY_GARBAGE": "1"}, rt.PROTOCOL_VIOLATION, rt.REASON_PROTOCOL_VIOLATION),
])
def test_startup_failures_map_to_their_exact_runtime_state(extra_env, expected_state, expected_reason):
    handle = _open(extra_env=extra_env)
    assert handle.fetcher is None
    assert (handle.state["state"], handle.state["reason_code"]) == (expected_state, expected_reason)
    assert handle.state["runtime_info"] is None  # no version without a READY handshake


def test_startup_timeout_is_startup_timeout():
    handle = _open(extra_env={"FAKE_WORKER_STARTUP_HANG": "1"}, startup_timeout=1.0)
    assert (handle.state["state"], handle.state["reason_code"]) == (rt.STARTUP_TIMEOUT, rt.REASON_STARTUP_TIMEOUT)


def test_spawn_failure_is_startup_failed(tmp_path):
    fake_interpreter = tmp_path / "not-an-executable"
    fake_interpreter.write_text("", encoding="utf-8")
    handle = _open(environ=_allow_env(**{rt.PROVIDER_PYTHON_ENV: str(fake_interpreter)}))
    assert (handle.state["state"], handle.state["reason_code"]) == (rt.STARTUP_FAILED, rt.REASON_SPAWN_FAILED)


def test_real_worker_reports_not_installed_without_importing_any_provider_package():
    def _findable(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except ImportError:  # the hermetic provider-import block
            return False

    if any(_findable(name) for name in ("vnstock", "vnai")):
        pytest.skip("provider packages are importable here; this check must never execute them")
    handle = _open(worker_script=REAL_WORKER, startup_timeout=30.0)
    assert handle.state["state"] == rt.NOT_INSTALLED
    assert handle.state["detail"]["missing_packages"] == ["vnai", "vnstock"]


def test_mid_operation_crash_and_request_timeout_are_classified():
    handle = _open()
    with pytest.raises(protocol.VnstockWorkerFailure):
        handle.fetcher.fetch("__CRASH_HARD__", "KBS", "2026-09-01", TARGET)
    assert handle.final_state()["state"] == rt.PROCESS_CRASHED
    handle.shutdown()

    handle = _open(request_timeout=1.0)
    with pytest.raises(protocol.VnstockWorkerTimeoutError):
        handle.fetcher.fetch("__HANG_FOREVER__", "KBS", "2026-09-01", TARGET)
    final = handle.final_state()
    assert (final["state"], final["reason_code"]) == (rt.UNAVAILABLE_CAUSE_UNKNOWN, rt.REASON_REQUEST_TIMEOUT)
    handle.shutdown()


@pytest.mark.parametrize(("tickers", "expected"), [
    (["AUTH_A", "AUTH_B"], rt.AUTH_FAILED),
    (["RATELIMIT_A", "RATELIMIT_B"], rt.RATE_LIMITED),
    (["AUTH_A", "EXACT_A"], rt.AVAILABLE),
    (["MISSING_A"], rt.AVAILABLE),
])
def test_auth_and_rate_limit_are_asserted_only_on_explicit_signals(tickers, expected):
    handle = _open()
    try:
        for ticker in tickers:
            handle.fetcher.fetch(ticker, "KBS", "2026-09-01", TARGET)
        assert handle.final_state()["state"] == expected
    finally:
        handle.shutdown()


# =============================================================================================
# 5. Credential / environment isolation
# =============================================================================================


def test_build_provider_environment_is_an_explicit_allow_list():
    parent = {"PATH": "/bin", "LANG": "C.UTF-8", "HTTPS_PROXY": "http://proxy", "PYTHONPATH": "/x",
              "RANDOM_APP_SETTING": "1", "VNSTOCK_API_KEY": "synthetic-provider-key", **SYNTHETIC_SECRETS}
    env = rt.build_provider_environment(parent)
    assert set(env) == {"PATH", "LANG", "HTTPS_PROXY"}
    allowed = rt.build_provider_environment(parent, allowed_provider_env=("VNSTOCK_API_KEY",))
    assert allowed["VNSTOCK_API_KEY"] == "synthetic-provider-key"
    assert not set(SYNTHETIC_SECRETS) & set(allowed)
    with pytest.raises(rt.ProviderRuntimeContractError, match="DENIED_FAMILY"):
        rt.build_provider_environment(parent, allowed_provider_env=("LIVESPEED_API_KEY",))
    for name in ("DNSE_X", "EXTRA_TOKEN", "EXTRA_SECRET", "EXTRA_PASSWORD"):
        with pytest.raises(rt.ProviderRuntimeContractError, match="EXTRA_DENIED"):
            rt.build_provider_environment(parent, extra={name: "v"})
    assert rt.build_provider_environment(parent, extra={"FAKE_WORKER_REPORT_ENV": "1"})["FAKE_WORKER_REPORT_ENV"] == "1"


def test_provider_worker_never_inherits_parent_credentials_or_python_path():
    parent = _allow_env(PYTHONPATH="/should/not/leak", **SYNTHETIC_SECRETS)
    handle = _open(environ=parent, extra_env={"FAKE_WORKER_REPORT_ENV": "1"})
    try:
        runtime = handle.fetcher.runtime_info
    finally:
        handle.shutdown()
    child_env = runtime["environment"]
    leaked_names = sorted(set(SYNTHETIC_SECRETS) & set(child_env))
    leaked_values = sorted(v for v in SYNTHETIC_SECRETS.values() if v in json.dumps(child_env))
    assert leaked_names == [] and leaked_values == []  # DNSE_CREDENTIAL_LEAK_TO_PROVIDER_PROCESS = NO
    assert "PYTHONPATH" not in child_env and rt.PROVIDER_PYTHON_ENV not in child_env
    assert runtime["flags"] == {"no_user_site": 1, "ignore_environment": 1, "utf8_mode": 1}
    assert Path(runtime["cwd"]).resolve() != ROOT.resolve()


def test_fetcher_default_parent_environment_is_os_environ_but_still_scrubbed(monkeypatch):
    for key, value in SYNTHETIC_SECRETS.items():
        monkeypatch.setenv(key, value)
    fetcher = fake_fetcher(env={"FAKE_WORKER_REPORT_ENV": "1"})
    try:
        fetcher.start()
        child_env = fetcher.runtime_info["environment"]
    finally:
        fetcher.shutdown()
    assert not set(SYNTHETIC_SECRETS) & set(child_env)


# =============================================================================================
# 6. DNSE quality license + resolver scenarios (fake worker transport)
# =============================================================================================


def _dnse_obs(session: str, *, agree: bool = True) -> dict:
    close = 10.1 if agree else 12.0
    return {"session": session, "open": 10.0 if agree else 12.0, "high": 10.2 if agree else 12.0,
            "low": 9.9 if agree else 12.0, "close": close, "volume": 123456,
            "provider": "DNSE", "dataset": "DNSE_OHLC_1D"}


def _dnse_snapshot(spec: dict[str, tuple[str, list]]) -> dict:
    records = {}
    for ticker, (disposition, observations) in spec.items():
        records[ticker] = {
            "status": "OBSERVED" if disposition == "EXACT_SESSION_RETAINED" else disposition,
            "reason": None if disposition == "EXACT_SESSION_RETAINED" else disposition,
            "disposition": disposition, "observations": observations,
            "payload_hash": f"hash-{ticker}" if observations else None,
            "request": {"symbol": ticker}, "provider_endpoint": "/price/ohlc" if observations else None,
        }
    return {
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "requested_at": REQUESTED_AT, "target_session": TARGET,
        "candidate_count": len(records), "attempted_candidate_count": len(records),
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET", "unattempted_without_explicit_disposition": 0,
        "source": {"provider": "DNSE"}, "records": records,
        "snapshot_identity": "p3f9_exact_session_snapshot:testhash",
    }


def _resolve(dnse_snapshot: dict, sentinel: list[str], *, runtime_state: dict | None = None):
    previous = get_active_governor()
    fetcher = None if runtime_state is not None else fake_fetcher()
    try:
        return resolve_exact_session_with_autorecovery(
            dnse_snapshot=dnse_snapshot, target_session=TARGET, requested_at=REQUESTED_AT,
            sentinel_cohort=sentinel, request_delay=0.0, sleep_fn=lambda _s: None,
            fetch_single_source=fetcher.fetch if fetcher else None,
            rate_governor=fetcher if fetcher else None,
            supplemental_runtime_state=runtime_state,
        )
    finally:
        if fetcher is not None:
            fetcher.shutdown()
        set_active_governor(previous)


def test_secondary_corroborates_clean_dnse_is_corroborated_healthy():
    evidence, _ = _resolve(_dnse_snapshot({"EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)])}), ["EXACT_A"])
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["qualifies_for_ordinary_daily"]) == ("CORROBORATED_HEALTHY", True)


def test_isolated_secondary_conflict_is_isolated_conflict_resolved():
    snapshot = _dnse_snapshot({"EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, agree=False)])})
    evidence, _ = _resolve(snapshot, ["EXACT_A"])
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_MATERIAL_CONFLICT"
    assert contract.dnse_quality_license(evidence)["license"] == "ISOLATED_CONFLICT_RESOLVED"


def test_runtime_live_but_no_secondary_observation_reproduces_and_closes_the_uncorroborated_hole():
    # Worker starts and answers, but KBS/VCI have no exact bar for any sentinel member.
    snapshot = _dnse_snapshot({"MISSING_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]),
                               "MISSING_B": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)])})
    evidence, projected = _resolve(snapshot, ["MISSING_A", "MISSING_B"])
    # The pre-V1 route: the sentinel verdict is DNSE_EXACT_BUT_UNCORROBORATED ...
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_EXACT_BUT_UNCORROBORATED"
    # ... which V1 no longer treats as a healthy ordinary-Daily license (owner decision D2).
    license_ = contract.dnse_quality_license(evidence)
    assert license_["license"] == "UNASSESSED_NO_SECONDARY_OBSERVATION"
    assert license_["qualifies_for_ordinary_daily"] is False
    # DNSE raw evidence is preserved, not invalidated.
    assert projected["records"]["MISSING_A"]["disposition"] == "EXACT_SESSION_RETAINED"
    assert license_["dnse_raw_evidence_status"] == "RETAINED_UNCHANGED"


def test_runtime_unavailable_records_every_recovery_and_sentinel_as_not_attempted():
    snapshot = _dnse_snapshot({
        "EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]),
        "GAP_B": ("SESSION_MISSING", []),
    })
    state = rt.runtime_state_record(rt.SECURITY_REVIEW_BLOCKED, rt.REASON_POLICY_SECURITY_REVIEW_BLOCKED)
    evidence, projected = _resolve(snapshot, ["EXACT_A"], runtime_state=state)
    assert evidence["recovery_attempts"] == {"VCI": 0, "KBS": 0}
    for ticker in ("EXACT_A", "GAP_B"):
        secondary = [o for o in evidence["records"][ticker]["observations"] if o["source"] != "DNSE"]
        assert {o["source"] for o in secondary} == {"VCI", "KBS"}
        assert all(o["status"] == "NOT_APPLICABLE" for o in secondary)
        assert all(o["reason_code"].startswith("NOT_ATTEMPTED_SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE") for o in secondary)
    gap = evidence["records"]["GAP_B"]["resolution"]
    assert gap["resolution"] == "SESSION_MISSING_DNSE_SUPPLEMENTAL_NOT_ATTEMPTED"  # never ALL_SOURCES_MISSING
    assert projected["records"]["GAP_B"]["multi_source_recovery_result"] == "SUPPLEMENTAL_RECOVERY_NOT_ATTEMPTED_RUNTIME_UNAVAILABLE"
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_QUALITY_UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_NOT_EVALUABLE
    assert contract.dnse_quality_license(evidence)["license"] == "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"
    # DNSE's own observation is untouched.
    dnse = [o for o in evidence["records"]["EXACT_A"]["observations"] if o["source"] == "DNSE"][0]
    assert dnse["status"] == "EXACT_SESSION_OBSERVED"
    assert projected["records"]["EXACT_A"]["observations"] == snapshot["records"]["EXACT_A"]["observations"]


def test_runtime_unavailable_residual_yield_probe_is_not_evaluated_not_inferred():
    snapshot = _dnse_snapshot({"GAP_A": ("SESSION_MISSING", []), "GAP_B": ("SESSION_MISSING", [])})
    state = rt.runtime_state_record(rt.NOT_CONFIGURED, rt.REASON_INTERPRETER_UNSET)
    previous = get_active_governor()
    try:
        evidence, _ = resolve_exact_session_with_autorecovery(
            dnse_snapshot=snapshot, target_session=TARGET, requested_at=REQUESTED_AT, sentinel_cohort=[],
            residual_yield_sentinel_tickers=["GAP_A"], request_delay=0.0, sleep_fn=lambda _s: None,
            supplemental_runtime_state=state,
        )
    finally:
        set_active_governor(previous)
    assert evidence["residual_gap_sentinel"]["decision"] == "NOT_EVALUATED_SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE"


def test_dnse_broad_anomaly_with_completed_recovery_is_broad_stale_recovered():
    tickers = [f"EXACT_{i}" for i in range(6)]
    snapshot = _dnse_snapshot({t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, agree=False)]) for t in tickers})
    evidence, _ = _resolve(snapshot, tickers[:5])
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    assert contract.dnse_quality_license(evidence)["license"] == "BROAD_STALE_RECOVERED"
    assert contract.dnse_quality_license(evidence, degraded_recovery_mode=None)["license"] == "BROAD_STALE_RECOVERED"
    assert contract.dnse_quality_license(evidence, degraded_recovery_mode="NOT_TRIGGERED")["license"] == "DATA_QUALITY_FAILED"


# --- A material conflict licenses ordinary Daily only when every conflict is proven resolved ---


def _exact_obs(ticker: str, source: str, close: float) -> dict:
    return contract.build_source_observation(
        ticker=ticker, requested_session=TARGET, observed_session=TARGET, source=source,
        provider_interface="TEST", retrieved_at=REQUESTED_AT, status=contract.STATUS_EXACT_SESSION_OBSERVED,
        native={"open": close, "high": close, "low": close, "close": close, "volume": 1000},
    )


def _conflict_evidence(spec: dict[str, tuple[float, float, float]], *, reverse: bool = False) -> dict:
    """Sentinel evidence built with the contract's own resolver/classifier from (DNSE, VCI, KBS) closes."""
    tickers = sorted(spec, reverse=reverse)
    observations = {}
    for ticker in tickers:
        dnse, vci, kbs = spec[ticker]
        rows = [_exact_obs(ticker, "DNSE", dnse), _exact_obs(ticker, "VCI", vci), _exact_obs(ticker, "KBS", kbs)]
        observations[ticker] = list(reversed(rows)) if reverse else rows
    return {
        "target_session": TARGET,
        "dnse_exact_session_count": len(tickers),
        "dnse_quality_sentinel": {"cohort_tickers": tickers,
                                  "health": contract.classify_dnse_provider_health(observations)},
        "degraded_provider_recovery": {"mode": "NOT_TRIGGERED"},
        "records": {t: {"observations": observations[t], "resolution": contract.resolve_ticker(t, observations[t])}
                    for t in tickers},
    }


RESOLVED_CONFLICTS = {"CLEAN": (10.1, 10.1, 10.1), "OK_1": (10.1, 12.0, 12.0), "OK_2": (20.0, 25.0, 25.0)}
# VCI and KBS disagree with each other and with DNSE: SOURCE_CONFLICT, never a justified value.
UNRESOLVED = {**RESOLVED_CONFLICTS, "BAD": (10.1, 12.0, 14.0)}


def test_material_conflict_with_every_conflict_resolved_is_isolated_conflict_resolved():
    evidence = _conflict_evidence(RESOLVED_CONFLICTS)
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_MATERIAL_CONFLICT"
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["qualifies_for_ordinary_daily"]) == ("ISOLATED_CONFLICT_RESOLVED", True)
    assert license_["conflict_resolution"]["resolved_conflict_tickers"] == ["OK_1", "OK_2"]
    assert license_["conflict_resolution"]["unresolved_conflict_tickers"] == []


def test_material_conflict_with_one_unresolved_conflict_is_not_licensed():
    evidence = _conflict_evidence(UNRESOLVED)
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_MATERIAL_CONFLICT"
    assert evidence["records"]["BAD"]["resolution"]["resolution"] == "SOURCE_CONFLICT"
    license_ = contract.dnse_quality_license(evidence)
    assert license_["license"] == "DATA_QUALITY_FAILED"
    assert license_["reason_code"] == "SENTINEL_MATERIAL_CONFLICT_UNRESOLVED"
    assert license_["qualifies_for_ordinary_daily"] is False
    assert license_["conflict_resolution"]["unresolved_conflict_tickers"] == ["BAD"]


@pytest.mark.parametrize("spec", [RESOLVED_CONFLICTS, UNRESOLVED])
def test_conflict_resolution_license_is_row_and_order_invariant(spec):
    assert contract.dnse_quality_license(_conflict_evidence(spec)) == contract.dnse_quality_license(
        _conflict_evidence(spec, reverse=True))


def test_published_resolution_must_agree_with_the_rederived_one():
    evidence = _conflict_evidence(RESOLVED_CONFLICTS)
    evidence["records"]["OK_1"]["resolution"] = {**evidence["records"]["OK_1"]["resolution"], "resolution": "SOURCE_CONFLICT"}
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["reason_code"]) == ("DATA_QUALITY_FAILED", "SENTINEL_MATERIAL_CONFLICT_UNRESOLVED")


def test_conflict_count_that_the_observations_cannot_reproduce_is_not_proven():
    evidence = _conflict_evidence(RESOLVED_CONFLICTS)
    evidence["dnse_quality_sentinel"]["health"]["conflict_count"] = 3
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["reason_code"]) == ("DATA_QUALITY_FAILED", "SENTINEL_MATERIAL_CONFLICT_RESOLUTION_NOT_PROVEN")
    del evidence["records"]["OK_2"]
    evidence["dnse_quality_sentinel"]["health"]["conflict_count"] = 2
    assert contract.dnse_quality_license(evidence)["qualifies_for_ordinary_daily"] is False


def test_unresolved_conflict_refuses_snapshot_reuse(tmp_path):
    snapshot_path, evidence_path = tmp_path / "snapshot.json", tmp_path / "evidence.json"
    snapshot_path.write_text(json.dumps({"degraded_provider_recovery": {"mode": "NOT_TRIGGERED"}}), encoding="utf-8")
    evidence_path.write_text(json.dumps(_conflict_evidence(RESOLVED_CONFLICTS)), encoding="utf-8")
    assert level2._canonical_snapshot_gate_satisfied(snapshot_path, evidence_path, TARGET) is True
    evidence_path.write_text(json.dumps(_conflict_evidence(UNRESOLVED)), encoding="utf-8")
    assert level2._canonical_snapshot_gate_satisfied(snapshot_path, evidence_path, TARGET) is False


def test_unresolved_conflict_blocks_ordinary_daily_acquisition(tmp_path, monkeypatch):
    import multi_source_exact_session_resolver as resolver

    _level2_acquire(tmp_path, monkeypatch, handle=available_handle(), dnse_records={
        "EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]),
    })
    monkeypatch.setattr(resolver, "resolve_exact_session_with_autorecovery",
                        lambda **_kw: (_conflict_evidence(UNRESOLVED), {"records": {}}))
    with pytest.raises(level2.SupplementalProviderBlocked) as exc:
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    assert exc.value.kind == level2.SUPPLEMENTAL_BLOCK_KIND_QUALITY
    assert exc.value.quality_license["license"] == "DATA_QUALITY_FAILED"
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    assert not paths["exact_session_snapshot"].exists() and not paths["multi_source_market_evidence"].exists()


@pytest.mark.retained_evidence(
    "operations-review/p3f9b-market-wide-exact-session-scaleout-20260911/multi_source_exact_session_market_evidence.json",
    "operations-review/p3f9b-market-wide-exact-session-scaleout-20260915/multi_source_exact_session_market_evidence.json",
)
@pytest.mark.parametrize(("nodash", "resolved"), [("20260911", 4), ("20260915", 11)])
def test_retained_isolated_conflict_sessions_still_qualify(nodash, resolved):
    path = ROOT / f"operations-review/p3f9b-market-wide-exact-session-scaleout-{nodash}/multi_source_exact_session_market_evidence.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))  # read only
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["qualifies_for_ordinary_daily"]) == ("ISOLATED_CONFLICT_RESOLVED", True)
    assert len(license_["conflict_resolution"]["resolved_conflict_tickers"]) == resolved
    assert license_["conflict_resolution"]["unresolved_conflict_tickers"] == []


@pytest.mark.parametrize(("evidence", "expected", "qualifies"), [
    ({}, "NOT_EVALUATED_NO_QUALITY_SENTINEL", False),
    ({"dnse_exact_session_count": 0, "dnse_quality_sentinel": {"cohort_tickers": [], "health": {
        "state": "DNSE_EXACT_BUT_UNCORROBORATED"}}}, "NOT_REQUIRED_NO_DNSE_EXACT_BAR", True),
    ({"dnse_exact_session_count": 3, "dnse_quality_sentinel": {"cohort_tickers": ["A"], "health": {
        "state": "DNSE_EXACT_BUT_UNCORROBORATED"}},
      "records": {"A": {"observations": [{"source": "KBS", "status": "MALFORMED"}]}}}, "DATA_QUALITY_FAILED", False),
    ({"dnse_quality_sentinel": {"health": {"state": "SOMETHING_NEW"}}}, "NOT_EVALUATED_NO_QUALITY_SENTINEL", False),
])
def test_quality_license_edge_cases(evidence, expected, qualifies):
    license_ = contract.dnse_quality_license(evidence)
    assert (license_["license"], license_["qualifies_for_ordinary_daily"]) == (expected, qualifies)


def test_quality_license_is_a_separate_axis_from_evidence_currency():
    assert contract.ORDINARY_DAILY_QUALIFYING_LICENSES.isdisjoint({
        "UNASSESSED_NO_SECONDARY_OBSERVATION", "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE", "DATA_QUALITY_FAILED",
    })
    license_ = contract.dnse_quality_license(healthy_sentinel_evidence(TARGET))
    assert license_["evidence_currency_relation"] == "SEPARATE_AXIS_CURRENT_SESSION_IS_NOT_CORROBORATION"
    import integrated_investment_decision_product as iid

    assert iid.EVIDENCE_CURRENCY_CURRENT_SESSION == "CURRENT_SESSION"  # vocabulary unchanged


# =============================================================================================
# 7. Level-2 acquisition boundary: governed block, raw DNSE evidence preserved
# =============================================================================================


def _level2_acquire(tmp_path, monkeypatch, *, handle: Any | None, dnse_records: dict) -> dict:
    """Run the real ensure_exact_session_snapshot with a synthetic DNSE Pass 1 and the real resolver."""
    import dnse_access
    import dnse_secrets_env
    import mva_exact_session_snapshot as snapshotter

    snapshot = _dnse_snapshot(dnse_records)
    monkeypatch.setattr(snapshotter, "canonical_candidates", lambda _root: list(dnse_records))
    monkeypatch.setattr(dnse_secrets_env, "ensure_credentials_loaded", lambda *a, **k: {"configured": True})
    monkeypatch.setattr(dnse_access, "credentials_for_request", lambda *a, **k: ("synthetic", "synthetic"))
    monkeypatch.setattr(snapshotter, "materialize_snapshot", lambda **_kw: json.loads(json.dumps(snapshot)))
    if handle is not None:
        monkeypatch.setattr(worker_client, "open_provider_runtime", lambda **_kw: handle)
    return snapshot


def test_blocked_runtime_ends_in_a_governed_runtime_block_and_retains_dnse_evidence(tmp_path, monkeypatch, popen_counter):
    # No open_provider_runtime patch: the real tracked SECURITY_REVIEW_BLOCKED policy applies.
    _level2_acquire(tmp_path, monkeypatch, handle=None, dnse_records={
        "EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]), "GAP_B": ("SESSION_MISSING", []),
    })
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    with pytest.raises(level2.SupplementalProviderBlocked) as exc:
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    assert exc.value.kind == level2.SUPPLEMENTAL_BLOCK_KIND_RUNTIME
    assert exc.value.runtime_state["state"] == rt.SECURITY_REVIEW_BLOCKED
    assert exc.value.quality_license["license"] == "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"
    assert popen_counter == []
    assert paths["dnse_only_exact_session_snapshot"].is_file()  # raw DNSE retained
    assert not paths["exact_session_snapshot"].exists()  # never a reusable canonical snapshot
    assert not paths["multi_source_market_evidence"].exists()
    block = json.loads(paths["supplemental_provider_block"].read_text(encoding="utf-8"))
    assert block["ordinary_daily"] == "BLOCKED" and block["degraded_publication"] == "NOT_IMPLEMENTED_V1"
    assert block["multi_source_evidence"]["records"]["GAP_B"]["resolution"]["resolution"] == (
        "SESSION_MISSING_DNSE_SUPPLEMENTAL_NOT_ATTEMPTED"
    )
    assert block["block_identity"].startswith("supplemental_provider_block:")


def test_live_runtime_without_secondary_observation_is_a_governed_quality_block(tmp_path, monkeypatch):
    fetcher = fake_fetcher()
    fetcher.start()
    _level2_acquire(tmp_path, monkeypatch, handle=available_handle(fetcher), dnse_records={
        "MISSING_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]),
    })
    with pytest.raises(level2.SupplementalProviderBlocked) as exc:
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    assert exc.value.kind == level2.SUPPLEMENTAL_BLOCK_KIND_QUALITY
    assert exc.value.runtime_state["state"] == rt.AVAILABLE
    assert exc.value.quality_license["license"] == "UNASSESSED_NO_SECONDARY_OBSERVATION"
    assert not level2.session_artifact_paths(tmp_path, TARGET)["exact_session_snapshot"].exists()


def test_mid_operation_worker_crash_is_a_governed_runtime_block(tmp_path, monkeypatch):
    fetcher = fake_fetcher()
    fetcher.start()
    _level2_acquire(tmp_path, monkeypatch, handle=available_handle(fetcher), dnse_records={
        "__CRASH_HARD__": ("SESSION_MISSING", []),
    })
    with pytest.raises(level2.SupplementalProviderBlocked) as exc:
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    assert exc.value.kind == level2.SUPPLEMENTAL_BLOCK_KIND_RUNTIME
    assert exc.value.runtime_state["state"] == rt.PROCESS_CRASHED


def test_qualified_run_writes_the_snapshot_with_both_axes_stamped(tmp_path, monkeypatch):
    fetcher = fake_fetcher()
    fetcher.start()
    _level2_acquire(tmp_path, monkeypatch, handle=available_handle(fetcher), dnse_records={
        "EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)]),
    })
    path = level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["provider_runtime_state"] == rt.AVAILABLE
    assert written["dnse_quality_license"]["license"] == "CORROBORATED_HEALTHY"
    evidence = json.loads(level2.session_artifact_paths(tmp_path, TARGET)["multi_source_market_evidence"].read_text())
    assert evidence["provider_runtime"]["state"] == rt.AVAILABLE
    assert evidence["dnse_quality_license"]["qualifies_for_ordinary_daily"] is True


# =============================================================================================
# 8. Reuse / resume / replay safety
# =============================================================================================


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_reuse_gate_refuses_unassessed_or_foreign_session_evidence(tmp_path):
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _write(paths["exact_session_snapshot"], {"resolved_completed_session": TARGET})
    evidence_path = paths["multi_source_market_evidence"]
    gate = level2._canonical_snapshot_gate_satisfied

    _write(evidence_path, healthy_sentinel_evidence(TARGET))
    assert gate(paths["exact_session_snapshot"], evidence_path, TARGET) is True
    # A pre-V1 snapshot written through the uncorroborated route is never reused as ordinary.
    uncorroborated = healthy_sentinel_evidence(TARGET)
    uncorroborated["dnse_quality_sentinel"]["health"] = {"state": "DNSE_EXACT_BUT_UNCORROBORATED"}
    _write(evidence_path, uncorroborated)
    assert gate(paths["exact_session_snapshot"], evidence_path, TARGET) is False
    # A prior session's healthy corroboration never licenses this session.
    _write(evidence_path, healthy_sentinel_evidence("2026-09-09"))
    assert gate(paths["exact_session_snapshot"], evidence_path, TARGET) is False
    evidence_path.write_text("{corrupt", encoding="utf-8")
    assert gate(paths["exact_session_snapshot"], evidence_path, TARGET) is False


def test_same_session_rerun_cannot_upgrade_an_unassessed_snapshot(tmp_path):
    paths = level2.session_artifact_paths(tmp_path, TARGET)
    _write(paths["exact_session_snapshot"], {"resolved_completed_session": TARGET})
    unassessed = healthy_sentinel_evidence(TARGET)
    unassessed["dnse_quality_sentinel"]["health"] = {"state": "DNSE_QUALITY_UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE"}
    # Even a stored label claiming a healthy license is ignored: the license is re-derived.
    unassessed["dnse_quality_license"] = {"license": "CORROBORATED_HEALTHY", "qualifies_for_ordinary_daily": True}
    _write(paths["multi_source_market_evidence"], unassessed)
    with pytest.raises(ValueError, match="P3F9B_EXISTING_SNAPSHOT_PROVIDER_HEALTH_GATE_UNRESOLVED"):
        level2.ensure_exact_session_snapshot(tmp_path, TARGET, tmp_path / "runtime")


def test_post_close_eligibility_gate_uses_the_license_and_session(tmp_path):
    from vn_time import VN_TZ
    from datetime import datetime

    paths = level2.session_artifact_paths(tmp_path, TARGET)
    snapshot = {
        "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2", "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0, "exact_session_observed_count": 900,
        "attempted_candidate_count": 1000, "requested_at": f"{TARGET}T19:00:00+07:00",
        "snapshot_sha256": "abc", "snapshot_identity": "p3f9_exact_session_snapshot:abc",
    }
    now = datetime(2026, 9, 10, 20, 0, tzinfo=VN_TZ)
    _write(paths["multi_source_market_evidence"], healthy_sentinel_evidence(TARGET))
    cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)
    uncorroborated = healthy_sentinel_evidence(TARGET)
    uncorroborated["dnse_quality_sentinel"]["health"] = {"state": "DNSE_EXACT_BUT_UNCORROBORATED"}
    _write(paths["multi_source_market_evidence"], uncorroborated)
    with pytest.raises(cpc.PreCutoffArtifactError, match="PROVIDER_HEALTH_GATE_NOT_SATISFIED"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)
    _write(paths["multi_source_market_evidence"], healthy_sentinel_evidence("2026-09-09"))
    with pytest.raises(cpc.PreCutoffArtifactError, match="EVIDENCE_SESSION_MISMATCH"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)
    paths["multi_source_market_evidence"].write_text("{corrupt", encoding="utf-8")
    with pytest.raises(cpc.PreCutoffArtifactError, match="EVIDENCE_UNREADABLE"):
        cpc.assert_post_close_eligible(snapshot, TARGET, now=now, artifact_root=tmp_path)


# =============================================================================================
# 9. Governed Daily stage, posture monotonicity, M1 eligibility
# =============================================================================================


def _block_error(kind: str) -> cpc.SupplementalProviderBlockError:
    state = rt.runtime_state_record(rt.SECURITY_REVIEW_BLOCKED, rt.REASON_POLICY_SECURITY_REVIEW_BLOCKED)
    license_ = {"license": "UNASSESSED_SUPPLEMENTAL_RUNTIME_UNAVAILABLE", "qualifies_for_ordinary_daily": False}
    return cpc.SupplementalProviderBlockError(
        f"REFUSE_CANONICAL_POST_CLOSE:{kind}", kind=kind, runtime_state=state,
        quality_license=license_, diagnostic_path=Path("block.json"),
    )


@pytest.mark.parametrize(("kind", "stage"), [
    ("SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE", "BLOCKED_SUPPLEMENTAL_PROVIDER_RUNTIME"),
    ("DNSE_QUALITY_LICENSE_NOT_QUALIFIED", "BLOCKED_DNSE_QUALITY_UNLICENSED"),
])
def test_daily_operation_maps_a_supplemental_block_to_its_governed_stage(tmp_path, monkeypatch, kind, stage):
    from test_canonical_daily_operation import _run

    def blocked_acquire(*_a, **_k):
        raise _block_error(kind)

    downstream = {"producer": 0}

    def producer(*_a, **_k):
        downstream["producer"] += 1
        raise AssertionError("no producer/decision/posture may run after a supplemental block")

    with pytest.raises(cdo.CanonicalDailyOperationError) as exc:
        _run(tmp_path, monkeypatch, acquire_fn=blocked_acquire, producer_fn=producer)
    assert exc.value.stage == stage
    assert exc.value.stage not in cdo.NOT_READY_STAGES  # not "rerun later"
    assert exc.value.stage != cdo.STAGE_FAILED_ACQUISITION_PIPELINE  # not a generic failure
    block = exc.value.local_state["supplemental_provider"]
    assert block["dnse_raw_evidence"] == "RETAINED" and block["publication"] == "NOT_ATTEMPTED"
    assert block["m1_live_acceptance_eligible"] is False
    # Posture monotonicity: the block happens before the producer, so no Integrated Decision /
    # research_action_posture artifact exists for this run -- losing supplemental qualification
    # can only remove authority, never produce a stronger posture.
    assert downstream["producer"] == 0
    assert cdo.m1_live_acceptance_eligible(exc.value.stage) is False
    text = cdo.format_owner_daily_status(exc.value, now=cdo.vn_now())
    assert f"Status: {stage}" in text and "M1 live acceptance: NOT_SATISFIED_BY_THIS_RUN" in text
    assert "Publication: BLOCKED" in text


def test_m1_live_acceptance_eligibility_requires_a_qualified_ordinary_daily():
    qualified = {
        "daily_operation_state": cdo.STATE_LOCAL_COMPLETE, "operating_mode": cdo.OPERATING_MODE_ORDINARY_DAILY,
        "acquisition": {"provider_runtime_state": "AVAILABLE",
                        "dnse_quality_license": {"license": "CORROBORATED_HEALTHY", "qualifies_for_ordinary_daily": True}},
    }
    assert cdo.m1_live_acceptance_eligible(qualified) is True
    for mutate in (
        lambda r: r["acquisition"].update(provider_runtime_state="SECURITY_REVIEW_BLOCKED"),
        lambda r: r["acquisition"].update(dnse_quality_license={
            "license": "UNASSESSED_NO_SECONDARY_OBSERVATION", "qualifies_for_ordinary_daily": False}),
        lambda r: r["acquisition"].pop("dnse_quality_license"),  # reused pre-V1 snapshot
        lambda r: r.update(daily_operation_state="BLOCKED_SUPPLEMENTAL_PROVIDER_RUNTIME"),
        lambda r: r.pop("operating_mode"),
    ):
        record = json.loads(json.dumps(qualified))
        mutate(record)
        assert cdo.m1_live_acceptance_eligible(record) is False
    for stage in cdo.SUPPLEMENTAL_PROVIDER_BLOCK_STAGES:
        assert cdo.m1_live_acceptance_eligible(stage) is False


def test_qualified_daily_record_carries_both_axes_and_ordinary_mode(tmp_path, monkeypatch):
    from test_canonical_daily_operation import _acquired, _run

    def acquire(*_a, **_k):
        acquired = _acquired(tmp_path)
        acquired["snapshot"]["provider_runtime_state"] = "AVAILABLE"
        acquired["snapshot"]["dnse_quality_license"] = {
            "license": "CORROBORATED_HEALTHY", "qualifies_for_ordinary_daily": True, "reason_code": "x"}
        return acquired

    record = _run(tmp_path, monkeypatch, acquire_fn=acquire)
    assert record["operating_mode"] == cdo.OPERATING_MODE_ORDINARY_DAILY
    assert record["acquisition"]["provider_runtime_state"] == "AVAILABLE"
    assert cdo.m1_live_acceptance_eligible(record) is True


def test_replay_of_a_pre_v1_operation_keeps_its_record_shape_and_is_not_m1_eligible(tmp_path, monkeypatch):
    """A reused pre-V1 snapshot carries neither axis: the immutable operation record keeps its
    pre-V1 shape (no IMMUTABLE_OPERATION_RECORD_CONFLICT on idempotent replay) and is never
    offered to M1 live acceptance."""
    from test_canonical_daily_operation import _run

    first = _run(tmp_path, monkeypatch)
    assert "operating_mode" not in first
    assert "provider_runtime_state" not in first["acquisition"]
    assert cdo.m1_live_acceptance_eligible(first) is False
    second = _run(tmp_path, monkeypatch)
    assert second["operation_identity"] == first["operation_identity"]


# =============================================================================================
# 10. Single provider boundary for technical-history recovery
# =============================================================================================


def _runner():
    sys.path.insert(0, str(ROOT / "tools"))
    import run_market_wide_current_technical_coverage_scaleout as runner

    return runner


def test_technical_history_recovery_never_imports_the_provider_adapter():
    import ast

    source = (ROOT / "tools" / "run_market_wide_current_technical_coverage_scaleout.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported |= {alias.name for alias in node.names}
    assert not imported & {"vn_stock_pipeline", "vnstock", "vnai", "fetch_single_source"}


def test_technical_history_recovery_records_runtime_unavailable_and_skips_vci(monkeypatch, popen_counter):
    runner = _runner()
    fetch = runner._ProviderHistoryFetch(session=TARGET)  # real tracked policy: blocked
    snapshot_record = {"disposition": "EXACT_SESSION_RETAINED", "observations": [
        {"session": TARGET, "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1}]}
    try:
        record = runner._feature_safe_record(
            ticker="HPG", dnse_record={"ticker": "HPG", "state": "FETCH_FAILED", "reason": "DNSE_TIMEOUT"},
            snapshot_record=snapshot_record, target_session=TARGET, retrieved_at="test",
            start="2026-07-01", end=TARGET, fetch=fetch,
        )
    finally:
        fetch.close()
    assert record["reason"] == runner.SUPPLEMENTAL_HISTORY_RUNTIME_UNAVAILABLE
    attempted = record["attempted_provider_series"]
    assert "VCI" not in attempted  # same runtime; never a second futile request
    assert attempted["KBS"]["reason"].startswith("SUPPLEMENTAL_PROVIDER_RUNTIME_UNAVAILABLE:SECURITY_REVIEW_BLOCKED")
    assert fetch.runtime_state()["state"] == rt.SECURITY_REVIEW_BLOCKED
    assert popen_counter == []


def test_technical_history_recovery_uses_the_isolated_worker_boundary(monkeypatch):
    runner = _runner()
    seen: list[dict] = []

    def fake_open(**kwargs):
        seen.append(kwargs)
        return _open()

    monkeypatch.setattr(runner.worker_client, "open_provider_runtime", fake_open)
    fetch = runner._ProviderHistoryFetch(session=TARGET)
    try:
        outcome = fetch("EXACT_HPG", "KBS", "2026-07-01", TARGET)
        assert outcome.status == "success"
        assert fetch.runtime_state()["state"] == rt.AVAILABLE
        assert fetch.worker_governor_diagnostic()["source"] == "VNSTOCK_WORKER_REMOTE_GOVERNOR"
    finally:
        fetch.close()
    assert seen == [{"session": TARGET}]


def test_available_runtime_daily_parent_never_imports_the_provider_adapter():
    # The AVAILABLE path (not only the blocked policy): the real ensure_exact_session_snapshot runs
    # the real resolver through a live fake worker to a qualified snapshot in a fresh process, and
    # any attempt to import vn_stock_pipeline/vnstock/vnai in that parent is trapped.
    script = Path(__file__).with_name("fixtures") / "check_available_daily_parent_import_containment.py"
    result = subprocess.run([sys.executable, "-u", str(script)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_OK" in result.stdout


def test_request_pacing_has_one_neutral_owner():
    import multi_source_exact_session_resolver as resolver
    import vn_stock_pipeline
    import vnstock_rate_governor

    assert resolver._default_request_delay() == vnstock_rate_governor.VNSTOCK_REQUEST_DELAY_SECONDS
    assert vn_stock_pipeline.REQUEST_DELAY == vnstock_rate_governor.VNSTOCK_REQUEST_DELAY_SECONDS == 1.1


def test_technical_history_recovery_process_never_imports_provider_modules():
    script = Path(__file__).with_name("fixtures") / "check_technical_recovery_import_containment.py"
    result = subprocess.run([sys.executable, "-u", str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "TECHNICAL_RECOVERY_IMPORT_CONTAINMENT_OK" in result.stdout
