"""Official exchange per-symbol, per-session trading statistics (HOSE / HNX public routes).

WHAT THIS MODULE IS
    A small, read-only source adapter for two first-party exchange surfaces that publish a
    dated, per-symbol daily trading history with an explicit matched / put-through / odd-lot
    split. Both were located by bounded discovery on 2026-09-28 from the exchanges' own public
    web front ends. Neither requires login, and neither is a commercial provider:

    * HOSE ``GET https://api.hsx.vn/mk/api/v1/market/securities/tradingresult/{SYMBOL}``
      (the route the hsx.vn single-page app calls for "Kết quả giao dịch"). JSON, 20 rows per
      page, newest first; one row per session with ``reportDate`` (UTC midnight epoch of the
      session date), ``mainVolume``/``mainValue`` (order matching, round lot),
      ``oddlotvolume``/``oddlotvalue``, ``bigLotVolume``/``bigLotValue`` (put-through, round
      lot), ``bigLotVolume_OL``/``bigLotValue_OL`` (put-through, odd lot) and
      ``totalShare``/``totalValue``. Shares and VND.
    * HNX ``POST https://hnx.vn/ModuleIssuer/Report_NY/ThongTinTongHopListSearch_Datas``
      (the "Thông tin tổng hợp" tab of the hnx.vn security page, used for both listed ``NY``
      and UPCoM ``UC`` securities). HTML table, newest first; one row per session with KLGD
      (shares) and GTGD (thousand VND), each split Khớp lệnh / Thỏa thuận / Tổng.

WHAT THIS MODULE IS NOT
    Not a crawler, not a scheduler, and not an authority decision. It builds request
    descriptions and parses retained response bytes. Every parse either returns rows whose
    internal arithmetic closes exactly (components sum to the published total) or reports a
    structured failure; it never coerces, rounds, or fills a missing session. Which liquidity
    use a parsed row may serve is decided by ``liquidity_authority_contract``.

The two exchanges do not define "matched" identically. HOSE publishes round-lot order matching
and odd-lot matching separately; HNX's Khớp lệnh is a single order-matching total. Rows
therefore carry the exchange's own component identity (``MATCHED_ROUND_LOT`` vs
``MATCHED_ALL``); one exchange's definition is never relabelled as the other's.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

CONTRACT_VERSION = "official_exchange_trading_statistics/v1"

HOSE = "HOSE"
HNX = "HNX"
UPCOM = "UPCOM"
EXCHANGES = (HOSE, HNX, UPCOM)

SOURCE_HOSE_TRADING_RESULT = "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT"
SOURCE_HNX_THONG_TIN_TONG_HOP = "HNX_PUBLIC_ISSUER_REPORT_THONG_TIN_TONG_HOP"

HOSE_TRADING_RESULT_URL = "https://api.hsx.vn/mk/api/v1/market/securities/tradingresult/{symbol}?pageIndex={page}&pageSize=20"
HOSE_PAGE_ROWS = 20
HNX_THONG_TIN_TONG_HOP_URL = "https://hnx.vn/ModuleIssuer/Report_NY/ThongTinTongHopListSearch_Datas"
HNX_MARKET_CODE = {HNX: "NY", UPCOM: "UC"}

# DNSE ``marketId`` values observed on retained trades_latest bodies.
DNSE_MARKET_ID_TO_EXCHANGE = {"STO": HOSE, "STX": HNX, "UPX": UPCOM}

# Component identities (shared vocabulary with liquidity_authority_contract).
MATCHED_ROUND_LOT = "MATCHED_ROUND_LOT"
MATCHED_ODD_LOT = "MATCHED_ODD_LOT"
PUT_THROUGH_ROUND_LOT = "PUT_THROUGH_ROUND_LOT"
PUT_THROUGH_ODD_LOT = "PUT_THROUGH_ODD_LOT"
MATCHED_ALL = "MATCHED_ALL"
PUT_THROUGH_ALL = "PUT_THROUGH_ALL"
TOTAL = "TOTAL"

#: HOSE raw field pairs (volume field, value field) per component.
HOSE_COMPONENT_FIELDS = {
    MATCHED_ROUND_LOT: ("mainVolume", "mainValue"),
    MATCHED_ODD_LOT: ("oddlotvolume", "oddlotvalue"),
    PUT_THROUGH_ROUND_LOT: ("bigLotVolume", "bigLotValue"),
    PUT_THROUGH_ODD_LOT: ("bigLotVolume_OL", "bigLotValue_OL"),
    TOTAL: ("totalShare", "totalValue"),
}
_HOSE_PARTS = (MATCHED_ROUND_LOT, MATCHED_ODD_LOT, PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT)
#: Aggregates derived by exact addition of HOSE's own published components.
HOSE_DERIVED_AGGREGATES = {MATCHED_ALL: (MATCHED_ROUND_LOT, MATCHED_ODD_LOT),
                           PUT_THROUGH_ALL: (PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT)}

#: HNX table columns (0-based cell index) per component: (volume shares, value thousand VND).
HNX_COMPONENT_CELLS = {MATCHED_ALL: (2, 5), PUT_THROUGH_ALL: (3, 6), TOTAL: (4, 7)}
HNX_ROW_CELL_COUNT = 15
#: Header labels the parser requires, in order, before it will read any numeric cell.
HNX_REQUIRED_HEADER_SEQUENCE = (
    "Ngày", "KLGD (Cổ phiếu)", "GTGD (Nghìn đồng)", "Khớp lệnh", "Thỏa thuận", "Tổng",
    "Khớp lệnh", "Thỏa thuận", "Tổng",
)

PARSED = "PARSED"


class OfficialTradingStatisticsError(ValueError):
    """A caller asked for something this adapter cannot describe (never a data failure)."""


def exchange_for_dnse_market_id(market_id: Any) -> str | None:
    return DNSE_MARKET_ID_TO_EXCHANGE.get(str(market_id)) if market_id is not None else None


def hose_request(symbol: str, *, page: int = 1) -> dict[str, Any]:
    if page < 1:
        raise OfficialTradingStatisticsError("HOSE_PAGE_INDEX_INVALID")
    symbol = symbol.upper()
    return {"exchange": HOSE, "source": SOURCE_HOSE_TRADING_RESULT, "symbol": symbol, "method": "GET",
            "url": HOSE_TRADING_RESULT_URL.format(symbol=symbol, page=page), "form": None, "page": page,
            "rows_requested": HOSE_PAGE_ROWS}


def hnx_request(symbol: str, *, exchange: str, rows: int = 60) -> dict[str, Any]:
    if exchange not in HNX_MARKET_CODE:
        raise OfficialTradingStatisticsError(f"HNX_ROUTE_NOT_FOR_EXCHANGE:{exchange}")
    if rows < 1:
        raise OfficialTradingStatisticsError("HNX_ROW_COUNT_INVALID")
    symbol = symbol.upper()
    form = {"p_issearch": "0", "p_market": HNX_MARKET_CODE[exchange], "p_symbol": symbol,
            "p_orderby": "col_a_TTTH", "p_ordertype": "DESC", "p_currentpage": "1", "p_record_on_page": str(rows)}
    return {"exchange": exchange, "source": SOURCE_HNX_THONG_TIN_TONG_HOP, "symbol": symbol, "method": "POST",
            "url": HNX_THONG_TIN_TONG_HOP_URL, "form": form, "page": 1, "rows_requested": rows}


def request_for(symbol: str, exchange: str, *, hose_page: int = 1, hnx_rows: int = 60) -> dict[str, Any]:
    if exchange == HOSE:
        return hose_request(symbol, page=hose_page)
    return hnx_request(symbol, exchange=exchange, rows=hnx_rows)


def _failure(status: str, **extra: Any) -> dict[str, Any]:
    return {"parse_status": status, "rows": [], **extra}


def _whole(value: Any, *, field: str) -> int:
    """A non-negative whole number from a JSON number; fractional or negative input fails."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"FIELD_NOT_NUMERIC:{field}")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"FIELD_NOT_NON_NEGATIVE_WHOLE:{field}")
    return int(number)


