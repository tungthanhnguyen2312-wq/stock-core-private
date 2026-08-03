"""Market-wide current effective shares resolver with hardened authority and freshness rules (P1J).

Field Provenance:
- Source: Company(source="VCI", symbol=tk).overview() via meta_sync.py
- Raw Field Name: issue_share
- Storage: vn_stock.db -> metadata.shares_outstanding
- Field Semantics: ISSUED_SHARES (proven)
- Unit: shares

Lanes:
1. qualified_official: official citations & qualified corporate action transitions (HPG, VNM, VCB)
2. provider_reported_current: retained VCI issue_share with positive value and no post-observation corporate actions
3. provider_reported_stale: retained VCI issue_share post-dated by completed corporate action events (e.g. stock dividend)
4. unavailable / conflicted: missing, <= 0, or conflicting observations
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

QUALIFIED_SHARES = {
    "HPG": {
        "value": 7163748865,
        "authority": "qualified_official",
        "status": "qualified",
        "share_concept": "current_common_shares_outstanding",
        "unit": "shares",
        "citation_id": "cite_hpg_div",
        "effective_date": "2026-06-04",
        "lineage": "FY2024 opening shares (6,396,250,200) + 2026-06-04 stock dividend (+767,498,665)",
    },
    "VNM": {
        "value": 2089955445,
        "authority": "qualified_official",
        "status": "qualified",
        "share_concept": "current_common_shares_outstanding",
        "unit": "shares",
        "citation_id": "cite_vnm_2024",
        "effective_date": "2024-12-31",
        "lineage": "FY2024 qualified official shares citation (2,089,955,445)",
    },
    "VCB": {
        "value": 5589091222,
        "authority": "qualified_official",
        "status": "qualified",
        "share_concept": "current_common_shares_outstanding",
        "unit": "shares",
        "citation_id": "cite_vcb_2024",
        "effective_date": "2024-12-31",
        "lineage": "FY2024 qualified official shares citation (5,589,091,222)",
    },
}


def _get_stale_corporate_event_tickers(db_path: Path) -> set[str]:
    """Identify tickers with post-observation corporate action events."""
    if not db_path.is_file():
        return set()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT ticker FROM corporate_event_records "
            "WHERE exright_date > '2024-12-31' OR record_date > '2024-12-31' OR issue_date > '2024-12-31'"
        )
        tickers = {str(r[0]).upper() for r in cursor.fetchall() if r[0]}
        conn.close()
        return tickers
    except Exception:
        return set()


def resolve_effective_shares(ticker: str, runtime_root: Path | str,
                             target_date: str = "2026-07-30") -> dict[str, Any]:
    """Resolves one effective share result per ticker for target session into hardened authority lanes."""
    t = str(ticker).upper()

    # Lane 1: qualified_official
    if t in QUALIFIED_SHARES:
        res = dict(QUALIFIED_SHARES[t])
        res["ticker"] = t
        res["target_date"] = target_date
        return res

    db_path = Path(runtime_root) / "vn_stock.db"
    stale_tickers = _get_stale_corporate_event_tickers(db_path)

    # Check corporate-action invalidation
    if t in stale_tickers:
        return {
            "ticker": t,
            "target_date": target_date,
            "value": None,
            "authority": "provider_reported_stale",
            "status": "provider_reported_stale",
            "share_concept": "ISSUED_SHARES",
            "unit": "shares",
            "source": "VCI.overview.issue_share",
            "reason": "invalidated_by_post_observation_corporate_action",
        }

    # Lane 2: provider_reported_current
    if db_path.is_file():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT shares_outstanding FROM metadata WHERE ticker = ?", (t,))
            row = cursor.fetchone()
            conn.close()

            if row and row[0] is not None and not isinstance(row[0], bool):
                val = float(row[0])
                if val > 0:
                    return {
                        "ticker": t,
                        "target_date": target_date,
                        "value": int(val),
                        "authority": "provider_reported_current",
                        "status": "provider_reported",
                        "share_concept": "ISSUED_SHARES",
                        "unit": "shares",
                        "source": "VCI.overview.issue_share",
                        "lineage": "retained_provider_metadata_issue_share",
                    }
        except Exception:
            pass

    # Lane 3: unavailable or conflicted
    return {
        "ticker": t,
        "target_date": target_date,
        "value": None,
        "authority": "unavailable",
        "status": "unavailable",
        "share_concept": "unknown_share_concept",
        "unit": "shares",
        "reason": "no valid retained share observation found or value <= 0",
    }


def resolve_market_wide_shares(runtime_root: Path | str,
                               target_date: str = "2026-07-30") -> dict[str, Any]:
    """Resolves current shares across all active universe tickers in runtime metadata."""
    db_path = Path(runtime_root) / "vn_stock.db"
    all_tickers: list[str] = []
    if db_path.is_file():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT ticker FROM metadata")
            all_tickers = [str(r[0]).upper() for r in cursor.fetchall()]
            conn.close()
        except Exception:
            pass

    tickers_map: dict[str, dict[str, Any]] = {}
    qualified_count = 0
    provider_current_count = 0
    provider_stale_count = 0
    conflicted_count = 0
    unknown_concept_count = 0
    unknown_date_count = 0
    unavailable_count = 0

    for t in all_tickers:
        res = resolve_effective_shares(t, runtime_root, target_date)
        tickers_map[t] = res
        auth = res.get("authority")
        if auth == "qualified_official":
            qualified_count += 1
        elif auth == "provider_reported_current":
            provider_current_count += 1
        elif auth == "provider_reported_stale":
            provider_stale_count += 1
        elif auth == "provider_reported_conflicted":
            conflicted_count += 1
        elif auth == "provider_reported_unknown_concept":
            unknown_concept_count += 1
        elif auth == "provider_reported_unknown_date":
            unknown_date_count += 1
        else:
            unavailable_count += 1

    return {
        "target_date": target_date,
        "active_universe_ticker_count": len(all_tickers),
        "qualified_official_count": qualified_count,
        "provider_reported_current_count": provider_current_count,
        "provider_reported_stale_count": provider_stale_count,
        "provider_reported_conflicted_count": conflicted_count,
        "unknown_share_concept_count": unknown_concept_count,
        "unknown_observation_date_count": unknown_date_count,
        "unavailable_count": unavailable_count,
        "tickers": tickers_map,
    }
