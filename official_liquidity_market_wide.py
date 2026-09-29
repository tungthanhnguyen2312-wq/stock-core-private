"""Market-wide official-exchange liquidity operationalization (OFFICIAL_EXCHANGE_LIQUIDITY_MARKET_WIDE_OPERATIONALIZATION_V1).

WHAT THIS MODULE DECIDES (pure functions; no network, no file IO)
    * the acquisition-rights gate per exchange: which official routes may be called in bulk for
      bounded internal research, and which may not (access is not permission);
    * the governed-universe frame: for every governed ticker its official exchange, DNSE exchange,
      route exchange and resolution state, with the denominators kept distinct;
    * a deterministic, budgeted acquisition plan built from that frame and the already-retained
      official series, before any request is made;
    * the per-ticker coverage class, the seven-dimension fitness (reusing the merged
      ``liquidity_authority_contract``), the Daily research view, and the sizing-readiness matrix.

WHAT IT NEVER DECIDES
    Promotion beyond the merged contract. EXECUTION_CAPACITY, POSITION_SIZING and PIT_BACKTEST stay
    BLOCKED. Missing ADTV blocks only the liquidity-dependent use; it never marks a stock
    insufficient. A missing session is never zero-filled and never forward-filled.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

import dnse_trades_liquidity_basis as dimension_basis
import liquidity_authority_contract as contract
import official_exchange_trading_statistics as official
from market_wide_historical_matched_liquidity import COVERAGE_RESTRICTED_WINDOW, EXACT_WINDOW, INSUFFICIENT_WINDOW

CONTRACT_VERSION = "official_exchange_liquidity_research/v1"
MILESTONE = "OFFICIAL_EXCHANGE_LIQUIDITY_MARKET_WIDE_OPERATIONALIZATION_V1"

# ---------------------------------------------------------------------------------
# Coverage taxonomy
# ---------------------------------------------------------------------------------
EXACT_20_SESSION_WINDOW = "EXACT_20_SESSION_WINDOW"
PARTIAL_WINDOW = "PARTIAL_WINDOW"
SOURCE_NOT_SUPPORTED = "SOURCE_NOT_SUPPORTED"
TICKER_NOT_FOUND = "TICKER_NOT_FOUND"
EXCHANGE_IDENTITY_CONFLICT = "EXCHANGE_IDENTITY_CONFLICT"
TRANSFERRED_LISTING = "TRANSFERRED_LISTING"
ZERO_TRADING_VALID = "ZERO_TRADING_VALID"
MISSING_SESSION = "MISSING_SESSION"
HTTP_OR_SOURCE_FAILURE = "HTTP_OR_SOURCE_FAILURE"
SEMANTIC_CONFLICT = "SEMANTIC_CONFLICT"
PUBLIC_ACQUISITION_NOT_AUTHORIZED = "PUBLIC_ACQUISITION_NOT_AUTHORIZED"
COVERAGE_CLASSES = (
    EXACT_20_SESSION_WINDOW, PARTIAL_WINDOW, SOURCE_NOT_SUPPORTED, TICKER_NOT_FOUND, EXCHANGE_IDENTITY_CONFLICT,
    TRANSFERRED_LISTING, ZERO_TRADING_VALID, MISSING_SESSION, HTTP_OR_SOURCE_FAILURE, SEMANTIC_CONFLICT,
    PUBLIC_ACQUISITION_NOT_AUTHORIZED,
)

# ---------------------------------------------------------------------------------
# Acquisition rights gate
# ---------------------------------------------------------------------------------
AUTHORIZED_BOUNDED_INTERNAL = "AUTHORIZED_BOUNDED_INTERNAL_RESEARCH_ACQUISITION"
RIGHTS_REVIEWED_ON = "2026-09-29"
_HNX_APPROVAL = ("Written permission or an information-service agreement from HNX (Sở Giao dịch Chứng khoán Hà Nội) covering "
                 "automated retrieval of per-symbol end-of-day trading statistics for HNX and UPCoM, and stating whether "
                 "internal research retention and derived-figure publication are permitted.")
ACQUISITION_RIGHTS: dict[str, dict[str, Any]] = {
    official.HOSE: {
        "decision": AUTHORIZED_BOUNDED_INTERNAL,
        "access": "PUBLIC_NO_LOGIN_FIRST_PARTY_ROUTE",
        "robots": {"url": "https://www.hsx.vn/robots.txt", "finding": "User-agent * with an empty Disallow: all paths allowed",
                   "api_host_robots": "https://api.hsx.vn/robots.txt returns 404 (no directive)"},
        "terms_finding": "no restrictive terms, licence notice or anti-automation statement located on the public site or its "
                         "single-page-application bundle; no affirmative licence either",
        "automated_bulk": "PERMITTED_ONLY_AS_BOUNDED_FOREGROUND_PACED_RETRIEVAL_FOR_INTERNAL_RESEARCH",
        "internal_retention": "PERMITTED_PRIVATE_LOCAL_ONLY",
        "redistribution": "NOT_ESTABLISHED_RAW_BODIES_NEVER_PUBLISHED",
        "external_approval_needed": None,
    },
    official.HNX: {
        "decision": PUBLIC_ACQUISITION_NOT_AUTHORIZED,
        "access": "PUBLIC_NO_LOGIN_FIRST_PARTY_ROUTE",
        "robots": {"url": "https://hnx.vn/robots.txt", "finding": "HTTP 404: no directive published"},
        "terms_finding": "site footer asks that HNX be contacted before information from the site is published; HNX sells market "
                         "data through fee-based information packages (real-time, end-of-day, historical); no statement "
                         "authorises bulk automated retrieval",
        "automated_bulk": "NOT_AUTHORIZED_MARKET_WIDE_CRAWL_NOT_PERFORMED",
        "internal_retention": "ONLY_EVIDENCE_ALREADY_RETAINED_BY_THE_PRIOR_BOUNDED_QUALIFICATION_PROBE",
        "redistribution": "NOT_ESTABLISHED_RAW_BODIES_NEVER_PUBLISHED",
        "external_approval_needed": _HNX_APPROVAL,
    },
    official.UPCOM: {
        "decision": PUBLIC_ACQUISITION_NOT_AUTHORIZED,
        "access": "PUBLIC_NO_LOGIN_FIRST_PARTY_ROUTE",
        "robots": {"url": "https://hnx.vn/robots.txt", "finding": "HTTP 404: no directive published"},
        "terms_finding": "UPCoM statistics are served by the same HNX route and terms as HNX-listed securities",
        "automated_bulk": "NOT_AUTHORIZED_MARKET_WIDE_CRAWL_NOT_PERFORMED",
        "internal_retention": "ONLY_EVIDENCE_ALREADY_RETAINED_BY_THE_PRIOR_BOUNDED_QUALIFICATION_PROBE",
        "redistribution": "NOT_ESTABLISHED_RAW_BODIES_NEVER_PUBLISHED",
        "external_approval_needed": _HNX_APPROVAL,
    },
}

ACQUISITION_MODE_LIMITS = {"foreground_only": True, "background_daemon": False, "unbounded_pagination": False,
                           "attempts_per_planned_request": 1, "retry_classes": ("HTTP_429", "HTTP_502", "HTTP_503", "HTTP_504", "URLError", "TimeoutError"),
                           "max_retries_per_request": 1, "vnstock_kbs_vci_calls": False, "dnse_live_calls": False}

_OFFICIAL_PRESENT = frozenset({"OFFICIAL_CURRENT_EXCHANGE_SECURITY", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"})
_OFFICIAL_EXCHANGE = {"HOSE": official.HOSE, "HNX_LISTED": official.HNX, "HNX": official.HNX, "UPCOM": official.UPCOM}
_DNSE_MARKET_OF = {official.HOSE: "STO", official.HNX: "STX", official.UPCOM: "UPX"}


class OfficialLiquidityMarketWideError(ValueError):
    """Malformed operational input; never silently coerced."""


# ---------------------------------------------------------------------------------
# Governed-universe frame
# ---------------------------------------------------------------------------------

def frame_universe(official_records: Mapping[str, Mapping[str, Any]], dnse_resolved: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """One frame row per governed (``stocklookup_candidate``) ticker.

    ``exchange_resolution`` is AGREE (official master and DNSE bind the same exchange),
    OFFICIAL_ONLY (no DNSE tick binding), TRANSFER_EVIDENCE (DNSE's latest market differs but its
    retained prior-market boards name the official exchange), CONFLICT (they differ without that
    evidence, or DNSE trades a ticker the official master no longer lists) or UNRESOLVED (neither).
    Only AGREE / OFFICIAL_ONLY yield a ``route_exchange``. ACTIVE_UNIVERSE is never inferred.
    """
    frame: dict[str, dict[str, Any]] = {}
    for ticker in sorted(t for t, row in official_records.items() if isinstance(row, Mapping) and row.get("stocklookup_candidate")):
        row = official_records[ticker]
        present = row.get("current_universe_status") in _OFFICIAL_PRESENT
        official_exchange = _OFFICIAL_EXCHANGE.get(str(row.get("exchange_or_market"))) if present else None
        dnse = dnse_resolved.get(ticker) or {}
        dnse_exchange = dnse.get("exchange")
        prior_markets = sorted((dnse.get("prior_market_boards") or {}))
        if official_exchange and dnse_exchange == official_exchange:
            resolution, route = "AGREE", official_exchange
        elif official_exchange and dnse_exchange is None:
            resolution, route = "OFFICIAL_ONLY", official_exchange
        elif official_exchange and _DNSE_MARKET_OF[official_exchange] in prior_markets:
            resolution, route = "TRANSFER_EVIDENCE", None
        elif official_exchange or dnse_exchange:
            resolution, route = "CONFLICT", None
        else:
            resolution, route = "UNRESOLVED", None
        frame[ticker] = {
            "ticker": ticker, "official_exchange": official_exchange, "official_presence": present,
            "official_current_universe_status": row.get("current_universe_status"), "official_qualification": row.get("qualification"),
            "dnse_exchange": dnse_exchange, "dnse_state": dnse.get("state"), "dnse_prior_market_ids": prior_markets,
            "exchange_resolution": resolution, "route_exchange": route,
            "eligibility_reason": {"AGREE": "OFFICIAL_MASTER_AND_DNSE_EXCHANGE_AGREE", "OFFICIAL_ONLY": "OFFICIAL_MASTER_ONLY_NO_DNSE_BINDING",
                                   "TRANSFER_EVIDENCE": "DNSE_LATEST_MARKET_DIFFERS_PRIOR_MARKET_BOARDS_NAME_OFFICIAL_EXCHANGE",
                                   "CONFLICT": "OFFICIAL_MASTER_AND_DNSE_DISAGREE_WITHOUT_TRANSFER_EVIDENCE" if official_exchange or dnse_exchange else "",
                                   "UNRESOLVED": "NO_CURRENT_OFFICIAL_LISTING_AND_NO_DNSE_BINDING"}[resolution],
        }
    return frame


def universe_denominators(frame: Mapping[str, Mapping[str, Any]], *, retained_tickers: Iterable[str], rights: Mapping[str, Mapping[str, Any]] = ACQUISITION_RIGHTS) -> dict[str, Any]:
    retained = set(retained_tickers)

    def by_exchange(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(row.get(key)) for row in rows).items()))

    rows = list(frame.values())
    presence = [r for r in rows if r["official_presence"]]
    resolved = [r for r in rows if r["route_exchange"]]
    supported = [r for r in resolved if rights[r["route_exchange"]]["decision"] == AUTHORIZED_BOUNDED_INTERNAL or r["ticker"] in retained]
    return {
        "governed_universe": len(rows),
        "current_official_presence_denominator": {"count": len(presence), "by_exchange": by_exchange(presence, "official_exchange"),
                                                  "note": "current official exchange-list presence; ACTIVE_UNIVERSE authority remains UNKNOWN and is not manufactured"},
        "exchange_resolved_subset": {"count": len(resolved), "by_exchange": by_exchange(resolved, "route_exchange")},
        "source_supported_subset": {"count": len(supported), "by_exchange": by_exchange(supported, "route_exchange"),
                                    "definition": "exchange-resolved AND (route authorized for bounded internal acquisition OR series already retained)"},
        "exchange_resolution_counts": by_exchange(rows, "exchange_resolution"),
    }


# ---------------------------------------------------------------------------------
# Acquisition plan
# ---------------------------------------------------------------------------------

def retained_is_current(slot: Mapping[str, Any] | None, *, target_session: str) -> bool:
    """A retained series counts for the plan only if it parsed cleanly and reaches the target session."""
    return bool(slot) and not slot.get("parse_failures") and slot.get("newest") == target_session


def plan_acquisition(frame: Mapping[str, Mapping[str, Any]], retained: Mapping[str, Mapping[str, Any]], *, target_session: str,
                     hard_request_budget: int, rights: Mapping[str, Mapping[str, Any]] = ACQUISITION_RIGHTS) -> dict[str, Any]:
    """The frozen request list, made before any request. Only authorized exchanges get requests."""
    requests, reused, blocked = [], [], defaultdict(list)
    for ticker, row in sorted(frame.items()):
        route = row["route_exchange"]
        if route is None:
            continue
        if rights[route]["decision"] != AUTHORIZED_BOUNDED_INTERNAL:
            if not retained_is_current(retained.get(ticker), target_session=target_session):
                blocked[route].append(ticker)
            else:
                reused.append({"ticker": ticker, "exchange": route})
            continue
        if retained_is_current(retained.get(ticker), target_session=target_session):
            reused.append({"ticker": ticker, "exchange": route})
            continue
        requests.append(official.request_for(ticker, route, hose_page=1))
    retry_allowance = len(requests) // 10
    if len(requests) + retry_allowance > hard_request_budget:
        raise OfficialLiquidityMarketWideError(f"PLAN_EXCEEDS_HARD_REQUEST_BUDGET:{len(requests)}+{retry_allowance}>{hard_request_budget}")
    plan = {
        "schema_version": "1.0.0", "contract_version": "official_exchange_liquidity_acquisition_plan/v1", "milestone": MILESTONE,
        "target_session": target_session, "rights": {ex: {"decision": r["decision"]} for ex, r in rights.items()},
        "selection_rule": "every route-resolved ticker whose exchange route is AUTHORIZED and whose retained series does not already reach the target session",
        "depth": "HOSE tradingresult page 1 = the newest 20 sessions; no deeper pagination is planned",
        "limits": dict(ACQUISITION_MODE_LIMITS),
        "planned_requests": len(requests), "retry_allowance": retry_allowance, "hard_request_budget": hard_request_budget,
        "planned_by_exchange": dict(sorted(Counter(r["exchange"] for r in requests).items())),
        "reused_retained_by_exchange": dict(sorted(Counter(r["exchange"] for r in reused).items())),
        "not_authorized_not_planned": {ex: len(t) for ex, t in sorted(blocked.items())},
        "requests": requests, "reused": reused, "not_authorized_tickers": {ex: sorted(t) for ex, t in sorted(blocked.items())},
    }
    return {**plan, **contract.content_identity(plan, kind="official_exchange_liquidity_acquisition_plan")}


# ---------------------------------------------------------------------------------
# Reconciliation + board-unit requalification
# ---------------------------------------------------------------------------------

def reconcile_and_qualify(series: Mapping[str, Mapping[str, Any]], dnse_resolved: Mapping[str, Mapping[str, Any]],
                          dnse_ohlc: Mapping[str, Any], *, target_session: str) -> dict[str, Any]:
    """Reconcile every acquired ticker's DNSE board counters with its official row; requalify units."""
    reconciliations, evidence = {}, []
    for ticker, slot in sorted(series.items()):
        item = dnse_resolved.get(ticker) or {}
        if item.get("exchange") != slot["exchange"]:
            reconciliations[ticker] = {"verdict": "EXCHANGE_BINDING_MISMATCH", "dnse_exchange": item.get("exchange"), "exchange": slot["exchange"]}
            continue
        measures = contract.dnse_session_measures(item, session=target_session)
        recon = contract.reconcile_session(measures, slot["rows"].get(target_session), exchange=slot["exchange"])
        points = contract.stale_board_points(item, slot["rows"], exchange=slot["exchange"], target_session=target_session)
        ohlc_v = (((dnse_ohlc.get(ticker) or {}).get("body") or {}).get("v")) or []
        g1 = next((m for m in measures["_active_measures"] if m["board"] == "G1"), None)
        reconciliations[ticker] = {**recon, "active_boards": measures["active_boards"], "unknown_boards": measures["unknown_boards"],
                                   "dnse_components": measures["components"],
                                   "dnse_ohlc_v_equals_g1_shares": bool(ohlc_v) and g1 is not None and Decimal(str(ohlc_v[-1])) == g1["volume_shares"]}
        if recon["verdict"] in (contract.EXACT, contract.VOLUME_TRUNCATED_VALUE_EXACT, contract.CONFLICT):
            evidence.append({"ticker": ticker, "exchange": slot["exchange"], "kind": "CURRENT_SESSION", "reconciliation": recon})
        evidence.extend({"ticker": ticker, "exchange": slot["exchange"], "kind": "STALE_BOARD_POINT", "point": p} for p in points)
    return {"reconciliations": reconciliations, "units": contract.qualify_board_units(evidence)}


