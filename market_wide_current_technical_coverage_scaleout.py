"""Bounded recovery of missing technical-history windows from DNSE OHLC evidence."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id
from mva_daily_research_bundle import market_features
from mva_exact_session_snapshot import _observation_rows


CONTRACT_VERSION = "market_wide_current_technical_coverage_scaleout/v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_technical_coverage_scaleout:{digest}"}


def _verify_p3f9b_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    if snapshot.get("snapshot_sha256") != stable_id(payload):
        raise ValueError("P3F9B_SNAPSHOT_IDENTITY_MISMATCH")


def recovery_candidates(*, baseline_artifact: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any]) -> list[str]:
    """Return only current-session records missing the existing 20-observation feature window."""
    baseline_identity = content_identity(baseline_artifact)
    if baseline_artifact.get("artifact_sha256") != baseline_identity["artifact_sha256"]:
        raise ValueError("BASELINE_RESEARCH_ARTIFACT_IDENTITY_MISMATCH")
    _verify_p3f9b_identity(p3f9b_snapshot)
    records = baseline_artifact.get("records")
    snapshot_records = p3f9b_snapshot.get("records")
    target = p3f9b_snapshot.get("resolved_completed_session")
    if not isinstance(records, Mapping) or not isinstance(snapshot_records, Mapping) or not target:
        raise ValueError("RECOVERY_INPUT_INVALID")
    if set(records) != set(snapshot_records):
        raise ValueError("RECOVERY_CANDIDATE_DENOMINATOR_MISMATCH")
    candidates = []
    for ticker in sorted(records):
        technical = records[ticker].get("technical_features", {})
        source = snapshot_records[ticker]
        has_target = any(row.get("session") == target for row in source.get("observations", []) if isinstance(row, Mapping))
        if (records[ticker].get("in_current_descriptive_scope")
                and technical.get("status") == "MISSING"
                and source.get("disposition") == "EXACT_SESSION_RETAINED"
                and has_target):
            candidates.append(ticker)
    return candidates


def recovery_record(*, ticker: str, response: Mapping[str, Any], target_session: str,
                    query: Mapping[str, Any], retrieved_at: str) -> dict[str, Any]:
    """Preserve a single unmodified provider response while classifying technical usability."""
    if not response.get("ok"):
        return {
            "ticker": ticker, "state": "FETCH_FAILED", "reason": response.get("error_code", "FETCH_FAILED"),
            "query": dict(query), "provider": response.get("provider"), "endpoint": response.get("endpoint"),
        }
    body = response.get("body")
    if not isinstance(body, Mapping):
        return {
            "ticker": ticker, "state": "MALFORMED_RESPONSE", "reason": "BODY_NOT_OBJECT", "query": dict(query),
            "provider": response.get("provider"), "endpoint": response.get("endpoint"),
        }
    observations, target_problem = _observation_rows(
        body, requested_session=target_session, query=query, retrieved_at=retrieved_at,
    )
    if target_problem is not None:
        state = "TARGET_SESSION_NOT_RECOVERED" if target_problem == "EXACT_SESSION_MISSING" else "MALFORMED_RESPONSE"
        return {
            "ticker": ticker, "state": state, "reason": target_problem, "query": dict(query),
            "provider": response.get("provider"), "endpoint": response.get("endpoint"),
            "payload_sha256": hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest(),
            "observations": observations,
        }
    features = market_features([{"date": row["session"], "close": row["close"], "volume": row["volume"]} for row in observations])
    state = "RECOVERED_COMPLETE_TECHNICAL_HISTORY" if features.get("status") == "SHADOW_ONLY" else "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK"
    return {
        "ticker": ticker, "state": state, "reason": None if state.startswith("RECOVERED") else "COMPLETE_20_SESSION_WINDOW_REQUIRED",
        "query": dict(query), "provider": response.get("provider"), "endpoint": response.get("endpoint"),
        "payload_sha256": hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest(),
        "observations": observations,
    }


def build_recovery_artifact(*, baseline_artifact: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any],
                            batch_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = recovery_candidates(baseline_artifact=baseline_artifact, p3f9b_snapshot=p3f9b_snapshot)
    target = p3f9b_snapshot["resolved_completed_session"]
    flattened: dict[str, Mapping[str, Any]] = {}
    for batch in batch_records:
        for record in batch.get("records", []):
            ticker = record.get("ticker") if isinstance(record, Mapping) else None
            if ticker in flattened:
                raise ValueError(f"DUPLICATE_RECOVERY_RECORD:{ticker}")
            if ticker:
                flattened[str(ticker)] = record
    if set(flattened) != set(candidates):
        raise ValueError(f"INCOMPLETE_RECOVERY_BATCHES:{len(flattened)}/{len(candidates)}")

    recovered = {
        ticker: dict(record)
        for ticker, record in sorted(flattened.items())
        if record.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    }
    states = Counter(str(record.get("state")) for record in flattened.values())
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "target_session": target,
        "source_lineage": {
            "baseline_research_artifact_identity": baseline_artifact.get("artifact_identity"),
            "p3f9b_snapshot_identity": p3f9b_snapshot.get("snapshot_identity"),
        },
        "candidate_selection": {
            "count": len(candidates),
            "reason": "CURRENT_SESSION_OBSERVED_TECHNICAL_FEATURE_MISSING_COMPLETE_20_SESSION_WINDOW_REQUIRED",
            "tickers": candidates,
        },
        "acquisition_results": {state: states[state] for state in sorted(states)},
        "recovered_history_overrides": recovered,
        "records": {ticker: dict(record) for ticker, record in sorted(flattened.items())},
        "authority_boundary": {
            "provider_scoped_technical_history": "CURRENT_DESCRIPTIVE_SHADOW_ONLY",
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "PIT": "BLOCKED",
            "ranking_recommendation_sizing_execution": "NOT_EMITTED",
        },
    }
    return {**artifact, **content_identity(artifact)}
