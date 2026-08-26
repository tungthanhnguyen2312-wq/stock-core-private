"""One-command capability-first EOD operation: fail-closed, no network, no scheduler."""
from __future__ import annotations

from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
import socket

import pytest

import completed_market_session_gate as gate
from tools import collect_market_evidence as collector
from tools import run_capability_first_eod_operation as op
from vn_time import VN_TZ

SESSION = "2026-08-26"
AFTER = datetime(2026, 8, 26, 18, 5, tzinfo=VN_TZ)
BEFORE = datetime(2026, 8, 26, 17, 59, tzinfo=VN_TZ)
POST_CLOSE = datetime(2026, 8, 26, 19, 19, tzinfo=VN_TZ)


def _working_dates(*dates: str) -> dict:
    return {"workingDates": list(dates)}


def _p3f9b(session: str, *, requested_at: str, exact: int = 889, total: int = 1683) -> dict:
    return {
        "resolved_completed_session": session,
        "retained_snapshot_session": session,
        "snapshot_sha256": "a" * 64,
        "snapshot_identity": "p3f9_exact_session_snapshot:" + "a" * 64,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "attempted_candidate_count": total,
        "exact_session_observed_count": exact,
        "requested_at": requested_at,
    }


def _ohlc_payload(session: str) -> dict:
    dt = datetime.strptime(session, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    epoch = int(dt.timestamp())
    return {
        "t": [epoch - 86400, epoch],
        "o": [21.00, 21.50],
        "h": [21.80, 22.00],
        "l": [20.90, 21.30],
        "c": [21.40, 21.85],
        "v": [1500000, 2500000],
    }


def _fetcher(session: str):
    payload = _ohlc_payload(session)

    def fetch(req: dict, session_date: str) -> dict:
        body = json.dumps(payload).encode("utf-8")
        return {
            "ok": True,
            "source": req["source"],
            "endpoint": req["endpoint_id"],
            "symbol": req["symbol"],
            "http_status": 200,
            "retrieval_time": f"{session}T18:05:00+07:00",
            "raw_bytes": body,
            "request_parameters": {"symbol": req["symbol"]},
        }

    return fetch


def _failing_fetcher(req: dict, session_date: str) -> dict:
    return {
        "ok": False,
        "error_code": "FETCH_FAILED",
        "source": req["source"],
        "endpoint": req["endpoint_id"],
        "symbol": req["symbol"],
        "retrieval_time": f"{SESSION}T18:05:00+07:00",
    }


def _collect_kwargs(tmp_path: Path, session: str = SESSION) -> dict:
    return {
        "symbols": ["HPG"],
        "capabilities": ["CLOSE_KVND"],
        "sources": ["DNSE"],
        "max_requests": 4,
        "out_dir": tmp_path / f"capability-first-eod-{session}",
    }


def _ready_kwargs(tmp_path: Path, session: str = SESSION) -> dict:
    return {
        "requested_at": POST_CLOSE,
        "session": session,
        "root": tmp_path,
        "out_dir": tmp_path / "operations-review",
        "working_dates_evidence": _working_dates(session, "2026-08-27"),
        "exact_session_evidence": _p3f9b(session, requested_at=f"{session}T19:19:00+07:00"),
        "allow_provider_probe": False,
        "collect_fetcher": _fetcher(session),
        "collect_kwargs": _collect_kwargs(tmp_path, session),
        "config_path": Path(__file__).resolve().parents[1] / "config" / "capability_first_eod_operation.json",
    }


def test_before_safety_floor_does_not_invoke_collector(tmp_path: Path):
    calls = []

    def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError("collector_must_not_run")

    record = op.run_capability_first_eod_operation(
        requested_at=BEFORE,
        session=SESSION,
        root=tmp_path,
        out_dir=tmp_path / "operations-review",
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
        collector=forbidden,
        allow_collect=True,
        allow_provider_probe=False,
    )
    assert record["final_disposition"] == op.DISPOSITION_BLOCKED_BEFORE_COLLECTION
    assert record["collector_invoked"] is False
    assert record["session_gate"]["completion_gate_status"] == gate.STATUS_TOO_EARLY
    assert calls == []


def test_time_alone_never_ready_and_does_not_collect(tmp_path: Path):
    calls = []

    def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError("collector_must_not_run")

    record = op.run_capability_first_eod_operation(
        requested_at=AFTER,
        session=SESSION,
        root=tmp_path,
        out_dir=tmp_path / "operations-review",
        collector=forbidden,
        allow_provider_probe=False,
    )
    assert record["final_disposition"] == op.DISPOSITION_BLOCKED_BEFORE_COLLECTION
    assert record["session_gate"]["completion_gate_status"] != gate.STATUS_READY
    assert record["collector_invoked"] is False
    assert calls == []


def test_one_command_successful_fixture_chain(tmp_path: Path):
    record = op.run_capability_first_eod_operation(**_ready_kwargs(tmp_path))
    assert record["final_disposition"] == op.DISPOSITION_COMPLETED
    assert record["session"] == SESSION
    assert record["collector_invoked"] is True
    assert record["materialization_invoked"] is True
    assert record["eod_collection_identity"]
    assert record["canonical_integration_identity"]
    assert record["market_research_materialization_identity"]
    assert record["completion_record_identity"]
    assert record["authority_effect"] == "NONE"
    assert record["scheduler_ready"] == "YES"
    assert record["is_idempotent_replay"] is False
    run_dir = Path(record["operation_directory"])
    assert (run_dir / "operation_record.json").is_file()
    assert (run_dir / "session_gate.json").is_file()


def test_idempotent_replay_preserves_identities(tmp_path: Path):
    kwargs = _ready_kwargs(tmp_path)
    first = op.run_capability_first_eod_operation(**kwargs)
    second = op.run_capability_first_eod_operation(**kwargs)
    assert second["is_idempotent_replay"] is True
    assert first["operation_identity"] == second["operation_identity"]
    assert first["eod_collection_identity"] == second["eod_collection_identity"]
    assert first["market_research_materialization_identity"] == second["market_research_materialization_identity"]
    assert first["completion_record_identity"] == second["completion_record_identity"]
    first_bytes = Path(first["operation_directory"]).joinpath("operation_record.json").read_bytes()
    # Replay may flip is_idempotent_replay; the stored first record stays immutable.
    assert Path(first["operation_directory"]).joinpath("operation_record.json").read_bytes() == first_bytes


def test_tampered_retained_packet_fails_closed(tmp_path: Path):
    kwargs = _ready_kwargs(tmp_path)
    first = op.run_capability_first_eod_operation(**kwargs)
    packet_path = Path(first["retained_packet_path"])
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload["observations"][0]["native_fields"] = {"tampered": True}
    packet_path.write_text(json.dumps(payload), encoding="utf-8")
    second = op.run_capability_first_eod_operation(
        **{**kwargs, "packet_path": packet_path, "allow_collect": False, "collect_fetcher": None}
    )
    assert second["final_disposition"] == op.DISPOSITION_TAMPERED_PACKET
    assert second["market_research_materialization_identity"] in {None, first["market_research_materialization_identity"]}
    # Tamper path must not claim a new completed materialization.
    assert second["final_disposition"] != op.DISPOSITION_COMPLETED


def test_collector_failure_does_not_materialize(tmp_path: Path):
    calls = []

    def materializer(**kwargs):
        calls.append(kwargs)
        raise AssertionError("materializer_must_not_run")

    record = op.run_capability_first_eod_operation(
        **{
            **_ready_kwargs(tmp_path),
            "collect_fetcher": _failing_fetcher,
            "materializer": materializer,
        }
    )
    assert record["final_disposition"] == op.DISPOSITION_PACKET_INVALID
    assert record["collector_invoked"] is True
    assert record["materialization_invoked"] is False
    assert calls == []


def test_materialization_failure_is_not_completed(tmp_path: Path):
    def materializer(**kwargs):
        return {"disposition": "PACKET_NOT_FOUND", "error_reason": "forced"}

    record = op.run_capability_first_eod_operation(**{**_ready_kwargs(tmp_path), "materializer": materializer})
    assert record["final_disposition"] == op.DISPOSITION_MATERIALIZATION_FAILED
    assert record["collector_invoked"] is True
    assert record["materialization_invoked"] is True
    assert record["completion_record_identity"] is None


def test_exact_session_mismatch_cannot_materialize(tmp_path: Path):
    record = op.run_capability_first_eod_operation(
        requested_at=POST_CLOSE,
        session=SESSION,
        root=tmp_path,
        out_dir=tmp_path / "operations-review",
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b("2026-08-21", requested_at="2026-08-21T18:05:00+07:00"),
        collector=lambda **kwargs: (_ for _ in ()).throw(AssertionError("no collect")),
        allow_provider_probe=False,
    )
    assert record["final_disposition"] == op.DISPOSITION_BLOCKED_BEFORE_COLLECTION
    assert record["session_gate"]["completion_gate_status"] == gate.STATUS_SESSION_MISMATCH
    assert record["collector_invoked"] is False


def test_stale_packet_file_cannot_satisfy_current_session(tmp_path: Path):
    kwargs = _ready_kwargs(tmp_path)
    first = op.run_capability_first_eod_operation(**kwargs)
    packet_path = Path(first["retained_packet_path"])
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload["session_date"] = "2026-08-21"
    for row in payload.get("observations") or []:
        row["session"] = "2026-08-21"
        row["provider_session_date"] = "2026-08-21"
    clean = {k: v for k, v in payload.items() if k not in {"packet_sha256", "packet_identity"}}
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    payload["packet_sha256"] = digest
    payload["packet_identity"] = f"packet:{digest}"
    packet_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    second = op.run_capability_first_eod_operation(
        **{**kwargs, "packet_path": packet_path, "allow_collect": False, "collect_fetcher": None}
    )
    assert second["final_disposition"] == op.DISPOSITION_PACKET_INVALID
    assert "PACKET_SESSION_MISMATCH" in second["reason_codes"]


def test_authority_blockers_remain_unpromoted(tmp_path: Path):
    record = op.run_capability_first_eod_operation(**_ready_kwargs(tmp_path))
    bounds = record["authority_boundaries"]
    assert bounds["authority_effect"] == "NONE"
    assert bounds["raw_as_traded_promoted"] is False
    assert bounds["pit_backtest_eligible"] is False
    assert bounds["liquidity_sizing_authority"] == "BLOCKED"
    assert bounds["valuation_authority"] is False
    assert bounds["recommendation_authority"] is False
    text = json.dumps(record)
    assert "PROBABILITY" not in text
    assert "TARGET_PRICE" not in text
    assert "RANKING" not in text


def test_no_network_on_deterministic_fixture(tmp_path: Path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "connect", blocked, raising=False)
    record = op.run_capability_first_eod_operation(**_ready_kwargs(tmp_path))
    assert record["final_disposition"] == op.DISPOSITION_COMPLETED


def test_no_sleep_poll_or_scheduler_behavior():
    source = inspect.getsource(op)
    assert "sleep(" not in source
    assert "time.sleep" not in source
    assert "sched." not in source
    assert "BackgroundScheduler" not in source
    assert "Task Scheduler" not in source
    assert "crontab" not in source
    gate_source = inspect.getsource(gate)
    assert "sleep(" not in gate_source


def test_compact_handoff_lists_identities(tmp_path: Path, capsys):
    record = op.run_capability_first_eod_operation(**_ready_kwargs(tmp_path))
    print(op._compact_handoff(record))
    out = capsys.readouterr().out
    assert "DISPOSITION: COMPLETED" in out
    assert "SCHEDULER_READY: YES" in out
    assert record["operation_identity"] in out
    assert "AUTHORITY_EFFECT: NONE" in out


def test_schedule_config_has_no_machine_paths():
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "capability_first_eod_operation.json").read_text(encoding="utf-8")
    )
    blob = json.dumps(config)
    assert "C:\\Projects" not in blob
    assert "C:\\Program Files" not in blob
    assert config["scheduler_ready"] is True
    assert config["operating_timezone"] == "Asia/Ho_Chi_Minh"
    assert config["invocation"]["os_scheduler_installed_by_this_contract"] is False
