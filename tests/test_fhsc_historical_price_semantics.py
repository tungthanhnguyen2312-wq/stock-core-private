from __future__ import annotations

from fhsc_historical_price_semantics import FIELDS, calibration_matrix, ratio_classification


def _uniform_representation() -> dict[str, str]:
    return {field: "TEST_PROVIDER_NATIVE_VALUE" for field in FIELDS}


def _history(tmp_path, symbol: str, rows: list[dict]) -> dict:
    import hashlib
    import json
    path = tmp_path / f"{symbol}.json"
    payload = {"data": {"symbol": symbol, "resolution": "1D", "time": [1787097600 for _ in rows],
                        **{field: [row[field] for row in rows] for field in (*FIELDS, "volume")}}}
    path.write_bytes(json.dumps(payload).encode())
    return {"symbol": symbol, "successful": True, "raw_path": path, "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "request_url": "test"}


def test_exact_scale_detection_and_non_constant_detection() -> None:
    assert ratio_classification(1000, 1)[0] == "EXACT_1000_TO_1"
    assert ratio_classification(10, 10)[0] == "EXACT_1_TO_1"
    assert ratio_classification(15, 2)[0] == "OTHER_CONSTANT_RATIO"
    assert ratio_classification(1, 0)[0] == "NOT_COMPARABLE"


def test_ohlc_is_handled_field_by_field_and_cannot_qualify_a_global_transform(tmp_path) -> None:
    record = _history(tmp_path, "HPG", [{"open": 10, "high": 12, "low": 9, "close": 11, "volume": 1}])
    dnse = [{"instrument": "HPG", "session": "2026-08-19", "open": 10, "high": 12, "low": 9, "close": 11000,
             "field_representation": _uniform_representation()}]
    matrix = calibration_matrix(dnse, [record])
    assert matrix["field_summary"]["open"]["invariant_ratio"] == "1"
    assert matrix["field_summary"]["close"]["invariant_ratio"] == "1000"
    assert matrix["candidate_transform_invariant_across_fields_issuers_sessions"] is False


def test_order_independence_and_no_authority_mutation(tmp_path) -> None:
    hpg = _history(tmp_path, "HPG", [{"open": 1, "high": 2, "low": 1, "close": 1, "volume": 1}])
    vcb = _history(tmp_path, "VCB", [{"open": 3, "high": 4, "low": 2, "close": 3, "volume": 1}])
    rows = [
        {"instrument": "HPG", "session": "2026-08-19", "open": 1, "high": 2, "low": 1, "close": 1,
         "field_representation": _uniform_representation()},
        {"instrument": "VCB", "session": "2026-08-19", "open": 3, "high": 4, "low": 2, "close": 3,
         "field_representation": _uniform_representation()},
    ]
    assert calibration_matrix(rows, [hpg, vcb]) == calibration_matrix(reversed(rows), [vcb, hpg])


def test_mixed_dnse_field_representations_fail_closed_for_every_ohlc_field(tmp_path) -> None:
    record = _history(tmp_path, "HPG", [{"open": 10, "high": 12, "low": 9, "close": 11, "volume": 1}])
    dnse = [{"instrument": "HPG", "session": "2026-08-19", "open": 10, "high": 12, "low": 9, "close": 11000,
             "field_representation": {"open": "RAW", "high": "RAW", "low": "RAW", "close": "NORMALIZED_X1000"}}]
    matrix = calibration_matrix(dnse, [record])
    assert matrix["total_comparable_pairs"] == 0
    assert matrix["excluded_pair_count"] == 4
    assert matrix["excluded_reason_counts"] == {"DNSE_MIXED_FIELD_REPRESENTATION": 4}
    assert {pair["classification"] for pair in matrix["pairs"]} == {"NOT_COMPARABLE"}


def test_undeclared_dnse_field_representations_cannot_silently_enter_calibration(tmp_path) -> None:
    record = _history(tmp_path, "HPG", [{"open": 10, "high": 12, "low": 9, "close": 11, "volume": 1}])
    matrix = calibration_matrix([{"instrument": "HPG", "session": "2026-08-19", "open": 10, "high": 12, "low": 9, "close": 11}], [record])
    assert matrix["field_summary"]["close"]["classifications"] == {"NOT_COMPARABLE": 1}
    assert matrix["pairs"][0]["exclusion_reason"] == "DNSE_FIELD_REPRESENTATION_UNDECLARED"