# ---------------------------------------------------------------------------------
# Per-ticker classification and record
# ---------------------------------------------------------------------------------
_FAILURE_OUTCOME_PREFIXES = ("HTTP_", "URLError", "TimeoutError", "EMPTY_BODY", "NOT_ATTEMPTED")


def _acquisition_failure_kind(slot: Mapping[str, Any]) -> str | None:
    """HTTP_OR_SOURCE_FAILURE for transport outcomes; SEMANTIC_CONFLICT for parsed-but-invalid payloads."""
    kinds = {failure["outcome"] for failure in slot.get("parse_failures") or []}
    if not kinds:
        return None
    if any(str(kind).startswith(_FAILURE_OUTCOME_PREFIXES) or "Error" in str(kind) for kind in kinds):
        return HTTP_OR_SOURCE_FAILURE
    return SEMANTIC_CONFLICT


def _zero_sessions(slot: Mapping[str, Any], window: Sequence[str]) -> list[str]:
    zero = []
    for session in window:
        row = slot["rows"].get(session)
        if row and row["row_integrity"] == "COMPONENTS_SUM_TO_TOTAL" and row["components"][contract.TOTAL]["value_vnd"] == 0:
            zero.append(session)
    return zero


def classify(row: Mapping[str, Any], slot: Mapping[str, Any] | None, adtv: Mapping[str, Any] | None, *,
             rights: Mapping[str, Mapping[str, Any]] = ACQUISITION_RIGHTS) -> dict[str, Any]:
    """Primary coverage class, secondary labels and reason codes for one ticker."""
    labels: list[str] = []
    route = row["route_exchange"]
    resolution = row["exchange_resolution"]
    if resolution == "TRANSFER_EVIDENCE":
        return {"coverage_class": TRANSFERRED_LISTING, "labels": [], "reason_codes": [row["eligibility_reason"]]}
    if resolution == "CONFLICT":
        return {"coverage_class": EXCHANGE_IDENTITY_CONFLICT, "labels": [], "reason_codes": [row["eligibility_reason"]]}
    if route is None:
        return {"coverage_class": SOURCE_NOT_SUPPORTED, "labels": [], "reason_codes": [row["eligibility_reason"], "NO_OFFICIAL_ROUTE_FOR_UNRESOLVED_EXCHANGE"]}
    if slot is None or (not slot["rows"] and not slot["responses"] and not slot["parse_failures"]):
        if rights[route]["decision"] != AUTHORIZED_BOUNDED_INTERNAL:
            return {"coverage_class": PUBLIC_ACQUISITION_NOT_AUTHORIZED, "labels": [],
                    "reason_codes": ["OFFICIAL_ROUTE_BULK_ACQUISITION_NOT_AUTHORIZED", f"EXTERNAL_APPROVAL_REQUIRED:{route}"]}
        return {"coverage_class": HTTP_OR_SOURCE_FAILURE, "labels": [], "reason_codes": ["PLANNED_REQUEST_NOT_EXECUTED"]}
    failure = _acquisition_failure_kind(slot)
    if not slot["rows"]:
        if failure is None or any(f["outcome"] in ("HOSE_LIST_ABSENT", "HOSE_RESPONSE_NOT_SUCCESS") for f in slot["parse_failures"]):
            return {"coverage_class": TICKER_NOT_FOUND, "labels": [], "reason_codes": ["OFFICIAL_ROUTE_RETURNED_NO_SESSION_ROWS_FOR_SYMBOL"]}
        return {"coverage_class": failure, "labels": [], "reason_codes": sorted({f["outcome"] for f in slot["parse_failures"]})}
    if failure is not None:
        return {"coverage_class": failure, "labels": [], "reason_codes": sorted({f["outcome"] for f in slot["parse_failures"]})}
    status = (adtv or {}).get("status")
    window = (adtv or {}).get("window_sessions") or []
    if any(r["row_integrity"] != "COMPONENTS_SUM_TO_TOTAL" for s, r in slot["rows"].items() if s in set(window)):
        return {"coverage_class": SEMANTIC_CONFLICT, "labels": [], "reason_codes": ["OFFICIAL_ROW_COMPONENTS_DO_NOT_SUM_TO_TOTAL"]}
    zero = _zero_sessions(slot, window)
    if zero:
        labels.append(ZERO_TRADING_VALID)
    if status == EXACT_WINDOW:
        return {"coverage_class": EXACT_20_SESSION_WINDOW, "labels": labels, "reason_codes": [], "zero_trading_sessions": zero}
    if status == COVERAGE_RESTRICTED_WINDOW:
        return {"coverage_class": MISSING_SESSION, "labels": labels, "reason_codes": list((adtv or {}).get("blockers") or []),
                "missing_sessions": (adtv or {}).get("missing_sessions")}
    return {"coverage_class": PARTIAL_WINDOW, "labels": labels, "reason_codes": list((adtv or {}).get("blockers") or [status or "WINDOW_UNRESOLVED"]),
            "missing_sessions": (adtv or {}).get("missing_sessions")}


