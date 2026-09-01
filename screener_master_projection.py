"""screener_master_projection/v1: derived Screener presentation read model.

A pure join over already-governed Producer artifacts. This module does not acquire
market data, does not read SQLite, does not recompute technical/fundamental/valuation
formulas, and is not a new source of factual authority.

Denominator is the current canonical screen-snapshot ticker set. Workspace-only extras
are never admitted. Missing join evidence stays on the row with an explicit status.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONTRACT_VERSION = "screener_master_projection/v1"
MILESTONE = "SCREENER_MASTER_PROJECTION_AND_DECISION_DRAWER_INTEGRATION_V1"
SCHEMA_VERSION = "1.0.0"
JS_GLOBAL = "window.SCREENER_MASTER_PROJECTION"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}

LISTING_TO_DISPLAY = {
    "HOSE": "HSX",
    "HCM": "HSX",
    "HSX": "HSX",
    "HNX": "HNX",
    "HNX_LISTED": "HNX",
    "UPCOM": "UPCOM",
    "UPX": "UPCOM",
    "DELISTED": "DELISTED",
}
DISPLAY_EXCHANGES = frozenset({"HSX", "HNX", "UPCOM", "DELISTED"})
ENTITY_CLASS_VOCABULARY = frozenset({
    "corporate", "bank", "securities", "insurance", "finance_company",
})
FORBIDDEN_SYNTHETIC_SECTORS = frozenset({
    "doanh nghiệp chung", "doanh nghiep chung", "general corporate", "unknown",
})
VCI_INDUSTRY_PROVIDER = "vnstock:Listing(source=VCI).symbols_by_industries"
VCI_INDUSTRY_FIELD = "industry"

CURRENT = "CURRENT"
STALE_BUT_RESEARCH_USABLE = "STALE_BUT_RESEARCH_USABLE"
STALE_NOT_USABLE_FOR_THIS_AXIS = "STALE_NOT_USABLE_FOR_THIS_AXIS"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
AVAILABLE = "AVAILABLE"
MIXED = "MIXED"

PRICE_AVAILABLE = "PRICE_AVAILABLE"
PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
SECTOR_AVAILABLE = "AVAILABLE"
SECTOR_UNKNOWN = "UNKNOWN"
LIQUIDITY_PROXY = "LIQUIDITY_RESEARCH_PROXY"
LIQUIDITY_UNAVAILABLE = "LIQUIDITY_RESEARCH_UNAVAILABLE"
EXECUTION_BLOCKED = "EXECUTION_CAPACITY_EXACT_BLOCKED"
EXECUTION_READY = "EXECUTION_CAPACITY_EXACT_READY"
FA_ABSENT = "ABSENT"


class ScreenerMasterProjectionError(ValueError):
    """A required input contract or invariant of this projection is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def js_fallback(artifact: Mapping[str, Any]) -> str:
    """Pure serialized equivalent of the JSON artifact. Not a second source."""
    return f"{JS_GLOBAL} = {_canonical(artifact)};\n"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def display_exchange_for(listing_exchange: Any) -> dict[str, Any]:
    """Map official listing vocabulary onto approved display vocabulary.

    HNX_LISTED must never fall through to DELISTED. Unknown listing evidence is
    UNKNOWN, never an invented delisting.
    """
    listing = _upper(listing_exchange)
    if not listing:
        return {
            "listing_exchange": None,
            "display_exchange": None,
            "status": UNKNOWN,
            "reason": "LISTING_EXCHANGE_ABSENT",
        }
    display = LISTING_TO_DISPLAY.get(listing)
    if display is None:
        return {
            "listing_exchange": listing,
            "display_exchange": None,
            "status": UNKNOWN,
            "reason": f"LISTING_EXCHANGE_UNMAPPED:{listing}",
        }
    if listing == "HNX_LISTED" and display == "DELISTED":
        raise ScreenerMasterProjectionError("HNX_LISTED_FELL_THROUGH_TO_DELISTED")
    return {
        "listing_exchange": listing,
        "display_exchange": display,
        "status": AVAILABLE,
        "reason": None,
    }


