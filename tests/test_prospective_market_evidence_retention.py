import copy
import json
from datetime import datetime

import pytest

import prospective_market_snapshot_contract as contract
import prospective_market_evidence_retention as retention

SESSION = "2026-10-01"


def snapshot(**changes):
    bar = {"session": SESSION, "retrieved_at": SESSION + "T09:00:00Z", "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
           "open": 10., "high": 12., "low": 9., "close": 11., "volume": 100, "exchange": "HOSE",
           "price_unit": "VND", "volume_unit": "SHARES", "volume_basis": "AS_REPORTED"}
    bar.update(changes)
    return {"resolved_completed_session": SESSION, "snapshot_identity": "exact:test", "records": {"AAA": {"observations": [bar]}}}


def official(**changes):
    row = {"ticker": "AAA", "session": SESSION, "exchange": "HOSE", "provider": "HOSE",
           "source_id": "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT", "ohlc": [10.,12.,9.,11.],
           "price_unit": "VND", "receipt_identity": "official:x", "knowledge_available_at": SESSION + "T08:30:00Z"}
    row.update(changes)
    return {"AAA": row}


@pytest.mark.parametrize("change", [
    {"ohlc": []}, {"ohlc": [10.]}, {"ohlc": [10.,12.,9.,11.,11.]}, {"ohlc": [10.,12.,9.,float('nan')]},
    {"ohlc": [True,12.,9.,11.]}, {"ohlc": ['10',12.,9.,11.]}, {"ohlc": [10.,12.,9.,float('inf')]},
    {"ticker": "BBB"}, {"session": "2026-09-30"}, {"exchange": "HNX"}, {"exchange": "UPCOM"},
    {"price_unit": "UNKNOWN"}, {"price_unit": "VND_1000"}, {"provider": "DNSE"}, {"source_id": "UNADMITTED"},
    {"receipt_identity": None}, {"knowledge_available_at": "2026-10-02T08:00:00Z"},
    {"knowledge_available_at": "2026-10-01T07:00:00Z"},
    {"knowledge_available_at": 123}, {"knowledge_available_at": {"date": "2026-10-01"}},
    {"source_basis_claim": contract.SOURCE_DOCUMENTS_ADJUSTED}])
def test_malformed_or_wrong_scope_official_never_raw(change):
    row = contract.build_session_manifest(snapshot(), session=SESSION, official_series=official(**change))["records"][0]
    assert contract.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in row["qualification"]["allowed_uses"]


@pytest.mark.parametrize("exchange", ["HNX", "UPCOM", None])
def test_hose_agreement_never_generalizes_exchange(exchange):
    row = contract.build_session_manifest(snapshot(exchange=exchange), session=SESSION, official_series=official())["records"][0]
    assert contract.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in row["qualification"]["allowed_uses"]


def test_raw_price_does_not_qualify_volume_or_normalize_lots():
    row = contract.build_session_manifest(snapshot(volume_unit="UNKNOWN"), session=SESSION, official_series=official())["records"][0]
    assert contract.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in row["qualification"]["allowed_uses"]
    assert not row["volume_qualification"]["allowed_uses"]
    row = contract.build_session_manifest(snapshot(volume_unit="LOTS"), session=SESSION)["records"][0]
    assert row["normalized"]["volume_value"]["volume"] == 100
    assert row["volume_qualification"]["normalization"] == "NONE"


def test_adjusted_provider_label_contradicts_raw_agreement():
    row = contract.build_session_manifest(snapshot(price_basis="CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"), session=SESSION, official_series=official())["records"][0]
    assert contract.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in row["qualification"]["allowed_uses"]


def test_hash_domain_cannot_be_relabelled_by_observation():
    row = contract.build_session_manifest(snapshot(payload_hash_kind="exact_http_response_body_sha256", payload_sha256="f"*64), session=SESSION)["records"][0]
    assert row["payload"]["hash_kind"] == "canonical_json_of_retained_observation"
    assert row["payload"]["sha256"] != "f"*64
    with pytest.raises(contract.SnapshotContractError, match="hash_kind"):
        contract.build_snapshot(provider="DNSE", source_id="X", route="/r", ticker="AAA", exchange=None, session=SESSION,
            receipt_at=SESSION+"T09:00:00Z", payload_sha256="f"*64, payload_bytes=2, payload_hash_kind="provider_or_canonical", next_session=None, ohlc={})


