"""Minimal, source-preserving bridge from the retained DNSE foreign-flow VALUE store into
``current_market_flow_positioning/v1``'s existing canonical-observation input shape.

WHY THIS EXISTS (Phase 13 investigation)
    ``current_market_flow_positioning.build()`` already consumes a
    ``canonical_market_evidence_integration`` envelope, normally produced from a live
    ``tools/collect_market_evidence.py`` session packet (a *different*, independent DNSE/FHSC
    acquisition path). That path is not populated by this milestone's no-network foundation.
    This bridge answers Phase 13's question ("can flow positioning consume the retained
    VALUE-store representation directly?") with a minimal adapter reusing the exact same
    canonical-integration boundary, rather than a second, competing flow-positioning engine.

SCOPE -- DELIBERATELY NARROW
    Only the already-qualified FOREIGN_BUY_VALUE / FOREIGN_SELL_VALUE / FOREIGN_NET_VALUE
    triple is bridged, for exact-session-current tickers only. Foreign volume and foreign room
    are never read here (both remain ``AVAILABLE_BUT_SEMANTICS_UNQUALIFIED`` in
    ``dnse_foreign_flow_capability.py``), and no other flow-positioning dimension (traded
    value, proprietary flow, active-order context) is ever fabricated for a ticker this bridge
    supplies -- an absent dimension stays absent, never a synthetic zero.

NOT WIRED INTO THE LIVE DAILY PIPELINE
    This module is a standalone, tested capability. ``canonical_post_close_pipeline.py``'s
    flow_price_divergence_shadow step already reads the VALUE store directly and does not
    depend on this bridge. Wiring a second producer of the SAME
    ``current_market_flow_positioning/v1`` contract into live Daily -- alongside the existing
    ``collect_market_evidence.py``-fed path -- is an explicit owner integration decision this
    milestone does not make; see the validation report for the reasoning.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import canonical_market_evidence_integration as canonical
from current_market_flow_positioning import build as build_flow_positioning
from dnse_foreign_flow_store import build_series

BRIDGE_CONTRACT_VERSION = "current_foreign_flow_positioning_bridge/v1"


def _content_hash(*, ticker: str, session: str, buy: Any, sell: Any, net: Any) -> str:
    payload = {"ticker": ticker, "session": session, "buy": buy, "sell": sell, "net": net}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _raw_observation(*, ticker: str, session: str, series: Mapping[str, Any]) -> dict[str, Any] | None:
    """One ``collect_market_evidence``-shaped raw observation, or None if this ticker has no
    qualified, exact-session-current VALUE flow to offer -- never a fabricated placeholder."""
    if series.get("status") != "available":
        return None
    latest = series.get("latest_session") or {}
    freshness = series.get("freshness") or {}
    if latest.get("session_date") != session or freshness.get("status") != "current":
        return None
    buy, sell, net = (latest.get("foreign_buy_value_vnd"), latest.get("foreign_sell_value_vnd"),
                      latest.get("foreign_net_value_vnd"))
    if buy is None or sell is None or net is None:
        return None
    return {
        "instrument": ticker, "session": session, "source": "DNSE", "endpoint_id": "foreign_trading",
        "status": "ACQUIRED", "retrieved_at": latest.get("observed_at"),
        "raw_path": f"dnse_foreign_flow_store:{ticker}:{session}",
        "raw_sha256": _content_hash(ticker=ticker, session=session, buy=buy, sell=sell, net=net),
        "provider_session_date": session, "usability_state": "RESEARCH_USABLE",
        "native_fields": {
            "FOREIGN_BUY_VALUE": {"value": buy, "unit": "vnd_raw_not_thousands", "raw_field": "totalBuyTradedAmount"},
            "FOREIGN_SELL_VALUE": {"value": sell, "unit": "vnd_raw_not_thousands", "raw_field": "totalSellTradedAmount"},
            "FOREIGN_NET_VALUE": {"value": net, "unit": "vnd_raw_not_thousands", "raw_field": "derived_buy_minus_sell"},
        },
        "canonical_fields": {
            "FOREIGN_BUY_VALUE": {"value": buy, "unit": "VND", "contract_id": "dnse.foreign_buy_value"},
            "FOREIGN_SELL_VALUE": {"value": sell, "unit": "VND", "contract_id": "dnse.foreign_sell_value"},
            "FOREIGN_NET_VALUE": {"value": net, "unit": "VND", "contract_id": "dnse.foreign_net_value"},
        },
    }


def build_from_store(*, runtime_root: Any, session: str, tickers: Sequence[str]) -> dict[str, Any]:
    """Build a ``current_market_flow_positioning/v1`` artifact from only the retained
    foreign-flow VALUE store -- zero network calls, no volume, no room."""
    observations = []
    for ticker in sorted({str(item).upper() for item in tickers}):
        series = build_series(runtime_root, ticker, reference_session_date=session)
        raw_observation = _raw_observation(ticker=ticker, session=session, series=series)
        if raw_observation is not None:
            observations.append(raw_observation)
    packet = {
        "packet_schema_version": "1.0.0", "session_date": session,
        "execution_mode": "RETAINED_FOREIGN_FLOW_VALUE_STORE_ONLY", "observations": observations,
    }
    integration = canonical.integrate_session_packet(packet)
    artifact = build_flow_positioning(canonical_integration=integration, candidate_tickers=list(tickers))
    # Wrapped, not mutated in place: build_flow_positioning() already stamped artifact_identity
    # over its own exact content: adding fields after the fact would make that digest stale.
    return {"bridge_contract_version": BRIDGE_CONTRACT_VERSION, "bridge_source_ticker_count": len(observations),
            "flow_positioning_artifact": artifact}
