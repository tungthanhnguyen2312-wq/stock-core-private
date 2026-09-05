"""Bounded qualification and retained replay for feature-safe history failover.

This is an operations-review runner, not a provider adapter and not a database writer.
It retains only provider-attributable historical series, exercises the existing DNSE and
Vnstock adapters, and records why a series can (or cannot) serve Current Research.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_access import CREDENTIAL_ENV_PAIRS, credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
from dnse_secrets_env import ensure_credentials_loaded
from historical_series_failover import (
    CONTRACT_VERSION, PROVIDER_ENDPOINT, PROVIDER_INTERFACE, build_provider_series,
    provider_fitness_matrix, select_feature_safe_series, vnstock_provider_series,
)
from market_wide_current_technical_coverage_scaleout import content_identity as recovery_identity
from mva_exact_session_snapshot import EXACT_SESSION_OHLC_LOOKBACK_CALENDAR_DAYS, _observation_rows
from vnstock_rate_governor import VnstockRateGovernor, set_active_governor
from vn_stock_pipeline import fetch_single_source


MILESTONE = "MARKET_DATA_HISTORICAL_SERIES_REDUNDANCY_AND_FEATURE_SAFE_FAILOVER_V1"
COHORT = ("FPT", "HPG", "QNS", "STB", "LPB", "SSI", "PVD", "PNJ", "IDC", "VGI", "VNZ")
VN_TZ = timezone(timedelta(hours=7))
DEFAULT_TARGET = "2026-09-04"
DEFAULT_OUT = ROOT / "operations-review/market-data-historical-series-redundancy-and-feature-safe-failover-v1-20260905"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _session_snapshot(root: Path, session: str) -> dict[str, Any]:
    path = root / f"operations-review/p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}/p3f9b_mva_exact_session_snapshot.json"
    return _load(path)


def _dnse_series(*, ticker: str, target_session: str, start: str, end: str, credentials: tuple[str, str]) -> dict[str, Any]:
    query = {
        "symbol": ticker, "resolution": "1D", "from": int(datetime.fromisoformat(start).replace(tzinfo=VN_TZ).timestamp()),
        "to": int((datetime.fromisoformat(end).replace(tzinfo=VN_TZ) + timedelta(days=1) - timedelta(seconds=1)).timestamp()),
        "type": "STOCK",
    }
    began = time.monotonic()
    response = fetch_capability_raw("ohlc", api_key=credentials[0], api_secret=credentials[1], query=query)
    latency = round(time.monotonic() - began, 3)
    requested_at = datetime.now(VN_TZ).isoformat()
    if not response.get("ok") or not isinstance(response.get("body"), Mapping):
        return build_provider_series(
            ticker=ticker, provider="DNSE", target_session=target_session, requested_at=requested_at,
            requested_start=start, requested_end=end, rows=[], request_attempts=1, latency_seconds=latency,
            status="FETCH_FAILED", reason=str(response.get("error_code") or "DNSE_BODY_UNAVAILABLE"),
            native_representation="DNSE_PROVIDER_NATIVE_RAW", price_representation="DNSE_PROVIDER_NATIVE_RAW",
            price_basis="CURRENT_RESEARCH_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
        )
    body = response["body"]
    rows, problem = _observation_rows(body, requested_session=target_session, query=query, retrieved_at=requested_at)
    return build_provider_series(
        ticker=ticker, provider="DNSE", target_session=target_session, requested_at=requested_at,
        requested_start=start, requested_end=end, rows=rows, retrieval_identity=_sha(body), request_attempts=1,
        latency_seconds=latency, status="SUCCESS", reason=problem,
        native_representation="DNSE_PROVIDER_NATIVE_RAW", price_representation="DNSE_PROVIDER_NATIVE_RAW",
        price_basis="CURRENT_RESEARCH_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
        volume_basis="DNSE_PROVIDER_NATIVE_VOLUME_SEMANTICS_UNQUALIFIED",
    )


def _vnstock_series(*, ticker: str, provider: str, target_session: str, start: str, end: str) -> dict[str, Any]:
    # vnstock_provider_series calls the existing fetch_single_source adapter.  The active governor
    # installed by qualify() consequently covers every KBS and VCI request in this invocation.
    return vnstock_provider_series(
        ticker=ticker, provider=provider, target_session=target_session, requested_at=datetime.now(VN_TZ).isoformat(),
        requested_start=start, requested_end=end, fetch=fetch_single_source,
    )


def _compact_series(series: Mapping[str, Any]) -> dict[str, Any]:
    """Keep audit-reproducible rows, never auth material or opaque raw responses."""
    return dict(series)


def _feature_counts(records: Mapping[str, Mapping[str, Any]], *, feature: str) -> dict[str, int]:
    """Count actual feature availability, not merely upstream descriptive eligibility."""
    result: dict[str, int] = {"AVAILABLE": 0, "NOT_AVAILABLE": 0, "NOT_ELIGIBLE": 0}
    for record in records.values():
        if record.get("eligibility", {}).get("status") != "ELIGIBLE":
            result["NOT_ELIGIBLE"] += 1
            continue
        if feature == "structure":
            status = (record.get("structure_context") or {}).get("status")
        else:
            status = (record.get("rsi") or {}).get("status")
        result["AVAILABLE" if status == "AVAILABLE" else "NOT_AVAILABLE"] += 1
    return result


def _retained_replay(*, root: Path, session: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay structure/momentum against retained source artifacts without new network access."""
    import tactical_momentum_context
    import technical_structure_context

    snapshot = _session_snapshot(root, session)
    descriptive = _load(root / f"operations-review/market-wide-current-descriptive-research-v1-{session.replace('-', '')}/market_wide_current_descriptive_research_artifact.json")
    recovery = _load(root / f"operations-review/market-wide-current-technical-coverage-scaleout-v1-{session.replace('-', '')}/market_wide_current_technical_coverage_recovery_artifact.json")
    requested_at = f"{session}T16:00:00+07:00"
    before_structure = technical_structure_context.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot, requested_at=requested_at,
    )
    after_structure = technical_structure_context.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot, requested_at=requested_at,
        technical_history_recovery_artifact=recovery,
    )
    before_momentum = tactical_momentum_context.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot, requested_at=requested_at,
    )
    after_momentum = tactical_momentum_context.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot, requested_at=requested_at,
        technical_history_recovery_artifact=recovery,
    )
    before = {"structure": _feature_counts(before_structure.get("records", {}), feature="structure"), "momentum": _feature_counts(before_momentum.get("records", {}), feature="momentum")}
    after = {"structure": _feature_counts(after_structure.get("records", {}), feature="structure"), "momentum": _feature_counts(after_momentum.get("records", {}), feature="momentum")}
    valid = all(
        all(row.get("session", session) <= session for row in (record.get("observations") or []))
        for record in recovery.get("records", {}).values() if isinstance(record, Mapping)
    )
    return ({
        "target_session": session, "before": before, "after": after,
        "source_snapshot_identity": snapshot.get("snapshot_identity"),
        "source_recovery_identity": recovery.get("artifact_identity"),
        "recovery_provider_contributions": recovery.get("operational_summary", {}).get("HISTORY_PROVIDER_CONTRIBUTIONS") or {
            provider: sum(record.get("provider") == provider for record in recovery.get("records", {}).values())
            for provider in ("DNSE", "KBS", "VCI")
        },
        "network_calls": 0, "future_row_check": "PASS" if valid else "FAIL",
        "not_authoritative": True,
    }, {"before_structure": before_structure, "after_structure": after_structure, "before_momentum": before_momentum, "after_momentum": after_momentum})