def test_idempotence_revision_and_original_known_time(tmp_path):
    first = retention.retain_market(snapshot(), session=SESSION, root=tmp_path)
    original_path = next((tmp_path / "operations-review/prospective-market-evidence-v1" / SESSION / "receipts").glob("*.json"))
    original = original_path.read_bytes()
    assert retention.retain_market(snapshot(), session=SESSION, root=tmp_path)["status"] == "ALREADY_RETAINED_IDENTICAL"
    revised = retention.retain_market(snapshot(close=10.5, volume=99, retrieved_at="2026-10-02T10:00:00Z"), session=SESSION, root=tmp_path)
    assert revised["artifact_identity"] != first["artifact_identity"]
    receipts = [json.loads(p.read_bytes()) for p in original_path.parent.glob("*.json")]
    newer = next(r for r in receipts if r["previous_version_identity"])
    assert newer["previous_version_identity"] == json.loads(original)["artifact_identity"]
    assert newer["revision"]["classification"] == contract.REVISED_RETROSPECTIVELY
    assert newer["volume_changed"] is True
    assert original_path.read_bytes() == original
    assert retention.retain_market(snapshot(), session=SESSION, root=tmp_path)["path"] == first["path"]
    assert json.loads(original)["observation"]["acquisition"]["knowledge_available_at_utc"] == SESSION+"T09:00:00Z"


def test_same_receipt_mutation_and_corrupt_path_fail_closed(tmp_path):
    retention.retain_market(snapshot(), session=SESSION, root=tmp_path)
    with pytest.raises(ValueError, match="IMMUTABLE_RECEIPT"):
        retention.retain_market(snapshot(close=10.4), session=SESSION, root=tmp_path)
    path = next((tmp_path / "operations-review/prospective-market-evidence-v1" / SESSION / "receipts").glob("*.json"))
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match="BYTES_MISMATCH"):
        retention.retain_market(snapshot(), session=SESSION, root=tmp_path)
    assert path.read_bytes().endswith(b' ')


def test_current_universe_retained_without_historical_active_membership(tmp_path):
    import current_official_market_universe as universe
    value = {"contract_version": universe.CONTRACT_VERSION, "records": {"AAA": {"exchange_or_market": "HOSE",
             "official_observed_at": SESSION+"T09:00:00Z", "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"}}}
    value.update(universe._identity(value))
    source = tmp_path / "universe.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    result = retention.retain_universe(source, root=tmp_path)
    assert json.loads(open(result["path"]).read())["records"][0]["active_universe_at_time"] == "UNKNOWN"
    retained = source.read_bytes()
    retention.retain_universe(source, root=tmp_path)
    assert source.read_bytes() == retained
    assert result["source_observations_with_known_time"] == 0  # no source row identity in the fixture


def test_selected_listing_sources_reuse_existing_bridge_and_never_backdate_static_rows(tmp_path, monkeypatch):
    import official_corporate_event_incremental_acquisition as acquisition
    hnx = {"artifact_identity":"hnx:fixture","captures":[{"sha256":"a"*64,"retrieved_at":"2026-10-02T02:00:00Z"}],
           "hnx_official_equity_universe":{"records":[{"ticker":"AAA","market":"UPCOM","source_identity":"a"*64}]},
           "rights_event_index":{"records":[]}}
    hose = {"artifact_identity":"hose:fixture","captures":[{"sha256":"b"*64,"retrieved_at":"2026-10-02T02:05:00Z"}],
            "datasets":{"hose_public_stock_master/v1":[{"ticker":"BBB","hose_security_id":"1","source_identity":"b"*64}]}}
    verified = {"hnx":hnx,"hose":hose,"attempt_identity":"attempt:fixture"}
    calls = []
    def verify(root,session):
        calls.append((root,session)); return verified
    monkeypatch.setattr(acquisition,"verify_successful_acquisition",verify)
    result = retention.retain_selected_listing_sources(tmp_path,acquisition_session="2026-10-02",root=tmp_path)
    assert calls == [(tmp_path,"2026-10-02")]
    assert result["observations"] == result["source_observations_with_known_time"] == 2
    retained = json.loads(open(result["path"]).read())
    assert all(r["active_universe_at_time"] == "UNKNOWN" for r in retained["records"])
    assert all(r["knowledge_available_at"].startswith("2026-10-02") for r in retained["records"])
    before = open(result["path"],'rb').read()
    assert retention.retain_selected_listing_sources(tmp_path,acquisition_session="2026-10-02",root=tmp_path)["artifact_identity"] == result["artifact_identity"]
    assert open(result["path"],'rb').read() == before


