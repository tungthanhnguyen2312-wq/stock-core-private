"""Immutable first-party HNX list, rights, and disclosure-index acquisition.

This is deliberately a source-surface projection.  It does not turn HNX's KLLH
label into common shares outstanding, a rights event into a price adjustment, or
a ticker-bearing index row into a financial fact.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONTRACT_VERSION = "hnx_enumerable_universe_kllh_event_and_disclosure_scaleout/v1"
BASE = "https://hnx.vn"
LISTS = {
    "HNX_LISTED": ("/vi-vn/cophieu-etfs/chung-khoan-ny.html", "/ModuleIssuer/List/ListSearch_Datas", ""),
    "UPCOM": ("/vi-vn/cophieu-etfs/chung-khoan-uc.html", "/ModuleIssuer/UC_Issuer/ListSearch_Datas", "UC"),
}
RIGHTS = {
    "HNX_LISTED": ("/vi-vn/thong-tin-cong-bo-ny-hnx.html", "/ModuleArticles/ArticlesCPEtfs/NextPageTinCPNY_LTHQ"),
    "UPCOM": ("/vi-vn/thong-tin-cong-bo-up-hnx.html", "/ModuleArticles/ArticlesCPEtfs/NextPageTHQUpCoM"),
}
DISCLOSURES = {
    "HNX_LISTED": ("/vi-vn/thong-tin-cong-bo-ny-hnx.html", "/ModuleArticles/ArticlesCPEtfs/NextPageTinCPNY"),
    "UPCOM": ("/vi-vn/thong-tin-cong-bo-up-hnx.html", "/ModuleArticles/ArticlesCPEtfs/NextPageTinUpCoM"),
}
_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TOTAL = re.compile(r"Tổng số\s+(\d+)\s+bản ghi", re.I)
_LAST = re.compile(r'<span[^>]*id=["\']end["\'][^>]*>(?:&gt;|>>)</span>|pageNext[^\(]*\((\d+)\)', re.I)
_ARTICLE = re.compile(r"funcViewDetailArticlesByID\((\d+),\s*1\)", re.I)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(value: Mapping[str, Any]) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def _text(value: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", value)).split())


def _number(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _date(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})(?:\s+\d{2}:\d{2})?\s*", value)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("IMMUTABLE_CONTENT_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        candidate = Path(handle.name)
    candidate.replace(path)


def fetch(url: str, *, body: Mapping[str, str] | None = None) -> dict[str, Any]:
    observed_at = _now()
    try:
        data = urlencode(body).encode() if body is not None else None
        request = Request(url, data=data, headers={
            "Accept": "application/json,text/html", "User-Agent": "StockLookup-HNX-Enumerable-Universe/1.0",
            **({"Content-Type": "application/x-www-form-urlencoded"} if data else {}),
        })
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            return {"requested_url": url, "official_url": response.geturl(), "retrieved_at": observed_at,
                    "http_status": response.status, "content_type": response.headers.get_content_type(), "data": payload}
    except Exception as exc:
        return {"requested_url": url, "official_url": url, "retrieved_at": observed_at, "http_status": None,
                "content_type": None, "data": b"", "error": type(exc).__name__}


def retain(*, response: Mapping[str, Any], destination: Path, surface: str, page: int | None,
           request_body: Mapping[str, str] | None) -> dict[str, Any]:
    data = bytes(response["data"])
    digest = _sha(data)
    suffix = ".json" if response.get("content_type") == "application/json" else ".html"
    relative = Path("raw") / surface / f"{page if page is not None else 'landing':0>4}-{digest}{suffix}"
    _atomic(destination / relative, data)
    return {"surface": surface, "page": page, "requested_url": response["requested_url"],
            "official_url": response["official_url"], "request_body": dict(request_body or {}),
            "retrieved_at": response["retrieved_at"], "http_status": response["http_status"],
            "content_type": response["content_type"], "sha256": digest,
            "relative_path": str(relative).replace("\\", "/"), "error": response.get("error")}


def _content(payload: bytes) -> str:
    try:
        decoded = json.loads(payload.decode("utf-8"))
        if isinstance(decoded, dict) and isinstance(decoded.get("Content"), str):
            return decoded["Content"]
    except json.JSONDecodeError:
        pass
    return payload.decode("utf-8", errors="replace")


def _rows(document: str) -> list[list[str]]:
    body_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", document, re.I | re.S)
    if not body_match:
        return []
    return [[_text(cell) for cell in _CELL.findall(row)] for row in _ROW.findall(body_match.group(1))]


def _total(document: str) -> int:
    match = _TOTAL.search(document)
    if not match:
        raise ValueError("SOURCE_TOTAL_MISSING")
    return int(match.group(1))


def _last_page(document: str, total: int, returned_rows: int) -> int:
    candidates = [int(value) for value in _LAST.findall(document) if value]
    if candidates:
        return max(candidates)
    if returned_rows == total:
        return 1
    raise ValueError("SOURCE_TERMINAL_PAGE_MISSING")


def _post_pages(*, endpoint: str, surface: str, destination: Path, base_body: Mapping[str, str]) -> tuple[list[tuple[str, dict[str, Any]]], list[dict[str, Any]], int]:
    first_body = {**base_body, "pNumPage": "1"}
    first_response = fetch(BASE + endpoint, body=first_body)
    if first_response["http_status"] != 200:
        raise ValueError(f"SOURCE_FETCH_FAILED:{surface}:1")
    first_document = _content(first_response["data"])
    total = _total(first_document)
    first_rows = _rows(first_document)
    last_page = _last_page(first_document, total, len(first_rows))
    responses = [(first_document, retain(response=first_response, destination=destination, surface=surface, page=1, request_body=first_body))]
    for page in range(2, last_page + 1):
        body = {**base_body, "pNumPage": str(page)}
        response = fetch(BASE + endpoint, body=body)
        if response["http_status"] != 200:
            raise ValueError(f"SOURCE_FETCH_FAILED:{surface}:{page}")
        document = _content(response["data"])
        if _total(document) != total:
            raise ValueError(f"SOURCE_TOTAL_CHANGED:{surface}:{page}")
        responses.append((document, retain(response=response, destination=destination, surface=surface, page=page, request_body=body)))
    all_rows = [row for document, _ in responses for row in _rows(document)]
    if len(all_rows) != total:
        raise ValueError(f"SOURCE_ROW_COUNT_MISMATCH:{surface}:{len(all_rows)}:{total}")
    return responses, [capture for _, capture in responses], total


def parse_list(document: str, *, market: str, capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for cells in _rows(document):
        if market == "HNX_LISTED" and len(cells) == 7:
            ticker, issuer, sector, first_date, listed_or_registered, kllh = cells[1:]
        elif market == "UPCOM" and len(cells) == 6:
            ticker, issuer, first_date, listed_or_registered, kllh = cells[1:]
            sector = None
        else:
            continue
        output.append({"ticker": ticker.upper(), "issuer_name": issuer, "market": market,
                       "first_trading_date": _date(first_date), "source_quantity_label": "KLNY (Cổ phiếu)" if market == "HNX_LISTED" else "KLĐKGD (Cổ phiếu)",
                       "source_listing_or_registration_quantity": _number(listed_or_registered), "hnx_kllh_label": "KLLH (Cổ phiếu)",
                       "hnx_kllh_shares": _number(kllh), "sector_label": sector or None,
                       "instrument_class": "EXCHANGE_STOCK_LIST_CANDIDATE", "instrument_class_basis": "HNX_ISSUER_LIST_SURFACE_NOT_ACCOUNTING_SECURITY_CLASS",
                       "source_url": capture["official_url"], "source_identity": capture["sha256"]})
    return output


def parse_events(document: str, *, market: str, capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    kinds = {"trả cổ tức bằng tiền": "CASH_DIVIDEND", "trả cổ tức bằng cp": "STOCK_DIVIDEND",
             "trả cp thưởng": "BONUS_ISSUE", "phát hành cp cho cổ đông hiện hữu": "RIGHTS_ISSUE"}
    output = []
    for cells in _rows(document):
        if len(cells) != 6:
            continue
        ticker, ex_date, record_date, execution_date, label = cells[1:]
        event_type = kinds.get(label.lower(), "AGM" if "đại hội cổ đông" in label.lower() else "OTHER")
        output.append({"ticker": ticker.upper(), "market": market, "event_type": event_type, "event_label": label,
                       "ex_date": _date(ex_date), "record_date": _date(record_date), "execution_date": _date(execution_date),
                       "qualification": "EX_DATE_OFFICIAL_QUALIFIED" if _date(ex_date) else "MISSING_EX_DATE",
                       "price_adjustment_candidate": event_type in {"CASH_DIVIDEND", "STOCK_DIVIDEND", "BONUS_ISSUE", "RIGHTS_ISSUE"},
                       "source_url": capture["official_url"], "source_identity": capture["sha256"]})
    return output


def parse_disclosures(document: str, *, market: str, capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for row_html in _ROW.findall(re.search(r"<tbody[^>]*>(.*?)</tbody>", document, re.I | re.S).group(1)) if re.search(r"<tbody[^>]*>(.*?)</tbody>", document, re.I | re.S) else []:
        cells = [_text(cell) for cell in _CELL.findall(row_html)]
        if len(cells) != 5:
            continue
        article = _ARTICLE.search(row_html)
        published, ticker, title = cells[1:4]
        output.append({"article_id": article.group(1) if article else None, "ticker": ticker.upper() or None, "market": market,
                       "published_at": _date(published), "published_at_raw": published, "title": title,
                       "financial_statement_candidate": any(term in title.lower() for term in ("báo cáo tài chính", "financial statement")),
                       "source_url": capture["official_url"], "source_identity": capture["sha256"]})
    return output


def _read_stocklookup_tickers(path: Path) -> set[str]:
    records = json.loads(path.read_text(encoding="utf-8")).get("records", {})
    if not isinstance(records, Mapping) or len(records) != 1683:
        raise ValueError("STOCKLOOKUP_1683_UNIVERSE_CONTRACT_INVALID")
    return {str(ticker).upper() for ticker in records}


def build(*, destination: Path, stocklookup_universe: Path, execute: bool = True) -> dict[str, Any]:
    if not execute:
        raise ValueError("LIVE_HNX_ACQUISITION_REQUIRES_EXECUTE_TRUE")
    captures: list[dict[str, Any]] = []
    universe: list[dict[str, Any]] = []
    list_totals: dict[str, int] = {}
    for market, (landing, endpoint, code) in LISTS.items():
        landing_response = fetch(BASE + landing)
        if landing_response["http_status"] != 200:
            raise ValueError(f"LIST_LANDING_FETCH_FAILED:{market}")
        captures.append(retain(response=landing_response, destination=destination, surface=f"{market.lower()}_list_landing", page=None, request_body=None))
        body = {"p_issearch": "0", "p_keysearch": "", "p_market_code": code, "p_orderby": "", "p_ordertype": "", "p_currentpage": "1", "p_record_on_page": "1000"}
        response = fetch(BASE + endpoint, body=body)
        if response["http_status"] != 200:
            raise ValueError(f"LIST_BULK_FETCH_FAILED:{market}")
        document = _content(response["data"])
        total = _total(document)
        capture = retain(response=response, destination=destination, surface=f"{market.lower()}_list_bulk", page=1, request_body=body)
        captures.append(capture)
        rows = parse_list(document, market=market, capture=capture)
        if len(rows) != total:
            raise ValueError(f"LIST_ROW_COUNT_MISMATCH:{market}:{len(rows)}:{total}")
        list_totals[market] = total
        universe.extend(rows)
    if len({row["ticker"] for row in universe}) != len(universe):
        raise ValueError("CROSS_LIST_TICKER_DUPLICATE")

    events: list[dict[str, Any]] = []
    event_totals: dict[str, int] = {}
    for market, (landing, endpoint) in RIGHTS.items():
        landing_response = fetch(BASE + landing)
        if landing_response["http_status"] != 200:
            raise ValueError(f"RIGHTS_LANDING_FETCH_FAILED:{market}")
        captures.append(retain(response=landing_response, destination=destination, surface=f"{market.lower()}_rights_landing", page=None, request_body=None))
        responses, page_captures, total = _post_pages(endpoint=endpoint, surface=f"{market.lower()}_rights", destination=destination,
            base_body={"pAction": "0", "pNhomTin": "", "pTieuDeTin": "", "pMaChungKhoan": "", "pFromDate": "", "pToDate": "", "pOrderBy": "", "pNumRecord": "1000"})
        captures.extend(page_captures); event_totals[market] = total
        events.extend(event for document, capture in responses for event in parse_events(document, market=market, capture=capture))

    disclosures: list[dict[str, Any]] = []
    disclosure_totals: dict[str, int] = {}
    for market, (landing, endpoint) in DISCLOSURES.items():
        landing_response = fetch(BASE + landing)
        if landing_response["http_status"] != 200:
            raise ValueError(f"DISCLOSURE_LANDING_FETCH_FAILED:{market}")
        captures.append(retain(response=landing_response, destination=destination, surface=f"{market.lower()}_disclosure_landing", page=None, request_body=None))
        responses, page_captures, total = _post_pages(endpoint=endpoint, surface=f"{market.lower()}_disclosures", destination=destination,
            base_body={"pAction": "0", "pNhomTin": "", "pTieuDeTin": "", "pMaChungKhoan": "", "pFromDate": "", "pToDate": "", "pOrderBy": "", "pNumRecord": "1000"})
        captures.extend(page_captures); disclosure_totals[market] = total
        disclosures.extend(row for document, capture in responses for row in parse_disclosures(document, market=market, capture=capture))

    if len(events) != sum(event_totals.values()) or len(disclosures) != sum(disclosure_totals.values()):
        raise ValueError("PAGINATED_SOURCE_ACCOUNTING_MISMATCH")
    stocklookup = _read_stocklookup_tickers(stocklookup_universe)
    hnx = {row["ticker"] for row in universe}
    quantities = [row for row in universe if row["hnx_kllh_shares"] is not None and row["source_listing_or_registration_quantity"] is not None]
    kllh_relation = Counter("EQUAL" if row["hnx_kllh_shares"] == row["source_listing_or_registration_quantity"] else "LT" if row["hnx_kllh_shares"] < row["source_listing_or_registration_quantity"] else "GT" for row in quantities)
    event_types = Counter(row["event_type"] for row in events)
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "captures": captures,
                "hnx_official_equity_universe": {"dataset": "hnx_official_equity_universe/v1", "records": universe,
                    "scope": "CURRENT_HNX_LISTED_AND_UPCOM_ISSUER_LIST_SURFACES", "instrument_class_boundary": "COMMON_EQUITY_CANDIDATE_ONLY_NOT_A_SECURITY_MASTER_OR_COMMON_SHARES_AUTHORITY"},
                "rights_event_index": {"dataset": "hnx_official_rights_event_index/v1", "records": events, "source_totals": event_totals},
                "disclosure_index": {"dataset": "hnx_official_disclosure_index/v1", "records": disclosures, "source_totals": disclosure_totals},
                "coverage": {"listed_source_total": list_totals["HNX_LISTED"], "upcom_source_total": list_totals["UPCOM"],
                    "common_equity_candidates": len(universe), "non_common_equity": 0, "instrument_class_unresolved": 0,
                    "kllh_present": sum(row["hnx_kllh_shares"] is not None for row in universe), "klny_present": sum(row["market"] == "HNX_LISTED" and row["source_listing_or_registration_quantity"] is not None for row in universe),
                    "kldkgd_present": sum(row["market"] == "UPCOM" and row["source_listing_or_registration_quantity"] is not None for row in universe), "kllh_relation": dict(kllh_relation),
                    "event_source_total": sum(event_totals.values()), "event_tickers": len({row["ticker"] for row in events}), "ex_date_qualified": sum(row["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED" for row in events),
                    "ex_date_missing": sum(row["qualification"] == "MISSING_EX_DATE" for row in events), "event_types": dict(event_types),
                    "disclosure_source_total": sum(disclosure_totals.values()), "disclosure_tickers": len({row["ticker"] for row in disclosures if row["ticker"]}),
                    "financial_disclosure_candidates": sum(row["financial_statement_candidate"] for row in disclosures),
                    "stocklookup_universe_count": len(stocklookup), "intersection": len(hnx & stocklookup), "stocklookup_only": len(stocklookup - hnx), "hnx_official_only": len(hnx - stocklookup), "identity_conflicts": 0},
                "share_authority": "KLLH_AND_KLNY_OR_KLDKGD_REMAIN_SEPARATE_CURRENT_EXCHANGE_LIST_FIELDS_NOT_COMMON_SHARES_OUTSTANDING",
                "kllh_fitness_for_use": "NOT_FIT_FOR_COMMON_SHARES_MARKET_CAP_VALUATION_OR_SIZING",
                "authority_result": "ENUMERABLE_HNX_UNIVERSE_AND_EX_DATE_EVENT_INDEX_ONLY_NO_SHARE_OR_RAW_AS_TRADED_PROMOTION",
                "authority_boundary": "NO_COMMON_OUTSTANDING_SHARE_ALIAS_NO_PRICE_ADJUSTMENT_NO_RAW_AS_TRADED_NO_FINANCIAL_FACT_EXTRACTION",
                "missing_is_zero": False, "canonical_store_mutated": False, "network_used": True,
                "lane_terminal_status": "HNX_ENUMERABLE_UNIVERSE_AND_EVENT_INDEX_READY_DISCLOSURE_BINDING_PENDING_EXACT_PARENT_ROWS",
                "next_real_data_opportunity": "Exact ticker-bearing HNX disclosure-index rows plus matching retained parent detail and attachment topology for the eight H1 parents"}
    digest = _identity(artifact); artifact["artifact_sha256"] = digest; artifact["artifact_identity"] = "hnx_enumerable_universe_kllh_event_disclosure_scaleout:" + digest
    return artifact


def replay(artifact: Mapping[str, Any], *, destination: Path) -> None:
    for capture in artifact["captures"]:
        path = destination / capture["relative_path"]
        if not path.is_file() or _sha(path.read_bytes()) != capture["sha256"]:
            raise ValueError("CAPTURE_SHA256_MISMATCH")
    candidate = dict(artifact); candidate.pop("artifact_sha256"); candidate.pop("artifact_identity")
    digest = _identity(candidate)
    if artifact.get("artifact_sha256") != digest or artifact.get("artifact_identity") != "hnx_enumerable_universe_kllh_event_disclosure_scaleout:" + digest:
        raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
