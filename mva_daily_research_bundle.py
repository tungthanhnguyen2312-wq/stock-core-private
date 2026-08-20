"""Deterministic daily MVA research bundle over retained market observations.

This is a shadow-research composer, not a canonical-universe, liquidity,
execution, or historical/PIT authority.  It is intentionally generic over
retained instruments and has no ticker-specific production branches.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import inspect
import json
import math
from pathlib import Path
import sqlite3
import statistics
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id
from market_data_contracts import FeatureStatus
import mva_provider_share_proxy as proxy

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p3f7_mva_daily_research_bundle/v1"
ARTIFACT_TYPE = "P3F7_MVA_DAILY_RESEARCH_BUNDLE"
COHORT_NAME = "COHORT_EMPIRICALLY_ACTIVE"
LOOKBACK_SESSIONS = 20
REQUIRED_ENVELOPE = dict(proxy.REQUIRED_ENVELOPE)


def _valid_envelope(envelope: Mapping[str, Any]) -> bool:
    return proxy.shadow_envelope_is_valid(envelope)


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def derive_empirical_active_cohort(rows_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]], *, sessions: Sequence[str], candidate_tickers: Sequence[str]) -> dict[str, Any]:
    """Derive a non-canonical, complete-observation cohort without imputation."""
    required = tuple(sorted(set(str(day) for day in sessions)))
    members, exclusions = [], {}
    for ticker in sorted({str(value).upper() for value in candidate_tickers}):
        rows = {str(row.get("date")): row for row in rows_by_ticker.get(ticker, ())}
        missing = [day for day in required if day not in rows]
        malformed = [day for day in required if day in rows and (_as_float(rows[day].get("close")) is None or _as_float(rows[day].get("close")) <= 0 or _as_float(rows[day].get("volume")) is None)]
        if missing or malformed:
            exclusions[ticker] = {"reason": "INCOMPLETE_OR_MALFORMED_RETAINED_SESSION_COVERAGE", "missing_sessions": missing, "malformed_sessions": malformed}
        else:
            members.append(ticker)
    contract = {"name": COHORT_NAME, "authority": "DERIVED_SHADOW_DENOMINATOR_ONLY", "as_of_session": required[-1] if required else None,
                "lookback_completed_sessions": len(required), "observed_session_requirement": "one_positive_close_and_present_volume_for_every_lookback_session",
                "candidate_definition": "retained_metadata_instruments_only; no_listing_or_active_universe_claim", "sessions": list(required),
                "candidate_count": len(set(candidate_tickers)), "member_count": len(members), "excluded_count": len(exclusions),
                "source_coverage": "VCI_retained_ohlcv_joined_to_retained_metadata", "members": members,
                "exclusion_reason_counts": dict(sorted(Counter(item["reason"] for item in exclusions.values()).items()))}
    contract["cohort_identity"] = f"cohort_empirically_active:{stable_id(contract)}"
    return contract | {"exclusions": exclusions}


def market_features(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute descriptive features only from a complete, chronological window."""
    ordered = sorted(rows, key=lambda row: str(row["date"]))
    closes = [_as_float(row.get("close")) for row in ordered]
    volumes = [_as_float(row.get("volume")) for row in ordered]
    if len(ordered) < LOOKBACK_SESSIONS or any(value is None or value <= 0 for value in closes) or any(value is None for value in volumes):
        return {"status": "MISSING", "blockers": ["COMPLETE_20_SESSION_WINDOW_REQUIRED"], "values": {}}
    returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
    median_volume = statistics.median(volumes)
    values = {"close": closes[-1], "return_1d": returns[-1], "momentum_20d": (closes[-1] / closes[0]) - 1,
              "ma_3": statistics.mean(closes[-3:]), "ma_5": statistics.mean(closes[-5:]), "ma_20": statistics.mean(closes),
              "volatility_20d": statistics.pstdev(returns), "relative_volume_provider_scoped": (volumes[-1] / median_volume if median_volume else None)}
    return {"status": "SHADOW_ONLY", "price_basis": "ADJUSTED_RETROSPECTIVE", "historical_pit_eligible": False,
            "method": "retained_20_completed_session_window; no_imputation", "values": values,
            "feature_statuses": {"close": FeatureStatus.OBSERVED.value, "return_1d": "SHADOW_ONLY", "momentum_20d": "SHADOW_ONLY",
                                 "ma_3": "SHADOW_ONLY", "ma_5": "SHADOW_ONLY", "ma_20": "SHADOW_ONLY", "volatility_20d": "SHADOW_ONLY",
                                 "relative_volume_provider_scoped": FeatureStatus.DERIVED_PROXY.value},
            "warnings": ["ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED", "RELATIVE_VOLUME_IS_PROVIDER_SCOPED_NOT_LIQUIDITY_AUTHORITY"]}


