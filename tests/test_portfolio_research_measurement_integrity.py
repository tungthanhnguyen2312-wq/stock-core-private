"""Adversarial caller measurements, not issuer data or production observations."""
from copy import deepcopy
import json

import pytest

from stocklookup_core.portfolio import portfolio_research_decision_workbench as workbench

DATES = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]


def rows():
    return [
        {"ticker": "AAA", "sector": "one", "current_returns": [.01, .02, -.01, .0],
         "current_return_dates": list(DATES), "measurements": {"objective": 0}},
        {"ticker": "BBB", "sector": "two", "current_returns": [.02, .01, -.02, .01],
         "current_return_dates": list(DATES), "measurements": {"objective": -2}},
    ]


def pair(built, left="AAA", right="BBB"):
    return next(p for p in built["current_correlation"]["pairs"] if (p["left"], p["right"]) == (left, right))


def strict_json(value):
    return json.loads(json.dumps(value, allow_nan=False))


def test_released_valid_dated_undated_and_missing_golden_identity():
    supplied = rows()
    original = deepcopy(supplied)
    dated = workbench.build_workbench(supplied, objective="objective")
    assert dated["workbench_identity"] == "portfolio_research_decision_workbench:8b60737088b88c020d87f441dca1b6ee41577999a0c81410477876a79877e919"
    assert pair(dated)["comparable"] is True
    assert supplied == original
    for row in supplied:
        row.pop("current_return_dates")
    undated = workbench.build_workbench(supplied, objective="objective")
    assert undated["workbench_identity"] == "portfolio_research_decision_workbench:b9443433bb59792559c2a0ef6e26dac5204fadf145636c7c222d4d4534c24ce8"
    assert pair(undated)["comparable"] is False and pair(undated)["value"] == pair(dated)["value"]
    missing = workbench.build_workbench([{"ticker": "AAA"}, {"ticker": "BBB"}])
    assert missing["workbench_identity"] == "portfolio_research_decision_workbench:38d26e7c2818fe06a110cdea0e23b9608f9c981df7b0aee9ba897fab6b19bc90"


@pytest.mark.parametrize("value,reason", [("x", "DATES_INVALID"), ("2026-02-30", "DATES_INVALID"),
    ("20261001", "DATES_INVALID"), ("2026-10-01T00:00:00Z", "DATES_INVALID"),
    (" 2026-10-01", "DATES_INVALID"), (None, "DATES_INVALID"), (True, "DATES_INVALID"),
    ("2026-10-02", "DATES_DUPLICATED")])
def test_invalid_or_duplicate_real_dates_never_verify_alignment(value, reason):
    supplied = rows()
    supplied[0]["current_return_dates"][0] = value
    built = strict_json(workbench.build_workbench(supplied))
    actual = pair(built)
    assert actual["status"] == "NOT_COMPARABLE" and actual["value"] is None
    assert actual["comparable"] is False and actual["date_alignment"] == reason


@pytest.mark.parametrize("value,reason", [(None, "NON_NUMERIC"), ("0.01", "NON_NUMERIC"),
    (True, "BOOLEAN_NOT_MEASUREMENT"), (False, "BOOLEAN_NOT_MEASUREMENT"),
    (float("nan"), "NONFINITE"), (float("inf"), "NONFINITE"), (float("-inf"), "NONFINITE"),
    (10 ** 400, "NUMERIC_RANGE_UNAVAILABLE")])
@pytest.mark.parametrize("dated", [True, False])
def test_all_return_points_must_be_typed_finite_without_boolean_coercion(value, reason, dated):
    supplied = rows()
    supplied[0]["current_returns"][0] = value
    if not dated:
        for row in supplied:
            row.pop("current_return_dates")
    actual = pair(strict_json(workbench.build_workbench(supplied)))
    assert actual["value"] is None and not actual["comparable"]
    assert actual["date_alignment"] == "RETURN_VALUES_" + reason


def test_bad_unshared_point_is_not_silently_pruned_and_other_pair_survives():
    supplied = rows()
    supplied[0]["current_returns"][0] = float("nan")
    supplied[1]["current_returns"] = supplied[1]["current_returns"][1:]
    supplied[1]["current_return_dates"] = DATES[1:]
    supplied.append({"ticker": "CCC", "current_returns": [.04, -.01, .03], "current_return_dates": DATES[1:]})
    built = strict_json(workbench.build_workbench(supplied))
    assert pair(built)["date_alignment"] == "RETURN_VALUES_NONFINITE"
    assert pair(built, "AAA", "CCC")["comparable"] is False
    assert pair(built, "BBB", "CCC")["comparable"] is True
    assert pair(built, "BBB", "CCC")["aligned_points"] == 3


