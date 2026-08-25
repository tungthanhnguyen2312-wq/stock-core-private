"""Historical daily matched-trading-value authority and ADTV20 contract.

This is a liquidity-input contract, not a sizing engine. It reuses the already
qualified G1 formula ``sum(G1.matchPrice * G1.matchQtty) * 10 * 1000`` VND and
never aliases total, odd-lot, or put-through value to matched value.

``ADTV20_MATCHED_VALUE`` is a trailing 20 *trading-session* average of qualified
matched value. It is not ``ADV``. ``ADV20_MATCHED_VOLUME`` is not emitted unless
matched volume is independently qualified, which this module does not claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from field_temporal_contract import stable_id
from historical_matched_traded_value_authority import (
    KNOWN_BOARDS,
    MATCHED_VALUE_FORMULA,
    QUALIFIED_BOARD,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers

CONTRACT_VERSION = "historical_matched_trading_value_authority/v1"
ARTIFACT_TYPE = "HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY"
FEATURE_ADTV20 = "ADTV20_MATCHED_VALUE"
FEATURE_ADV20_VOLUME = "ADV20_MATCHED_VOLUME"
EXPECTED_ADTV_SESSIONS = 20

EXACT_RECONCILED = "EXACT_RECONCILED"
COVERAGE_RESTRICTED_RECONCILED = "COVERAGE_RESTRICTED_RECONCILED"
INSUFFICIENT_DISCRIMINATION = "INSUFFICIENT_DISCRIMINATION"
CONFLICTING = "CONFLICTING"
UNAVAILABLE = "UNAVAILABLE"

MATCHED_VALUE_OBSERVATION_QUALIFIED = "MATCHED_VALUE_OBSERVATION_QUALIFIED_COVERAGE_RESTRICTED"
UNAVAILABLE_NO_VALUE_ANCHOR = "UNAVAILABLE_NO_INDEPENDENT_MATCHED_VALUE_ANCHOR"
UNAVAILABLE_MISSING_TRADES = "UNAVAILABLE_MISSING_FROM_RETAINED_TRADES_CORPUS"
TERMINAL_DISPOSITIONS = frozenset({
    MATCHED_VALUE_OBSERVATION_QUALIFIED, UNAVAILABLE_NO_VALUE_ANCHOR, UNAVAILABLE_MISSING_TRADES,
})

PUT_THROUGH_BOARDS = frozenset({"T1", "T3", "T4", "T6"})
ODD_LOT_BOARDS = frozenset({"G4", "T4", "T6"})
REGULAR_MATCHED_BOARD = "G1"

SOURCE_SEMANTICS = {
    "dnse_trades_history_g1": {
        "identity": "matched_trading_value_vnd",
        "proven_scope": "FPT/HPG/SSI/VCB x 2026-08-07/10/11 exact FHSC anchors",
        "formula": MATCHED_VALUE_FORMULA,
        "unit": "VND",
        "promotable_generic": False,
    },
    "dnse_trades_history_g4": {
        "identity": "odd_lot_matched_component",
        "proven_scope": "board label documented; value/quantity scale not qualified",
        "promotable_generic": False,
    },
    "dnse_trades_history_t_boards": {
        "identity": "put_through_component",
        "proven_scope": "T1/T3 round-lot put-through; T4/T6 odd-lot put-through; not in matched value",
        "promotable_generic": False,
    },
    "dnse_daily_ohlc_v": {
        "identity": "hose_empirical_matched_volume_shares_shadow",
        "proven_scope": "HOSE discriminating DNSE v = FHSC matched volume; not a value field",
        "promotable_generic": False,
    },
    "dnse_daily_ohlc_va": {
        "identity": None,
        "proven_scope": "OBSERVED_ABSENT from DNSE daily OHLC",
        "promotable_generic": False,
    },
    "grossTradeAmount": {
        "identity": "unresolved_board_dependent_cumulative_counter",
        "proven_scope": "not matched-value authority",
        "promotable_generic": False,
    },
}


def _quantity(value: Any) -> Decimal:
    if isinstance(value, bool):
        return Decimal("0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return result if result.is_finite() else Decimal("0")


def classify_session_discrimination(board_composition: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A session proves composition only when odd-lot and/or put-through quantity is nonzero."""
    odd_lot = Decimal("0")
    put_through = Decimal("0")
    regular = Decimal("0")
    observed = []
    for row in board_composition:
        board = str(row.get("board_id") or "")
        qty = _quantity(row.get("raw_quantity"))
        observed.append(board)
        if board == REGULAR_MATCHED_BOARD:
            regular += qty
        if board in ODD_LOT_BOARDS:
            odd_lot += qty
        if board in PUT_THROUGH_BOARDS:
            put_through += qty
    discriminating = odd_lot > 0 or put_through > 0
    return {
        "status": "DISCRIMINATING" if discriminating else "NON_DISCRIMINATING",
        "regular_matched_g1_raw_quantity": str(regular),
        "odd_lot_raw_quantity": str(odd_lot),
        "put_through_raw_quantity": str(put_through),
        "observed_boards": sorted(set(observed)),
        "missing_boards_not_imputed_zero": sorted(set(KNOWN_BOARDS) - set(observed)),
    }


