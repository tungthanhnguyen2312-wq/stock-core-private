"""One foreground DNSE WebSocket closed-OHLC shadow observation; never a daemon."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credential_status, credentials_for_request, safe_error_code  # noqa: E402
from dnse_prospective_pit_shadow import (  # noqa: E402
    COLLECTOR_ID, OBSERVATIONS_FILENAME, ProspectivePitContractError, SCHEMA_ID, build_observation,
    canonical_json, retain_observation, sha256_json, validate_payload_correspondence,
)

DEFAULT_OUT_DIR = ROOT.parent / "operations-review" / "dnse-prospective-pit-shadow-20260811"
WS_URL = "wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json"
EXECUTION_MANIFEST_FILENAME = "execution_manifest.json"
MAX_CONTROL_MESSAGE_BUDGET = 2
MAX_IGNORED_MESSAGE_BUDGET = 2
MAX_TOTAL_RECEIVE_BUDGET = 5
MAX_TOTAL_SESSION_TIMEOUT_SECONDS = 120.0


class OutputDirectoryCollisionError(ValueError):
    """Raised rather than overwriting or mixing evidence from an older invocation."""


def _fresh_output_directory_required(out_dir: Path) -> None:
    evidence_paths = [out_dir / EXECUTION_MANIFEST_FILENAME, out_dir / OBSERVATIONS_FILENAME]
    existing = [path.name for path in evidence_paths if path.exists()]
    if existing:
        raise OutputDirectoryCollisionError(
            "output_directory_contains_collector_evidence:" + ",".join(sorted(existing))
        )


def _record_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _auth_message(api_key: str, api_secret: str) -> dict[str, Any]:
    # Exact HMAC message form from DNSE's published openapi-sdk AuthManager.
    timestamp = int(time.time())
    nonce = str(int(time.time() * 1_000_000))
    message = f"{api_key}:{timestamp}:{nonce}"
    signature = hmac.new(api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"action": "auth", "api_key": api_key, "signature": signature,
            "timestamp": timestamp, "nonce": nonce}


async def collect_once(*, ticker: str, resolution: str, timeout_seconds: float,
                       total_session_timeout_seconds: float,
                       collector_execution_id: str) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds_must_be_positive")
    if not 0 < total_session_timeout_seconds <= MAX_TOTAL_SESSION_TIMEOUT_SECONDS:
        raise ValueError("total_session_timeout_seconds_out_of_range")
    creds = credentials_for_request()
    if creds is None:
        return {"status": "CREDENTIAL_INJECTION_REQUIRED"}
    api_key, api_secret = creds
    channel = f"ohlc_closed.{resolution}.json"
    control_message_counts: dict[str, int] = {}
    ignored_message_types: dict[str, int] = {}
    timeout_stage: str | None = None
    observability = {
        "control_message_counts": control_message_counts,
        "ignored_message_types": ignored_message_types,
        "timeout_stage": timeout_stage,
        "message_budgets": {
            "control": MAX_CONTROL_MESSAGE_BUDGET,
            "ignored_non_bc": MAX_IGNORED_MESSAGE_BUDGET,
            "total_receive": MAX_TOTAL_RECEIVE_BUDGET,
        },
    }
    try:
        import websockets
        async with asyncio.timeout(total_session_timeout_seconds):
            timeout_stage = "connect"
            observability["timeout_stage"] = timeout_stage
            async with websockets.connect(WS_URL, open_timeout=10, close_timeout=5, ping_interval=None) as socket:
                timeout_stage = "welcome"
                observability["timeout_stage"] = timeout_stage
                await asyncio.wait_for(socket.recv(), timeout=timeout_seconds)  # welcome, intentionally not retained
                await socket.send(canonical_json(_auth_message(api_key, api_secret)))
                timeout_stage = "authentication"
                observability["timeout_stage"] = timeout_stage
                auth = json.loads(await asyncio.wait_for(socket.recv(), timeout=timeout_seconds))
                if (auth.get("action") or auth.get("a")) != "auth_success":
                    return {"status": "AUTHENTICATION_FAIL", "observability": observability}
                await socket.send(canonical_json({"action": "subscribe", "channels": [
                    {"name": channel, "symbols": [ticker]}
                ]}))
                control_count = ignored_count = semantic_received = 0
                # `ping` is transport keepalive, not a semantic frame.  It is
                # observable and answered, but it cannot exhaust any receive
                # budget; the enclosing asyncio.timeout remains the absolute
                # wall-clock bound even under a keepalive flood.
                while (semantic_received < MAX_TOTAL_RECEIVE_BUDGET and
                       control_count < MAX_CONTROL_MESSAGE_BUDGET and
                       ignored_count < MAX_IGNORED_MESSAGE_BUDGET):
                    timeout_stage = "post_subscribe_message"
                    observability["timeout_stage"] = timeout_stage
                    raw = await asyncio.wait_for(socket.recv(), timeout=timeout_seconds)
                    received = datetime.now(timezone.utc)
                    data = json.loads(raw)
                    action = data.get("action") or data.get("a")
                    if action == "ping":
                        _record_count(control_message_counts, "ping")
                        await socket.send(canonical_json({"action": "pong"}))
                        # Fake/immediate transports must still yield so the
                        # absolute timeout can expire under a keepalive flood.
                        await asyncio.sleep(0)
                        continue
                    semantic_received += 1
                    if action:
                        control_count += 1
                        _record_count(control_message_counts, str(action))
                        continue
                    if data.get("T") != "bc":
                        ignored_count += 1
                        _record_count(ignored_message_types, str(data.get("T", "missing")))
                        continue
                    validate_payload_correspondence(
                        payload=data, expected_symbol=ticker, expected_resolution=resolution,
                        expected_channel=channel,
                    )
                    observation = build_observation(payload=data, channel=channel, message_type="bc",
                                                    receipt_at=received,
                                                    collector_execution_id=collector_execution_id)
                    observability["timeout_stage"] = None
                    return {"status": "COMPLETED_EVENT_OBSERVED", "observation": observation,
                            "observability": observability}
                observability["timeout_stage"] = None
                return {"status": "BLOCKED_NO_COMPLETED_EVENT_OBSERVED", "observability": observability}
    except asyncio.TimeoutError:
        return {"status": "BLOCKED_NO_COMPLETED_EVENT_OBSERVED", "observability": observability}
    except ProspectivePitContractError as error:
        return {"status": "CONNECTION_OR_PROTOCOL_FAIL", "error_code": str(error),
                "observability": observability}
    except Exception as error:
        return {"status": "CONNECTION_OR_PROTOCOL_FAIL", "error_code": safe_error_code(error),
                "observability": observability}
    finally:
        # Avoid holding credentials in the long-lived local frame after this one run.
        api_key = api_secret = ""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def run(*, ticker: str, resolution: str, timeout_seconds: float, total_session_timeout_seconds: float,
        out_dir: Path) -> dict[str, Any]:
    _fresh_output_directory_required(out_dir)
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    collector_execution_id = sha256_json({
        "collector_id": COLLECTOR_ID, "started_at_utc": started, "ticker": ticker,
        "resolution": resolution,
    })
    result = asyncio.run(collect_once(
        ticker=ticker, resolution=resolution, timeout_seconds=timeout_seconds,
        total_session_timeout_seconds=total_session_timeout_seconds,
        collector_execution_id=collector_execution_id,
    ))
    manifest: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "collector_id": COLLECTOR_ID,
        "authority_state": "EXPERIMENT_SHADOW_ONLY",
        "run_mode": "single_foreground_websocket_session_no_reconnect",
        "provider": "DNSE/Livespeed",
        "endpoint": "wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json",
        "ticker": ticker,
        "channel": f"ohlc_closed.{resolution}.json",
        "started_at_utc": started,
        "collector_execution_id": collector_execution_id,
        "result_status": result["status"],
        "observability": result.get("observability", {}),
    }
    if result["status"] == "COMPLETED_EVENT_OBSERVED":
        retention = retain_observation(out_dir, result["observation"])
        manifest["retention"] = retention
        manifest["observation_payload_sha256"] = result["observation"]["payload_sha256"]
        manifest["observation_record_sha256"] = sha256_json(result["observation"])
    elif "error_code" in result:
        manifest["error_code"] = result["error_code"]
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / EXECUTION_MANIFEST_FILENAME, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--ticker", default="HPG")
    parser.add_argument("--resolution", default="1")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--total-session-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"dry_run": True, "mode": "single_foreground_websocket_session_no_reconnect",
                          "ticker": args.ticker, "channel": f"ohlc_closed.{args.resolution}.json"}, sort_keys=True))
        return 0
    if not credential_status()["configured"]:
        print("CREDENTIAL_INJECTION_REQUIRED")
        return 2
    try:
        report = run(ticker=args.ticker, resolution=args.resolution, timeout_seconds=args.timeout_seconds,
                     total_session_timeout_seconds=args.total_session_timeout_seconds,
                     out_dir=Path(args.out_dir))
    except (OutputDirectoryCollisionError, ValueError) as error:
        print(str(error))
        return 3
    print(json.dumps({key: report[key] for key in ("result_status", "ticker", "channel", "retention", "error_code") if key in report}, sort_keys=True))
    return 0 if report["result_status"] in {"COMPLETED_EVENT_OBSERVED", "BLOCKED_NO_COMPLETED_EVENT_OBSERVED"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
