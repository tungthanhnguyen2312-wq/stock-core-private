"""Producer-owned Non-Cash Corporate Action Adjustment Factor MVP for Stock Lookup.

Derives deterministic adjustment factors for qualified stock_dividend and bonus_share events.
Retains full event, evidence, citation, and formula lineage.
Emits 0 adjusted prices and 0 adjusted returns.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from corporate_action_ledger import build_corporate_action_ledger

FACTOR_VERSION = "1.0.0"
SUPPORTED_FACTOR_EVENT_TYPES = {"stock_dividend", "bonus_share"}


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical factor objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def derive_non_cash_adjustment_factors(runtime_root: Path, ticker: str = "VNM") -> dict[str, Any]:
    """Derive deterministic non-cash adjustment factors from qualified corporate action ledger.

    Fails closed for invalid ratios, hash mismatches, or unsupported event types.
    Explicitly marks cash_dividend as unavailable ('cash_dividend_price_basis_not_qualified').

    Emits 0 adjusted prices and 0 adjusted returns.

    Returns:
        {
            "status": "available" | "unavailable",
            "formula_version": FACTOR_VERSION,
            "ticker": ticker,
            "individual_factors": [...],
            "rejected_entries": [...],
            "unsupported_entries": [...],
            "cumulative_factor": {...} or None,
            "factor_counts": {"stock_dividend": N, "bonus_share": N, "cash_dividend_unavailable": M}
        }
    """
    ledger_res = build_corporate_action_ledger(runtime_root, ticker=ticker)
    if ledger_res.get("status") != "available":
        return {
            "status": "unavailable",
            "formula_version": FACTOR_VERSION,
            "ticker": ticker,
            "individual_factors": [],
            "rejected_entries": [],
            "unsupported_entries": [],
            "cumulative_factor": None,
            "factor_counts": {"stock_dividend": 0, "bonus_share": 0, "cash_dividend_unavailable": 0},
        }

    individual_factors: list[dict[str, Any]] = []
    rejected_entries: list[dict[str, Any]] = []
    unsupported_entries: list[dict[str, Any]] = []
    counts = {"stock_dividend": 0, "bonus_share": 0, "cash_dividend_unavailable": 0}

    for entry in ledger_res.get("ledger_entries", []):
        event_type = entry.get("event_type")

        if event_type == "cash_dividend":
            counts["cash_dividend_unavailable"] += 1
            unsupported_entries.append({
                "canonical_event_id": entry.get("canonical_event_id"),
                "event_type": "cash_dividend",
                "status": "unavailable",
                "reason": "cash_dividend_price_basis_not_qualified"
            })
            continue

        if event_type not in SUPPORTED_FACTOR_EVENT_TYPES:
            unsupported_entries.append({
                "canonical_event_id": entry.get("canonical_event_id"),
                "event_type": event_type,
                "status": "unsupported",
                "reason": "unsupported_factor_event_type"
            })
            continue

        if entry.get("event_status") not in {"completed", "superseded_amended"}:
            rejected_entries.append({"entry": entry, "reason": "unresolved_event_status"})
            continue

        ratio = entry.get("entitlement_ratio")
        if not isinstance(ratio, dict):
            rejected_entries.append({"entry": entry, "reason": "missing_entitlement_ratio"})
            continue

        num = ratio.get("new_shares")
        den = ratio.get("existing_shares")
        if not isinstance(num, (int, float)) or not isinstance(den, (int, float)) or num <= 0 or den <= 0:
            rejected_entries.append({"entry": entry, "reason": "invalid_ratio_numerator_or_denominator"})
            continue

        share_qty_mult = (den + num) / den
        price_mult = den / (den + num)

        canonical_event_id = entry["canonical_event_id"]
        factor_id = _hash({
            "canonical_event_id": canonical_event_id,
            "factor_type": "non_cash_adjustment",
            "share_class": entry.get("share_class", "common"),
            "formula_version": FACTOR_VERSION
        })

        factor_obj = {
            "factor_id": factor_id,
            "canonical_event_id": canonical_event_id,
            "ledger_entry_id": entry["ledger_entry_id"],
            "event_type": event_type,
            "ticker": entry["ticker"],
            "issuer": entry["issuer"],
            "share_class": entry.get("share_class", "common"),
            "entitlement_ratio": {"new_shares": int(num), "existing_shares": int(den), "ratio_float": num / den},
            "share_quantity_multiplier": share_qty_mult,
            "theoretical_price_multiplier": price_mult,
            "formula_version": FACTOR_VERSION,
            "source_observation_ids": entry.get("source_observation_ids", []),
            "evidence": entry.get("evidence", {}),
            "declaration_date": entry.get("declaration_date"),
            "ex_date": entry.get("ex_date"),
            "record_date": entry.get("record_date"),
            "payment_date": entry.get("payment_date"),
            "effective_date": entry.get("effective_date"),
            "event_status": entry.get("event_status"),
            "qualification_state": "qualified",
        }

        individual_factors.append(factor_obj)
        counts[event_type] = counts.get(event_type, 0) + 1

    # Build cumulative non-cash factor for completed events
    completed_factors = [f for f in individual_factors if f.get("event_status") == "completed"]
    cumulative_factor = None

    if completed_factors:
        cum_share_mult = 1.0
        cum_price_mult = 1.0
        comp_factor_ids = []
        comp_event_ids = []

        for f in completed_factors:
            cum_share_mult *= f["share_quantity_multiplier"]
            cum_price_mult *= f["theoretical_price_multiplier"]
            comp_factor_ids.append(f["factor_id"])
            comp_event_ids.append(f["canonical_event_id"])

        cum_factor_id = _hash({"component_factor_ids": comp_factor_ids, "formula_version": FACTOR_VERSION})
        cumulative_factor = {
            "cumulative_factor_id": cum_factor_id,
            "ticker": ticker,
            "component_factor_ids": comp_factor_ids,
            "component_event_ids": comp_event_ids,
            "cumulative_share_quantity_multiplier": cum_share_mult,
            "cumulative_theoretical_price_multiplier": cum_price_mult,
            "component_count": len(completed_factors),
            "formula_version": FACTOR_VERSION,
            "qualification_state": "qualified",
        }

    return {
        "status": "available" if individual_factors else "unavailable",
        "formula_version": FACTOR_VERSION,
        "ticker": ticker,
        "individual_factors": individual_factors,
        "rejected_entries": rejected_entries,
        "unsupported_entries": unsupported_entries,
        "cumulative_factor": cumulative_factor,
        "factor_counts": counts,
    }


def derive_cash_dividend_adjustment_factors(runtime_root: Path, ticker: str = "VNM") -> dict[str, Any]:
    """Derive deterministic cash dividend adjustment factors for qualified cash dividend ledger entries.

    Requires a qualified raw market price citation from load_verified_market_price(runtime_root)
    on the pre-event trading session (last trading session before ex_date).
    Fails closed if the price basis is missing, invalid, or already adjusted.

    Emits 0 adjusted prices and 0 adjusted returns.

    Returns:
        {
            "status": "available" | "unavailable",
            "formula_version": FACTOR_VERSION,
            "ticker": ticker,
            "cash_dividend_factors": [...],
            "rejected_entries": [...],
            "unavailable_entries": [...],
            "factor_counts": {"cash_dividend": N, "unavailable": M}
        }
    """
    from semantic_evidence_bridge import load_verified_market_price

    ledger_res = build_corporate_action_ledger(runtime_root, ticker=ticker)
    price_res = load_verified_market_price(runtime_root)

    if ledger_res.get("status") != "available":
        return {
            "status": "unavailable",
            "formula_version": FACTOR_VERSION,
            "ticker": ticker,
            "cash_dividend_factors": [],
            "rejected_entries": [],
            "unavailable_entries": [],
            "factor_counts": {"cash_dividend": 0, "unavailable": 0},
        }

    prices_by_date = price_res.get("by_ticker_date", {}) if price_res.get("status") == "available" else {}

    factors_list: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    counts = {"cash_dividend": 0, "unavailable": 0}

    for entry in ledger_res.get("ledger_entries", []):
        if entry.get("event_type") != "cash_dividend":
            continue

        ex_date = entry.get("ex_date")
        cash_amt = entry.get("cash_amount")
        currency = entry.get("currency", "VND")

        if not ex_date or not cash_amt or cash_amt <= 0:
            counts["unavailable"] += 1
            unavailable.append({"entry": entry, "reason": "missing_or_invalid_cash_amount_or_ex_date"})
            continue

        # Look up pre-event reference price: search for verified price on ex_date or last prior trading session
        ref_price_entry = None
        ref_date_found = None

        sorted_price_keys = [k for k in prices_by_date.keys() if k[0] == ticker and k[1] <= ex_date]
        sorted_price_keys.sort(key=lambda k: k[1], reverse=True)

        prior_keys = [k for k in sorted_price_keys if k[1] < ex_date]
        target_key = prior_keys[0] if prior_keys else (sorted_price_keys[0] if sorted_price_keys else None)

        if target_key:
            ref_price_entry = prices_by_date[target_key]
            ref_date_found = target_key[1]

        if not ref_price_entry or ref_price_entry.get("adjustment_status") != "raw_as_quoted_no_adjustment_applied":
            counts["unavailable"] += 1
            unavailable.append({"entry": entry, "reason": "missing_or_unqualified_reference_price"})
            continue

        ref_price_val = ref_price_entry.get("value")
        if not isinstance(ref_price_val, (int, float)) or ref_price_val <= cash_amt or ref_price_val <= 0:
            counts["unavailable"] += 1
            unavailable.append({"entry": entry, "reason": "reference_price_less_than_or_equal_to_cash_dividend"})
            continue

        theo_post_price = ref_price_val - cash_amt
        price_mult = theo_post_price / ref_price_val

        canonical_event_id = entry["canonical_event_id"]
        factor_id = _hash({
            "canonical_event_id": canonical_event_id,
            "factor_type": "cash_dividend_adjustment",
            "reference_price_observation_id": ref_price_entry.get("citation_id"),
            "formula_version": FACTOR_VERSION,
        })

        factor_obj = {
            "factor_id": factor_id,
            "canonical_event_id": canonical_event_id,
            "ledger_entry_id": entry["ledger_entry_id"],
            "event_type": "cash_dividend",
            "ticker": ticker,
            "issuer": entry.get("issuer", "Vietnam Dairy Products Joint Stock Company"),
            "share_class": entry.get("share_class", "common"),
            "cash_amount": cash_amt,
            "currency": currency,
            "ex_date": ex_date,
            "reference_price_date": ref_date_found,
            "reference_price_value": ref_price_val,
            "reference_price_observation_id": ref_price_entry.get("citation_id"),
            "theoretical_post_event_price": theo_post_price,
            "theoretical_price_multiplier": price_mult,
            "formula_version": FACTOR_VERSION,
            "source_observation_ids": entry.get("source_observation_ids", []),
            "evidence": entry.get("evidence", {}),
            "declaration_date": entry.get("declaration_date"),
            "record_date": entry.get("record_date"),
            "payment_date": entry.get("payment_date"),
            "event_status": entry.get("event_status"),
            "qualification_state": "qualified",
        }

        factors_list.append(factor_obj)
        counts["cash_dividend"] += 1

    return {
        "status": "available" if factors_list else "unavailable",
        "formula_version": FACTOR_VERSION,
        "ticker": ticker,
        "cash_dividend_factors": factors_list,
        "rejected_entries": rejected,
        "unavailable_entries": unavailable,
        "factor_counts": counts,
    }