def _component(volume: int, value: int) -> dict[str, int]:
    return {"volume_shares": volume, "value_vnd": value}


def parse_hose_trading_result(body: bytes | str, *, symbol: str) -> dict[str, Any]:
    """Parse one retained HOSE ``tradingresult`` page into per-session component rows."""
    symbol = symbol.upper()
    try:
        payload = json.loads(body if isinstance(body, str) else body.decode("utf-8"), parse_float=Decimal)
    except (ValueError, UnicodeDecodeError):
        return _failure("MALFORMED_JSON")
    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        return _failure("HOSE_RESPONSE_NOT_SUCCESS")
    data = payload.get("data")
    if not isinstance(data, Mapping) or not isinstance(data.get("list"), list):
        return _failure("HOSE_LIST_ABSENT")
    paging = data.get("paging") if isinstance(data.get("paging"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in data["list"]:
        if not isinstance(raw, Mapping):
            rejected.append({"reason": "ROW_NOT_OBJECT"})
            continue
        if str(raw.get("symbol") or "").strip().upper() != symbol:
            rejected.append({"reason": "SYMBOL_MISMATCH", "raw_symbol": raw.get("symbol")})
            continue
        epoch = raw.get("reportDate")
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch % 86400:
            rejected.append({"reason": "REPORT_DATE_NOT_UTC_MIDNIGHT_EPOCH", "raw_report_date": epoch})
            continue
        session = datetime.fromtimestamp(epoch, tz=timezone.utc).date()
        if raw.get("month") != session.month or raw.get("year") != session.year:
            rejected.append({"reason": "REPORT_DATE_MONTH_YEAR_DISAGREE", "session": session.isoformat()})
            continue
        try:
            components = {name: _component(_whole(raw.get(vol), field=vol), _whole(raw.get(val), field=val))
                          for name, (vol, val) in HOSE_COMPONENT_FIELDS.items()}
        except ValueError as exc:
            rejected.append({"reason": str(exc), "session": session.isoformat()})
            continue
        parts_volume = sum(components[name]["volume_shares"] for name in _HOSE_PARTS)
        parts_value = sum(components[name]["value_vnd"] for name in _HOSE_PARTS)
        integrity = (parts_volume == components[TOTAL]["volume_shares"] and parts_value == components[TOTAL]["value_vnd"])
        # Exact sums of HOSE's own published parts; never HNX figures relabelled.
        for aggregate, (first, second) in HOSE_DERIVED_AGGREGATES.items():
            components[aggregate] = _component(components[first]["volume_shares"] + components[second]["volume_shares"],
                                               components[first]["value_vnd"] + components[second]["value_vnd"])
        rows.append({"symbol": symbol, "exchange": HOSE, "session": session.isoformat(),
                     "components": components, "derived_components": sorted(HOSE_DERIVED_AGGREGATES),
                     "row_integrity": "COMPONENTS_SUM_TO_TOTAL" if integrity else "COMPONENTS_DO_NOT_SUM_TO_TOTAL",
                     "symbol_binding": "RESPONSE_FIELD",
                     "raw_row": json.loads(json.dumps(raw, default=str))})
    sessions = [row["session"] for row in rows]
    if len(set(sessions)) != len(sessions):
        return _failure("DUPLICATE_SESSION_ROWS", rejected=rejected)
    return {"parse_status": PARSED, "source": SOURCE_HOSE_TRADING_RESULT, "symbol": symbol, "exchange": HOSE,
            "rows": sorted(rows, key=lambda row: row["session"], reverse=True), "rejected": rejected,
            "paging": {key: paging.get(key) for key in ("pageIndex", "pageSize", "totalCount", "totalPages")}}


_TAG = re.compile(r"<[^>]+>")


def _cell_text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _vn_decimal(text: str, *, field: str) -> Decimal:
    """Vietnamese number text: ``.`` groups thousands, ``,`` is the decimal separator."""
    cleaned = text.strip()
    if not cleaned or not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?", cleaned):
        raise ValueError(f"FIELD_NOT_VN_NUMBER:{field}:{text!r}")
    try:
        return Decimal(cleaned.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"FIELD_NOT_VN_NUMBER:{field}:{text!r}") from exc


def parse_hnx_thong_tin_tong_hop(body: bytes | str, *, symbol: str, exchange: str) -> dict[str, Any]:
    """Parse one retained HNX "Thông tin tổng hợp" table into per-session component rows.

    The page does not echo the symbol per row, so the symbol is bound by the retained request
    form only (``symbol_binding = REQUEST_PARAMETER_ONLY``); a downstream reconciliation against
    an independent same-session observation is what confirms the binding.
    """
    if exchange not in HNX_MARKET_CODE:
        raise OfficialTradingStatisticsError(f"HNX_ROUTE_NOT_FOR_EXCHANGE:{exchange}")
    symbol = symbol.upper()
    try:
        text = body if isinstance(body, str) else body.decode("utf-8")
    except UnicodeDecodeError:
        return _failure("MALFORMED_HTML_ENCODING")
    headers = [_cell_text(fragment) for fragment in re.findall(r"<th[^>]*>(.*?)</th>", text, re.S)]
    position = 0
    for label in headers:
        if position < len(HNX_REQUIRED_HEADER_SEQUENCE) and label == HNX_REQUIRED_HEADER_SEQUENCE[position]:
            position += 1
    if position != len(HNX_REQUIRED_HEADER_SEQUENCE):
        return _failure("HNX_HEADER_SCHEMA_DRIFT", headers=headers)
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [_cell_text(fragment) for fragment in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)]
        if not cells:
            continue
        if len(cells) != HNX_ROW_CELL_COUNT:
            rejected.append({"reason": "ROW_CELL_COUNT_UNEXPECTED", "cell_count": len(cells)})
            continue
        try:
            session = datetime.strptime(cells[1], "%d/%m/%Y").date().isoformat()
        except ValueError:
            rejected.append({"reason": "SESSION_DATE_INVALID", "raw_date": cells[1]})
            continue
        try:
            components = {}
            for name, (volume_index, value_index) in HNX_COMPONENT_CELLS.items():
                volume = _vn_decimal(cells[volume_index], field=f"{name}.volume")
                value_vnd = _vn_decimal(cells[value_index], field=f"{name}.value") * 1000
                if volume != volume.to_integral_value() or value_vnd != value_vnd.to_integral_value():
                    raise ValueError(f"FIELD_NOT_WHOLE_AFTER_UNIT_SCALING:{name}")
                components[name] = _component(int(volume), int(value_vnd))
        except ValueError as exc:
            rejected.append({"reason": str(exc), "session": session})
            continue
        integrity = (components[MATCHED_ALL]["volume_shares"] + components[PUT_THROUGH_ALL]["volume_shares"] == components[TOTAL]["volume_shares"]
                     and components[MATCHED_ALL]["value_vnd"] + components[PUT_THROUGH_ALL]["value_vnd"] == components[TOTAL]["value_vnd"])
        rows.append({"symbol": symbol, "exchange": exchange, "session": session, "components": components,
                     "row_integrity": "COMPONENTS_SUM_TO_TOTAL" if integrity else "COMPONENTS_DO_NOT_SUM_TO_TOTAL",
                     "symbol_binding": "REQUEST_PARAMETER_ONLY", "raw_cells": cells,
                     "value_source_unit": "THOUSAND_VND"})
    sessions = [row["session"] for row in rows]
    if len(set(sessions)) != len(sessions):
        return _failure("DUPLICATE_SESSION_ROWS", rejected=rejected)
    return {"parse_status": PARSED, "source": SOURCE_HNX_THONG_TIN_TONG_HOP, "symbol": symbol, "exchange": exchange,
            "rows": sorted(rows, key=lambda row: row["session"], reverse=True), "rejected": rejected}


def parse_response(request: Mapping[str, Any], body: bytes | str) -> dict[str, Any]:
    if request.get("source") == SOURCE_HOSE_TRADING_RESULT:
        return parse_hose_trading_result(body, symbol=str(request["symbol"]))
    if request.get("source") == SOURCE_HNX_THONG_TIN_TONG_HOP:
        return parse_hnx_thong_tin_tong_hop(body, symbol=str(request["symbol"]), exchange=str(request["exchange"]))
    raise OfficialTradingStatisticsError(f"UNREGISTERED_OFFICIAL_SOURCE:{request.get('source')}")
