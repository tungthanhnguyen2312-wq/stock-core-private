"""Bounded live refresh of the HNX_LISTED + UPCOM current issuer LIST surfaces only.

This milestone (CURRENT_OFFICIAL_MARKET_UNIVERSE_REFRESH_AND_SECURITY_STATUS_V1) needs a
current exchange-presence snapshot, not a rights/event-index refresh. The list surfaces
(``LISTS`` in ``hnx_enumerable_universe_kllh_event_disclosure_scaleout.py``) each return their
full result set on page 1 (confirmed live: HNX_LISTED and UPCOM both report ``total ==
len(first_page_rows)``) -- 4 bounded requests total (2 landing + 2 bulk).

The rights/event-index surfaces are a different story: HNX_LISTED paginates cleanly at 2 pages,
but UPCOM's rights endpoint enforces a small server-side page size regardless of the requested
``pNumRecord`` and requires 300+ sequential POSTs to exhaust -- confirmed live (103 pages fetched
in several minutes with no end in sight, matching the old retained artifact's own hardcoded
``expected_pages=327`` comment for this exact surface). That is not a bounded acquisition and is
not needed for this milestone's reconciliation math (``current_official_market_universe.
build_artifact`` reads the rights-event dataset only for one descriptive ``event_context_linkage``
summary field, never for the 1,683 reconciliation). So this script deliberately carries the
retained 2026-08-24 rights/event-index dataset forward unrefreshed rather than either fabricating
one or spending an unbounded number of live requests on an axis this milestone does not need;
resuming the UPCOM rights refresh remains a distinct, separately-scoped future acquisition
(pattern already established by ``tools/acquire_hnx_enumerable_event_slice.py``'s declared-slice
approach for exactly this kind of small-page-size, many-page HNX surface).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hnx_enumerable_universe_kllh_event_disclosure_scaleout import (
    BASE, LISTS, RIGHTS, fetch, retain, _content, _total, _identity, parse_list, parse_events,
)

OLD = ROOT / "operations-review" / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824" / "hnx_enumerable_universe_artifact.json"
OUT = ROOT / "operations-review" / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260913"


def main() -> None:
    old_artifact = json.loads(OLD.read_text(encoding="utf-8"))
    old_events = old_artifact["datasets"]["hnx_official_rights_event_index/v1"]
    old_disclosures = old_artifact["datasets"].get("hnx_official_disclosure_index/v1", [])
    old_coverage = old_artifact["coverage"]

    captures: list[dict] = []
    universe: list[dict] = []
    list_totals: dict[str, int] = {}
    for market, (landing, endpoint, code) in LISTS.items():
        landing_response = fetch(BASE + landing)
        if landing_response["http_status"] != 200:
            raise ValueError(f"LIST_LANDING_FETCH_FAILED:{market}")
        captures.append(retain(response=landing_response, destination=OUT, surface=f"{market.lower()}_list_landing", page=None, request_body=None))
        body = {"p_issearch": "0", "p_keysearch": "", "p_market_code": code, "p_orderby": "", "p_ordertype": "", "p_currentpage": "1", "p_record_on_page": "1000"}
        response = fetch(BASE + endpoint, body=body)
        if response["http_status"] != 200:
            raise ValueError(f"LIST_BULK_FETCH_FAILED:{market}")
        document = _content(response["data"])
        total = _total(document)
        capture = retain(response=response, destination=OUT, surface=f"{market.lower()}_list_bulk", page=1, request_body=body)
        captures.append(capture)
        rows = parse_list(document, market=market, capture=capture)
        if len(rows) != total:
            raise ValueError(f"LIST_ROW_COUNT_MISMATCH:{market}:{len(rows)}:{total}")
        list_totals[market] = total
        universe.extend(rows)
    if len({row["ticker"] for row in universe}) != len(universe):
        raise ValueError("CROSS_LIST_TICKER_DUPLICATE")

    from collections import Counter
    quantities = [row for row in universe if row["hnx_kllh_shares"] is not None and row["source_listing_or_registration_quantity"] is not None]
    kllh_relation = Counter("EQUAL" if row["hnx_kllh_shares"] == row["source_listing_or_registration_quantity"] else "LT" if row["hnx_kllh_shares"] < row["source_listing_or_registration_quantity"] else "GT" for row in quantities)
    event_types = Counter(row["event_type"] for row in old_events)

    stocklookup = json.loads((ROOT / "operations-review" / "current-universe-status-and-session-coverage-resolution-v1-20260911" / "current_universe_status_and_session_coverage_resolution_artifact.json").read_text(encoding="utf-8"))["records"]
    if len(stocklookup) != 1683:
        raise ValueError("STOCKLOOKUP_1683_UNIVERSE_CONTRACT_INVALID")
    hnx = {row["ticker"] for row in universe}
    sl = {str(t).upper() for t in stocklookup}

    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "hnx_enumerable_universe_kllh_event_and_disclosure_scaleout/v1",
        "captures": captures,
        "datasets": {
            "hnx_official_equity_universe/v1": universe,
            "hnx_official_rights_event_index/v1": old_events,
            "hnx_official_disclosure_index/v1": old_disclosures,
        },
        "dataset_freshness": {
            "hnx_official_equity_universe/v1": "LIVE_REFRESH_2026-09-13",
            "hnx_official_rights_event_index/v1": "CARRIED_FORWARD_FROM_2026-08-24_NOT_REFRESHED_THIS_MILESTONE",
            "hnx_official_disclosure_index/v1": "CARRIED_FORWARD_FROM_2026-08-24_NOT_REFRESHED_THIS_MILESTONE",
            "reason": (
                "UPCOM's rights/event endpoint enforces a small server-side page size regardless "
                "of the requested pNumRecord and requires 300+ sequential pages to exhaust -- not "
                "a bounded acquisition, and not read by current_official_market_universe.build_"
                "artifact's 1,683-ticker reconciliation math (only its descriptive event_context_"
                "linkage summary field). Left for a dedicated future acquisition using the existing "
                "declared-slice pattern (tools/acquire_hnx_enumerable_event_slice.py)."
            ),
        },
        "coverage": {
            "listed_source_total": list_totals["HNX_LISTED"], "upcom_source_total": list_totals["UPCOM"],
            "common_equity_candidates": len(universe), "non_common_equity": 0, "instrument_class_unresolved": 0,
            "kllh_present": sum(row["hnx_kllh_shares"] is not None for row in universe),
            "klny_present": sum(row["market"] == "HNX_LISTED" and row["source_listing_or_registration_quantity"] is not None for row in universe),
            "kldkgd_present": sum(row["market"] == "UPCOM" and row["source_listing_or_registration_quantity"] is not None for row in universe),
            "kllh_relation": dict(kllh_relation),
            "event_source_total": old_coverage.get("event_source_total"),
            "event_tickers": len({row["ticker"] for row in old_events}),
            "ex_date_qualified": sum(row["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED" for row in old_events),
            "ex_date_missing": sum(row["qualification"] == "MISSING_EX_DATE" for row in old_events),
            "event_types": dict(event_types),
            "disclosure_source_total": old_coverage.get("disclosure_source_total"),
            "disclosure_tickers": len({row["ticker"] for row in old_disclosures if row.get("ticker")}),
            "financial_disclosure_candidates": sum(row.get("financial_statement_candidate", False) for row in old_disclosures),
            "stocklookup_universe_count": len(sl), "intersection": len(hnx & sl), "stocklookup_only": len(sl - hnx),
            "hnx_official_only": len(hnx - sl), "identity_conflicts": 0,
        },
        "share_authority": "KLLH_AND_KLNY_OR_KLDKGD_REMAIN_SEPARATE_CURRENT_EXCHANGE_LIST_FIELDS_NOT_COMMON_SHARES_OUTSTANDING",
        "kllh_fitness_for_use": "NOT_FIT_FOR_COMMON_SHARES_MARKET_CAP_VALUATION_OR_SIZING",
        "authority_result": "ENUMERABLE_HNX_UNIVERSE_LIST_REFRESHED_LIVE_2026_09_13; EVENT_AND_DISCLOSURE_INDEXES_CARRIED_FORWARD_UNREFRESHED",
        "authority_boundary": "NO_COMMON_OUTSTANDING_SHARE_ALIAS_NO_PRICE_ADJUSTMENT_NO_RAW_AS_TRADED_NO_FINANCIAL_FACT_EXTRACTION",
        "missing_is_zero": False, "canonical_store_mutated": False, "network_used": True,
        "lane_terminal_status": "HNX_ENUMERABLE_LIST_REFRESH_V1_COMPLETE; EVENT_INDEX_REFRESH_OUT_OF_BOUNDED_SCOPE",
        "next_real_data_opportunity": "Bounded declared-slice refresh of the UPCOM rights/event index (300+ small pages) as its own separately-scoped acquisition job.",
    }
    digest = _identity(artifact)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "hnx_enumerable_universe_kllh_event_disclosure_scaleout:" + digest

    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "hnx_enumerable_universe_artifact.json"
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print("coverage:", artifact["coverage"])


if __name__ == "__main__":
    main()
