"""DNSE market-data raw-ingest readiness inventory.

This is a collection-planning inventory, not analytical authority.  It is
deliberately conservative: a dataset can be ready for immutable raw retention
while its price, volume, board, or foreign-flow semantics remain UNKNOWN.
"""
from __future__ import annotations

from typing import Any

from dnse_market_data import MARKET_DATA_ENDPOINTS

READY_FOR_RAW_INGEST = "READY_FOR_RAW_INGEST"
REQUIRES_REQUEST_CONTRACT_FIX = "REQUIRES_REQUEST_CONTRACT_FIX"
NOT_APPLICABLE = "NOT_APPLICABLE"
DEFERRED = "DEFERRED"


def _entry(capability: str, dataset: str, classification: str, *,
           instrument_types: list[str], request_behavior: str,
           time_dimensions: str, existing_support: str, note: str) -> dict[str, Any]:
    endpoint = MARKET_DATA_ENDPOINTS[capability]["path"]
    return {
        "capability": capability,
        "endpoint": endpoint,
        "provider": "DNSE",
        "dataset": dataset,
        "classification": classification,
        "instrument_types": instrument_types,
        "request_behavior": request_behavior,
        "time_dimensions": time_dimensions,
        "existing_support": existing_support,
        "raw_semantics": "PRESERVE_PROVIDER_FIELDS; analytical_semantics_not_promoted",
        "note": note,
    }


def dataset_inventory() -> list[dict[str, Any]]:
    """Return deterministic planning facts for every allowlisted market endpoint."""
    entries = [
        _entry("instruments", "security_master", READY_FOR_RAW_INGEST,
               instrument_types=["all provider-discovered instruments"],
               request_behavior="paginated page/limit; provider total/pageSize drives termination",
               time_dimensions="retrieved_at snapshot", existing_support="dnse_instrument_universe; discover_market_universe.py",
               note="Dynamic universe authority; raw marketId/securityGroupId retained verbatim."),
        _entry("ohlc", "ohlc_1D", READY_FOR_RAW_INGEST,
               instrument_types=["ST/EQUITY for type=STOCK", "INDEX when separately requested"],
               request_behavior="symbol/type/resolution/from/to; bounded inclusive date chunks",
               time_dimensions="daily source rows in opaque payload; retrieved_at", existing_support="bulk_ingest_dnse_raw.py",
               note="Raw retention is allowed with price_basis=UNKNOWN; 1D is the proven token."),
        _entry("working_dates", "working_dates", READY_FOR_RAW_INGEST,
               instrument_types=["market-wide"], request_behavior="global GET; observed provider response is a forward calendar window",
               time_dimensions="provider calendar dates; retrieved_at", existing_support="ingest_dnse_global_market_raw.py",
               note="Retain observed calendar response; no session semantics are promoted."),
        _entry("security_definition", "security_definition", DEFERRED,
               instrument_types=["per symbol"], request_behavior="per-symbol current security definition",
               time_dimensions="retrieved_at only", existing_support="dnse_market_data allowlist",
               note="Overlaps security master and has no historical snapshot cadence in this milestone."),
        _entry("trading_session", "trading_session", DEFERRED,
               instrument_types=["market-wide"], request_behavior="global current-session GET",
               time_dimensions="retrieved_at only", existing_support="dnse_market_data allowlist",
               note="Needs an explicit operational snapshot cadence before collection."),
        _entry("trades_history", "trades_history", REQUIRES_REQUEST_CONTRACT_FIX,
               instrument_types=["per symbol/board"], request_behavior="observed narrow range and nextPageToken pagination",
               time_dimensions="intraday event time", existing_support="dnse_market_data_probe.py",
               note="Need bounded pagination and board/request-contract rules; raw semantics remain separate."),
        _entry("quotes_history", "quotes_history", REQUIRES_REQUEST_CONTRACT_FIX,
               instrument_types=["per symbol/board"], request_behavior="observed narrow range and nextPageToken pagination",
               time_dimensions="intraday quote time", existing_support="dnse_market_data_probe.py",
               note="Need bounded pagination and board/request-contract rules."),
        _entry("foreign_trading", "foreign_trading", READY_FOR_RAW_INGEST,
               instrument_types=["ST/EQUITY for the current dynamic stock universe"],
               request_behavior="one Vietnam-local session per symbol; DESC; optional boardId; nextPageToken exhausted page by page",
               time_dimensions="provider row time/trading session plus requested session date",
               existing_support="bulk_ingest_dnse_foreign_trading_raw.py",
               note="Raw page retention is ready; board IDs are preserved and foreign-flow VALUE authority is unchanged."),
    ]
    for capability, dataset in (("trades_latest", "trades_latest"), ("quotes_latest", "quotes_latest"),
                                ("expected_price", "expected_price"), ("close_price", "close_price")):
        entries.append(_entry(capability, dataset, DEFERRED,
                              instrument_types=["per symbol/board"], request_behavior="current/latest snapshot",
                              time_dimensions="retrieved_at only", existing_support="dnse_market_data allowlist",
                              note="Needs explicit cadence and board request contract before market-wide retention."))
    return sorted(entries, key=lambda item: item["capability"])


def inventory_by_classification() -> dict[str, list[dict[str, Any]]]:
    result = {kind: [] for kind in (READY_FOR_RAW_INGEST, REQUIRES_REQUEST_CONTRACT_FIX,
                                    NOT_APPLICABLE, DEFERRED)}
    for entry in dataset_inventory():
        result[entry["classification"]].append(entry)
    return result