def _ratio(numerator: Mapping[str, Any] | None, feature: Mapping[str, Any] | None, *, name: str, authority: str) -> dict[str, Any]:
    base = {"name": name, "authority": authority, "value": None, "numerator": None}
    if not feature or feature.get("status") != EXACT_WINDOW:
        return {**base, "status": "UNAVAILABLE", "reason_codes": [f"DENOMINATOR_{(feature or {}).get('status') or 'NOT_COMPUTED'}"]}
    denominator = Decimal(feature["value"])
    if denominator <= 0:
        return {**base, "status": "UNAVAILABLE", "reason_codes": ["DENOMINATOR_ZERO"]}
    if numerator is None:
        return {**base, "status": "UNAVAILABLE", "reason_codes": ["NUMERATOR_NOT_MEASURED_FOR_TARGET_SESSION"]}
    value = (Decimal(str(numerator["amount"])) / denominator).quantize(Decimal("0.0001"))
    return {**base, "status": "VALID", "value": format(value, "f"), "numerator": dict(numerator), "reason_codes": []}


def _current_numerators(slot: Mapping[str, Any] | None, dnse_components: Mapping[str, Any] | None, basis: str | None, target_session: str) -> tuple[dict | None, dict | None]:
    """Target-session matched value/volume: the exact official row first, else the qualified DNSE unit contract."""
    official_row = (slot or {}).get("rows", {}).get(target_session)
    if official_row and official_row["row_integrity"] == "COMPONENTS_SUM_TO_TOTAL":
        comp = official_row["components"][contract.MATCHED_ALL]
        source = "OFFICIAL_EXCHANGE_ROW"
        return ({"amount": comp["value_vnd"], "unit": "VND", "source": source, "component": contract.MATCHED_ALL},
                {"amount": comp["volume_shares"], "unit": "shares", "source": source, "component": contract.MATCHED_ALL})
    if dnse_components and basis in (contract.BASIS_OFFICIAL_RECONCILED, contract.BASIS_UNIT_CONTRACT_APPLIED):
        comp = dnse_components[contract.MATCHED_ALL]
        source = "DNSE_QUALIFIED_BOARD_UNIT_CONTRACT"
        return ({"amount": comp["value_vnd"], "unit": "VND", "source": source, "component": contract.MATCHED_ALL},
                {"amount": comp["volume_shares"], "unit": "shares", "source": source, "component": contract.MATCHED_ALL})
    return None, None


