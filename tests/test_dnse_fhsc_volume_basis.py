from dnse_fhsc_volume_basis import (
    BASIS_UNRESOLVED, DNSE_EQUALS_MATCHED, DNSE_EQUALS_TOTAL,
    FHSC_HISTORY_VOLUME_MATCHED, FHSC_HISTORY_VOLUME_NON_INVARIANT,
    HISTORY_EQUALS_MATCHED, HISTORY_EQUALS_TOTAL, NOT_COMPARABLE,
    classify_dnse_volume, classify_fhsc_history, reconcile_volume_rows,
)


def _trading(*, matched=100, put_through=20, total=120):
    return {"parse_status": "PARSED", "matched_volume": matched, "put_through_volume": put_through,
            "total_volume": total, "retained_arithmetic_identity": matched + put_through == total}


def test_documented_retained_identity_and_history_matched():
    trading = _trading()
    assert trading["retained_arithmetic_identity"]
    assert classify_fhsc_history(100, trading, documented_identity=True) == HISTORY_EQUALS_MATCHED


def test_history_total_and_non_invariant_behavior_are_distinct():
    assert classify_fhsc_history(120, _trading(), documented_identity=True) == HISTORY_EQUALS_TOTAL
    result = reconcile_volume_rows(
        [{"instrument": "AAA", "session": "2026-08-20", "raw_value": 100}, {"instrument": "BBB", "session": "2026-08-20", "raw_value": 120}],
        [{"instrument": "AAA", "session": "2026-08-20", "volume": 100}, {"instrument": "BBB", "session": "2026-08-20", "volume": 120}],
        [{"instrument": "AAA", "session": "2026-08-20", **_trading()}, {"instrument": "BBB", "session": "2026-08-20", **_trading()}],
        documented_identity=True, required_observations=2)
    assert result["fhsc_history_volume_basis"] == FHSC_HISTORY_VOLUME_NON_INVARIANT


def test_dnse_matched_total_and_generic_failure_are_distinct():
    trading = _trading()
    assert classify_dnse_volume(100, trading, documented_identity=True) == DNSE_EQUALS_MATCHED
    assert classify_dnse_volume(120, trading, documented_identity=True) == DNSE_EQUALS_TOTAL
    assert classify_dnse_volume(100, trading, documented_identity=False) == BASIS_UNRESOLVED


def test_ambiguous_zero_put_through_cannot_auto_map():
    assert classify_fhsc_history(100, _trading(matched=100, put_through=0, total=100), documented_identity=True) == NOT_COMPARABLE


def test_one_exception_blocks_universal_mapping_and_order_does_not_change_replay():
    dnse = [
        {"instrument": "AAA", "session": "2026-08-20", "raw_value": 100},
        {"instrument": "BBB", "session": "2026-08-20", "raw_value": 100},
        {"instrument": "CCC", "session": "2026-08-20", "raw_value": 120},
    ]
    history = [{**row, "volume": row["raw_value"]} for row in dnse]
    trading = [{"instrument": row["instrument"], "session": row["session"], **_trading()} for row in dnse]
    first = reconcile_volume_rows(dnse, history, trading, documented_identity=True)
    second = reconcile_volume_rows(reversed(dnse), reversed(history), reversed(trading), documented_identity=True)
    assert first["dnse_volume_basis_candidate"] == "NO_VOLUME_BASIS_QUALIFIED"
    assert first == second


def test_empirical_basis_never_creates_liquidity_authority():
    dnse = [{"instrument": ticker, "session": "2026-08-20", "raw_value": 100} for ticker in ("AAA", "BBB", "CCC", "DDD")]
    history = [{**row, "volume": 100} for row in dnse]
    trading = [{"instrument": row["instrument"], "session": row["session"], **_trading()} for row in dnse]
    result = reconcile_volume_rows(dnse, history, trading, documented_identity=True)
    assert result["fhsc_history_volume_basis"] == FHSC_HISTORY_VOLUME_MATCHED
    assert result["dnse_volume_basis_candidate"] == "DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL"
    assert not result["liquidity_authority"]
    assert not result["position_sizing_safe"]


def test_zero_put_through_consistency_does_not_block_discriminating_three_ticker_mapping():
    dnse = [{"instrument": ticker, "session": "2026-08-20", "raw_value": 100} for ticker in ("AAA", "BBB", "CCC", "DDD")]
    history = [{**row, "volume": 100} for row in dnse]
    trading = [
        {"instrument": "AAA", "session": "2026-08-20", **_trading(matched=100, put_through=10, total=110)},
        {"instrument": "BBB", "session": "2026-08-20", **_trading(matched=100, put_through=20, total=120)},
        {"instrument": "CCC", "session": "2026-08-20", **_trading(matched=100, put_through=30, total=130)},
        {"instrument": "DDD", "session": "2026-08-20", **_trading(matched=100, put_through=0, total=100)},
    ]
    result = reconcile_volume_rows(dnse, history, trading, documented_identity=True)
    assert result["dnse_volume_basis_candidate"] == "DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL"
    assert result["zero_put_through_non_discriminating_consistency_count"] == 1


def test_artifact_request_records_do_not_contain_secret_shaped_fields():
    record = {"symbol": "HPG", "request_url": "https://example.test/history", "raw_sha256": "0" * 64}
    assert not {key for key in record if any(word in key.lower() for word in ("secret", "api_key", "authorization", "signature"))}
