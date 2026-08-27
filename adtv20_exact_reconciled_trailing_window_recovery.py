"""ADTV20 exact-reconciled trailing-window recovery inside the existing matched-value lane.

Follow-on to ADTV20_WINDOW_INTEGRITY_AND_CONFLICT_QUALIFICATION_V1 /
HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY_V1. Not a new architecture lane.

Reuses the existing G1 formula, trailing-20 calendar, HOSE discriminating-exact
applicability, and conflict taxonomy. Does not emit ADV20_MATCHED_VOLUME,
liquidity, sizing, execution, ranking, or PIT/RAW_AS_TRADED authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dnse_fhsc_volume_basis import parse_fhsc_trading_history
from field_temporal_contract import stable_id
from fhsc_retained_live_reconciliation import FHSC_BASE_URL, TIER1_HEADER_NAME, load_finhay_api_key
from historical_matched_traded_value_authority import (
    MATCHED_VALUE_FORMULA,
    QUALIFIED_BOARD,
    reconcile_fhsc_anchor,
    summarize_complete_trade_session,
)
from historical_matched_trading_value_authority import (
    ADTV20_BLOCKED,
    ADTV20_NOT_APPLICABLE,
    ADTV20_PARTIAL,
    ADTV20_READY,
    APPLICABLE_EXCHANGES,
    CONFLICT_FHSC_INCLUDES_G4_RAW_SHARES,
    EXPECTED_ADTV_SESSIONS,
    adtv20_matched_value,
    adv20_matched_volume_status,
    classify_conflict_cause,
    classify_session_discrimination,
    session_value_reconciliation,
    trailing_expected_sessions,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers

CONTRACT_VERSION = "adtv20_exact_reconciled_trailing_window_recovery/v1"
ARTIFACT_TYPE = "ADTV20_EXACT_RECONCILED_TRAILING_WINDOW_RECOVERY"
FEATURE_ADTV20 = "ADTV20_MATCHED_VALUE"
FHSC_HISTORY_PATH = "/market/stocks/{symbol}/trading/history"
FHSC_HISTORY_FROM = "2026-06-17"
FHSC_HISTORY_TO = "2026-08-25"
DEFAULT_REQUEST_BUDGET = 6
STRUCTURALLY_ABSENT_TRADES_PAIRS = (
    ("POM", "2026-07-13"),
    ("VCI", "2026-07-13"),
    ("HPH", "2026-07-14"),
    ("SGR", "2026-07-14"),
    ("OCH", "2026-07-15"),
    ("CT3", "2026-07-16"),
    ("ONE", "2026-08-11"),
)

STATE_QUALIFIED_G1_EXACT = "QUALIFIED_G1_EXACT"
STATE_NUMERIC_EXACT_NON_DISCRIMINATING = "NUMERIC_EXACT_NON_DISCRIMINATING"
STATE_CONFLICT_G1_VS_FHSC = "CONFLICT_G1_VS_FHSC"
STATE_G1_PLUS_G4_CONFLICT = "G1_PLUS_G4_CONFLICT_PATTERN"
STATE_FHSC_MISSING = "FHSC_MISSING"
STATE_DNSE_TRADES_MISSING = "DNSE_TRADES_MISSING"
STATE_STRUCTURALLY_ABSENT = "STRUCTURALLY_ABSENT"
STATE_EXCHANGE_NOT_APPLICABLE = "EXCHANGE_NOT_APPLICABLE"
STATE_NOT_COMPARABLE = "NOT_COMPARABLE"

CELL_STATES = (
    STATE_QUALIFIED_G1_EXACT,
    STATE_NUMERIC_EXACT_NON_DISCRIMINATING,
    STATE_CONFLICT_G1_VS_FHSC,
    STATE_G1_PLUS_G4_CONFLICT,
    STATE_FHSC_MISSING,
    STATE_DNSE_TRADES_MISSING,
    STATE_STRUCTURALLY_ABSENT,
    STATE_EXCHANGE_NOT_APPLICABLE,
    STATE_NOT_COMPARABLE,
)

OUTCOME_A = "OUTCOME_A_TRAILING20_QUALIFICATION_DEEPENED"
OUTCOME_B = "OUTCOME_B_BOUNDED_ACQUISITION_PARTIAL"
OUTCOME_C = "OUTCOME_C_CURRENT_SOURCE_CEILING_ESTABLISHED"

ROOT = Path(__file__).resolve().parent
DEFAULT_OFFICIAL_UNIVERSE = (
    ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
    / "current_official_market_universe_artifact.json"
)
DEFAULT_SCALEOUT_DIR = ROOT / "operations-review" / "fhsc-historical-matched-value-coverage-scaleout-v1"
DEFAULT_OUT_DIR = ROOT / "operations-review" / "adtv20-exact-reconciled-trailing-window-recovery-v1"

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "qualified_liquidity_inputs": False,
    "position_sizing_is_safe": False,
    "adv20_matched_volume": "NOT_EMITTED",
    "raw_as_traded": "NOT_PROMOTED",
    "pit": "BLOCKED",
    "ranking": False,
    "recommendation": False,
    "target": False,
    "probability": False,
    "portfolio": False,
    "adtv20_is_not_safe_position_size": True,
    "adtv20_is_not_executable_capacity": True,
}


def _load_json(path: Path) -> Any:
    return json_loads(path.read_text(encoding="utf-8"))


def json_loads(text: str) -> Any:
    import json
    return json.loads(text)


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"


def exchange_by_ticker(official_universe: Mapping[str, Any], tickers: Sequence[str]) -> dict[str, str]:
    records = official_universe.get("records") or {}
    return {ticker: str((records.get(ticker) or {}).get("exchange_or_market") or "") for ticker in tickers}


def classify_cell(
    *,
    ticker: str,
    session: str,
    exchange: str,
    qualified_row: Mapping[str, Any] | None,
    recon_row: Mapping[str, Any] | None,
    structurally_absent: bool,
) -> str:
    if structurally_absent:
        return STATE_STRUCTURALLY_ABSENT
    if qualified_row is not None:
        discrimination = classify_session_discrimination(qualified_row.get("board_composition") or [])
        if exchange in APPLICABLE_EXCHANGES and discrimination["status"] == "DISCRIMINATING":
            return STATE_QUALIFIED_G1_EXACT
        if discrimination["status"] != "DISCRIMINATING":
            return STATE_NUMERIC_EXACT_NON_DISCRIMINATING
        return STATE_EXCHANGE_NOT_APPLICABLE
    if recon_row is not None:
        status = recon_row.get("status")
        if status == "CONFLICT":
            composition = recon_row.get("board_composition")
            if composition:
                cause = classify_conflict_cause({**recon_row, "board_composition": composition})
                if cause["cause"] == CONFLICT_FHSC_INCLUDES_G4_RAW_SHARES:
                    return STATE_G1_PLUS_G4_CONFLICT
            return STATE_CONFLICT_G1_VS_FHSC
        if status == "NOT_COMPARABLE":
            return STATE_NOT_COMPARABLE
        if status == "EXACT":
            return STATE_NUMERIC_EXACT_NON_DISCRIMINATING
        return STATE_NOT_COMPARABLE
    return STATE_FHSC_MISSING


def inventory_trailing20(
    *,
    tickers: Sequence[str],
    exchanges: Mapping[str, str],
    window: Sequence[str],
    qualified_rows: Sequence[Mapping[str, Any]],
    recon_rows: Sequence[Mapping[str, Any]],
    structurally_absent: Iterable[tuple[str, str]] = STRUCTURALLY_ABSENT_TRADES_PAIRS,
) -> dict[str, Any]:
    """Classify every official ticker × expected trailing-20 session. Residual must be 0."""
    window = list(window)
    expected = len(tickers) * len(window)
    absent = {(str(ticker), str(session)) for ticker, session in structurally_absent}
    q_index = {(str(row["ticker"]), str(row["session"])): row for row in qualified_rows}
    r_index = {(str(row["ticker"]), str(row["session"])): row for row in recon_rows}
    counts: Counter[str] = Counter()
    hose_counts: Counter[str] = Counter()
    per_ticker: dict[str, dict[str, Any]] = {}
    fhsc_missing_by_session: Counter[str] = Counter()
    cells_by_ticker: dict[str, dict[str, str]] = {}
    for ticker in tickers:
        exchange = str(exchanges.get(ticker) or "")
        cell_states: dict[str, str] = {}
        state_count: Counter[str] = Counter()
        for session in window:
            state = classify_cell(
                ticker=ticker,
                session=session,
                exchange=exchange,
                qualified_row=q_index.get((ticker, session)),
                recon_row=r_index.get((ticker, session)),
                structurally_absent=(ticker, session) in absent,
            )
            cell_states[session] = state
            state_count[state] += 1
            counts[state] += 1
            if exchange in APPLICABLE_EXCHANGES:
                hose_counts[state] += 1
            if state == STATE_FHSC_MISSING:
                fhsc_missing_by_session[session] += 1
        cells_by_ticker[ticker] = cell_states
        qualified = int(state_count[STATE_QUALIFIED_G1_EXACT])
        per_ticker[ticker] = {
            "ticker": ticker,
            "exchange_or_market": exchange or None,
            "qualified_session_count": qualified,
            "missing_session_count": int(state_count[STATE_FHSC_MISSING] + state_count[STATE_DNSE_TRADES_MISSING] + state_count[STATE_STRUCTURALLY_ABSENT]),
            "conflicting_session_count": int(state_count[STATE_CONFLICT_G1_VS_FHSC] + state_count[STATE_G1_PLUS_G4_CONFLICT]),
            "non_discriminating_session_count": int(state_count[STATE_NUMERIC_EXACT_NON_DISCRIMINATING]),
            "not_comparable_session_count": int(state_count[STATE_NOT_COMPARABLE]),
            "restricted_scope_session_count": int(state_count[STATE_EXCHANGE_NOT_APPLICABLE]),
            "fhsc_missing_sessions": [session for session, state in cell_states.items() if state == STATE_FHSC_MISSING],
            "qualified_sessions": [session for session, state in cell_states.items() if state == STATE_QUALIFIED_G1_EXACT],
            "cell_states": cell_states,
        }
    accounted = sum(counts.values())
    residual = expected - accounted
    if residual != 0:
        raise ValueError(f"TRAILING20_INVENTORY_RESIDUAL_NONZERO:expected={expected} accounted={accounted} residual={residual}")
    hole_sessions = [session for session in window if fhsc_missing_by_session[session] == len(tickers)]
    return {
        "expected_ticker_session_pairs": expected,
        "accounted": accounted,
        "residual": residual,
        "window": window,
        "state_counts": {state: int(counts[state]) for state in CELL_STATES},
        "hose_state_counts": {state: int(hose_counts[state]) for state in CELL_STATES},
        "fhsc_missing_by_session": dict(fhsc_missing_by_session),
        "session_wide_fhsc_holes": hole_sessions,
        "per_ticker": per_ticker,
        "cells_by_ticker": cells_by_ticker,
    }


def acquisition_plan(
    inventory: Mapping[str, Any],
    *,
    budget: int = DEFAULT_REQUEST_BUDGET,
) -> dict[str, Any]:
    """Deterministic cohort: HOSE names whose only trailing-20 gap is FHSC_MISSING, closest to 20/20."""
    rows = []
    for ticker, rec in (inventory.get("per_ticker") or {}).items():
        if rec.get("exchange_or_market") not in APPLICABLE_EXCHANGES:
            continue
        qualified = int(rec["qualified_session_count"])
        fhsc_missing = list(rec.get("fhsc_missing_sessions") or [])
        conflict = int(rec["conflicting_session_count"])
        nondisc = int(rec["non_discriminating_session_count"])
        not_comparable = int(rec["not_comparable_session_count"])
        sole = qualified > 0 and fhsc_missing and conflict == 0 and nondisc == 0 and not_comparable == 0
        if not sole:
            continue
        rows.append({
            "ticker": ticker,
            "qualified_session_count": qualified,
            "fhsc_missing_sessions": fhsc_missing,
            "sole_blocker": STATE_FHSC_MISSING,
            "distance_to_ready": EXPECTED_ADTV_SESSIONS - qualified,
        })
    rows.sort(key=lambda item: (-item["qualified_session_count"], item["ticker"]))
    selected = rows[: max(0, int(budget))]
    return {
        "request_budget": int(budget),
        "route": f"FHSC {FHSC_HISTORY_PATH}",
        "route_role": "SUPPLEMENTAL_BOUNDED",
        "canonical_market_data_provider": "DNSE_LIVESPEED",
        "selection_rule": "HOSE_TICKERS_SOLE_BLOCKER_FHSC_MISSING_CLOSEST_TO_20_OF_20",
        "eligible_count": len(rows),
        "selected": selected,
        "session_wide_fhsc_holes": list(inventory.get("session_wide_fhsc_holes") or []),
    }


def fetch_fhsc_history_once(
    symbol: str,
    *,
    api_key: str,
    start: str = FHSC_HISTORY_FROM,
    end: str = FHSC_HISTORY_TO,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Exactly one GET. No cache, no sleep, no retry."""
    params = {"from": start, "to": end, "resolution": "1D"}
    path = f"/market/stocks/{symbol}/trading/history"
    url = f"{FHSC_BASE_URL}{path}?{urlencode(params)}"
    retrieval_time = datetime.now(UTC).isoformat()
    req = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})
    open_fn = opener or (lambda request, timeout=30: urlopen(request, timeout=timeout))
    try:
        with open_fn(req, timeout=30) as response:
            body = response.read()
            status = int(getattr(response, "status", 200) or 200)
            mime = None
            headers = getattr(response, "headers", None)
            if headers is not None and hasattr(headers, "get_content_type"):
                mime = headers.get_content_type()
    except HTTPError as error:
        return {
            "symbol": symbol,
            "endpoint": path,
            "request_parameters": params,
            "request_url": url,
            "retrieval_time": retrieval_time,
            "http_status": int(error.code),
            "successful": False,
            "failure_disposition": f"HTTP_ERROR_{int(error.code)}",
            "raw_response_retained": False,
            "rate_limited": int(error.code) == 429,
        }
    except OSError as error:
        return {
            "symbol": symbol,
            "endpoint": path,
            "request_parameters": params,
            "request_url": url,
            "retrieval_time": retrieval_time,
            "successful": False,
            "failure_disposition": f"NETWORK_ERROR_{type(error).__name__}",
            "raw_response_retained": False,
            "rate_limited": False,
        }
    digest = sha256(body).hexdigest()
    return {
        "symbol": symbol,
        "endpoint": path,
        "request_parameters": params,
        "request_url": url,
        "retrieval_time": retrieval_time,
        "http_status": status,
        "mime_type": mime,
        "successful": status == 200,
        "raw_response_retained": True,
        "raw_sha256": digest,
        "raw_bytes": body,
        "rate_limited": False,
    }


