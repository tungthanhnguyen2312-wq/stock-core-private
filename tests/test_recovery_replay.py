"""RECOVERY_REPLAY (DNSE_FIRST_DAILY_AND_RECOVERY_INFRASTRUCTURE_CORRECTIVE): hermetic tests.

Every provider response is a fixture; no network, secret, production root or retained evidence is
touched. The target session is a parameter everywhere -- nothing here relies on a hard-coded one.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import canonical_daily_operation as cdo
import daily_session_level2_package as level2
import recovery_replay as rr
from vn_time import VN_TZ

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_recovery_replay as runner  # noqa: E402

TARGET = "2026-09-25"
FF_COHORT = ["FPT", "HPG"]


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------


def _epoch(session: str) -> int:
    return int(datetime.combine(date.fromisoformat(session), datetime.min.time(), VN_TZ).timestamp())


def _sessions_ending(last: str, count: int) -> list[str]:
    out, day = [], date.fromisoformat(last)
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return sorted(out)


def _ohlc_body(sessions: list[str], *, base: float = 10.0, last_close: float | None = None) -> dict:
    closes = [base + i * 0.1 for i in range(len(sessions))]
    if last_close is not None and closes:
        closes[-1] = last_close
    return {"t": [_epoch(s) for s in sessions], "o": closes, "h": [c + 0.2 for c in closes],
            "l": [c - 0.2 for c in closes], "c": closes, "v": [1000 + i for i in range(len(sessions))]}


def ok(body: dict, raw: bytes | None = None) -> dict:
    """A 200 as the governed fetch boundary returns it with ``retain_raw_bytes=True``."""
    raw = raw if raw is not None else json.dumps(body, indent=1).encode("utf-8")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {"ok": False, "http_status": 200, "error_code": "response_body_not_json", "raw_bytes": raw}
    return {"ok": True, "http_status": 200, "body": parsed, "raw_bytes": raw}


def err(status: int | None, code: str, body: Any = None, **extra) -> dict:
    out = {"ok": False, "error_code": code, **extra}
    if status is not None:
        out["http_status"] = status
        payload = body if body is not None else {"error": code}
        out["raw_bytes"] = json.dumps(payload).encode("utf-8")
        out["body"] = payload
    return out


class FakeDnse:
    """Scripted per-ticker responses; the last scripted response repeats."""

    def __init__(self, ohlc: dict[str, list[dict]], foreign: dict[str, list[dict]] | None = None):
        self.ohlc = {k: list(v) for k, v in ohlc.items()}
        self.foreign = {k: list(v) for k, v in (foreign or {}).items()}
        self.calls: list[tuple[str, str | None, dict]] = []

    def __call__(self, capability: str, *, api_key: str, api_secret: str, symbol: str | None, query: dict) -> dict:
        assert api_key == "synthetic-key" and api_secret == "synthetic-secret"
        self.calls.append((capability, symbol, dict(query)))
        if capability == "ohlc":
            script = self.ohlc[query["symbol"]]
            response = script.pop(0) if len(script) > 1 else script[0]
            return {**response, "endpoint": "/price/ohlc", "query_sent": dict(query)}
        script = self.foreign[symbol]
        response = script.pop(0) if len(script) > 1 else script[0]
        return {**response, "endpoint": f"/price/{symbol}/foreign-trading", "query_sent": dict(query)}


def _ff_page(ticker: str, rows: list[tuple[str, int, int]], cursor: str | None) -> dict:
    return ok({"foreigners": [
        {"symbol": ticker, "time": t, "totalBuyTradedAmount": b, "totalSellTradedAmount": s,
         "totalBuyVolume": 1, "totalSellVolume": 1, "boardId": "G1", "marketId": "HOSE"}
        for t, b, s in rows], "nextPageToken": cursor})


def _candidate_db(root: Path, tickers: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "vn_stock.db")
    con.execute("CREATE TABLE metadata (ticker TEXT, exchange TEXT, industry TEXT)")
    for i, t in enumerate(tickers):
        con.execute("INSERT INTO metadata VALUES (?,?,?)", (t, "HOSE" if i % 2 == 0 else "HNX", f"IND{i % 3}"))
    con.commit()
    con.close()
    return root


class Env:
    def __init__(self, tmp_path: Path, tickers: list[str]):
        self.base = tmp_path
        self.candidate_root = _candidate_db(tmp_path / "source-runtime", tickers)
        self.producer = tmp_path / "producer-checkout"
        self.producer.mkdir()
        self.output = tmp_path / "recovery" / "output"
        self.runtime = tmp_path / "recovery" / "runtime"
        self.state = tmp_path / "recovery" / "state"
        self.sleeps: list[float] = []
        self.t = [0.0]

    def argv(self, *extra: str) -> list[str]:
        return ["--target-session", TARGET, "--output-root", str(self.output), "--runtime-root", str(self.runtime),
                "--state-root", str(self.state), "--candidate-runtime-root", str(self.candidate_root), *extra]

    def run(self, fetcher: Any, *extra: str, live: bool = True) -> tuple[int, dict]:
        import contextlib
        import io

        def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.t[0] += seconds

        def clock() -> float:
            return self.t[0]

        flags = list(extra)
        if live and "--acknowledge-live-provider-calls" not in flags and "--analyze-only" not in flags and "--plan-only" not in flags:
            flags.append("--acknowledge-live-provider-calls")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = runner.main(self.argv(*flags), fetcher=fetcher, credentials=("synthetic-key", "synthetic-secret"),
                               sleep=sleep, clock=clock, now_iso=lambda: "2026-09-26T21:00:00+07:00",
                               production_roots=[self.producer])
        return code, json.loads(buf.getvalue())

    def journal(self, ticker: str) -> dict:
        return json.loads((self.state / "journal" / "dnse_ohlc" / f"{ticker}.json").read_text(encoding="utf-8"))

    def output_json(self, name: str) -> dict:
        return json.loads((self.output / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _ff_cohort(monkeypatch):
    monkeypatch.setattr(runner, "_foreign_flow_cohort", lambda enabled: list(FF_COHORT) if enabled else [])


HISTORY = _sessions_ending(TARGET, 25)
PRIOR_ONLY = _sessions_ending("2026-09-24", 25)


def _standard_ohlc() -> dict[str, list[dict]]:
    return {
        "FPT": [ok(_ohlc_body(HISTORY))],
        "HPG": [ok(_ohlc_body(HISTORY, last_close=5.0))],
        "PRI": [ok(_ohlc_body(PRIOR_ONLY))],
        "NOH": [ok({"t": [], "o": [], "h": [], "l": [], "c": [], "v": []})],
        "REJ": [err(400, "http_status_400", {"message": "invalid symbol"})],
    }


def _standard_ff() -> dict[str, list[dict]]:
    return {
        "FPT": [_ff_page("FPT", [(f"{TARGET} 14:45:00", 900, 400)], "c1"),
                _ff_page("FPT", [(f"{TARGET} 10:00:00", 100, 50)], None)],
        "HPG": [_ff_page("HPG", [(f"{TARGET} 14:45:00", 100, 700)], None)],
    }


# ---------------------------------------------------------------------------------------------
# Fresh run, dispositions, raw retention, package labels
# ---------------------------------------------------------------------------------------------


def test_fresh_run_complete_with_every_terminal_disposition(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG", "PRI", "NOH", "REJ"])
    fake = FakeDnse(_standard_ohlc(), _standard_ff())
    code, summary = env.run(fake)
    assert code == 0 and summary["status"] == rr.RUN_COMPLETE
    assert {env.journal(t)["disposition"] for t in ("FPT", "HPG")} == {rr.EXACT_SESSION_OBSERVED}
    assert env.journal("PRI")["disposition"] == rr.PRIOR_SESSION_ONLY
    assert env.journal("NOH")["disposition"] == rr.NO_HISTORY
    assert env.journal("REJ")["disposition"] == rr.PROVIDER_REJECTED
    assert len(env.journal("REJ")["attempts"]) == 1  # a provider 400 is never retried
    ohlc_calls = [c for c in fake.calls if c[0] == "ohlc"]
    assert len(ohlc_calls) == 5  # one per candidate, sequential
    # Pacing: at least 1.0 s between request starts (the first start needs no wait).
    assert summary["pacing_seconds_slept"] >= 1.0 * (len(fake.calls) - 1) - 1e-9
    quality = env.output_json("recovery_acquisition_quality.json")
    assert quality["attempted_count"] == 5 and quality["exact_session_count"] == 2
    assert quality["exact_over_attempted_ratio"] == 0.4
    assert (quality["provider_rejected_count"], quality["prior_session_only_count"], quality["no_history_count"]) == (1, 1, 1)
    assert quality["known_disposition_count"] == 5 and quality["unknown_or_unresolved_disposition_count"] == 0
    assert quality["exchange_distribution"]["label"] == rr.OVERLAY_LABEL
    assert quality["ordinary_daily_safety_floor_comparison"]["semantics"].endswith("NOT_PROOF_OF_MARKET_COMPLETENESS")
    assert quality["healthy_market_threshold"] == "NONE_DEFINED"


def _stem(env, ticker: str, attempt: int = 1) -> Path:
    return env.state / env.journal(ticker)["attempts"][attempt - 1]["raw_stem"]


def test_exact_provider_bytes_are_retained_before_interpretation_with_real_acquisition_time(tmp_path):
    env = Env(tmp_path, ["FPT", "REJ"])
    exact = b'{ "t": %s,\n "o":%s,"h":%s,"l":%s,"c":%s,"v":%s }' % tuple(
        json.dumps(v).encode() for v in _ohlc_body(HISTORY).values())
    fake = FakeDnse({"FPT": [ok(_ohlc_body(HISTORY), raw=exact)], "REJ": _standard_ohlc()["REJ"]})
    code, _ = env.run(fake, "--no-foreign-flow")
    assert code == 0
    attempt = env.journal("FPT")["attempts"][0]
    stem = _stem(env, "FPT")
    body = rr.body_path(stem).read_bytes()
    assert body == exact  # the exact bytes, never regenerated from a Python object
    assert rr.sha256_bytes(body) == attempt["body_sha256"] and len(body) == attempt["body_length"]
    envelope = json.loads(rr.envelope_path(stem).read_text(encoding="utf-8"))
    assert "body" not in envelope  # the envelope never carries a re-serialized body
    assert envelope["completion_marker"] == rr.RAW_COMPLETION_MARKER
    assert envelope["body_hash_scope"] == "EXACT_HTTP_RESPONSE_BODY_BYTES_AS_RECEIVED"
    assert envelope["target_session"] == TARGET and envelope["request_identity"] == rr.ohlc_request_identity("FPT", TARGET)
    assert envelope["acquired_at"] == "2026-09-26T21:00:00+07:00"  # real time, never backdated
    assert envelope["acquisition_temporal_claim"] == "ACQUIRED_RETROSPECTIVELY_AT_ACQUIRED_AT_NOT_ON_TARGET_SESSION"
    assert envelope["requested_range"]["to_session"] == TARGET
    assert envelope["price_basis"] == rr.PRICE_BASIS and "ADJUSTED_RETROSPECTIVE" in envelope["price_basis"]
    assert envelope["endpoint"] == "/price/ohlc" and envelope["provider"] == "DNSE"
    assert rr.sha256_bytes(rr.envelope_path(stem).read_bytes()) == attempt["envelope_sha256"]
    rejected_stem = _stem(env, "REJ")
    assert json.loads(rr.envelope_path(rejected_stem).read_text(encoding="utf-8"))["http_status"] == 400
    assert json.loads(rr.body_path(rejected_stem).read_bytes()) == {"message": "invalid symbol"}


def test_reconstruction_carries_hard_labels_and_no_decision_product(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG", "PRI", "NOH", "REJ"])
    env.run(FakeDnse(_standard_ohlc(), _standard_ff()))
    rec = env.output_json("recovery_session_market_reconstruction.json")
    assert rec["contract_version"] == "recovery_session_market_reconstruction/v1"
    assert rec["operating_mode"] == "RECOVERY_REPLAY"
    assert rec["temporal_claim"] == "SESSION_MARKET_RECONSTRUCTION_ONLY"
    assert rec["pit_friday_decision_reconstruction"] is False
    assert rec["m1_live_acceptance_eligible"] is False
    assert rec["publication"] == "FORBIDDEN"
    assert rec["acquisition_time_semantics"]["claims_acquisition_on_target_session"] is False
    assert set(rr.FORBIDDEN_PRODUCTS) <= set(rec["not_built_forbidden_in_recovery_replay"])
    rr.assert_no_forbidden_products(rec)
    text = json.dumps(rec)
    for key in ("research_action_posture", "integrated_investment_decision", "daily_integrated_decision_brief", "KNOWN_AS_OF_"):
        assert f'"{key}' not in text
    # No brief / IID / handoff / dashboard file is produced at all.
    produced = {p.name for p in env.output.rglob("*") if p.is_file()}
    assert produced == {"recovery_session_market_reconstruction.json", "recovery_acquisition_quality.json",
                        "recovery_foreign_flow_value.json"}
    # Cohorts are distinct; the candidate list is never a market denominator.
    cohorts = rec["cohorts"]
    assert cohorts["ACQUISITION_ATTEMPT_COHORT"] == {"count": 5, "is_market_denominator": False,
                                                    "source_kind": "GOVERNED_RUNTIME_METADATA_TICKERS_READ_ONLY_AT_RECOVERY_TIME"}
    assert cohorts["EXACT_SESSION_OBSERVED_COHORT"]["count"] == 2
    assert cohorts["DESCRIPTIVE_ANALYSIS_COHORT"]["count"] == 2
    assert cohorts["QUALIFIED_ELIGIBILITY_COHORT"].startswith("NOT_ESTABLISHED")
    assert set(cohorts["denominator_exclusions"]) == {"PRI", "NOH", "REJ"}
    assert rec["descriptive_breadth"]["denominator"] == 2
    assert (rec["descriptive_breadth"]["advancers"], rec["descriptive_breadth"]["decliners"]) == (1, 1)
    fpt = rec["per_ticker"]["FPT"]
    assert fpt["technical_context_latest_20"]["status"] == "AVAILABLE"
    assert fpt["relative_volume_20"]["semantics"].startswith("SAME_PROVIDER_DIMENSIONLESS")
    assert rec["authority_boundary"]["ACTIVE_UNIVERSE"] == "UNKNOWN_NOT_PROMOTED"
    assert rec["overlays"]["official_universe"]["status"] == "NOT_ATTACHED"
    assert rec["sector_descriptors"]["label"] == rr.OVERLAY_LABEL
    assert rec["sector_descriptors"]["known_as_of_target_session"] is False


# ---------------------------------------------------------------------------------------------
# Resume / reuse / conflict
# ---------------------------------------------------------------------------------------------


def test_identical_rerun_reuses_validated_raw_without_any_network_call(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG", "PRI", "NOH", "REJ"])
    env.run(FakeDnse(_standard_ohlc(), _standard_ff()))
    first = env.output_json("recovery_session_market_reconstruction.json")

    def no_network(*_a, **_k):
        raise AssertionError("resume must not call the provider")

    code, summary = env.run(no_network)
    assert code == 0 and summary["plan_state"] == "RESUMED_FROZEN_PLAN"
    assert env.output_json("recovery_session_market_reconstruction.json")["artifact_identity"] == first["artifact_identity"]


def test_resume_after_three_consecutive_429_stop(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    throttled = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [err(429, "rate_limited", retry_after_seconds=7)],
                          "CCC": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(throttled, "--no-foreign-flow")
    assert code == 3 and summary["status"] == rr.RUN_PARTIAL_RETRYABLE
    assert summary["stop_reason"] == rr.STOP_RATE_LIMIT and summary["complete"] is False
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()
    assert [c[2]["symbol"] for c in throttled.calls] == ["AAA", "BBB", "BBB", "BBB"]
    assert 7 in [round(s) for s in env.sleeps] or any(s >= 7 for s in env.sleeps)  # Retry-After honored
    assert not (env.state / "journal" / "dnse_ohlc" / "CCC.json").exists()  # never attempted after the stop
    assert env.output_json("recovery_acquisition_quality.json")["not_attempted_count"] == 1
    healthy = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [ok(_ohlc_body(HISTORY))], "CCC": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(healthy, "--no-foreign-flow")
    assert code == 0 and summary["status"] == rr.RUN_COMPLETE
    assert [c[2]["symbol"] for c in healthy.calls] == ["BBB", "CCC"]  # AAA reused, not re-requested
    assert (env.output / "recovery_session_market_reconstruction.json").is_file()
    assert not (env.output / "recovery_partial_diagnostic.json").exists()  # retired, never current
    assert len(env.journal("BBB")["attempts"]) == 4


def test_retry_after_is_honored_before_the_retry(tmp_path):
    env = Env(tmp_path, ["AAA"])
    fake = FakeDnse({"AAA": [err(429, "rate_limited", retry_after_seconds=30), ok(_ohlc_body(HISTORY))]})
    code, _ = env.run(fake, "--no-foreign-flow")
    assert code == 0
    assert any(s >= 30 for s in env.sleeps)
    journal = env.journal("AAA")
    assert [a["disposition"] for a in journal["attempts"]] == [rr.RATE_LIMITED, rr.EXACT_SESSION_OBSERVED]
    assert journal["retry_state"]["transient_retries_used"] == 1


def test_transport_failure_retries_then_terminal_when_exhausted(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    fake = FakeDnse({"AAA": [err(None, "request_failed_ConnectionError"), ok(_ohlc_body(HISTORY))],
                     "BBB": [err(503, "http_status_503")]})
    code, summary = env.run(fake, "--no-foreign-flow")
    assert code == 4 and summary["status"] == rr.RUN_PARTIAL_UNRESOLVED  # exhausted transient is a defect
    assert env.journal("AAA")["disposition"] == rr.EXACT_SESSION_OBSERVED
    bbb = env.journal("BBB")
    assert bbb["state"] == rr.TICKER_UNRESOLVED
    assert bbb["disposition"] == rr.TRANSPORT_FAILURE and bbb["retry_state"]["exhausted"] is True
    assert len(bbb["attempts"]) == rr.DEFAULT_MAX_ATTEMPTS_PER_TICKER
    quality = env.output_json("recovery_acquisition_quality.json")
    assert quality["transport_failure_count"] == 1 and quality["unknown_or_unresolved_disposition_count"] == 1


def test_authentication_failure_stops_network_acquisition(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    fake = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [err(401, "authentication_failed")],
                     "CCC": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(fake)
    assert code == 6 and summary["status"] == rr.RUN_BLOCKED_AUTH
    assert [c[2].get("symbol") for c in fake.calls] == ["AAA", "BBB"]  # no further calls, no foreign flow
    assert summary["foreign_flow_complete"] == 0 and not any(c[0] == "foreign_trading" for c in fake.calls)


def test_hard_call_budget_stops_acquisition(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    fake = FakeDnse({t: [ok(_ohlc_body(HISTORY))] for t in ("AAA", "BBB", "CCC")})
    code, summary = env.run(fake, "--no-foreign-flow", "--call-budget", "2")
    assert code == 3 and summary["status"] == rr.RUN_PARTIAL_RETRYABLE and summary["stop_reason"] == rr.STOP_BUDGET
    assert len(fake.calls) == 2
    assert env.output_json("recovery_acquisition_quality.json")["not_attempted_count"] == 1


def test_single_raw_conflict_among_complete_candidates_is_never_complete(tmp_path):
    """BLOCKER 1: one tampered retained raw among otherwise-complete candidates -> BLOCKED_INTEGRITY,
    non-zero exit, no completion claim, and it stays blocked on rerun (never auto-resolved)."""
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    code, _ = env.run(FakeDnse({t: [ok(_ohlc_body(HISTORY))] for t in ("AAA", "BBB", "CCC")}), "--no-foreign-flow")
    assert code == 0 and (env.output / "recovery_session_market_reconstruction.json").is_file()
    body = rr.body_path(_stem(env, "AAA"))
    _flip(body)  # same length, different bytes

    def no_network(*_a, **_k):
        raise AssertionError("no network on resume")

    for _ in range(2):  # the rerun stays blocked under the conflict-resolution contract
        code, summary = env.run(no_network, "--no-foreign-flow")
        assert code == rr.EXIT_CODES[rr.RUN_BLOCKED_INTEGRITY] == 5
        assert summary["status"] == rr.RUN_BLOCKED_INTEGRITY and summary["complete"] is False
        assert summary["run_status"]["integrity_blocked"][0]["ticker"] == "AAA"
        assert not (env.output / "recovery_session_market_reconstruction.json").exists()  # no completion claim
        diagnostic = env.output_json("recovery_partial_diagnostic.json")
        assert diagnostic["reconstruction_complete"] is False
        assert diagnostic["artifact_kind"] == "PARTIAL_DIAGNOSTIC_NOT_A_COMPLETED_RECONSTRUCTION"
        assert diagnostic["contract_version"] == "recovery_partial_diagnostic/v1"
        run_state = json.loads((env.state / "run_state.json").read_text(encoding="utf-8"))
        assert run_state["complete"] is False
        assert run_state["conflict_resolution_contract"] == rr.CONFLICT_RESOLUTION_CONTRACT
    assert env.journal("AAA")["state"] == rr.TICKER_INTEGRITY
    assert env.journal("AAA")["conflict"] == "RAW_BODY_HASH_MISMATCH"  # hash checked before resume
    assert env.journal("BBB")["state"] == rr.TICKER_CLASSIFIED
    # The earlier completion claim was moved aside, never left as current.
    assert list(env.output.glob("recovery_session_market_reconstruction.json.retired-*"))
    quality = env.output_json("recovery_acquisition_quality.json")
    assert quality["acquisition_complete"] is False
    assert quality["raw_payload_conflicts"] == [{"ticker": "AAA", "conflict": "RAW_BODY_HASH_MISMATCH"}]


def _layout(env) -> rr.RecoveryLayout:
    return rr.RecoveryLayout(env.output.resolve(), env.runtime.resolve(), env.state.resolve())


def _plant_orphan(env, ticker: str = "AAA", *, response: dict | None = None, attempt: int = 1,
                  mutate_envelope=None, mutate_body=None) -> Path:
    """Simulate a crash after the raw was retained but before the journal advanced."""
    layout = _layout(env)
    identity = rr.ohlc_request_identity(ticker, TARGET)
    stem = layout.raw_stem(ticker, identity, attempt)
    writer = rr.RecoveryWriter({"state_root": layout.state_root})
    rr.retain_response(writer, stem, capability="ohlc", ticker=ticker, target_session=TARGET, request_identity=identity,
                       attempt=attempt, response=response or ok(_ohlc_body(HISTORY)),
                       query=rr.ohlc_request_query(ticker, TARGET), endpoint="/price/ohlc",
                       started_at="2026-09-26T20:59:59+07:00", acquired_at="2026-09-26T21:00:00+07:00")
    if mutate_envelope is not None:
        envelope = json.loads(rr.envelope_path(stem).read_text(encoding="utf-8"))
        mutate_envelope(envelope)
        rr.envelope_path(stem).write_text(json.dumps(envelope), encoding="utf-8")
    if mutate_body is not None:
        mutate_body(rr.body_path(stem))
    return stem


def _no_network(*_a, **_k):
    raise AssertionError("an orphan must never trigger another provider call")


def test_valid_complete_orphan_is_adopted_without_another_call(tmp_path):
    env = Env(tmp_path, ["AAA"])
    env.run(None, "--plan-only", "--no-foreign-flow")
    _plant_orphan(env)
    code, summary = env.run(_no_network, "--no-foreign-flow")
    assert code == 0 and summary["status"] == rr.RUN_COMPLETE
    attempt = env.journal("AAA")["attempts"][0]
    assert attempt["recovered_from_orphan_raw"] is True and attempt["network_call"] is True
    assert attempt["disposition"] == rr.EXACT_SESSION_OBSERVED
    assert summary["counters"]["calls"] == 1  # the crashed call still counts against the budget


def _truncate(path: Path) -> None:
    path.write_bytes(path.read_bytes()[:-7])


def _flip(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-3] = ord("9") if data[-3] != ord("9") else ord("8")
    path.write_bytes(bytes(data))


@pytest.mark.parametrize(("label", "kwargs", "code"), [
    ("missing raw file", {"mutate_body": lambda p: p.unlink()}, "RAW_BODY_FILE_MISSING"),
    ("truncated file", {"mutate_body": _truncate}, "RAW_BODY_LENGTH_MISMATCH_TRUNCATED_OR_EXTENDED"),
    ("mismatched hash", {"mutate_body": _flip}, "RAW_BODY_HASH_MISMATCH"),
    ("mismatched request identity", {"mutate_envelope": lambda e: e.update(request_identity="dnse_ohlc_1d:other")},
     "RAW_ENVELOPE_REQUEST_IDENTITY_MISMATCH"),
    ("mismatched symbol", {"mutate_envelope": lambda e: e.update(ticker="ZZZ")}, "RAW_ENVELOPE_TICKER_MISMATCH"),
    ("mismatched target session", {"mutate_envelope": lambda e: e.update(target_session="2026-09-24")},
     "RAW_ENVELOPE_TARGET_SESSION_MISMATCH"),
    ("mismatched request parameters", {"mutate_envelope": lambda e: e["requested_range"]["query"].update({"from": 1})},
     "RAW_ENVELOPE_REQUEST_PARAMETERS_MISMATCH"),
    ("missing completion marker", {"mutate_envelope": lambda e: e.pop("completion_marker")}, "RAW_COMPLETION_MARKER_MISSING"),
    ("wrong contract", {"mutate_envelope": lambda e: e.update(contract_version="recovery_raw_provider_response/v1")},
     "RAW_ENVELOPE_CONTRACT_MISMATCH"),
    ("malformed payload", {"response": ok({}, raw=b'{"t": [1, 2'), }, "RAW_BODY_MALFORMED_UNDER_RESPONSE_CONTRACT"),
    ("valid parse but incomplete envelope: no acquired_at", {"mutate_envelope": lambda e: e.pop("acquired_at")},
     "RAW_ENVELOPE_ACQUIRED_AT_MISSING"),
    ("valid parse but incomplete envelope: no status metadata", {"mutate_envelope": lambda e: e.update(http_status=None)},
     "RAW_ENVELOPE_STATUS_METADATA_INCONSISTENT"),
    ("valid parse but incomplete envelope: body length absent", {"mutate_envelope": lambda e: e.pop("body_length")},
     "RAW_BODY_LENGTH_MISMATCH_TRUNCATED_OR_EXTENDED"),
])
def test_invalid_orphan_is_never_adopted_and_blocks_the_run(tmp_path, label, kwargs, code):
    env = Env(tmp_path, ["AAA", "BBB"])
    env.run(None, "--plan-only", "--no-foreign-flow")
    if "response" in kwargs:
        # A malformed 200 body is retained exactly (the fetch boundary reports it as not-JSON);
        # force the envelope to claim ok so the adopting side must catch it.
        kwargs = {"response": {**kwargs["response"], "ok": True}}
    _plant_orphan(env, **kwargs)
    fake = FakeDnse({"BBB": [ok(_ohlc_body(HISTORY))]})
    exit_code, summary = env.run(fake, "--no-foreign-flow")
    assert exit_code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY, label
    journal = env.journal("AAA")
    assert journal["state"] == rr.TICKER_INTEGRITY and journal["disposition"] == rr.UNKNOWN
    assert journal["conflict"] == "INVALID_ORPHAN:" + code, label
    assert journal["attempts"] == []  # never adopted as evidence
    assert [c[2]["symbol"] for c in fake.calls] == ["BBB"]  # AAA never re-requested
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()


def test_body_without_completed_envelope_is_an_invalid_orphan_and_is_never_overwritten(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    env.run(None, "--plan-only", "--no-foreign-flow")
    stem = _layout(env).raw_stem("AAA", rr.ohlc_request_identity("AAA", TARGET), 1)
    squatter = rr.body_path(stem)
    squatter.parent.mkdir(parents=True)
    squatter.write_bytes(b'{"half written')
    code, _ = env.run(FakeDnse({"BBB": [ok(_ohlc_body(HISTORY))]}), "--no-foreign-flow")
    assert code == 5
    assert env.journal("AAA")["conflict"] == "INVALID_ORPHAN:ORPHAN_BODY_WITHOUT_COMPLETED_ENVELOPE"
    assert squatter.read_bytes() == b'{"half written'
    assert env.journal("BBB")["state"] == rr.TICKER_CLASSIFIED


def test_write_once_refuses_different_bytes_for_the_same_path(tmp_path):
    writer = rr.RecoveryWriter({"state_root": tmp_path.resolve()})
    target = tmp_path / "raw.body"
    sha, length = writer.write_bytes_once(target, b'{"a":1}')
    assert (sha, length) == (rr.sha256_bytes(b'{"a":1}'), 7)
    assert writer.write_bytes_once(target, b'{"a":1}') == (sha, length)  # identical: no-op
    with pytest.raises(rr.RawPayloadConflict):
        writer.write_bytes_once(target, b'{"a": 1}')
    assert target.read_bytes() == b'{"a":1}'


def test_whitespace_and_key_order_give_different_raw_identity_but_equal_parsed_content(tmp_path):
    compact = b'{"t":[1],"c":[2]}'
    spaced = b'{ "t": [1], "c": [2] }\n'
    reordered = b'{"c":[2],"t":[1]}'
    hashes = {rr.sha256_bytes(x) for x in (compact, spaced, reordered)}
    assert len(hashes) == 3
    assert json.loads(compact) == json.loads(spaced) == json.loads(reordered)
    env = Env(tmp_path, ["AAA", "BBB"])
    body = _ohlc_body(HISTORY)
    a = json.dumps(body, separators=(",", ":")).encode()
    b = json.dumps(dict(reversed(list(body.items()))), indent=3).encode()
    code, _ = env.run(FakeDnse({"AAA": [ok(body, raw=a)], "BBB": [ok(body, raw=b)]}), "--no-foreign-flow")
    assert code == 0
    ja, jb = env.journal("AAA")["attempts"][0], env.journal("BBB")["attempts"][0]
    assert ja["body_sha256"] == rr.sha256_bytes(a) and jb["body_sha256"] == rr.sha256_bytes(b)
    assert ja["body_sha256"] != jb["body_sha256"]
    rec = env.output_json("recovery_session_market_reconstruction.json")["per_ticker"]
    assert rec["AAA"]["session_bar"] == rec["BBB"]["session_bar"]  # same parsed content


def test_fetcher_without_exact_bytes_is_an_integrity_stop(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    parsed_only = {"ok": True, "http_status": 200, "body": _ohlc_body(HISTORY)}  # no raw_bytes
    fake = FakeDnse({"AAA": [parsed_only], "BBB": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(fake, "--no-foreign-flow")
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert summary["stop_reason"] == rr.STOP_INTEGRITY
    assert env.journal("AAA")["conflict"] == "RAW_RETENTION_FAILED:FETCH_ADAPTER_DID_NOT_RETURN_EXACT_RESPONSE_BYTES"
    assert [c[2]["symbol"] for c in fake.calls] == ["AAA"]  # acquisition stops for review


def test_governed_fetch_boundary_returns_exact_bytes_without_credentials():
    import dnse_bulk_market_data as bulk

    exact = b'{ "t" : [1714000000] ,"o":[1],"h":[1],"l":[1],"c":[1],"v":[1] }'

    class Response:
        status_code = 200
        content = exact
        headers = {"Content-Type": "application/json", "Retry-After": None}

        def json(self):
            raise AssertionError("recovery decodes from the exact bytes, not response.json()")

    seen = {}

    def request_get(url, params, headers, timeout):
        seen["headers"] = headers
        return Response()

    result = bulk.fetch_capability_raw("ohlc", api_key="k-synthetic", api_secret="s-synthetic",
                                       query={"symbol": "AAA"}, request_get=request_get, retain_raw_bytes=True)
    assert result["ok"] is True and result["raw_bytes"] == exact
    assert "body" not in result  # the fetch boundary must not parse before durable raw retention
    assert result["content_type"] == "application/json"
    text = json.dumps({k: v for k, v in result.items() if k != "raw_bytes"})
    assert "s-synthetic" not in text and "X-Signature" not in text and "k-synthetic" not in text
    # Even non-JSON 200 bytes are passed through unchanged; retention verification rejects them.
    Response.content = b"<html>maintenance</html>"
    broken = bulk.fetch_capability_raw("ohlc", api_key="k", api_secret="s", query={}, request_get=request_get,
                                       retain_raw_bytes=True)
    assert broken["ok"] is True and "body" not in broken
    assert broken["raw_bytes"] == b"<html>maintenance</html>"
    # Default callers are unchanged: no raw_bytes key.
    Response.content = exact
    Response.json = lambda self: json.loads(exact)
    assert "raw_bytes" not in bulk.fetch_capability_raw("ohlc", api_key="k", api_secret="s", query={}, request_get=request_get)


def test_governed_recovery_fetcher_asks_the_boundary_for_exact_bytes(monkeypatch):
    import dnse_bulk_market_data as bulk

    captured = {}
    monkeypatch.setattr(bulk, "fetch_capability_raw", lambda capability, **kw: captured.update(kw, capability=capability) or {})
    rr.governed_recovery_fetcher()("ohlc", api_key="k", api_secret="s", symbol=None, query={"symbol": "AAA"})
    assert captured["retain_raw_bytes"] is True and captured["capability"] == "ohlc"


def test_http_date_retry_after_is_exposed_only_for_recovery_opt_in():
    import dnse_bulk_market_data as bulk
    from datetime import timezone
    from email.utils import format_datetime

    class Response:
        status_code = 429
        content = b'{"message":"slow down"}'
        headers = {"Retry-After": format_datetime(datetime.now(timezone.utc) + timedelta(seconds=90))}

    request = lambda *_a, **_k: Response()
    recovery = bulk.fetch_capability_raw("ohlc", api_key="k", api_secret="s", query={},
                                         request_get=request, retain_raw_bytes=True)
    ordinary = bulk.fetch_capability_raw("ohlc", api_key="k", api_secret="s", query={}, request_get=request)
    assert 0 < recovery["retry_after_seconds"] <= 90
    assert "retry_after_seconds" not in ordinary and "raw_bytes" not in ordinary


def test_network_call_is_reserved_before_a_crash_and_counts_on_resume(tmp_path):
    env = Env(tmp_path, ["AAA"])
    env.run(None, "--plan-only", "--no-foreign-flow", "--call-budget", "2")

    def crash_after_call(*_a, **_k):
        raise RuntimeError("simulated process death before raw write")

    with pytest.raises(RuntimeError, match="simulated process death"):
        env.run(crash_after_call, "--no-foreign-flow", "--call-budget", "2")
    assert env.journal("AAA")["reserved_calls"] == 1
    assert env.journal("AAA")["attempts"] == []

    fake = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(fake, "--no-foreign-flow", "--call-budget", "2")
    assert code == 0 and summary["counters"]["calls"] == 2
    assert len(fake.calls) == 1 and env.journal("AAA")["reserved_calls"] == 2
    assert env.journal("AAA")["attempts"][0]["attempt"] == 2


def test_spent_call_cannot_be_reissued_past_budget_after_crash(tmp_path):
    env = Env(tmp_path, ["AAA"])
    env.run(None, "--plan-only", "--no-foreign-flow", "--call-budget", "1")
    with pytest.raises(RuntimeError):
        env.run(lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("crash")),
                "--no-foreign-flow", "--call-budget", "1")
    code, summary = env.run(_no_network, "--no-foreign-flow", "--call-budget", "1")
    assert code == 3 and summary["stop_reason"] == rr.STOP_BUDGET
    assert summary["counters"]["calls"] == 1


def test_completion_claim_is_retired_before_a_new_run_can_crash(tmp_path, monkeypatch):
    env = Env(tmp_path, ["AAA"])
    assert env.run(FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))]}), "--no-foreign-flow")[0] == 0
    assert (env.output / "recovery_session_market_reconstruction.json").exists()

    def crash(**_kwargs):
        raise RuntimeError("simulated second-run crash")

    monkeypatch.setattr(rr, "acquire_ohlc", crash)
    with pytest.raises(RuntimeError, match="second-run crash"):
        env.run(_no_network, "--no-foreign-flow")
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()
    state = json.loads((env.state / "run_state.json").read_text(encoding="utf-8"))
    assert state["complete"] is False and state["acquisition_status"] == "IN_PROGRESS"


def test_frozen_plan_identity_and_candidate_hash_are_verified_on_resume(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    env.run(None, "--plan-only", "--no-foreign-flow")
    path = env.state / "acquisition_plan.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["metadata_overlay"]["records"]["AAA"]["industry"] = "CHANGED"
    path.write_text(json.dumps(plan), encoding="utf-8")
    code, summary = env.run(_no_network, "--no-foreign-flow")
    assert code == 2 and summary["reason"].startswith("FROZEN_PLAN_INTEGRITY_INVALID")


def test_terminal_journal_disposition_must_match_verified_raw(tmp_path):
    env = Env(tmp_path, ["AAA"])
    env.run(FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))]}), "--no-foreign-flow")
    path = env.state / "journal" / "dnse_ohlc" / "AAA.json"
    journal = json.loads(path.read_text(encoding="utf-8"))
    journal["disposition"] = rr.PRIOR_SESSION_ONLY
    path.write_text(json.dumps(journal), encoding="utf-8")
    code, summary = env.run(_no_network, "--no-foreign-flow")
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert env.journal("AAA")["conflict"] == "JOURNAL_DISPOSITION_MISMATCH"


def test_resume_verifies_prior_retry_evidence_before_reusing_terminal_success(tmp_path):
    env = Env(tmp_path, ["AAA"])
    fake = FakeDnse({"AAA": [err(503, "http_status_503"), ok(_ohlc_body(HISTORY))]})
    assert env.run(fake, "--no-foreign-flow")[0] == 0
    first = env.state / env.journal("AAA")["attempts"][0]["raw_stem"]
    rr.body_path(first).write_bytes(b"changed prior retry")
    code, summary = env.run(_no_network, "--no-foreign-flow")
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()


def test_analyze_only_rechecks_raw_before_claiming_complete(tmp_path):
    env = Env(tmp_path, ["AAA"])
    assert env.run(FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))]}), "--no-foreign-flow")[0] == 0
    body = rr.body_path(_stem(env, "AAA"))
    body.write_bytes(b"tampered after completion")
    code, summary = env.run(_no_network, "--no-foreign-flow", "--analyze-only")
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()
    assert env.journal("AAA")["state"] == rr.TICKER_INTEGRITY


# ---------------------------------------------------------------------------------------------
# Foreign-flow chain identity
# ---------------------------------------------------------------------------------------------


def test_chain_hash_algorithm_is_deterministic_order_and_length_sensitive():
    pages = ["a" * 64, "b" * 64, "c" * 64]
    assert rr.chain_sha256(pages) == rr.chain_sha256(list(pages))
    expected = rr.sha256_text(rr.canonical_json({"chain_contract": "recovery_foreign_flow_chain/v1", "page_sha256": pages}))
    assert rr.chain_sha256(pages) == expected
    assert rr.chain_sha256(list(reversed(pages))) != rr.chain_sha256(pages)
    assert rr.chain_sha256(pages + ["d" * 64]) != rr.chain_sha256(pages)
    assert rr.chain_sha256(pages[:2]) != rr.chain_sha256(pages)


def test_foreign_flow_request_identity_binds_cursor_and_contract():
    first = rr.ff_request_identity("FPT", TARGET, 0, None)
    assert first != rr.ff_request_identity("FPT", TARGET, 1, "c1")
    assert first != rr.ff_request_identity("HPG", TARGET, 0, None)
    assert first != rr.ff_request_identity("FPT", "2026-09-24", 0, None)


def test_foreign_flow_chain_refuses_broken_cursor_lineage(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, _standard_ff()))
    path = env.state / "journal" / "dnse_foreign_trading" / "FPT.json"
    chain = json.loads(path.read_text(encoding="utf-8"))
    chain["pages"][1]["page_cursor"] = "wrong"
    path.write_text(json.dumps(chain), encoding="utf-8")
    code, summary = env.run(_no_network)
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert env.output_json("recovery_foreign_flow_value.json")["records"]["FPT"]["status"] == "CHAIN_INTEGRITY_FAILED"


def test_pending_foreign_flow_chain_is_verified_before_cursor_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_foreign_flow_cohort", lambda enabled: ["FPT"] if enabled else [])
    env = Env(tmp_path, ["FPT"])
    page = _ff_page("FPT", [(f"{TARGET} 14:45:00", 900, 400)], "c1")

    def crash_on_second_page(capability, **kwargs):
        if capability == "ohlc":
            return ok(_ohlc_body(HISTORY))
        if kwargs["query"].get("nextPageToken") == "c1":
            raise RuntimeError("crash before second page")
        return page

    with pytest.raises(RuntimeError, match="crash before second page"):
        env.run(crash_on_second_page)
    path = env.state / "journal" / "dnse_foreign_trading" / "FPT.json"
    chain = json.loads(path.read_text(encoding="utf-8"))
    assert chain["state"] == rr.FF_PENDING and len(chain["pages"]) == 1
    chain["pages"][0]["next_cursor"] = "forged"
    path.write_text(json.dumps(chain), encoding="utf-8")
    code, summary = env.run(_no_network)
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY


def test_incomplete_chain_retains_its_chain_hash_but_never_normalizes(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    ff = {"FPT": [_ff_page("FPT", [(f"{TARGET} 14:45:00", 900, 400)], "c1"), err(400, "http_status_400")],
          "HPG": _standard_ff()["HPG"]}
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, ff))
    chain = json.loads((env.state / "journal" / "dnse_foreign_trading" / "FPT.json").read_text(encoding="utf-8"))
    identity = chain["chain_identity"]
    assert identity["page_count"] == 1 and identity["terminal_cursor_reached"] is False
    assert identity["chain_sha256"] == rr.chain_sha256(identity["page_sha256"])
    assert identity["request_identity"]["target_session"] == TARGET and identity["acquired_at_min"]
    out = env.output_json("recovery_foreign_flow_value.json")["records"]["FPT"]
    assert out["status"] == "NON_TERMINAL_CHAIN_NOT_NORMALIZED" and out["value"] is None
    assert out["chain_identity"]["chain_sha256"] == identity["chain_sha256"]


def test_first_foreign_flow_page_rejection_cannot_claim_complete(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    ff = {"FPT": [err(400, "http_status_400")], "HPG": _standard_ff()["HPG"]}
    code, summary = env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"],
                                      "HPG": _standard_ohlc()["HPG"]}, ff))
    assert code == 4 and summary["status"] == rr.RUN_PARTIAL_UNRESOLVED
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()


def test_complete_chain_carries_its_chain_hash_and_normalizes(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, _standard_ff()))
    out = env.output_json("recovery_foreign_flow_value.json")["records"]["FPT"]
    assert out["status"] == "COMPLETE_CHAIN_VALUE_NORMALIZED"
    identity = out["chain_identity"]
    assert identity["page_count"] == 2 and identity["terminal_cursor_reached"] is True
    assert identity["chain_sha256"] == rr.chain_sha256(identity["page_sha256"])
    assert len(set(identity["page_sha256"])) == 2


def test_tampered_foreign_flow_page_blocks_integrity_and_never_normalizes(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, _standard_ff()))
    value_store = env.runtime / "data" / "dnse-foreign-flow" / "observations" / "FPT.json"
    assert value_store.exists()
    page = env.state / "raw" / "dnse_foreign_trading" / "FPT" / "page_0001.body"
    page.write_bytes(page.read_bytes() + b" ")

    code, summary = env.run(_no_network)
    assert code == 5 and summary["status"] == rr.RUN_BLOCKED_INTEGRITY
    assert summary["run_status"]["foreign_flow"]["integrity_blocked"][0]["ticker"] == "FPT"
    out = env.output_json("recovery_foreign_flow_value.json")["records"]["FPT"]
    assert out["status"] == "CHAIN_INTEGRITY_FAILED"
    assert not value_store.exists()


def test_plan_is_frozen_and_changed_controls_refuse_resume(tmp_path):
    env = Env(tmp_path, ["AAA"])
    code, summary = env.run(None, "--plan-only")
    assert code == 0 and summary["provider_calls"] == 0
    assert summary["controls"]["call_budget"] == 1 + rr.DEFAULT_MAX_TRANSIENT_RETRIES
    code, summary = env.run(None, "--plan-only", "--min-start-interval-seconds", "2.0")
    assert code == 2 and summary["reason"].startswith("FROZEN_PLAN_MISMATCH")


# ---------------------------------------------------------------------------------------------
# Foreign flow
# ---------------------------------------------------------------------------------------------


def test_complete_foreign_flow_chain_normalizes_value_only_into_the_isolated_store(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    production_store = tmp_path / "source-runtime" / "data" / "dnse-foreign-flow"
    code, summary = env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, _standard_ff()))
    assert code == 0 and summary["foreign_flow_complete"] == 2
    ff = env.output_json("recovery_foreign_flow_value.json")
    assert ff["temporal_claim"] == "RETROSPECTIVE_VALUE_ONLY" and ff["is_actionable"] is False
    assert ff["authority"] == "DNSE_RETROSPECTIVE_VALUE_ONLY"
    assert ff["volume_authority"].startswith("ABSOLUTE_UNIT_AND_COMPOSITION_UNQUALIFIED")
    fpt = ff["records"]["FPT"]
    assert (fpt["foreign_buy_value"], fpt["foreign_sell_value"], fpt["foreign_net_value"]) == (900, 400, 500)
    assert fpt["pages"] == 2 and "foreign_buy_volume" not in fpt
    assert (env.runtime / "data" / "dnse-foreign-flow" / "observations" / "FPT.json").is_file()
    assert not production_store.exists()  # production current foreign-flow store untouched
    observer = env.output_json("recovery_session_market_reconstruction.json")["flow_price_observer"]
    assert observer["is_actionable"] is False and observer["records"]["FPT"]["flow_sign"] == "NET_BUY"


def test_non_terminal_foreign_flow_chain_is_never_normalized(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    ff = {"FPT": [_ff_page("FPT", [(f"{TARGET} 14:45:00", 900, 400)], "c1"), err(400, "http_status_400")],
          "HPG": _standard_ff()["HPG"]}
    code, summary = env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, ff))
    assert code == 4 and summary["status"] == rr.RUN_PARTIAL_UNRESOLVED  # an incomplete chain is never COMPLETE
    out = env.output_json("recovery_foreign_flow_value.json")
    assert out["records"]["FPT"]["status"] == "NON_TERMINAL_CHAIN_NOT_NORMALIZED"
    assert out["records"]["FPT"]["value"] is None
    assert not (env.runtime / "data" / "dnse-foreign-flow" / "observations" / "FPT.json").exists()
    assert out["records"]["HPG"]["status"] == "COMPLETE_CHAIN_VALUE_NORMALIZED"


def test_foreign_flow_retry_after_is_preserved_across_a_stopped_run(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    ohlc = {"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}
    throttled = FakeDnse(ohlc, {"FPT": [err(429, "rate_limited", retry_after_seconds=7)],
                               "HPG": _standard_ff()["HPG"]})
    code, summary = env.run(throttled)
    assert code == 3 and summary["stop_reason"] == rr.STOP_RATE_LIMIT
    chain = json.loads((env.state / "journal" / "dnse_foreign_trading" / "FPT.json").read_text(encoding="utf-8"))
    assert chain["attempts"] == 3 and chain["pending_retry_after_seconds"] == 7
    slept_before = len(env.sleeps)
    healthy = FakeDnse(ohlc, _standard_ff())
    code, summary = env.run(healthy)
    assert code == 0 and summary["status"] == rr.RUN_COMPLETE
    assert any(s >= 7 for s in env.sleeps[slept_before:])
    assert not any(capability == "ohlc" for capability, _, _ in healthy.calls)


def test_foreign_flow_call_reservation_survives_a_crash(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    ohlc = {"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}
    fake = FakeDnse(ohlc, _standard_ff())

    def crash_on_foreign_flow(capability, **kwargs):
        if capability == "foreign_trading":
            raise RuntimeError("foreign-flow crash before raw write")
        return fake(capability, **kwargs)

    with pytest.raises(RuntimeError, match="foreign-flow crash"):
        env.run(crash_on_foreign_flow, "--foreign-flow-call-budget", "1")
    chain = json.loads((env.state / "journal" / "dnse_foreign_trading" / "FPT.json").read_text(encoding="utf-8"))
    assert chain["attempts"] == 1
    code, summary = env.run(_no_network, "--foreign-flow-call-budget", "1")
    assert code == 3 and summary["counters"]["foreign_flow_calls"] == 1
    assert summary["stop_reason"] == rr.STOP_BUDGET


def test_foreign_flow_page_limit_leaves_the_chain_non_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "DEFAULT_FOREIGN_FLOW_MAX_PAGES", 2)
    env = Env(tmp_path, ["FPT"])
    looping = {"FPT": [_ff_page("FPT", [(f"{TARGET} 14:{m:02d}:00", 1, 1)], f"c{m}") for m in range(10)],
               "HPG": _standard_ff()["HPG"]}
    plan = rr.build_plan(target_session=TARGET, candidates=["FPT"], candidate_source="x",
                         foreign_flow_cohort=["FPT"], foreign_flow_max_pages=2)
    roots = rr.assert_isolated_roots({"output_root": env.output, "runtime_root": env.runtime, "state_root": env.state},
                                     production_roots=[env.producer])
    layout = rr.RecoveryLayout(roots["output_root"], roots["runtime_root"], roots["state_root"])
    writer = rr.RecoveryWriter(roots)
    result = rr.acquire_foreign_flow(plan=plan, layout=layout, writer=writer, fetcher=FakeDnse({}, looping),
                                     api_key="synthetic-key", api_secret="synthetic-secret",
                                     pacer=rr.Pacer(1.0, clock=lambda: 0.0, sleep=lambda s: None),
                                     counters=rr.RunCounters())
    assert result["chains"]["FPT"]["failure"] == "NON_TERMINAL_PAGE_LIMIT_REACHED"
    normalized = rr.normalize_foreign_flow(plan=plan, layout=layout, writer=writer)
    assert normalized["records"]["FPT"]["status"] == "NON_TERMINAL_CHAIN_NOT_NORMALIZED"


# ---------------------------------------------------------------------------------------------
# Isolation / refusal
# ---------------------------------------------------------------------------------------------


def test_live_calls_require_explicit_acknowledgement(tmp_path):
    env = Env(tmp_path, ["AAA"])

    def no_network(*_a, **_k):
        raise AssertionError("no network without acknowledgement")

    code, summary = env.run(no_network, live=False)
    assert code == 2 and summary["reason"] == "LIVE_PROVIDER_CALLS_NOT_ACKNOWLEDGED" and summary["provider_calls"] == 0


def test_every_recovery_root_is_required(tmp_path):
    with pytest.raises(SystemExit):
        runner.parse_args(["--target-session", TARGET, "--output-root", str(tmp_path / "o"), "--state-root", str(tmp_path / "s")])


@pytest.mark.parametrize("bad", ["relative/path", ""])
def test_relative_or_empty_root_is_refused(tmp_path, bad):
    with pytest.raises(rr.RecoveryIsolationError):
        rr.assert_isolated_roots({"output_root": bad, "runtime_root": tmp_path / "r", "state_root": tmp_path / "s"},
                                 production_roots=[])


def test_recovery_roots_near_production_paths_are_refused(tmp_path):
    producer = tmp_path / "producer"
    (producer / ".git").mkdir(parents=True)
    good = {"runtime_root": tmp_path / "rec" / "runtime", "state_root": tmp_path / "rec" / "state"}
    cases = {
        "inside producer": producer / "recovery-out",
        "producer itself": producer,
        "contains producer": tmp_path,
        "operations-review namespace": tmp_path / "x" / "operations-review" / "out",
        "dashboard-runtime namespace": tmp_path / "dashboard-runtime" / "out",
        "ai handoff namespace": tmp_path / "stocklookup-ai-handoffs" / "out",
    }
    for label, output in cases.items():
        with pytest.raises(rr.RecoveryIsolationError):
            rr.assert_isolated_roots({"output_root": output, **good}, production_roots=[producer])
    # Any git work tree (Dashboard / AI-handoff repositories are git work trees).
    other_repo = tmp_path / "other-repo"
    (other_repo / ".git").mkdir(parents=True)
    with pytest.raises(rr.RecoveryIsolationError, match="GIT_WORK_TREE"):
        rr.assert_isolated_roots({"output_root": other_repo / "out", **good}, production_roots=[producer])
    # An existing root holding a production sentinel.
    sentinel_root = tmp_path / "looks-like-runtime"
    sentinel_root.mkdir()
    (sentinel_root / "vn_stock.db").write_text("", encoding="utf-8")
    with pytest.raises(rr.RecoveryIsolationError, match="PRODUCTION_SENTINEL"):
        rr.assert_isolated_roots({"output_root": sentinel_root, **good}, production_roots=[producer])
    # Overlapping recovery roots and a root overlapping the read-only candidate source.
    with pytest.raises(rr.RecoveryIsolationError, match="ROOTS_OVERLAP"):
        rr.assert_isolated_roots({"output_root": tmp_path / "rec" / "state" / "o", **good}, production_roots=[producer])
    with pytest.raises(rr.RecoveryIsolationError, match="READ_ONLY_SOURCE"):
        rr.assert_isolated_roots({"output_root": tmp_path / "src" / "o", **good}, production_roots=[producer],
                                 read_only_roots=[tmp_path / "src"])
    ok_roots = rr.assert_isolated_roots({"output_root": tmp_path / "rec" / "output", **good}, production_roots=[producer])
    assert set(ok_roots) == {"output_root", "runtime_root", "state_root"}


def test_symlink_alias_into_production_is_refused(tmp_path):
    import os

    production = tmp_path / "production"
    production.mkdir()
    alias = tmp_path / "alias"
    try:
        os.symlink(production, alias, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable on this host")
    with pytest.raises(rr.RecoveryIsolationError, match="OVERLAPS_PRODUCTION_ROOT"):
        rr.assert_isolated_roots({"output_root": alias / "out", "runtime_root": tmp_path / "r",
                                  "state_root": tmp_path / "s"}, production_roots=[production])
    writer = rr.RecoveryWriter({"output_root": (tmp_path / "safe").resolve()})
    with pytest.raises(rr.RecoveryIsolationError):
        writer.write_json_atomic(alias / "out" / "artifact.json", {})


def test_real_producer_checkout_is_always_a_production_root(tmp_path):
    with pytest.raises(rr.RecoveryIsolationError):
        rr.assert_isolated_roots({"output_root": ROOT / "recovery-out", "runtime_root": tmp_path / "r",
                                  "state_root": tmp_path / "s"})


def test_runner_refuses_production_overlap_with_zero_calls(tmp_path):
    env = Env(tmp_path, ["AAA"])
    argv = ["--target-session", TARGET, "--output-root", str(env.producer / "out"), "--runtime-root", str(env.runtime),
            "--state-root", str(env.state), "--candidate-runtime-root", str(env.candidate_root),
            "--acknowledge-live-provider-calls"]

    def no_network(*_a, **_k):
        raise AssertionError("refused before any call")

    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = runner.main(argv, fetcher=no_network, credentials=("k", "s"), production_roots=[env.producer])
    assert code == 2 and json.loads(buf.getvalue())["reason"].startswith("RECOVERY_ROOT_OVERLAPS_PRODUCTION_ROOT")
    assert not env.state.exists()


def test_writer_refuses_any_target_outside_the_isolated_roots(tmp_path):
    writer = rr.RecoveryWriter({"state_root": (tmp_path / "state").resolve()})
    with pytest.raises(rr.RecoveryIsolationError):
        writer.write_json_atomic(tmp_path / "elsewhere.json", {})
    with pytest.raises(rr.RecoveryIsolationError):
        writer.write_json_atomic(ROOT / "operations-review" / "x.json", {})


def test_a_full_run_writes_only_inside_the_isolated_roots(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG", "PRI", "NOH", "REJ"])
    before_source = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "source-runtime").rglob("*"))
    env.run(FakeDnse(_standard_ohlc(), _standard_ff()))
    after_source = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "source-runtime").rglob("*"))
    assert before_source == after_source  # read-only candidate source untouched
    assert not any(env.producer.iterdir())
    written = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert written == {"source-runtime", "recovery"}


def test_target_session_is_validated_not_hard_coded(tmp_path):
    with pytest.raises(rr.RecoveryPlanError, match="WEEKEND"):
        rr.validate_target_session("2026-09-26", now=datetime(2026, 9, 28, tzinfo=VN_TZ))
    with pytest.raises(rr.RecoveryPlanError, match="NOT_A_PAST_SESSION"):
        rr.validate_target_session("2026-09-28", now=datetime(2026, 9, 28, 20, tzinfo=VN_TZ))
    assert rr.validate_target_session("2026-09-17", now=datetime(2026, 9, 28, tzinfo=VN_TZ)) == "2026-09-17"
    assert rr.ohlc_request_identity("AAA", "2026-09-17") != rr.ohlc_request_identity("AAA", "2026-09-18")


# ---------------------------------------------------------------------------------------------
# Recovery can never become ordinary Daily / M1 / Friday knowledge
# ---------------------------------------------------------------------------------------------


def test_recovery_artifacts_are_never_m1_eligible_or_reusable(tmp_path):
    env = Env(tmp_path, ["FPT", "HPG"])
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "HPG": _standard_ohlc()["HPG"]}, _standard_ff()))
    rec = env.output_json("recovery_session_market_reconstruction.json")
    assert level2.is_recovery_replay_artifact(rec)
    as_record = {**rec, "daily_operation_state": cdo.STATE_PUBLISHED,
                 "acquisition": {"provider_runtime_state": "SECURITY_REVIEW_BLOCKED",
                                 "dnse_quality_license": {"license": "CORROBORATED_HEALTHY"}}}
    assert cdo.m1_live_acceptance_eligible(as_record) is False
    as_record["operating_mode"] = cdo.OPERATING_MODE_ORDINARY_DAILY  # even relabelled, the marker remains
    assert cdo.m1_live_acceptance_eligible(as_record) is False
    for name in ("recovery_acquisition_quality.json", "recovery_foreign_flow_value.json"):
        assert level2.is_recovery_replay_artifact(env.output_json(name))
    plan = json.loads((env.state / "acquisition_plan.json").read_text(encoding="utf-8"))
    assert level2.is_recovery_replay_artifact(plan)


def test_forbidden_products_and_known_as_of_claims_are_refused():
    with pytest.raises(rr.RecoveryPlanError, match="FORBIDDEN_PRODUCT"):
        rr.assert_no_forbidden_products({"per_ticker": {"FPT": {"research_action_posture": "ACCUMULATE"}}})
    with pytest.raises(rr.RecoveryPlanError, match="FORBIDDEN_PRODUCT"):
        rr.assert_no_forbidden_products({"KNOWN_AS_OF_2026_09_25": True})
    with pytest.raises(rr.RecoveryPlanError, match="TARGET_SESSION_KNOWLEDGE"):
        rr.assert_no_forbidden_products({"label": "KNOWN_AS_OF_2026_09_25"})


def test_retained_official_universe_is_only_a_later_overlay():
    official = {"artifact_identity": "current_official_market_universe:abc", "official_snapshot_observed_at": "2026-08-24"}
    label = rr.classify_overlay(official, target_session=TARGET)
    assert label["label"] == "CURRENT_RESEARCH_OVERLAY_ACQUIRED_OR_RETAINED_LATER"
    assert label["known_as_of_target_session"] is False
    assert label["active_universe_authority"] == "UNKNOWN_NOT_PROMOTED"
    # A stored claim without its own proof flag cannot gain PIT semantics either.
    assert rr.classify_overlay({"knowledge_time_session": TARGET}, target_session=TARGET)["known_as_of_target_session"] is False


def test_recovery_modules_never_import_a_vnstock_provider_package():
    import subprocess

    code = (
        "import sys; sys.path.insert(0, 'tools'); import recovery_replay, run_recovery_replay; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('vnstock', 'vnai', 'vn_stock_pipeline', "
        "'vnstock_worker_client', 'vnstock_worker_process')); print(','.join(bad)); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    source = (ROOT / "recovery_replay.py").read_text(encoding="utf-8") + (ROOT / "tools" / "run_recovery_replay.py").read_text(encoding="utf-8")
    import re

    imported = set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", source, flags=re.M))
    assert not imported & {"vnstock", "vnai", "vn_stock_pipeline", "vnstock_worker_client", "publish_dashboard",
                           "ai_handoff_publication", "dashboard_release_publisher",
                           "integrated_investment_decision_product", "daily_integrated_decision_brief",
                           "canonical_daily_operation", "next_session_decision_brief"}


def test_unknown_disposition_is_never_complete(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    fake = FakeDnse({"AAA": [ok({}, raw=b"<html>maintenance</html>")], "BBB": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(fake, "--no-foreign-flow")
    assert code == 4 and summary["status"] == rr.RUN_PARTIAL_UNRESOLVED
    journal = env.journal("AAA")
    assert journal["state"] == rr.TICKER_UNRESOLVED and journal["disposition"] == rr.UNKNOWN
    assert rr.body_path(env.state / journal["attempts"][0]["raw_stem"]).read_bytes() == b"<html>maintenance</html>"
    assert not (env.output / "recovery_session_market_reconstruction.json").exists()
    assert env.output_json("recovery_partial_diagnostic.json")["reconstruction_complete"] is False
