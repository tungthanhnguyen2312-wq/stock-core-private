"""Market-wide Phase 2 canonical, quality, semantic, and PIT foundation.

This module intentionally does not fetch, delete, or rewrite raw data.  It transforms a
retained raw OHLC corpus into lineage-bearing canonical rows and a separate exception queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from market_data_contracts import ExceptionDisposition, FeatureStatus, PriceBasis, stable_id
from provider_price_basis_registry import active_bounded_authorities, bounded_price_basis_for


QUALITY_RULE_VERSION = "1.0.0"
SEMANTIC_REGISTRY_VERSION = "1.0.0"
VOLUME_BASIS_UNKNOWN = "UNKNOWN"
PIT_HISTORICAL_ONLY = FeatureStatus.HISTORICAL_ONLY.value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def semantic_registry() -> list[dict[str, Any]]:
    """Return repository-authoritative board entries plus explicit unknown contracts."""
    authority = "docs/market_wide_ingest_first_architecture.md"
    entries = []
    for code, meaning in {"G1": "ROUND_LOT", "G4": "ODD_LOT", "T1": "PUT_THROUGH_ROUND_LOT",
                          "T3": "PUT_THROUGH_ROUND_LOT", "T4": "PUT_THROUGH_ODD_LOT",
                          "T6": "PUT_THROUGH_ODD_LOT"}.items():
        entries.append({"semantic_key": f"DNSE.board.{code}", "provider": "DNSE", "raw_field": "boardId",
                        "raw_code": code, "normalized_meaning": meaning, "status": "DOCUMENTED",
                        "evidence_reference": authority, "effective_from": None, "effective_to": None,
                        "version": SEMANTIC_REGISTRY_VERSION})
    entries.extend([
        {"semantic_key": "DNSE.volume_basis", "provider": "DNSE", "raw_field": "volume", "raw_code": None,
         "normalized_meaning": None, "status": "UNKNOWN", "evidence_reference": authority,
         "effective_from": None, "effective_to": None, "version": SEMANTIC_REGISTRY_VERSION,
         "reason": "No market-wide unit/aggregation evidence; no multiplier is applied."},
        {"semantic_key": "DNSE.price_basis.bulk_ohlc", "provider": "DNSE", "raw_field": "ohlc", "raw_code": None,
         "normalized_meaning": PriceBasis.UNKNOWN.value, "status": "UNQUALIFIED", "evidence_reference": authority,
         "effective_from": None, "effective_to": None, "version": SEMANTIC_REGISTRY_VERSION,
         "reason": "HPG/VCB evidence is bounded and is not generalized to the bulk corpus."},
    ])
    for authority_record in active_bounded_authorities():
        entries.append({
            "semantic_key": f"DNSE.price_basis.{authority_record['authority_id'].replace(':', '_')}",
            "provider": authority_record["provider"], "raw_field": "ohlc", "raw_code": None,
            "normalized_meaning": authority_record["price_basis"], "status": "EVIDENCED_BOUNDED",
            "evidence_reference": "dnse_ohlc_price_basis_capability.py",
            "effective_from": authority_record["effective_from"], "effective_to": authority_record["effective_to"],
            "version": SEMANTIC_REGISTRY_VERSION,
            "reason": "Instrument/date/event-scoped DNSE authority; no provider-wide generalization.",
        })
    return entries


def price_basis_for(provider: str, dataset: str, instrument: str, session: str) -> tuple[str, str]:
    """Return a known basis only when the exact bounded authority covers this row."""
    resolved = bounded_price_basis_for(provider, dataset, instrument, session)
    return str(resolved["price_basis"]), str(resolved["reason"])


def canonical_instrument_identity(provider: str, symbol: str, universe: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic provider-scoped identity without normalizing exchange guesses."""
    raw_group = universe.get("raw_security_group_id") or universe.get("securityGroupId")
    instrument_class = universe.get("instrument_class", "UNKNOWN_SECURITY_GROUP")
    exchange_raw = universe.get("exchange_raw") or universe.get("marketId")
    return {"provider_symbol": symbol, "provider_instrument_identity": f"{provider}:{symbol}",
            "canonical_instrument_id": f"{provider}:{symbol}", "exchange_raw": exchange_raw,
            "canonical_exchange": "UNKNOWN", "canonical_exchange_status": "UNQUALIFIED",
            "canonical_exchange_reason": "exchange_raw_mapping_not_authoritatively_documented",
            "security_group_id": raw_group, "instrument_class": instrument_class,
            "identity_status": FeatureStatus.CANONICAL.value if instrument_class == "EQUITY" else FeatureStatus.UNKNOWN.value,
            "effective_from": universe.get("listed_date") or universe.get("listedDate")}


