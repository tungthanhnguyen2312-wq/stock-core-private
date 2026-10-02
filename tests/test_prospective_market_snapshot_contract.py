from datetime import datetime

import pytest

import prospective_market_snapshot_contract as c

H = "a" * 64
OHLC = {"open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2}


def snap(receipt="2026-09-28T09:40:00+00:00", session="2026-09-28", nxt=None, **kw):
    base = dict(provider="P", source_id="S", route="/r", ticker="abc", exchange="HOSE", session=session, receipt_at=receipt,
                payload_sha256=H, payload_bytes=10, payload_hash_kind="canonical_json_of_retained_observation", next_session=nxt, ohlc=OHLC)
    base.update(kw)
    return c.build_snapshot(**base)


def test_post_close_same_session_capture_is_prospective():
    record = snap()
    assert record["acquisition"]["capture_timing"] == c.PROSPECTIVE_SAME_SESSION_CAPTURE
    assert c.USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE in record["qualification"]["allowed_uses"]
    assert record["observation"]["never_revised_proven"] is False


def test_pre_close_receipt_is_not_prospective_closed_bar():
    record = snap(receipt="2026-09-28T05:00:00+00:00")  # 12:00 Vietnam, before the 15:00 close
    assert record["acquisition"]["capture_timing"] == c.RETROSPECTIVE_ACQUISITION
    assert c.USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE not in record["qualification"]["allowed_uses"]


def test_next_day_before_0900_vn_is_prospective_without_calendar_and_after_needs_next_session():
    early = snap(receipt="2026-09-28T23:30:00+00:00")  # 06:30 Vietnam next calendar day
    assert early["acquisition"]["capture_timing"] == c.PROSPECTIVE_SAME_SESSION_CAPTURE
    late_unknown = snap(receipt="2026-09-29T03:00:00+00:00")  # 10:00 Vietnam, calendar has no next session
    assert late_unknown["acquisition"]["capture_timing"] == c.CAPTURE_TIMING_UNKNOWN
    late_known = snap(receipt="2026-09-29T03:00:00+00:00", nxt="2026-09-29")
    assert late_known["acquisition"]["capture_timing"] == c.RETROSPECTIVE_ACQUISITION


def test_weekend_gap_uses_governed_next_session():
    # Friday session captured Sunday morning: before Monday's open.
    record = snap(session="2026-09-25", receipt="2026-09-27T01:00:00+00:00", nxt="2026-09-28")
    assert record["acquisition"]["capture_timing"] == c.PROSPECTIVE_SAME_SESSION_CAPTURE


def test_raw_as_traded_requires_independent_agreement_and_never_from_route_alone():
    assert c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in snap()["qualification"]["allowed_uses"]
    assert "RAW_AS_TRADED_REQUIRES_INDEPENDENT_CROSS_SOURCE_AGREEMENT" in snap()["qualification"]["withheld_reason_codes"]
    agreed = snap(cross_source_agreement=True)
    assert c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in agreed["qualification"]["allowed_uses"]
    assert c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in snap(cross_source_agreement=False)["qualification"]["allowed_uses"]


def test_adjusted_basis_never_raw_even_with_agreement():
    for kw in ({"source_claim": c.SOURCE_DOCUMENTS_ADJUSTED}, {"empirical": c.EMPIRICAL_ADJUSTED_ACROSS_EVENT}):
        record = snap(cross_source_agreement=True, **kw)
        assert c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in record["qualification"]["allowed_uses"]
        assert "SOURCE_BASIS_ADJUSTED_NOT_RAW" in record["qualification"]["withheld_reason_codes"]


def test_retrospective_acquisition_keeps_only_revision_baseline():
    record = snap(receipt="2026-10-05T03:00:00+00:00", nxt="2026-09-29", cross_source_agreement=True)
    assert record["qualification"]["allowed_uses"] == [c.USE_REVISION_DETECTION_BASELINE]
    assert record["qualification"]["state"] == "RETAINED_KNOWN_TIME_BASELINE_ONLY"


def test_never_granted_uses_are_always_listed_and_never_allowed():
    record = snap(cross_source_agreement=True)
    assert set(c.NEVER_GRANTED).isdisjoint(record["qualification"]["allowed_uses"])
    assert record["qualification"]["never_granted_by_this_contract"] == list(c.NEVER_GRANTED)


def test_three_claims_are_separate_and_identity_deterministic():
    a, b = snap(), snap()
    assert a["snapshot_identity"] == b["snapshot_identity"]
    assert a["basis"]["source_basis_claim"] == c.SOURCE_BASIS_UNDOCUMENTED
    assert a["basis"]["adjusted_raw_unknown_claim"] == "unknown"
    assert a["observation"]["possession_at_known_time_proven"] is True
    assert snap(receipt="2026-09-28T09:41:00+00:00")["snapshot_identity"] != a["snapshot_identity"]


def test_invalid_inputs_fail_closed():
    with pytest.raises(c.SnapshotContractError):
        snap(receipt=datetime(2026, 9, 28, 9, 40))  # naive
    with pytest.raises(c.SnapshotContractError):
        snap(payload_sha256="short")
    with pytest.raises(c.SnapshotContractError):
        snap(source_claim="MAYBE")
    with pytest.raises(c.SnapshotContractError):
        snap(board_basis={"api_key": "leak"})


def test_zero_price_is_not_a_traded_price():
    record = snap(ohlc={"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0})
    assert record["qualification"]["allowed_uses"] == []
    assert record["qualification"]["state"] == "NOT_QUALIFIED"


def test_revision_classification_classes():
    t0 = snap(receipt="2026-09-28T09:40:00+00:00")
    same = snap(receipt="2026-09-29T02:00:00+00:00")
    assert c.revision_classification(t0, same)["classification"] == c.NEVER_REVISED_OBSERVED_SAMPLE
    assert "not generalised" in c.revision_classification(t0, same)["scope"]
    changed = snap(receipt="2026-09-29T02:00:00+00:00", ohlc={**OHLC, "close": 9.3})
    assert c.revision_classification(t0, changed)["classification"] == c.REVISED_RETROSPECTIVELY
    assert c.revision_classification(t0, None)["classification"] == c.NO_COMPARABLE_SNAPSHOT
    assert c.revision_classification(same, t0)["reason"] == "T1_NOT_AFTER_T0"
    other = snap(receipt="2026-09-29T02:00:00+00:00", ticker="xyz")
    assert c.revision_classification(t0, other)["reason"] == "IDENTITY_MISMATCH"


def test_summary_is_counts_only():
    summary = c.summarize([snap(), snap(cross_source_agreement=True)])
    assert summary["snapshots"] == 2
    assert "10.2" not in str(summary)


def _exact_snapshot(session="2026-09-28"):
    def obs(close, retrieved="2026-09-28T09:40:00+00:00", sess=session):
        return {"session": sess, "open": 10.0, "high": 10.5, "low": 9.9, "close": close, "volume": 100,
                "retrieved_at": retrieved, "dataset": "DNSE_OHLC_1D", "provider": "DNSE", "price_unit": "SOURCE_PRICE_UNIT_UNDOCUMENTED"}
    return {"resolved_completed_session": session, "snapshot_identity": "p3f9_exact_session_snapshot:x", "records": {
        "AAA": {"observations": [obs(10.1, sess="2026-09-25"), obs(10.2)]},
        "BBB": {"observations": [obs(9.0, retrieved=None)]},
        "CCC": {"observations": []}}}


def test_session_manifest_links_bars_to_known_time_receipts_and_skips_never_substitutes():
    manifest = c.build_session_manifest(_exact_snapshot(), session="2026-09-28")
    assert manifest["summary"]["snapshots"] == 1 and manifest["snapshot_identities"] == [manifest["records"][0]["snapshot_identity"]]
    assert manifest["skipped"] == {"NO_RECEIPT_TIME": 1, "NO_TARGET_SESSION_OBSERVATION": 1}
    assert manifest["records"][0]["normalized"]["ohlc"]["close"] == 10.2  # the target session, not an older bar
    assert manifest["summary"]["by_allowed_use"].get(c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE) is None
    assert c.build_session_manifest(_exact_snapshot(), session="2026-09-28")["artifact_identity"] == manifest["artifact_identity"]


def test_session_manifest_raw_fitness_only_with_independent_official_agreement():
    snapshot = _exact_snapshot()
    snapshot["records"]["AAA"]["observations"][-1].update(exchange="HOSE", price_unit="VND")
    official = {"ticker": "AAA", "exchange": "HOSE", "session": "2026-09-28", "provider": "HOSE",
                "source_id": "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT", "receipt_identity": "receipt:x",
                "knowledge_available_at": "2026-09-28T09:30:00Z", "price_unit": "VND", "ohlc": [10.0,10.5,9.9,10.2]}
    agree = c.build_session_manifest(snapshot, session="2026-09-28", official_series={"AAA": official})
    assert agree["summary"]["by_allowed_use"][c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE] == 1
    differ = c.build_session_manifest(snapshot, session="2026-09-28", official_series={"AAA": {**official, "ohlc": [10.0,10.5,9.9,10.3]}})
    assert c.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE not in differ["summary"]["by_allowed_use"]


def test_session_manifest_rejects_other_session_snapshot():
    with pytest.raises(c.SnapshotContractError):
        c.build_session_manifest(_exact_snapshot("2026-09-25"), session="2026-09-28")
