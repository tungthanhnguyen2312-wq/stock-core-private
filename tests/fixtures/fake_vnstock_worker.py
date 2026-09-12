"""Deterministic fake VNStock worker for offline process-boundary tests.

Implements the exact same wire protocol as ``vnstock_worker_process.py`` but never imports
``vnstock``/``vnai``/``vn_stock_pipeline`` and never makes a network call. Scenario is selected
entirely by the requested ``ticker``'s prefix (see ``_SCENARIOS`` below) so tests can drive every
required acceptance case without any external configuration file.

Special control tickers (process-level, checked in the main dispatch loop, never inside the
worker thread pool):
    ``__SYSTEMEXIT_PROCESS__``   -- the whole process calls ``sys.exit(5)`` (acceptance case K).
    ``__HANG_FOREVER__``         -- the request is accepted but never answered (acceptance case L).
    ``__CRASH_HARD__``           -- the whole process calls ``os._exit(9)`` with no response at
                                     all, no clean shutdown (a harder crash than SystemExit).

Startup-failure simulation (acceptance case J): set env var ``FAKE_WORKER_STARTUP_FAIL=1`` --
the process exits(1) before ever emitting a ``ready`` message.

Malformed-response simulation (acceptance case M): ticker prefix ``__RAW_GARBAGE__`` writes a
non-JSON line to stdout instead of a well-formed response.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from vnstock_worker_protocol import (  # noqa: E402
    MSG_FETCH,
    MSG_FETCH_RESULT,
    MSG_GOVERNOR_DIAGNOSTIC,
    MSG_GOVERNOR_DIAGNOSTIC_RESULT,
    MSG_READY,
    MSG_SHUTDOWN,
    MSG_SHUTDOWN_ACK,
    MSG_WORKER_ERROR,
    PROTOCOL_VERSION,
)

_WRITE_LOCK = threading.Lock()


def _emit(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with _WRITE_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _canned_outcome(ticker: str, provider: str) -> dict:
    base = {
        "status": "success", "rows": [], "unit_scale": 1000, "lineage": [], "errors": [],
        "transient_failure": False, "request_attempts": 1, "retry_count": 0, "timeout_count": 0,
        "http_429_count": 0, "http_5xx_count": 0, "retry_after_seconds": 0.0,
    }
    if ticker.startswith("EXACT_"):
        base["rows"] = [
            {
                "ticker": ticker, "date": "2026-09-10", "open": 10000, "high": 10200,
                "low": 9900, "close": 10100, "volume": 123456, "source": provider,
            }
        ]
        return base
    if ticker.startswith("MISSING_"):
        base["status"] = "empty"
        return base
    if ticker.startswith("TRANSPORT_"):
        base.update(status="failed", transient_failure=True, errors=[f"{provider}:transport_test_failure"])
        return base
    if ticker.startswith("REJECT_"):
        base.update(status="failed", transient_failure=False, errors=[f"{provider}:permanent_test_failure"])
        return base
    if ticker.startswith("MALFORMED_"):
        base.update(status="failed", transient_failure=False, errors=[f"{provider}:invalid_schema_test"])
        return base
    # Default: clean session-missing, the safest default for any ticker this fixture doesn't
    # recognize, so an un-prefixed ticker never silently looks like a successful observation.
    base["status"] = "empty"
    return base


def _process_fetch(message: dict) -> None:
    ticker = message.get("ticker", "")
    provider = message.get("provider", "")
    request_id = message.get("request_id")
    if ticker.startswith("__RAW_GARBAGE__"):
        with _WRITE_LOCK:
            sys.stdout.write("{not valid json at all\n")
            sys.stdout.flush()
        return
    if ticker.startswith("__HANG_FOREVER__"):
        time.sleep(3600)
        return
    outcome = _canned_outcome(ticker, provider)
    _emit(
        {
            "protocol_version": PROTOCOL_VERSION, "type": MSG_FETCH_RESULT, "request_id": request_id,
            "provider": provider, "ticker": ticker, **outcome,
        }
    )


def main() -> int:
    if os.environ.get("FAKE_WORKER_STARTUP_FAIL") == "1":
        return 1

    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="fake-vnstock-worker")
    _emit({"protocol_version": PROTOCOL_VERSION, "type": MSG_READY, "request_id": None})

    attempts = {"count": 0}
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            msg_type = message.get("type")
            ticker = message.get("ticker", "") if msg_type == MSG_FETCH else ""
            if ticker.startswith("__SYSTEMEXIT_PROCESS__"):
                sys.exit(5)
            if ticker.startswith("__CRASH_HARD__"):
                os._exit(9)
            if msg_type == MSG_FETCH:
                attempts["count"] += 1
                pool.submit(_process_fetch, message)
            elif msg_type == MSG_GOVERNOR_DIAGNOSTIC:
                _emit(
                    {
                        "protocol_version": PROTOCOL_VERSION, "type": MSG_GOVERNOR_DIAGNOSTIC_RESULT,
                        "request_id": message.get("request_id"),
                        "diagnostic": {
                            "contract_version": "vnstock_rate_governor/v1", "attempts": attempts["count"],
                            "not_authoritative": True,
                        },
                    }
                )
            elif msg_type == MSG_SHUTDOWN:
                _emit({"protocol_version": PROTOCOL_VERSION, "type": MSG_SHUTDOWN_ACK, "request_id": message.get("request_id")})
                break
    finally:
        pool.shutdown(wait=True, cancel_futures=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