def session_value_reconciliation(row: Mapping[str, Any]) -> str:
    fhsc = row.get("fhsc_reconciliation") or {}
    discrimination = classify_session_discrimination(row.get("board_composition") or [])
    if fhsc.get("status") == "CONFLICT":
        return CONFLICTING
    if row.get("qualification_status") != "MATCHED_VALUE_QUALIFIED" or fhsc.get("status") != "EXACT":
        return UNAVAILABLE
    if discrimination["status"] != "DISCRIMINATING":
        return INSUFFICIENT_DISCRIMINATION
    return EXACT_RECONCILED


def adtv20_matched_value(rows: Iterable[Mapping[str, Any]], *, expected_sessions: int = EXPECTED_ADTV_SESSIONS) -> dict[str, Any]:
    """Trailing 20 actual qualified trading sessions. Holidays are not missing observations."""
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("qualification_status") != "MATCHED_VALUE_QUALIFIED":
            continue
        if row.get("matched_value_vnd") is None:
            continue
        by_ticker[str(row["ticker"])].append(row)
    result: dict[str, Any] = {}
    for ticker, values in sorted(by_ticker.items()):
        ordered = sorted(values, key=lambda item: str(item.get("session") or ""))
        observed = len(ordered)
        coverage_ratio = observed / expected_sessions if expected_sessions else 0
        ready = observed >= expected_sessions
        window = ordered[-expected_sessions:] if ready else ordered
        average = None
        if ready:
            total = sum(_quantity(item["matched_value_vnd"]) for item in window)
            average = int(total / expected_sessions) if total == total.to_integral_value() else format(total / expected_sessions, "f")
        result[ticker] = {
            "feature_id": FEATURE_ADTV20,
            "status": "ADTV20_READY" if ready else "ADTV20_INSUFFICIENT_HISTORY",
            "expected_sessions": expected_sessions,
            "observed_sessions": observed,
            "coverage_ratio": coverage_ratio,
            "unit": "VND",
            "identity": "matched_trading_value_vnd",
            "adtv20_matched_value_vnd": average,
            "window_sessions": [item["session"] for item in window],
            "calendar_day_imputation": False,
            "participation_policy_embedded": False,
            "reason": None if ready else "NO_AVERAGE_EMITTED_UNTIL_20_EXPECTED_COMPLETE_QUALIFIED_TRADING_SESSIONS",
        }
    return result


def adv20_matched_volume_status() -> dict[str, Any]:
    """Volume is not derived from a passing value contract."""
    return {
        "feature_id": FEATURE_ADV20_VOLUME,
        "status": "NOT_EMITTED",
        "ready_count": 0,
        "reason": "MATCHED_TRADING_VOLUME_SHARES_NOT_INDEPENDENTLY_QUALIFIED_AS_GENERIC_FIELD",
    }