def test_daily_automatically_retains_exact_selected_listing_receipts(tmp_path,monkeypatch):
    import canonical_post_close_pipeline as pipeline
    import daily_session_level2_package as level2
    import corporate_currency_rollforward as corporate
    from test_canonical_post_close_pipeline import _write_snapshot, _write_triage
    paths = level2.session_artifact_paths(tmp_path,SESSION)
    order = []
    monkeypatch.setattr(level2,"ensure_exact_session_snapshot",lambda *_a,**_k:_write_snapshot(paths,SESSION,
        requested_at=SESSION+"T19:00:00+07:00",exact=500,total=1000))
    result = corporate.CorporateCurrencyRollforwardResult(b'{"selected_acquisition_session":"2026-10-02"}',None,None)
    monkeypatch.setattr(corporate,"rollforward",lambda *_a,**_k:order.append("corporate") or result)
    def retain(source_root,**kwargs):
        assert source_root == tmp_path and kwargs == {"acquisition_session":"2026-10-02","root":tmp_path}
        order.append("listing_receipts");return {"status":"RETAINED","observations":2,"active_membership_qualified":0}
    monkeypatch.setattr(retention,"retain_selected_listing_sources",retain)
    monkeypatch.setattr(level2,"materialize_independent_components",lambda *_a,**_k:order.append("optional_components"))
    monkeypatch.setattr(level2,"maybe_build_triage_dependent",lambda *_a,**_k:_write_triage(paths,SESSION))
    acquired = pipeline.acquire_and_materialize(tmp_path,SESSION,tmp_path/"runtime",now=datetime.fromisoformat("2026-10-02T12:00:00+07:00"),enable_corporate_currency_rollforward=True)
    assert order == ["corporate","listing_receipts","optional_components"]
    assert acquired["prospective_market_evidence"]["listing_sources"]["observations"] == 2


def test_missing_terms_and_later_calendar_correction_never_qualify_factor(tmp_path):
    import current_official_event_context as context
    event = {"ticker": "AAA", "event_id": "event:v1", "source_record_identity": "source:row", "ex_date": SESSION,
             "record_date": "2026-10-02", "execution_date": "2026-10-12", "event_state": "EX_DATE_TODAY",
             "official_observed_at": SESSION+"T09:00:00Z", "published_at": None}
    value = {"contract_version": context.CONTRACT_VERSION, "all_current_universe_event_records": [event]}
    value.update(context._identity(value))
    first = retention.retain_corporate(value, root=tmp_path)
    before = open(first["path"], 'rb').read()
    changed = copy.deepcopy(value)
    changed["all_current_universe_event_records"][0].update(ex_date="2026-10-03", event_id="event:v2", official_observed_at="2026-10-02T10:00:00Z")
    changed.update(context._identity(changed))
    second = retention.retain_corporate(changed, root=tmp_path)
    assert first["qualified_factor_count"] == second["qualified_factor_count"] == 0
    assert open(first["path"], 'rb').read() == before


@pytest.mark.parametrize("failure", ["corporate", "fundamental_valuation"])
def test_actual_acquisition_retains_before_optional_outage(tmp_path, monkeypatch, failure):
    import canonical_post_close_pipeline as pipeline
    import daily_session_level2_package as level2
    import corporate_currency_rollforward as corporate
    from test_canonical_post_close_pipeline import _write_snapshot
    from test_production_call_shape_smoke import _offline_smoke_guard
    paths = level2.session_artifact_paths(tmp_path, SESSION)
    def ensure(*_a, **_k):
        _write_snapshot(paths, SESSION, requested_at=SESSION+"T19:00:00+07:00", exact=500, total=1000, records=snapshot()["records"])
    def outage(*_a, **_k):
        manifest = list((tmp_path / "operations-review/prospective-market-evidence-v1" / SESSION / "manifests").glob("*.json"))
        assert len(manifest) == 1 and json.loads(manifest[0].read_bytes())["summary"]["snapshots"] == 1
        raise RuntimeError("optional outage")
    monkeypatch.setattr(level2, "ensure_exact_session_snapshot", ensure)
    if failure == "corporate":
        monkeypatch.setattr(corporate, "rollforward", outage)
    else:
        monkeypatch.setattr(level2, "materialize_independent_components", outage)
    with _offline_smoke_guard() as counters:
        with pytest.raises(RuntimeError, match="optional outage"):
            pipeline.acquire_and_materialize(tmp_path, SESSION, tmp_path / "runtime", now=datetime.fromisoformat(SESSION+"T19:00:00+07:00"),
                enable_corporate_currency_rollforward=failure == "corporate")
    assert all(v == 0 for v in counters.values())
