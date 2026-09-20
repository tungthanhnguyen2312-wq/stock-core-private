"""dashboard_home_summary/v1: small, presentation-only Home summary for the public Dashboard.

Home (dashboard.html) does not need any individual ticker's full record -- only a
handful of already-computed aggregate counts (breadth, research-stance distribution,
tactical-state distribution, liquidity/execution coverage, sector labels) that the
existing ``screener_master_projection/v1`` artifact already lets a consumer derive.
Before this module, Home derived those aggregates client-side, in the browser, by
downloading the full projection (every ticker's full card, ~6.4MB decoded) and
iterating it several times with ``assets/js/dashboard-product-summary.js``'s
``summarizeScreenerOverview()``.

This module performs the IDENTICAL aggregation -- same fields, same conditions, same
counts -- once, server-side, over the same already-governed projection artifact, and
emits only the small aggregate result. It is a pure re-aggregation: it reads no raw
market data, computes no new ratio/threshold/score, and adds no field
``screener_master_projection.py`` does not already expose per ticker. Numerical parity
with the JS ``summarizeScreenerOverview()`` output is a hard contract -- see
``tests/test_dashboard_home_summary.py``'s cross-check against a real retained
projection artifact and the JS reimplementation.

Never emits: ranking, score, recommendation, target price, probability, or any new
market-regime/state logic beyond the same purely descriptive breadth-ratio label the
JS layer already used (``breadth_state``: NGHIENG_TANG / NGHIENG_GIAM / GIANG_CO / UNAVAILABLE).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

CONTRACT_VERSION = "dashboard_home_summary/v1"
SCHEMA_VERSION = "1.0.0"
SOURCE_CONTRACT_VERSION = "screener_master_projection/v1"
JS_GLOBAL = "window.DASHBOARD_HOME_SUMMARY"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}

ENTITY_CLASS_VOCABULARY = frozenset({
    "corporate", "bank", "securities", "insurance", "finance_company",
})
STANCE_ORDER = (
    "INITIATE_RESEARCH_CANDIDATE",
    "ACCUMULATE_RESEARCH_CANDIDATE",
    "WAIT_FOR_CONFIRMATION",
    "HIGH_RISK_SPECULATION_ONLY",
    "AVOID_NEW_ENTRY",
    "INSUFFICIENT_EVIDENCE",
)
TACTICAL_ORDER = (
    "DOWNTREND",
    "SELLING_PRESSURE_EASING",
    "UPTREND_CONFIRMED",
    "EARLY_REVERSAL_CANDIDATE",
    "BREAKDOWN_RISK",
    "SIDEWAYS_NEUTRAL",
    "DISTRIBUTION_RISK",
    "BASE_BUILDING",
    "BREAKOUT_READY",
)
#: Top-N sector rows retained -- Home's chart only ever renders the top 10 (see
#: assets/js/dashboard-product-summary.js renderOverviewCharts); keeping the summary
#: bounded regardless of how many distinct sector labels exist market-wide.
SECTOR_ROWS_RETAINED = 10


class DashboardHomeSummaryError(ValueError):
    """A required input contract or invariant of this summary is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _has_current_price(card: Mapping[str, Any]) -> bool:
    price = card.get("price") if isinstance(card, Mapping) else None
    return bool(isinstance(price, Mapping) and price.get("status") == "PRICE_AVAILABLE")


def _is_priced(card: Mapping[str, Any]) -> bool:
    price = card.get("price") if isinstance(card, Mapping) else None
    if not isinstance(price, Mapping) or price.get("change_pct_status") != "AVAILABLE":
        return False
    try:
        float(price.get("change_pct"))
    except (TypeError, ValueError):
        return False
    return True


def _change_pct(card: Mapping[str, Any]) -> float:
    return float(card["price"]["change_pct"])


def _is_tactical_available(card: Mapping[str, Any]) -> bool:
    tactical = card.get("tactical") if isinstance(card, Mapping) else None
    return bool(isinstance(tactical, Mapping) and tactical.get("status") == "AVAILABLE" and tactical.get("entry_state"))


def _is_liquidity_proxy(card: Mapping[str, Any]) -> bool:
    liquidity = card.get("liquidity") if isinstance(card, Mapping) else None
    if not isinstance(liquidity, Mapping):
        return False
    return liquidity.get("fitness") == "LIQUIDITY_RESEARCH_PROXY" or liquidity.get("method") == "LIQUIDITY_RESEARCH_PROXY"


def _is_execution_exact_ready(card: Mapping[str, Any]) -> bool:
    execution = card.get("execution") if isinstance(card, Mapping) else None
    return bool(isinstance(execution, Mapping) and execution.get("capacity_exact_status") == "EXECUTION_CAPACITY_EXACT_READY")


def _sector_label(card: Mapping[str, Any]) -> str | None:
    sector = card.get("sector") if isinstance(card, Mapping) else None
    if not isinstance(sector, Mapping) or sector.get("status") != "AVAILABLE":
        return None
    label = sector.get("label")
    label = label.strip() if isinstance(label, str) else ""
    if not label or label.lower() in ENTITY_CLASS_VOCABULARY:
        return None
    return label


def breadth_state(up: int, down: int) -> str:
    """Pure, deterministic, descriptive breadth label -- mirrors
    ``assets/js/dashboard-product-summary.js``'s ``marketBreadthStateLabel`` exactly
    (same 1.2x-lean thresholds). Never a buy/sell signal: it characterizes the already-
    computed up/down counts, nothing else, and is not read by any downstream decision
    logic.
    """
    if up + down == 0:
        return "UNAVAILABLE"
    if up >= down * 1.2:
        return "NGHIENG_TANG"
    if down >= up * 1.2:
        return "NGHIENG_GIAM"
    return "GIANG_CO"


