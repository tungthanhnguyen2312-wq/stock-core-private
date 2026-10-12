"""First-party, bounded SJC gold-price adapter.

Replaces the runtime macro path's prior dependency on
``vnstock.explorer.misc.gold_price.sjc_gold_price`` (see docs/DECISIONS.md
MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1). That wrapper was statically inspected
(installed vnstock 4.0.4, ``vnstock/explorer/misc/gold_price.py``) to extract its exact
request/parse contract, reproduced here directly against SJC's own public price-service
endpoint:

    POST https://sjc.com.vn/GoldPrice/Services/PriceService.ashx
    body (application/x-www-form-urlencoded): method=GetSJCGoldPriceByDate&toDate=DD/MM/YYYY
    -> 200 JSON {"success": true, "data": [{"TypeName","BranchName","BuyValue","SellValue"}, ...]}

This route is public and keyless -- no API key, no session/auth header, no
undocumented/authenticated VNStock-owned infrastructure. The original wrapper attaches
browser-like headers (via ``vnstock.core.utils.user_agent.get_headers(data_source="SJC")``)
purely to avoid basic bot-blocking on a public endpoint; ``SJC_HEADERS`` below reproduces the
same fixed Referer/Origin/User-Agent values as a plain literal instead of importing that
vnstock module, so this adapter's own import graph never touches vnstock/vnai.
"""
from __future__ import annotations

from collections import namedtuple
from datetime import datetime

import requests

SJC_GOLD_PRICE_URL = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"
DEFAULT_TIMEOUT_SECONDS = 10
PREFERRED_BRANCH_SUBSTRING = "Hồ Chí Minh"  # "Hồ Chí Minh"

SJC_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://sjc.com.vn/bieu-do-gia-vang",
    "Origin": "https://sjc.com.vn",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# status: "OK" | "REQUEST_FAILED" | "PARSE_FAILED" | "SOURCE_RETURNED_NO_VALUE"
MacroFetchResult = namedtuple("MacroFetchResult", "pairs status reason")


def fetch_sjc_gold_sell_price(
    date: str | None = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MacroFetchResult:
    """One bounded request for the SJC (Ho Chi Minh branch preferred) gold sell price on
    ``date`` (default: today, local clock).

    Returns a ``MacroFetchResult`` whose ``pairs`` is ``[(date, sell_price)]`` on success or
    ``[]`` on any failure, with an explicit ``status``/``reason`` classification.
    """
    if date is None:
        query_date = datetime.now().date()
    else:
        try:
            query_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return MacroFetchResult([], "REQUEST_FAILED", "INVALID_DATE_FORMAT")

    body = f"method=GetSJCGoldPriceByDate&toDate={query_date.strftime('%d/%m/%Y')}"
    try:
        response = requests.post(
            SJC_GOLD_PRICE_URL, headers=SJC_HEADERS, data=body, timeout=timeout,
        )
    except requests.Timeout:
        return MacroFetchResult([], "REQUEST_FAILED", "TIMEOUT")
    except requests.RequestException as exc:
        return MacroFetchResult([], "REQUEST_FAILED", type(exc).__name__)

    if response.status_code != 200:
        return MacroFetchResult([], "REQUEST_FAILED", f"HTTP_{response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        return MacroFetchResult([], "PARSE_FAILED", type(exc).__name__)

    if not isinstance(payload, dict) or not payload.get("success"):
        return MacroFetchResult([], "SOURCE_RETURNED_NO_VALUE", "SUCCESS_FALSE_OR_MALFORMED")

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return MacroFetchResult([], "SOURCE_RETURNED_NO_VALUE", "EMPTY_DATA_LIST")

    branch_row = next(
        (row for row in rows if PREFERRED_BRANCH_SUBSTRING in str(row.get("BranchName", ""))),
        rows[0],
    )
    try:
        sell_value = float(branch_row["SellValue"])
    except (KeyError, TypeError, ValueError):
        return MacroFetchResult([], "PARSE_FAILED", "SELL_VALUE_NOT_NUMERIC")

    return MacroFetchResult([(query_date.strftime("%Y-%m-%d"), sell_value)], "OK", None)