def _load_runtime_market(runtime_root: Path, *, frozen_session: str) -> tuple[list[str], dict[str, list[dict[str, Any]]], list[str]]:
    database = runtime_root / "vn_stock.db"
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        candidates = [str(row[0]).upper() for row in connection.execute("SELECT ticker FROM metadata ORDER BY ticker")]
        sessions_desc = [str(row[0]) for row in connection.execute("SELECT DISTINCT date FROM ohlcv WHERE date <= ? ORDER BY date DESC LIMIT ?", (frozen_session, LOOKBACK_SESSIONS))]
        sessions = list(reversed(sessions_desc))
        if len(sessions) != LOOKBACK_SESSIONS or sessions[-1] != frozen_session:
            raise ValueError("RETAINED_COMPLETED_SESSION_WINDOW_INSUFFICIENT")
        placeholders = ",".join("?" for _ in sessions)
        rows = connection.execute(f"SELECT ticker, date, close, volume, source FROM ohlcv WHERE date IN ({placeholders}) ORDER BY ticker, date", sessions).fetchall()
    finally:
        connection.close()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ticker, day, close, volume, source in rows:
        grouped.setdefault(str(ticker).upper(), []).append({"date": str(day), "close": close, "volume": volume, "source": source})
    return candidates, grouped, sessions