def build_historical_matched_trading_value_authority(
    *,
    official_universe: Mapping[str, Any],
    qualified_rows: Sequence[Mapping[str, Any]],
    trades_universe: Sequence[str],
    source_identities: Mapping[str, Any] | None = None,
    trades_source_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One terminal disposition per official-universe ticker; no sizing policy."""
    tickers = official_research_universe_tickers(official_universe)
    if not tickers:
        raise ValueError("OFFICIAL_RESEARCH_UNIVERSE_EMPTY")
    trades = {str(ticker).upper() for ticker in trades_universe}
    session_rows = []
    for row in qualified_rows:
        discrimination = classify_session_discrimination(row.get("board_composition") or [])
        status = session_value_reconciliation(row)
        session_rows.append({
            "ticker": row["ticker"], "session": row["session"],
            "matched_trading_value_vnd": row.get("matched_value_vnd"),
            "matched_trading_volume_shares": None,
            "g1_share_quantity": row.get("g1_share_quantity"),
            "value_reconciliation": status,
            "discrimination": discrimination,
            "board_composition": row.get("board_composition"),
            "qualification_status": row.get("qualification_status"),
            "fhsc_reconciliation": row.get("fhsc_reconciliation"),
        })
    if not session_rows:
        cohort_reconciliation = UNAVAILABLE
    elif any(item["value_reconciliation"] == CONFLICTING for item in session_rows):
        cohort_reconciliation = CONFLICTING
    elif all(item["value_reconciliation"] == EXACT_RECONCILED for item in session_rows):
        cohort_reconciliation = COVERAGE_RESTRICTED_RECONCILED
    else:
        cohort_reconciliation = UNAVAILABLE
    qualified_tickers = {item["ticker"] for item in session_rows if item["qualification_status"] == "MATCHED_VALUE_QUALIFIED"}
    records: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        ticker_sessions = [item for item in session_rows if item["ticker"] == ticker]
        if ticker_sessions:
            disposition = MATCHED_VALUE_OBSERVATION_QUALIFIED
            blockers = ["ADTV20_REQUIRES_20_QUALIFIED_COMPLETE_TRADING_SESSIONS"] if len(ticker_sessions) < EXPECTED_ADTV_SESSIONS else []
        elif ticker in trades:
            disposition = UNAVAILABLE_NO_VALUE_ANCHOR
            blockers = ["NO_INDEPENDENT_EXACT_MATCHED_VALUE_ANCHOR"]
        else:
            disposition = UNAVAILABLE_MISSING_TRADES
            blockers = ["MISSING_FROM_RETAINED_TRADES_CORPUS"]
        records[ticker] = {
            "ticker": ticker,
            "authority_tier": disposition,
            "matched_trading_value_vnd_sessions": ticker_sessions,
            "session_count": len(ticker_sessions),
            "blockers": blockers,
            "fitness_for_use": "MATCHED_VALUE_OBSERVATION_ONLY" if ticker_sessions else "NOT_ELIGIBLE",
            "adtv20_matched_value": None,
            "adv20_matched_volume": None,
            "position_sizing": "BLOCKED",
            "participation_policy": "NOT_EMBEDDED",
        }
    adtv = adtv20_matched_value(qualified_rows)
    for ticker, feature in adtv.items():
        if ticker in records:
            records[ticker]["adtv20_matched_value"] = feature
    ready = sum(1 for feature in adtv.values() if feature["status"] == "ADTV20_READY")
    recon_counts = Counter(item["value_reconciliation"] for item in session_rows)
    disc_counts = Counter(item["discrimination"]["status"] for item in session_rows)
    tiers = Counter(row["authority_tier"] for row in records.values())
    unexplained = abs(len(records) - len(tickers))
    if unexplained or any(row["authority_tier"] not in TERMINAL_DISPOSITIONS for row in records.values()):
        raise ValueError("MATCHED_VALUE_DISPOSITION_CONTRACT_BROKEN")
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "source_identities": dict(source_identities or {}),
        "source_semantics": SOURCE_SEMANTICS,
        "matched_value_contract": {
            "identity": "matched_trading_value_vnd",
            "formula": MATCHED_VALUE_FORMULA,
            "unit": "VND",
            "qualified_board": QUALIFIED_BOARD,
            "excluded_boards_preserved": ["G4", "T1", "T3", "T4", "T6"],
            "auction_versus_continuous": "NOT_SPLIT_NO_UNIVERSAL_SESSION_CLOCK",
            "gross_trade_amount": "NOT_USED",
            "ohlc_v_not_a_value_field": True,
            "formula_status": "QUALIFIED_EMPIRICAL_SCOPE" if session_rows else "NOT_QUALIFIED",
            "cohort_reconciliation": cohort_reconciliation,
        },
        "adtv20_contract": {
            "feature_id": FEATURE_ADTV20,
            "definition": "trailing 20 actual qualified trading sessions of matched_trading_value_vnd",
            "unit": "VND",
            "calendar_day_imputation": False,
            "coverage_tolerance_17_of_20": False,
            "expected_sessions": EXPECTED_ADTV_SESSIONS,
            "ready_count": ready,
        },
        "adv20_volume_contract": adv20_matched_volume_status(),
        "reconciliation": {
            "eligible_anchor_sessions": len(qualified_rows),
            "complete_qualified_sessions": len(session_rows),
            "discriminating_sessions": disc_counts.get("DISCRIMINATING", 0),
            "non_discriminating_sessions": disc_counts.get("NON_DISCRIMINATING", 0),
            "value_reconciliation_counts": dict(sorted(recon_counts.items())),
            "cohort_status": cohort_reconciliation,
        },
        "trades_source_contract": dict(trades_source_contract or {}),
        "records": records,
        "qualified_session_rows": session_rows,
        "coverage": {
            "universe_denominator": len(records),
            "trades_universe_denominator": len(trades),
            "denominator_reconciles": unexplained == 0 and sum(tiers.values()) == len(records),
            "unexplained_count": unexplained,
            "authority_tier_distribution": dict(sorted(tiers.items())),
            "adtv20_ready_count": ready,
            "adv20_matched_volume_ready_count": 0,
            "qualified_observation_tickers": len(qualified_tickers),
            "qualified_observation_sessions": len(session_rows),
        },
        "authority_boundary": {
            "qualified_liquidity_inputs": False,
            "position_sizing_is_safe": False,
            "participation_cap": "NOT_EMBEDDED",
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtesting": "BLOCKED",
            "current_common_shares": "UNCHANGED",
            "valuation_value_eligibility": "UNCHANGED",
            "frozen_sessions_not_regenerated": ["2026-08-21", "2026-08-24"],
            "current_session_liquidity_research": "SEPARATE_LANE",
        },
        "verdict": (
            "HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY_PASS" if ready else
            "MATCHED_TRADING_VALUE_AUTHORITY_CEILING_ESTABLISHED"
        ),
    }
    if not artifact["coverage"]["denominator_reconciles"]:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    artifact["artifact_sha256"] = stable_id({key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}})
    artifact["artifact_identity"] = f"historical_matched_trading_value_authority:{artifact['artifact_sha256']}"
    return artifact


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in dict(artifact).items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"historical_matched_trading_value_authority:{digest}"}
