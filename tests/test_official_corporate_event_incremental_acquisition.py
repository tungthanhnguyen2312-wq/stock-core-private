from __future__ import annotations

import json
from pathlib import Path

import pytest

import hnx_enumerable_universe_kllh_event_disclosure_scaleout as hnx_module
import official_corporate_event_incremental_acquisition as incremental

ROOT = Path(__file__).resolve().parents[1]


def _stocklookup_universe(root: Path) -> None:
    ops = root / "operations-review" / f"{incremental.BREADTH_FOUNDATION_PREFIX}20260904"
    ops.mkdir(parents=True, exist_ok=True)
    payload = {"records": {f"T{i:04}": {} for i in range(1683)}}
    (ops / "current_market_universe_breadth_foundation_artifact.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _hnx_row(cells: list[str]) -> str:
    tds = "".join(f"<td>{cell}</td>" for cell in cells)
    return f"<tr>{tds}</tr>"


def _hnx_table(total: int, rows: list[list[str]]) -> bytes:
    body = "".join(_hnx_row(row) for row in rows)
    html = f"<html>Tổng số {total} bản ghi<table><tbody>{body}</tbody></table></html>"
    return html.encode("utf-8")


def _make_hnx_fetch(*, hpg_ex_date: str = "05/09/2026"):
    def _fake_hnx_fetch(url: str, *, body=None):
        now = "2026-09-05T00:00:00Z"

        def _ok(data: bytes) -> dict:
            return {"requested_url": url, "official_url": url, "retrieved_at": now,
                     "http_status": 200, "content_type": "text/html", "data": data}

        if "UC_Issuer" in url:
            return _ok(_hnx_table(1, [["0", "BBB", "Issuer B", "01/01/2020", "500000", "400000"]]))
        if "ListSearch_Datas" in url:
            return _ok(_hnx_table(1, [["0", "HPG", "Issuer A", "Sector", "01/01/2020", "1000000", "900000"]]))
        if "NextPageTinCPNY_LTHQ" in url:
            return _ok(_hnx_table(1, [["0", "HPG", hpg_ex_date, "01/09/2026", "", "trả cổ tức bằng tiền"]]))
        if "NextPageTHQUpCoM" in url:
            return _ok(_hnx_table(0, []))
        if "NextPageTinCPNY" in url:
            return _ok(_hnx_table(1, [["0", "01/09/2026", "HPG", "Báo cáo tài chính Q2", "x"]]))
        if "NextPageTinUpCoM" in url:
            return _ok(_hnx_table(0, []))
        return _ok(b"<html>landing</html>")

    return _fake_hnx_fetch


def _hose_response(url: str) -> dict:
    if "stock?page" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "HPG", "name": "Hoa Phat", "isin": "VNHPG",
                                                       "securitiesType": 1, "listingStatusId": 11,
                                                       "listingVolume": "100", "outStanding": "90"}],
                                            "paging": {"totalCount": 1}}}
    elif "listing-dashboard" in url:
        data = {"success": True, "data": {"securitiesTotal": 1}}
    elif "indicies/0" in url:
        data = {"success": True, "data": [{"id": 5, "name": "VN30"}]}
    elif "indicies/5/" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "HPG"}], "paging": {"totalCount": 1}}}
    elif "foreign" in url:
        data = {"success": True, "data": {"list": [{"reportDate": 1, "totalRoom": 2, "currentRoom": 3}]}}
    elif "market/securities/HPG" in url:
        data = {"success": True, "data": {"mainValue": 4}}
    elif "dividend" in url:
        data = {"success": True, "data": [{"type": "cash", "transNoRightDate": "2026-09-10", "lastRegDate": "2026-09-08"}]}
    elif "news/securities/2458" in url:
        data = {"success": True, "data": {"list": [{"id": 2, "title": "HPG"}]}}
    elif "news/securitiesType" in url:
        data = {"success": True, "data": {"list": [{"id": 3, "title": "Market"}]}}
    elif "NewsFeed" in url:
        return {"requested_url": url, "official_url": url, "retrieved_at": "2026-09-05T00:00:00Z",
                "http_status": 200, "content_type": "application/rss+xml", "data": b"<rss/>"}
    else:
        data = {"success": True, "data": {}}
    return {"requested_url": url, "official_url": url, "retrieved_at": "2026-09-05T00:00:00Z",
            "http_status": 200, "content_type": "application/json", "data": json.dumps(data).encode()}