def evidence_currency(slot: Mapping[str, Any] | None, target_session: str) -> dict[str, Any]:
    newest = (slot or {}).get("newest")
    if newest is None:
        return {"target_session": target_session, "official_newest_session": None, "state": "NO_OFFICIAL_SERIES"}
    return {"target_session": target_session, "official_newest_session": newest,
            "state": "CURRENT_TARGET_SESSION" if newest == target_session else ("STALE_OFFICIAL_SERIES_ENDS_BEFORE_TARGET" if newest < target_session else "OFFICIAL_SERIES_AFTER_TARGET")}


def build_record(*, row: Mapping[str, Any], slot: Mapping[str, Any] | None, dnse_item: Mapping[str, Any] | None, recon: Mapping[str, Any] | None,
                 units: Mapping[str, Mapping[str, Any]] | None, calendar: Any, target_session: str,
                 rights: Mapping[str, Mapping[str, Any]] = ACQUISITION_RIGHTS) -> dict[str, Any]:
    ticker, route = row["ticker"], row["route_exchange"]
    features: dict[str, Any] = {}
    acquired = bool(slot) and bool(slot["rows"]) and not slot["parse_failures"]
    if acquired and calendar is not None:
        for feature_id, component, metric, size in contract.TRAILING_FEATURES:
            features[feature_id] = contract.official_trailing_feature(
                ticker=ticker, exchange=slot["exchange"], feature_id=feature_id, component=component, metric=metric, size=size,
                target_session=target_session, calendar=calendar, rows_by_session=slot["rows"], series_exhausted=slot["exhausted"],
                oldest_retained_session=slot["oldest"])
    coverage = classify(row, slot, features.get("ADTV20_MATCHED_ALL_VND"))

    # Current-session basis: DNSE boards resolved for the route exchange only.
    active_boards: list[str] = []
    basis = put_through = None
    dnse_measures = None
    if dnse_item and route and dnse_item.get("exchange") == route and units is not None:
        dnse_measures = contract.dnse_session_measures(dnse_item, session=target_session)
        active_boards = dnse_measures["active_boards"]
        if active_boards:
            usable_recon = recon if (recon or {}).get("exchange") == route and recon.get("verdict") not in (None, "EXCHANGE_BINDING_MISMATCH") else None
            basis = contract.matched_measurement_basis(active_boards, units[route], usable_recon)
            put_through = contract.put_through_precision(active_boards, units[route], usable_recon)
    current_active = bool(active_boards)
    fitness = contract.dimension_fitness(current_basis=basis, current_active=current_active, official_series_acquired=acquired, features=features)
    if coverage["coverage_class"] == PUBLIC_ACQUISITION_NOT_AUTHORIZED:
        for dim in (contract.HISTORICAL_LIQUIDITY_RESEARCH, contract.ADV_VOLUME_RESEARCH, contract.ADTV_RESEARCH):
            fitness[dim] = {**fitness[dim], "reason": "PUBLIC_ACQUISITION_NOT_AUTHORIZED: official per-symbol series for this exchange may not be bulk-retrieved without HNX approval",
                            "external_dependency": "HNX_INFORMATION_SERVICE_APPROVAL"}
    numer_value, numer_volume = _current_numerators(slot, (dnse_measures or {}).get("components"), basis, target_session)
    ratio_value = _ratio(numer_value, features.get("ADTV20_MATCHED_ALL_VND"), name="CURRENT_MATCHED_VALUE_TO_ADTV20", authority="OFFICIAL_RESEARCH_SCOPED")
    ratio_volume = _ratio(numer_volume, features.get("ADV20_MATCHED_ALL_SHARES"), name="CURRENT_MATCHED_VOLUME_TO_ADV20",
                          authority="PARTIAL_AS_TRADED_SHARES_NOT_CORPORATE_ACTION_NORMALIZED")
    currency = evidence_currency(slot, target_session)
    responses = (slot or {}).get("responses") or []
    view = {
        "current_session": {"session": target_session, "matched_value_vnd": numer_value, "matched_volume_shares": numer_volume,
                            "measurement_basis": basis, "put_through_precision": put_through, "active_boards": active_boards},
        "adv20_matched_all_shares": {"status": (features.get("ADV20_MATCHED_ALL_SHARES") or {}).get("status"), "value": (features.get("ADV20_MATCHED_ALL_SHARES") or {}).get("value")},
        "adtv20_matched_all_vnd": {"status": (features.get("ADTV20_MATCHED_ALL_VND") or {}).get("status"), "value": (features.get("ADTV20_MATCHED_ALL_VND") or {}).get("value")},
        "current_value_to_adtv20": ratio_value, "current_volume_to_adv20": ratio_volume,
        "window_coverage": coverage["coverage_class"], "evidence_currency": currency,
        "fitness": {dim: cell["state"] for dim, cell in fitness.items()},
        "reason_codes": sorted(set(coverage["reason_codes"])),
    }
    return {
        "ticker": ticker, "route_exchange": route, "universe": {k: row[k] for k in ("official_exchange", "dnse_exchange", "exchange_resolution", "eligibility_reason", "official_presence")},
        "coverage": coverage, "features": features, "fitness": fitness, "research_view": view,
        "evidence_refs": {"source": (slot or {}).get("source"), "responses": [{k: r.get(k) for k in ("sha256", "retrieved_at", "url", "rows")} for r in responses],
                          "sessions_retained": len((slot or {}).get("rows") or {}), "oldest": (slot or {}).get("oldest"), "newest": (slot or {}).get("newest")},
        "current_session_reconciliation": ({k: recon[k] for k in ("verdict", "matched_verdict", "put_through_verdict") if k in recon} if recon else None),
    }


