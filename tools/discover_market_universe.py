"""CLI: discover the dynamic DNSE market universe and persist it.

Calls DNSE OpenAPI ``/market/instruments`` with no symbol/index/market filter
(``dnse_instrument_universe.discover_universe``), so the provider itself
returns its complete instrument population, paginated -- never a hardcoded
ticker list or count. Writes a deterministic, content-hashed universe
snapshot (Parquet + manifest) plus one immutable raw Parquet observation per
fetched page (through ``market_raw_lake``, dataset ``"instruments"``).

Without ``--live``, only the first-page call plan is printed and no network
call, credential load, or file write happens at all -- matching
``tools/dnse_market_data_probe.py``'s existing dry-run convention.

SCOPING NOTE: no page-level checkpoint/resume here
    A full sweep at the default page size is only ~15-20 HTTP requests (the
    known Vietnamese market universe is on the order of 1,500-1,700
    instruments), several orders of magnitude smaller than the per-symbol
    bulk dataset ingestion this milestone also builds
    (``tools/bulk_ingest_dnse_raw.py``, potentially thousands of requests).
    Re-running this tool after an interruption is a cheap full resweep, not
    a problem needing incremental resume, so this tool does not carry the
    same checkpoint apparatus. Each fetched page is still persisted as an
    immutable raw observation for provenance, and this run's *credentials*
    and *raw lake* mechanics are identical to the bulk-ingestion tool's.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from dnse_access import credential_status, credentials_for_request  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
import dnse_instrument_universe as universe  # noqa: E402
import market_raw_lake as lake  # noqa: E402
from market_data_contracts import RawObservation  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402
import vn_time  # noqa: E402

CREDENTIAL_INJECTION_REQUIRED = "DNSE_CREDENTIAL_INJECTION_REQUIRED"
UNIVERSE_SNAPSHOT_RELATIVE = Path("data") / "market_raw_lake" / "universe"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def _page_observation(page: int, response: Mapping[str, Any], *, retrieved_at: str) -> RawObservation:
    body = response.get("body") or {}
    payload_json = _canonical_json(body)
    return RawObservation(
        provider=universe.PROVIDER, dataset=universe.DATASET,
        instrument=f"universe_page_{page:04d}", retrieved_at=retrieved_at,
        request_identity=_canonical_json(response.get("query_sent") or {}),
        raw_payload_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        schema_version=universe.SCHEMA_VERSION, raw_payload=body,
        provenance={"endpoint": response.get("endpoint"), "http_status": response.get("http_status"),
                    "elapsed_ms": response.get("elapsed_ms")},
    )


def run(*, runtime_root: Path, api_key: str, api_secret: str, page_size: int, max_pages: int | None,
        run_id: str, request_get: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Discover the universe and persist snapshot + per-page raw observations.

    Assumes valid credentials are already resolved by the caller -- this
    function performs no credential lookup itself, which keeps it fully
    injectable for tests.
    """
    retrieved_at = vn_time.vn_now_iso()
    raw_write_results: list[dict[str, Any]] = []

    def on_page_success(page: int, response: dict[str, Any]) -> None:
        observation = _page_observation(page, response, retrieved_at=retrieved_at)
        existing = lake.find_same_run_logical_observation(runtime_root, observation, run_id)
        if existing is not None:
            raw_write_results.append({"path": str(existing), "written": False,
                                      "reason": "already_present_same_run_logical_observation",
                                      "observation_id": observation.observation_id})
            return
        raw_write_results.append(lake.write_raw_observation(runtime_root, observation, run_id=run_id))

    discovery = universe.discover_universe(
        api_key=api_key, api_secret=api_secret, retrieved_at=retrieved_at,
        page_size=page_size, max_pages=max_pages, request_get=request_get,
        on_page_success=on_page_success,
    )
    manifest = universe.snapshot_manifest(discovery)
    frame = universe.build_snapshot_frame(discovery["records"])
    snapshot_path = runtime_root / UNIVERSE_SNAPSHOT_RELATIVE / f"{manifest['snapshot_id']}.parquet"
    lake.write_snapshot_parquet(snapshot_path, frame)
    manifest_path = runtime_root / UNIVERSE_SNAPSHOT_RELATIVE / f"{manifest['snapshot_id']}.manifest.json"
    atomic_write_json(manifest_path, manifest)

    return {
        "status": discovery["status"],
        "run_id": run_id,
        "manifest": manifest,
        "snapshot_path": str(snapshot_path),
        "manifest_path": str(manifest_path),
        "raw_pages_written": sum(1 for item in raw_write_results if item.get("written")),
        "raw_pages_already_present": sum(1 for item in raw_write_results if not item.get("written")),
        "malformed_record_count": discovery["malformed_record_count"],
        "duplicate_identity_count": discovery["duplicate_identity_count"],
        "records": discovery["records"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                         help="Actually call the network. Without this, only the call plan is printed.")
    parser.add_argument("--runtime-root", default=None, help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--secrets-file", default=None,
                         help="Defaults to STOCK_LOOKUP_SECRETS_FILE, else the owner-approved local path.")
    parser.add_argument("--page-size", type=int, default=universe.DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=universe.DEFAULT_MAX_PAGES)
    parser.add_argument("--run-id", default=None, help="Defaults to a timestamp-derived id.")
    args = parser.parse_args(argv)

    if not args.live:
        print(json.dumps({
            "dry_run": True, "capability": "instruments", "endpoint": "/market/instruments",
            "first_page_query": {"page": 1, "limit": args.page_size}, "max_pages": args.max_pages,
            "note": "No hardcoded total ticker count -- pagination is driven by the "
                    "provider's own total/pageSize fields on each response.",
        }, indent=2, sort_keys=True))
        return 0

    ensure_credentials_loaded(args.secrets_file)
    if credential_status()["configured"] is False:
        print(CREDENTIAL_INJECTION_REQUIRED)
        return 2
    api_key, api_secret = credentials_for_request()

    runtime_root = resolve_runtime_root(args.runtime_root)
    run_id = args.run_id or vn_time.vn_now().strftime("run-%Y%m%dT%H%M%S")
    result = run(runtime_root=runtime_root, api_key=api_key, api_secret=api_secret,
                page_size=args.page_size, max_pages=args.max_pages, run_id=run_id)
    print(json.dumps({k: v for k, v in result.items() if k != "records"},
                     indent=2, sort_keys=True, default=str))
    print(f"discovered_count={len(result['records'])}")
    return 0 if result["status"] == "COMPLETE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