def _acquire(tmp_path, monkeypatch, *, session: str, hpg_ex_date: str = "05/09/2026"):
    monkeypatch.setattr(hnx_module, "fetch", _make_hnx_fetch(hpg_ex_date=hpg_ex_date))
    return incremental.acquire(tmp_path, session=session, hose_fetcher=_hose_response)


@pytest.fixture(autouse=True)
def _universe(tmp_path):
    _stocklookup_universe(tmp_path)


# --- 1. incremental acquisition happy path ---

def test_acquire_succeeds_and_retains_a_session_manifest(tmp_path, monkeypatch):
    attempt = _acquire(tmp_path, monkeypatch, session="2026-09-05")
    assert attempt["disposition"] == incremental.SUCCESS
    assert attempt["acquisition_session"] == "2026-09-05"
    assert attempt["prior_session_referenced"] is None
    assert attempt["any_change_since_prior_success"] is True
    manifest_path = tmp_path / incremental.SESSIONS_RELATIVE / "2026-09-05" / incremental.ATTEMPT_FILENAME
    assert manifest_path.is_file()


def test_acquire_refuses_to_run_twice_for_the_same_session(tmp_path, monkeypatch):
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    with pytest.raises(incremental.IncrementalAcquisitionError, match="ACQUISITION_SESSION_ALREADY_RETAINED"):
        _acquire(tmp_path, monkeypatch, session="2026-09-05")


def test_a_failed_session_may_be_retried_but_a_successful_one_may_not(tmp_path, monkeypatch):
    """A failure is not retained evidence of anything but an outage, so the same calendar session
    may be retried once the underlying condition clears -- unlike a SUCCESS, which is real,
    retained evidence and must never be silently redone."""
    monkeypatch.setattr(hnx_module, "fetch", _network_outage)
    first = incremental.acquire(tmp_path, session="2026-09-05", hose_fetcher=_hose_response)
    assert first["disposition"] == incremental.FAILURE
    second = _acquire(tmp_path, monkeypatch, session="2026-09-05")
    assert second["disposition"] == incremental.SUCCESS
    with pytest.raises(incremental.IncrementalAcquisitionError, match="ACQUISITION_SESSION_ALREADY_RETAINED"):
        _acquire(tmp_path, monkeypatch, session="2026-09-05")


# --- 2. immutable retention / no overwrite ---

def test_raw_captures_are_content_addressed_and_never_overwritten(tmp_path, monkeypatch):
    attempt = _acquire(tmp_path, monkeypatch, session="2026-09-05")
    raw_root = tmp_path / incremental.RAW_STORE_RELATIVE
    paths_before = sorted(p for p in raw_root.rglob("*") if p.is_file())
    assert paths_before
    contents_before = {p: p.read_bytes() for p in paths_before}
    # A second acquisition (different session) over identical source content must reuse the same
    # raw files byte-for-byte, never rewrite them.
    _acquire(tmp_path, monkeypatch, session="2026-09-06")
    for path, data in contents_before.items():
        assert path.read_bytes() == data


# --- 3. same-content idempotence ---

def test_identical_evidence_across_sessions_is_classified_unchanged_reused(tmp_path, monkeypatch):
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    second = _acquire(tmp_path, monkeypatch, session="2026-09-06")
    assert second["any_change_since_prior_success"] is False
    assert second["hnx_change_classification"]["any_change"] is False
    assert second["hose_change_classification"]["any_change"] is False
    assert second["hnx_change_classification"]["new_or_changed_count"] == 0


def test_compare_captures_is_a_pure_function_provable_from_fixtures_alone(tmp_path):
    """Mission Section 13: idempotence must be provable without any network acquisition."""
    prior = [{"surface": "a", "page": 1, "sha256": "x"}, {"surface": "b", "page": None, "sha256": "y"}]
    identical = [{"surface": "a", "page": 1, "sha256": "x"}, {"surface": "b", "page": None, "sha256": "y"}]
    result = incremental.compare_captures(prior, identical)
    assert result["any_change"] is False
    assert result["unchanged_count"] == 2
    assert result["new_or_changed_count"] == 0


# --- 4. changed-content versioning ---