# ---------------------------------------------------------------------------------
# Coverage tables, matrix, readiness
# ---------------------------------------------------------------------------------

def coverage_tables(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, Counter] = {ex: Counter() for ex in official.EXCHANGES}
    unrouted: Counter = Counter()
    labels: Counter = Counter()
    for record in records.values():
        cls = record["coverage"]["coverage_class"]
        if record["route_exchange"]:
            by_class[record["route_exchange"]][cls] += 1
        else:
            unrouted[cls] += 1
        for label in record["coverage"]["labels"]:
            labels[f"{record['route_exchange']}:{label}"] += 1
    dims = {dim: dict(sorted(Counter(f"{r['route_exchange'] or 'UNROUTED'}:{r['fitness'][dim]['state']}" for r in records.values()).items()))
            for dim in contract.LIQUIDITY_DIMENSIONS}
    exact = {ex: sum(1 for r in records.values() if r["route_exchange"] == ex and (r["features"].get("ADTV20_MATCHED_ALL_VND") or {}).get("status") == EXACT_WINDOW) for ex in official.EXCHANGES}
    exact_adv = {ex: sum(1 for r in records.values() if r["route_exchange"] == ex and (r["features"].get("ADV20_MATCHED_ALL_SHARES") or {}).get("status") == EXACT_WINDOW) for ex in official.EXCHANGES}
    return {"by_exchange_and_class": {ex: dict(sorted(c.items())) for ex, c in by_class.items()},
            "unrouted_by_class": dict(sorted(unrouted.items())), "labels": dict(sorted(labels.items())),
            "dimension_counts": dims, "adtv20_exact_by_exchange": exact, "adv20_exact_by_exchange": exact_adv,
            "adtv20_exact_total": sum(exact.values()), "adv20_exact_total": sum(exact_adv.values())}


