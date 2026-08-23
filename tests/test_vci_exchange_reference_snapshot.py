import pytest

from vci_exchange_reference_snapshot import (
    VciExchangeReferenceSnapshotError,
    build_snapshot,
    verify_identity,
)


def test_build_snapshot_counts_by_exchange_and_is_deterministic():
    rows = [
        {"ticker": "aaa", "exchange": "HSX", "updated": "2026-08-14T10:00:00+07:00"},
        {"ticker": "bbb", "exchange": "DELISTED", "updated": "2026-08-14T10:00:01+07:00"},
        {"ticker": "ccc", "exchange": None, "updated": None},
    ]
    first = build_snapshot(rows=rows, retrieved_at="2026-08-23T00:00:00+07:00")
    second = build_snapshot(rows=rows, retrieved_at="2026-08-23T00:00:00+07:00")

    assert first["snapshot_identity"] == second["snapshot_identity"]
    assert first["row_count"] == 3
    assert first["by_exchange"] == {"DELISTED": 1, "HSX": 1, "MISSING": 1}
    assert first["records"]["AAA"]["exchange"] == "HSX"
    assert first["records"]["BBB"]["exchange"] == "DELISTED"
    assert first["records"]["CCC"]["exchange"] is None
    verify_identity(first)


def test_unrecognized_exchange_value_is_retained_not_discarded():
    rows = [{"ticker": "ZZZ", "exchange": "SOME_NEW_LABEL", "updated": None}]
    snapshot = build_snapshot(rows=rows, retrieved_at="2026-08-23T00:00:00+07:00")

    assert snapshot["records"]["ZZZ"]["exchange"] == "SOME_NEW_LABEL"
    assert snapshot["records"]["ZZZ"]["recognized_exchange_value"] is False
    assert snapshot["unrecognized_exchange_values"] == ["SOME_NEW_LABEL"]


def test_missing_ticker_and_duplicate_ticker_fail_closed():
    with pytest.raises(VciExchangeReferenceSnapshotError):
        build_snapshot(rows=[{"exchange": "HSX"}], retrieved_at="2026-08-23T00:00:00+07:00")
    with pytest.raises(VciExchangeReferenceSnapshotError):
        build_snapshot(
            rows=[{"ticker": "AAA", "exchange": "HSX"}, {"ticker": "aaa", "exchange": "HNX"}],
            retrieved_at="2026-08-23T00:00:00+07:00",
        )


def test_verify_identity_rejects_tampered_snapshot():
    snapshot = build_snapshot(rows=[{"ticker": "AAA", "exchange": "HSX"}], retrieved_at="2026-08-23T00:00:00+07:00")
    tampered = dict(snapshot)
    tampered["by_exchange"] = {"HSX": 999}
    with pytest.raises(VciExchangeReferenceSnapshotError):
        verify_identity(tampered)
