"""First-party, bounded Vietcombank USD/VND exchange-rate adapter.

Replaces the runtime macro path's prior dependency on
``vnstock.explorer.misc.exchange_rate.vcb_exchange_rate`` (see
docs/DECISIONS.md MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1). That wrapper was
statically inspected (installed vnstock 4.0.4,
``vnstock/explorer/misc/exchange_rate.py``) to extract its exact request/parse contract,
reproduced here directly against Vietcombank's own public export endpoint:

    GET https://www.vietcombank.com.vn/api/exchangerates/exportexcel?date=YYYY-MM-DD
    -> 200 JSON {"Data": "<base64-encoded .xlsx workbook>", ...}

The workbook's "ExchangeRate" sheet has a fixed 5-column shape (CurrencyCode, CurrencyName,
Buy Cash, Buy Transfer, Sell) with 2 header rows and 4 footer/notes rows that the original
wrapper strips via ``iloc[2:-4]``; that slicing is reproduced exactly. This route is public
and keyless -- no API key, no session, no authenticated/undocumented VNStock-owned
infrastructure -- so no vnstock/vnai import is required or performed here.
"""
from __future__ import annotations

import base64
import io
import math
import warnings
from collections import namedtuple
from datetime import datetime

import pandas as pd
import requests

# The exported workbook has no default style; openpyxl's own default is a harmless cosmetic
# fallback (identical warning the original vnstock wrapper already suppressed).
warnings.filterwarnings(
    "ignore", message="Workbook contains no default style, apply openpyxl's default",
)

VCB_EXCHANGE_RATE_URL = "https://www.vietcombank.com.vn/api/exchangerates/exportexcel"
DEFAULT_TIMEOUT_SECONDS = 10
SHEET_NAME = "ExchangeRate"
EXPECTED_COLUMNS = ["currency_code", "currency_name", "buy_cash", "buy_transfer", "sell"]

# status: "OK" | "REQUEST_FAILED" | "PARSE_FAILED" | "SOURCE_RETURNED_NO_VALUE"
MacroFetchResult = namedtuple("MacroFetchResult", "pairs status reason")


def fetch_vcb_usd_sell_rate(
    date: str | None = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MacroFetchResult:
    """One bounded request for the USD sell rate on ``date`` (default: today, local clock).

    Returns a ``MacroFetchResult`` whose ``pairs`` is ``[(date, sell_rate)]`` on success or
    ``[]`` on any failure, with an explicit ``status``/``reason`` classification distinguishing
    a transport failure from an unparseable response from an absent USD row -- never silently
    substitutes a stale or fabricated value.
    """
    query_date = date or datetime.now().strftime("%Y-%m-%d")
    try:
        response = requests.get(
            VCB_EXCHANGE_RATE_URL, params={"date": query_date}, timeout=timeout,
        )
    except requests.Timeout:
        return MacroFetchResult([], "REQUEST_FAILED", "TIMEOUT")
    except requests.RequestException as exc:
        return MacroFetchResult([], "REQUEST_FAILED", type(exc).__name__)

    if response.status_code != 200:
        return MacroFetchResult([], "REQUEST_FAILED", f"HTTP_{response.status_code}")

    try:
        payload = response.json()
        excel_bytes = base64.b64decode(payload["Data"])
        frame = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=SHEET_NAME)
        frame = frame.iloc[2:-4].copy()
        frame.columns = EXPECTED_COLUMNS
    except Exception as exc:  # noqa: BLE001 - any parse/shape defect is PARSE_FAILED, not a crash
        return MacroFetchResult([], "PARSE_FAILED", type(exc).__name__)

    usd_rows = frame[frame["currency_code"].astype(str).str.upper() == "USD"]
    if usd_rows.empty:
        return MacroFetchResult([], "SOURCE_RETURNED_NO_VALUE", "USD_ROW_ABSENT")

    raw_sell = usd_rows["sell"].iloc[0]
    # pandas' Excel reader silently parses several tokens (e.g. "N/A") to NaN; treating that as
    # a "successfully parsed" float would fabricate a value from a genuinely missing cell.
    if pd.isna(raw_sell):
        return MacroFetchResult([], "SOURCE_RETURNED_NO_VALUE", "SELL_CELL_EMPTY_OR_NA")

    try:
        sell_value = float(str(raw_sell).replace(",", "").strip())
    except (TypeError, ValueError):
        return MacroFetchResult([], "PARSE_FAILED", "SELL_VALUE_NOT_NUMERIC")

    if not math.isfinite(sell_value):
        return MacroFetchResult([], "PARSE_FAILED", "SELL_VALUE_NOT_FINITE")

    return MacroFetchResult([(query_date, sell_value)], "OK", None)