# Execution-capacity readiness: which sizing inputs exist, per ticker. No size is ever emitted.
AVAILABLE_DATA = "AVAILABLE_DATA"
POLICY_NOT_DEFINED = "POLICY_NOT_DEFINED"
DATA_NOT_QUALIFIED = "DATA_NOT_QUALIFIED"
PIT_REQUIRED = "PIT_REQUIRED"
USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
READINESS_STATES = (AVAILABLE_DATA, POLICY_NOT_DEFINED, DATA_NOT_QUALIFIED, PIT_REQUIRED, USER_INPUT_REQUIRED)
READINESS_DIMENSIONS = ("ADTV20", "ADV20", "CURRENT_LIQUIDITY", "VOLATILITY_BASIS", "ORDER_SIZE_INPUT", "PARTICIPATION_RATE_POLICY",
                        "DAYS_TO_LIQUIDATE_POLICY", "MARKET_IMPACT_MODEL", "PRICE_LIMIT_INTRADAY_CONSTRAINTS", "PORTFOLIO_CAPITAL_HOLDINGS_RISK_BUDGET",
                        "POINT_IN_TIME_LIQUIDITY_KNOWLEDGE")


def execution_capacity_readiness(record: Mapping[str, Any]) -> dict[str, str]:
    fit = record["fitness"]
    return {
        "ADTV20": AVAILABLE_DATA if fit[contract.ADTV_RESEARCH]["state"] == contract.ELIGIBLE else DATA_NOT_QUALIFIED,
        "ADV20": AVAILABLE_DATA if fit[contract.ADV_VOLUME_RESEARCH]["state"] in (contract.ELIGIBLE, contract.PARTIAL) else DATA_NOT_QUALIFIED,
        "CURRENT_LIQUIDITY": AVAILABLE_DATA if fit[contract.CURRENT_SESSION_LIQUIDITY_RESEARCH]["state"] == contract.ELIGIBLE else DATA_NOT_QUALIFIED,
        "VOLATILITY_BASIS": DATA_NOT_QUALIFIED,
        "ORDER_SIZE_INPUT": USER_INPUT_REQUIRED,
        "PARTICIPATION_RATE_POLICY": POLICY_NOT_DEFINED,
        "DAYS_TO_LIQUIDATE_POLICY": POLICY_NOT_DEFINED,
        "MARKET_IMPACT_MODEL": POLICY_NOT_DEFINED,
        "PRICE_LIMIT_INTRADAY_CONSTRAINTS": POLICY_NOT_DEFINED,
        "PORTFOLIO_CAPITAL_HOLDINGS_RISK_BUDGET": USER_INPUT_REQUIRED,
        "POINT_IN_TIME_LIQUIDITY_KNOWLEDGE": PIT_REQUIRED,
    }