def run_bounded_acquisition(
    plan: Mapping[str, Any],
    *,
    api_key: str | None,
    raw_dir: Path,
    budget: int | None = None,
    opener: Callable[..., Any] | None = None,
    fetcher: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    selected = list(plan.get("selected") or [])
    limit = int(budget if budget is not None else plan.get("request_budget") or DEFAULT_REQUEST_BUDGET)
    records: list[dict[str, Any]] = []
    sent = 0
    if not selected:
        return {
            "request_budget": limit,
            "requests_sent": 0,
            "http_disposition": {},
            "records": [],
            "terminated_reason": "EMPTY_COHORT",
            "new_fhsc_sessions": {},
        }
    if not api_key and fetcher is None:
        return {
            "request_budget": limit,
            "requests_sent": 0,
            "http_disposition": {},
            "records": [],
            "terminated_reason": "API_KEY_UNAVAILABLE",
            "new_fhsc_sessions": {},
        }
    raw_dir.mkdir(parents=True, exist_ok=True)
    new_sessions: dict[str, list[str]] = {}
    terminated = "COMPLETED"
    for item in selected:
        if sent >= limit:
            terminated = "BUDGET_EXHAUSTED"
            break
        ticker = str(item["ticker"])
        sent += 1
        rec = dict((fetcher or fetch_fhsc_history_once)(ticker, api_key=api_key, opener=opener))
        raw_bytes = rec.pop("raw_bytes", None)
        if rec.get("rate_limited"):
            records.append(rec)
            terminated = "RATE_LIMITED"
            break
        if rec.get("successful") and raw_bytes:
            path = raw_dir / f"{ticker}_stock_trading_history_{rec['raw_sha256'][:16]}.json"
            if not path.exists():
                path.write_bytes(raw_bytes)
            try:
                rec["raw_path"] = path.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                rec["raw_path"] = path.as_posix()
            parsed = parse_fhsc_trading_history(raw_bytes, instrument=ticker)
            sessions = [
                str(row["session"])
                for row in (parsed.get("rows") or [])
                if row.get("parse_status") == "PARSED" and row.get("session")
            ]
            rec["parsed_session_count"] = len(sessions)
            rec["has_target_sessions"] = {
                session: session in sessions for session in item.get("fhsc_missing_sessions") or []
            }
            rec["parsed_rows_by_session"] = {
                str(row["session"]): row
                for row in (parsed.get("rows") or [])
                if row.get("parse_status") == "PARSED" and row.get("session")
            }
            new_sessions[ticker] = sessions
        records.append(rec)
    disposition = Counter(
        ("HTTP_" + str(row.get("http_status"))) if row.get("http_status") else row.get("failure_disposition") or "UNKNOWN"
        for row in records
    )
    return {
        "request_budget": limit,
        "requests_sent": sent,
        "http_disposition": dict(disposition),
        "records": records,
        "terminated_reason": terminated,
        "new_fhsc_sessions": new_sessions,
    }


def evaluation_rows_from_qualified(qualified_rows: Sequence[Mapping[str, Any]], exchanges: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in qualified_rows:
        ticker = str(row.get("ticker") or "")
        exchange = exchanges.get(ticker) or row.get("exchange_or_market")
        evaluated = dict(row)
        evaluated["value_reconciliation"] = session_value_reconciliation(evaluated, exchange=exchange)
        evaluated["matched_trading_value_vnd"] = evaluated.get("matched_value_vnd")
        evaluated["exchange_or_market"] = exchange
        rows.append(evaluated)
    return rows


def merge_new_exact_row(
    existing: Sequence[Mapping[str, Any]],
    new_row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Upgrade only the exact ticker/session cell. No cross-ticker/session copy."""
    ticker = str(new_row.get("ticker") or "")
    session = str(new_row.get("session") or "")
    merged = [dict(row) for row in existing if not (str(row.get("ticker")) == ticker and str(row.get("session")) == session)]
    merged.append(dict(new_row))
    return merged


def recompute_adtv20(
    rows: Sequence[Mapping[str, Any]],
    *,
    tickers: Sequence[str],
    exchanges: Mapping[str, str],
    window: Sequence[str],
) -> dict[str, Any]:
    features = adtv20_matched_value(
        rows,
        expected_trading_sessions=window,
        exchange_by_ticker=exchanges,
        tickers=tickers,
    )
    counts = Counter(str(item["status"]) for item in features.values())
    return {
        "features": features,
        "ready_count": int(counts.get(ADTV20_READY, 0)),
        "partial_count": int(counts.get(ADTV20_PARTIAL, 0)),
        "blocked_count": int(counts.get(ADTV20_BLOCKED, 0)),
        "not_applicable_count": int(counts.get(ADTV20_NOT_APPLICABLE, 0)),
    }


def reconcile_acquired_session(
    *,
    ticker: str,
    session: str,
    fhsc_row: Mapping[str, Any],
    dnse_pages: Sequence[Mapping[str, Any]] | None,
    raw_payload_hashes: Sequence[str] | None = None,
    exchange: str | None = None,
) -> dict[str, Any] | None:
    if not dnse_pages:
        return None
    candidate = summarize_complete_trade_session(
        ticker=ticker, session=session, pages=dnse_pages, raw_payload_hashes=raw_payload_hashes or ["acquired"],
    )
    anchor = {
        "ticker": ticker,
        "session": session,
        "fhsc_identity_retained_exact": True,
        "fhsc_matched_volume": fhsc_row.get("matched_volume"),
        "fhsc_matched_value": fhsc_row.get("matched_value"),
    }
    recon = reconcile_fhsc_anchor(candidate, anchor)
    candidate["fhsc_reconciliation"] = recon
    if recon["status"] == "EXACT":
        candidate["qualification_status"] = "MATCHED_VALUE_QUALIFIED"
    else:
        candidate["qualification_status"] = "CONFLICTING"
    candidate["value_reconciliation"] = session_value_reconciliation(candidate, exchange=exchange)
    candidate["matched_trading_value_vnd"] = candidate.get("matched_value_vnd")
    candidate["exchange_or_market"] = exchange
    return candidate


def build_recovery_artifact(
    *,
    inventory: Mapping[str, Any],
    plan: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    acquisition: Mapping[str, Any] | None,
    source_identities: Mapping[str, Any] | None = None,
    new_qualified_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    window = list(inventory.get("window") or [])
    before_ready = int(before.get("ready_count") or 0)
    after_ready = int(after.get("ready_count") or 0)
    sent = int((acquisition or {}).get("requests_sent") or 0)
    new_n = len(new_qualified_rows or [])
    if after_ready > before_ready and sent == 0:
        outcome = OUTCOME_A
    elif sent > 0 and (new_n > 0 or after_ready > before_ready):
        outcome = OUTCOME_B
    else:
        outcome = OUTCOME_C
    holes = list(inventory.get("session_wide_fhsc_holes") or [])
    reopening = (
        "Independent matched-value observation for session-wide FHSC hole(s) "
        + ",".join(holes)
        + " via the already-approved FHSC /market/stocks/{symbol}/trading/history route "
        "or another already-qualified independent matched-value field; then 20/20 HOSE "
        "discriminating exacts on the expected trailing window."
        if holes else
        "Additional independent FHSC matched-value observations for HOSE trailing-20 "
        "FHSC_MISSING cells closest to 20/20, without coercing G1+G4 conflicts."
    )
    compact_tickers = []
    after_features = after.get("features") or {}
    for ticker, rec in (inventory.get("per_ticker") or {}).items():
        feature = after_features.get(ticker) or {}
        compact_tickers.append({
            "ticker": ticker,
            "exchange_or_market": rec.get("exchange_or_market"),
            "status": feature.get("status"),
            "expected_session_count": EXPECTED_ADTV_SESSIONS,
            "qualified_session_count": feature.get("qualified_sessions", rec.get("qualified_session_count")),
            "missing_session_count": rec.get("missing_session_count"),
            "conflicting_session_count": rec.get("conflicting_session_count"),
            "non_discriminating_session_count": rec.get("non_discriminating_session_count"),
            "restricted_scope_session_count": rec.get("restricted_scope_session_count"),
            "qualified_window_sessions": feature.get("qualified_window_sessions") or rec.get("qualified_sessions"),
            "reason": feature.get("reason"),
        })
    compact_tickers.sort(key=lambda item: item["ticker"])
    payload = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "outcome": outcome,
        "matched_value_formula": MATCHED_VALUE_FORMULA,
        "qualified_board": QUALIFIED_BOARD,
        "g4_excluded_from_g1_matched_value": True,
        "trailing_window": window,
        "expected_sessions": EXPECTED_ADTV_SESSIONS,
        "inventory": {
            "expected_ticker_session_pairs": inventory.get("expected_ticker_session_pairs"),
            "accounted": inventory.get("accounted"),
            "residual": inventory.get("residual"),
            "state_counts": inventory.get("state_counts"),
            "hose_state_counts": inventory.get("hose_state_counts"),
            "fhsc_missing_by_session": inventory.get("fhsc_missing_by_session"),
            "session_wide_fhsc_holes": holes,
        },
        "acquisition_plan": {
            "request_budget": plan.get("request_budget"),
            "route": plan.get("route"),
            "route_role": plan.get("route_role"),
            "selection_rule": plan.get("selection_rule"),
            "eligible_count": plan.get("eligible_count"),
            "selected_tickers": [item["ticker"] for item in (plan.get("selected") or [])],
            "selected": plan.get("selected"),
        },
        "acquisition": None if acquisition is None else {
            "request_budget": acquisition.get("request_budget"),
            "requests_sent": acquisition.get("requests_sent"),
            "http_disposition": acquisition.get("http_disposition"),
            "terminated_reason": acquisition.get("terminated_reason"),
            "records": [
                {key: value for key, value in row.items() if key not in {"parsed_rows_by_session", "raw_bytes"}}
                for row in (acquisition.get("records") or [])
            ],
        },
        "new_qualified_observations": [
            {"ticker": row.get("ticker"), "session": row.get("session"),
             "value_reconciliation": row.get("value_reconciliation"),
             "matched_trading_value_vnd": row.get("matched_trading_value_vnd")}
            for row in (new_qualified_rows or [])
        ],
        "before": {
            "ready_count": before.get("ready_count"),
            "partial_count": before.get("partial_count"),
            "blocked_count": before.get("blocked_count"),
            "not_applicable_count": before.get("not_applicable_count"),
        },
        "after": {
            "ready_count": after.get("ready_count"),
            "partial_count": after.get("partial_count"),
            "blocked_count": after.get("blocked_count"),
            "not_applicable_count": after.get("not_applicable_count"),
        },
        "records": compact_tickers,
        "adv20_matched_volume": adv20_matched_volume_status(),
        "source_identities": dict(source_identities or {}),
        "reopening_gate": reopening,
        "authority_boundary": dict(AUTHORITY_BOUNDARIES),
        "authority_effect": "NONE",
    }
    digest = stable_id({key: value for key, value in payload.items()})
    payload["artifact_sha256"] = digest
    payload["artifact_identity"] = f"adtv20_exact_reconciled_trailing_window_recovery:{digest}"
    return payload


def load_retained_inputs(
    *,
    official_universe_path: Path = DEFAULT_OFFICIAL_UNIVERSE,
    scaleout_dir: Path = DEFAULT_SCALEOUT_DIR,
) -> dict[str, Any]:
    official = _load_json(official_universe_path)
    tickers = official_research_universe_tickers(official)
    exchanges = exchange_by_ticker(official, tickers)
    report = _load_json(scaleout_dir / "historical_matched_trading_value_authority_report.json")
    window = list((report.get("adtv20_contract") or {}).get("trailing_window") or [])
    if len(window) != EXPECTED_ADTV_SESSIONS:
        raise ValueError(f"RETAINED_TRAILING_WINDOW_NOT_20:{window}")
    qualified_rows = _load_json(scaleout_dir / "historical_matched_value_qualified_rows.json")
    recon = _load_json(scaleout_dir / "historical_matched_value_reconciliation_artifact.json")
    return {
        "official_universe": official,
        "tickers": tickers,
        "exchanges": exchanges,
        "window": window,
        "qualified_rows": qualified_rows,
        "recon_rows": recon.get("rows") or [],
        "source_identities": {
            "official_universe": official.get("artifact_identity"),
            "prior_matched_value_authority": report.get("artifact_identity"),
            "fhsc_openapi_capability": f"fhsc:{FHSC_HISTORY_PATH}",
            "dnse_trades_corpus": "DNSE:trades_history:40sessions",
        },
        "prior_counts": {
            "ready_count": report.get("adtv20_ready_count"),
            "partial_count": report.get("adtv20_partial_count"),
            "blocked_count": report.get("adtv20_blocked_count"),
            "not_applicable_count": report.get("adtv20_not_applicable_count"),
        },
    }
