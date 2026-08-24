"""Deterministic, fail-closed assessment of retained matched-value stores.

The output explains whether storage *semantics*, rather than mere record coverage,
permit a historical matched-traded-value expansion.  It never derives notional from
daily OHLCV and treats an unresolved raw counter as unavailable rather than value.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

VERSION = "1.0.0"
CONTRACT_VERSION = "historical_matched_value_existing_store_requalification/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _identity(value: Mapping[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


def inventory_record(*, dataset: str, file_count: int, columns: Iterable[str], source_kind: str,
                     semantic_note: str, bytes_count: int | None = None) -> dict[str, Any]:
    """Classify real schema fields without inferring a value from a filename or formula."""
    fields = {str(field) for field in columns}
    execution = {"price", "quantity", "board_id"}.issubset(fields) or {"matchPrice", "matchQtty", "boardId"}.issubset(fields)
    return {
        "dataset": dataset, "source_kind": source_kind, "file_count": int(file_count),
        "bytes": bytes_count, "columns": sorted(fields),
        "execution_tick_price_quantity": execution,
        "board_trade_type_identity": "board_id" in fields or "boardId" in fields,
        "explicit_matched_traded_value": "matched_traded_value" in fields,
        "explicit_put_through_traded_value": "put_through_traded_value" in fields,
        "explicit_total_traded_value": any(field in fields for field in {"traded_value", "total_traded_value", "value", "va"}),
        "only_ohlcv": {"open", "high", "low", "close", "volume"}.issubset(fields) and not execution,
        "semantic_note": semantic_note,
    }


def fhsc_anchor_interpretation(prior: Mapping[str, Any]) -> dict[str, Any]:
    """Read the prior artifact's exact counts; no coverage-based extrapolation is allowed."""
    counts = dict(prior.get("fhsc_reconciliation_contract", {}).get("reconciliation_counts") or {})
    rows = list(prior.get("qualified_rows") or [])
    exact = counts.get("EXACT", 0)
    tickers = sorted({str(row.get("ticker")) for row in rows})
    sessions = sorted({str(row.get("session")) for row in rows})
    if exact != len(rows) or exact != 12 or len(tickers) != 4 or len(sessions) != 3:
        raise ValueError("prior_fhsc_anchor_scope_not_the_retained_12_exact_rows")
    return {
        "exact_rows": exact, "tickers": tickers, "sessions": sessions,
        "transform_verdict": "EMPIRICALLY_VALIDATED_ONLY_FOR_4_TICKERS_3_SESSIONS_12_ROWS",
        "generalization": "NOT_JUSTIFIED_NO_INDEPENDENT_MATCHED_VALUE_ANCHOR_OUTSIDE_12_ROWS",
    }


def build_artifact(*, inventories: Iterable[Mapping[str, Any]], database_inventory: Iterable[Mapping[str, Any]],
                   prior: Mapping[str, Any], raw_counter_fields: Iterable[str]) -> dict[str, Any]:
    stores = [dict(row) for row in inventories]
    databases = [dict(row) for row in database_inventory]
    anchor = fhsc_anchor_interpretation(prior)
    fields = sorted(set(raw_counter_fields))
    artifact: dict[str, Any] = {
        "artifact_type": CONTRACT_VERSION, "version": VERSION,
        "historical_store_inventory": stores, "database_inventory": databases,
        "raw_trades_field_observation": {
            "execution_fields": ["boardId", "matchPrice", "matchQtty"],
            "counter_fields_observed": fields,
            "gross_trade_amount_semantics": "UNRESOLVED_BOARD_DEPENDENT_CUMULATIVE_COUNTER_NOT_VALUE_AUTHORITY",
        },
        "source_schema_contract": {
            "G1": "boardId=G1; qualified only for the exact FHSC anchor rows",
            "matchPrice": "DNSE retained raw field; native thousands-VND multiplier validated only in the 12-row scope",
            "matchQtty": "DNSE retained raw field; x10 quantity multiplier validated only in the 12-row scope",
            "formula": "sum(G1.matchPrice * G1.matchQtty) * 10 * 1000",
        },
        "fhsc_12_row_interpretation": anchor,
        "daily_volume_semantics": {
            "result": "DAILY_VOLUME_NOT_A_VALUE_FIELD",
            "board_test": "40-session retained C5 shows 10*G1 equals daily v on 35164/35231 rows; put-through boards are not thereby included",
            "price_and_liquidity_basis_independence": "historical price adjustment status does not establish volume adjustment status",
        },
        "qualified_matched_value": {
            "tickers": anchor["tickers"], "sessions": anchor["sessions"], "rows": anchor["exact_rows"],
            "adv20": {"ready": False, "reason": "3_OF_20_QUALIFIED_COMPLETE_SESSIONS_PER_TICKER"},
        },
        "authority_result": "EXISTING_STORE_CANNOT_UNLOCK_ADV20",
        "position_sizing_status": "BLOCKED",
        "lane_terminal_status": "EXISTING_STORE_CANNOT_UNLOCK_ADV20",
        "next_data_gate": "20_EXPECTED_COMPLETE_SESSIONS_WITH_INDEPENDENT_EXACT_G1_MATCHED_VALUE_ANCHORS_OR_AN_INDEPENDENTLY_QUALIFIED_EXPLICIT_MATCHED_VALUE_FIELD",
    }
    digest = _identity(artifact)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = f"historical_matched_value_existing_store_requalification:{digest}"
    return artifact