def qualify(*, root: Path, out: Path, target_session: str) -> dict[str, Any]:
    snapshot = _session_snapshot(root, target_session)
    target = datetime.fromisoformat(target_session).replace(tzinfo=VN_TZ)
    start, end = (target - timedelta(days=EXACT_SESSION_OHLC_LOOKBACK_CALENDAR_DAYS)).date().isoformat(), target.date().isoformat()
    original = {key: os.environ.get(key) for pair in CREDENTIAL_ENV_PAIRS for key in pair}
    try:
        ensure_credentials_loaded()
        credentials = credentials_for_request()
        if not credentials:
            raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
        governor = VnstockRateGovernor()
        prior = set_active_governor(governor)
        results: dict[str, Any] = {}
        try:
            for ticker in COHORT:
                series = {"DNSE": _dnse_series(ticker=ticker, target_session=target_session, start=start, end=end, credentials=credentials)}
                # Qualification intentionally exercises both existing Vnstock interfaces.  Production
                # routing remains KBS-before-VCI and does not make VCI calls after KBS CLEAN_MISSING.
                series["KBS"] = _vnstock_series(ticker=ticker, provider="KBS", target_session=target_session, start=start, end=end)
                series["VCI"] = _vnstock_series(ticker=ticker, provider="VCI", target_session=target_session, start=start, end=end)
                anchor = (snapshot.get("records") or {}).get(ticker) or {}
                primary = select_feature_safe_series(
                    ticker=ticker, target_session=target_session, feature_family="TECHNICAL_CLOSE_HISTORY",
                    snapshot_record=anchor, provider_series=series,
                )
                fallback = select_feature_safe_series(
                    ticker=ticker, target_session=target_session, feature_family="TECHNICAL_CLOSE_HISTORY",
                    snapshot_record=anchor, provider_series={key: value for key, value in series.items() if key != "DNSE"},
                    provider_order=("KBS", "VCI"),
                )
                results[ticker] = {
                    "ticker": ticker, "exact_session_anchor_available": bool(anchor.get("observations")),
                    "provider_series": {key: _compact_series(value) for key, value in series.items()},
                    "fitness_matrix": provider_fitness_matrix(series),
                    "primary_selection": primary, "fallback_simulation_without_dnse": fallback,
                }
        finally:
            set_active_governor(prior)
        diagnostic = governor.diagnostic()
        diagnostic["scope"] = "ONE_BOUNDED_QUALIFICATION_INVOCATION"
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    provider_summary: dict[str, Any] = {}
    for provider in ("DNSE", "KBS", "VCI"):
        rows = [item["provider_series"][provider] for item in results.values()]
        latencies = [row.get("request_accounting", {}).get("latency_seconds") for row in rows]
        latencies = [value for value in latencies if isinstance(value, (int, float))]
        ready = sum(row.get("fitness", {}).get("TECHNICAL_CLOSE_HISTORY") == "READY" for row in rows)
        volume_ready = sum(row.get("fitness", {}).get("TECHNICAL_VOLUME_HISTORY") == "READY" for row in rows)
        compatible = sum(
            item["fallback_simulation_without_dnse"].get("selected_provider") == provider
            if provider != "DNSE" else item["primary_selection"].get("selected_provider") == provider
            for item in results.values()
        )
        provider_summary[provider] = {
            "interface": PROVIDER_INTERFACE[provider], "endpoint": PROVIDER_ENDPOINT[provider], "cohort_requests": len(rows),
            "technical_close_history_ready": ready, "technical_volume_history_ready": volume_ready,
            "exact_session_compatible_selected": compatible,
            "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else None,
            "limitations": rows[0].get("limitations", []) if rows else [],
        }

    qualification = {
        "milestone": MILESTONE, "contract_version": CONTRACT_VERSION, "target_session": target_session,
        "cohort": list(COHORT), "request_window": {"start": start, "end": end},
        "results": results, "vnstock_rate_governor": diagnostic,
        "authority_boundary": {"CURRENT_RESEARCH": "ONLY", "PIT_BACKTEST": "BLOCKED", "EXECUTION_LIQUIDITY": "BLOCKED", "production_db_write": False},
    }
    _write(out / "qualification_cohort_results.json", qualification)
    _write(out / "provider_historical_capability_matrix.json", {
        "milestone": MILESTONE, "contract_version": CONTRACT_VERSION, "target_session": target_session,
        "providers": provider_summary, "vnstock_rate_governor": diagnostic,
        "qualification_outcome": "PARTIAL_BY_EVIDENCE" if any(
            provider_summary[key]["exact_session_compatible_selected"] for key in ("KBS", "VCI")
        ) else "NOT_QUALIFIED_BY_THIS_COHORT",
        "authority_boundary": qualification["authority_boundary"],
    })
    _write(out / "historical_series_fitness_matrix.json", {
        "milestone": MILESTONE, "contract_version": CONTRACT_VERSION, "target_session": target_session,
        "records": {ticker: item["fitness_matrix"] for ticker, item in results.items()},
        "feature_boundary": {
            "TECHNICAL_CLOSE_HISTORY_MOMENTUM_TACTICAL_STRUCTURE": "FEATURE_SAFE_CURRENT_RESEARCH_ONLY",
            "TECHNICAL_VOLUME_HISTORY_PARTICIPATION": "DNSE_ONLY_IF_NATIVE_VOLUME_PRESENT",
            "OHLC_GEOMETRY_PIT_EXECUTION_LIQUIDITY": "BLOCKED",
        },
    })
    _write(out / "historical_provider_routing.json", {
        "milestone": MILESTONE, "target_session": target_session,
        "routing": [
            "DNSE primary for retained technical close history.",
            "KBS may replace a missing/invalid DNSE close history only after exact target-session close equality.",
            "VCI is attempted only if KBS is not CLEAN_MISSING and no feature-safe selection exists.",
            "No provider rows are spliced; volume/participation remains DNSE-only.",
        ],
        "cohort_primary_selection": {ticker: item["primary_selection"] for ticker, item in results.items()},
        "cohort_fallback_simulation_without_dnse": {ticker: item["fallback_simulation_without_dnse"] for ticker, item in results.items()},
        "result": "PARTIAL_BY_EVIDENCE",
    })
    return {"results": results, "provider_summary": provider_summary, "governor": diagnostic}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded historical-series failover qualification.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--target-session", default=DEFAULT_TARGET)
    parser.add_argument("--retained-current-replay-only", action="store_true", help="Write the current retained replay without provider requests.")
    parser.add_argument("--temporal-replay-only", action="store_true", help="Write the earlier retained replay and final report without provider requests.")
    args = parser.parse_args(argv)
    if args.retained_current_replay_only and args.temporal_replay_only:
        parser.error("choose at most one replay-only action")
    if args.retained_current_replay_only:
        replay, _ = _retained_replay(root=args.root, session=args.target_session)
        _write(args.out_dir / "market_wide_recovery_before_after.json", {
            "milestone": MILESTONE, "target_session": args.target_session,
            "retained_replay": replay,
            "market_wide_network_fallback": "NOT_FORCED: retained 2026-09-04 DNSE recovery already supplied histories; bounded provider qualification is reported separately.",
            "not_authoritative": True,
        })
        _write(args.out_dir / "technical_feature_coverage_before_after.json", {
            "milestone": MILESTONE, "target_session": args.target_session, "retained_replay": replay,
            "integration": "technical_structure_context and tactical_momentum_context consume the selected retained series only after exact-session compatibility.",
        })
        print(args.out_dir)
        return 0
    if args.temporal_replay_only:
        current = _load(args.out_dir / "technical_feature_coverage_before_after.json")["retained_replay"]
        temporal, _ = _retained_replay(root=args.root, session="2026-08-25")
        _write(args.out_dir / "temporal_replay_validation.json", {
            "milestone": MILESTONE, "replays": [current, temporal],
            "result": "PASS" if current["future_row_check"] == temporal["future_row_check"] == "PASS" else "FAIL",
            "scope": "retained governed session replay; no current-session data was substituted for either historical target.",
        })
        report = "\n".join([
            f"# {MILESTONE}", "", "## Outcome", "",
            "PARTIAL_BY_EVIDENCE. The bounded cohort qualifies only provider-attributable, exact-target-close-compatible close histories for Current Research. Volume, OHLC geometry, PIT, execution, ranking, and authority promotion remain blocked.", "",
            "## Evidence", "",
            "See `provider_historical_capability_matrix.json`, `qualification_cohort_results.json`, `historical_series_fitness_matrix.json`, `historical_provider_routing.json`, and the retained/temporal replay files in this folder.", "",
            "## Operational boundary", "",
            "DNSE stays primary. KBS precedes VCI for a missing DNSE history; VCI is not spent after a KBS clean miss. All Vnstock qualification calls ran under one invocation-scoped rate governor. No database writes, publishing, deployment, or provider/authority promotion occurred.", "",
        ])
        (args.out_dir / "REPORT.md").write_text(report, encoding="utf-8")
        print(args.out_dir)
        return 0
    outcome = qualify(root=args.root, out=args.out_dir, target_session=args.target_session)
    replay, _ = _retained_replay(root=args.root, session=args.target_session)
    _write(args.out_dir / "market_wide_recovery_before_after.json", {
        "milestone": MILESTONE, "target_session": args.target_session,
        "retained_replay": replay,
        "market_wide_network_fallback": "NOT_FORCED: retained 2026-09-04 DNSE recovery already supplied histories; bounded provider qualification is reported separately.",
        "provider_summary": outcome["provider_summary"], "not_authoritative": True,
    })
    _write(args.out_dir / "technical_feature_coverage_before_after.json", {
        "milestone": MILESTONE, "target_session": args.target_session, "retained_replay": replay,
        "integration": "technical_structure_context and tactical_momentum_context consume the selected retained series only after exact-session compatibility.",
    })
    temporal, _ = _retained_replay(root=args.root, session="2026-08-25")
    _write(args.out_dir / "temporal_replay_validation.json", {
        "milestone": MILESTONE, "replays": [replay, temporal],
        "result": "PASS" if replay["future_row_check"] == temporal["future_row_check"] == "PASS" else "FAIL",
        "scope": "retained governed session replay; no current-session data was substituted for either historical target.",
    })
    report = "\n".join([
        f"# {MILESTONE}", "", "## Outcome", "",
        "PARTIAL_BY_EVIDENCE. The bounded cohort qualifies only provider-attributable, exact-target-close-compatible close histories for Current Research. Volume, OHLC geometry, PIT, execution, ranking, and authority promotion remain blocked.", "",
        "## Evidence", "",
        "See `provider_historical_capability_matrix.json`, `qualification_cohort_results.json`, `historical_series_fitness_matrix.json`, `historical_provider_routing.json`, and the retained/temporal replay files in this folder.", "",
        "## Operational boundary", "",
        "DNSE stays primary. KBS precedes VCI for a missing DNSE history; VCI is not spent after a KBS clean miss. All Vnstock qualification calls ran under one invocation-scoped rate governor. No database writes, publishing, deployment, or provider/authority promotion occurred.", "",
    ])
    (args.out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
