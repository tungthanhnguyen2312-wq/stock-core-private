"""DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_V1: plan / status. No live probe."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_official_liquidity_rollforward as rollforward  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    payload, error = rollforward.load_official_payload(path)
    if payload is None:
        raise SystemExit(f"OFFICIAL_ARTIFACT_UNREADABLE:{error}:{path}")
    return payload


def plan_command(args: argparse.Namespace) -> dict[str, Any]:
    universe = json.loads(Path(args.universe).read_text(encoding="utf-8")) if args.universe else None
    series = rollforward.load_retained_series(args.prior_official_dir)
    if universe is None:
        raise SystemExit("UNIVERSE_REQUIRED")
    frame = rollforward._frame_from_universe(universe)
    plan = rollforward.plan_daily_rollforward(frame, series, target_session=args.session)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "daily_official_liquidity_rollforward_plan.json", plan)
    return {
        "target_session": args.session,
        "status": plan.get("status"),
        "planned_requests": plan.get("planned_requests"),
        "planned_by_exchange": plan.get("planned_by_exchange"),
        "hnx_upcom_planned_requests": plan.get("hnx_upcom_planned_requests"),
        "hard_request_budget": plan.get("hard_request_budget"),
        "retry_allowance": plan.get("retry_allowance"),
        "live_acceptance": rollforward.LIVE_ACCEPTANCE,
    }


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    result = rollforward.materialize_same_session_official_liquidity(
        session=args.session,
        artifact_root=Path(args.artifact_root),
        retained_evidence_root=Path(args.retained_root),
        allow_network=False,
        prior_official_dir=args.prior_official_dir,
    )
    return {k: result.get(k) for k in (
        "status", "reason", "artifact_identity", "planned_requests", "http_requests_made",
        "hnx_upcom_planned_requests", "live_acceptance", "status_path",
    )}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--session", required=True)
    plan.add_argument("--universe", type=Path, required=True)
    plan.add_argument("--prior-official-dir", type=Path, default=None)
    plan.add_argument("--output-dir", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("--session", required=True)
    status.add_argument("--artifact-root", type=Path, required=True)
    status.add_argument("--retained-root", type=Path, required=True)
    status.add_argument("--prior-official-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    result = {"plan": plan_command, "status": status_command}[args.command](args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
