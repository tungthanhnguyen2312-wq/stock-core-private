"""Deterministic same-session technical coverage dispositions over retained artifacts.

Reconciles the candidate universe, official research universe, and same-session
technical/tactical observations without regenerating the governed session.
Previous-session technicals never count as same-session coverage.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping

from current_official_market_universe import (
    OFFICIAL_CURRENT_EXCHANGE_SECURITY,
    OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE,
)


CONTRACT_VERSION = "same_session_technical_coverage_disposition/v1"
OFFICIAL_STATUSES = frozenset({OFFICIAL_CURRENT_EXCHANGE_SECURITY, OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE})
DISPOSITIONS = (
    "SAME_SESSION_TECHNICAL_COVERED",
    "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
    "OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE",
    "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING",
    "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION",
    "MALFORMED_OR_CONFLICTED",
    "PROVIDER_SESSION_UNAVAILABLE",
    "UNEXPLAINED",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": "same_session_technical_coverage_disposition:" + digest}


def official_research_universe(official_universe: Mapping[str, Any]) -> set[str]:
    tickers: set[str] = set()
    for ticker, record in (official_universe.get("records") or {}).items():
        if not isinstance(record, Mapping):
            continue
        if record.get("stocklookup_candidate") and record.get("current_universe_status") in OFFICIAL_STATUSES:
            tickers.add(str(ticker))
    return tickers


def _has_target_bar(source: Mapping[str, Any], target_session: str) -> bool:
    return any(
        isinstance(row, Mapping) and row.get("session") == target_session
        for row in source.get("observations") or []
    )


def _classify_one(
    *,
    ticker: str,
    descriptive: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    status: Mapping[str, Any],
    official: Mapping[str, Any] | None,
    target_session: str,
    official_tickers: set[str],
) -> dict[str, Any]:
    technical = descriptive.get("technical_features") or {}
    source_disp = snapshot.get("disposition")
    has_target = _has_target_bar(snapshot, target_session)
    same_session = technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is True
    in_official = ticker in official_tickers
    nearby = int((status or {}).get("nearby_observation_count_in_retained_window") or 0)
    qualification = (official or {}).get("qualification")
    conflicted = False
    if same_session and source_disp != "EXACT_SESSION_RETAINED":
        conflicted = True
    if same_session and not has_target:
        conflicted = True
    if source_disp == "EXACT_SESSION_RETAINED" and not has_target:
        conflicted = True
    if same_session and not in_official:
        conflicted = True

    if conflicted:
        disposition, reason = "MALFORMED_OR_CONFLICTED", "CONFLICTING_SAME_SESSION_AND_SOURCE_STATE"
    elif same_session:
        disposition, reason = "SAME_SESSION_TECHNICAL_COVERED", "EXACT_SESSION_BAR_AND_COMPLETE_TECHNICAL_WINDOW"
    elif source_disp == "PROVIDER_REJECTED":
        disposition, reason = "PROVIDER_REJECTED_OR_INVALID_SYMBOL", str(qualification or snapshot.get("reason") or "PROVIDER_REJECTED")
    elif not in_official:
        disposition, reason = "OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE", str(qualification or "STOCKLOOKUP_ONLY_UNRESOLVED")
    elif has_target and technical.get("status") == "MISSING":
        disposition, reason = "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION", "COMPLETE_20_SESSION_WINDOW_REQUIRED"
    elif has_target and not same_session:
        disposition, reason = "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING", str(technical.get("status") or "UNKNOWN")
    elif source_disp == "SESSION_MISSING" or descriptive.get("activity_and_session_state") == "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION":
        disposition = "PROVIDER_SESSION_UNAVAILABLE"
        if technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is False:
            reason = "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"
        elif nearby > 0:
            reason = "TARGET_SESSION_GAP_WITH_NEARBY_OBSERVED_ACTIVITY"
        else:
            reason = "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"
    else:
        disposition, reason = "UNEXPLAINED", "NO_MUTUALLY_EXCLUSIVE_RULE_MATCHED"

    return {
        "ticker": ticker,
        "disposition": disposition,
        "reason_code": reason,
        "in_official_research_universe": in_official,
        "snapshot_disposition": source_disp,
        "activity_and_session_state": descriptive.get("activity_and_session_state"),
        "technical_status": technical.get("status"),
        "is_current_session": technical.get("is_current_session"),
        "feature_as_of_session": technical.get("feature_as_of_session"),
        "has_exact_session_bar": has_target,
        "nearby_observation_count_in_retained_window": nearby,
        "official_qualification": qualification,
    }


def build(
    *,
    descriptive: Mapping[str, Any],
    official_universe: Mapping[str, Any],
    p3f9b_snapshot: Mapping[str, Any],
    universe_status: Mapping[str, Any],
    tactical: Mapping[str, Any] | None = None,
    recovery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = p3f9b_snapshot.get("resolved_completed_session") or descriptive.get("session")
    desc_records = descriptive.get("records") or {}
    snap_records = p3f9b_snapshot.get("records") or {}
    status_records = universe_status.get("records") or {}
    official_records = official_universe.get("records") or {}
    if not isinstance(desc_records, Mapping) or not isinstance(snap_records, Mapping):
        raise ValueError("COVERAGE_DISPOSITION_INPUT_INVALID")
    if set(desc_records) != set(snap_records):
        raise ValueError("CANDIDATE_DENOMINATOR_MISMATCH")
    if target != descriptive.get("session") or target != (universe_status.get("input_candidates") or {}).get("resolved_completed_session"):
        raise ValueError("COVERAGE_DISPOSITION_SESSION_MISMATCH")
    official_tickers = official_research_universe(official_universe)
    recovered = set((recovery or {}).get("recovered_history_overrides") or {}) if isinstance(recovery, Mapping) else set()

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(desc_records):
        row = _classify_one(
            ticker=ticker,
            descriptive=desc_records[ticker],
            snapshot=snap_records[ticker],
            status=status_records.get(ticker) or {},
            official=official_records.get(ticker) if isinstance(official_records.get(ticker), Mapping) else None,
            target_session=str(target),
            official_tickers=official_tickers,
        )
        row["recovered_extended_history"] = ticker in recovered
        records[ticker] = row

    counts = Counter(row["disposition"] for row in records.values())
    reasons = Counter(row["reason_code"] for row in records.values())
    official_rows = [row for row in records.values() if row["in_official_research_universe"]]
    official_counts = Counter(row["disposition"] for row in official_rows)
    covered = counts.get("SAME_SESSION_TECHNICAL_COVERED", 0)
    tactical_classified = (tactical or {}).get("coverage", {}).get("classified_count") if isinstance(tactical, Mapping) else None
    if tactical_classified is not None and tactical_classified != covered:
        raise ValueError("TACTICAL_CLASSIFIED_COUNT_MISMATCH")
    unexplained = counts.get("UNEXPLAINED", 0)
    if unexplained:
        raise ValueError("UNEXPLAINED_COVERAGE_DISPOSITION:" + str(unexplained))
    if sum(counts.values()) != len(records):
        raise ValueError("DISPOSITION_COUNT_DRIFT")

    official_only_tickers = sorted(
        str(ticker) for ticker, record in official_records.items()
        if isinstance(record, Mapping) and not record.get("stocklookup_candidate")
    )

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": target,
        "authority_boundary": {
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "PIT": "BLOCKED",
            "ranking_recommendation_sizing_execution": "NOT_EMITTED",
            "previous_session_technicals_are_not_same_session_coverage": True,
            "no_trade_session_not_inferred_from_missing_bar": True,
        },
        "source_artifact_identities": {
            "descriptive": descriptive.get("artifact_identity"),
            "official_universe": official_universe.get("artifact_identity"),
            "p3f9b_snapshot": p3f9b_snapshot.get("snapshot_identity") or p3f9b_snapshot.get("artifact_identity"),
            "universe_status": universe_status.get("artifact_identity"),
            "tactical": (tactical or {}).get("artifact_identity"),
            "technical_history_recovery": (recovery or {}).get("artifact_identity"),
        },
        "candidate_universe": {
            "count": len(records),
            "disposition_counts": {name: counts.get(name, 0) for name in DISPOSITIONS},
            "reason_counts": dict(sorted(reasons.items())),
        },
        "official_research_universe": {
            "count": len(official_tickers),
            "disposition_counts": {name: official_counts.get(name, 0) for name in DISPOSITIONS},
            "same_session_technical_covered": official_counts.get("SAME_SESSION_TECHNICAL_COVERED", 0),
            "missing_same_session_technical": len(official_tickers) - official_counts.get("SAME_SESSION_TECHNICAL_COVERED", 0),
        },
        "coverage_ceiling": {
            "same_session_technical_equals_exact_session_observed_after_history_recovery": True,
            "observed_exact_session_count": covered,
            "history_recovery_applied_count": len(recovered),
            "recoverable_raw_present_materialization_missing": counts.get("RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING", 0),
            "recoverable_pipeline_filter_residual": counts.get("PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION", 0),
            "structural_unavailable_or_outside_universe": (
                counts.get("PROVIDER_REJECTED_OR_INVALID_SYMBOL", 0)
                + counts.get("OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE", 0)
                + counts.get("PROVIDER_SESSION_UNAVAILABLE", 0)
            ),
            "unexplained": unexplained,
            "semantic_note": "Same-session technical coverage cannot exceed exact-session observed bars. Missing target-session bars are not fabricated as zero-trade sessions.",
        },
        "official_only_not_in_candidate_universe": {
            "count": len(official_only_tickers),
            "tickers": official_only_tickers,
        },
        "records": records,
    }
    return {**artifact, **content_identity(artifact)}