def test_changed_source_content_is_retained_as_a_new_version_not_an_overwrite(tmp_path, monkeypatch):
    first = _acquire(tmp_path, monkeypatch, session="2026-09-05", hpg_ex_date="05/09/2026")
    second = _acquire(tmp_path, monkeypatch, session="2026-09-06", hpg_ex_date="20/09/2026")
    assert second["any_change_since_prior_success"] is True
    assert second["hnx_change_classification"]["any_change"] is True
    # the OLD raw capture for the rights surface must still be present and unmutated (append-only)
    first_hnx_rights = next(c for c in first["hnx_captures"] if c["surface"] == "hnx_listed_rights")
    second_hnx_rights = next(c for c in second["hnx_captures"] if c["surface"] == "hnx_listed_rights")
    assert first_hnx_rights["sha256"] != second_hnx_rights["sha256"]
    raw_root = tmp_path / incremental.RAW_STORE_RELATIVE
    assert (raw_root / first_hnx_rights["relative_path"]).is_file()
    assert (raw_root / second_hnx_rights["relative_path"]).is_file()


def test_compare_captures_pure_function_detects_a_changed_hash(tmp_path):
    prior = [{"surface": "a", "page": 1, "sha256": "x"}]
    changed = [{"surface": "a", "page": 1, "sha256": "z"}]
    result = incremental.compare_captures(prior, changed)
    assert result["any_change"] is True
    assert result["per_surface_page"]["a:1"] == incremental.CHANGED_NEW_VERSION


# --- 5. acquisition failure fail-closed ---

def _network_outage(url: str, *, body=None):
    """Simulates what hnx_module.fetch() itself returns on a real network failure (its own
    try/except already catches the raw exception and reports http_status=None), so build()'s own
    existing ``if ... != 200: raise ValueError(...)`` fail-closed check is what this exercises --
    not a bypass of that layer."""
    return {"requested_url": url, "official_url": url, "retrieved_at": "2026-09-05T00:00:00Z",
            "http_status": None, "content_type": None, "data": b"", "error": "URLError"}


def test_acquisition_failure_is_retained_explicitly_not_silently_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(hnx_module, "fetch", _network_outage)
    attempt = incremental.acquire(tmp_path, session="2026-09-05", hose_fetcher=_hose_response)
    assert attempt["disposition"] == incremental.FAILURE
    assert attempt["error_type"] == "ValueError"  # hnx_module.build()'s own fail-closed fetch check
    assert "LIST_LANDING_FETCH_FAILED" in attempt["error_message"]
    manifest_path = tmp_path / incremental.SESSIONS_RELATIVE / "2026-09-05" / incremental.ATTEMPT_FILENAME
    assert _load_json(manifest_path)["disposition"] == incremental.FAILURE


def test_failed_session_is_never_selected_as_latest_successful(tmp_path, monkeypatch):
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    monkeypatch.setattr(hnx_module, "fetch", _network_outage)
    incremental.acquire(tmp_path, session="2026-09-06", hose_fetcher=_hose_response)
    latest = incremental.latest_successful_session(tmp_path)
    assert latest["acquisition_session"] == "2026-09-05"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- 6. latest snapshot selection ---

def test_latest_successful_session_resolves_the_most_recent_success(tmp_path, monkeypatch):
    _acquire(tmp_path, monkeypatch, session="2026-09-04")
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    latest = incremental.latest_successful_session(tmp_path)
    assert latest["acquisition_session"] == "2026-09-05"


def test_latest_successful_session_is_none_when_nothing_retained(tmp_path):
    assert incremental.latest_successful_session(tmp_path) is None


# --- 7. canonical current_official_event_context materialization ---

def test_materialize_current_official_event_context_from_latest_session(tmp_path, monkeypatch):
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    official_universe_path = (
        ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )
    result = incremental.materialize_current_official_event_context(
        tmp_path, official_universe_path=official_universe_path,
    )
    assert result["acquisition_session"] == "2026-09-05"
    written = _load_json(tmp_path / result["output_path"])
    assert written["research_session"] == "2026-09-05"
    assert written["contract_version"] == "current_official_event_context/v1"
    # HPG's HNX- and HOSE-sourced rights events must both be present with strict temporal-field
    # separation preserved (record_date is never collapsed onto ex_date).
    hpg = written["records"]["HPG"]
    assert len(hpg["events"]) >= 2
    for event in hpg["events"]:
        assert event["record_date"] != event.get("ex_date") or event.get("ex_date") is None


