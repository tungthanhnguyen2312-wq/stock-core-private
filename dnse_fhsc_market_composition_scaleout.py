"""Fail-closed cross-sectional DNSE/FHSC market-composition scale-out."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "dnse_fhsc_market_composition_scaleout/v1"
DNSE_EQUALS_MATCHED = "DNSE_EQUALS_MATCHED"
DNSE_EQUALS_TOTAL = "DNSE_EQUALS_TOTAL"
DNSE_EQUALS_PUT_THROUGH = "DNSE_EQUALS_PUT_THROUGH"
DNSE_EQUALS_NONE = "DNSE_EQUALS_NONE"
NON_DISCRIMINATING_ZERO_PUT_THROUGH = "NON_DISCRIMINATING_ZERO_PUT_THROUGH"
NOT_COMPARABLE = "NOT_COMPARABLE"
DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE = "DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"dnse_fhsc_market_composition_scaleout:{digest}"}


def _nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def classify_volume(dnse_value: Any, trading: Mapping[str, Any]) -> str:
    """Classify one exact observation without assigning a generic value by label."""
    if not _nonnegative_integer(dnse_value) or not trading.get("retained_arithmetic_identity"):
        return NOT_COMPARABLE
    matched, put_through, total = (trading.get(name) for name in ("matched_volume", "put_through_volume", "total_volume"))
    if not all(_nonnegative_integer(value) for value in (matched, put_through, total)):
        return NOT_COMPARABLE
    if put_through == 0:
        return NON_DISCRIMINATING_ZERO_PUT_THROUGH if dnse_value == matched == total else DNSE_EQUALS_NONE
    hits = [(DNSE_EQUALS_MATCHED, matched), (DNSE_EQUALS_PUT_THROUGH, put_through), (DNSE_EQUALS_TOTAL, total)]
    matched_labels = [label for label, value in hits if dnse_value == value]
    return matched_labels[0] if len(matched_labels) == 1 else DNSE_EQUALS_NONE


def _keyed(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(row.get("instrument", "")).upper(), str(row.get("session", ""))): dict(row) for row in rows}


def _candidate(rows: list[Mapping[str, Any]], *, require_multiple_exchanges: bool) -> str:
    discriminating = [row for row in rows if row.get("classification") not in {NON_DISCRIMINATING_ZERO_PUT_THROUGH, NOT_COMPARABLE}]
    if not discriminating:
        return "NO_UNIVERSAL_VOLUME_MAPPING"
    labels = {row["classification"] for row in discriminating}
    if labels != {DNSE_EQUALS_MATCHED} or any(row.get("fhsc_history_classification") != "FHSC_HISTORY_EQUALS_MATCHED" for row in discriminating):
        return "NO_UNIVERSAL_VOLUME_MAPPING"
    if len({row["ticker"] for row in discriminating}) < 2:
        return "NO_UNIVERSAL_VOLUME_MAPPING"
    if require_multiple_exchanges and len({row["exchange"] for row in discriminating}) < 2:
        return "NO_UNIVERSAL_VOLUME_MAPPING"
    return ("DNSE_MATCHED_VOLUME_SEMANTICS_SCALEOUT_VALIDATED" if require_multiple_exchanges
            else "DNSE_MATCHED_VOLUME_SEMANTICS_HOSE_SCALEOUT_VALIDATED")


def reconcile_scaleout(
    dnse_rows: Iterable[Mapping[str, Any]], trading_rows: Iterable[Mapping[str, Any]],
    *, fhsc_history_rows: Iterable[Mapping[str, Any]], exchange_by_ticker: Mapping[str, str], expected_keys: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    """Join the fixed cohort; missing rows remain visible and never become zeroes."""
    dnse, trading, history = _keyed(dnse_rows), _keyed(trading_rows), _keyed(fhsc_history_rows)
    matrix: list[dict[str, Any]] = []
    for ticker, session in sorted(expected_keys):
        d, t, h = dnse.get((ticker, session)), trading.get((ticker, session)), history.get((ticker, session))
        exchange = exchange_by_ticker[ticker]
        if d is None or t is None or h is None:
            missing = [name for name, value in (("DNSE_OHLC", d), ("FHSC_HISTORY", h), ("FHSC_TRADING", t)) if value is None]
            matrix.append({"ticker": ticker, "session": session, "exchange": exchange, "classification": NOT_COMPARABLE,
                           "unavailable_reason": "_AND_".join(missing) + "_MISSING"})
            continue
        classification = classify_volume(d.get("raw_value"), t)
        history_classification = (
            "FHSC_HISTORY_EQUALS_MATCHED" if h.get("volume") == t.get("matched_volume") and t.get("put_through_volume", 0) > 0
            else "FHSC_HISTORY_NON_DISCRIMINATING_ZERO_PUT_THROUGH" if h.get("volume") == t.get("matched_volume") == t.get("total_volume") and t.get("put_through_volume") == 0
            else "FHSC_HISTORY_DISAGREEMENT"
        )
        matrix.append({"ticker": ticker, "session": session, "exchange": exchange, "dnse_ohlc_volume": d.get("raw_value"),
                       "fhsc_history_volume": h.get("volume"), "fhsc_history_classification": history_classification, "fhsc_matched_volume": t.get("matched_volume"), "fhsc_put_through_volume": t.get("put_through_volume"),
                       "fhsc_total_volume": t.get("total_volume"), "fhsc_identity_retained_exact": t.get("retained_arithmetic_identity"),
                       "classification": classification})
    counts = Counter(row["classification"] for row in matrix)
    exchange_summary = {}
    for exchange in sorted(set(exchange_by_ticker.values())):
        rows = [row for row in matrix if row["exchange"] == exchange]
        per = Counter(row["classification"] for row in rows)
        exchange_summary[exchange] = {"total_rows": len(rows), "discriminating_rows": sum(row["classification"] not in {NON_DISCRIMINATING_ZERO_PUT_THROUGH, NOT_COMPARABLE} for row in rows),
                                      "matched_rows": per[DNSE_EQUALS_MATCHED], "total_rows_match": per[DNSE_EQUALS_TOTAL],
                                      "put_through_rows": per[DNSE_EQUALS_PUT_THROUGH], "contradictory_rows": per[DNSE_EQUALS_NONE],
                                      "non_discriminating_rows": per[NON_DISCRIMINATING_ZERO_PUT_THROUGH], "unavailable_rows": per[NOT_COMPARABLE],
                                      "candidate": _candidate(rows, require_multiple_exchanges=False)}
    contradictions = counts[DNSE_EQUALS_NONE]
    return {"volume_matrix": matrix, "aggregate_summary": {"total_comparable_rows": len(matrix) - counts[NOT_COMPARABLE],
            "discriminating_rows": len(matrix) - counts[NOT_COMPARABLE] - counts[NON_DISCRIMINATING_ZERO_PUT_THROUGH],
            "dnse_equals_matched": counts[DNSE_EQUALS_MATCHED], "dnse_equals_total": counts[DNSE_EQUALS_TOTAL],
            "dnse_equals_put_through": counts[DNSE_EQUALS_PUT_THROUGH], "contradictory_rows": contradictions,
            "non_discriminating_rows": counts[NON_DISCRIMINATING_ZERO_PUT_THROUGH], "unavailable_rows": counts[NOT_COMPARABLE]},
            "exchange_specific_summary": exchange_summary, "candidate_mapping": _candidate(matrix, require_multiple_exchanges=True),
            "authority_effect": "NONE", "liquidity_authority": False, "position_sizing_safe": False}


def value_matrix(trading_rows: Iterable[Mapping[str, Any]], *, exchange_by_ticker: Mapping[str, str], expected_keys: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Retain explicit FHSC values while fail-closing the absent DNSE comparator."""
    indexed = _keyed(trading_rows); matrix = []
    for ticker, session in sorted(expected_keys):
        row = indexed.get((ticker, session))
        if row is None:
            matrix.append({"ticker": ticker, "session": session, "exchange": exchange_by_ticker[ticker],
                           "dnse_value_classification": DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE,
                           "fhsc_value_availability": "FHSC_TRADING_VALUE_OBSERVATION_MISSING"})
            continue
        matrix.append({"ticker": row["instrument"], "session": row["session"], "exchange": exchange_by_ticker[row["instrument"]],
                       "fhsc_matched_value": row.get("matched_value"), "fhsc_put_through_value": row.get("put_through_value"),
                       "fhsc_total_value": row.get("total_value"), "fhsc_identity_retained_exact": row.get("retained_value_arithmetic_identity"),
                       "dnse_value_classification": DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE, "fhsc_value_availability": "OBSERVED"})
    return {"matrix": matrix, "aggregate_summary": {"total_comparable_rows": 0, "discriminating_rows": 0,
            "dnse_equals_matched": 0, "dnse_equals_total": 0, "dnse_equals_put_through": 0, "contradictory_rows": 0,
            "non_discriminating_rows": 0, "unavailable_rows": len(matrix)},
            "verdict": "DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE", "authority_effect": "NONE"}
