"""Market-wide current-session descriptive DNSE board-composition dataset."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

import dnse_trades_liquidity_basis as basis

CONTRACT_VERSION = "market_wide_current_liquidity_research/v1"
MILESTONE = "MARKET_WIDE_CURRENT_LIQUIDITY_RESEARCH_SCALEOUT_V1"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Recompute this artifact's content hash from its own bytes, excluding the identity
    fields it carries itself. Mirrors dnse_fhsc_market_composition_scaleout.content_identity()
    / dnse_fhsc_volume_basis.content_identity() so a downstream consumer (e.g.
    export_ai_bundle.py) can verify a retained artifact reproduces its own recorded
    artifact_sha256 before attaching any of its records to a bundle."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_liquidity_research:{digest}"}


def _ohlc_volume(body: Mapping[str, Any], session: str) -> float | None:
    times, volumes = body.get("t"), body.get("v")
    if not isinstance(times, list) or not isinstance(volumes, list) or len(times) != len(volumes):
        return None
    from datetime import datetime, timezone
    from vn_time import VN_TZ
    found: list[float] = []
    for epoch, volume in zip(times, volumes):
        if isinstance(epoch, (int, float)) and not isinstance(epoch, bool) and isinstance(volume, (int, float)) and not isinstance(volume, bool):
            date = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(VN_TZ).date().isoformat()
            if date == session:
                found.append(float(volume))
    return found[0] if len(found) == 1 else None


def _record(ticker: str, trade: Mapping[str, Any], ohlc: Mapping[str, Any]) -> dict[str, Any]:
    if not trade.get("ok"):
        return {"ticker": ticker, "disposition": trade.get("disposition", "PROVIDER_REJECTED"), "reason": trade.get("reason", "TRADES_LATEST_UNAVAILABLE")}
    parsed = basis.parse_trades_response(trade["body"], symbol=ticker, endpoint="trades_latest")
    if parsed["parse_status"] != "PARSED":
        return {"ticker": ticker, "disposition": "MALFORMED", "reason": parsed["parse_status"]}
    snapshot = basis.board_latest_snapshot(parsed["records"])
    session = snapshot["target_session_date"]
    active = [item for item in snapshot["boards"].values() if item.get("activity_state") == basis.OBSERVED_ACTIVE_THIS_SESSION]
    if not session or not active:
        return {"ticker": ticker, "disposition": "INCOMPLETE", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD", "board_snapshot": snapshot}
    if not ohlc.get("ok"):
        return {"ticker": ticker, "disposition": ohlc.get("disposition", "PROVIDER_REJECTED"), "reason": "CURRENT_OHLC_UNAVAILABLE", "board_snapshot": snapshot}
    volume = _ohlc_volume(ohlc["body"], session)
    if volume is None:
        return {"ticker": ticker, "disposition": "MISSING", "reason": "COMPATIBLE_CURRENT_OHLC_V_MISSING", "board_snapshot": snapshot}
    categories = basis.board_category_totals(snapshot)
    raw_total = sum(item["active_volume_raw_total"] for item in categories.values())
    for item in categories.values():
        item["provider_raw_composition_ratio"] = (item["active_volume_raw_total"] / raw_total if raw_total else None)
        item["ratio_basis"] = "CURRENT_SESSION_PROVIDER_RAW_COUNTERS_ONLY_NOT_EXECUTED_SHARE_OR_TURNOVER_RATIO"
    cross = basis.g1_scale_cross_check(snapshot, ohlc_v=volume)
    contract = basis.session_liquidity_research_contract(current_session_boards_active=True, historical_scan_state=None)
    basis.assert_fail_closed(contract)
    return {"ticker": ticker, "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "session": session,
            "board_snapshot": snapshot, "board_composition": categories, "g1_v_reconciliation": cross,
            "current_ohlc_v": volume, "liquidity_research_contract": contract,
            "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED"}


def build_artifact(*, candidates: list[str], trades: Mapping[str, Mapping[str, Any]], ohlc: Mapping[str, Mapping[str, Any]], requested_at: str) -> dict[str, Any]:
    records = {ticker: _record(ticker, trades.get(ticker, {"ok": False, "disposition": "MISSING"}), ohlc.get(ticker, {"ok": False, "disposition": "MISSING"})) for ticker in sorted(candidates)}
    counts = Counter(row["disposition"] for row in records.values())
    eligible = [row for row in records.values() if row["disposition"] == "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE"]
    artifact: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "universe": {"canonical_candidate_count": len(candidates), "authority": "runtime_metadata_ticker_sorted_v1"},
        "coverage": {"disposition_counts": dict(sorted(counts.items())), "reconciled_count": len(records), "eligible_current_session_count": len(eligible), "unattempted_without_disposition": 0},
        "records": records, "authority_boundary": {"CURRENT_SESSION_LIQUIDITY_RESEARCH": "DESCRIPTIVE_ONLY", "QUALIFIED_LIQUIDITY_INPUTS": False,
        "ADV_VOLUME_RESEARCH": "BLOCKED", "ADTV_RESEARCH": "BLOCKED", "POSITION_SIZING": "BLOCKED", "EXECUTION_CAPACITY": "BLOCKED", "PIT_BACKTEST": "BLOCKED", "RAW_AS_TRADED": "NOT_PROMOTED", "gross_trade_amount": "NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED", "derived_price_times_shares": "NOT_COMPUTED"}}
    identity = content_identity(artifact)
    artifact["artifact_sha256"] = identity["artifact_sha256"]
    artifact["artifact_identity"] = identity["artifact_identity"]
    return artifact