def readiness_summary(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    per_dimension: dict[str, Counter] = {dim: Counter() for dim in READINESS_DIMENSIONS}
    ready_data = Counter()
    for record in records.values():
        cells = execution_capacity_readiness(record)
        for dim, state in cells.items():
            per_dimension[dim][state] += 1
        if cells["ADTV20"] == AVAILABLE_DATA and cells["CURRENT_LIQUIDITY"] == AVAILABLE_DATA:
            ready_data[record["route_exchange"] or "UNROUTED"] += 1
    return {"dimensions": {dim: dict(sorted(c.items())) for dim, c in per_dimension.items()},
            "tickers_with_qualified_liquidity_data_by_exchange": dict(sorted(ready_data.items())),
            "next_milestone_blockers": ["PARTICIPATION_RATE_POLICY", "DAYS_TO_LIQUIDATE_POLICY", "MARKET_IMPACT_MODEL", "PRICE_LIMIT_INTRADAY_CONSTRAINTS",
                                        "ORDER_SIZE_INPUT", "PORTFOLIO_CAPITAL_HOLDINGS_RISK_BUDGET", "POINT_IN_TIME_LIQUIDITY_KNOWLEDGE"],
            "position_sizing": dimension_basis.BLOCKED, "execution_capacity": dimension_basis.BLOCKED,
            "note": "Readiness only; POLICY_NOT_DEFINED and PIT_REQUIRED cells are the bounded scope of the next sizing milestone."}


# ---------------------------------------------------------------------------------
# Legacy liquidity-consumer inventory (drift-guarded by tests)
# ---------------------------------------------------------------------------------
ACTIVE, SHADOW, DEAD, HISTORICAL_ONLY = "ACTIVE", "SHADOW", "DEAD", "HISTORICAL_ONLY"
_PROXY = "rolling mean(close x volume)/1e9 on the retained price series (a value proxy, not an official traded value)"
LEGACY_LIQUIDITY_CONSUMERS: dict[str, dict[str, str]] = {
    "vn_indicators.py": {"state": ACTIVE, "field": "gtgd20_ty", "note": _PROXY,
                         "disposition": "NOT_MIGRATED: proxy semantics differ from official MATCHED_ALL ADTV20; official coverage is HOSE + a retained cohort only"},
    "stock_analyzer.py": {"state": ACTIVE, "field": "gtgd20_ty", "note": "legacy CLI screener thresholds (LIQ_MIN_TY, FTSE_GTGD_MIN_TY) tuned to the proxy",
                          "disposition": "NOT_MIGRATED: outside the Current Research Daily path; migrating would silently change screen membership"},
    "ai_analyzer.py": {"state": ACTIVE, "field": "gtgd20_ty", "note": "legacy CLI filter gtgd20_ty >= 3",
                       "disposition": "NOT_MIGRATED: legacy CLI, outside the Daily path"},
    "candle_scan.py": {"state": ACTIVE, "field": "gtgd20_ty", "note": "legacy candle scan snapshot column",
                       "disposition": "NOT_MIGRATED: legacy CLI, outside the Daily path"},
    "candlestick_patterns.py": {"state": ACTIVE, "field": "gtgd20_ty_calc / avg_volume20", "note": _PROXY,
                                "disposition": "NOT_MIGRATED: legacy candle-scan support"},
    "canonical_dashboard_runtime_release.py": {"state": ACTIVE, "field": "gtgd20_ty (screener column)",
                                               "note": "unsupported canonical fields are emitted blank, never copied from a legacy release",
                                               "disposition": "NOT_MIGRATED: filling the column is a Dashboard publication, out of scope here"},
    "screener_master_projection.py": {"state": ACTIVE, "field": "liquidity.research_value",
                                      "note": "numeric research value guarded as NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20",
                                      "disposition": "NOT_MIGRATED: Dashboard-facing projection; the qualified numeric value is delivered through the Daily decision input instead"},
    "risk_liquidity.py": {"state": ACTIVE, "field": "average_volume", "note": "AI-bundle market-risk liquidity over the DNSE OHLC v basis (G1 x 10 shares)",
                          "disposition": "NOT_MIGRATED: official ADV20 is PARTIAL and covers a subset; replacing it would drop coverage"},
    "market_price_volume_basis_authority.py": {"state": HISTORICAL_ONLY, "field": "legacy.gtgd20_ty / VCI average volume", "note": "registry rows; every fitness is BLOCKED",
                                               "disposition": "RETAINED_AS_AUTHORITY_REGISTRY"},
    "market_volume_value_semantic_contract.py": {"state": HISTORICAL_ONLY, "field": "legacy.gtgd20_ty", "note": "field contract; prohibited uses recorded",
                                                 "disposition": "RETAINED_AS_FIELD_CONTRACT"},
    "market_volume_capability_matrix.py": {"state": HISTORICAL_ONLY, "field": "gtgd20 / average_volume", "note": "capability matrix; sizing capabilities UNAVAILABLE_BY_CONTRACT",
                                           "disposition": "RETAINED_AS_CAPABILITY_MATRIX"},
    "kbs_trading_value_coverage.py": {"state": SHADOW, "field": "KBS va", "note": "KBS trading-value shadow; no live KBS runtime",
                                      "disposition": "SHADOW_RETAINED_NO_LIVE_CALL"},
    "kbs_capability_matrix.py": {"state": SHADOW, "field": "KBS average volume", "note": "KBS capability matrix shadow",
                                 "disposition": "SHADOW_RETAINED_NO_LIVE_CALL"},
}
LEGACY_PROXY_TOKENS = ("gtgd20", "avg_volume20", "average_volume")