def build_home_summary(projection: Mapping[str, Any], *, requested_at: str) -> dict[str, Any]:
    """Build the presentation-only Home summary from an already-governed
    ``screener_master_projection/v1`` artifact. Fails closed on any session/contract
    incoherence -- Home must never render a summary bound to a different artifact than
    the one it claims.
    """
    if not isinstance(projection, Mapping):
        raise DashboardHomeSummaryError("PROJECTION_NOT_A_MAPPING")
    if projection.get("contract_version") != SOURCE_CONTRACT_VERSION:
        raise DashboardHomeSummaryError("SOURCE_CONTRACT_VERSION_MISMATCH")
    as_of_session = projection.get("as_of_session")
    if not as_of_session or not isinstance(as_of_session, str):
        raise DashboardHomeSummaryError("SOURCE_SESSION_MISSING")
    source_identity = projection.get("artifact_identity")
    if not source_identity or not isinstance(source_identity, str):
        raise DashboardHomeSummaryError("SOURCE_ARTIFACT_IDENTITY_MISSING")
    cards_raw = projection.get("cards")
    if not isinstance(cards_raw, Mapping) or not cards_raw:
        raise DashboardHomeSummaryError("SOURCE_EMPTY_CORPUS")
    coverage = projection.get("coverage")
    if not isinstance(coverage, Mapping) or coverage.get("ticker_denominator") != len(cards_raw):
        raise DashboardHomeSummaryError("SOURCE_DENOMINATOR_MISMATCH")

    cards = list(cards_raw.values())
    denominator = len(cards)
    price_available = [card for card in cards if _has_current_price(card)]
    priced = [card for card in cards if _is_priced(card)]
    up = sum(1 for card in priced if _change_pct(card) > 0)
    down = sum(1 for card in priced if _change_pct(card) < 0)
    flat = sum(1 for card in priced if _change_pct(card) == 0)
    tactical_available = [card for card in cards if _is_tactical_available(card)]
    tactical_counts = Counter({state: 0 for state in TACTICAL_ORDER})
    for card in tactical_available:
        tactical_counts[card["tactical"]["entry_state"]] += 1
    stance_counts = Counter({stance: 0 for stance in STANCE_ORDER})
    for card in cards:
        research = card.get("research") if isinstance(card, Mapping) else None
        stance = research.get("stance") if isinstance(research, Mapping) else None
        if stance:
            stance_counts[stance] += 1
    liquidity_proxy_count = sum(1 for card in cards if _is_liquidity_proxy(card))
    execution_exact_ready = sum(1 for card in cards if _is_execution_exact_ready(card))

    official_scope = projection.get("official_scope_coverage")
    official_scope_coherent = bool(
        isinstance(official_scope, Mapping)
        and official_scope.get("temporally_eligible")
        and official_scope.get("research_session") == as_of_session
    )

    sector_counts: Counter[str] = Counter()
    sector_labeled = 0
    for card in cards:
        label = _sector_label(card)
        if not label:
            continue
        sector_labeled += 1
        sector_counts[label] += 1
    sector_rows = [
        {"label": label, "count": count}
        for label, count in sorted(sector_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:SECTOR_ROWS_RETAINED]

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "requested_at": requested_at,
        "as_of_session": as_of_session,
        "source_artifact_identity": source_identity,
        "denominator": denominator,
        "reference_ticker_count": denominator,
        "current_research_scope_count": official_scope.get("current_official_research_scope_count") if official_scope_coherent else None,
        "outside_current_official_scope_count": official_scope.get("outside_current_official_scope_count") if official_scope_coherent else None,
        "official_scope_observed_at": official_scope.get("official_snapshot_observed_at") if official_scope_coherent else None,
        "price_available_count": len(price_available),
        "price_unavailable_count": denominator - len(price_available),
        "tactical_available_count": len(tactical_available),
        "tactical_unavailable_count": denominator - len(tactical_available),
        "session_breadth": {
            "available": len(priced) > 0,
            "priced": len(priced),
            "up": up,
            "down": down,
            "flat": flat,
            "price_available": len(price_available),
            "unpriced": denominator - len(price_available),
            "missing_session_return": len(price_available) - len(priced),
            "state": breadth_state(up, down),
        },
        "research_stance": {
            "available": denominator > 0,
            "counts": dict(sorted(stance_counts.items())),
            "order": list(STANCE_ORDER),
        },
        "tactical": {
            "available": len(tactical_available) > 0,
            "coverage": len(tactical_available),
            "counts": dict(sorted(tactical_counts.items())),
            "order": list(TACTICAL_ORDER),
        },
        "liquidity": {
            "proxy_available": liquidity_proxy_count > 0 or denominator > 0,
            "proxy_count": liquidity_proxy_count,
            "execution_exact_ready": execution_exact_ready,
            "execution_exact_established": execution_exact_ready > 0,
        },
        "sector": {
            "available": sector_labeled > 0,
            "labeled": sector_labeled,
            "rows": sector_rows,
        },
        "authority_effect": "NONE / PRESENTATION_READ_MODEL_ONLY",
        "blocked_outputs": {
            "universal_score": "SCORING_PROHIBITED",
            "ordinal_rank": "RANKING_PROHIBITED",
            "probability_of_success": "FORECAST_PROHIBITED",
            "target_price": "NOT_EMITTED",
            "market_regime": "NOT_COMPUTED",
        },
    }
    summary.update(content_identity(summary))
    return summary


def js_fallback(summary: Mapping[str, Any]) -> str:
    return f"{JS_GLOBAL} = {json.dumps(summary, ensure_ascii=False, separators=(',', ':'))};\n"
