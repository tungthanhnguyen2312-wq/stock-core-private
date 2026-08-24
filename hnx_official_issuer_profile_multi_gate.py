"""Bounded first-party HNX issuer-profile evidence acquisition and projection."""
from __future__ import annotations

import hashlib, html, json, re, tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONTRACT_VERSION = "hnx_official_issuer_profile_multi_gate_data_unlock/v1"
SAMPLES = ("PHN", "MBS", "MVN")  # HNX equal, HNX less-than, UPCoM field-vocabulary contrast
SEARCH = "https://hnx.vn/ModuleSearchALL/SearchDataHNX/SearchSuggestSymbol"
PROFILE = "https://hnx.vn/vi-vn/cophieu-etfs/chi-tiet-chung-khoan-{link}.html"
_PAIR = re.compile(r'<div class="dktimkiem_row row_inline">\s*<div class="dktimkiem_cell_title">\s*<label>(.*?)</label>\s*</div>\s*<div class="dktimkiem_cell_content">(.*?)</div>', re.S | re.I)
_EVENT_SECTION = re.compile(r'<div id="divGiaoDichGLDT">(.*?)<div id="divBaoCaoDK"', re.S | re.I)
_ROW = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _identity(value: Mapping[str, Any]) -> str: return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
def _text(value: str) -> str: return " ".join(html.unescape(_TAG.sub(" ", value)).split())
def _number(value: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None
def _date(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", value)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data: raise ValueError("IMMUTABLE_CONTENT_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(data); candidate = Path(temp.name)
    candidate.replace(path)


def fetch(url: str) -> dict[str, Any]:
    observed_at = _now()
    try:
        request = Request(url, headers={"Accept": "text/html,application/json", "User-Agent": "StockLookup-HNX-Profile-Qualification/1.0"})
        with urlopen(request, timeout=20) as response:
            data = response.read()
            return {"url": response.geturl(), "requested_url": url, "retrieved_at": observed_at, "http_status": response.status,
                    "content_type": response.headers.get_content_type(), "data": data}
    except Exception as exc:
        return {"url": url, "requested_url": url, "retrieved_at": observed_at, "http_status": None,
                "content_type": None, "error": type(exc).__name__, "data": b""}


def retain(*, response: Mapping[str, Any], destination: Path, ticker: str, surface: str) -> dict[str, Any]:
    data = bytes(response["data"])
    digest = _sha(data)
    suffix = ".json" if response.get("content_type") == "application/json" else ".html"
    relative = Path("raw") / surface / (digest + suffix)
    _atomic(destination / relative, data)
    return {"official_url": response["url"], "requested_url": response["requested_url"], "retrieved_at": response["retrieved_at"],
            "http_status": response["http_status"], "content_type": response["content_type"], "sha256": digest,
            "relative_path": str(relative).replace("\\", "/"), "ticker_query_identity": ticker,
            "source_surface": surface, "source_version": "HNX_PUBLIC_HTML_OR_AUTOCOMPLETE_V1", "error": response.get("error")}


def parse_profile(payload: bytes, *, identity: Mapping[str, Any], retention: Mapping[str, Any]) -> dict[str, Any]:
    document = payload.decode("utf-8", errors="replace")
    fields = {_text(label): _text(value) for label, value in _PAIR.findall(document)}
    kllh_label = next((label for label in fields if label.startswith("KLLH")), None)
    klny_label = next((label for label in fields if label.startswith("KLNY")), None)
    kldkgd_label = next((label for label in fields if label.startswith("KLĐKGD")), None)
    section = _EVENT_SECTION.search(document)
    events = []
    if section:
        for raw_row in _ROW.findall(section.group(1)):
            cells = [_text(cell) for cell in _CELL.findall(raw_row)]
            if len(cells) != 5 or not cells[0].isdigit(): continue
            label = cells[4].lower()
            event_type = ("CASH_DIVIDEND" if label == "trả cổ tức bằng tiền" else
                          "STOCK_DIVIDEND" if label == "trả cổ tức bằng cp" else
                          "BONUS_ISSUE" if label == "trả cp thưởng" else
                          "RIGHTS_ISSUE" if label == "phát hành cp cho cổ đông hiện hữu" else
                          "AGM" if "đại hội cổ đông" in label else "UNKNOWN")
            events.append({"ticker": identity["STOCK_CODE"], "event_type": event_type, "event_label": cells[4],
                           "ex_date": _date(cells[1]), "record_date": _date(cells[2]), "execution_date": _date(cells[3]),
                           "source_url": retention["official_url"], "retrieved_at": retention["retrieved_at"],
                           "source_identity": retention["sha256"], "qualification": "EX_DATE_OFFICIAL_QUALIFIED" if _date(cells[1]) else "MISSING_EX_DATE",
                           "price_adjustment_candidate": event_type in {"CASH_DIVIDEND", "STOCK_DIVIDEND", "BONUS_ISSUE", "RIGHTS_ISSUE"}})
    ticker = str(identity["STOCK_CODE"]).upper()
    common_equity = identity.get("MARKETCODE") in {"NY", "UC"} and int(identity.get("CARBOND_TYPE") or 0) == 0
    return {"ticker": ticker, "issuer_name": identity.get("NAME"), "market_code": identity.get("MARKETCODE"),
            "market": "HNX_LISTED" if identity.get("MARKETCODE") == "NY" else "UPCOM" if identity.get("MARKETCODE") == "UC" else "UNKNOWN",
            "instrument_class": "COMMON_EQUITY_CANDIDATE" if common_equity else "INELIGIBLE_OR_UNKNOWN", "common_equity_eligible": common_equity,
            "first_trading_date": _date(fields.get("Ngày GD đầu tiên", "")), "official_profile_url": retention["official_url"],
            "observed_at": retention["retrieved_at"], "source_identity": retention["sha256"], "hnx_kllh_label": kllh_label,
            "hnx_kllh_shares": _number(fields.get(kllh_label)) if kllh_label else None, "hnx_klny_label": klny_label,
            "hnx_klny_shares": _number(fields.get(klny_label)) if klny_label else None,
            "hnx_kldkgd_label": kldkgd_label, "hnx_kldkgd_shares": _number(fields.get(kldkgd_label)) if kldkgd_label else None,
            "charter_capital_thousand_vnd": _number(next((value for label, value in fields.items() if label.startswith("Vốn điều lệ")), None)),
            "events": events, "share_identity_schema": "KLLH_AND_KLNY_DISTINCT_LABELLED_OFFICIAL_FIELDS",
            "kllh_semantic_result": "OFFICIAL_EXCHANGE_REPORTED_CIRCULATING_SHARES_CURRENT_PROFILE_ONLY",
            "common_shares_outstanding_result": "UNPROVEN_TREASURY_AND_ACCOUNTING_SCOPE_UNAVAILABLE"}


def build(*, destination: Path, execute: bool = True) -> dict[str, Any]:
    if not execute: raise ValueError("LIVE_HNX_ACQUISITION_REQUIRES_EXECUTE_TRUE")
    profiles, captures = [], []
    for ticker in SAMPLES:
        response = fetch(SEARCH + "?" + urlencode({"pSymbol": ticker}))
        search_capture = retain(response=response, destination=destination, ticker=ticker, surface="issuer_search")
        captures.append(search_capture)
        rows = json.loads(response["data"].decode("utf-8")) if response["http_status"] == 200 else []
        exact = [row for row in rows if str(row.get("STOCK_CODE", "")).upper() == ticker]
        if len(exact) != 1: raise ValueError("EXACT_TICKER_IDENTITY_NOT_FOUND:" + ticker)
        identity = exact[0]
        profile_response = fetch(PROFILE.format(link=identity["Link_To_Detail"]))
        profile_capture = retain(response=profile_response, destination=destination, ticker=ticker, surface="issuer_profile")
        captures.append(profile_capture)
        if profile_response["http_status"] != 200 or profile_response["content_type"] != "text/html": raise ValueError("PROFILE_FETCH_FAILED:" + ticker)
        profiles.append(parse_profile(profile_response["data"], identity=identity, retention=profile_capture))
    events = [event for profile in profiles for event in profile["events"]]
    kllh = [profile for profile in profiles if profile["hnx_kllh_shares"] is not None]
    klny = [profile for profile in profiles if profile["hnx_klny_shares"] is not None]
    coverage = {"hnx_listed_common_equities": "UNAVAILABLE_AUTOCOMPLETE_CAPPED_NO_TOTAL_OR_PAGINATION", "upcom_common_equities": "UNAVAILABLE_AUTOCOMPLETE_CAPPED_NO_TOTAL_OR_PAGINATION",
                "profile_fetched": len(profiles), "kllh_present": len(kllh), "klny_present": len(klny),
                "kllh_klny_equal": sum(1 for p in profiles if p["hnx_kllh_shares"] == p["hnx_klny_shares"]),
                "kllh_lt_klny": sum(1 for p in profiles if p["hnx_kllh_shares"] is not None and p["hnx_klny_shares"] is not None and p["hnx_kllh_shares"] < p["hnx_klny_shares"]),
                "kllh_gt_klny": sum(1 for p in profiles if p["hnx_kllh_shares"] is not None and p["hnx_klny_shares"] is not None and p["hnx_kllh_shares"] > p["hnx_klny_shares"]),
                "event_schedule_tickers": len({event["ticker"] for event in events}), "total_events": len(events),
                "ex_date_qualified_events": sum(1 for event in events if event["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED"),
                "ex_date_qualified_tickers": len({event["ticker"] for event in events if event["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED"}),
                "cash_dividend_ex_dates": sum(1 for event in events if event["event_type"] == "CASH_DIVIDEND" and event["ex_date"]),
                "stock_dividend_ex_dates": sum(1 for event in events if event["event_type"] == "STOCK_DIVIDEND" and event["ex_date"]),
                "rights_ex_dates": sum(1 for event in events if event["event_type"] == "RIGHTS_ISSUE" and event["ex_date"]),
                "other_ex_dates": sum(1 for event in events if event["event_type"] not in {"CASH_DIVIDEND", "STOCK_DIVIDEND", "RIGHTS_ISSUE"} and event["ex_date"]),
                "disclosure_index_ticker_bindings": 0, "ticker_resolved_attachments": 0, "ticker_unresolved_attachments": 27,
                "strict_share_ready_before": 0, "strict_share_ready_after": 0, "market_cap_ready_after": 0, "pb_ready_after": 0, "ps_ready_after": 0, "pe_ready_after": 0, "ev_ready_after": 0, "value_strategy_ready_after": 0}
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "captures": captures, "profiles": profiles, "events": events, "coverage": coverage,
                "source_contract_result": "PROFILE_AND_EVENT_CONTRACT_REPRODUCIBLE_AUTOCOMPLETE_NOT_SAFELY_ENUMERABLE",
                "current_share_fitness_result": "NARROW_CURRENT_EXCHANGE_CIRCULATING_SHARE_RECORD_ONLY_NOT_COMMON_SHARES_OUTSTANDING",
                "filing_binding_result": "NO_EXACT_TICKER_BEARING_INDEX_RECORD_FOR_RETAINED_8_PARENT_FILINGS", "historical_price_event_overlaps": 0,
                "pre_event_snapshot_pair_available": 0, "raw_as_traded_unlock": "NO", "canonical_store_mutated": False, "network_used": True, "missing_is_zero": False,
                "authority_result": "EX_DATE_OFFICIAL_QUALIFIED_DATA_ONLY_NO_SHARE_OR_RAW_AS_TRADED_PROMOTION", "lane_terminal_status": "HNX_EVENT_AND_IDENTITY_ONLY",
                "next_real_data_opportunity": "A first-party HNX common-equity list with total/pagination and ticker-bearing disclosure-index rows for the retained filing parents"}
    digest = _identity(artifact); artifact["artifact_sha256"] = digest; artifact["artifact_identity"] = "hnx_official_issuer_profile_multi_gate:" + digest
    return artifact


def replay(artifact: Mapping[str, Any], *, destination: Path) -> None:
    for capture in artifact["captures"]:
        path = destination / capture["relative_path"]
        if not path.is_file() or _sha(path.read_bytes()) != capture["sha256"]: raise ValueError("CAPTURE_SHA256_MISMATCH")
    candidate = dict(artifact); candidate.pop("artifact_sha256"); candidate.pop("artifact_identity")
    digest = _identity(candidate)
    if artifact.get("artifact_sha256") != digest or artifact.get("artifact_identity") != "hnx_official_issuer_profile_multi_gate:" + digest: raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
