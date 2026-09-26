"""RECOVERY_REPLAY runner: isolated, resumable retrospective reconstruction of one past session.

This is NOT a Daily. It never runs ``stocklookup.ps1 daily`` / canonical Daily, never publishes,
never writes the producer checkout, a production runtime root, the Dashboard, the AI handoff or any
current/latest pointer, and its outputs can never satisfy an ordinary-Daily reuse gate or M1 live
acceptance. See ``recovery_replay.py`` for the contract.

Fail-closed defaults:
  * ``--target-session``, ``--output-root``, ``--runtime-root`` and ``--state-root`` are required and
    must be absolute, mutually non-overlapping, and outside every production/current namespace;
  * live provider calls additionally require ``--acknowledge-live-provider-calls``;
  * ``--plan-only`` validates roots and freezes the acquisition plan with zero provider calls;
  * ``--analyze-only`` rebuilds the reconstruction from the retained journal with zero provider calls.

Rerunning the identical command resumes from the journal: terminal tickers whose retained raw bytes
still validate are never requested again; conflicting retained bytes stop only that ticker.

Exit codes: 0 = acquisition COMPLETE and package written; 3 = stopped/incomplete (resumable, package
written from what is retained); 2 = refusal (roots, plan mismatch, missing acknowledgement, ...).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import recovery_replay as rr  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Isolated RECOVERY_REPLAY of one past session (DNSE only).")
    parser.add_argument("--target-session", required=True, help="Explicit past session YYYY-MM-DD.")
    parser.add_argument("--output-root", required=True, help="Isolated analysis-package root.")
    parser.add_argument("--runtime-root", required=True, help="Isolated recovery runtime root (foreign-flow store).")
    parser.add_argument("--state-root", required=True, help="Isolated journal/checkpoint/raw root.")
    parser.add_argument("--candidate-runtime-root", default=None,
                        help="Governed candidate source (read-only vn_stock.db metadata). Defaults to "
                             "STOCK_LOOKUP_RUNTIME_ROOT. Only read when the plan is first frozen.")
    parser.add_argument("--call-budget", type=int, default=None,
                        help="Hard OHLC call ceiling (default: candidate count + max transient retries).")
    parser.add_argument("--max-transient-retries", type=int, default=rr.DEFAULT_MAX_TRANSIENT_RETRIES)
    parser.add_argument("--max-attempts-per-ticker", type=int, default=rr.DEFAULT_MAX_ATTEMPTS_PER_TICKER)
    parser.add_argument("--min-start-interval-seconds", type=float, default=rr.DEFAULT_MIN_START_INTERVAL_SECONDS)
    parser.add_argument("--stop-after-consecutive-429", type=int, default=rr.DEFAULT_STOP_AFTER_CONSECUTIVE_429)
    parser.add_argument("--foreign-flow-call-budget", type=int, default=rr.DEFAULT_FOREIGN_FLOW_CALL_BUDGET)
    parser.add_argument("--no-foreign-flow", action="store_true", help="Skip the 11-name foreign-flow recovery.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true", help="Validate roots and freeze the plan; zero provider calls.")
    mode.add_argument("--analyze-only", action="store_true", help="Rebuild the package from retained raw; zero provider calls.")
    parser.add_argument("--acknowledge-live-provider-calls", action="store_true",
                        help="Required for any live DNSE request.")
    return parser.parse_args(argv)


def _foreign_flow_cohort(enabled: bool) -> list[str]:
    if not enabled:
        return []
    from owner_research_focus import load_owner_research_focus

    return sorted({str(t).upper() for t in load_owner_research_focus().get("broader_watchlist") or ()})


def _emit(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def main(
    argv: Sequence[str] | None = None, *, fetcher: Callable[..., Mapping[str, Any]] | None = None,
    credentials: tuple[str, str] | None = None, sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic, now_iso: Callable[[], str] | None = None,
    production_roots: Sequence[Path] | None = None,
) -> int:
    args = parse_args(argv)
    now_iso = now_iso or (lambda: rr.vn_now().isoformat())
    try:
        target = rr.validate_target_session(args.target_session)
        candidate_root = args.candidate_runtime_root or os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT") or None
        roots = rr.assert_isolated_roots(
            {"output_root": args.output_root, "runtime_root": args.runtime_root, "state_root": args.state_root},
            production_roots=production_roots,
            read_only_roots=[candidate_root] if candidate_root else (),
        )
    except (rr.RecoveryIsolationError, rr.RecoveryPlanError) as exc:
        _emit({"status": "REFUSED", "reason": str(exc), "operating_mode": rr.OPERATING_MODE, "provider_calls": 0})
        return 2
    layout = rr.RecoveryLayout(roots["output_root"], roots["runtime_root"], roots["state_root"])
    writer = rr.RecoveryWriter(roots)

    existing_plan = rr._load_json(layout.plan_path) if layout.plan_path.is_file() else None
    try:
        if isinstance(existing_plan, Mapping):
            requested = rr.build_plan(
                target_session=target, candidates=existing_plan["acquisition_attempt_cohort"]["tickers"],
                candidate_source=existing_plan["acquisition_attempt_cohort"]["source"],
                foreign_flow_cohort=existing_plan["foreign_flow"]["cohort"] if not args.no_foreign_flow else [],
                call_budget=args.call_budget if args.call_budget is not None else existing_plan["controls"]["call_budget"],
                max_transient_retries=args.max_transient_retries,
                min_start_interval_seconds=args.min_start_interval_seconds,
                max_attempts_per_ticker=args.max_attempts_per_ticker,
                stop_after_consecutive_429=args.stop_after_consecutive_429,
                foreign_flow_call_budget=args.foreign_flow_call_budget,
            )
            diffs = rr.plan_matches(existing_plan, requested)
            if diffs:
                raise rr.RecoveryPlanError("FROZEN_PLAN_MISMATCH:" + ",".join(diffs))
            plan = dict(existing_plan)
            plan_state = "RESUMED_FROZEN_PLAN"
        else:
            if not candidate_root:
                raise rr.RecoveryPlanError("CANDIDATE_RUNTIME_ROOT_REQUIRED_TO_FREEZE_PLAN")
            source = rr.read_candidate_source(Path(candidate_root))
            plan = rr.build_plan(
                target_session=target, candidates=source["tickers"], candidate_source=source["database"],
                metadata_overlay=source["overlay"], foreign_flow_cohort=_foreign_flow_cohort(not args.no_foreign_flow),
                call_budget=args.call_budget, max_transient_retries=args.max_transient_retries,
                min_start_interval_seconds=args.min_start_interval_seconds,
                max_attempts_per_ticker=args.max_attempts_per_ticker,
                stop_after_consecutive_429=args.stop_after_consecutive_429,
                foreign_flow_call_budget=args.foreign_flow_call_budget, created_at=now_iso(),
            )
            writer.write_json_atomic(layout.plan_path, plan)
            plan_state = "FROZEN_NEW_PLAN"
    except rr.RecoveryPlanError as exc:
        _emit({"status": "REFUSED", "reason": str(exc), "operating_mode": rr.OPERATING_MODE, "provider_calls": 0})
        return 2

    summary: dict[str, Any] = {
        "operating_mode": rr.OPERATING_MODE, "target_session": target, "plan_state": plan_state,
        "plan_identity": plan["artifact_identity"], "candidate_count": plan["acquisition_attempt_cohort"]["candidate_count"],
        "controls": plan["controls"], "foreign_flow_cohort": plan["foreign_flow"]["cohort"],
        "roots": {k: str(v) for k, v in roots.items()},
        "layout": {
            "plan": str(layout.plan_path), "journal": str(layout.state_root / "journal"),
            "raw": str(layout.state_root / "raw"), "reconstruction": str(layout.reconstruction_path),
            "quality": str(layout.quality_path), "foreign_flow": str(layout.foreign_flow_path),
        },
        **rr.HARD_LABELS,
    }
    if args.plan_only:
        summary.update(status="PLAN_ONLY", provider_calls=0)
        _emit(summary)
        return 0

    counters = rr.RunCounters()
    pacer = rr.Pacer(plan["controls"]["min_start_interval_seconds"], clock=clock, sleep=sleep)
    if args.analyze_only:
        acquisition = {"status": "ANALYZE_ONLY", "network_calls_this_run": 0}
        journals = {t: rr._load_json(layout.journal_path(t)) or {} for t in plan["acquisition_attempt_cohort"]["tickers"]}
        ff_status = "ANALYZE_ONLY"
    else:
        if not args.acknowledge_live_provider_calls:
            summary.update(status="REFUSED", reason="LIVE_PROVIDER_CALLS_NOT_ACKNOWLEDGED", provider_calls=0)
            _emit(summary)
            return 2
        if fetcher is None:
            from dnse_bulk_market_data import fetch_capability_raw

            fetcher = fetch_capability_raw
        if credentials is None:
            from dnse_access import credentials_for_request
            from dnse_secrets_env import ensure_credentials_loaded

            ensure_credentials_loaded()
            credentials = credentials_for_request()
            if not credentials:
                summary.update(status="REFUSED", reason="DNSE_CREDENTIAL_INJECTION_REQUIRED", provider_calls=0)
                _emit(summary)
                return 2
        acquisition = rr.acquire_ohlc(
            plan=plan, layout=layout, writer=writer, fetcher=fetcher, api_key=credentials[0],
            api_secret=credentials[1], pacer=pacer, counters=counters, now_iso=now_iso,
        )
        journals = acquisition.pop("journals")
        ff_status = "SKIPPED"
        if plan["foreign_flow"]["cohort"] and acquisition["status"] not in (rr.RUN_STOPPED_AUTH, rr.RUN_STOPPED_RATE_LIMIT):
            ff = rr.acquire_foreign_flow(
                plan=plan, layout=layout, writer=writer, fetcher=fetcher, api_key=credentials[0],
                api_secret=credentials[1], pacer=pacer, counters=counters, now_iso=now_iso,
            )
            ff_status = ff["status"]
    foreign_flow = None
    if plan["foreign_flow"]["cohort"]:
        foreign_flow = rr.normalize_foreign_flow(plan=plan, layout=layout, writer=writer)
        writer.write_json_atomic(layout.foreign_flow_path, foreign_flow)
    quality = rr.build_quality_report(plan, journals)
    writer.write_json_atomic(layout.quality_path, quality)
    reconstruction = rr.build_reconstruction(
        plan=plan, layout=layout, journals=journals, quality=quality, foreign_flow=foreign_flow,
        acquisition_status=acquisition["status"],
    )
    writer.write_json_atomic(layout.reconstruction_path, reconstruction)
    run_state = {
        "operating_mode": rr.OPERATING_MODE, "target_session": target, "plan_identity": plan["artifact_identity"],
        "acquisition_status": acquisition["status"], "foreign_flow_status": ff_status,
        "network_calls_this_run": acquisition.get("network_calls_this_run", 0),
        "counters": counters.as_dict(), "updated_at": now_iso(),
        "reconstruction_identity": reconstruction["artifact_identity"],
    }
    writer.write_json_atomic(layout.run_state_path, run_state)
    summary.update(
        status=acquisition["status"], foreign_flow_status=ff_status, counters=counters.as_dict(),
        quality={k: quality[k] for k in (
            "attempted_count", "exact_session_count", "exact_over_attempted_ratio", "provider_rejected_count",
            "prior_session_only_count", "no_history_count", "transport_failure_count", "rate_limit_count",
            "unknown_count", "not_attempted_count")},
        foreign_flow_complete=None if foreign_flow is None else foreign_flow["complete_count"],
        reconstruction_identity=reconstruction["artifact_identity"],
        pacing_seconds_slept=round(pacer.slept, 3),
    )
    _emit(summary)
    return 0 if acquisition["status"] in (rr.RUN_COMPLETE, "ANALYZE_ONLY") else 3


if __name__ == "__main__":
    raise SystemExit(main())
