"""Local, research-only reconstruction of historical tactical-classifier inputs.

This module deliberately has a narrow role.  It freezes only the SQLite OHLCV rows actually
selected for an historical completed-session window, reuses the existing technical-feature,
screening, and tactical-classifier implementations, and makes the temporal/basis limitations
part of the output.  It never opens a provider connection, changes the classifier, treats a
mutable database as immutable, or turns a later observation into PIT authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import current_market_screening_opportunity_comparison_foundation as screening_module
import market_wide_current_descriptive_research as descriptive_module
import market_wide_current_fundamental_research as fundamental_module
from market_regime_breadth_context import _descriptor
from mva_daily_research_bundle import LOOKBACK_SESSIONS, market_features
import tactical_reversal_retrospective_validation as retained_replay
import watchlist_tactical_entry_classifier as classifier


CONTRACT_VERSION = "historical_tactical_replay_evidence_foundation/v1"
MILESTONE = "HISTORICAL_TACTICAL_REPLAY_EVIDENCE_FOUNDATION_V1"

RETROSPECTIVE_RESEARCH_RECONSTRUCTION = "RETROSPECTIVE_RESEARCH_RECONSTRUCTION"
PIT_QUALIFIED_RECONSTRUCTION = "PIT_QUALIFIED_RECONSTRUCTION"
NOT_RECONSTRUCTABLE = "NOT_RECONSTRUCTABLE"
RECONSTRUCTION_QUALIFICATIONS = frozenset({
    RETROSPECTIVE_RESEARCH_RECONSTRUCTION,
    PIT_QUALIFIED_RECONSTRUCTION,
    NOT_RECONSTRUCTABLE,
})

RESEARCH_TICKERS = ("SSI", "PNJ")
PAN_CONTROL_TICKER = "PAN"
HISTORICAL_START = "2026-07-20"
HISTORICAL_END = "2026-08-10"
PAN_CONTROL_SESSIONS = ("2026-09-09", "2026-09-10")
DNSE_SOURCE = "DNSE"
SQLITE_PATH_CONTRACT = "<runtime-root>/vn_stock.db"
PRICE_BASIS = "ADJUSTED_RETROSPECTIVE"
RESEARCH_PRICE_SERIES_IDENTITY = "LOCAL_DNSE_ADJUSTED_RETROSPECTIVE_SELECTED_SERIES"


class HistoricalTacticalReplayEvidenceError(ValueError):
    """A local evidence or temporal contract was not met."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity(prefix: str, value: Any) -> str:
    return f"{prefix}:{_digest(value)}"


def _without_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}


def _freeze_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "frozen_content_identity"}


def _with_descriptive_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.update(descriptive_module.content_identity(result))
    return result


def _with_fundamental_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.update(fundamental_module.content_identity(result))
    return result


def _sqlite_connection(runtime_root: Path) -> sqlite3.Connection:
    database = Path(runtime_root) / "vn_stock.db"
    if not database.is_file():
        raise HistoricalTacticalReplayEvidenceError("RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _rows_digest(rows: Sequence[Mapping[str, Any]], lineages: Sequence[Mapping[str, Any]]) -> str:
    return _identity("sqlite_selected_rows", {"rows": list(rows), "lineages": list(lineages)})


def _session_window(connection: sqlite3.Connection, target_session: str) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT date FROM ohlcv WHERE date <= ? ORDER BY date DESC LIMIT ?",
        (target_session, LOOKBACK_SESSIONS),
    ).fetchall()
    sessions = list(reversed([str(row[0]) for row in rows]))
    if len(sessions) != LOOKBACK_SESSIONS or not sessions or sessions[-1] != target_session:
        raise HistoricalTacticalReplayEvidenceError(
            f"COMPLETE_20_SESSION_WINDOW_UNAVAILABLE:{target_session}"
        )
    return sessions


