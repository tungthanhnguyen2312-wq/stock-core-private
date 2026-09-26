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


def ok(body: dict) -> dict:
    return {"ok": True, "http_status": 200, "body": body}


def err(status: int | None, code: str, **extra) -> dict:
    out = {"ok": False, "error_code": code, **extra}
    if status is not None:
        out["http_status"] = status
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
        "REJ": [err(400, "http_status_400", body={"message": "invalid symbol"})],
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


def test_raw_is_retained_before_interpretation_with_real_acquisition_time(tmp_path):
    env = Env(tmp_path, ["FPT", "REJ"])
    env.run(FakeDnse({"FPT": _standard_ohlc()["FPT"], "REJ": _standard_ohlc()["REJ"]}), "--no-foreign-flow")
    attempt = env.journal("FPT")["attempts"][0]
    raw_path = env.state / attempt["raw_path"]
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert rr.sha256_text(raw_path.read_text(encoding="utf-8")) == attempt["raw_sha256"]
    assert raw["target_session"] == TARGET and raw["request_identity"] == rr.ohlc_request_identity("FPT", TARGET)
    assert raw["acquired_at"] == "2026-09-26T21:00:00+07:00"  # real time, never backdated
    assert raw["acquisition_temporal_claim"] == "ACQUIRED_RETROSPECTIVELY_AT_ACQUIRED_AT_NOT_ON_TARGET_SESSION"
    assert raw["requested_range"]["to_session"] == TARGET
    assert TARGET in raw["provider_session_timestamps"]["sessions"]
    assert raw["price_basis"] == rr.PRICE_BASIS and "ADJUSTED_RETROSPECTIVE" in raw["price_basis"]
    assert raw["endpoint"] == "/price/ohlc" and raw["provider"] == "DNSE"
    rejected = json.loads((env.state / env.journal("REJ")["attempts"][0]["raw_path"]).read_text(encoding="utf-8"))
    assert rejected["http_status"] == 400 and rejected["body"] == {"message": "invalid symbol"}


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
    assert code == 3 and summary["status"] == rr.RUN_STOPPED_RATE_LIMIT
    assert [c[2]["symbol"] for c in throttled.calls] == ["AAA", "BBB", "BBB", "BBB"]
    assert 7 in [round(s) for s in env.sleeps] or any(s >= 7 for s in env.sleeps)  # Retry-After honored
    assert not (env.state / "journal" / "dnse_ohlc" / "CCC.json").exists()  # never attempted after the stop
    assert env.output_json("recovery_acquisition_quality.json")["not_attempted_count"] == 1
    healthy = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [ok(_ohlc_body(HISTORY))], "CCC": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(healthy, "--no-foreign-flow")
    assert code == 0 and summary["status"] == rr.RUN_COMPLETE
    assert [c[2]["symbol"] for c in healthy.calls] == ["BBB", "CCC"]  # AAA reused, not re-requested
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
    code, _ = env.run(fake, "--no-foreign-flow")
    assert code == 0
    assert env.journal("AAA")["disposition"] == rr.EXACT_SESSION_OBSERVED
    bbb = env.journal("BBB")
    assert bbb["disposition"] == rr.TRANSPORT_FAILURE and bbb["retry_state"]["exhausted"] is True
    assert len(bbb["attempts"]) == rr.DEFAULT_MAX_ATTEMPTS_PER_TICKER
    quality = env.output_json("recovery_acquisition_quality.json")
    assert quality["transport_failure_count"] == 1 and quality["unknown_or_unresolved_disposition_count"] == 1


def test_authentication_failure_stops_network_acquisition(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    fake = FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [err(401, "authentication_failed")],
                     "CCC": [ok(_ohlc_body(HISTORY))]})
    code, summary = env.run(fake)
    assert code == 3 and summary["status"] == rr.RUN_STOPPED_AUTH
    assert [c[2].get("symbol") for c in fake.calls] == ["AAA", "BBB"]  # no further calls, no foreign flow
    assert summary["foreign_flow_status"] == "SKIPPED"