def test_materialize_writes_to_the_directory_the_latest_pointer_resolver_scans_for(tmp_path, monkeypatch):
    import daily_session_level2_package as level2

    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    official_universe_path = (
        ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )
    incremental.materialize_current_official_event_context(tmp_path, official_universe_path=official_universe_path)
    paths = level2.session_artifact_paths(tmp_path, "2026-09-05")
    assert paths["official_event_context"].is_file()
    assert paths["official_event_context"].parent.name == "current-official-event-context-integration-v1-20260905"


def test_materialize_raises_without_a_successful_session(tmp_path):
    with pytest.raises(incremental.IncrementalAcquisitionError, match="NO_SUCCESSFUL_ACQUISITION_SESSION_RETAINED"):
        incremental.materialize_current_official_event_context(tmp_path)


def test_materialize_rejects_an_unsuccessful_or_unknown_session(tmp_path, monkeypatch):
    monkeypatch.setattr(hnx_module, "fetch", _network_outage)
    incremental.acquire(tmp_path, session="2026-09-05", hose_fetcher=_hose_response)
    with pytest.raises(incremental.IncrementalAcquisitionError, match="ACQUISITION_SESSION_NOT_SUCCESSFUL"):
        incremental.materialize_current_official_event_context(tmp_path, acquisition_session="2026-09-05")
    with pytest.raises(incremental.IncrementalAcquisitionError, match="ACQUISITION_SESSION_NOT_SUCCESSFUL"):
        incremental.materialize_current_official_event_context(tmp_path, acquisition_session="2026-01-01")


# --- 8. genuine historical temporal replay: zero future-event leak across two real sessions ---

def test_earlier_session_materialization_never_sees_a_later_sessions_new_event(tmp_path, monkeypatch):
    """The strongest available proof for mission Sections 14-15: acquire an earlier session with
    one HPG rights event, then a later session where that event's own ex_date has moved (the kind
    of change a real re-acquisition could genuinely observe). Materializing the EARLIER session
    explicitly must reproduce exactly what was retained then -- never the later session's own
    updated date -- because it is built from that session's own retained artifacts, not "latest"."""
    official_universe_path = (
        ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )
    _acquire(tmp_path, monkeypatch, session="2026-08-25", hpg_ex_date="20/08/2026")
    _acquire(tmp_path, monkeypatch, session="2026-09-04", hpg_ex_date="10/09/2026")

    earlier = incremental.materialize_current_official_event_context(
        tmp_path, acquisition_session="2026-08-25", official_universe_path=official_universe_path,
    )
    later = incremental.materialize_current_official_event_context(
        tmp_path, acquisition_session="2026-09-04", official_universe_path=official_universe_path,
    )
    earlier_written = _load_json(tmp_path / earlier["output_path"])
    later_written = _load_json(tmp_path / later["output_path"])
    assert earlier_written["research_session"] == "2026-08-25"
    assert later_written["research_session"] == "2026-09-04"

    earlier_hnx_ex_dates = {e["ex_date"] for e in earlier_written["records"]["HPG"]["events"] if e["source"] == "hnx_official_rights_event_index/v1"}
    later_hnx_ex_dates = {e["ex_date"] for e in later_written["records"]["HPG"]["events"] if e["source"] == "hnx_official_rights_event_index/v1"}
    assert earlier_hnx_ex_dates == {"2026-08-20"}
    assert later_hnx_ex_dates == {"2026-09-10"}
    assert "2026-09-10" not in earlier_hnx_ex_dates  # the later session's own date never leaks backward


# --- 9. downstream pass-through: the canonical Daily pipeline picks up the fresh artifact ---

def test_downstream_current_corporate_event_context_consumes_the_freshly_materialized_artifact(tmp_path, monkeypatch):
    """Downstream pass-through proof (mission Section 16): the very next consumer,
    current_corporate_event_context.build_artifact() -- the same function canonical_post_close_
    pipeline._corporate_event_context() calls in production (fixed last milestone) -- must accept
    this module's freshly materialized official_event_context artifact directly, with zero shape
    changes required on either side."""
    import current_corporate_event_context as event_context_module

    official_universe_path = (
        ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )
    _acquire(tmp_path, monkeypatch, session="2026-09-05")
    result = incremental.materialize_current_official_event_context(tmp_path, official_universe_path=official_universe_path)
    official_event_context = _load_json(tmp_path / result["output_path"])
    official_universe = _load_json(official_universe_path)

    downstream = event_context_module.build_artifact(
        official_universe=official_universe, official_event_context=official_event_context,
        research_session="2026-09-05",
    )
    assert downstream["research_session"] == "2026-09-05"
    assert downstream["records"]["HPG"]["events"]
