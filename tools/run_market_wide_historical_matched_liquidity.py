"""Build the retained-only historical regular-board matched-liquidity evidence package.

No network, provider, database, Daily operation, or runtime registry write is
performed.  The runner reuses the retained Task-160 canonical-Trades manifest,
its logical-unit coverage, and the existing exact-reconciled G1 value lane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_file, atomic_write_json
from governed_trading_session_calendar import load_governed_trading_session_calendar
from market_wide_historical_matched_liquidity import (
    CONTRACT_VERSION,
    EXACT_WINDOW,
    FEATURES,
    QUALIFIED_MATCHED_VALUE,
    build_artifact,
    content_identity,
    coverage_distribution,
    daily_cells_from_retained_evidence,
    unit_coverage_from_manifest,
)


MILESTONE = "MARKET_WIDE_HISTORICAL_MATCHED_LIQUIDITY_AND_ADTV_FOUNDATION_V1"
EVIDENCE_DIR = ROOT / "operations-review" / "market-wide-historical-matched-liquidity-adtv-foundation-v1-20260905"
TASK160_DIR = WORKSPACE / "operations-review" / "task-160-canonical-materialization-v1-20260817"
UNIT_COVERAGE = WORKSPACE / "operations-review" / "task-160-controlled-rerun-v1-20260817" / "composite" / "composite_unit_coverage.json"
MATCHED_VALUE_DIR = ROOT / "operations-review" / "fhsc-historical-matched-value-coverage-scaleout-v1"
INTEGRATED_20260904 = ROOT / "operations-review" / "canonical-post-close-v1" / "2026-09-04" / "enrichment" / "integrated_investment_decision_product.json"
OFFICIAL_UNIVERSE = ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
GOVERNED_CALENDAR = ROOT / "config" / "governed_trading_session_calendar_v1.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(path: Path, prefix: str) -> str:
    return f"{prefix}:{_sha256_file(path)}"


def _write_json(out_dir: Path, name: str, payload: Mapping[str, Any]) -> None:
    atomic_write_json(out_dir / name, payload)


def _write_report(out_dir: Path, report: Mapping[str, Any]) -> None:
    coverage = report["market_wide_coverage"]
    value = report["daily_matched_value"]
    lines = [
        "# Market-wide historical matched liquidity and ADTV foundation V1",
        "",
        "## Result",
        "",
        f"`{report['terminal_status']}`. Canonical Trades is the primary historical input, but its retained session range ends at `{report['canonical_trades_input']['last_session']}`. Therefore neither requested replay target has a canonical-Trades target-session window.",
        "",
        "## Coverage",
        "",
        f"- Current governed universe: {coverage['universe_denominator']} tickers.",
        f"- Current-universe exchange/market distribution: {', '.join(f'{key}={value}' for key, value in sorted(coverage['exchange_or_market_distribution'].items()))}.",
        f"- Canonical Trades materialization: {report['canonical_trades_input']['canonical_rows']:,} rows across {report['canonical_trades_input']['retained_session_count']} sessions.",
        f"- Exact canonical G1 matched-value daily cells retained from the existing reconciliation lane: {value['qualified_matched_value_cells']:,}.",
        f"- Exact ADV20 / ADV60 / ADTV20 / ADTV60 at 2026-09-04: 0 / 0 / 0 / 0.",
        "- Position sizing remains not evaluated and false for every ticker.",
        "",
        "## Boundaries",
        "",
        "- No daily-provider `v` or `va` semantics are used or promoted.",
        "- G1 is the explicit regular-board matched scope; G4 and T1/T3/T4/T6 remain separate and are not summed into it.",
        "- The existing exact-reconciled G1 value cohort does not qualify a generic matched-share volume field. ADV stays fail-closed.",
        "- No RAW_AS_TRADED, PIT, execution, participation cap, sizing, market-impact, or slippage authority is created.",
        "",
        "## Primary blocker",
        "",
        "The principal blocker is retained data coverage: the canonical trade corpus stops on 2026-08-11, before the requested 2026-08-25 and 2026-09-04 target sessions. Within the retained range, unit/board-value reconciliation is an additional explicit limiter for non-exact cells.",
        "",
    ]
    atomic_write_file(out_dir / "REPORT.md", "\n".join(lines), validator=None)


def _universe(integrated: Mapping[str, Any], official: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    exchanges = {
        str(ticker).upper(): str((row or {}).get("exchange_or_market") or "UNKNOWN")
        for ticker, row in (official.get("records") or {}).items()
    }
    return {
        str(ticker).upper(): {"exchange_or_market": exchanges.get(str(ticker).upper(), "UNKNOWN")}
        for ticker in (integrated.get("records") or {})
    }


def _watchlist(primary: Mapping[str, Any], daily: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, Any]:
    requested = ("FPT", "HPG", "SSI", "QNS", "PVD", "PNJ", "VNM", "VCB", "EVF", "NVL", "POW", "PAN")
    exact = [row for row in daily.values() if row.get("matched_value_state") == QUALIFIED_MATCHED_VALUE]
    exact.sort(key=lambda row: (float(row.get("regular_board_matched_value_vnd") or 0), row["ticker"], row["session"]))
    failed = [row for row in daily.values() if row.get("session_completeness") == "KNOWN_FAILED"]
    no_trade = [row for row in daily.values() if row.get("session_completeness") == "NO_TRADES_CONFIRMED"]
    return {
        "target_session": primary["target_session"],
        "required_tickers": {ticker: primary["records"].get(ticker, {"status": "NOT_IN_CURRENT_UNIVERSE"}) for ticker in requested},
        "real_examples": {
            "high_exact_daily_matched_value": exact[-1] if exact else "NO_REAL_CASE",
            "low_exact_daily_matched_value": exact[0] if exact else "NO_REAL_CASE",
            "known_failed_unit": failed[0] if failed else "NO_REAL_CASE",
            "confirmed_no_trade_session": no_trade[0] if no_trade else "NO_REAL_CASE",
            "coverage_restricted_window": "NO_REAL_CASE_AT_TARGET_SESSION_BECAUSE_TARGET_NOT_IN_CANONICAL_TRADES_CALENDAR",
            "semantic_blocker": "NO_REAL_CASE_AT_TARGET_SESSION_BECAUSE_TARGET_NOT_IN_CANONICAL_TRADES_CALENDAR",
        },
    }


def _feature_counts(artifact: Mapping[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for feature_id, _, _, _ in FEATURES:
        result[feature_id] = sum(record["features"][feature_id]["status"] == EXACT_WINDOW for record in artifact["records"].values())
    return result


def build(out_dir: Path = EVIDENCE_DIR, *, calendar_path: Path = GOVERNED_CALENDAR) -> dict[str, Any]:
    manifest_path = TASK160_DIR / "shadow" / "materialization_manifest.json"
    canonical_root = TASK160_DIR / "shadow" / "canonical" / "provider=DNSE" / "dataset=trades_history"
    reconciliation_path = MATCHED_VALUE_DIR / "historical_matched_value_reconciliation_artifact.json"
    qualified_path = MATCHED_VALUE_DIR / "historical_matched_value_qualified_rows.json"
    for path in (manifest_path, UNIT_COVERAGE, reconciliation_path, qualified_path, INTEGRATED_20260904, OFFICIAL_UNIVERSE):
        if not path.exists():
            raise FileNotFoundError(f"RETAINED_INPUT_MISSING:{path}")

    manifest, unit_payload = _load(manifest_path), _load(UNIT_COVERAGE)
    reconciliation, qualified = _load(reconciliation_path), _load(qualified_path)
    integrated, official = _load(INTEGRATED_20260904), _load(OFFICIAL_UNIVERSE)
    partitions = sorted(canonical_root.glob("session_date=*/part-00000.parquet"))
    if len(partitions) != len(manifest.get("sessions") or []):
        raise ValueError("CANONICAL_TRADES_PARTITION_MANIFEST_MISMATCH")
    schema = pq.ParquetFile(partitions[0]).schema_arrow.names
    required_fields = {"symbol", "session_date", "raw_timestamp", "timestamp_normalized", "price", "quantity", "board_id", "raw_record_identity", "source_page_payload_hash"}
    if not required_fields.issubset(set(schema)):
        raise ValueError("CANONICAL_TRADES_INPUT_SCHEMA_MISSING_REQUIRED_FIELDS")

    units = unit_coverage_from_manifest(unit_payload["units"])
    daily = daily_cells_from_retained_evidence(
        unit_coverage=units,
        reconciliation_rows=reconciliation["rows"],
        qualified_value_rows=qualified,
    )
    if len(daily) != len(units):
        raise ValueError("DAILY_CELL_COVERAGE_RESIDUAL")
    observed_sessions = list(unit_payload["session_universe"])
    calendar = load_governed_trading_session_calendar(calendar_path)
    universe = _universe(integrated, official)
    source_identities = {
        "canonical_trades_manifest": _source_identity(manifest_path, "sha256"),
        "canonical_trades_unit_coverage": _source_identity(UNIT_COVERAGE, "sha256"),
        "canonical_trades_reconciliation": _source_identity(reconciliation_path, "sha256"),
        "qualified_g1_matched_value_rows": _source_identity(qualified_path, "sha256"),
        "governed_current_universe": integrated.get("artifact_identity"),
        "governed_trading_session_calendar": calendar.identity,
    }
    primary = build_artifact(target_session="2026-09-04", universe=universe, calendar=calendar, daily_cells=daily, source_identities=source_identities)
    temporal = build_artifact(target_session="2026-08-25", universe=universe, calendar=calendar, daily_cells=daily, source_identities=source_identities)
    if any(session > "2026-08-25" for _, session in daily):
        raise ValueError("FUTURE_TRADE_LEAK_ADMITTED")
    if any(record["target_session"] != "2026-08-25" for record in temporal["records"].values()):
        raise ValueError("FUTURE_LIQUIDITY_FEATURE_LEAK_ADMITTED")

    daily_coverage = coverage_distribution(daily)
    primary_features = _feature_counts(primary)
    session_states = Counter(row["session_completeness"] for row in daily.values())
    method_cohorts = {
        "canonical_g1_matched_value_exact_reconciled": sum(row.get("matched_value_state") == QUALIFIED_MATCHED_VALUE for row in daily.values()),
        "canonical_g1_matched_volume_semantics_unqualified": sum(row.get("matched_volume_state") == "SEMANTICS_UNQUALIFIED" for row in daily.values()),
        "confirmed_no_trade_sessions": sum(row.get("session_completeness") == "NO_TRADES_CONFIRMED" for row in daily.values()),
        "known_failed_sessions": sum(row.get("session_completeness") == "KNOWN_FAILED" for row in daily.values()),
    }
    blockers = dict(sorted(Counter(
        blocker for row in primary["records"].values() for feature in row["features"].values() for blocker in feature["blockers"]
    ).items()))
    canonical_contract = {
        "dataset": "DNSE_CANONICAL_TRADES_40_SESSION",
        "source_kind": "CANONICAL_EXECUTION",
        "producer": "task-160 canonical Trades materialization",
        "retained_session_range": [min(observed_sessions), max(observed_sessions)],
        "retained_session_count": len(observed_sessions),
        "analytical_session_calendar": calendar.to_dict(),
        "canonical_rows": manifest["aggregate"]["canonical_rows"],
        "schema_fields": schema,
        "identity_fields": ["symbol", "session_date", "raw_record_identity", "source_page_identity", "source_page_payload_hash", "source_record_index"],
        "execution_fields": ["board_id", "price", "quantity", "raw_timestamp", "timestamp_normalized"],
        "board_scope": {"regular_board": "G1", "excluded_components": ["G4", "T1", "T3", "T4", "T6"]},
        "price_unit": "G1 matched-VND formula qualified only in existing exact-reconciled daily cohort",
        "quantity_unit": "generic matched-share volume remains unqualified; no ADV emitted",
        "duplicate_handling": "raw_record_identity; materialization manifest reports duplicate_identities=0",
        "completeness_manifest": source_identities["canonical_trades_unit_coverage"],
        "semantic_limitations": manifest["semantic_limitations"],
    }
    daily_value = {
        "contract": "REGULAR_BOARD_MATCHED_VALUE_VND / canonical G1 only where existing exact reconciliation qualifies it",
        "qualified_matched_value_cells": method_cohorts["canonical_g1_matched_value_exact_reconciled"],
        "state_distribution": daily_coverage["matched_value_state_distribution"],
        "calculation_identity": "sum(G1.matchPrice_x_10_x_G1.matchQtty)_x_10_x_1000/v1",
        "daily_provider_va_used": False,
    }
    daily_volume = {
        "contract": "REGULAR_BOARD_MATCHED_VOLUME_SHARES / G1 only",
        "qualified_matched_volume_cells": sum(row.get("matched_volume_state") == "QUALIFIED_MATCHED_VOLUME" for row in daily.values()),
        "state_distribution": daily_coverage["matched_volume_state_distribution"],
        "daily_provider_v_used": False,
        "reason": "Existing canonical retention carries quantity but does not provide generic matched-share unit authority.",
    }
    exchange_distribution = dict(sorted(Counter(
        str(info.get("exchange_or_market") or "UNKNOWN") for info in universe.values()
    ).items()))
    report = {
        "executor": "CODEX", "milestone": MILESTONE, "terminal_status": "PARTIAL_BY_EVIDENCE",
        "canonical_trades_input": {"canonical_rows": canonical_contract["canonical_rows"], "retained_session_count": len(observed_sessions), "first_session": min(observed_sessions), "last_session": max(observed_sessions)},
        "daily_matched_value": daily_value,
        "market_wide_coverage": {
            "universe_denominator": len(universe),
            "exchange_or_market_distribution": exchange_distribution,
            **primary_features,
        },
        "primary_blocker": "CANONICAL_TRADES_HISTORY_ENDS_2026_08_11",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir, "liquidity_capability_inventory.json", {
        "contract_version": CONTRACT_VERSION,
        "capabilities": [
            {"capability": "canonical_trades_materialization", "producer": "Task-160", "input_artifact": str(manifest_path), "output_artifact": "canonical Trades Parquet", "provider": "DNSE", "market_scope": "40 retained sessions", "price_unit": "recorded; value qualified only in exact G1 cohort", "quantity_unit": "generic shares unqualified", "board_semantics": "G1 regular / G4 odd-lot / T* put-through", "historical_scope": "2026-06-17..2026-08-11", "current_research_fitness": "coverage restricted", "pit_fitness": "blocked", "execution_fitness": "blocked", "consumer": "this contract", "known_blocker": "target sessions beyond retained corpus"},
            {"capability": "current_descriptive_liquidity", "producer": "market_wide_current_liquidity_research", "input_artifact": "trades_latest", "output_artifact": "current session board composition", "provider": "DNSE", "market_scope": "current session", "price_unit": "not value authority", "quantity_unit": "provider raw", "board_semantics": "separate board families", "historical_scope": "none", "current_research_fitness": "descriptive only", "pit_fitness": "blocked", "execution_fitness": "blocked", "consumer": "optional AI bundle pass-through", "known_blocker": "not a trailing historical contract"},
            {"capability": "existing_exact_g1_matched_value", "producer": "historical_matched_trading_value_authority", "input_artifact": str(qualified_path), "output_artifact": "exact-reconciled G1 daily values", "provider": "DNSE canonical Trades + retained FHSC reconciliation", "market_scope": "qualified cohort only", "price_unit": "VND in exact cohort", "quantity_unit": "not generic ADV authority", "board_semantics": "G1 only", "historical_scope": "within 40 retained sessions", "current_research_fitness": "coverage restricted", "pit_fitness": "blocked", "execution_fitness": "promotion review required", "consumer": "this contract", "known_blocker": "no target-session coverage / no exact trailing window"},
        ],
    })
    _write_json(out_dir, "canonical_trades_input_contract.json", canonical_contract)
    _write_json(out_dir, "daily_matched_volume_coverage.json", daily_volume)
    _write_json(out_dir, "daily_matched_value_coverage.json", daily_value)
    _write_json(out_dir, "session_completeness_distribution.json", {"ticker_session_pairs": len(daily), "distribution": dict(sorted(session_states.items())), "known_failed_units": method_cohorts["known_failed_sessions"], "no_trade_confirmed": method_cohorts["confirmed_no_trade_sessions"]})
    _write_json(out_dir, "adv_adtv_coverage.json", {"target_session": primary["target_session"], "feature_status_distribution": primary["coverage"]["feature_status_distribution"], "exact_counts": primary_features, "no_calendar_day_imputation": True})
    _write_json(out_dir, "liquidity_blocker_distribution.json", {"target_session": primary["target_session"], "primary_blockers": blockers, "daily_cell_blockers": daily_coverage["blocker_distribution"], "primary_reason": report["primary_blocker"]})
    _write_json(out_dir, "method_cohort_distribution.json", method_cohorts)
    _write_json(out_dir, "market_wide_liquidity_replay_20260904.json", primary)
    _write_json(out_dir, "watchlist_liquidity_replay.json", _watchlist(primary, daily))
    _write_json(out_dir, "temporal_replay_validation.json", {"target_session": "2026-08-25", "future_trade_leak_admitted": 0, "future_liquidity_feature_leak_admitted": 0, "result": temporal, "limitation": "Target session is after the canonical Trades retention endpoint; no current session was used to fill the hole."})
    _write_json(out_dir, "portfolio_risk_readiness.json", {"universe_denominator": len(universe), "liquidity_research_ready": sum(bool(row["research_liquidity_eligible"]) for row in primary["records"].values()), "liquidity_execution_input_ready": sum(bool(row["execution_liquidity_input_eligible"]) for row in primary["records"].values()), "position_sizing_ready": 0, "position_sizing_status": "POSITION_SIZING_NOT_EVALUATED", "next_gate": "OWNER_REVIEW_ONLY"})
    _write_json(out_dir, "before_after_capability.json", {"before": {"exact_adtv20": 0, "exact_adtv60": 0, "research_liquidity_ready": 0, "execution_input_ready": 0, "position_sizing_ready": 0}, "after": {"exact_adtv20": primary_features["ADTV20_MATCHED_VND"], "exact_adtv60": primary_features["ADTV60_MATCHED_VND"], "research_liquidity_ready": sum(bool(row["research_liquidity_eligible"]) for row in primary["records"].values()), "execution_input_ready": sum(bool(row["execution_liquidity_input_eligible"]) for row in primary["records"].values()), "position_sizing_ready": 0}, "change": "A deterministic canonical-Trades completeness/window contract and explicit market-wide coverage; no target-session coverage or sizing authority increase."})
    _write_report(out_dir, report)
    return {**report, **content_identity(report)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=EVIDENCE_DIR)
    parser.add_argument("--calendar-path", type=Path, default=GOVERNED_CALENDAR,
                        help="Explicit governed analytical session calendar; never infer it from Trades coverage.")
    parser.add_argument("--twice", action="store_true", help="prove deterministic output identity")
    args = parser.parse_args(argv)
    first = build(args.out_dir, calendar_path=args.calendar_path)
    if args.twice and build(args.out_dir, calendar_path=args.calendar_path)["artifact_identity"] != first["artifact_identity"]:
        raise SystemExit("NONDETERMINISTIC_EVIDENCE_PACKAGE")
    print(json.dumps({"terminal_status": first["terminal_status"], "artifact_identity": first["artifact_identity"], "market_wide_coverage": first["market_wide_coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