def test_hard_call_budget_stops_acquisition(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB", "CCC"])
    fake = FakeDnse({t: [ok(_ohlc_body(HISTORY))] for t in ("AAA", "BBB", "CCC")})
    code, summary = env.run(fake, "--no-foreign-flow", "--call-budget", "2")
    assert code == 3 and summary["status"] == rr.RUN_STOPPED_BUDGET
    assert len(fake.calls) == 2
    assert env.output_json("recovery_acquisition_quality.json")["not_attempted_count"] == 1


def test_tampered_retained_raw_stops_only_that_ticker(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    env.run(FakeDnse({t: [ok(_ohlc_body(HISTORY))] for t in ("AAA", "BBB")}), "--no-foreign-flow")
    raw_path = env.state / env.journal("AAA")["attempts"][0]["raw_path"]
    raw_path.write_text(raw_path.read_text(encoding="utf-8").replace('"DNSE"', '"DNSX"', 1), encoding="utf-8")

    def no_network(*_a, **_k):
        raise AssertionError("no network on resume")

    code, _ = env.run(no_network, "--no-foreign-flow")
    assert code == 0
    assert env.journal("AAA")["state"] == rr.STOPPED_CONFLICT
    assert env.journal("AAA")["conflict"] == "RETAINED_RAW_HASH_MISMATCH"
    assert env.journal("BBB")["disposition"] == rr.EXACT_SESSION_OBSERVED
    quality = env.output_json("recovery_acquisition_quality.json")
    assert quality["raw_payload_conflicts"] == [{"ticker": "AAA", "conflict": "RETAINED_RAW_HASH_MISMATCH"}]
    assert "AAA" not in env.output_json("recovery_session_market_reconstruction.json")["per_ticker"]


def test_conflicting_bytes_for_the_same_request_identity_are_never_overwritten(tmp_path):
    env = Env(tmp_path, ["AAA", "BBB"])
    env.run(FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [ok(_ohlc_body(HISTORY))]}), "--plan-only", "--no-foreign-flow")
    squatter = env.state / "raw" / "dnse_ohlc" / "AAA" / (rr.ohlc_request_identity("AAA", TARGET).split(":")[1] + "__attempt01.json")
    squatter.parent.mkdir(parents=True)
    squatter.write_text('{"request_identity": "someone-else"}\n', encoding="utf-8")
    code, _ = env.run(FakeDnse({"AAA": [ok(_ohlc_body(HISTORY))], "BBB": [ok(_ohlc_body(HISTORY))]}), "--no-foreign-flow")
    assert code == 0  # one ticker's conflict never corrupts the run
    assert env.journal("AAA")["state"] == rr.STOPPED_CONFLICT
    assert env.journal("AAA")["conflict"] == "CONFLICTING_RETAINED_RAW_PAYLOAD"
    assert squatter.read_text(encoding="utf-8") == '{"request_identity": "someone-else"}\n'
    assert env.journal("BBB")["disposition"] == rr.EXACT_SESSION_OBSERVED


def test_orphan_raw_from_a_crash_is_reused_without_a_second_call(tmp_path):
    env = Env(tmp_path, ["AAA"])
    env.run(None, "--plan-only", "--no-foreign-flow")
    identity = rr.ohlc_request_identity("AAA", TARGET)
    record = rr.build_raw_record(ticker="AAA", target_session=TARGET, request_identity=identity, attempt=1,
                                 response={**ok(_ohlc_body(HISTORY)), "endpoint": "/price/ohlc",
                                           "query_sent": rr.ohlc_request_query("AAA", TARGET)},
                                 started_at="x", acquired_at="2026-09-26T20:00:00+07:00")
    layout = rr.RecoveryLayout(env.output.resolve(), env.runtime.resolve(), env.state.resolve())
    path = layout.raw_path("AAA", identity, 1)
    path.parent.mkdir(parents=True)
    path.write_text(rr.raw_record_text(record), encoding="utf-8", newline="\n")

    def no_network(*_a, **_k):
        raise AssertionError("orphan raw must be reused")

    code, _ = env.run(no_network, "--no-foreign-flow")
    assert code == 0
    attempt = env.journal("AAA")["attempts"][0]
    assert attempt["recovered_from_orphan_raw"] is True and attempt["disposition"] == rr.EXACT_SESSION_OBSERVED


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
    assert code == 0
    out = env.output_json("recovery_foreign_flow_value.json")
    assert out["records"]["FPT"]["status"] == "NON_TERMINAL_CHAIN_NOT_NORMALIZED"
    assert out["records"]["FPT"]["value"] is None
    assert not (env.runtime / "data" / "dnse-foreign-flow" / "observations" / "FPT.json").exists()
    assert out["records"]["HPG"]["status"] == "COMPLETE_CHAIN_VALUE_NORMALIZED"


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
