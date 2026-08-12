"""Checkpointed immutable raw ingestion for ready global DNSE datasets.

The initial supported dataset is ``working_dates``.  It is intentionally a
small, global request rather than a fabricated instrument loop; its provider
calendar fields are retained opaque and no session semantics are inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credential_status, credentials_for_request  # noqa: E402
from dnse_bulk_market_data import fetch_capability_raw  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
import market_raw_lake as lake  # noqa: E402
from market_data_contracts import RawObservation  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402
import vn_time  # noqa: E402

PROVIDER = "DNSE"
DATASET = "working_dates"
CAPABILITY = "working_dates"
UNIT_ID = "market"
CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def run_scope_id() -> str:
    return hashlib.sha256(_canonical_json({"provider": PROVIDER, "dataset": DATASET,
                                            "endpoint": "/market/working-dates", "query": {}}).encode("utf-8")
                          ).hexdigest()[:24]


def _observation(response: dict[str, Any], *, retrieved_at: str, run_id: str,
                 checkpoint_identity: str) -> RawObservation:
    body = response.get("body") or {}
    payload_json = _canonical_json(body)
    request = {"provider": PROVIDER, "dataset": DATASET, "endpoint": response.get("endpoint"),
               "query": response.get("query_sent") or {}}
    return RawObservation(
        provider=PROVIDER, dataset=DATASET, instrument=UNIT_ID, retrieved_at=retrieved_at,
        request_identity=_canonical_json(request),
        raw_payload_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        schema_version="1.0.0", raw_payload=body,
        provenance={"endpoint": response.get("endpoint"), "request_parameters": response.get("query_sent") or {},
                    "http_status": response.get("http_status"), "elapsed_ms": response.get("elapsed_ms"),
                    "ingestion_run_id": run_id, "checkpoint_identity": checkpoint_identity,
                    "checkpoint_unit_id": UNIT_ID},
    )


def run(*, runtime_root: Path, api_key: str, api_secret: str, run_id: str,
        request_get: Callable[..., Any] | None = None) -> dict[str, Any]:
    scope = run_scope_id()
    checkpoint = lake.load_checkpoint(runtime_root, PROVIDER, DATASET, scope)
    started_at = vn_time.vn_now_iso()
    skipped: list[str] = []
    attempted: list[str] = []
    successful: list[str] = []
    failed: list[dict[str, Any]] = []
    if lake.unit_status(checkpoint, UNIT_ID) == "success":
        skipped.append(UNIT_ID)
    else:
        attempted.append(UNIT_ID)
        response = fetch_capability_raw(CAPABILITY, api_key=api_key, api_secret=api_secret,
                                        query={}, request_get=request_get)
        if response.get("ok"):
            observation = _observation(response, retrieved_at=vn_time.vn_now_iso(), run_id=run_id,
                                       checkpoint_identity=scope)
            write = lake.write_raw_observation(runtime_root, observation, run_id=run_id)
            checkpoint = lake.record_unit_result(checkpoint, UNIT_ID, status="success",
                                                 raw_file=write["path"], observation_id=observation.observation_id)
            lake.save_checkpoint(runtime_root, checkpoint)
            successful.append(UNIT_ID)
        else:
            code = str(response.get("error_code"))
            checkpoint = lake.record_unit_result(checkpoint, UNIT_ID, status="failed", error_code=code)
            lake.save_checkpoint(runtime_root, checkpoint)
            failed.append({"unit_id": UNIT_ID, "error_code": code})
    cumulative_successful = sorted(lake.completed_units(checkpoint))
    cumulative_failed = [{"unit_id": unit, "error_code": checkpoint["units"][unit].get("error_code")}
                         for unit in sorted(lake.units_with_status(checkpoint, "failed"))]
    manifest = lake.build_manifest(
        provider=PROVIDER, dataset=DATASET, run_id=run_id, run_scope_id=scope,
        started_at=started_at, ended_at=vn_time.vn_now_iso(), requested_units=[UNIT_ID],
        attempted_units=attempted, successful_units=cumulative_successful, failed_units=cumulative_failed,
        skipped_units=skipped, output_dir=str(lake.raw_run_dir(runtime_root, PROVIDER, DATASET, run_id)),
        checkpoint_file=str(lake.checkpoint_path(runtime_root, PROVIDER, DATASET, scope)),
        extra={"capability": CAPABILITY, "endpoint": "/market/working-dates",
               "raw_semantics": "PRESERVE_PROVIDER_FIELDS; no_session_semantics_promoted"},
    )
    lake.save_manifest(runtime_root, manifest)
    return {"status": "COMPLETE" if not failed else "COMPLETE_WITH_FAILURES", "manifest": manifest,
            "run_scope_id": scope}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--secrets-file", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"dry_run": True, "capability": CAPABILITY, "endpoint": "/market/working-dates",
                          "dataset": DATASET, "unit": UNIT_ID}, sort_keys=True))
        return 0
    ensure_credentials_loaded(args.secrets_file)
    if not credential_status()["configured"]:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2
    key, secret = credentials_for_request()
    result = run(runtime_root=resolve_runtime_root(args.runtime_root), api_key=key, api_secret=secret,
                 run_id=args.run_id or vn_time.vn_now().strftime("run-%Y%m%dT%H%M%S"))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
