from __future__ import annotations

import json
from pathlib import Path

from hose_public_xhr_and_periodic_series_recon import PUBLIC_XHR, build, replay


def _response(url: str):
    if "stock?page" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "AAA", "name": "A", "isin": "VNAAA", "securitiesType": 1, "listingStatusId": 11, "listingVolume": "100", "outStanding": "90"}], "paging": {"totalCount": 1}}}
    elif "listing-dashboard" in url:
        data = {"success": True, "data": {"securitiesTotal": 1}}
    elif "indicies/0" in url:
        data = {"success": True, "data": [{"id": 5, "name": "VN30"}]}
    elif "indicies/5/" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "AAA"}], "paging": {"totalCount": 1}}}
    elif "foreign" in url:
        data = {"success": True, "data": {"list": [{"reportDate": 1, "totalRoom": 2, "currentRoom": 3}]}}
    elif "market/securities/HPG" in url:
        data = {"success": True, "data": {"mainValue": 4}}
    elif "dividend" in url:
        data = {"success": True, "data": [{"type": "cash", "transNoRightDate": 1, "lastRegDate": 2}]}
    elif "news/securities/2458" in url:
        data = {"success": True, "data": {"list": [{"id": 2, "title": "HPG"}]}}
    elif "news/securitiesType" in url:
        data = {"success": True, "data": {"list": [{"id": 3, "title": "Market"}]}}
    elif "NewsFeed" in url:
        return {"requested_url": url, "official_url": url, "retrieved_at": "2026-08-24T00:00:00Z", "http_status": 200, "content_type": "application/rss+xml", "data": b"<rss/>"}
    else:
        data = {"success": True, "data": {}}
    return {"requested_url": url, "official_url": url, "retrieved_at": "2026-08-24T00:00:00Z", "http_status": 200, "content_type": "application/json", "data": json.dumps(data).encode()}


def test_public_xhr_snapshot_replays_and_preserves_share_boundary(tmp_path: Path):
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": {f"T{i:04}": {} for i in range(1683)}}), encoding="utf-8")
    hnx = tmp_path / "hnx.json"
    hnx.write_text(json.dumps({"datasets": {"hnx_official_equity_universe/v1": [{"ticker": "T0000"}]}}), encoding="utf-8")
    artifact = build(destination=tmp_path, stocklookup_universe=universe, hnx_universe=hnx, fetcher=_response)
    replay(artifact, destination=tmp_path)
    assert artifact["coverage"]["hose_public_universe_rows"] == 1
    assert artifact["coverage"]["public_issued_share_rows"] == 0
    assert artifact["share_semantics"]["public_current_kllh_result"].startswith("HOSE_OUTSTANDING_VOLUME")
    assert set(PUBLIC_XHR) == {capture["surface"] for capture in artifact["captures"]}