def load_screen_snapshot_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ScreenerMasterProjectionError(f"SCREEN_SNAPSHOT_MISSING:{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ScreenerMasterProjectionError("SCREEN_SNAPSHOT_EMPTY")
    return rows


def load_vci_industry_labels(path: Path) -> dict[str, dict[str, Any]]:
    """Load retained VCI provider industry labels. Conflicts fail closed to UNKNOWN."""
    if not path.is_file():
        raise ScreenerMasterProjectionError(f"VCI_INDUSTRY_SNAPSHOT_MISSING:{path}")
    candidates: dict[str, list[dict[str, Any]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("provider") != VCI_INDUSTRY_PROVIDER or row.get("field") != VCI_INDUSTRY_FIELD:
            continue
        if not isinstance(row.get("value"), str) or not row["value"].strip():
            continue
        ticker = _upper(row.get("ticker"))
        if not ticker:
            continue
        candidates.setdefault(ticker, []).append(row)
    resolved: dict[str, dict[str, Any]] = {}
    for ticker, rows in candidates.items():
        labels = {" ".join(str(row["value"]).split()) for row in rows}
        if len(labels) != 1:
            resolved[ticker] = {
                "label": None,
                "status": UNKNOWN,
                "reason": "CONFLICTING_RETAINED_VCI_INDUSTRY_LABELS",
                "namespace": "VCI_PROVIDER_INDUSTRY",
                "as_of": None,
                "source_identity": None,
            }
            continue
        row = rows[0]
        resolved[ticker] = {
            "label": next(iter(labels)),
            "status": AVAILABLE,
            "reason": None,
            "namespace": "VCI_PROVIDER_INDUSTRY",
            "as_of": (row.get("timestamps") or {}).get("observed_at"),
            "source_identity": f"{ticker}:industry",
        }
    return resolved


def _session_from_snapshot(rows: Sequence[Mapping[str, Any]]) -> str:
    dates = [_text(row.get("date") or row.get("latest_price_date") or row.get("reference_market_date"))
             for row in rows]
    dates = [item for item in dates if item]
    if not dates:
        raise ScreenerMasterProjectionError("SCREEN_SNAPSHOT_SESSION_ABSENT")
    return max(dates)


def _price_view(row: Mapping[str, Any], *, session: str, source_identity: str | None) -> dict[str, Any]:
    value = _number(row.get("close"))
    change = _number(row.get("chg_today_pct"))
    observation = _text(row.get("canonical_observation_status")) or None
    basis = _text(row.get("canonical_price_basis")) or None
    as_of = _text(row.get("date") or row.get("latest_price_date")) or None
    if value is None:
        status = PRICE_UNAVAILABLE
        reason = observation or "UNAVAILABLE_NO_EXACT_SESSION_OBSERVATION"
        freshness = UNAVAILABLE
    else:
        status = PRICE_AVAILABLE
        reason = None
        freshness = CURRENT if as_of == session else (STALE_BUT_RESEARCH_USABLE if as_of else UNAVAILABLE)
    change_status = AVAILABLE if change is not None else (UNKNOWN if value is None else UNKNOWN)
    change_reason = None if change is not None else "SESSION_RETURN_ABSENT"
    return {
        "value": value,
        "change_pct": change,
        "change_pct_unit": "FRACTION",
        "change_pct_status": change_status,
        "change_pct_reason": change_reason,
        "status": status,
        "reason": reason,
        "basis": basis,
        "as_of": as_of,
        "source_identity": source_identity,
        "freshness": freshness,
    }


def _is_forbidden_sector_label(label: str) -> bool:
    folded = label.strip().casefold()
    return folded in ENTITY_CLASS_VOCABULARY or folded in FORBIDDEN_SYNTHETIC_SECTORS


def _sector_view(ticker: str, industry_by_ticker: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    record = industry_by_ticker.get(ticker)
    if not isinstance(record, Mapping):
        return {
            "label": None,
            "code": None,
            "namespace": "VCI_PROVIDER_INDUSTRY",
            "status": SECTOR_UNKNOWN,
            "reason": "NO_RETAINED_PROVIDER_INDUSTRY_LABEL",
            "as_of": None,
        }
    label = record.get("label")
    status = record.get("status") or (SECTOR_AVAILABLE if isinstance(label, str) and label.strip() else SECTOR_UNKNOWN)
    if not isinstance(label, str) or not label.strip():
        return {
            "label": None,
            "code": None,
            "namespace": record.get("namespace") or "VCI_PROVIDER_INDUSTRY",
            "status": SECTOR_UNKNOWN,
            "reason": record.get("reason") or "NO_RETAINED_PROVIDER_INDUSTRY_LABEL",
            "as_of": record.get("as_of"),
        }
    if _is_forbidden_sector_label(label):
        return {
            "label": None,
            "code": None,
            "namespace": record.get("namespace") or "VCI_PROVIDER_INDUSTRY",
            "status": SECTOR_UNKNOWN,
            "reason": f"ENTITY_CLASS_OR_SYNTHETIC_SECTOR_REJECTED:{label}",
            "as_of": record.get("as_of"),
        }
    if status != SECTOR_AVAILABLE:
        return {
            "label": None,
            "code": None,
            "namespace": record.get("namespace") or "VCI_PROVIDER_INDUSTRY",
            "status": SECTOR_UNKNOWN,
            "reason": record.get("reason") or "PROVIDER_INDUSTRY_NOT_AVAILABLE",
            "as_of": record.get("as_of"),
        }
    return {
        "label": label,
        "code": record.get("code"),
        "namespace": record.get("namespace") or "VCI_PROVIDER_INDUSTRY",
        "status": SECTOR_AVAILABLE,
        "reason": None,
        "as_of": record.get("as_of"),
    }


def _entity_type_view(ticker: str, entity_by_ticker: Mapping[str, Any], workspace_card: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = entity_by_ticker.get(ticker)
    if isinstance(raw, Mapping):
        value = raw.get("value") or raw.get("entity_class") or raw.get("entity_type")
        status = raw.get("status")
        reason = raw.get("reason")
    else:
        value = raw
        status = None
        reason = None
    if not isinstance(value, str) or not value.strip():
        if isinstance(workspace_card, Mapping):
            value = (workspace_card.get("valuation") or {}).get("entity_class")
    if isinstance(value, str) and value.strip():
        token = value.strip()
        folded = token.casefold()
        if folded in {"unknown", "unclassified"}:
            return {
                "value": None,
                "status": UNKNOWN,
                "reason": reason or "ENTITY_TYPE_UNKNOWN",
            }
        return {
            "value": folded if folded in ENTITY_CLASS_VOCABULARY else token,
            "status": status or AVAILABLE,
            "reason": reason,
        }
    return {
        "value": None,
        "status": status or UNKNOWN,
        "reason": reason or "ENTITY_TYPE_NOT_RETAINED",
    }


def _freshness_token(value: Any) -> str:
    if isinstance(value, Mapping):
        token = value.get("freshness_status") or value.get("status") or value.get("state")
    else:
        token = value
    if token in {CURRENT, STALE_BUT_RESEARCH_USABLE, STALE_NOT_USABLE_FOR_THIS_AXIS, UNAVAILABLE, MIXED, UNKNOWN}:
        return str(token)
    if not token:
        return UNAVAILABLE
    return str(token)


def _liquidity_view(
    ticker: str,
    *,
    workspace_card: Mapping[str, Any] | None,
    liquidity_by_ticker: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = liquidity_by_ticker.get(ticker) if isinstance(liquidity_by_ticker.get(ticker), Mapping) else {}
    card_liq = (workspace_card or {}).get("liquidity") if isinstance(workspace_card, Mapping) else {}
    if not isinstance(card_liq, Mapping):
        card_liq = {}
    method = record.get("method") or card_liq.get("readiness") or LIQUIDITY_UNAVAILABLE
    descriptive = (
        record.get("descriptive_state")
        or record.get("disposition")
        or card_liq.get("descriptive_research_state")
        or method
    )
    fitness = record.get("fitness") or method
    as_of = record.get("as_of") or record.get("session") or card_liq.get("source_session")
    # No qualified market-wide numeric VND ADV20 exists. Never invent close×volume GTGD.
    research_value = record.get("research_value")
    if research_value is not None:
        raise ScreenerMasterProjectionError(f"UNSUPPORTED_NUMERIC_RESEARCH_LIQUIDITY:{ticker}")
    if method in {LIQUIDITY_PROXY, "ELIGIBLE", "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE"} or descriptive in {
        "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "AVAILABLE", LIQUIDITY_PROXY,
    }:
        method = LIQUIDITY_PROXY
        status = AVAILABLE
        reason = None
    else:
        method = method or LIQUIDITY_UNAVAILABLE
        status = UNKNOWN
        reason = record.get("reason") or card_liq.get("reason") or "LIQUIDITY_RESEARCH_PROXY_NOT_QUALIFIED"
    liquidity = {
        "research_value": None,
        "research_value_status": UNKNOWN,
        "research_value_reason": "NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20",
        "method": method,
        "fitness": fitness or method,
        "as_of": as_of,
        "descriptive_state": descriptive,
        "status": status,
        "reason": reason,
    }
    execution_status = (
        record.get("capacity_exact_status")
        or record.get("exact_execution_capacity_status")
        or card_liq.get("exact_execution_capacity_status")
        or EXECUTION_BLOCKED
    )
    if execution_status in {"ELIGIBLE", EXECUTION_READY}:
        execution_status = EXECUTION_READY
        execution_reason = None
    else:
        execution_status = EXECUTION_BLOCKED
        execution_reason = (
            record.get("capacity_exact_reason")
            or card_liq.get("exact_execution_capacity_reason")
            or "EXECUTION_CAPACITY_EXACT_NOT_QUALIFIED"
        )
    execution = {
        "capacity_exact_status": execution_status,
        "capacity_exact_reason": execution_reason,
    }
    return liquidity, execution


def _tactical_view(workspace_card: Mapping[str, Any] | None, *, session: str) -> dict[str, Any]:
    if not isinstance(workspace_card, Mapping):
        return {
            "entry_state": None,
            "entry_action": None,
            "as_of": None,
            "freshness": UNAVAILABLE,
            "status": UNKNOWN,
            "reason": "WORKSPACE_CARD_ABSENT",
        }
    tactical = workspace_card.get("tactical") if isinstance(workspace_card.get("tactical"), Mapping) else {}
    entry_state = workspace_card.get("entry_state") or tactical.get("primary_entry_state")
    entry_action = workspace_card.get("entry_action") or tactical.get("entry_action")
    as_of = tactical.get("source_session") or workspace_card.get("as_of_session")
    freshness = _freshness_token(tactical.get("freshness_status") or (workspace_card.get("lineage") or {}).get("per_axis_freshness", {}).get("tactical"))
    if entry_state:
        return {
            "entry_state": entry_state,
            "entry_action": entry_action,
            "as_of": as_of or session,
            "freshness": freshness if freshness != UNAVAILABLE else CURRENT,
            "status": AVAILABLE,
            "reason": None,
        }
    return {
        "entry_state": None,
        "entry_action": entry_action,
        "as_of": as_of,
        "freshness": freshness,
        "status": UNKNOWN,
        "reason": "TACTICAL_ENTRY_STATE_ABSENT",
    }


def _research_view(workspace_card: Mapping[str, Any] | None, *, session: str, workspace_identity: str | None) -> dict[str, Any]:
    if not isinstance(workspace_card, Mapping):
        return {
            "stance": None,
            "stance_readiness": None,
            "as_of": None,
            "status": UNKNOWN,
            "reason": "WORKSPACE_CARD_ABSENT",
        }
    stance = workspace_card.get("research_stance")
    readiness = workspace_card.get("research_stance_readiness")
    as_of = workspace_card.get("as_of_session") or session
    if stance:
        return {
            "stance": stance,
            "stance_readiness": readiness,
            "as_of": as_of,
            "status": AVAILABLE,
            "reason": None,
        }
    return {
        "stance": None,
        "stance_readiness": readiness,
        "as_of": as_of,
        "status": UNKNOWN,
        "reason": "RESEARCH_STANCE_ABSENT",
    }


def _workspace_ref(ticker: str, workspace_card: Mapping[str, Any] | None, workspace_identity: str | None) -> dict[str, Any]:
    if not isinstance(workspace_card, Mapping):
        return {
            "ticker": ticker,
            "producer_artifact_identity": workspace_identity,
            "status": UNKNOWN,
            "reason": "WORKSPACE_CARD_ABSENT",
        }
    card_ticker = _upper(workspace_card.get("ticker") or ticker)
    if card_ticker != ticker:
        raise ScreenerMasterProjectionError(f"WORKSPACE_TICKER_IDENTITY_MISMATCH:{ticker}:{card_ticker}")
    return {
        "ticker": ticker,
        "producer_artifact_identity": workspace_identity,
        "status": AVAILABLE,
        "reason": None,
    }


def _financial_v2_view(ticker: str, financial_by_ticker: Mapping[str, Mapping[str, Any]], workspace_card: Mapping[str, Any] | None) -> dict[str, Any]:
    record = financial_by_ticker.get(ticker)
    if not isinstance(record, Mapping) and isinstance(workspace_card, Mapping):
        why = ((workspace_card.get("why") or {}).get("financial_analysis") or {})
        record = why.get("compact") if isinstance(why, Mapping) else None
        if record is None and isinstance(why, Mapping) and why.get("status"):
            record = {"status": why.get("status"), "reason": why.get("reason") or "FA_V2_CONTEXT_ABSENT"}
    if not isinstance(record, Mapping):
        return {
            "status": FA_ABSENT,
            "fitness": FA_ABSENT,
            "current_research_ready": False,
            "profitability_state": None,
            "cash_conversion_state": None,
            "capital_efficiency_state": None,
            "short_term_liquidity_state": None,
            "working_capital_state": None,
            "reason": "FA_V2_CONTEXT_ABSENT",
        }
    status = record.get("status") or FA_ABSENT
    working = record.get("working_capital_state")
    ready = record.get("current_research_ready") is True
    if status == FA_ABSENT:
        fitness = FA_ABSENT
        reason = record.get("reason") or "FA_V2_CONTEXT_ABSENT"
    elif ready:
        fitness = "READY"
        reason = None
    else:
        fitness = "RESEARCH_CONTEXT"
        reason = None
    return {
        "status": status,
        "fitness": fitness,
        "current_research_ready": ready,
        "profitability_state": record.get("profitability_state"),
        "cash_conversion_state": record.get("cash_conversion_state"),
        "capital_efficiency_state": record.get("capital_efficiency_state"),
        "short_term_liquidity_state": working,
        "working_capital_state": working,
        "reason": reason,
    }


def _row_freshness(parts: Mapping[str, str]) -> str:
    states = {token for token in parts.values() if token}
    if not states or states == {UNAVAILABLE}:
        return UNAVAILABLE
    if states == {CURRENT}:
        return CURRENT
    if STALE_NOT_USABLE_FOR_THIS_AXIS in states and CURRENT not in states and STALE_BUT_RESEARCH_USABLE not in states:
        return STALE_NOT_USABLE_FOR_THIS_AXIS
    if states <= {CURRENT, STALE_BUT_RESEARCH_USABLE}:
        return STALE_BUT_RESEARCH_USABLE if STALE_BUT_RESEARCH_USABLE in states else CURRENT
    return MIXED


def _assert_no_naked_required_null(card: Mapping[str, Any]) -> None:
    required = (
        ("price", card["price"]["value"], card["price"]["status"], card["price"].get("reason")),
        ("sector", card["sector"]["label"], card["sector"]["status"], card["sector"].get("reason")),
        ("entity_type", card["entity_type"]["value"], card["entity_type"]["status"], card["entity_type"].get("reason")),
        ("liquidity.research_value", card["liquidity"]["research_value"], card["liquidity"]["research_value_status"], card["liquidity"].get("research_value_reason")),
        ("tactical.entry_state", card["tactical"]["entry_state"], card["tactical"]["status"], card["tactical"].get("reason")),
        ("research.stance", card["research"]["stance"], card["research"]["status"], card["research"].get("reason")),
        ("display_exchange", card["display_exchange"], card["exchange_status"], card.get("exchange_reason")),
    )
    naked = [name for name, value, status, reason in required if value is None and not (status and (reason or status))]
    if naked:
        raise ScreenerMasterProjectionError(f"NAKED_REQUIRED_NULL:{card.get('ticker')}:{','.join(naked)}")


def _count_naked_required_null(cards: Mapping[str, Mapping[str, Any]]) -> int:
    count = 0
    for card in cards.values():
        checks = (
            (card["price"]["value"], card["price"]["status"], card["price"].get("reason")),
            (card["sector"]["label"], card["sector"]["status"], card["sector"].get("reason")),
            (card["entity_type"]["value"], card["entity_type"]["status"], card["entity_type"].get("reason")),
            (card["liquidity"]["research_value"], card["liquidity"]["research_value_status"], card["liquidity"].get("research_value_reason")),
            (card["tactical"]["entry_state"], card["tactical"]["status"], card["tactical"].get("reason")),
            (card["research"]["stance"], card["research"]["status"], card["research"].get("reason")),
            (card["display_exchange"], card["exchange_status"], card.get("exchange_reason")),
        )
        count += sum(1 for value, status, reason in checks if value is None and not (status and (reason or status)))
    return count


def build_ticker_card(
    *,
    ticker: str,
    snapshot_row: Mapping[str, Any],
    session: str,
    snapshot_identity: str | None,
    workspace_card: Mapping[str, Any] | None,
    workspace_identity: str | None,
    industry_by_ticker: Mapping[str, Mapping[str, Any]],
    entity_by_ticker: Mapping[str, Any],
    liquidity_by_ticker: Mapping[str, Mapping[str, Any]],
    financial_by_ticker: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    exchange = display_exchange_for(snapshot_row.get("listing_exchange"))
    price = _price_view(snapshot_row, session=session, source_identity=snapshot_identity)
    sector = _sector_view(ticker, industry_by_ticker)
    entity_type = _entity_type_view(ticker, entity_by_ticker, workspace_card)
    liquidity, execution = _liquidity_view(ticker, workspace_card=workspace_card, liquidity_by_ticker=liquidity_by_ticker)
    tactical = _tactical_view(workspace_card, session=session)
    research = _research_view(workspace_card, session=session, workspace_identity=workspace_identity)
    financial_v2 = _financial_v2_view(ticker, financial_by_ticker, workspace_card)
    freshness = {
        "price": price["freshness"],
        "sector": CURRENT if sector["status"] == SECTOR_AVAILABLE else UNAVAILABLE,
        "liquidity": CURRENT if liquidity["status"] == AVAILABLE else UNAVAILABLE,
        "tactical": tactical["freshness"],
        "research": CURRENT if research["status"] == AVAILABLE else UNAVAILABLE,
        "financial_v2": CURRENT if financial_v2["status"] == "AVAILABLE" else UNAVAILABLE,
    }
    freshness["row"] = _row_freshness(freshness)
    card = {
        "ticker": ticker,
        "listing_exchange": exchange["listing_exchange"],
        "display_exchange": exchange["display_exchange"],
        "exchange_status": exchange["status"],
        "exchange_reason": exchange["reason"],
        "price": price,
        "sector": sector,
        "entity_type": entity_type,
        "liquidity": liquidity,
        "execution": execution,
        "tactical": tactical,
        "research": research,
        "workspace_ref": _workspace_ref(ticker, workspace_card, workspace_identity),
        "financial_v2": financial_v2,
        "freshness": freshness,
        "authority_boundary": {
            "is_actionable": False,
            "no_score": True,
            "no_rank": True,
            "no_probability": True,
            "no_target_price": True,
            "research_stance_is_not_execution_order": True,
            "tactical_entry_is_not_buy": True,
            "data_ready_is_not_buy": True,
            "no_fake_gtgd": True,
            "no_close_times_volume_adv20": True,
        },
    }
    _assert_no_naked_required_null(card)
    return card


def _workspace_cards(workspace: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(workspace, Mapping):
        return {}
    cards = workspace.get("cards")
    if not isinstance(cards, Mapping):
        return {}
    return { _upper(ticker): card for ticker, card in cards.items() if isinstance(card, Mapping) }


def _financial_records(financial_v2: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(financial_v2, Mapping):
        return {}
    records = financial_v2.get("records")
    if not isinstance(records, Mapping):
        return {}
    return { _upper(ticker): record for ticker, record in records.items() if isinstance(record, Mapping) }


def build_projection(
    *,
    snapshot_rows: Sequence[Mapping[str, Any]],
    requested_at: str,
    as_of_session: str | None = None,
    snapshot_identity: str | None = None,
    workspace: Mapping[str, Any] | None = None,
    financial_v2: Mapping[str, Any] | None = None,
    industry_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
    entity_by_ticker: Mapping[str, Any] | None = None,
    liquidity_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
    official_universe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not snapshot_rows:
        raise ScreenerMasterProjectionError("EMPTY_SCREEN_SNAPSHOT_DENOMINATOR")
    seen: list[str] = []
    duplicates: set[str] = set()
    rows_by_ticker: dict[str, Mapping[str, Any]] = {}
    for row in snapshot_rows:
        ticker = _upper(row.get("ticker"))
        if not ticker:
            raise ScreenerMasterProjectionError("SCREEN_SNAPSHOT_TICKER_ABSENT")
        if ticker in rows_by_ticker:
            duplicates.add(ticker)
        seen.append(ticker)
        rows_by_ticker[ticker] = row
    if duplicates:
        raise ScreenerMasterProjectionError(f"SCREEN_SNAPSHOT_DUPLICATE_TICKERS:{','.join(sorted(duplicates))}")
    tickers = list(rows_by_ticker)
    session = as_of_session or _session_from_snapshot(snapshot_rows)
    workspace_cards = _workspace_cards(workspace)
    workspace_only = sorted(set(workspace_cards) - set(tickers))
    financial_records = _financial_records(financial_v2)
    industry = { _upper(key): value for key, value in (industry_by_ticker or {}).items() }
    entities = { _upper(key): value for key, value in (entity_by_ticker or {}).items() }
    liquids = { _upper(key): value for key, value in (liquidity_by_ticker or {}).items() }
    workspace_identity = workspace.get("artifact_identity") if isinstance(workspace, Mapping) else None

    official_records = {}
    if isinstance(official_universe, Mapping):
        raw = official_universe.get("records")
        if isinstance(raw, Mapping):
            official_records = { _upper(key): value for key, value in raw.items() if isinstance(value, Mapping) }

    cards: dict[str, Any] = {}
    for ticker in tickers:
        row = dict(rows_by_ticker[ticker])
        official = official_records.get(ticker)
        if isinstance(official, Mapping) and not _text(row.get("listing_exchange")):
            row["listing_exchange"] = official.get("exchange_or_market") or official.get("listing_exchange")
        cards[ticker] = build_ticker_card(
            ticker=ticker,
            snapshot_row=row,
            session=session,
            snapshot_identity=snapshot_identity,
            workspace_card=workspace_cards.get(ticker),
            workspace_identity=workspace_identity,
            industry_by_ticker=industry,
            entity_by_ticker=entities,
            liquidity_by_ticker=liquids,
            financial_by_ticker=financial_records,
        )
    if set(cards) != set(tickers):
        raise ScreenerMasterProjectionError("SILENT_TICKER_DROP")
    if any(extra in cards for extra in workspace_only):
        raise ScreenerMasterProjectionError("WORKSPACE_ONLY_TICKER_ADMITTED")

    naked = _count_naked_required_null(cards)
    if naked:
        raise ScreenerMasterProjectionError(f"NAKED_REQUIRED_NULL_COUNT:{naked}")

    priced = sum(card["price"]["status"] == PRICE_AVAILABLE for card in cards.values())
    unpriced = len(cards) - priced
    sector_available = sum(card["sector"]["status"] == SECTOR_AVAILABLE for card in cards.values())
    sector_unknown = len(cards) - sector_available
    hnx_listed = sum(card["listing_exchange"] == "HNX_LISTED" for card in cards.values())
    hnx_display = sum(card["listing_exchange"] == "HNX_LISTED" and card["display_exchange"] == "HNX" for card in cards.values())
    if hnx_listed and hnx_display != hnx_listed:
        raise ScreenerMasterProjectionError("HNX_LISTED_DISPLAY_REGRESSION")

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "as_of_session": session,
        "denominator": {
            "ticker_count": len(cards),
            "source": "canonical_screen_snapshot",
            "zero_duplicates": True,
            "workspace_only_extras_excluded": len(workspace_only),
        },
        "zero_silent_drops": True,
        "coverage": {
            "ticker_denominator": len(cards),
            "zero_silent_drops": True,
            "duplicate_count": 0,
            "workspace_only_extras_excluded": len(workspace_only),
            "price_available_count": priced,
            "price_unavailable_explicit_count": unpriced,
            "hnx_listed_count": hnx_listed,
            "hnx_listed_display_hnx_count": hnx_display,
            "sector_available_count": sector_available,
            "sector_unknown_count": sector_unknown,
            "entity_type_available_count": sum(card["entity_type"]["status"] == AVAILABLE for card in cards.values()),
            "research_liquidity_proxy_count": sum(card["liquidity"]["method"] == LIQUIDITY_PROXY for card in cards.values()),
            "numeric_liquidity_value_count": sum(card["liquidity"]["research_value"] is not None for card in cards.values()),
            "execution_capacity_exact_blocked_count": sum(card["execution"]["capacity_exact_status"] == EXECUTION_BLOCKED for card in cards.values()),
            "research_stance_available_count": sum(card["research"]["status"] == AVAILABLE for card in cards.values()),
            "tactical_available_count": sum(card["tactical"]["status"] == AVAILABLE for card in cards.values()),
            "financial_v2_available_count": sum(card["financial_v2"]["status"] == "AVAILABLE" for card in cards.values()),
            "financial_v2_absent_count": sum(card["financial_v2"]["status"] == FA_ABSENT for card in cards.values()),
            "workspace_join_count": sum(card["workspace_ref"]["status"] == AVAILABLE for card in cards.values()),
            "naked_required_null_count": 0,
            "research_stance_distribution": dict(sorted(Counter(card["research"]["stance"] or "NONE" for card in cards.values()).items())),
            "tactical_entry_state_distribution": dict(sorted(Counter(card["tactical"]["entry_state"] or "NONE" for card in cards.values()).items())),
        },
        "source_artifacts": {
            "screen_snapshot": snapshot_identity,
            "investment_decision_workspace": workspace_identity,
            "financial_analysis_product_integration": financial_v2.get("artifact_identity") if isinstance(financial_v2, Mapping) else None,
            "official_market_universe": official_universe.get("artifact_identity") if isinstance(official_universe, Mapping) else None,
        },
        "blocked_outputs": {
            "universal_score": "SCORING_PROHIBITED",
            "ordinal_rank": "RANKING_PROHIBITED",
            "probability_of_success": "FORECAST_PROHIBITED",
            "target_price": "NOT_EMITTED",
            "fake_gtgd20": "NOT_EMITTED",
            "close_times_volume_adv20": "NOT_COMPUTED",
            "entity_class_as_sector": "REJECTED",
            "synthetic_generic_sector": "REJECTED",
        },
        "cards": cards,
        "authority_effect": "NONE / PRESENTATION_READ_MODEL_ONLY",
    }
    artifact.update(content_identity(artifact))
    return artifact


def snapshot_tickers(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return [_upper(row.get("ticker")) for row in rows]