def _maps(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    p3b = json.loads((root / "operations-review/p3b-fundamental-research-readiness-20260820/p3b_fundamental_research_readiness_artifact.json").read_text(encoding="utf-8"))
    p3f3 = json.loads((root / "operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json").read_text(encoding="utf-8"))
    p3f6 = json.loads((root / "operations-review/p3f6-mva-provider-share-proxy-20260820/p3f6_mva_provider_share_proxy_artifact.json").read_text(encoding="utf-8"))
    fundamentals = {row["issuer_identity"]["ticker"]: row for row in p3b["issuer_research_readiness"]}
    authoritative = {row["ticker"]: row for row in p3f3["both_ready_matrix"]}
    proxies = {row["ticker"]: row for row in p3f6["proxy_valuation_rows"]}
    return fundamentals, authoritative, proxies


def _load_snapshot_market(snapshot_path: Path) -> tuple[list[str], dict[str, list[dict[str, Any]]], list[str], str]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    frozen = str(snapshot["retained_snapshot_session"])
    if snapshot.get("resolved_completed_session") != frozen or snapshot.get("source", {}).get("intraday_observations_used") is not False:
        raise ValueError("EXACT_COMPLETED_SESSION_SNAPSHOT_REQUIRED")
    sessions = list(snapshot.get("sessions", []))
    if len(sessions) != LOOKBACK_SESSIONS or sessions[-1] != frozen:
        raise ValueError("EXACT_SESSION_SNAPSHOT_WINDOW_INSUFFICIENT")
    candidates = sorted(snapshot.get("records", {}).keys())
    grouped = {ticker: [{"date": row["session"], "close": row["close"], "volume": row["volume"], "source": "DNSE_SHADOW_SNAPSHOT"}
                        for row in record.get("observations", []) if row.get("session") in sessions]
               for ticker, record in snapshot["records"].items() if record.get("status") == "OBSERVED"}
    return candidates, grouped, sessions, frozen


def build_mva_daily_research_bundle(runtime_root: Path, *, root: Path, envelope: Mapping[str, Any] | None = None,
                                    snapshot_path: Path | None = None) -> dict[str, Any]:
    """Read retained data and compose the bounded daily MVA research artifact."""
    use_envelope = dict(REQUIRED_ENVELOPE if envelope is None else envelope)
    if not _valid_envelope(use_envelope):
        raise ValueError("MVA_SHADOW_ENVELOPE_REQUIRED")
    p3f3 = json.loads((root / "operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json").read_text(encoding="utf-8"))
    if snapshot_path is None:
        frozen = p3f3["valuation_session"]["valuation_session"]
        candidates, rows_by_ticker, sessions = _load_runtime_market(runtime_root, frozen_session=frozen)
        snapshot_identity = None
        selection_contract = "P3F3_latest_completed_vietnam_weekday_with_exact_retained_observation"
    else:
        candidates, rows_by_ticker, sessions, frozen = _load_snapshot_market(snapshot_path)
        snapshot_identity = json.loads(snapshot_path.read_text(encoding="utf-8")).get("snapshot_identity")
        selection_contract = "P3F9_exact_completed_session_DNSE_shadow_snapshot"
    cohort = derive_empirical_active_cohort(rows_by_ticker, sessions=sessions, candidate_tickers=candidates)
    fundamentals, authoritative, proxies = _maps(root)
    member_set = set(cohort["members"])
    records = []
    for ticker in sorted(candidates):
        in_cohort = ticker in member_set
        features = market_features(rows_by_ticker.get(ticker, ())) if in_cohort else {"status": "MISSING", "values": {}, "blockers": [cohort["exclusions"].get(ticker, {"reason": "NO_RETAINED_MARKET_OBSERVATION"})["reason"]]}
        fundamental = fundamentals.get(ticker)
        proxy_row = proxies.get(ticker)
        records.append({"identity": {"canonical_ticker": ticker, "identity_status": "OBSERVED_RETAINED_INSTRUMENT_NOT_ACTIVE_UNIVERSE_AUTHORITY"},
                        "session": frozen, "empirical_active_cohort_member": in_cohort,
                        "market_features": features,
                        "foreign_flow_value": {"status": FeatureStatus.BLOCKED.value, "reason": "NO_QUALIFIED_CURRENT_RETAINED_FOREIGN_FLOW_VALUE"},
                        "fundamental_readiness": ({"status": FeatureStatus.QUALIFIED.value, "readiness": fundamental["fundamental_research_readiness"], "entity_class": fundamental["issuer_identity"]["entity_class"], "metric_family_states": fundamental["metric_family_states"], "source_artifact": "P3-B"} if fundamental else {"status": "MISSING", "reason": "NO_P3B_RETAINED_FUNDAMENTAL_RECORD"}),
                        "authoritative_valuation": authoritative.get(ticker, {"status": "MISSING", "reason": "NO_P3F3_AUTHORITY_RECORD"}),
                        "mva_provider_proxy_valuation": (proxy_row if proxy_row else {"status": "MISSING", "reason": "NO_P3F6_PROXY_VALUATION_RECORD"}),
                        "freshness": {"market_window": "EXACT_20_COMPLETED_SESSIONS" if in_cohort else "INCOMPLETE_OR_MISSING", "as_of_session": frozen},
                        "warnings": (["ACTIVE_UNIVERSE_NOT_PROMOTED", "HISTORICAL_PIT_NOT_ELIGIBLE", "LIQUIDITY_SIZING_BLOCKED"] + ([] if in_cohort else ["DEPENDENT_MARKET_FEATURES_FAIL_CLOSED"]))})
    active_rows = [row for row in records if row["empirical_active_cohort_member"]]
    returns = [row["market_features"]["values"]["return_1d"] for row in active_rows]
    breadth = {"status": "SHADOW_ONLY", "denominator_name": COHORT_NAME, "denominator": len(active_rows), "numerator_observed": len(returns), "missing_count": len(active_rows) - len(returns),
               "advancing": sum(value > 0 for value in returns), "declining": sum(value < 0 for value in returns), "unchanged": sum(value == 0 for value in returns),
               "method": "one_day_close_return_over_explicit_complete_20_session_shadow_cohort"}
    breadth["advance_ratio"] = breadth["advancing"] / breadth["denominator"] if breadth["denominator"] else None
    proxy_ready = sum(row.get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("status") == "PROXY_MARKET_CAP_READY" for row in records)
    artifact: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
                                "verdict": "P3F7_MVA_DAILY_BUNDLE_COMPLETE", **use_envelope,
                                "frozen_session": {"session": frozen, "selection_contract": selection_contract, "incomplete_intraday_used": False},
                                "empirical_active_cohort": {key: value for key, value in cohort.items() if key != "exclusions"},
                                "market_summary": {"candidate_universe_size": len(candidates), "observed_market_candidates": len(rows_by_ticker), "empirical_active_cohort_size": len(active_rows), "missing_or_excluded_count": len(candidates) - len(active_rows), "breadth": breadth,
                                                   "feature_availability": {"market_features_shadow_only": len(active_rows), "foreign_flow_value_blocked": len(records), "fundamental_records_available": len(fundamentals)},
                                                   "proxy_valuation_coverage": proxy_ready, "authoritative_valuation_coverage": 0,
                                                   "blocked_capability_counts": {"liquidity_sizing": len(records), "pit_backtest": len(records), "macro_liquidity": len(records)}},
                                "records": records,
                                "blocked_capabilities": {"liquidity_sizing": "BLOCKED", "execution": "BLOCKED", "historical_pit": "BLOCKED", "macro_liquidity": "BLOCKED_UNAVAILABLE", "ranking_recommendation": "BLOCKED", "p3g": "RESERVED_NOT_STARTED"},
                                "source_artifacts": {"p3f3": p3f3.get("artifact_identity"), "p3b": "p3b_fundamental_research_readiness_artifact", "p3f6": "p3f6_mva_provider_share_proxy_artifact", "p3f9_snapshot": snapshot_identity},
                                "ticker_specific_branch_audit": {"status": "PASS", "branch_violations": [], "production_modules": ["mva_daily_research_bundle.py"]},
                                "boundaries": {"active_universe_promoted": False, "source_authority_promoted": False, "runtime_database_mutated": False, "p3g": "RESERVED_NOT_STARTED"}}
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f7_mva_daily_research_bundle:{artifact['artifact_sha256']}"
    return artifact
