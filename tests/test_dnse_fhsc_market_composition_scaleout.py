from dnse_fhsc_market_composition_scaleout import (
    DNSE_EQUALS_MATCHED, DNSE_EQUALS_NONE, DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE,
    NON_DISCRIMINATING_ZERO_PUT_THROUGH, classify_volume, reconcile_scaleout, value_matrix,
)
from dnse_fhsc_volume_basis import parse_fhsc_trading_history


def _trading(matched=100, put_through=10):
    return {"matched_volume": matched, "put_through_volume": put_through, "total_volume": matched + put_through,
            "retained_arithmetic_identity": True, "matched_value": 1000, "put_through_value": 100,
            "total_value": 1100, "retained_value_arithmetic_identity": True}


def test_discriminating_and_zero_component_rows_stay_separate():
    assert classify_volume(100, _trading()) == DNSE_EQUALS_MATCHED
    assert classify_volume(100, _trading(100, 0)) == NON_DISCRIMINATING_ZERO_PUT_THROUGH


def test_zero_put_through_cannot_create_confidence_or_hide_contradiction():
    assert classify_volume(99, _trading(100, 0)) == DNSE_EQUALS_NONE
    result = reconcile_scaleout(
        [{"instrument": "AAA", "session": "d", "raw_value": 100}, {"instrument": "BBB", "session": "d", "raw_value": 100}],
        [{"instrument": "AAA", "session": "d", **_trading(100, 0)}, {"instrument": "BBB", "session": "d", **_trading(100, 0)}],
        fhsc_history_rows=[{"instrument": "AAA", "session": "d", "volume": 100}, {"instrument": "BBB", "session": "d", "volume": 100}], exchange_by_ticker={"AAA": "HOSE", "BBB": "HNX"}, expected_keys=[("AAA", "d"), ("BBB", "d")])
    assert result["candidate_mapping"] == "NO_UNIVERSAL_VOLUME_MAPPING"


def test_invariant_cross_exchange_matched_mapping_and_deterministic_order():
    dnse = [{"instrument": "AAA", "session": "d", "raw_value": 100}, {"instrument": "BBB", "session": "d", "raw_value": 100}]
    trading = [{"instrument": "AAA", "session": "d", **_trading()}, {"instrument": "BBB", "session": "d", **_trading(100, 20)}]
    kwargs = {"fhsc_history_rows": [{"instrument": "AAA", "session": "d", "volume": 100}, {"instrument": "BBB", "session": "d", "volume": 100}], "exchange_by_ticker": {"AAA": "HOSE", "BBB": "HNX"}, "expected_keys": [("AAA", "d"), ("BBB", "d")]}
    first, second = reconcile_scaleout(dnse, trading, **kwargs), reconcile_scaleout(reversed(dnse), reversed(trading), **kwargs)
    assert first == second
    assert first["candidate_mapping"] == "DNSE_MATCHED_VOLUME_SEMANTICS_SCALEOUT_VALIDATED"


def test_one_contradiction_blocks_universal_mapping_and_exchange_scope_is_separate():
    result = reconcile_scaleout(
        [{"instrument": "AAA", "session": "d", "raw_value": 100}, {"instrument": "BBB", "session": "d", "raw_value": 110}],
        [{"instrument": "AAA", "session": "d", **_trading()}, {"instrument": "BBB", "session": "d", **_trading(100, 20)}],
        fhsc_history_rows=[{"instrument": "AAA", "session": "d", "volume": 100}, {"instrument": "BBB", "session": "d", "volume": 100}], exchange_by_ticker={"AAA": "HOSE", "BBB": "HNX"}, expected_keys=[("AAA", "d"), ("BBB", "d")])
    assert result["candidate_mapping"] == "NO_UNIVERSAL_VOLUME_MAPPING"
    assert result["exchange_specific_summary"]["HOSE"]["candidate"] == "NO_UNIVERSAL_VOLUME_MAPPING"


def test_single_exchange_can_be_narrowly_validated_but_not_promoted_to_cross_exchange():
    result = reconcile_scaleout(
        [{"instrument": "AAA", "session": "d", "raw_value": 100}, {"instrument": "BBB", "session": "d", "raw_value": 100}],
        [{"instrument": "AAA", "session": "d", **_trading()}, {"instrument": "BBB", "session": "d", **_trading(100, 20)}],
        fhsc_history_rows=[{"instrument": "AAA", "session": "d", "volume": 100}, {"instrument": "BBB", "session": "d", "volume": 100}],
        exchange_by_ticker={"AAA": "HOSE", "BBB": "HOSE"}, expected_keys=[("AAA", "d"), ("BBB", "d")])
    assert result["candidate_mapping"] == "NO_UNIVERSAL_VOLUME_MAPPING"
    assert result["exchange_specific_summary"]["HOSE"]["candidate"] == "DNSE_MATCHED_VOLUME_SEMANTICS_HOSE_SCALEOUT_VALIDATED"


def test_value_requires_explicit_comparator_and_agreement_never_creates_authority():
    values = value_matrix([{"instrument": "AAA", "session": "d", "close": 999, **_trading()}], exchange_by_ticker={"AAA": "HOSE"}, expected_keys=[("AAA", "d")])
    assert values["matrix"][0]["dnse_value_classification"] == DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE
    assert values["verdict"] == DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE
    assert values["authority_effect"] == "NONE"
    assert "dnse_value" not in values["matrix"][0], "price × volume must never manufacture traded value"


def test_provider_agreement_never_enables_liquidity_or_sizing():
    result = reconcile_scaleout(
        [{"instrument": "AAA", "session": "d", "raw_value": 100}, {"instrument": "BBB", "session": "d", "raw_value": 100}],
        [{"instrument": "AAA", "session": "d", **_trading()}, {"instrument": "BBB", "session": "d", **_trading()}],
        fhsc_history_rows=[{"instrument": "AAA", "session": "d", "volume": 100}, {"instrument": "BBB", "session": "d", "volume": 100}],
        exchange_by_ticker={"AAA": "HOSE", "BBB": "HNX"}, expected_keys=[("AAA", "d"), ("BBB", "d")])
    assert result["authority_effect"] == "NONE"
    assert not result["liquidity_authority"] and not result["position_sizing_safe"]


def test_retained_fhsc_volume_and_value_identities_are_explicitly_verified():
    raw = b'{"data":{"data":[{"date":"2026-08-20","matched":{"volume":100,"value":1000},"put_through":{"volume":20,"value":200},"total":{"volume":120,"value":1200}}]}}'
    row = parse_fhsc_trading_history(raw, instrument="AAA")["rows"][0]
    assert row["retained_arithmetic_identity"]
    assert row["retained_value_arithmetic_identity"]


def test_retained_request_metadata_has_no_secret_shaped_fields():
    record = {"symbol": "AAA", "endpoint": "/market/stocks/AAA/trading/history", "raw_sha256": "0" * 64}
    assert not {key for key in record if any(word in key.lower() for word in ("secret", "api_key", "authorization", "signature"))}