def expand_raw_ohlc(raw_rows: Iterable[Mapping[str, Any]], universe_by_symbol: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Expand retained DNSE OHLC payload arrays; malformed payloads become quality rows, never drops."""
    records: list[dict[str, Any]] = []
    for raw in raw_rows:
        payload = json.loads(raw["raw_payload_json"])
        symbol = str(raw["instrument"])
        arrays = {key: payload.get(key) for key in ("t", "o", "h", "l", "c", "v")}
        lengths = {len(v) for v in arrays.values() if isinstance(v, list)}
        identity = canonical_instrument_identity(raw["provider"], symbol, universe_by_symbol.get(symbol, {}))
        if len(lengths) != 1 or len(lengths) == 0 or next(iter(lengths)) == 0:
            records.append({"provider": raw["provider"], "dataset": raw["dataset"], "provider_symbol": symbol,
                            **identity,
                            "raw_observation_id": raw["observation_id"], "raw_payload_hash": raw["raw_payload_hash"],
                            "raw_file": raw.get("raw_file"), "retrieved_at": raw["retrieved_at"],
                            "request_identity": raw["request_identity"], "schema_version": raw["schema_version"],
                            "session": pd.NaT, "open": np.nan, "high": np.nan, "low": np.nan, "close": np.nan,
                            "volume": np.nan, "price_basis_status": PriceBasis.UNKNOWN.value,
                            "price_basis_reason": "bulk_scope_not_covered_by_bounded_price_basis_evidence",
                            "semantic_status": FeatureStatus.UNKNOWN.value, "semantic_reason": "volume_board_aggregation_unknown",
                            "volume_basis_status": VOLUME_BASIS_UNKNOWN, "pit_status": PIT_HISTORICAL_ONLY,
                            "pit_reason": "historical_raw_availability_not_proven", "source_event_time": None,
                            "bar_index": None, "ingest_schema_error": "empty_ohlc_payload" if lengths == {0} else "payload_arrays_missing_or_length_mismatch"})
            continue
        for index in range(next(iter(lengths))):
            event_time = pd.to_datetime(arrays["t"][index], unit="s", utc=True, errors="coerce") if arrays["t"][index] is not None else pd.NaT
            session = event_time.date() if not pd.isna(event_time) else pd.NaT
            basis, basis_reason = price_basis_for(raw["provider"], raw["dataset"], symbol, str(session))
            records.append({**identity, "provider": raw["provider"], "dataset": raw["dataset"], "session": session,
                            "open": arrays["o"][index], "high": arrays["h"][index], "low": arrays["l"][index],
                            "close": arrays["c"][index], "volume": arrays["v"][index], "raw_observation_id": raw["observation_id"],
                            "raw_payload_hash": raw["raw_payload_hash"], "raw_file": raw.get("raw_file"),
                            "request_identity": raw["request_identity"], "retrieved_at": raw["retrieved_at"],
                            "schema_version": raw["schema_version"], "bar_index": index, "price_basis_status": basis,
                            "price_basis_reason": basis_reason, "semantic_status": FeatureStatus.UNKNOWN.value,
                            "semantic_reason": "volume_board_aggregation_unknown", "volume_basis_status": VOLUME_BASIS_UNKNOWN,
                            "pit_status": PIT_HISTORICAL_ONLY, "pit_reason": "historical_raw_availability_not_proven",
                            "source_event_time": None if pd.isna(event_time) else event_time.isoformat(), "ingest_schema_error": None})
    return pd.DataFrame(records)


def _issue(row: Mapping[str, Any], rule_id: str, severity: str, observed: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    identity = {"raw_observation_id": row.get("raw_observation_id"), "session": str(row.get("session")), "rule_id": rule_id,
                "observed": observed}
    return {"exception_id": stable_id(identity), "provider": row.get("provider", "DNSE"), "dataset": row.get("dataset", "ohlc"),
            "instrument": row.get("provider_symbol"), "observation_id": row.get("raw_observation_id"),
            "session": None if pd.isna(row.get("session")) else str(row.get("session")), "exception_type": "DATA_QUALITY",
            "quality_rule": rule_id, "rule_version": QUALITY_RULE_VERSION, "severity": severity,
            "observed_value": _json(observed), "context": _json(context), "source_lineage": _json({
                "raw_file": row.get("raw_file"), "raw_payload_hash": row.get("raw_payload_hash"), "request_identity": row.get("request_identity")}),
            "detected_at": "DERIVED_FROM_RETAINED_INPUT", "disposition": ExceptionDisposition.UNRESOLVED.value,
            "disposition_reason": "automated finding requires review", "resolved_at": None, "resolution_evidence": None}


def evaluate_quality(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vectorized daily-OHLC quality results and unresolved exceptions, without raw mutation."""
    result = frame.copy()
    if result.empty:
        return result.assign(quality_status=pd.Series(dtype=str), quality_flags=pd.Series(dtype=str)), pd.DataFrame()
    numeric = ["open", "high", "low", "close", "volume"]
    for col in numeric:
        result[col] = pd.to_numeric(result[col], errors="coerce")
    flags: dict[int, list[tuple[str, str, Any, dict[str, Any]]]] = {i: [] for i in result.index}
    def add(mask: pd.Series, rule: str, severity: str, observed_col: str | None = None, context: dict[str, Any] | None = None) -> None:
        for idx in result.index[mask.fillna(False)]:
            flags[idx].append((rule, severity, result.at[idx, observed_col] if observed_col else None, context or {}))
    add(result["ingest_schema_error"].notna(), "malformed_payload_schema", "high", "ingest_schema_error")
    add(result["session"].isna(), "invalid_session_timestamp", "high")
    add(result[["open", "high", "low", "close"]].isna().any(axis=1), "missing_required_ohlc_field", "high")
    add(~np.isfinite(result[numeric]).all(axis=1), "invalid_numeric_value", "high")
    add((result[["open", "high", "low", "close"]] <= 0).any(axis=1), "non_positive_price", "high")
    add(result["volume"] < 0, "negative_volume", "high", "volume")
    add((result["low"] > result[["open", "close"]].min(axis=1)) | (result["high"] < result[["open", "close"]].max(axis=1)), "impossible_ohlc_relation", "high")
    logical = ["canonical_instrument_id", "session", "price_basis_status"]
    add(result.duplicated(logical, keep=False), "duplicate_logical_observation", "medium")
    add(result.duplicated(["provider_instrument_identity", "session"], keep=False), "duplicate_provider_identity", "medium")
    ordered = result.sort_values(["canonical_instrument_id", "session", "raw_observation_id"], kind="stable").copy()
    previous = ordered.groupby("canonical_instrument_id", sort=False)["close"].shift()
    ratios = ordered["close"] / previous
    log_returns = np.log(ratios.where((ratios > 0) & np.isfinite(ratios)))
    median = log_returns.groupby(ordered["canonical_instrument_id"], sort=False).transform(lambda x: x.rolling(10, min_periods=5).median())
    mad = (log_returns - median).abs().groupby(ordered["canonical_instrument_id"], sort=False).transform(lambda x: x.rolling(10, min_periods=5).median())
    ordered["_return"] = ratios - 1
    ordered["_mad"] = ((log_returns - median).abs() > (8 * mad)).fillna(False) & (mad > 0)
    ordered["_extreme"] = (ratios >= 1.5) | (ratios <= (1 / 1.5))
    volume_ratio = ordered["volume"] / ordered.groupby("canonical_instrument_id", sort=False)["volume"].shift()
    ordered["_volume_extreme"] = (volume_ratio >= 10) | ((volume_ratio <= .1) & (volume_ratio > 0))
    ordered["_stale"] = ordered.groupby("canonical_instrument_id", sort=False)["close"].transform(lambda x: x.rolling(5, min_periods=5).apply(lambda w: float(w.nunique() == 1), raw=False).eq(1))
    for _, row in ordered[ordered["_extreme"] | ordered["_mad"] | ordered["_volume_extreme"] | ordered["_stale"]].iterrows():
        idx = row.name
        if row["_extreme"]: flags[idx].append(("extreme_log_return", "medium", row["close"], {"return": row["_return"]}))
        if row["_mad"]: flags[idx].append(("rolling_mad_return_outlier", "medium", row["close"], {"method": "rolling_median_mad"}))
        if row["_volume_extreme"]: flags[idx].append(("extreme_log_volume_change", "medium", row["volume"], {"method": "prior_session_ratio"}))
        if row["_stale"]: flags[idx].append(("stale_or_frozen_series", "low", row["close"], {"window_sessions": 5}))
        if row["_extreme"]: flags[idx].append(("potential_corporate_action_discontinuity", "medium", row["close"], {"reason": "review_required_not_auto_classified"}))
    exceptions = [_issue(result.loc[idx], rule, severity, observed, context) for idx, items in flags.items() for rule, severity, observed, context in items]
    result["quality_flags"] = [json.dumps([item[0] for item in flags[i]], separators=(",", ":")) for i in result.index]
    result["quality_status"] = [FeatureStatus.SUSPECT.value if flags[i] else FeatureStatus.CANONICAL.value for i in result.index]
    result["missing_session_check_status"] = "NOT_EVALUATED_NO_SESSION_CALENDAR_AUTHORITY"
    return result, pd.DataFrame(exceptions)


def phase1_provider_exceptions(failed_symbols: Iterable[str], universe_by_symbol: Mapping[str, Mapping[str, Any]], request_scope: str) -> pd.DataFrame:
    rows = []
    for symbol in sorted(set(failed_symbols)):
        universe = universe_by_symbol.get(symbol, {})
        identity = canonical_instrument_identity("DNSE", symbol, universe)
        key = {"provider": "DNSE", "dataset": "ohlc", "symbol": symbol, "scope": request_scope, "http_status": 400}
        rows.append({"exception_id": stable_id(key), "provider": "DNSE", "dataset": "ohlc", "instrument": symbol,
                     "observation_id": None, "session": None, "exception_type": "PROVIDER_INGESTION_FAILURE",
                     "quality_rule": "http_status_400", "rule_version": QUALITY_RULE_VERSION, "severity": "high",
                     "observed_value": "400", "context": _json({"request_scope": request_scope, "exchange_raw": identity["exchange_raw"]}),
                     "source_lineage": _json({"coverage_request_scope": request_scope}), "detected_at": "RETAINED_PHASE1_EVIDENCE",
                     "disposition": ExceptionDisposition.UNRESOLVED.value, "disposition_reason": "No retained provider response body or causal message.",
                     "resolved_at": None, "resolution_evidence": None})
    return pd.DataFrame(rows)


def volume_reconciliation_summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {"status": VOLUME_BASIS_UNKNOWN, "method_version": "1.0.0", "rows_examined": int(len(frame)),
            "reason": "OHLC payloads contain no board-level fields; no candidate multiplier or aggregation relation is promoted.",
            "candidate_transforms": []}


@dataclass(frozen=True)
class FinancialPitFact:
    feature_id: str; instrument: str; value: float | int | None; period_end: str; publish_date: str
    received_at: str; effective_from: str; revision_publish_date: str | None; source_document: str
    statement_scope: str; audit_status: str; revision_of: str | None = None

    @property
    def available_at(self) -> str:
        return max(self.publish_date, self.effective_from, self.revision_publish_date or "")


def financial_facts_visible_as_of(facts: Iterable[FinancialPitFact], as_of: str) -> list[FinancialPitFact]:
    """Choose only facts available by as-of, with later revisions replacing earlier states prospectively."""
    visible = [fact for fact in facts if fact.available_at <= as_of]
    latest: dict[tuple[str, str], FinancialPitFact] = {}
    for fact in sorted(visible, key=lambda f: (f.available_at, f.source_document)):
        latest[(fact.instrument, fact.feature_id)] = fact
    return [latest[key] for key in sorted(latest)]
