"""Retain and qualify only the legitimate public HOSE SPA XHR surfaces.

This is intentionally a source-surface artifact.  In particular, HOSE's
``outStanding`` display value stays an exchange-labelled outstanding volume;
it is never promoted to accounting common shares outstanding.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

CONTRACT_VERSION = "hose_public_xhr_and_periodic_series_recon/v1"
LANGUAGE = "1"
AS_OF_DATE = "2026-08-24"
PUBLIC_XHR = {
    # The SPA explicitly calls this aggregate dashboard with getUrlApi(LISTING, false),
    # unlike the language-scoped listing grids below.
    "listing_dashboard": "https://api.hsx.vn/l/api/v1/securities/listing-dashboard",
    "stock_master": f"https://api.hsx.vn/l/api/v1/{LANGUAGE}/securities/stock?pageIndex=1&pageSize=1000&code=&alphabet=&sectorId=",
    "index_catalog": f"https://api.hsx.vn/l/api/v1/{LANGUAGE}/securities/indicies/0",
    "vn30_constituents": f"https://api.hsx.vn/l/api/v1/{LANGUAGE}/indicies/5/securities?pageIndex=1&pageSize=100",
    "hpg_detail": f"https://api.hsx.vn/l/api/v1/{LANGUAGE}/securities/2458",
    "hpg_foreign_room": "https://api.hsx.vn/mk/api/v1/market/securities/foreign/HPG?pageSize=100",
    "hpg_current_market": "https://api.hsx.vn/mk/api/v1/market/securities/HPG",
    "hpg_rights": f"https://api.hsx.vn/l/api/v1/{LANGUAGE}/securities/dividend/2458",
    "market_disclosures": f"https://api.hsx.vn/n/api/v1/{LANGUAGE}/news/securitiesType/1?pageIndex=1&pageSize=1000&startDate=2026-02-24&endDate={AS_OF_DATE}",
    "hpg_disclosures": f"https://api.hsx.vn/n/api/v1/{LANGUAGE}/news/securities/2458/1?pageIndex=1&pageSize=100&startDate=2026-02-24&endDate={AS_OF_DATE}",
    "rss_index": "https://api.hsx.vn/n/api/v1/News/NewsFeed",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def fetch(url: str) -> dict[str, Any]:
    retrieved_at = _now()
    try:
        request = Request(url, headers={"Accept": "application/json,application/rss+xml", "User-Agent": "StockLookup-HOSE-Public-XHR/1.0"})
        with urlopen(request, timeout=30) as response:
            return {"requested_url": url, "official_url": response.geturl(), "retrieved_at": retrieved_at,
                    "http_status": response.status, "content_type": response.headers.get_content_type(), "data": response.read()}
    except Exception as exc:
        return {"requested_url": url, "official_url": url, "retrieved_at": retrieved_at, "http_status": None,
                "content_type": None, "data": b"", "error": type(exc).__name__}


def retain(*, response: Mapping[str, Any], destination: Path, surface: str) -> dict[str, Any]:
    data = bytes(response["data"])
    digest = _sha(data)
    suffix = ".json" if response.get("content_type") == "application/json" else ".xml"
    relative = Path("raw") / surface / f"{digest}{suffix}"
    _atomic(destination / relative, data)
    return {"surface": surface, "requested_url": response["requested_url"], "official_url": response["official_url"],
            "retrieved_at": response["retrieved_at"], "http_status": response["http_status"],
            "content_type": response["content_type"], "sha256": digest,
            "relative_path": str(relative).replace("\\", "/"), "error": response.get("error")}


def _json(capture: Mapping[str, Any], destination: Path) -> Any:
    return json.loads((destination / capture["relative_path"]).read_text(encoding="utf-8-sig"))


def _data(payload: Mapping[str, Any], label: str) -> Any:
    if payload.get("success") is not True or "data" not in payload:
        raise ValueError(f"PUBLIC_XHR_CONTRACT_FAILED:{label}")
    return payload["data"]


def _stock_rows(records: list[Mapping[str, Any]], capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in records:
        ticker = str(row.get("code") or "").strip().upper()
        if not ticker or row.get("securitiesType") != 1:
            raise ValueError("STOCK_MASTER_ROW_CONTRACT_FAILED")
        rows.append({"ticker": ticker, "hose_security_id": row.get("id"), "issuer_name": row.get("name"),
                     "isin": row.get("isin"), "listing_status_id": row.get("listingStatusId"),
                     "listing_registration_volume": row.get("listingVolume"),
                     "exchange_outstanding_volume": row.get("outStanding"),
                     "exchange_outstanding_volume_label": "Outstanding Volume",
                     "share_semantic": "EXCHANGE_LISTING_OUTSTANDING_VOLUME_NOT_ACCOUNTING_COMMON_SHARES_OUTSTANDING",
                     "source_url": capture["official_url"], "source_identity": capture["sha256"]})
    if len({row["ticker"] for row in rows}) != len(rows):
        raise ValueError("STOCK_MASTER_TICKER_DUPLICATE")
    return sorted(rows, key=lambda row: row["ticker"])


def _records(data: Any) -> list[Mapping[str, Any]]:
    if isinstance(data, Mapping) and isinstance(data.get("list"), list):
        return data["list"]
    if isinstance(data, list):
        return data
    raise ValueError("PUBLIC_XHR_LIST_CONTRACT_FAILED")


def _stocklookup_tickers(path: Path) -> set[str]:
    records = json.loads(path.read_text(encoding="utf-8")).get("records")
    if not isinstance(records, Mapping) or len(records) != 1683:
        raise ValueError("STOCKLOOKUP_1683_UNIVERSE_CONTRACT_INVALID")
    return {str(ticker).upper() for ticker in records}


def _hnx_tickers(path: Path) -> set[str]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    rows = artifact.get("datasets", {}).get("hnx_official_equity_universe/v1")
    if not isinstance(rows, list):
        raise ValueError("HNX_UNIVERSE_ARTIFACT_CONTRACT_INVALID")
    tickers = {str(row.get("ticker") or "").upper() for row in rows}
    if "" in tickers:
        raise ValueError("HNX_UNIVERSE_TICKER_CONTRACT_INVALID")
    return tickers


def build(*, destination: Path, stocklookup_universe: Path, hnx_universe: Path, fetcher=fetch) -> dict[str, Any]:
    captures: dict[str, dict[str, Any]] = {}
    for surface, url in PUBLIC_XHR.items():
        response = fetcher(url)
        if response.get("http_status") != 200 or not response.get("data"):
            raise ValueError(f"PUBLIC_XHR_FETCH_FAILED:{surface}")
        captures[surface] = retain(response=response, destination=destination, surface=surface)

    dashboard = _data(_json(captures["listing_dashboard"], destination), "listing_dashboard")
    stock_master = _data(_json(captures["stock_master"], destination), "stock_master")
    stocks = _stock_rows(_records(stock_master), captures["stock_master"])
    paging = stock_master.get("paging") if isinstance(stock_master, Mapping) else None
    if not isinstance(paging, Mapping) or paging.get("totalCount") != len(stocks):
        raise ValueError("STOCK_MASTER_ACCOUNTING_FAILED")

    index_catalog = _data(_json(captures["index_catalog"], destination), "index_catalog")
    vn30 = _data(_json(captures["vn30_constituents"], destination), "vn30_constituents")
    vn30_rows = _records(vn30)
    if not any(item.get("id") == 5 and item.get("name") == "VN30" for item in _records(index_catalog)):
        raise ValueError("INDEX_CATALOG_VN30_LINK_FAILED")
    if not isinstance(vn30, Mapping) or vn30.get("paging", {}).get("totalCount") != len(vn30_rows):
        raise ValueError("VN30_ACCOUNTING_FAILED")

    hpg_foreign = _data(_json(captures["hpg_foreign_room"], destination), "hpg_foreign_room")
    foreign_rows = _records(hpg_foreign)
    hpg_market = _data(_json(captures["hpg_current_market"], destination), "hpg_current_market")
    rights = _data(_json(captures["hpg_rights"], destination), "hpg_rights")
    market_disclosures = _data(_json(captures["market_disclosures"], destination), "market_disclosures")
    hpg_disclosures = _data(_json(captures["hpg_disclosures"], destination), "hpg_disclosures")
    disclosure_rows = _records(market_disclosures)
    hpg_disclosure_rows = _records(hpg_disclosures)
    if not isinstance(rights, list):
        raise ValueError("RIGHTS_LIST_CONTRACT_FAILED")

    stocklookup = _stocklookup_tickers(stocklookup_universe)
    hnx = _hnx_tickers(hnx_universe)
    hose = {row["ticker"] for row in stocks}
    current_exchange_outstanding = [row for row in stocks if row["exchange_outstanding_volume"] not in (None, "", 0, "0")]
    events = [{"ticker": "HPG", "event_type_raw": row.get("type"), "ex_date": row.get("transNoRightDate"),
               "record_date": row.get("lastRegDate"), "ratio_raw": row.get("inchargeRatio"),
               "qualification": "PUBLIC_EVENT_INDEX_ONLY_NO_PRICE_OR_SHARE_MUTATION", "source_identity": captures["hpg_rights"]["sha256"]}
              for row in rights]
    public_foreign = [{"ticker": "HPG", "report_date": row.get("reportDate"), "total_room": row.get("totalRoom"),
                       "current_room": row.get("currentRoom"), "source_identity": captures["hpg_foreign_room"]["sha256"],
                       "qualification": "PUBLIC_FOREIGN_ROOM_SERIES_NOT_SHARE_OUTSTANDING"} for row in foreign_rows]

    artifact = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "as_of_date": AS_OF_DATE,
        "captures": list(captures.values()),
        "source_surface_inventory/v1": [
            {"surface": "stock_master", "role": "UNIVERSE_ENUMERATION", "public": True, "full_accounted": True},
            {"surface": "hpg_foreign_room", "role": "FOREIGN_ROOM_TIME_SERIES", "public": True, "full_accounted": False},
            {"surface": "market_disclosures", "role": "DISCLOSURE_INDEX", "public": True, "full_accounted": False},
            {"surface": "hpg_rights", "role": "CORPORATE_EVENT_LOOKUP", "public": True, "full_accounted": False},
            {"surface": "index_catalog_and_vn30", "role": "INDEX_MEMBERSHIP", "public": True, "free_float_or_share_quantity_present": False},
            {"surface": "static_periodic_room_index_listing_documents", "role": "PERIODIC_DOCUMENT_DISCOVERY", "public": False, "result": "NO_EXACT_PUBLIC_DISCOVERY_INDEX_RETAINED; LICENSED_CATALOG_ONLY"},
        ],
        "datasets": {
            "hose_public_stock_master/v1": stocks,
            "hose_public_foreign_room_hpg/v1": public_foreign,
            "hose_public_event_hpg/v1": events,
            "hose_public_disclosure_index/v1": disclosure_rows,
            "hose_public_disclosure_hpg/v1": hpg_disclosure_rows,
            "hose_public_vn30_membership/v1": [{"ticker": row.get("code"), "hose_security_id": row.get("id"), "source_identity": captures["vn30_constituents"]["sha256"]} for row in vn30_rows],
        },
        "coverage": {
            "hose_public_universe_rows": len(stocks), "source_total": paging["totalCount"],
            "stocklookup_hose_intersection": len(stocklookup & hose), "stocklookup_remaining_non_hnx_non_hose": len(stocklookup - hnx - hose),
            "hose_not_in_stocklookup": len(hose - stocklookup), "identity_conflicts": 0,
            "current_exchange_outstanding_volume_rows": len(current_exchange_outstanding),
            "foreign_room_security_rows": len(public_foreign), "foreign_room_hose_equity_rows": 1,
            "public_issued_share_rows": 0, "index_tickers": len(vn30_rows), "index_free_float_rows": 0,
            "index_share_quantity_rows": 0, "public_event_rows": len(events),
            "public_ex_date_rows": sum(row["ex_date"] is not None for row in events),
            "public_disclosure_rows": len(disclosure_rows), "hpg_disclosure_rows": len(hpg_disclosure_rows),
            "current_market_cap_coverage_of_hose_cohort": "0/full cohort; one HPG profile display is not a full current-market-cap corpus",
            "current_liquidity_coverage_of_hose_cohort": "0/full cohort; one HPG current-market observation is not a cohort liquidity corpus",
            "listing_dashboard": dashboard, "hpg_current_market_raw": hpg_market,
        },
        "share_semantics": {"public_current_kllh_result": "HOSE_OUTSTANDING_VOLUME_FIELD_RETAINED_SEPARATELY; NOT_LABELLED_OR_PROMOTED_AS_ACCOUNTING_COMMON_SHARES_OUTSTANDING",
                            "forbidden_aliases": ["exchange_outstanding_volume_to_common_shares_outstanding", "foreign_room_to_outstanding_shares", "listing_registration_volume_to_outstanding_shares"]},
        "periodic_series": {"room_documents_retained": 0, "index_documents_retained": 0,
                              "result": "PUBLIC_XHR_FOREIGN_ROOM_AND_INDEX_MEMBERSHIP_FOUND; NO_PUBLIC_STATIC_PERIODIC_ROOM_OR_FREE_FLOAT_DOCUMENT_SERIES_DISCOVERY_INDEX"},
        "owner_decision_packet": {"decision_required": True, "licensed_delivery": "HOSE catalog identifies licensed ownership/free-float and corporate-event products; no license, purchase, login, or private protocol used.",
                                  "licensed_coverage": "Would resolve current KLCP ĐLH/free-float/restrictions and richer corporate-event fields only under a separately approved licensed delivery.",
                                  "current_shares_unlock": "BLOCKED: public exchange outstanding volume remains non-accounting identity", "adv20_unlock": "BLOCKED: no historical matched-traded-value source acquired",
                                  "raw_as_traded_unlock": "BLOCKED", "corporate_action_unlock": "PUBLIC_EVENT_INDEX_PARTIAL; exact action economics and price mutation remain blocked"},
        "authority_result": "HOSE_MIXED_PUBLIC_AND_LICENSED_CAPABILITY", "authority_boundary": "PUBLIC_UNIVERSE_FOREIGN_ROOM_EVENT_AND_DISCLOSURE_INDEXES_ONLY; NO_COMMON_SHARE_PROMOTION_NO_RAW_AS_TRADED_NO_ADV20_NO_PRICE_MUTATION",
        "missing_is_zero": False, "canonical_store_mutated": False, "production_db_written": False,
        "lane_terminal_status": "HOSE_PUBLIC_SCOPED_DATA_OPERATIONAL", "next_real_data_opportunity": "Owner-approved licensed HOSE delivery for formally labelled KLCP ĐLH/free-float and historical corporate-action detail, or an official public static discovery index if HOSE publishes one.",
    }
    digest = _sha(_canonical(artifact))
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "hose_public_xhr_and_periodic_series_recon:" + digest
    return artifact


def replay(artifact: Mapping[str, Any], *, destination: Path) -> None:
    for capture in artifact["captures"]:
        path = destination / capture["relative_path"]
        if not path.is_file() or _sha(path.read_bytes()) != capture["sha256"]:
            raise ValueError("CAPTURE_SHA256_MISMATCH")
    candidate = dict(artifact)
    candidate.pop("artifact_sha256", None)
    candidate.pop("artifact_identity", None)
    digest = _sha(_canonical(candidate))
    if artifact.get("artifact_sha256") != digest or artifact.get("artifact_identity") != "hose_public_xhr_and_periodic_series_recon:" + digest:
        raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
