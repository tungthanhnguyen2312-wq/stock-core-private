"""Raw-first qualification for KBS's distinct public profile share field.

KBS's ``outstanding_shares`` is deliberately not assumed to mean common
shares outstanding.  This adapter retains exact responses and records a
field-level failure-closed disposition before any valuation consumer can see
it.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

from field_temporal_contract import stable_id

CONTRACT_VERSION = "authoritative_current_common_shares_qualification/v1"
SOURCE = "KBS_PUBLIC_COMPANY_PROFILE"
ENDPOINT = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/profile/{ticker}?l=1"


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _date(value: Any) -> str | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except (ValueError, TypeError):
        return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool): return None
    try: number = float(value)
    except (TypeError, ValueError): return None
    return int(number) if number > 0 and number.is_integer() else None


def _record(payload: Any) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping) and "outstanding_shares" in payload: return payload
    if isinstance(payload, Mapping):
        for key in ("data", "record", "result"):
            item = payload.get(key)
            if isinstance(item, Mapping) and "outstanding_shares" in item: return item
            if isinstance(item, list) and len(item) == 1 and isinstance(item[0], Mapping) and "outstanding_shares" in item[0]: return item[0]
    return None


def retain_response(ticker: str, *, status: int | None, body: bytes, retrieved_at: str, output_root: Path, error: str | None = None) -> dict[str, Any]:
    sha = hashlib.sha256(body).hexdigest()
    raw_dir = output_root / "raw" / SOURCE
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{ticker.upper()}-{sha}.json"
    if raw_path.exists() and raw_path.read_bytes() != body: raise ValueError("RAW_CONTENT_HASH_CONFLICT")
    raw_path.write_bytes(body)
    parsed: Any = None
    parse_error = None
    try: parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: parse_error = type(exc).__name__
    return {"ticker": ticker.upper(), "source": SOURCE, "endpoint": ENDPOINT.format(ticker=ticker.upper()), "http_status": status, "retrieved_at": retrieved_at, "raw_sha256": sha, "raw_path": str(raw_path), "raw_bytes": len(body), "raw_payload": parsed, "parse_error": parse_error, "transport_error": error}


def fetch_and_retain(ticker: str, output_root: Path, *, get=requests.get, retrieved_at: str | None = None) -> dict[str, Any]:
    now = retrieved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        response = get(ENDPOINT.format(ticker=ticker.upper()), timeout=(5, 15))
        return retain_response(ticker, status=int(response.status_code), body=bytes(response.content), retrieved_at=now, output_root=output_root)
    except requests.RequestException as exc:
        return retain_response(ticker, status=None, body=b"", retrieved_at=now, output_root=output_root, error=type(exc).__name__)


def classify_observation(raw: Mapping[str, Any], *, target_session: str, action_tickers: set[str]) -> dict[str, Any]:
    ticker = str(raw["ticker"]).upper()
    if raw.get("http_status") != 200 or raw.get("parse_error") or raw.get("transport_error"):
        return {"ticker": ticker, "disposition": "UNAVAILABLE", "reason": "SOURCE_RESPONSE_UNAVAILABLE_OR_MALFORMED", "identity": None, "value": None}
    record = _record(raw.get("raw_payload"))
    value = _integer(record.get("outstanding_shares")) if record else None
    source_as_of = _date(record.get("as_of_date")) if record else None
    base = {"ticker": ticker, "source": SOURCE, "identity": "provider_reported_outstanding_shares", "value": value, "source_as_of": source_as_of, "raw_sha256": raw["raw_sha256"], "semantic_contract": "KBS field label is retained verbatim; no retained provider schema/document defines common-share scope, treasury treatment, or an effective interval."}
    if value is None:
        return {**base, "disposition": "UNAVAILABLE", "reason": "OUTSTANDING_SHARES_FIELD_MISSING_OR_INVALID"}
    if source_as_of is None:
        return {**base, "disposition": "CONTINUITY_UNPROVEN", "reason": "SOURCE_AS_OF_DATE_MISSING"}
    if source_as_of > target_session:
        return {**base, "disposition": "CONTINUITY_UNPROVEN", "reason": "SOURCE_AS_OF_AFTER_TARGET_SESSION"}
    if ticker in action_tickers:
        return {**base, "disposition": "STALE", "reason": "RETAINED_SHARE_CHANGING_CORPORATE_ACTION_REQUIRES_CONTINUITY_PROOF"}
    return {**base, "disposition": "CONTINUITY_UNPROVEN", "reason": "PROVIDER_SEMANTICS_AND_EFFECTIVE_INTERVAL_NOT_DOCUMENTED"}


def build_artifact(*, universe: Sequence[str], raw_rows: Sequence[Mapping[str, Any]], target_session: str, action_tickers: set[str]) -> dict[str, Any]:
    observed = {str(row["ticker"]).upper(): classify_observation(row, target_session=target_session, action_tickers=action_tickers) for row in raw_rows}
    rows = {ticker: observed.get(ticker, {"ticker": ticker, "disposition": "NOT_ATTEMPTED_FOR_JUSTIFIED_SCOPE", "reason": "PILOT_SEMANTICS_DID_NOT_QUALIFY_FOR_BULK_SCALEOUT", "identity": None, "value": None}) for ticker in sorted(set(universe))}
    counts = Counter(row["disposition"] for row in rows.values())
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "target_session": target_session, "source": {"name": SOURCE, "endpoint_template": ENDPOINT, "new_vs_proxy": "KBS.outstanding_shares is retained separately from VCI.issue_share; values are never aliased or reconciled as equal identities."}, "raw_evidence": [{key: row.get(key) for key in ("ticker", "endpoint", "http_status", "retrieved_at", "raw_sha256", "raw_path", "raw_bytes", "parse_error", "transport_error")} for row in raw_rows], "share_schema": {"identities_preserved": ["issued_shares", "listed_shares", "treasury_shares", "common_shares_outstanding", "weighted_average_basic_shares", "diluted_shares", "provider_reported_outstanding_shares"], "forbidden_aliases": ["provider_reported_outstanding_shares_to_common_shares_outstanding", "issued_minus_treasury_without_explicit_source_contract"]}, "records": rows, "coverage": {"universe_count": len(rows), "source_requestable": len(rows), "raw_acquired": len(raw_rows), "semantically_qualified": 0, "current_continuity_qualified": 0, "stale": counts["STALE"], "conflicting": counts["CONFLICTING"], "unavailable": counts["UNAVAILABLE"], "dispositions": dict(sorted(counts.items()))}, "cross_source_reconciliation": {"status": "SEMANTICALLY_NOT_COMPARABLE", "reason": "KBS provider-reported outstanding_shares and VCI issued_shares retain different undocumented provider semantics; no averaging or selection performed."}, "fitness_for_use": {"CURRENT_MARKET_CAP": "BLOCKED", "CURRENT_PB": "BLOCKED", "CURRENT_PS": "BLOCKED", "CURRENT_EV": "BLOCKED", "CURRENT_PE_CURRENT_SHARE_APPROXIMATION": "BLOCKED"}, "valuation_unlock": {"strict_share_ready_before": 0, "strict_share_ready_after": 0, "strict_market_cap_ready_before": 0, "strict_market_cap_ready_after": 0, "peer_valuation_unlock": False, "value_strategy_unlock": False}, "authority_boundary": {"common_shares_outstanding_promoted": False, "provider_proxy_preserved": True, "raw_as_traded": "NOT_PROMOTED", "pit": "NOT_PROMOTED", "is_actionable": False}, "verdict": "NO_NEW_SCALABLE_AUTHORITY"}
    artifact["artifact_sha256"] = stable_id(artifact); artifact["artifact_identity"] = "authoritative_current_common_shares_qualification:" + artifact["artifact_sha256"]
    return artifact