@pytest.mark.parametrize("series,reason", [(None, "RETURN_SERIES_PRESENT_NULL"), ("bad", "RETURN_SERIES_INVALID_SHAPE"),
    ({}, "RETURN_SERIES_INVALID_SHAPE"), ((.01, .02), "RETURN_SERIES_INVALID_SHAPE")])
def test_missing_null_and_malformed_series_are_distinct(series, reason):
    supplied = rows()
    supplied[0]["current_returns"] = series
    actual = pair(strict_json(workbench.build_workbench(supplied)))
    assert actual["value"] is None and not actual["comparable"]
    assert actual["date_alignment"] == reason


@pytest.mark.parametrize("series", [[1e308, -1e308, 1e308, -1e308], [1e154, -1e154, 1e154, -1e154]])
def test_finite_extremes_cannot_emit_nonfinite_pearson(series):
    supplied = rows()
    supplied[0]["current_returns"] = series
    actual = pair(strict_json(workbench.build_workbench(supplied)))
    assert actual["value"] is None and actual["status"] == "NOT_COMPARABLE"
    assert actual["date_alignment"] == "CORRELATION_NUMERICAL_UNAVAILABLE"


@pytest.mark.parametrize("series", [[0, 0, 0, 0], [1e-200, -1e-200, 1e-200, -1e-200]])
def test_constant_or_underflowing_variance_has_no_positive_comparability(series):
    supplied = rows()
    supplied[0]["current_returns"] = series
    actual = pair(strict_json(workbench.build_workbench(supplied)))
    assert actual["value"] is None and actual["status"] == "NOT_COMPARABLE"
    assert not actual["comparable"]


def test_alignment_sorts_shared_canonical_dates_without_calendar_or_pit_inference():
    supplied = rows()
    baseline = workbench.build_workbench(supplied)
    supplied[1]["current_returns"].reverse()
    supplied[1]["current_return_dates"].reverse()
    built = workbench.build_workbench(list(reversed(supplied)))
    assert built == baseline
    assert pair(built)["authority"] == "CURRENT_RESEARCH_ONLY_NOT_PIT"
    supplied[1]["current_returns"] = supplied[1]["current_returns"][:2]
    supplied[1]["current_return_dates"] = supplied[1]["current_return_dates"][:2]
    actual = pair(workbench.build_workbench(supplied))
    assert actual["value"] is None and actual["aligned_points"] == 2 and not actual["comparable"]


@pytest.mark.parametrize("value,reason", [(True, "BOOLEAN_NOT_MEASUREMENT"), (False, "BOOLEAN_NOT_MEASUREMENT"),
    (None, "PRESENT_NULL"), ("10", "NON_NUMERIC"), (float("nan"), "NONFINITE"),
    (float("inf"), "NONFINITE"), (float("-inf"), "NONFINITE"), (10 ** 400, "NUMERIC_RANGE_UNAVAILABLE")])
def test_malformed_objective_is_rejected_without_reordering_valid_members(value, reason):
    supplied = rows()
    supplied.append({"ticker": "CCC", "measurements": {"objective": value}})
    supplied.append({"ticker": "DDD", "measurements": {}})
    result = strict_json(workbench.build_workbench(supplied, objective="objective"))
    actual = result["ranking"]
    assert actual["ordered_tickers"] == ["AAA", "BBB"]  # Real zero and negative stay numbers.
    assert actual["measurement_missing"] == ["CCC", "DDD"]
    assert actual["measurement_rejected"] == {"CCC": reason}
    assert actual["is_capital_allocation"] is False and result["is_actionable"] is False


def test_exact_duplicates_normalize_and_conflicting_duplicates_refuse_both_orders():
    supplied = rows()
    duplicate = deepcopy(supplied[0])
    duplicate["ticker"] = " aaa "
    exact = workbench.build_workbench(supplied + [duplicate])
    assert exact == workbench.build_workbench([duplicate] + list(reversed(supplied)))
    assert exact["member_count"] == 2 and exact["duplicate_tickers_collapsed"] == ["AAA"]
    for key, value in [("sector", "different"), ("current_returns", [.1, .2, .3, .4]),
                       ("current_returns", tuple(duplicate["current_returns"])), ("measurements", {"objective": 99})]:
        conflict = {**duplicate, key: value}
        for candidates in ([*supplied, conflict], [conflict, *supplied]):
            with pytest.raises(ValueError, match="CONFLICTING_DUPLICATE_TICKER"):
                workbench.build_workbench(candidates)
