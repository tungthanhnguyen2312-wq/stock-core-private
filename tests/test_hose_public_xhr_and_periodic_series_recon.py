from __future__ import annotations

import json
from pathlib import Path

from hose_public_xhr_and_periodic_series_recon import PUBLIC_XHR, _disclosure_urls, build, replay


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
    expected_surfaces = set(PUBLIC_XHR) | set(_disclosure_urls("2026-08-24"))
    assert expected_surfaces == {capture["surface"] for capture in artifact["captures"]}


def test_as_of_date_defaults_to_today_and_accepts_explicit_override(tmp_path: Path):
    """Regression guard for OFFICIAL_CORPORATE_EVENT_INCREMENTAL_ACQUISITION_AND_FRESHNESS_V1:
    AS_OF_DATE used to be a permanently frozen 2026-08-24 module constant, so every disclosure
    fetch stayed capped at that literal date forever regardless of when the acquisition actually
    ran. build() now defaults to the real current Vietnam civil date and still accepts an explicit
    override for deterministic/historical replay."""
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": {f"T{i:04}": {} for i in range(1683)}}), encoding="utf-8")
    hnx = tmp_path / "hnx.json"
    hnx.write_text(json.dumps({"datasets": {"hnx_official_equity_universe/v1": [{"ticker": "T0000"}]}}), encoding="utf-8")
    seen_urls: list[str] = []

    def _tracking_response(url: str):
        seen_urls.append(url)
        return _response(url)

    explicit = build(destination=tmp_path / "explicit", stocklookup_universe=universe, hnx_universe=hnx,
                      fetcher=_tracking_response, as_of_date="2026-01-15")
    assert explicit["as_of_date"] == "2026-01-15"
    assert any("endDate=2026-01-15" in url for url in seen_urls)

    default = build(destination=tmp_path / "default", stocklookup_universe=universe, hnx_universe=hnx, fetcher=_response)
    from vn_time import vn_today
    assert default["as_of_date"] == vn_today()