def _query_rows(
    connection: sqlite3.Connection, *, target_session: str, sessions: Sequence[str], source: str,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Select one provider-scoped, T0 cross-section and exactly its lookback rows.

    The target-session source filter is an intentional compatibility guard: neither close nor
    provider-relative volume is allowed to span DNSE and VCI merely to improve coverage.
    """
    candidate_rows = connection.execute(
        "SELECT ticker FROM ohlcv WHERE date = ? AND source = ? ORDER BY ticker",
        (target_session, source),
    ).fetchall()
    candidates = [str(row[0]).upper() for row in candidate_rows]
    if not candidates:
        raise HistoricalTacticalReplayEvidenceError(f"NO_PROVIDER_SCOPED_T0_COHORT:{target_session}:{source}")
    date_marks = ",".join("?" for _ in sessions)
    ticker_marks = ",".join("?" for _ in candidates)
    raw_rows = connection.execute(
        f"SELECT ticker, date, open, high, low, close, volume, source FROM ohlcv "
        f"WHERE date IN ({date_marks}) AND ticker IN ({ticker_marks}) AND source = ? "
        "ORDER BY ticker, date",
        (*sessions, *candidates, source),
    ).fetchall()
    rows = [
        {
            "ticker": str(ticker).upper(), "date": str(day), "open": opening,
            "high": high, "low": low, "close": close, "volume": volume,
            "source": str(row_source),
        }
        for ticker, day, opening, high, low, close, volume, row_source in raw_rows
    ]
    lineage_rows = connection.execute(
        f"SELECT ticker, trading_session_date, provider, provider_version, adapter_schema_version, "
        f"endpoint, canonical_field, retrieved_at, source_record_hash, unit_scale "
        f"FROM ohlcv_lineage WHERE trading_session_date IN ({date_marks}) "
        f"AND ticker IN ({ticker_marks}) AND provider = ? ORDER BY ticker, trading_session_date, canonical_field",
        (*sessions, *candidates, source),
    ).fetchall()
    lineages = [
        {
            "ticker": str(ticker).upper(), "trading_session_date": str(day), "provider": str(provider),
            "provider_version": str(version), "adapter_schema_version": str(adapter),
            "endpoint": str(endpoint), "canonical_field": str(field), "retrieved_at": str(retrieved_at),
            "source_record_hash": str(record_hash), "unit_scale": unit_scale,
        }
        for ticker, day, provider, version, adapter, endpoint, field, retrieved_at, record_hash, unit_scale in lineage_rows
    ]
    return candidates, rows, lineages


def freeze_sqlite_evidence(
    runtime_root: Path,
    *,
    target_sessions: Sequence[str] | None = None,
    source: str = DNSE_SOURCE,
) -> dict[str, Any]:
    """Read a mutable local DB once and retain only the rows this reconstruction consumes.

    The returned rows are a compact content-addressed freeze; neither a database copy nor a
    whole-database SHA is produced.  Consumers can rebuild every historical feature from this
    payload without reopening SQLite.
    """
    connection = _sqlite_connection(Path(runtime_root))
    try:
        if target_sessions is None:
            available = connection.execute(
                "SELECT DISTINCT date FROM ohlcv WHERE date BETWEEN ? AND ? ORDER BY date",
                (HISTORICAL_START, HISTORICAL_END),
            ).fetchall()
            target_sessions = [str(row[0]) for row in available]
        selections: dict[str, dict[str, Any]] = {}
        frozen_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        frozen_lineages: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for target_session in sorted(set(str(item) for item in target_sessions)):
            sessions = _session_window(connection, target_session)
            candidates, rows, lineages = _query_rows(
                connection, target_session=target_session, sessions=sessions, source=source,
            )
            selection_identity = _rows_digest(rows, lineages)
            selections[target_session] = {
                "target_session": target_session,
                "lookback_sessions": sessions,
                "provider": source,
                "candidate_tickers": candidates,
                "selected_row_count": len(rows),
                "selected_lineage_count": len(lineages),
                "selected_rows_identity": selection_identity,
                "observed_price_basis": PRICE_BASIS,
                "price_basis_fitness": "CURRENT_RETROSPECTIVE_RESEARCH_ONLY",
            }
            for row in rows:
                frozen_rows[(row["ticker"], row["date"], row["source"])] = row
            for lineage in lineages:
                frozen_lineages[(lineage["ticker"], lineage["trading_session_date"], lineage["provider"], lineage["canonical_field"])] = lineage
    finally:
        connection.close()

    rows = sorted(frozen_rows.values(), key=lambda row: (row["ticker"], row["date"], row["source"]))
    lineages = sorted(
        frozen_lineages.values(),
        key=lambda row: (row["ticker"], row["trading_session_date"], row["provider"], row["canonical_field"]),
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION + "/sqlite-freeze",
        "source_contract": {
            "kind": "LOCAL_MUTABLE_SQLITE_READ_ONLY_SELECTED_ROWS",
            "path": SQLITE_PATH_CONTRACT,
            "table": "ohlcv",
            "lineage_table": "ohlcv_lineage",
            "provider": source,
            "selection": "provider-scoped T0 row plus exact prior 20 completed DB sessions",
            "database_was_opened_read_only": True,
            "whole_database_retained": False,
            "whole_database_hash": None,
        },
        "selections": selections,
        "frozen_ohlcv_rows": rows,
        "frozen_lineage_rows": lineages,
    }
    payload["frozen_content_identity"] = _identity(
        "historical_tactical_replay_selected_evidence", _freeze_payload(payload),
    )
    return payload


def _index_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        ticker, day = row.get("ticker"), row.get("date")
        if isinstance(ticker, str) and isinstance(day, str):
            indexed[ticker.upper()][day] = row
    return indexed


def _source_knowledge(lineages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    timestamps = sorted({str(row.get("retrieved_at")) for row in lineages if row.get("retrieved_at")})
    return {
        "known_retrieval_timestamps": timestamps,
        "knowledge_available_at": timestamps[-1] if timestamps else None,
        "knowledge_available_at_target_session": False,
        "reason_codes": (
            ["LINEAGE_RETRIEVAL_AFTER_TARGET_OR_UNRESOLVED"]
            if timestamps else ["LINEAGE_RETRIEVAL_TIMESTAMP_UNAVAILABLE"]
        ),
    }


def _technical_from_rows(
    rows_by_day: Mapping[str, Mapping[str, Any]], *, sessions: Sequence[str], target_session: str,
    selection_identity: str, source: str,
) -> dict[str, Any]:
    missing = [day for day in sessions if day not in rows_by_day]
    if missing:
        return {
            "status": "MISSING", "blockers": ["COMPLETE_20_SESSION_WINDOW_REQUIRED"],
            "missing_sessions": missing, "values": {}, "feature_as_of_session": None,
            "is_current_session": False,
            "technical_history_provenance": {
                "source": "LOCAL_MUTABLE_SQLITE_SELECTED_ROWS_FROZEN", "provider": source,
                "selected_rows_identity": selection_identity,
            },
        }
    history = [rows_by_day[day] for day in sessions]
    result = market_features([
        {"date": row["date"], "close": row["close"], "volume": row["volume"]}
        for row in history
    ])
    return {
        **result,
        "feature_as_of_session": target_session,
        "is_current_session": result.get("status") == "SHADOW_ONLY",
        "technical_history_provenance": {
            "source": "LOCAL_MUTABLE_SQLITE_SELECTED_ROWS_FROZEN", "provider": source,
            "selected_rows_identity": selection_identity,
            "observed_price_basis": PRICE_BASIS,
            "knowledge_available_at_target_session": False,
        },
    }


def _sector_context() -> dict[str, Any]:
    """Return the explicit absence rather than borrowing the August metadata for July."""
    return {
        "status": "NOT_RECONSTRUCTABLE",
        "reason_codes": [
            "LOCAL_SECTOR_METADATA_EFFECTIVE_DATE_UNAVAILABLE",
            "LATER_METADATA_NOT_BORROWED_FOR_HISTORICAL_T0",
        ],
        "consumed": False,
    }


def _fundamental_source(session: str) -> dict[str, Any]:
    """A deliberately empty, identified source: absent T0 evidence is not neutral evidence."""
    return _with_fundamental_identity({
        "schema_version": "1.0.0",
        "contract_version": "market_wide_current_fundamental_research/v1",
        "session": session,
        "records": {},
        "reconstruction_fitness": {
            "status": "NOT_RECONSTRUCTABLE",
            "reason_codes": [
                "NO_LOCAL_FUNDAMENTAL_RECORD_WITH_KNOWLEDGE_AVAILABLE_AT_T0",
                "LATER_FUNDAMENTAL_OR_CORPORATE_EVENT_NOT_BORROWED",
            ],
        },
    })


def _descriptive_source(
    *, selection: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], lineages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    target_session = str(selection["target_session"])
    sessions = list(selection["lookback_sessions"])
    source = str(selection["provider"])
    selection_identity = str(selection["selected_rows_identity"])
    candidates = list(selection["candidate_tickers"])
    indexed = _index_rows(rows)
    records: dict[str, dict[str, Any]] = {}
    sector_context = _sector_context()
    for ticker in candidates:
        technical = _technical_from_rows(
            indexed.get(ticker, {}), sessions=sessions, target_session=target_session,
            selection_identity=selection_identity, source=source,
        )
        values = technical.get("values") or {}
        close, ma20 = values.get("close"), values.get("ma_20")
        trend = None
        if isinstance(close, (int, float)) and isinstance(ma20, (int, float)):
            trend = "ABOVE_MA20" if close > ma20 else "AT_OR_BELOW_MA20"
        records[ticker] = {
            "ticker": ticker,
            "activity_and_session_state": "RETAINED_PROVIDER_SCOPED_T0_OBSERVED",
            "membership_state": "RETAINED_PROVIDER_SCOPED_OBSERVATION_NOT_ACTIVE_UNIVERSE_AUTHORITY",
            "in_current_descriptive_scope": True,
            "technical_features": technical,
            "trend_state": trend,
            "liquidity": {
                "status": "UNAVAILABLE",
                "reason": "NO_SAME_SESSION_BOARD_COMPOSITION_RETAINED_FOR_HISTORICAL_RECONSTRUCTION",
            },
            "sector_classification": dict(sector_context),
        }

    technical_records = [
        record for record in records.values()
        if record["technical_features"].get("status") == "SHADOW_ONLY"
        and record["technical_features"].get("is_current_session") is True
    ]
    values = [record["technical_features"]["values"] for record in technical_records]
    returns = [item["return_1d"] for item in values if isinstance(item.get("return_1d"), (int, float))]
    momenta = [item["momentum_20d"] for item in values if isinstance(item.get("momentum_20d"), (int, float))]
    volatilities = [item["volatility_20d"] for item in values if isinstance(item.get("volatility_20d"), (int, float))]
    advancing = sum(value > 0 for value in returns)
    declining = sum(value < 0 for value in returns)
    above = sum(record.get("trend_state") == "ABOVE_MA20" for record in technical_records)
    denominator = len(records)
    breadth = {
        "current_active_equity_denominator": denominator,
        "observed_session_cohort": denominator,
        "same_session_technical_feature_available_count": len(technical_records),
        "coverage_ratio_of_denominator": len(technical_records) / denominator if denominator else 0.0,
        "coverage_ratio_of_observed_session_cohort": len(technical_records) / denominator if denominator else 0.0,
        "stale_feature_available_but_not_current_session_count": 0,
        "session": target_session,
        "quality_state": "PARTIAL_COVERAGE_EXPLICIT",
        "advancing": advancing,
        "declining": declining,
        "unchanged": len(technical_records) - advancing - declining,
        "advance_ratio": advancing / len(technical_records) if technical_records else None,
        "trend": {
            "above_ma20": above,
            "at_or_below_ma20": len(technical_records) - above,
            "unavailable": denominator - len(technical_records),
        },
        "breadth_descriptor": _descriptor(advancing, declining, len(technical_records), prefix="MARKET_BREADTH"),
        "momentum_descriptor": _descriptor(
            sum(value > 0 for value in momenta), sum(value < 0 for value in momenta), len(momenta),
            prefix="MOMENTUM_BREADTH",
        ),
        "volatility": {
            "available_count": len(volatilities),
            "median": median(volatilities) if volatilities else None,
            "authority_tier": "RETROSPECTIVE_RESEARCH_ONLY",
            "warning": "T0_CROSS_SECTION_FROM_FROZEN_LOCAL_ROWS_NOT_HISTORICAL_REGIME_AUTHORITY",
        },
        "provider_relative_volume": {
            "available_count": sum(
                isinstance(item.get("relative_volume_provider_scoped"), (int, float)) for item in values
            ),
            "authority_tier": "DERIVED_PROXY",
            "warning": "SINGLE_PROVIDER_DNSE_SCOPED_NOT_LIQUIDITY_OR_TURNOVER_AUTHORITY",
        },
        "authority_boundary": {
            "not_authoritative_market_universe": True,
            "not_bull_bear_call_forecast_or_timing": True,
            "no_ranking_or_recommendation": True,
            "historical_pit": "NOT_PROMOTED",
        },
    }
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": "market_wide_current_descriptive_research/v1",
        "session": target_session,
        "input_lineage": {
            "historical_reconstruction_contract": CONTRACT_VERSION,
            "selected_rows_identity": selection_identity,
            "source_provider": source,
            "session": target_session,
            "lineage_retrieval": _source_knowledge(lineages),
        },
        "market_breadth": breadth,
        "sector_breadth": {
            "method": "NOT_COMPUTED; later-sector-metadata is not borrowed for T0",
            "sector_count_total": 0,
            "sector_count_available": 0,
            "sector_count_insufficient_coverage": 0,
            "sectors": {},
            "reconstruction_fitness": sector_context,
        },
        "cross_sectional_features": {
            "feature_set": ["close", "return_1d", "ma_3", "ma_5", "ma_20", "momentum_20d", "volatility_20d", "relative_volume_provider_scoped"],
            "method": "mva_daily_research_bundle.market_features (reused unmodified)",
            "current_active_equity_denominator": denominator,
            "same_session_available_count": len(technical_records),
            "same_session_coverage_ratio": len(technical_records) / denominator if denominator else 0.0,
        },
        "liquidity_features": {
            "eligible_count": 0,
            "authority_boundary": "HISTORICAL_BOARD_COMPOSITION_NOT_RECONSTRUCTED",
        },
        "validation": {
            "coverage": {
                "input_candidates": denominator,
                "current_active_equity_denominator": denominator,
                "observed_session_cohort": denominator,
                "same_session_technical_feature_available_count": len(technical_records),
                "technical_feature_unavailable_count": denominator - len(technical_records),
            },
            "lineage": {
                "historical_reconstruction_contract": CONTRACT_VERSION,
                "selected_rows_identity": selection_identity,
                "session": target_session,
            },
            "session": target_session,
        },
        "authority_boundary": {
            "historical_pit_raw_as_traded": "NOT_PROMOTED",
            "sector_context": "NOT_RECONSTRUCTABLE_NOT_DEFAULTED",
            "fundamental_context": "NOT_RECONSTRUCTABLE_NOT_DEFAULTED",
            "liquidity_execution_sizing": "NOT_RECONSTRUCTED_AND_BLOCKED",
        },
        "records": records,
    }
    return _with_descriptive_identity(payload)


def _selection_rows(
    freeze: Mapping[str, Any], selection: Mapping[str, Any], *, kind: str,
) -> list[Mapping[str, Any]]:
    sessions = set(selection["lookback_sessions"])
    candidates = set(selection["candidate_tickers"])
    provider = selection["provider"]
    source_rows = freeze["frozen_ohlcv_rows"] if kind == "ohlcv" else freeze["frozen_lineage_rows"]
    date_field = "date" if kind == "ohlcv" else "trading_session_date"
    provider_field = "source" if kind == "ohlcv" else "provider"
    return [
        row for row in source_rows
        if row.get(date_field) in sessions and row.get("ticker") in candidates and row.get(provider_field) == provider
    ]


def _qualification(*, row: Mapping[str, Any] | None, knowledge: Mapping[str, Any]) -> tuple[str, list[str]]:
    if row is None or row.get("entry_state") is None:
        return NOT_RECONSTRUCTABLE, ["REQUIRED_TECHNICAL_OR_CLASSIFIER_OUTPUT_UNAVAILABLE"]
    if knowledge.get("knowledge_available_at_target_session") is True and row.get("historical_pit_eligible") is True:
        return PIT_QUALIFIED_RECONSTRUCTION, []
    return RETROSPECTIVE_RESEARCH_RECONSTRUCTION, [
        "CURRENT_RETROSPECTIVE_ADJUSTED_PRICE_BASIS",
        "LOCAL_LINEAGE_KNOWLEDGE_NOT_PROVEN_AVAILABLE_AT_T0",
        "PIT_AUTHORITY_UNCHANGED",
    ]


def _r6_record(record: Mapping[str, Any]) -> dict[str, Any]:
    signals = record.get("signals") or {}
    momentum = signals.get("momentum_20d")
    confirmations = []
    if signals.get("momentum_bucket") in {"UPPER_QUARTILE", "UPPER_MIDDLE"}:
        confirmations.append("MARKET_RELATIVE_MOMENTUM_UPPER_HALF")
    if signals.get("sector_momentum_bucket") in {"UPPER_QUARTILE", "UPPER_MIDDLE"}:
        confirmations.append("SECTOR_RELATIVE_MOMENTUM_UPPER_HALF")
    if signals.get("return_1d", 0) > 0 and signals.get("elevated_volume_vs_cohort_median") is True:
        confirmations.append("POSITIVE_RETURN_AND_ELEVATED_PROVIDER_RELATIVE_VOLUME")
    if not isinstance(momentum, (int, float)) or momentum <= 0:
        disposition = "R6_NOT_REACHED_MOMENTUM_NONPOSITIVE"
    elif record.get("rule_id") == "R6_EARLY_REVERSAL_CANDIDATE":
        disposition = "R6_CONFIRMED_BY_EXISTING_CLASSIFIER"
    elif record.get("rule_id") == "R6B_EARLY_REVERSAL_UNCONFIRMED_NEUTRAL":
        disposition = "R6_POSITIVE_MOMENTUM_BUT_INDEPENDENT_CONFIRMATION_ABSENT"
    else:
        disposition = "R6_NOT_REACHED_BY_EXISTING_ORDERED_CLASSIFIER"
    return {
        "rule_id_from_existing_classifier": record.get("rule_id"),
        "momentum_20d": momentum,
        "momentum_sign": "POSITIVE" if isinstance(momentum, (int, float)) and momentum > 0 else "NONPOSITIVE_OR_UNAVAILABLE",
        "independent_confirmation_evidence": confirmations,
        "disposition": disposition,
        "policy_changed": False,
    }


def same_basis_research_return(*, start: Mapping[str, Any], end: Mapping[str, Any]) -> dict[str, Any]:
    """Return a research-only result only for one declared retrospective series.

    This is deliberately narrower than a raw/PIT return.  A matching source label alone is not
    enough: the caller must preserve the explicit internal-series identity on both observations.
    """
    start_basis = start.get("price_basis") or {}
    end_basis = end.get("price_basis") or {}
    if start_basis.get("observed") != end_basis.get("observed"):
        return {"status": "NOT_COMPUTED", "reason_codes": ["PRICE_BASIS_MISMATCH"], "return_pct": None}
    if start_basis.get("research_series_identity") != end_basis.get("research_series_identity"):
        return {"status": "NOT_COMPUTED", "reason_codes": ["PRICE_SERIES_IDENTITY_MISMATCH"], "return_pct": None}
    start_price = (start.get("signals") or {}).get("close")
    end_price = (end.get("signals") or {}).get("close")
    if not isinstance(start_price, (int, float)) or not isinstance(end_price, (int, float)) or start_price == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["COMPARABLE_CLOSE_UNAVAILABLE"], "return_pct": None}
    return {
        "status": "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY",
        "reason_codes": ["PIT_NOT_QUALIFIED"],
        "return_pct": (end_price - start_price) / start_price,
    }


def _representative_row(record: Mapping[str, Any], qualification: str, reason_codes: Sequence[str]) -> dict[str, Any]:
    result = {
        "reconstruction_qualification": qualification,
        "reconstruction_reason_codes": list(reason_codes),
        "ticker": record.get("ticker"),
        "entry_state": record.get("entry_state"),
        "entry_action": record.get("entry_action"),
        "action": record.get("action"),
        "rule_id": record.get("rule_id"),
        "signals": record.get("signals"),
        "r6_check": _r6_record(record),
        "price_basis": {
            "observed": PRICE_BASIS,
            "research_series_identity": RESEARCH_PRICE_SERIES_IDENTITY,
            "same_series_research_only": True,
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
        },
    }
    return result


def _historical_replays(freeze: Mapping[str, Any]) -> dict[str, Any]:
    sessions: dict[str, Any] = {}
    for target_session, selection in sorted((freeze.get("selections") or {}).items()):
        rows = _selection_rows(freeze, selection, kind="ohlcv")
        lineages = _selection_rows(freeze, selection, kind="lineage")
        descriptive = _descriptive_source(selection=selection, rows=rows, lineages=lineages)
        screening = screening_module.build_artifact(descriptive)
        fundamental = _fundamental_source(target_session)
        result = classifier.build_artifact(
            descriptive_source=descriptive,
            screening_source=screening,
            fundamental_source=fundamental,
            requested_at=f"HISTORICAL_RECONSTRUCTION:{target_session}",
        )
        knowledge = _source_knowledge(lineages)
        representatives: dict[str, Any] = {}
        for ticker in RESEARCH_TICKERS:
            row = result["records"].get(ticker)
            qualification, reasons = _qualification(row=row, knowledge=knowledge)
            representatives[ticker] = (
                _representative_row(row, qualification, reasons)
                if row is not None else {
                    "ticker": ticker,
                    "reconstruction_qualification": qualification,
                    "reconstruction_reason_codes": reasons,
                    "entry_state": None,
                    "entry_action": "WAIT",
                    "rule_id": "R0_TECHNICAL_FEATURES_UNAVAILABLE",
                }
            )
        sessions[target_session] = {
            "session": target_session,
            "method": "existing_mva_market_features_then_existing_screening_then_watchlist_tactical_entry_classifier.build_artifact",
            "selected_rows_identity": selection["selected_rows_identity"],
            "source_knowledge": knowledge,
            "source_artifacts": {
                "descriptive": descriptive["artifact_identity"],
                "screening": screening["artifact_identity"],
                "fundamental": fundamental["artifact_identity"],
                "classifier": result["artifact_identity"],
            },
            "coverage": result["coverage"],
            "sector_context": _sector_context(),
            "fundamental_context": fundamental["reconstruction_fitness"],
            "representative_records": representatives,
        }
    return sessions


def _same_series_timing(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    chronological = sorted(rows, key=lambda row: str(row.get("session")))
    prices = [
        (str(row.get("session")), row.get("signals", {}).get("close"))
        for row in chronological
        if isinstance((row.get("signals") or {}).get("close"), (int, float))
    ]
    if not prices:
        return {"status": "NOT_COMPUTED", "reason_codes": ["COMPARABLE_SAME_SERIES_CLOSE_UNAVAILABLE"]}
    low_session, low_price = min(prices, key=lambda item: (item[1], item[0]))
    first_easing = next((row for row in chronological if row.get("entry_state") == "SELLING_PRESSURE_EASING"), None)
    first_early = next((row for row in chronological if row.get("entry_action") == "EARLY_ENTRY"), None)
    first_confirmation = next((row for row in chronological if row.get("entry_action") == "BUY_ON_CONFIRMATION"), None)
    first_signal = first_early or first_confirmation
    result: dict[str, Any] = {
        "status": "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY",
        "price_basis": PRICE_BASIS,
        "pit_qualified": False,
        "reference_low": {"session": low_session, "close": low_price},
        "first_selling_pressure_easing": _brief_state(first_easing),
        "first_early_action": _brief_state(first_early),
        "first_confirmation": _brief_state(first_confirmation),
        "false_start": {"status": "NO_EARLY_OR_CONFIRMATION_SIGNAL", "lower_low_after_signal": None},
        "mae_mfe_from_first_signal": None,
    }
    if first_signal is None:
        return result
    signal_session = str(first_signal.get("session"))
    signal_price = (first_signal.get("signals") or {}).get("close")
    after = [(session, price) for session, price in prices if session >= signal_session]
    if not isinstance(signal_price, (int, float)) or signal_price == 0 or not after:
        result["false_start"] = {"status": "NOT_COMPUTED", "lower_low_after_signal": None}
        return result
    lower = [(session, price) for session, price in after[1:] if price < signal_price]
    lowest_session, lowest_price = min(after, key=lambda item: (item[1], item[0]))
    highest_session, highest_price = max(after, key=lambda item: (item[1], item[0]))
    result["signal_distance_from_reference_low_pct"] = (signal_price - low_price) / low_price if low_price else None
    reference_row = next((row for row in chronological if str(row.get("session")) == low_session), None)
    result["return_from_reference_low_to_signal"] = (
        same_basis_research_return(start=reference_row, end=first_signal)
        if isinstance(reference_row, Mapping) else None
    )
    result["session_lag_from_reference_low"] = next(
        (index for index, row in enumerate(chronological) if str(row.get("session")) == signal_session), None,
    ) - next((index for index, row in enumerate(chronological) if str(row.get("session")) == low_session), 0)
    result["false_start"] = {
        "status": "LOWER_LOW_AFTER_SIGNAL" if lower else "NO_LOWER_LOW_AFTER_SIGNAL",
        "lower_low_after_signal": bool(lower),
        "signal_session": signal_session,
        "first_lower_low_session": lower[0][0] if lower else None,
    }
    result["mae_mfe_from_first_signal"] = {
        "signal_session": signal_session,
        "mae_pct": (lowest_price - signal_price) / signal_price,
        "mae_session": lowest_session,
        "mfe_pct": (highest_price - signal_price) / signal_price,
        "mfe_session": highest_session,
    }
    return result


def _brief_state(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "session": row.get("session"), "entry_state": row.get("entry_state"),
        "entry_action": row.get("entry_action"), "rule_id": row.get("rule_id"),
    }


def _timing_by_ticker(historical_sessions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for ticker in RESEARCH_TICKERS:
        rows = []
        for session, replay in sorted(historical_sessions.items()):
            record = (replay.get("representative_records") or {}).get(ticker)
            if isinstance(record, Mapping):
                rows.append({"session": session, **record})
        results[ticker] = _same_series_timing(rows)
    return results


def _pan_control_replay(retained_evidence_root: Path) -> dict[str, Any]:
    """Use only the exact retained September sources to explain the requested PAN control."""
    import daily_research_session_operations as session_operations

    registry = session_operations.load_registry(retained_evidence_root)
    controls: dict[str, Any] = {}
    for session in PAN_CONTROL_SESSIONS:
        inputs, selection = session_operations.resolve_inputs(retained_evidence_root, session, registry)
        replay = retained_replay.replay_registered_session(
            session=session, inputs=inputs, selection=selection, tickers=(PAN_CONTROL_TICKER,),
        )
        row = replay["records"][PAN_CONTROL_TICKER]
        controls[session] = {
            "reconstruction_qualification": RETROSPECTIVE_RESEARCH_RECONSTRUCTION,
            "reconstruction_reason_codes": [
                "EXACT_RETAINED_CONTROL_SNAPSHOT", "POINT_IN_TIME_PRICE_BASIS_UNQUALIFIED",
            ],
            "method": "existing_watchlist_tactical_entry_classifier.build_artifact via retained exact-session replay",
            "record": _representative_row(row, RETROSPECTIVE_RESEARCH_RECONSTRUCTION, [
                "EXACT_RETAINED_CONTROL_SNAPSHOT", "POINT_IN_TIME_PRICE_BASIS_UNQUALIFIED",
            ]),
            "source_artifacts": {
                name: {"artifact_identity": details.get("artifact_identity"), "relative_path": details.get("path")}
                for name, details in selection.items()
                if name in {"descriptive", "screening", "fundamental", "tactical"}
            },
        }
    prior, current = controls[PAN_CONTROL_SESSIONS[0]]["record"], controls[PAN_CONTROL_SESSIONS[1]]["record"]
    return {
        "records": controls,
        "transition": {
            "from_session": PAN_CONTROL_SESSIONS[0], "from_state": prior.get("entry_state"),
            "from_action": prior.get("entry_action"), "from_rule_id": prior.get("rule_id"),
            "to_session": PAN_CONTROL_SESSIONS[1], "to_state": current.get("entry_state"),
            "to_action": current.get("entry_action"), "to_rule_id": current.get("rule_id"),
            "explanation": "Existing classifier output changed; the foundation does not alter its rule ordering or thresholds.",
        },
    }


def build_artifact(
    *, freeze: Mapping[str, Any], retained_evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Compose the immutable research artifact from an already frozen selected-row payload."""
    if freeze.get("contract_version") != CONTRACT_VERSION + "/sqlite-freeze":
        raise HistoricalTacticalReplayEvidenceError("SQLITE_FREEZE_CONTRACT_UNSUPPORTED")
    expected = _identity("historical_tactical_replay_selected_evidence", _freeze_payload(freeze))
    if freeze.get("frozen_content_identity") != expected:
        raise HistoricalTacticalReplayEvidenceError("FROZEN_SELECTED_ROW_IDENTITY_MISMATCH")
    historical = _historical_replays(freeze)
    qualifications = Counter(
        record.get("reconstruction_qualification")
        for replay in historical.values()
        for record in (replay.get("representative_records") or {}).values()
    )
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "reconstruction_qualifications": sorted(RECONSTRUCTION_QUALIFICATIONS),
        "source_inventory": {
            "sqlite_ohlcv": freeze["source_contract"],
            "frozen_selected_evidence_identity": freeze["frozen_content_identity"],
            "frozen_ohlcv_row_count": len(freeze.get("frozen_ohlcv_rows") or []),
            "frozen_lineage_row_count": len(freeze.get("frozen_lineage_rows") or []),
            "sector": _sector_context(),
            "fundamental_and_corporate_event": {
                "status": "NOT_RECONSTRUCTABLE",
                "reason_codes": ["NO_LOCAL_T0_KNOWLEDGE_QUALIFIED_FUNDAMENTAL_OR_EVENT_SOURCE_CONSUMED"],
                "later_evidence_rejected": True,
            },
        },
        "frozen_selected_evidence": dict(freeze),
        "historical_reconstructions": historical,
        "historical_timing": _timing_by_ticker(historical),
        "coverage": {
            "historical_sessions": len(historical),
            "representative_tickers": list(RESEARCH_TICKERS),
            "representative_qualification_counts": dict(sorted(qualifications.items())),
        },
        "authority_boundary": {
            "classifier_policy_changed": False,
            "daily_modified": False,
            "integrated_decision_modified": False,
            "portfolio_modified": False,
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
            "price_basis_authority": "UNCHANGED",
            "provider_or_network_calls": False,
            "database_written": False,
            "probability_or_recommendation": "NOT_EMITTED",
        },
    }
    if retained_evidence_root is None:
        artifact["pan_control"] = {
            "status": NOT_RECONSTRUCTABLE,
            "reason_codes": ["RETAINED_EVIDENCE_ROOT_NOT_SUPPLIED_FOR_EXACT_PAN_CONTROL_REPLAY"],
        }
    else:
        artifact["pan_control"] = _pan_control_replay(Path(retained_evidence_root))
    artifact["artifact_sha256"] = _digest(artifact)
    artifact["artifact_identity"] = "historical_tactical_replay_evidence_foundation:" + artifact["artifact_sha256"]
    return artifact


def build_from_runtime(
    *, runtime_root: Path, retained_evidence_root: Path | None = None,
    target_sessions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Read local SQLite once, freeze selected rows, then build the reconstruction artifact."""
    freeze = freeze_sqlite_evidence(runtime_root, target_sessions=target_sessions)
    return build_artifact(freeze=freeze, retained_evidence_root=retained_evidence_root)
